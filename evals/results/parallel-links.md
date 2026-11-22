# Eval: parallel-links (89ad72cab915, profile quick)

**Verdict: HOLD** (provisional)

- incomplete evaluation (use --profile full)
- Gate A: fixtures amd64 container 36/36 not run
- Gate A: dev MATCH amd64 container not run
- Gate B: writes only to output/scratch (read-only container run) not run
- Gate B: image builds from clean not run

Run 2026-11-21T19:19:28-0500 → 2026-11-21T19:24:37-0500, 308.9 s. Host: Apple M5 Pro, 15 CPUs. Evaluator 6d97ad78fa1d+dirty.

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
| B | 60M peak memory <= 16 GB | PASS | peak footprint 5.99 GB; max RSS incl. file-backed pages 11.40 GB |
| B | 60M local wall <= 30 s | PASS | median 5.95 s |
| B | stdout < 1 MB | PASS | max 0 bytes |
| B | threads < 1000 | PASS | max 9 sampled (dev, NCPU=8) |
| B | writes only to output/scratch (read-only container run) | NOT_RUN |  |
| B | image builds from clean | NOT_RUN |  |
| B | repo < 50 MB, no data | PASS | 1.17 MB tracked |
| C | >= 5% faster than v1 (submit-ready) | PASS | 0.676s vs 1.550s = +56.4% (local, baseline's own result JSON) |
| C | > 2x pooled stdev | PASS | delta 0.8743s vs 2sd 0.0562s |

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
| dev (perf-1M) | 11 | 0.080s | 0.076s | 0.082s | 0.0146 | 1199.6 | 13.4 | 0.48 | 0.19/0.12 | 0.33 GB | 0.43 GB | yes |
| seed-42 (perf-20M) | 5 | 0.676s | 0.619s | 0.680s | 0.0257 | 2835.3 | 31.8 | 0.81 | 3.83/0.52 | 2.07 GB | 3.99 GB | no |
| seed-43 (perf-60M) | 1 | 5.955s | 5.955s | 5.955s | 0.0000 | 957.3 | 10.8 | 0.37 | 12.37/5.11 | 5.99 GB | 11.40 GB | no |

Phases, dev (median of 11 runs):

| Phase | Wall | Share | CPU | CPU / wall |
| --- | --- | --- | --- | --- |
| lookups | 0.005s | 6% | 0.019s | 3.60 |
| events parsed | 0.017s | 21% | 0.120s | 7.00 |
| clicks parsed | 0.005s | 6% | 0.020s | 3.80 |
| events deduped | 0.001s | 1% | 0.009s | 9.00 |
| sessions + attribution | 0.012s | 15% | 0.090s | 7.50 |
| written | 0.020s | 25% | 0.064s | 3.20 |
| (after last mark: exit/unmap + spawn) | 0.020s | 25% | n/a | n/a |

Resources (median): page reclaims 25813, page faults 0, vol ctx sw 2, invol ctx sw 2013, peak footprint 0.31 GiB
Hardware counters (median): instructions/row 2,955.61, cycles/row 1,281.06, IPC 2.31

Phases, seed-42 (median of 5 runs):

| Phase | Wall | Share | CPU | CPU / wall |
| --- | --- | --- | --- | --- |
| lookups | 0.025s | 4% | 0.155s | 6.24 |
| events parsed | 0.309s | 46% | 2.420s | 7.83 |
| clicks parsed | 0.050s | 7% | 0.377s | 7.58 |
| events deduped | 0.034s | 5% | 0.258s | 7.47 |
| sessions + attribution | 0.119s | 18% | 0.933s | 7.83 |
| written | 0.036s | 5% | 0.219s | 5.79 |
| (after last mark: exit/unmap + spawn) | 0.095s | 14% | n/a | n/a |

Resources (median): page reclaims 242699, page faults 0, vol ctx sw 22, invol ctx sw 7607, peak footprint 1.93 GiB
Hardware counters (median): instructions/row 2,568.28, cycles/row 842.52, IPC 3.05

Phases, seed-43 (median of 1 runs):

| Phase | Wall | Share | CPU | CPU / wall |
| --- | --- | --- | --- | --- |
| lookups | 0.096s | 2% | 0.431s | 4.49 |
| events parsed | 3.953s | 66% | 9.866s | 2.50 |
| clicks parsed | 0.862s | 14% | 1.593s | 1.85 |
| events deduped | 0.234s | 4% | 1.487s | 6.36 |
| sessions + attribution | 0.506s | 8% | 3.436s | 6.79 |
| written | 0.077s | 1% | 0.526s | 6.83 |
| (after last mark: exit/unmap + spawn) | 0.227s | 4% | n/a | n/a |

Resources (median): page reclaims 465811, page faults 347964, vol ctx sw 38, invol ctx sw 354383, peak footprint 5.58 GiB
Hardware counters (median): instructions/row 2,802.70, cycles/row 1,120.34, IPC 2.50

## Size scaling

- perf-20M/perf-1M: time ×8.424 for events ×20.062
- perf-60M/perf-20M: time ×8.814 for events ×2.983
- perf-60M/perf-1M: time ×74.247 for events ×59.837
- perf-1M: 74.81 ns/event
- perf-20M: 31.41 ns/event
- perf-60M: 92.82 ns/event

## Constraints and sizes

- threads max 9 (dev, NCPU=8); stdout max 0 bytes
- binary 4.00 MB; images
- repo tracked 1.17 MB
- native build 48.84s (cached)
- probe on dev: sampled RSS max 0.07 GiB

Baseline for Gate C: v1 (submit-ready), 20M median 1.550s
