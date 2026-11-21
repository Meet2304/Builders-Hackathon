# Correctness review: `method/v3` @ 1ea8059 (diff against v2 953af43)

Analyst thread, branch `analysis`, 2026-11-21. Scope: the rewrite's new code paths, checked against
`docs/rules.md`:
- packed and interned IDs;
- dedup by side stream;
- direct-index products and campaigns;
- the SIMD and SWAR line scan;
- batched link lookups;
- every `assert`.

Method:
1. A line-by-line read of the diff against the rules.
2. **Hand-built adversarial cases**, one per risk, in `evals/insights/v3_review/cases.py`, with the runner in
   `run.py` next to it.
3. Diffing the v3 output against the Python oracle under **10 knob settings**: default, `NO_FAST=1/2/3`,
   `PARTS=1/3`, `CHUNK=1/97`, `HASH_BITS=0`, `NCPU=1`.
4. The existing 1000-seed fuzz corpus.
5. The amd64 SSE2 path through an emulated `x86-64-v2` image.

No timed runs.

## Verdict: no bugs found. v3 is correct on everything I could construct.

| Check | Result |
| --- | --- |
| 7 review cases × 10 knob settings, native arm64 (NEON) | **70/70 MATCH** |
| 7 review cases × {default, `NO_FAST=3` SWAR, `CHUNK=97`}, amd64 container (SSE2, `x86-64-v2`, emulated) | **21/21 MATCH** |
| v3 unit tests on amd64 (`classifiers_are_exact`, `record_scan_matches_split_fields`, `keys_preserve_equality_and_order`, ...) | **5/5 pass** |
| Existing fuzz corpus, seeds 0..999, NCPU cycling 1/2/4/8 | **854/854 strict, 146/146 robust** |
| Do the cases hit the intended paths? I checked the oracle's answers by hand (component names, tie winners, dedup survivors, category per product) | yes, all as designed |

Re-run with:

```
.venv/bin/python evals/insights/v3_review/run.py <sessions binary> <work dir>
```

It takes about 1 minute and exits 1 on any mismatch or crash.

Nothing needs to go to Method as a bug. There are six non-blocking notes at the end: two comments that
mislead, two shortcuts that rely on the spec, and two performance cliffs.

## Risks, the case that probes each, and the result

### 1. Packed vs interned ID boundary and order (`pack`, `Ids::key`, `Ids::cmp`)

**What could go wrong:**
- byte order differing between packed keys (u64 compare) and fallback keys (byte compare);
- a 10-character ID colliding with an 11-character one;
- `_` and upper case mis-ranked;
- UTF-8 or space IDs packed;
- a fallback ID never winning a component's minimum.

**Code check:**
- `SYM` assigns codes in ASCII order: `0-9` < `A-Z` < `_` < `a-z`.
- Zero padding makes a prefix sort first.
- Bits 3..0 are always 0 for a packed key and 1 for an interned one, so the two never collide and neither is the
  table's empty key 0.
- `cmp` falls back to bytes whenever either side is interned.
- The same string always takes the same path, including under `NO_FAST=2`, whose choice depends only on the
  string's hash.
- The only places that compare keys for order are `load_links` (minimum per component) and the click sort
  (`click_id` tie). Both use `ids.cmp`.

**Case `ids`:** 15 link components, each linked in shuffled order across 3 files, plus 6 click-tie groups.

| Probe | Oracle and v3 |
| --- | --- |
| `abcdefghij` (10, packed) vs `abcdefghij0` (11, fallback) | `abcdefghij` |
| `abcdefghija` (11) vs `abcdefghik` (10) | `abcdefghija` (fallback wins) |
| `abcdefghijz` vs `abcdefghijA` (both 11) | `abcdefghijA` |
| `Zz`, `_a`, `a`, `é` | `Zz` |
| `zz` vs `~a` (`~` isn't packable) | `zz` |
| `u1`, `" u1"`, `"u1 "` | `" u1"` |
| `0`, `00`, `000000000000` | `0` |
| `k9`, `k10`, `kk`, `K`, `k_` | `K` |
| `ZZZZZZZZZZ` vs `ZZZZZZZZZZZ` | the 10-char one |
| `é1`, `é2` | `é1` |
| `m5` and the link-only `!m` | `!m` |
| `abcdefghijé` with `abcdefghij` (merges with component 1) | `abcdefghij` |
| `a-b`, `a_b`, `a.b`, `aZb` | `a-b` |
| `9999999999`, `99999999999`, `A` | `9999999999` |
| `q1` and `"q2\r"` (CR inside a quoted ID) | `q1` |
| unlinked `x` and `X` | two persons |
| click ties at the same ts: `{abcdefghij0, abcdefghij}`, `{abcdefghija, abcdefghik}`, `{é, z}`, `{Z9, _0, a}`, `{abcdefghijz, abcdefghijA}`, `{" b", !b, b}`, each with a quoted duplicate copy | credits `abcdefghij`, `abcdefghija`, `z`, `Z9`, `abcdefghijA`, `" b"`: all correct |

**Result: MATCH under every knob.**

### 2. Dedup (`parse_event`, `EvOut::flush`, `dedup_part`, drops routed to `process_part`)

**What could go wrong:**
- a later valid copy rescuing an invalid or late winner;
- a tie keeping two copies;
- a drop marking the wrong row (wrong task, partition or sequence number);
- `HASH_BITS=0` collisions merging distinct event IDs.

**Code check:**
- Every well-formed line with a non-empty `event_id` gets an `EidEnt`. Valid ones get a row reference, and
  invalid ones get `INVALID`.
- `validate` includes the late check, so a late winner is invalid, as the rules require.
- Only a strictly smaller ingest replaces the winner, and every loser that produced a row is dropped. That gives
  "no rescue" for free.
- The drop layout is dest:16, t:24, seq:24. `dest < 4096` and `t < 2^24` are both asserted. `seq < 2^20` is
  asserted in `flush`.
- `process_part` rebuilds each task's offset from the same `r[p]` vectors, so the indexes agree.

**Case `dedup`:** 10 probes, each on its own user, plus a 4,000-event bulk with 0 to 3 copies per event spread
over 9 files. In the bulk, 40% of later copies name another user (so drops cross partitions), 20% of later copies
have a bad ts, and IDs mix packed and fallback forms.

| Probe | Expected (oracle) |
| --- | --- |
| D1: the min-ingest copy has `ts` hour 25 | dropped, no rescue |
| D2: min copy late by 24 h + 1 s; D2b exactly 24 h | D2 dropped, D2b kept |
| D3: valid@+5 s, `View`@+3 s, valid@+4 s in 3 files | dropped |
| D4: three identical copies with equal ingest, quoted differently | counted once, 250 cents |
| D5: winner user `du5`, later copy user `du5other` (different price) | event and revenue on `du5` only |
| D6: winner has an empty user | dropped |
| D7: earliest copy malformed (8 fields) | the next copy wins |
| D8: winner is a purchase with price `0` | dropped |
| D9: `eventid_long_1` ×2, `é1` ×2, `" e1"`, `e1`, `E1`, `"e1 "` | 6 distinct events |
| D10: winner `ts` outside the window | dropped |

**Result: MATCH under every knob,** including `PARTS=1/3` (routing), `HASH_BITS=0` (every event ID collides in
the probe sequence) and `CHUNK=1` (thousands of tasks, so the `t` field is exercised).

### 3. Direct-index products and campaigns (`IdIndex`)

**What could go wrong:**
- `p07` aliasing `p7`;
- `p0` and `p` mishandled;
- the 2^22 bound leaking (`p4194304` treated as a slot);
- an absent ID reading a stale slot;
- last-wins vs first-wins.

**Code check:**
- Only the canonical form (prefix, then 1 to 7 digits, no leading zero, value < 2^22) takes the array.
- Every other string goes to the hash map, and `set` and `get` share `direct_slot`, so the split is exact.
- An absent slot is `u32::MAX`, or past the end of the array.
- Products are last-wins and campaigns first-wins. `products.csv` and `campaigns.csv` have unique IDs per the
  rules, so the difference can't show (see note 1).

**Case `lookups`:**
- **Products, one purchase each, with a distinct category per product:**
  - present: `p0`, `p00`, `p07`, `p7`, `P7`, `p4194303`, `p4194304`, `p9999999`, `p10000000`, `p`, `p-1`,
    `"p 1"`, `"p1 "`, `p99999999999999999999`, `p１` (full-width), `pp7`, `p+7`;
  - absent: `p8`, `p0007`, `p01`, `p4194305`, `p000`, `P0`, `p1`, `p٧`.
- **Campaigns:**
  - present: `c_0`, `c_00`, `c_7`, `c_07`, `C_7`, `c_4194304`, `c_4194303`, `c_`, `c_9999999`, `"c_1 "`,
    `c_99999999999999999999`, `c__1`;
  - absent: `c_8`, `c_007`, `c_4194305`, `c_1`, `c`, `c_٣`.

**Result: MATCH.** Each present ID gets its own category or campaign, and each absent one gets `unknown` or
`organic`.

### 4. SIMD and SWAR scan fallbacks (`for_each_record`, `classify_*`)

**What could go wrong:**
- the fast path accepting a line that `split_fields` would reject, or slicing it differently (quotes, CRLF, a
  missing final newline, lines that cross 64-byte blocks, lines longer than a chunk);
- the zero-padded tail block;
- the x86 SSE2 classifier differing from NEON.

**Code check:**
- The fast path needs no `"` in the line and exactly N−1 commas. Otherwise the line goes through v1's
  `split_fields`.
- `\r` is an ordinary byte on both paths, as the rules require.
- A line with ≥ 1 comma is never empty, so the fast path can't accept an empty line.
- The tail block is zero-padded. NUL matches none of the three classes, and a real NUL in the data sits only
  before `end`.
- Chunks always end just after a `\n` or at end of file, so a line is never split across tasks.

**Case `scan`:**
- **CRLF:**
  - a `view` with price `12\r` is valid;
  - a `purchase` priced `1000\r` is invalid;
  - a click with ts `...Z\r` is invalid;
  - the link side `cru6\r` is a separate ID.
- **Malformed shapes, all dropped:** empty line, `,,,,,,`, a lone `"`, `""""""`, a trailing comma, a leading
  comma, a quote mid-field, `"mu"x`, `""mu""`, `;` instead of a comma, a line holding only `\r`, and junk before
  a quote.
- **Quoting:**
  - every field quoted, with price `0250`;
  - a quoted empty `product_id` (dropped);
  - a `""` price on a view.
- **A NUL byte inside a user ID.**
- **Block boundaries:** 140 lines with the user ID padded 0 to 139 characters, so every delimiter and quote
  lands on every block offset, with random quoting and bad prices `1"2` and `1,2`.
- **Very long lines:** a 300-character user, a 500-character product, a 200-character click_id. Under
  `CHUNK=97` these are lines longer than a chunk.
- **A header-only file.**

`scan_no_final_newline` is the same case built from seed 12 with no final newline in any file. That input is
outside the rules (`robust`).

**Result: MATCH** with NEON (default), SWAR (`NO_FAST=3`), scalar (`NO_FAST=1`) and `CHUNK=1/97` natively, and
with **SSE2** in the amd64 container. The SSE2 path is the one the scorer runs.

### 5. Asserts and panics on valid but unusual input

| Site | Can valid input trigger it? |
| --- | --- |
| `EvOut::flush`: `seq < 1<<20` (rows per task and partition) | **No.** A task is ≤ `MAX_TASK_BYTES` (8 MiB) plus at most one line of overhang per chunk. The shortest valid event line is about 46 bytes: the in-window `ts` needs ≥ 13 digits and `ingest_ts` is 20 bytes. That's ≤ 183k rows even with `PARTS=1`, well under 1,048,576. |
| `main`: `ev_out.len() < 1<<24` | No. 60M at 4 MiB is about 1,300 tasks, and `task_group` bounds tasks for tiny chunk sizes. |
| `keys.binary_search(..).unwrap()` in `load_links` | No. Every looked-up key was inserted. |
| `ActiveSet::remove` underflow, `list.last().unwrap()` | No. Removes always follow adds, in window order. |
| `manifest` `expect`s, `File::open` / `mmap` `expect`s | Only on a missing or unreadable manifest or file, which is outside the rules. |
| Knob `panic!`s | Only for malformed `SESSIONS_DEBUG_*` values, which are never set on the scorer. |
| Overflow: `e.ts - base` in 40 bits; `local << 40` | Guarded: `wide` falls back when the window plus 7 days exceeds 2^40 ms, or when a partition has ≥ 2^24 people. |

**Cases `edges` and `whale`:**
- `edges`: no valid events (only an empty-user event, a click and a link). Output is empty tables.
- `whale`: one person over a 400-ID chain, 60k events and 3k clicks. Under `PARTS=1` and `NCPU=1` that puts
  every row in one partition and one task.

**Result: MATCH, no crash.**

## Notes for Method (non-blocking; none changes output on in-spec data)

1. **Products are last-wins and campaigns first-wins** (`load_products` vs `load_campaigns`). The rules
   guarantee unique IDs in both files, so this can't show. Making both use the same rule
   would remove a "why?" for reviewers.
2. **The dedup tie comment is misleading.** "On a tie the first copy stays" holds in `e[q]` order, not file
   order: valid rows enter `e[q]` when the batch flushes, after the invalid rows parsed in the same batch. This
   is correct only because the rules make equal-ingest copies identical. Worth a one-line comment saying that.
3. **There's no click dedup at all.** This is correct because the rules say click copies are identical, and
   credit and assists are idempotent over identical clicks. My first draft accidentally reused a click_id across
   two persons (outside the rules). v3 then counted both clicks while the oracle kept one, and the output
   differed by one assisted session. That's not a bug, but it shows the shortcut leans on the rules' guarantee.
4. **The `MAX_TASK_BYTES` doc says a valid line is "at least 16 bytes".** The real floor is about 46. The
   assert is safe either way; just fix the comment.
5. **Performance cliff, not correctness:** every unpackable ID takes a 64-shard `Mutex` in `Ids::intern`, and
   `Ids::bytes` locks the mutex inside the click-sort comparator. I checked the real data: in a 400k-row sample
   of seed-43, **0** event or user IDs are unpackable, and all 50,000 products and 2,000 campaigns are
   canonical. So the generator never hits this path. If the final data ever had longer IDs, v3 would stay
   correct but slow down.
6. **The `cascadelake` build isn't tested locally.** The scorer compiles with `target-cpu=cascadelake`, which
   lets LLVM auto-vectorize with AVX-512. The classifier uses explicit SSE2, so its meaning is fixed, but no
   local run executes AVX-512 code. The risk is a compiler bug, which is low. QEMU can't run AVX-512, so this
   gap stays open.

## Requests for Eval

- Add `evals/insights/v3_review/run.py` to Gate A, or port its seven cases into `evals/fuzz/gen.py`'s
  `id-shapes` and `dedup` foci.
  - It's cheap: about 1 minute native and about 4 minutes for the amd64 subset.
  - It pins the exact boundaries v3 introduced: 10 vs 11 characters, and fallback IDs winning a component's
    minimum and a click tie.
- Run the amd64 image under `NO_FAST=3` (SWAR) as well as the default (SSE2) for the fixtures and the dev
  answer, and keep the amd64 `cargo test` from this review (`classifiers_are_exact` ran on SSE2 here).
