# Eval: allocator-mimalloc (3cf92b03367c, profile linux)

**Verdict: HOLD** (provisional)

- incomplete evaluation (use --profile full)
- Gate A: fixtures amd64 container 36/36 not run
- Gate A: dev MATCH amd64 container not run
- Gate B: 60M peak memory <= 16 GB not run
- Gate B: 60M local wall <= 30 s not run
- Gate B: threads < 1000 not run
- Gate B: writes only to output/scratch (read-only container run) not run
- Gate B: image builds from clean not run

Run 2026-11-21T18:35:39-0500 → 2026-11-21T18:37:43-0500, 124.0 s. Host: Apple M5 Pro, 15 CPUs. Evaluator e93a363c8f45+dirty.

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
| A | deterministic canonical hash | PASS | 6 runs over 1 datasets |
| B | 60M peak memory <= 16 GB | NOT_RUN |  |
| B | 60M local wall <= 30 s | NOT_RUN |  |
| B | stdout < 1 MB | PASS | max 0 bytes |
| B | threads < 1000 | NOT_RUN |  |
| B | writes only to output/scratch (read-only container run) | NOT_RUN |  |
| B | image builds from clean | NOT_RUN |  |
| B | repo < 50 MB, no data | PASS | 0.52 MB tracked |
| C | >= 5% faster than v1 (submit-ready) | PASS | 1.559s vs 1.655s = +5.8% (local, interleaved A/B in this eval) |
| C | > 2x pooled stdev | PASS | delta 0.0967s vs 2sd 0.0747s |
| C | Linux 20M secondary signal | SUPPORTS | 1.5528s vs 1.9569s (+20.6%, 5 pairs) |

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

Fuzz (gen c05c7a1570ec, seeds 0..149): strict 129/129 MATCH, robust 21/21.

Determinism: seed-42 same hash over 6 runs (files not byte-identical)

Debug knobs
- `SESSIONS_DEBUG_HASH_BITS=4`: pass
- `SESSIONS_DEBUG_CHUNK=97`: pass
- `SESSIONS_DEBUG_PARTS=1`: pass
- `SESSIONS_DEBUG_PARTS=4096`: pass
- `SESSIONS_DEBUG_NO_FAST=1`: pass

## Performance (native, NCPU=8)

| Dataset | Runs | Median | Min | p90 | Stdev | MB/s | Mev/s | CPU util | user/sys | Peak footprint | Max RSS (incl. file pages) | Noisy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| seed-42 (perf-20M) | 5 | 1.601s | 1.552s | 1.895s | 0.1363 | 1196.3 | 13.4 | 0.85 | 10.08/0.90 | 3.98 GB | 5.90 GB | yes |

Phases, seed-42 (median of 5 runs):

| Phase | Wall | Share | CPU | CPU / wall |
| --- | --- | --- | --- | --- |
| lookups | 0.106s | 7% | 0.130s | 1.23 |
| events parsed | 0.693s | 43% | 5.456s | 7.87 |
| clicks parsed | 0.144s | 9% | 1.086s | 7.54 |
| events deduped | 0.207s | 13% | 1.585s | 7.61 |
| sessions + attribution | 0.306s | 19% | 2.340s | 7.66 |
| written | 0.042s | 3% | 0.260s | 6.45 |
| (after last mark: exit/unmap + spawn) | 0.110s | 7% | n/a | n/a |

Resources (median): page reclaims 360225, page faults 0, vol ctx sw 4, invol ctx sw 8817, peak footprint 3.71 GiB
Hardware counters (median): instructions/row 4,218.56, cycles/row 2,143.28, IPC 1.97

## Linux and native 20M timing

| Runtime | Version | Runs | Median | Min | Minor faults / row | Major faults / row |
| --- | --- | --- | --- | --- | --- | --- |
| Linux arm64 | allocator-mimalloc | 5 | 1.553s | 1.531s | 0.000972 | 0.000000 |
| Linux arm64 | v1 | 5 | 1.957s | 1.862s | 0.037772 | 0.000000 |
| Native | allocator-mimalloc | 5 | 1.559s | 1.550s | n/a | n/a |
| Native | v1 | 5 | 1.655s | 1.608s | n/a | n/a |

Named volume, 8 CPUs, 24 GiB cgroup limit, THP always, page size 4096 B.

## Constraints and sizes

- threads max None (None); stdout max 0 bytes
- binary 3.95 MB; images arm64 142 MB
- repo tracked 0.52 MB
- native build 19.28s (cached); image arm64 38.2s

Baseline for Gate C: v1 (submit-ready), 20M median 1.550s
