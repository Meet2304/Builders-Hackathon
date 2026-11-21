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

## Addendum: `method/v3` @ 29b64bf (mimalloc `8004f65`, window timestamp decoder `29b64bf`)

**Verdict: no bugs found.** The two new commits don't change output on anything I could construct.

| Check | Result |
| --- | --- |
| 5 new timestamp cases (`v3_review/cases_ts.py`) × 10 knobs, native arm64, against the oracle | 50/50 MATCH |
| The original 7 cases × 10 knobs, re-run at 29b64bf | 70/70 MATCH |
| `cargo test --release` at 29b64bf, including the new `timestamp_decoder_matches_parse_ts` | 6/6 pass |
| Mutation check: 4 deliberately broken decoders run on the new cases | 4/4 caught (see below) |

### What the decoder does, and why it is exact

`TimestampDecoder` answers three shapes itself and sends everything else to v1's `parse_ts`:

- **F1 and F2 (length 20 with `Z`, length 25 with `±` and `:`):** a 512-slot table holds every calendar day from
  `window_start - 8 days` to `window_end + 8 days`. The slot index is (month's last digit & 1, day tens & 15,
  day ones & 15). A hit needs bytes 0..8 to equal the stored `YYYY-MM-`, the high nibble of both day digits to be
  `0x3_`, and `s[10] == 'T'`.
  - Together these pin all 10 date bytes exactly. The table only holds real dates, so Feb 30, Feb 29 in a
    non-leap year, `-00` and `-32` always miss and fall back to `parse_ts`, which rejects them.
  - Two days can only share a slot if they have the same day number in months of the same last-digit parity.
    That needs about 59 or more days, and the table is capped at 48 (`last - first > 48` leaves it empty).
  - `clock_ms` checks all 8 clock bytes: digits by SWAR, the two `:` lanes must XOR to zero, and h ≤ 23,
    m ≤ 59, s ≤ 59. That's the same range as the rules.
  - F2 offsets go through the same `dig2` and range checks as `parse_ts`. All 20 or 25 bytes are checked on
    every path.
- **F3, length 13:** both 8-byte halves must be all digits; the top 5 digits are loaded with 3 zero lanes, so the
  value is `D5 × 10^8 + D8`. Any other 13-byte string returns `None`, which matches `parse_ts`, because F1 and
  F2 are never 13 bytes long.
- **Everything else** (F3 of any other length, leading zeros, overflow, dates off the table, a window wider than
  48 days, `NO_FAST=1`) goes to `parse_ts` unchanged.

On generator data the table is always on (14-day windows at midnight). It covers every click (back to
start − 7 days), every ingest of a late event (at most 5 days after `ts`), and every F2 local date (±12 h).

### The new cases (`evals/insights/v3_review/cases_ts.py`)

Each probe pins the decoded value **to the millisecond**:

- **Event probes:** the probe event sits between two anchors of the same user at t − 30:00 and t + 30:00, where t
  is the oracle's value.
  - The anchors are 16-digit F3, so they bypass the decoder.
  - The three events make one session only if the probe decodes to exactly t. A wrong reject gives two
    one-event sessions; any other value gives a split.
- **Click probes:** each click has its own campaign, and its person has purchase sessions starting at t and at
  t + 7 days. The click credits the first only if it decodes to ≤ t, and the second only if it decodes to ≥ t.
- **Ingest probes:**
  - Lags of 24 h − 1 s, 24 h, 24 h + 1 s, 0, −9 d, −10 d, +9 d and +30 d, so some ingest dates land off the
    table and use the fallback.
  - Dedup pairs where the smaller ingest is off the table and the larger is on it, with the invalid copy first
    or second. This checks that the fallback and table values order correctly and that an invalid winner isn't
    rescued.
- **Probe strings, about 14–17k per case:**
  - Every day from window − 12 to window + 12 days, which crosses both table edges.
  - 8 clocks, including `24:00:00`, `12:60:00`, `12:00:60` and a misplaced colon.
  - 11 zones: `Z`, `±00:00`, `+05:30`, `-10:00`, `+12:00`, `±23:59`, `+24:00`, `+05:60` and `+0530`.
  - F3 of 12, 13, 14 and 16 digits, plus a 13-byte non-digit.
  - Impossible dates whose bytes land in the table's index space (`10-3:`, `10-0:`, `1:-01`, `02-30`, `09-31`).
  - Single-byte mutations of 60 sampled strings at every position, using 24 characters: digits, `:;/-+TtZz .`,
    NUL, DEL and 0xFF.
- **Windows:**

  | Case | Window | What it exercises |
  | --- | --- | --- |
  | `ts_yearend` | 2027-12-25..2028-01-08 | year crossing |
  | `ts_leap` | 2028-02-22..2028-03-07 | Feb 29 2028 |
  | `ts_offmidnight30` | 2026-10-01T05:30Z, 30 days | off-midnight start; table on at 46 days |
  | `ts_wide40` | 40 days | table off: fallback only |
  | `ts_autumn` | 2026-09-24..10-08 | the 09→10 month-parity edge |

**Mutation check (do the cases bite?).** I built four broken decoders from 29b64bf and ran each on the five cases:

| Mutant | Caught in |
| --- | --- |
| Drop the day-digit high-nibble check (accepts `2026-10- 5` as day 05, `2026-10-1\0` as day 10) | 4/5 |
| A clock ending `:59` decodes 1 ms late | 4/5 |
| F3 mask keeps 6 high lanes instead of 5 | 5/5 |
| A `-10:xx` offset decodes 1 ms late | 4/5 |

The one miss each time is `ts_wide40`, where the table is off by design, so table mutants can't show there.

### mimalloc

- **Logic:** none changes. `#[global_allocator]` only.
- **Build:** `libmimalloc-sys` compiles C with `cc`. `rust:1-slim-bookworm` ships gcc and libc6-dev, and
  `target-cpu` is passed only as `RUSTFLAGS` (cc-rs doesn't read it), so the C side builds generically on
  both arches.
- **Not checked by me:** I did not build the amd64 image of 29b64bf, because the bench lock was held by Explorer.
  Eval's Gate A amd64 container build covers it.
- **Runtime:** no file writes, no network, and no extra threads, so the read-only root, uid 1000 and the
  4,096-thread cap are unaffected.

### Requests for Eval (addendum)

- Add `run.py BINARY WORK cases_ts.py` to Gate A next to the original cases. It takes about 20 s native for
  50 runs.
- Gate A on 29b64bf must include the amd64 container build and fixtures: it's the first commit with a C
  dependency, so it needs that.
- `evals/fuzz/gen.py` draws only 14-day midnight windows, the same as the generator. That's fine for the score,
  but a `windows` focus with year-end, leap-day and off-midnight windows would keep the table edges covered if
  the decoder changes again.
