# Eval: allocator-jemalloc (13a78473ff99, profile linux)

**Verdict: HOLD** (provisional)

- Gate C: > 2x pooled stdev (delta 0.0996s vs 2sd 0.2008s)
- Gate A: fixtures amd64 container 36/36 not run
- Gate A: dev MATCH amd64 container not run
- Gate B: 60M peak memory <= 16 GB not run
- Gate B: 60M local wall <= 30 s not run
- Gate B: threads < 1000 not run
- Gate B: writes only to output/scratch (read-only container run) not run
- Gate B: image builds from clean not run
- predicted board 20M: 3.181s from 4,255 instr/row (26.8 G/s + 0.000s fixed); 4.963s from local wall (×3.10). Target: 0.28 s ⇒ 14 ns/row ⇒ ≤ 308–375 instructions/row (fixed 0.05–0.00 s, 26.8 G instr/s effective)

## Predicted board time (20M practice)

| Predictor | Predicted board | Input | Model |
| --- | --- | --- | --- |
| instructions (primary) | **3.181 s** | 4,255 instr/row | 0.000 s + instr/row × 20M / 26.75 G/s (rate, 1 point(s)) |
| local wall | 4.963 s | 20M median | 0.000 s + 3.103 × local (ratio, 1 point(s)) |

Target: 0.28 s ⇒ 14 ns/row ⇒ ≤ 308–375 instructions/row (fixed 0.05–0.00 s, 26.8 G instr/s effective).
Primary prediction is above the 0.28 s target.

Run 2026-11-21T18:39:28-0500 → 2026-11-21T18:41:57-0500, 149.0 s. Host: Apple M5 Pro, 15 CPUs. Evaluator e93a363c8f45+dirty.

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
| C | >= 5% faster than v1 (submit-ready) | PASS | 1.606s vs 1.706s = +5.8% (local, interleaved A/B in this eval) |
| C | > 2x pooled stdev | FAIL | delta 0.0996s vs 2sd 0.2008s |
| C | Linux 20M A/B | SUPPORTS | 1.5580s vs 1.8709s (+16.7%, 5 pairs) |

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
| seed-42 (perf-20M) | 5 | 1.599s | 1.550s | 1.750s | 0.0799 | 1197.6 | 13.4 | 0.82 | 9.73/0.78 | 4.36 GB | 6.28 GB | no |

Phases, seed-42 (median of 5 runs):

| Phase | Wall | Share | CPU | CPU / wall |
| --- | --- | --- | --- | --- |
| lookups | 0.103s | 6% | 0.123s | 1.19 |
| events parsed | 0.681s | 43% | 5.374s | 7.90 |
| clicks parsed | 0.139s | 9% | 1.034s | 7.52 |
| events deduped | 0.177s | 11% | 1.367s | 7.72 |
| sessions + attribution | 0.294s | 18% | 2.244s | 7.58 |
| written | 0.045s | 3% | 0.256s | 5.78 |
| (after last mark: exit/unmap + spawn) | 0.151s | 9% | n/a | n/a |

Resources (median): page reclaims 402041, page faults 0, vol ctx sw 5, invol ctx sw 3706, peak footprint 4.06 GiB
Hardware counters (median): instructions/row 4,255.00, cycles/row 2,064.54, IPC 2.06

## Linux and native 20M timing

| Runtime | Version | Runs | Median | Min | Minor faults / row | Major faults / row |
| --- | --- | --- | --- | --- | --- | --- |
| Linux arm64 | allocator-jemalloc | 5 | 1.558s | 1.510s | 0.001393 | 0.000000 |
| Linux arm64 | v1 | 5 | 1.871s | 1.859s | 0.037875 | 0.000000 |
| Native | allocator-jemalloc | 5 | 1.606s | 1.545s | n/a | n/a |
| Native | v1 | 5 | 1.706s | 1.604s | n/a | n/a |

Named volume, 8 CPUs, 24 GiB cgroup limit, THP always, page size 4096 B.

| Linux metric | Candidate median | Baseline median |
| --- | --- | --- |
| Minor faults | 29,960 | 814,613 |
| Major faults | 0 | 0 |
| System CPU (s) | n/a | n/a |
| Exit tail (s) | n/a | n/a |
| VM THP allocations | n/a | n/a |
| VM THP fallbacks | n/a | n/a |
| Peak sampled anonymous (GiB) | n/a | n/a |
| Peak sampled anonymous huge pages (GiB) | n/a | n/a |

## Constraints and sizes

- threads max None (None); stdout max 0 bytes
- binary 4.12 MB; images arm64 143 MB
- repo tracked 0.52 MB
- native build 21.77s; image arm64 43.7s

Baseline for Gate C: v1 (submit-ready), 20M median 1.550s
