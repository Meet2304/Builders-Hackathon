# Verify v7: the lock-free long-ID path (Analyst 2)

Independent verifier for Method's move 6 on `method/v5`. All data here is from the **new generator**
(21:08 ET, `docs/rules.md` line 101): 1 in 8 distinct `user_id` / `event_id` / `click_id` values is a
prefix letter plus 32 lowercase hex characters (33 bytes). The base is v5 `3671aeb` (the v7 base before
move 6).

## 1. How much of v5 goes to `Ids::intern` (new seed-42, 21,505,895 event lines, 5,149,640 click lines)

### Call counts (instrumented copy of `3671aeb`; counters only, no logic change)

| Phase    | `intern` calls | of which 33-byte lowercase hex | other (dirty, uppercase…) |
| -------- | -------------: | -----------------------------: | ------------------------: |
| links    | 221,997        | 221,882                        | 115                       |
| events   | 5,520,769      | 5,520,747                      | 22                        |
| clicks   | 1,307,055      | 1,307,051                      | 4                         |
| **total**| **7,049,821**  | **7,049,680**                  | **141**                   |

- Distinct interned strings: **3,301,710**, so 53% of calls hit an existing entry.
- Per line: 0.257 `intern` calls per event line (about 12.8% of the eid + user lookups), and 0.254 per click line.
- `Ids::cmp` slow path (at least one interned side): 197,927 in links union-find, plus 67,785 in
  sessions (click tie-breaks). `Ids::bytes` slow path: 211,827 (links) + 90,495 (sessions) + 294,671
  (output `user_id` strings). Each of those takes a shard **lock** in v5.
- Only 141 calls (0.002%) are not 33-byte lowercase hex. These are the uppercase and dirty IDs, and they
  must stay on the exact fallback.

### Counterfactuals (same commit, only `intern` changed; output deliberately wrong, timing only)

- `vtl`: the same xxh3 plus a 64-way `HashMap<&[u8],u32>` insert, into **thread-local** maps (no lock and no
  sharing; it keeps the map and cache work).
- `vnolock`: `key = xxh3(bytes) << 4 | 1`, with no map at all (the ideal lower bound for a fixed-width
  encoding).

Instructions per event line (macOS `ri_instructions`, warm cache, robust to load):

| Phase        | v5 NCPU=1 | vnolock NCPU=1 | Δ     | v5 NCPU=8 | vnolock NCPU=8 | Δ        |
| ------------ | --------: | -------------: | ----: | --------: | -------------: | -------: |
| lookups      | 35.3      | 27.0           | −8    | 36.6      | 27.8           | −9       |
| events parse | 834.8     | 744.5          | **−90** | 916.3   | 753.1          | **−163** |
| clicks parse | 155.3     | 135.3          | −20   | 184.8     | 138.2          | −47      |
| whole run    | 1,423.7   | 1,310.0        | −114  | 1,557.7   | 1,291.7        | **−266** |

- At NCPU=1, `intern` costs about 350 instructions per call (90 × 21.5M / 5.52M): xxh3, a second foldhash,
  the probe, the insert, lock and unlock, and the `Vec` push.
- At NCPU=8, events parse grows by another 73 instructions per line, and clicks by 27. Under contention
  the spin and park loops of the std `Mutex` retire instructions too.
- **CPU time is the bigger signal.** Events parse used 3.90 s of CPU in v5 against 2.09 s for vnolock at
  NCPU=1: 46% of the phase's single-thread CPU, with no contention at all. Each new insert misses the
  cache on a hash table that grows to 3.3M entries.
- Native NCPU=8 walls (machine load 40–60, so these are indicative only): events parse 2.73 s → 0.57 s,
  clicks 1.29 s → 0.18 s. In v5 the 8 threads average about 1.9 busy cores during events parse.
  They're parked on the shard locks.

(gVisor timing of v5 vs v7 is Explorer 5's job, per the Orchestrator; it is not repeated here.)

### Timed native A/B under the bench lock (seed-42, NCPU=8, 3 interleaved runs each; machine load 34–45)

| Phase (wall, median) | v5 `3671aeb` | vtl (map, no lock) | vnolock (hash only) |
| -------------------- | -----------: | -----------------: | ------------------: |
| events parse         | 1.05 s       | 0.53 s             | 0.37 s              |
| clicks parse         | 0.24 s       | 0.19 s             | 0.08 s              |
| whole run            | 1.79 s       | 1.25 s             | 0.92 s              |

(One v5 run at 3.85 s, from a load spike, is excluded from the median.)

- **`intern` is about 65% of v5's events-parse wall and 60% of its clicks-parse wall at NCPU=8, and about 0.87 s
  of the 1.79 s whole run.**
- Of that, the shard locks are about 0.52 s (v5 → vtl), and the hash-map work with its cache misses is about
  0.17 s (vtl → vnolock).
- At NCPU=1 the order flips. Events parse takes 3.88 s (v5), 3.39 s (vtl) and 1.98 s (vnolock), so single-
  threaded the map work (about 255 ns per insert: random probes into a table of 3.3M entries) costs more than
  the uncontended lock.
- A fix has to remove both: no lock, and no pointer-chasing map. That is what move 6 aims at.
- NCPU=8 instruction counts swing with load: rayon's idle spin and the Mutex spin retire instructions, from
  1,064 down to 906 instructions per line in v5 events parse. Treat NCPU=1 instruction counts as the clean
  metric.

## 2. Spec check of move 6 (`method/v5` @ `e693e18`)

**Verdict: PASS. No spec defects found.**

### The design as built
- A 33-byte ID whose first byte is a packable symbol and whose other 32 bytes are lowercase hex becomes
  (hi, lo) with digit 0 in the top nibble. It goes into `LongTable`: insert-only, lock-free, linear probing,
  a CAS on a per-slot state word. The key is `slot << 10 | SYM[prefix] << 4 | 2`.
- Packed keys have low nibble 0 and interned keys have 1, so the three kinds are disjoint.
- Anything else, or a long ID whose 128-probe window is full, takes the old interner (tag 1).

### Comparison sites (all of them, from a grep of `is_packed`, `& 15`, `.cmp(` on IDs)

| Site | Rule (spec line) | How v7 compares | OK |
| ---- | ---------------- | --------------- | -- |
| `click_ord` (window walk, run sort) | smallest `click_id` on ts ties (63) | raw u64 only if **both** packed, else `Ids::cmp` | ✓ |
| `sort_clicks_old` / `sort_unstable_by` | same | `Ids::cmp` | ✓ |
| `links.rs` union (smaller root) | byte-wise smallest names the person (44) | `Ids::cmp` | ✓ |
| `Ids::cmp` long vs long | byte order | SYM(prefix) first (SYM preserves order), then (hi, lo) as u128; same length (33), and a hex digit's value rises with ASCII | ✓ |
| `Ids::cmp` mixed kinds | byte order | decode both to bytes and compare the slices (handles prefix relations, e.g. `u3f` < `u3f…32 hex`) | ✓ |
| dedup (eid), link table, person interning, partitions | exact equality (51, 68) | key equality: one string gives one key (see below) and different strings give different keys (disjoint tags, unique slots, unique intern indices) | ✓ |
| output `user_id` | the name's exact bytes (78) | `bytes()`: DESYM[sym] + lowercase digits, 33 bytes | ✓ |

No remaining code assumes "not packed means interned" (`k >> 4` is used as an intern index only after the
`k & 15 == 2` branch has been ruled out).

### One string, one key (overflow consistency)
- Slots only go from empty to writing to ready, and never move.
- An insert claims the first empty slot on the fixed probe sequence from `h`. Every slot before it was full
  at that moment and stays full, so a later lookup walks the same non-matching slots and reaches it.
- If a window is full of other values, it stays full, so every copy of that value goes to the interner. It
  then gets one key there, under the Mutex.
- Two threads inserting the same value meet at the slot one of them claimed: the loser's CAS fails, it spins
  while the state is 1, then compares.
- Ordering: `hi` and `lo` are stored Relaxed before a Release store of state 2, and readers load the state
  with Acquire before reading `hi` and `lo`. `value()` skips the state check in release builds. That's safe
  because a key exists only after a `slot()` that saw state 2, and keys cross threads only through rayon
  joins and returns.

### Fallback inputs (must not take the long path)
- Uppercase hex anywhere (`HEX` maps only `0-9a-f`), 31, 32 and 34 digits, a non-hex digit, and an
  unpackable prefix (`-`, `.`): all go to the interner.
- An uppercase *prefix* with lowercase digits (`U` + 32 hex) takes the long path, which is fine: it is
  packable, SYM orders it, and DESYM restores it.

### Evidence
- `cargo test --release`: 11/11, including Method's extended `keys_preserve_equality_and_order`. That test
  covers 6,000 long and near-miss IDs × 5 configs, including a 64-slot table with every value colliding.
- Fixtures 36/36. New dev MATCH.
- **seed-42 (new generator, 20M): MATCH against `data/expected/seed-42` (Eval's regenerated oracle answer)**,
  and identical to v5's output.
- **My adversarial suite** `evals/insights2/v7_longid/{gen.py,run.py}`: **900/900 MATCH (150 seeds × 6 knobs)**, oracle vs binary, 6 knobs each
  (default; `HASH_BITS=0`, so every long ID collides and the windows overflow, mixing long and interned keys
  for one prefix; `HASH_BITS=3` + `PARTS=1`; `NO_FAST=1`, `2` and `3`, with `CHUNK=97`), at NCPU 8, 2 and 1
  by seed. It covers:
  - a digit pool reused under several prefixes, and runs of 28–31 shared digits
  - all-0, all-f and neighbouring digit strings
  - short packable IDs that are byte-prefixes of long ones, or diverge right after the shared part
  - whole and single-digit uppercase hex, and uppercase prefixes
  - 32-, 34-byte and non-hex near misses
  - IDs that appear only in links (some are the person's smallest)
  - groups of clicks tied at the session-start millisecond across key kinds
  - event IDs repeated with a later ingest (sometimes another user), and earlier invalid copies that kill
    the event
- **Suite sensitivity:** 4 broken builds of `e693e18`, 20 seeds × 6 knobs each:

  | Mutant | Breakage | Seeds caught |
  | ------ | -------- | -----------: |
  | M1 | `click_ord` raw-compares any non-interned pair | 20/20 |
  | M2 | long vs long ignores the prefix | 20/20 |
  | M3 | `HEX` accepts `A` and `F` (uppercase decoded as lowercase) | 18/20 |
  | M4 | `Ids::cmp` raw-compares packed vs long | 20/20 |

  Only the `NO_FAST=1` knob, which never builds long keys, passes on every mutant, as expected.

## 3. Move 6 performance (native, indicative; gVisor numbers are Explorer 5's)

seed-42, NCPU=1, the clean metric. These runs were measured under machine load, so the walls are only a guide; CPU and instructions are robust.

| events parse | v5 `3671aeb` | v7 `e693e18` | ideal (hash-only key) |
| ------------ | -----------: | -----------: | --------------------: |
| instructions per line | 825 | **811** | 732 |
| CPU          | 3.72 s       | **2.73 s**   | 1.95 s                |

| clicks parse | v5 | v7 | ideal |
| ------------ | -: | -: | ----: |
| instructions per line | 153 | 146 | 135 |
| CPU          | 0.76 s | 0.51 s | 0.36 s |

- **The lock is gone, and about 56% of the single-thread intern CPU with it.** Under contention the gain is
  larger: the native NCPU=8 run took 1.43 s whole against v5's 1.75–1.79 s in the same window (load-
  affected). Expect most of Explorer 5's 1.53 s → ~0.6 s gVisor events-parse gap to close.
- **Instructions barely moved (−14 per line), because the scalar `hex32` loop costs about 190 of the roughly
  300 instructions per long ID.** A SIMD hex-32 validator and packer (SSSE3/NEON, around 15 instructions) is
  worth about −60 instructions per event line. → **Method**, with Explorer 2's `explore/gemini-hex32`.
- The remaining CPU over ideal (about 0.8 s single-threaded) is `LongTable` misses.
  - At 20M the table is 8.4M slots × 24 B = 201 MB at load 0.39. At the 60M final it is 33.5M slots
    = 805 MB at load about 0.30, touched at random, so about 197k first-touch 4 KiB page faults. Those are
    expensive under gVisor.
  - Two options: size it from the distinct long IDs rather than `in_bytes / 256`, or pack slots to 16 B
    (sentinel plus a 128-bit CAS). → **Explorer 5** to measure fault time at 60M under runsc before anyone
    builds this.
- The `written` phase went from about 65 to about 117 instructions per line. That comes from the **move 4
  revert** in `c7acf4a` (dictionaries and statistics are back), as intended, not from move 6.

## Recommendations
- **Eval:** add `evals/insights2/v7_longid/run.py <binary> 150 <workdir>` to Gate A for any change that touches
  `Ids`, `click_ord`, links or dedup. It needs the venv oracle and runs in about 15 min at nice 19.
- **Method:** SIMD `hex32` next (−60 instructions per line). Keep `Ids::cmp`'s mixed-kind path on byte
  slices: the mutants show that any shortcut there is caught at once.
- **Red Team:** my suite and yours overlap on the hex family. Mine adds HASH_BITS=0 (forced overflow into the
  interner) and mutation coverage.
