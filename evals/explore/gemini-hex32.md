# Explore: hex-32 ID validator and exact packer (Gemini → Opus)

Branch `explore/gemini-hex32`, off `3671aeb`. The code is the standalone `src/hex32.rs`. `main.rs` only gains `#[allow(dead_code)] mod hex32;`, so the engine is unchanged.

## Why
Since the 21:08 ET generator change (`docs/rules.md` line 101), 1 in 8 distinct user, event and click IDs is a prefix letter plus 32 lowercase hex digits, 33 bytes in all. `pack_fast` takes at most 10 characters, so every one of these goes through the mutex-sharded `Ids::intern`. That costs v5 0.42 s → 1.14 s at 20M.

**Prefix correction:** click IDs start with `k`, not `c`. Real rows look like `k5d2c63d12d02230abdafecbc22c307a0`, and the generator does `out.push(b'k')`. The prefixes are `u` (user), `e` (event) and `k` (click). The kernel accepts `c e k u`.

Dev-data check (the first two part files of each table): every 33-byte ID field matches `[ceku][0-9a-f]{32}`. The exception is one upper-cased link side (`U…`, from link dirt), which `parse` rejects, so it still goes through `intern` and the result stays exact. No ID has a length from 11 to 32.

| field | 33-byte hex | short (≤ 10) |
|---|---:|---:|
| events `event_id` | 4,622 | 32,340 |
| events `user_id` | 4,470 | 32,489 |
| clicks `click_id` | 946 | 6,450 |
| clicks `user_id` | 933 | 6,460 |
| links sides | 720 (+1 `U…`) | 5,555 |

## API (`src/hex32.rs`)
- `parse(b) -> Option<(u8, u128)>`: returns `Some((b[0], value))` iff `b.len() == 33`, `b[0]` is in `c e k u`, and every byte of `b[1..]` is in `[0-9a-f]`. `value` is the 32 digits as one big-endian hex number. This is exact and invertible.
- `parse_with(b, prefix) -> Option<u128>`: the same, but `b[0]` must equal `prefix`. This is the one the field parsers want: for `user_id` call `parse_with(b, b'u')`, and a hit means the key is `value` alone.
- `write(prefix, value, &mut [u8; 33])`: the inverse, used when writing a person's name.
- `head_key(prefix, value) -> u64` and `cmp_short_long(short_key, prefix, value)`: comparison against short packed keys (see Ordering).
- `tag2(prefix)`: `c e k u` → 0..=3, in byte order.
- `self_test() -> bool`: checks the SIMD path against the scalar path on about 25k inputs. Use it as a startup guard, like `pack_simd_self_test`.
- `parse_scalar`: the portable reference.

## Ordering: how to keep byte-wise order exact
1. **Same prefix:** u128 order equals the strings' byte order. The width is fixed at 32 digits, and digit order matches ASCII (`'0'..'9' < 'a'..'f'`).
2. **Different prefixes:** the prefix byte alone decides (`c < e < k < u`). If needed, `tag2` packs the prefix into 2 bits as the high-order part of the key.
3. **Short packed ID `S` (key `pack(S)`) vs long ID `H`:** `S < H` iff `pack(S) <= head_key(H)`. Here `head_key(H) = pack(H[..10])`. If the two keys are equal, `S` is a proper prefix of `H`, so `S` is shorter and smaller. Otherwise the zero-padded 6-bit codes differ first at the first differing byte, exactly as the strings do. The two can never be equal: the lengths are 1..=10 versus 33. Tested against `pack` for every proper prefix of 400 long IDs and for one-byte variants at each position.
4. **Interned IDs** (uppercase, `_`, other widths): compare bytes, rebuilding the long ID with `write`.

So a person-name minimum or a `click_id` tiebreak can compare short against short (u64), long against long (u128, after checking the prefix), and short against long (one `head_key`) without touching `intern`.

## Kernel
NEON and SSSE3, branch-free apart from the two exits:
- Two unaligned 16-byte loads of `b[1..17]` and `b[17..33]`. Both are inside the slice, so no page check is needed.
- Classification by nibble tables, as in `pack_simd`. `LO[lo] & HI[hi] != 0` accepts exactly `0x30..=0x39` and `0x61..=0x66`.
- One horizontal test: `cmeq` / `orr` / `addp` on NEON, and `vptestnmb` + `kortestw` on cascadelake.
- Digit value = `lo + OFF[hi]` (9 for row 6).
- Pair-merge to bytes: `shl #4` + `usra #8` and `uzp1` on NEON, or `pmaddubsw ×0x0110` and `packuswb` on SSSE3.
- Two `rev`s or `movbe`s to get big-endian order.

The scalar fallback, used for x86 without SSSE3, is a 32-step `HEXVAL` table loop.

### Instructions per call
Static count of an `#[inline(never)]` wrapper around `parse_with(b, b'u')`, all on the accept path, which runs straight through:

| target | accept path | reject (bad digit) | note |
|---|---:|---:|---|
| aarch64 (apple-m1) | 47 | 31 | includes 3 adrp+ldr table loads and about 6 Option-return stores |
| x86_64 cascadelake | 42 | 28 | `vptestnmb`/`kortestw`, `movbe` stores |

Once inlined into a parse loop, the table loads and the return stores go away, leaving about 35 (NEON) and about 33 (x86). The prefix and length check costs 4 of these. For comparison, `xxh3_64` of 33 bytes plus a locked `HashMap` probe in `intern` costs hundreds of instructions plus a lock round trip.

### Timing
`hex32bench` (an ignored test), run 3 times under the bench lock on Apple M-series aarch64. The loop runs over 4,096 distinct 33-byte `u` IDs (135 KB, L2-resident) and calls through a `&dyn Fn`, so the figures include an indirect call each time:

| path | ns/call (3 runs) |
|---|---|
| `parse`, accept | 2.69 / 2.63 / 2.77 |
| `parse_with`, accept | 2.87 / 3.45 / 2.82 |
| `parse_scalar`, accept | 17.1 / 16.3 / 18.5 |
| `parse`, reject (uppercase last digit) | 1.75 / 1.67 / 1.98 |

That makes SIMD about 6× faster than the scalar loop, at about 9–10 cycles per call including the call overhead. At 20M rows, with about 12.5% long IDs over three ID fields, that is about 7.5M calls, or about 20 ms core time spread over 8 threads. That is noise next to `intern`.

## Correctness
`cargo test --release hex32` gives 7/7. These tests ran natively on aarch64 (NEON), and under linux/amd64 emulation in Docker with `-C target-cpu=x86-64-v2` (SSSE3 path) and `-C target-cpu=x86-64` (scalar fallback). They cover:
- **every_position_every_byte:** all 256 byte values at each of the 33 positions, on 4 bases (34k cases). The SIMD result equals the scalar one, it is `Some` iff the byte class is right, and it round-trips through `write`. Uppercase `A`–`F` at any digit position is rejected.
- **pairs_of_bad_bytes:** every pair of positions × 12 bad bytes (`A F G g / : `` ` `` , "` and high bytes).
- **wrong_lengths_and_prefixes:** lengths 0..=34 (only 33 passes); 32 bare hex digits; prefixes `U E K C 0 a f p _ space`; a slice shorter than its buffer.
- **roundtrip_and_value:** 80k random values × 4 prefixes, plus 0 and `u128::MAX`.
- **order_matches_bytes**, **short_vs_long_order:** as above.
- **self_test_passes.**

The engine is unchanged (dead module), so fixtures and dev MATCH carry over from `3671aeb`. They need re-running once Method wires the kernel in.

## Porting into `Ids::key` (for Method's u128 plumbing)
```rust
// in the field parser, before pack_fast / intern:
if b.len() == 33 {
    if let Some(v) = hex32::parse_with(b, b'u') {   // b'e' event_id, b'k' click_id
        return Key::Long(v);                          // exact; prefix implied by the field
    }
}
```
- Check `len == 33` first, inline, so short IDs pay one compare.
- A `u` + hex string appearing in a non-user field, or any other surprise, gets `None` and falls through to `intern`, so the result stays exact.
- Gate the kernel on `hex32::self_test()` at startup, exactly like `simd_pack`.
- To print a person's name, use `hex32::write(b'u', v, &mut buf)`.
- To sort or take the minimum with mixed widths, use rules 1–4 above. If a single u128 sort key is needed for mixed short and long user IDs, note that `head_key` alone is not injective (all long IDs with the same first 10 bytes collide). Rank by `(head_key, is_long, value)` instead. That order matches byte order for short-vs-long (rule 3) and long-vs-long (equal head means equal prefix and first 9 digits, and the value decides).

## Verdict
Ready to drop in. It is exact by construction and covered by exhaustive per-position tests on all three code paths. It costs about 35 instructions per long ID, against a sharded-mutex intern. The win comes from Method removing these IDs from `intern`. That should take most of the 0.42 → 1.14 s regression back out, to be measured on `method/v5` once the plumbing lands.
