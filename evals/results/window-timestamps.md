# Eval: window-timestamps (d1da46eb91f9, profile quick)

**Verdict: HOLD** (provisional)

- Gate C: >= 5% faster than v1 (submit-ready) (1.584s vs 1.550s = -2.2% (local, baseline's own result JSON))
- Gate C: > 2x pooled stdev (delta -0.0345s vs 2sd 0.0788s)
- Gate A: fixtures amd64 container 36/36 not run
- Gate A: dev MATCH amd64 container not run
- Gate B: writes only to output/scratch (read-only container run) not run
- Gate B: image builds from clean not run
- predicted board 20M: 2.774s from 3,711 instr/row (26.8 G/s + 0.000s fixed); 4.916s from local wall (×3.10). Target: 0.28 s ⇒ 14 ns/row ⇒ ≤ 308–375 instructions/row (fixed 0.05–0.00 s, 26.8 G instr/s effective)
- WARNING: 60M max RSS incl. file-backed (page-cache) pages is 16.26 GB > 16 GB: page cache counts against the scorer's cgroup, so reclaim pressure is possible near 24 GB

## Predicted board time (20M practice)

| Predictor | Predicted board | Input | Model |
| --- | --- | --- | --- |
| instructions (primary) | **2.774 s** | 3,711 instr/row | 0.000 s + instr/row × 20M / 26.75 G/s (rate, 1 point(s)) |
| local wall | 4.916 s | 20M median | 0.000 s + 3.103 × local (ratio, 1 point(s)) |

Target: 0.28 s ⇒ 14 ns/row ⇒ ≤ 308–375 instructions/row (fixed 0.05–0.00 s, 26.8 G instr/s effective).
Primary prediction is above the 0.28 s target.

Run 2026-11-21T18:25:01-0500 → 2026-11-21T18:25:49-0500, 47.7 s. Host: Apple M5 Pro, 15 CPUs. Evaluator 02e24a24450d.

## Gates

| Gate | Check | Status | Detail |
| --- | --- | --- | --- |
| A | fixtures native 36/36 | PASS | 36/36 |
| A | fixtures amd64 container 36/36 | NOT_RUN |  |
| A | dev MATCH native | PASS | MATCH |
| A | dev MATCH amd64 container | NOT_RUN |  |
| A | differential vs reference (all oracle datasets) | PASS | 10/10 MATCH |
| A | fuzz/adversarial strict MATCH | PASS | 129/129 (seeds 0..149) |
| A | SESSIONS_DEBUG_HASH_BITS=4 | PASS |  |
| A | SESSIONS_DEBUG_CHUNK=97 | PASS |  |
| A | SESSIONS_DEBUG_PARTS=1 | PASS |  |
| A | SESSIONS_DEBUG_PARTS=4096 | PASS |  |
| A | SESSIONS_DEBUG_NO_FAST=1 | PASS |  |
| A | deterministic canonical hash | PASS | 19 runs over 3 datasets |
| B | 60M peak memory <= 16 GB | PASS | peak footprint 11.53 GB; max RSS incl. file-backed pages 16.26 GB |
| B | 60M local wall <= 30 s | PASS | median 9.59 s |
| B | stdout < 1 MB | PASS | max 0 bytes |
| B | threads < 1000 | PASS | max 9 sampled (dev, NCPU=8) |
| B | writes only to output/scratch (read-only container run) | NOT_RUN |  |
| B | image builds from clean | NOT_RUN |  |
| B | repo < 50 MB, no data | PASS | 0.52 MB tracked |
| C | >= 5% faster than v1 (submit-ready) | FAIL | 1.584s vs 1.550s = -2.2% (local, baseline's own result JSON) |
| C | > 2x pooled stdev | FAIL | delta -0.0345s vs 2sd 0.0788s |

## Correctness

- fixtures_native: 36/36
- dev_answer_native: MATCH

| Dataset | Kind | Result | user_daily rows | campaign_daily rows |
| --- | --- | --- | --- | --- |
| dev | oracle | MATCH | 117038 | 27400 |
| seed-2 | oracle | MATCH | 25041 | 19032 |
| seed-3 | oracle | MATCH | 25329 | 19018 |
| seed-4 | oracle | MATCH | 25204 | 19139 |
| seed-5 | oracle | MATCH | 25139 | 18987 |
| seed-6 | oracle | MATCH | 24728 | 18871 |
| seed-15 | oracle | MATCH | 36881 | 22115 |
| seed-62 | oracle | MATCH | 37083 | 22190 |
| seed-62-20m | oracle | MATCH | 2249561 | 28014 |
| seed-42 | oracle | MATCH | 2246306 | 28014 |
| seed-43 | consistency | invariants OK; MATCH vs v1 | 6671410 | 28014 |

Fuzz (gen c05c7a1570ec, seeds 0..149): strict 129/129 MATCH, robust 21/21.

Determinism: dev same hash over 12 runs (files not byte-identical), seed-42 same hash over 6 runs (files not byte-identical), seed-43 same hash over 1 runs

Debug knobs
- `SESSIONS_DEBUG_HASH_BITS=4`: pass
- `SESSIONS_DEBUG_CHUNK=97`: pass
- `SESSIONS_DEBUG_PARTS=1`: pass
- `SESSIONS_DEBUG_PARTS=4096`: pass
- `SESSIONS_DEBUG_NO_FAST=1`: pass

## Performance (native, NCPU=8)

| Dataset | Runs | Median | Min | p90 | Stdev | MB/s | Mev/s | CPU util | user/sys | Peak footprint | Max RSS (incl. file pages) | Noisy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dev (perf-1M) | 11 | 0.133s | 0.129s | 0.135s | 0.0022 | 723.4 | 8.1 | 0.45 | 0.36/0.11 | 0.35 GB | 0.55 GB | no |
| seed-42 (perf-20M) | 5 | 1.584s | 1.503s | 1.630s | 0.0467 | 1209.0 | 13.6 | 0.83 | 9.64/0.83 | 4.14 GB | 6.46 GB | no |
| seed-43 (perf-60M) | 1 | 9.591s | 9.591s | 9.591s | 0.0000 | 594.4 | 6.7 | 0.57 | 35.27/8.77 | 11.53 GB | 16.26 GB | no |

Phases, dev (median of 11 runs):

| Phase | Wall | Share | CPU | CPU / wall |
| --- | --- | --- | --- | --- |
| lookups | 0.006s | 5% | 0.010s | 1.67 |
| events parsed | 0.024s | 18% | 0.167s | 7.00 |
| clicks parsed | 0.007s | 5% | 0.032s | 4.57 |
| events deduped | 0.012s | 9% | 0.078s | 6.58 |
| sessions + attribution | 0.015s | 11% | 0.113s | 7.60 |
| written | 0.019s | 14% | 0.083s | 4.30 |
| (after last mark: exit/unmap + spawn) | 0.051s | 38% | n/a | n/a |

Resources (median): page reclaims 39125, page faults 0, vol ctx sw 4, invol ctx sw 1991, peak footprint 0.32 GiB
Hardware counters (median): instructions/row 4,146.13, cycles/row 1,902.49, IPC 2.18

Phases, seed-42 (median of 5 runs):

| Phase | Wall | Share | CPU | CPU / wall |
| --- | --- | --- | --- | --- |
| lookups | 0.103s | 7% | 0.121s | 1.18 |
| events parsed | 0.672s | 42% | 5.279s | 7.86 |
| clicks parsed | 0.140s | 9% | 1.063s | 7.54 |
| events deduped | 0.205s | 13% | 1.443s | 7.01 |
| sessions + attribution | 0.292s | 18% | 2.293s | 7.85 |
| written | 0.054s | 3% | 0.302s | 5.76 |
| (after last mark: exit/unmap + spawn) | 0.111s | 7% | n/a | n/a |

Resources (median): page reclaims 414966, page faults 0, vol ctx sw 6, invol ctx sw 11072, peak footprint 3.85 GiB
Hardware counters (median): instructions/row 3,711.40, cycles/row 2,069.55, IPC 1.80

Phases, seed-43 (median of 1 runs):

| Phase | Wall | Share | CPU | CPU / wall |
| --- | --- | --- | --- | --- |
| lookups | 0.355s | 4% | 0.397s | 1.12 |
| events parsed | 5.144s | 54% | 22.186s | 4.31 |
| clicks parsed | 1.041s | 11% | 4.978s | 4.78 |
| events deduped | 1.589s | 17% | 6.864s | 4.32 |
| sessions + attribution | 1.124s | 12% | 8.668s | 7.71 |
| written | 0.111s | 1% | 0.746s | 6.72 |
| (after last mark: exit/unmap + spawn) | 0.227s | 2% | n/a | n/a |

Resources (median): page reclaims 1370538, page faults 347988, vol ctx sw 6, invol ctx sw 507415, peak footprint 10.74 GiB
Hardware counters (median): instructions/row 4,130.34, cycles/row 2,865.77, IPC 1.44

## Size scaling

- perf-20M/perf-1M: time ×11.913 for events ×20.062
- perf-60M/perf-20M: time ×6.053 for events ×2.983
- perf-60M/perf-1M: time ×72.109 for events ×59.837
- perf-1M: 124.06 ns/event
- perf-20M: 73.67 ns/event
- perf-60M: 149.5 ns/event

## Constraints and sizes

- threads max 9 (dev, NCPU=8); stdout max 0 bytes
- binary 3.82 MB; images 
- repo tracked 0.52 MB
- native build 17.49s (cached)
- probe on dev: sampled RSS max 0.31 GiB

Baseline for Gate C: v1 (submit-ready), 20M median 1.550s
