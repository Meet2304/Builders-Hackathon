# v4 design: what has to be true to beat 0.28 s on the board

Analyst, 2026-11-21, written against `method/v3` @ `29b64bf` while Eval's v3 full eval runs. Every number marked
**[est.]** is my estimate from v2's measured phase CPU, v3's dev numbers and code reading. Replace them with
Eval's v3 phase marks when they land. Inputs: `evals/results/v2.json` and `.md`, `evals/explore/window-timestamps.md`,
`evals/explore/allocator-bakeoff.md`, `evals/insights/v1.md` §4 and `v2.md` §4, and v3's source.

## 0. Headline

1. **v3's SIMD fast path is skipped by 79% of event lines and 59% of click lines.** The fast path requires a
   line with no `"` at all. The rules quote 20% of fields at random, so only 0.8⁷ ≈ 21% of 7-field event lines
   qualify.
   - I checked a 40 MB sample of the largest seed-42 file: **79.0% of event lines, 59.1% of click lines and
     35.8% of link lines contain a quote.**
   - Every quoted line goes to v1's byte-loop `split_fields`, which costs about 680 instructions per line
     (v1 §4.2 probe), against about 60–80 on the fast path.
   - **A fast path that also accepts whole-field quotes is the largest single move left (≈ −470 instructions per
     event line)**, and its fallback stays exact.
2. **The budget: about 250 instructions per event line, all phases included, plus ≈ 35 ms of fixed cost.** That
   assumes the 8 vCPUs are 4 Cascade Lake cores × 2 hyperthreads at about 3 GHz. That's roughly 25 G instr/s
   for the whole box, and 30 GB/s of DRAM.
   - v2 measured 4,264 instructions per line. v3 is ≈ 2,700 **[est.]**, so we need about 10× fewer.
   - Four incremental moves take v3 to about 1,000–1,200. The last 4× needs the whole target architecture
     done tightly, not one trick.
3. **The 0.28 s board time is practice, at about 20M events and 1.8 GB** (`docs/PLAN.md`: practice ≈ 20M, final
   ≈ 60M and 5.4–5.5 GB). It is not a 60M time.
   - Scaled linearly, the leaders would be at about 0.8–0.9 s on the 60M final.
   - Our final budget is ≈ 0.70 s at 60M (§1).
4. **The biggest unknown is the scorer's speed relative to this Mac, and we have zero calibration points.**
   `evals/submissions.json` is empty. If the scorer is 8 real cores, or this model is off by 2×, the target is
   about 500 instructions per line, not 250, and the incremental path might be enough.
   - **Submit v3 as soon as it passes Gate A.** A slower submission never replaces the best one, so it costs
     nothing, and its board time decides how deep v4 has to go.

## 1. Time budget per phase (8 Cascade Lake vCPUs)

**Model.**
- 8 vCPU = 4 cores × 2 HT at about 3.0 GHz all-core turbo. HT gives about 1.25× per core, so the box runs
  ≈ 5 core-equivalents. At IPC ≈ 1.7 that's ≈ 25 G instr/s.
- DRAM is ≈ 30 GB/s for this VM's share of the socket.
- These assumptions are the leaders' result worked backwards. 0.28 s at 20M implies roughly 6–7 G instructions
  in total.
- At 20M: ≈ 20.5M event lines (77 B average), ≈ 4.9M click lines (47 B) and ≈ 0.9M link lines (21 B). That's
  1.75 GB in total.

Per-line columns are per **event** line. Clicks are amortised: about 0.24 clicks per event.

| Phase | 20M budget (s) | Instr/event line budget | v2 measured instr/line ¹ | v3 expected instr/line **[est.]** | 60M budget (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fixed: exec, manifest, pool, open and mmap of ~110 files, `process::exit` | 0.008 | – | – | – | 0.010 |
| Links + products + campaigns | 0.012 | 10 | 46 | 40 | 0.045 ² |
| Events: SIMD classify + field split | 0.035 | 40 | | **≈ 550** ³ | 0.105 |
| Events: decode (2 IDs, 2 timestamps, type, product, price) | 0.050 | 60 | 2,195 (all of events) | ≈ 450 | 0.150 |
| Events: link probe + emit dedup entry and row | 0.025 | 25 | | ≈ 400 | 0.080 ² |
| Clicks: parse, validate, probe, emit (≈ 100 instr per click) | 0.020 | 25 | 431 | ≈ 330 | 0.060 |
| Dedup (side stream) | 0.012 | 15 | 585 | ≈ 185 | 0.040 |
| Sessions + attribution (intern, sort, session loop, credit and assists) | 0.060 | 70 | 897 | ≈ 600 | 0.190 |
| Output (Parquet, both tables) | 0.010 | 5 | 109 | ≈ 100 | 0.020 |
| Barrier tails (≈ 6 phase barriers × ½ chunk) and serial glue | 0.015 | – | – | – | 0.020 |
| **Total** | **0.247** | **≈ 250** | **4,264** | **≈ 2,700** | **≈ 0.72** |

1. v2's measured total is 4,264 instr/line (Eval, 20M). I split it by v2's per-phase CPU shares (events 5.53, clicks 1.09,
   dedup 1.47, sessions 2.26, Parquet 0.28, lookups 0.12 core-s), assuming IPC is flat across phases.
2. Superlinear at 60M:
   - The link table grows to ≈ 3.6M IDs, so probes become DRAM and TLB misses. Prefetching hides the
     latency, but the table needs THP.
   - With P fixed at 256, partitions are 3× larger and spill L2. Scale P with input (§2, G6).
3. 79% of lines × ≈ 680 + 21% × ≈ 70.

**Memory traffic budget.**
- At 20M, the input is 1.75 GB.
- With 16 B dedup entries and 16 B rows, each written once and read once, add ≈ 1.3 GB. That's ≈ 3 GB, or
  ≈ 0.1 s at 30 GB/s, overlapped with compute.
- The parse phase alone needs ≈ 19 GB/s (109 B per line in 0.115 s). That fits, but only if rows stay compact.
- v3 writes 44 B per event (16 B `EidEnt` + 4 B ref + 24 B `Row`) and then copies rows again into 24 B `PEv`.
  That's ≈ 4.5 GB in total **[est.]**, about 0.15 s of pure bandwidth on the scorer.

**Fixed costs are already small in v3.** mimalloc took Linux faults from 967k to 21k and the exit tail from
161 ms to 11 ms (allocator bake-off). File-backed mmap faults with the kernel's 64 KB fault-around are ≈ 27k
for 1.75 GB, ≈ 0.05–0.1 core-s, paid in parallel inside the parse. What's left is ≈ 10–20 ms of barrier tails
and serial glue.

## 2. Gap list: v3 vs budget, and what closes each gap

Ordered by expected gain. "Instr" is per event line. Seconds assume 25 G instr/s on the scorer and ≈ 8 G
instr/core-s locally (v2: 87 G instructions in 10.7 core-s).

| # | Phase | v3 → target | Technique | Gain at 20M: scorer s / local core-s | Risk |
| --- | --- | --- | --- | --- | --- |
| **G1** | Classify + split | 550 → 60 (events); clicks ≈ 59% fallback → ≈ 0 | **A quote-aware fast path** (exact rule below). Clicks and links get it too. | **≈ 0.40 s / ≈ 1.3 core-s** | Low: anything unusual still goes to `split_fields` |
| **G2** | Emit + sessions | 400 + 600 → 25 + 70, plus ≈ 1.5 GB less traffic | **Compact streams and a counting sort, with no `PEv` copy** (below) | ≈ 0.30–0.40 s / ≈ 1.0 core-s | Medium: row layout, ts offsets, whale partitions |
| **G3** | Decode | 450 → 60 | **SWAR ID packing** (pshufb or tbl nibble LUT, then multiply-compaction): ≈ 15 vs ≈ 40 instructions per ID, × 3 IDs per line. Look up the category **only for purchases**, since it's only used under `price > 0`. Match the type on (length, first 8 bytes). | ≈ 0.25 s / ≈ 0.8 core-s | Low: exhaustive equivalence test against `pack()` |
| G4 | Clicks | 330 → 25 | G1 + G3 together. Ck is 32 → 24 B (`ts` as a u32 offset). | ≈ 0.07 s / ≈ 0.25 core-s | Low |
| G5 | Dedup | 185 → 15 | Merge `EidEnt` + ref into 16 B (`eid u64 \| ingest_off u32 \| ref u32`). Size P so the per-partition table fits L2 (≤ 1 MB on Cascade Lake). | ≈ 0.12 s / ≈ 0.4 core-s | Low–medium: ingest range check (below) |
| G6 | All partitioned phases | Load balance, L2 fit | **Process partitions in descending row count.** Whales hold 1–2% of all events each, so one partition is ≈ 5× the mean. Scale P with input bytes: 256 at 20M, 1024 at 60M (measure it). | ≈ 0.01–0.03 s tail; more at 60M | Very low |
| G7 | Barriers | ≈ 6 → ≈ 4 | One task pool for events + clicks (independent until dedup). Run the serial `drops_by` regroup in parallel. | ≈ 0.01 s | Very low |
| G8 | Classify ISA | SSE2 (≈ 40 instr / 64 B) → AVX2 (≈ 18) or AVX-512BW (≈ 8) | Guarded by a **startup self-test** (below) | ≈ 0.03 s | **High unless testable**: we can't run AVX-512 locally |
| G9 | Output | 100 → 5 | A hand-rolled plain-encoded Parquet writer per worker, straight from `Acc`. | ≈ 0.02 s | Medium: format exactness |
| G10 | Links | 40 → 10 | Hash instead of `binary_search` per pair; parallel union-find. Matters at 60M. | ≈ 0.01 s at 20M, ≈ 0.04 s at 60M | Low |

G1–G5 together take v3 from ≈ 2,700 to ≈ 400–500 instr/line **[est.]**. G6–G10 and tuning are worth another
≈ 100–150. **Getting under 0.28 s needs all of G1–G6 at about their targets.** That is the target
architecture, built incrementally on v3. No v3 code is thrown away: the scan, IDs, dedup design, decoder and
session loop all stay.

### G1: the exact quote-aware fast path

Inside `for_each_record`, for a line [ls, le) with exactly N−1 commas, record the quote bits (m[2]) the same
way the comma bits are recorded. For each field [s, e):
- if `buf[s] == '"'`: require `e − s ≥ 2` and `buf[e−1] == '"'`, then slice to [s+1, e−1) and count 2 quotes;
- the line is accepted only if `popcount(quote bits in [ls, le)) == counted quotes`.

That accepts exactly the lines `split_fields` accepts with ≥ 1 quote.
- A quote inside a field, or a lone quote at a field's end, makes the counts differ.
- `"` alone fails `e − s ≥ 2`.
- `""` becomes empty, as in `split_fields`.

A line longer than one 64 B block needs its quote bits accumulated across blocks, the same way commas are.
A bit-array of quote positions per line is enough, since a valid line has at most 2N quotes. Anything over that
falls back.

**Verify with:**
- the v3-review `scan` case and all 82 Eval dialect cases at `CHUNK=1/97`;
- a new unit test: random lines over the alphabet `{a, ",", ",", "\"", "\r", " "}` with N−1 to N+1 commas,
  fast path vs `split_fields`, ≥ 10⁶ lines;
- fuzz under `NO_FAST=3`.

### G2: compact streams and sorting with no copy

- **Row (16 B):** `person u64`, then `ts_off u32` = (ts − (window_start − 7 d)) in ms, then
  `price:24 | cat:8` as a u32.
  - The click window plus the event window is 21 days, or 1.81 × 10⁹ ms < 2³¹. Price is at most 10⁷ < 2²⁴.
  - If the manifest window is wider than 2³² ms, or there are more than 255 categories, use the current 24 B
    layout. v3 already has a `wide` flag.
- **Dedup entry (16 B):** `eid u64`, then `ingest_off u32` in **seconds**, then `ref u32`.
  - `ingest_ts` is always valid F1 (whole seconds) by the rules. Store `(ingest_ms − base_ms) / 1000` when the
    ms value is a whole second and the offset fits; otherwise set a global "wide ingest" flag and rerun the
    task with the 24 B layout.
  - Unparsable ingest becomes `u32::MAX`, which keeps v3's `i64::MAX` ordering.
  - Ties stay ties: equal ms means equal seconds.
- **process_part without `PEv`:**
  1. Pass 1 reads the task segments, interns persons (L1/L2 table, ≈ 2.7k persons per partition at 20M) and
     counts rows per local person.
  2. Pass 2 scatters into one contiguous 16 B buffer at prefix-sum offsets (counting sort by person).
  3. Sort each person's run by `ts_off`: insertion sort for ≤ 32 rows (the mean is ≈ 30), and a radix sort
     on u32 for whales. Clicks get the same treatment.
  - That replaces pdqsort over 24 B structs (≈ 17 comparisons per row) with ≈ 2 streaming passes plus ≈ 8
    comparisons per row.
  - Ties in `ts` have no required order ("in whatever order they were read"), so an unstable sort stays
    exact.
- **Verify with:** fixtures, dev, every oracle, fuzz under all knobs, and the v3-review `whale` case
  (60k rows, one person). Add a fuzz focus with a window wider than 24 days, to force the wide layout.

### G8: SIMD past SSE2 only behind a startup self-test

The scorer builds with `target-cpu=cascadelake`, but nothing local can execute AVX-512. That includes QEMU and
Rosetta. Two rules:
1. Prefer AVX2. First check that the amd64 Docker image on this Mac actually reports `avx2` in
   `/proc/cpuinfo` under Rosetta. If it doesn't, AVX2 is untested too.
2. Any ISA path we can't run locally ships behind a **startup self-test**. Classify a fixed 4 KB pattern
   (every byte value at every lane) with the SIMD path and the SWAR path. Use SIMD only if the two agree
   bit for bit. That costs ≈ 10 µs, and it turns a miscompile or wrong intrinsic into a fallback instead of
   wrong output.

## 3. Structural points the incremental path can't reach

1. **Two writes per event row is the minimum, so make both 16 B.** Links have to finish before events, dedup
   is global over `event_id`, and sessions need all of a person's events. So a single fused pass with no
   intermediate rows can't be exact.
   - One in 64 duplicated events names a different user in its later copies. Dedup inside person partitions
     would need the cross-partition fix-up that v3's drop stream already is.
   - The floor is one dedup entry and one row per event, each written once and read once. Beyond 16 B each,
     every extra byte costs ≈ 2 × 20.5M × 1 B ≈ 41 MB of traffic.
2. **Every phase must be branch-light per field, not just per line.** At 250 instructions per line, one
   unpredictable branch per field (≈ 15 cycles × 7) is a large share of the budget.
   - v3's per-delimiter loop branches three ways per bit.
   - The target works line by line from the newline mask. It extracts the N−1 comma positions with `tzcnt` and
     the `x & (x − 1)` reset, with no per-bit type test, then validates and decodes with straight-line code.
3. **Output straight from partitions.** v3 already builds user rows per fold accumulator and writes one Parquet
   file per accumulator. A plain-encoded, uncompressed writer that writes columns straight from `Acc` would skip
   Arrow's `RecordBatch` (G9). It's worth doing only after G1–G6.
4. **Schedule against skew.** Whales (5 × 1–2% of events) and shared-device mega-persons put 5–10× the mean
   rows into a few partitions. On 8 threads, the largest partition sets the tail of sessions, unless partitions
   run in descending size order (G6). A whale with 400k rows is too big to split, since it's one person, but
   sorting first lets it overlap with the others.
5. **No new fixed costs.** No `MAP_POPULATE` over all input in one thread, no `read()` copies (≈ 0.18 core-s
   for 1.75 GB) and no thread pools beyond rayon's one. An untested option: `MADV_POPULATE_READ` per worker
   range, which might save the ≈ 27k file faults inside the parse. Measure it on Linux before using it.

## 4. Who does what

The three threads' parse work doesn't overlap: Method owns the scan loop, Explorer 2 owns field decode and the
sort kernels, and Sol owns links and the audit.

### Method (`method/v4`, branched from v3; one move per commit, each gated)

1. **G1 quote-aware fast path** in `for_each_record`, for events, clicks and links. The unit test above is part
   of the commit. Expected ≈ −470 instr/line, ≈ −1.3 core-s or ≈ −0.2 s local wall at 20M **[est.]**.
2. **G2 compact streams + counting-sort `process_part`**, with the `wide` fallback layouts. Expected ≈ −600
   instr/line and ≈ −1.5 GB of traffic.
3. **G6 + G7:** sort partitions by size, one events + clicks task pool, a parallel drop regroup, and P scaled
   to input bytes.
4. **Integrate Explorer 2's packer and sort kernels** (G3) when they arrive with their equivalence tests.

Stop rule: after each move, Eval's quick profile reports instructions per line. If a move delivers less than
half its estimate, profile it before the next move.

### Explorer 2 (Grok + Gemini: radix sort, parse path, input I/O and threads)

1. **SWAR or SIMD ID packer**, a drop-in for `pack()`: NEON `tbl` and SSSE3 `pshufb` nibble LUT, plus the
   portable SWAR. Include an exhaustive test against `pack()` over all strings up to 3 chars, 10⁷ random strings
   up to 12 chars, and every single-byte change of 10/11-character strings. Report instructions per ID.
2. **Per-person sort kernels for G2:** counting sort by local person, insertion sort below 32 rows, and an LSD
   radix sort on u32 `ts_off` for big runs. Benchmark them on real seed-42 partitions (dump 3 partitions,
   including the whale's). Report instructions per row.
3. **AVX2 classifier + startup self-test** (G8). First answer whether the amd64 container exposes `avx2`
   under Rosetta. If it doesn't, ship the self-test only and keep SSE2.
4. **Input I/O on Linux (arm64 container, the 20M named volume):** plain mmap vs `MADV_POPULATE_READ` per worker
   range vs `MAP_POPULATE`, cold and warm. Report minor faults, sys CPU and the parse-phase wall.

### Explorer (Sol: parallel links, unneeded-work audit)

1. **Links (G10):** hash-map dense indexing instead of `binary_search` per pair, plus a parallel union-find
   (CAS-based link-by-index, then pointer jumping). Measure at 60M, where links and lookups are ≈ 0.3 s on v1.
   The 1-in-20,000 chains of 50–400 IDs are the correctness edge.
2. **Unneeded-work audit, with a number for each item:**
   - the category lookup on non-purchase rows (it's used only when `price > 0`);
   - the `rf` ref and dedup entry for rows with an empty `event_id` (already skipped; confirm);
   - clicks of persons with no events. After the events phase, a per-partition person bitset could skip them
     at the click push.
   - the serial `drops_by` loop;
   - how many `Acc` accumulators `fold` actually creates. Each is (2,001 × 14 × 32 B) ≈ 0.9 MB zeroed and then
     merged serially.
   - the assist loop's cost per session (`for &c in &active.list`) for whale campaigns with many clicks.
3. **Skew report (G6):** row counts per person partition at 20M and 60M (max/mean, top 5), and the wall of the
   slowest `process_part`. That decides whether size-ordered scheduling is enough.

## 5. Requests for Eval (needed to steer v4)

- **Calibration:** ask the user to submit v3 as soon as Gate A passes, and record the board time in
  `evals/submissions.json` and `calibration.json`. Everything in §1 assumes 25 G instr/s, and one point fixes
  that.
- **Per-phase instructions:** add instructions per event line **per phase** to the quick profile (perf counters
  read at each `lap`, or `kperf` locally). The total alone can't show which move under-delivered.
- **Fast-path coverage:** add a stats-only debug counter (`SESSIONS_DEBUG_STATS=1`, stderr) for the fraction
  of lines on the fast path, per input kind. The 79% gap was invisible in every eval so far.
- **Skew:** report the max/mean partition rows and the wall of the slowest partition.

## 6. Confidence and open questions

- **High:** the quote finding (measured on a sample of real data), the exactness of the G1 rule (it mirrors
  `split_fields` exactly), and the ordering of G1–G3.
- **Medium:** per-phase v3 instruction counts. They're derived, not measured. Check them against Eval's v3
  marks.
- **Low:** the absolute scorer model (25 G instr/s, 30 GB/s). The alternative reading is 8 vCPUs = 8 physical
  cores, or a newer Xeon, which halves every per-line requirement. **The v3 submission settles this.**
- **Open:**
  - Can the leaders' 0.28 s include a warm page cache? We can't control that either way. Our budget assumes
    the input is cached, as the board's repeated runs are likely to be.
  - Does a different chunk size beat 4 MB once the per-line cost drops 5×? Tails shrink with smaller chunks,
    while per-task overhead (256 partition Vec headers) grows.
