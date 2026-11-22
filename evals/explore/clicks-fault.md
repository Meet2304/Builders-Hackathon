# Clicks phase: fewer fresh pages (explore/clicks-fault, base 0340530)

Goal: cut what the clicks phase allocates and touches (v5: 111 ms plain → 197 ms runsc).

## What touched fresh pages

At 20M (seed-42: 5.15M click lines, 275 MB), the clicks phase added about 30.6k minor faults
(16 KB mac pages), or about 478 MB of RSS:
- the mmapped click files: 275 MB (file-backed; v2 already measured fault-around as cheap).
- the rows: each task (4 MB chunk, about 70 tasks) had 256 bucket `Vec<Ck>`, each presized to
  `bytes/60/nb*1.25`. Real lines are about 53 B, so the headroom was about 16%. Mimalloc packs the
  buckets next to each other, so the gaps (under a page) were touched anyway. With 32 B rows
  that came to about 205 MB of touched capacity for about 155 MB of data.
- The sort scratch in `process_part` (`cks`, `ck_spare`, `ck_at`) is per worker and reused
  across partitions: not a source.

## Changes

1. **`Ck` from 32 B to 24 B.** `tc = (ts - base) << ckb | camp`, where `ckb` is the bit width
   of `ncamp` (11 bits for 2,000 campaigns). At startup the code asserts that `end - base`
   fits in `64 - ckb` bits. With 4-digit years that is always true for fewer than 2^15
   campaigns.
2. **One exact-size allocation per task.** The parse pushes into a per-worker `flat` buffer,
   reused across tasks through `map_init`. `CkOut::finish` then does a stable counting scatter
   by partition into a single `Vec<Ck>` of exactly n rows, plus an `off[nb+1]` array. `CkPart`
   implements `Index<usize, Output=[Ck]>`, so the `&part[p]` call sites are unchanged. Order
   within a partition is still parse order.
3. A debug knob, `SESSIONS_DEBUG_FAULTS=1`, adds cumulative `minflt` and `maxrss` to each
   phase log line (getrusage; off by default).

## Numbers (mac native, seed-42 20M, NCPU=8, nice 19, 2 runs each, deltas consistent)

| binary (sha256) | clicks-phase minflt | clicks-phase RSS | clicks-phase instr | total minflt | peak RSS |
|---|---|---|---|---|---|
| base 0340530 + knob `dcf67065b390` | +30.6k | +478 MB | 2.38 G | 254k | 3958 MB |
| 24 B Ck `bebc7df94b20` | +28.7k | +449 MB | 2.34 G | 252k | 3947 MB |
| + exact per-task alloc `c76c19445f21` | **+24.9k** | **+389 MB** | **2.23 G** | **247k** | **3851 MB** |

The clicks phase is now at its floor: the file map (275 MB) plus 24 B × the valid clicks
(about 115 MB). On Linux with 4 KB pages, the anonymous part drops from about 205 MB to about
115 MB, which is about 22k fewer 4 KB faults if there are no huge pages. That reduction matters
under gVisor.

## Gates

fixtures 36/36; dev MATCH, also under NO_FAST=1/2/3; seed-42 MATCH; seed-62-20m MATCH;
`cargo test --release` 22 passed; sampled fuzz (every 7th case of the 4 generators × 4 knob
configs: default, NO_FAST=2, CHUNK=97 PARTS=3, NO_FAST=1 PARTS=1): 2616 runs, 0 failures.

## Port recipe

The changes are local to `Ck`, `CkOut`/`CkPart`, the clicks `par_chunks` block in `pipeline`,
the two `sort_clicks_*` functions (`c.ts(ctx)`, `c.camp(ctx)`; `counted` now takes `ctx`),
`Ctx.ckb`, `Win.{ck_base,ckb}` (set in `main` right after `ncamp` is known), and one
constructor line in `columns.rs`.

Not tried, and needs runsc: `MADV_POPULATE_READ` per task range on the click maps. The file
part (275 MB) is now about 70% of the phase's fresh pages.
