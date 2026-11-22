# Eval: v7b (96af24b7cfda, profile full)

**Verdict: HOLD**

- Gate C: gVisor 20M >= 5% faster and > 2x pooled stdev (gVisor 20M 1.360s vs v5 1.910s = +28.8% (same session, 3+3 interleaved runs; 2sd 0.653s))
- predicted board 20M: 2.135s from 1,359 instr/row (63.0 G/s + 1.703s fixed); 2.329s from local wall (×2.20 + 1.128s). Target: 0.28 s is below the fitted fixed cost of 1.70 s (63.0 G instr/s on the remainder). Cutting instructions does not reach it while that overhead remains.

## Headline

| Metric | Value |
| --- | --- |
| **20M under gVisor (primary predictor)** | **1.360 s** process (min 1.290, 3 runs); 1.562 s with runsc start/teardown; board estimate 1.309 s (×0.9623 from 1 point) |
| 20M gVisor: faults, RSS, output | ru_minflt 0, ru_majflt 0, cgroup pgfault 2,399,580 / pgmajfault 441, peak RSS 4.06 GiB, output 0.0 MB |
| 20M plain Docker: faults, RSS, output | ru_minflt 18,118, ru_majflt 0, cgroup pgfault 18,765 / pgmajfault 0, peak RSS 3.97 GiB, output 23.5 MB |
| 20M gVisor, baseline v5 (same session) | 1.910 s → candidate +28.8% |
| 20M plain Docker (same harness) | 0.550 s (gVisor adds +0.810 s) |
| **Predicted board 20M** | **2.135 s** (instructions model) |
| **Predicted board 60M** | **3.056 s** at 62.96 G/s, 3.135 s with the 6% cycle extra |
| Instructions per row (60M) | 1,328 |
| … instructions predictor | 2.135 s |
| … wall-ratio predictor | 2.329 s |
| **Instructions per row (20M)** | **1,359** |
| Linux arm64 20M | 0.434 s (11 runs, THP madvise) |
| Native 20M | 0.545 s; 0.469 s without the macOS exit tail |
| ru_minflt 20M | 254,448 |
| ru_majflt 20M | 0 |
| Peak RSS 20M | 3.88 GiB |
| Output bytes 20M | 23.5 MB |
| ru_minflt 60M | 756,409 |
| ru_majflt 60M | 4 |
| Peak RSS 60M | 11.54 GiB |
| Output bytes 60M | 69.3 MB |
| ru_minflt Linux 20M | 18,019 |
| ru_majflt Linux 20M | 0 |

## Compared with v5 (5b7bcc2395, the submitted reference)

Full table: [results/v7b-vs-v5.md](v7b-vs-v5.md). Δ is this version minus the reference. Significance needs > 2× pooled stdev, Welch |t| > 3 and ≥ 1%.

**Headline**

| Metric | v5 | v7b | Δ | Δ% | significance |
| --- | ---: | ---: | ---: | ---: | --- |
| predicted board 20M (instructions, primary) | 2.1424s | 2.1347s | -0.0076s | -0.4% |  |
| predicted board 20M (wall ratio) | 2.2318s | 2.3289s | +0.0971s | +4.4% |  |
| instructions/row 20M | 1,383 | 1,359 | -24.1 | -1.7% | better (t=-12.8) |
| cycles/row 20M | 596 | 684 | +87.8 | +14.7% | worse (t=18.2) |
| IPC 20M (M5) | 2.322 | 1.989 | -0.334 | -14.4% | worse (t=-24.2) |

**Same-session timing (B's eval re-timed v5 interleaved)**

| Metric | v5 | v7b | Δ | Δ% | significance |
| --- | ---: | ---: | ---: | ---: | --- |
| native 20M, interleaved A/B | 0.9927s | 0.5393s | -0.4534s | -45.7% | better (t=-35.7) |
| Linux arm64 20M, interleaved A/B | 0.7760s | 0.4340s | -0.3420s | -44.1% | better (t=-64.1) |
| Linux minor faults | 17,856 | 18,019 | +163 | +0.9% | ~ (t=11.0) |

**Per-phase counters, 20M (untimed probes)**

| Metric | v5 | v7b | Δ | Δ% | significance |
| --- | ---: | ---: | ---: | ---: | --- |
| total instr/row | 1,387 | 1,358 | -28.6 | -2.1% |  |
| total cycles/row | 594 | 680 | +85.1 | +14.3% |  |
| lookups instr/row | 26.7 | 36.5 | +9.87 | +37.0% |  |
| lookups cycles/row | 30.1 | 48.5 | +18.3 | +60.9% |  |
| events parsed instr/row | 710 | 768 | +58.2 | +8.2% |  |
| events parsed cycles/row | 280 | 364 | +84.1 | +30.1% |  |
| clicks parsed instr/row | 147 | 144 | -2.69 | -1.8% |  |
| clicks parsed cycles/row | 55.3 | 74 | +18.6 | +33.7% |  |
| events deduped instr/row | 37.1 | 35.8 | -1.26 | -3.4% |  |
| events deduped cycles/row | 49.8 | 46.4 | -3.4 | -6.8% |  |
| sessions + attribution instr/row | 329 | 239 | -89.1 | -27.1% |  |
| sessions + attribution cycles/row | 132 | 104 | -28.4 | -21.5% |  |
| written instr/row | 130 | 132 | +1.74 | +1.3% |  |
| written cycles/row | 43.8 | 43.3 | -0.56 | -1.3% |  |
| (after last mark: exit/unmap) instr/row | 6.96 | 0 | -6.96 | -100.0% |  |
| (after last mark: exit/unmap) cycles/row | 2.42 | 0 | -2.42 | -100.0% |  |
| fast-path share clicks | 1.000 | 1.000 | 0.000 | +0.0% |  |
| fast-path share events | 1.000 | 1.000 | 0.000 | +0.0% |  |
| fast-path share links | 1.000 | 1.000 | 0.000 | +0.0% |  |

**Per-phase counters, 60M (untimed probes)**

| Metric | v5 | v7b | Δ | Δ% | significance |
| --- | ---: | ---: | ---: | ---: | --- |
| total instr/row | 1,364 | 1,340 | -24 | -1.8% |  |
| total cycles/row | 612 | 731 | +118 | +19.3% |  |
| lookups instr/row | 23.7 | 34.9 | +11.1 | +46.8% |  |
| lookups cycles/row | 30.8 | 45.5 | +14.7 | +47.6% |  |
| events parsed instr/row | 707 | 763 | +56.2 | +7.9% |  |
| events parsed cycles/row | 274 | 375 | +102 | +37.2% |  |
| clicks parsed instr/row | 145 | 142 | -2.99 | -2.1% |  |
| clicks parsed cycles/row | 56.1 | 77.7 | +21.5 | +38.3% |  |
| events deduped instr/row | 37.3 | 39.4 | +2.11 | +5.7% |  |
| events deduped cycles/row | 76.5 | 80.4 | +3.86 | +5.0% |  |
| sessions + attribution instr/row | 328 | 242 | -86.5 | -26.4% |  |
| sessions + attribution cycles/row | 143 | 117 | -26 | -18.2% |  |
| written instr/row | 119 | 120 | +0.73 | +0.6% |  |
| written cycles/row | 33.2 | 34.7 | +1.51 | +4.5% |  |
| (after last mark: exit/unmap) instr/row | 5.16 | 0 | -5.16 | -100.0% |  |
| (after last mark: exit/unmap) cycles/row | 1.62 | 0 | -1.62 | -100.0% |  |
| fast-path share clicks | 1.000 | 1.000 | 0.000 | +0.0% |  |
| fast-path share events | 1.000 | 1.000 | 0.000 | +0.0% |  |
| fast-path share links | 1.000 | 1.000 | 0.000 | +0.0% |  |

## Predicted board time (20M practice)

| Predictor | Predicted board | Input | Model |
| --- | --- | --- | --- |
| instructions (primary) | **2.135 s** | 1,359 instr/row | 1.703 s + instr/row × 20M / 62.96 G/s (linear, 3 point(s)) |
| 60M final, instructions | **3.056 s** | 1,328 instr/row × 64.15M lines | ÷ 62.96 G/s (Analyst 2) |
| 60M final, with cycle extra | 3.135 s | the instruction estimate × 1.058 | v3's 60M/20M wall grew 6% faster than the event lines |
| local wall | 2.329 s | 20M median | 1.128 s + 2.202 × local (linear, 3 point(s)) |

Target: 0.28 s is below the fitted fixed cost of 1.70 s (63.0 G instr/s on the remainder). Cutting instructions does not reach it while that overhead remains..
Primary prediction is above the 0.28 s target.

Run 2026-11-22T02:22:03-0500 → 2026-11-22T02:43:21-0500, 1278.5 s. Host: Apple M5 Pro, 15 CPUs. Evaluator c44d3c96bbfd+dirty.

## Gates

| Gate | Check | Status | Detail |
| --- | --- | --- | --- |
| A | fixtures native 36/36 | PASS | 36/36 |
| A | fixtures amd64 container 36/36 | PASS | 36/36 |
| A | dev MATCH native | PASS | MATCH |
| A | dev MATCH amd64 container | PASS | MATCH |
| A | differential vs reference (all oracle datasets) | PASS | 10/10 MATCH |
| A | fuzz/adversarial strict MATCH | PASS | 852/852 (seeds 0..999) |
| A | fuzz windows focus strict MATCH | PASS | 227/227 (seeds 100000..100299) |
| A | review v3-review MATCH | PASS | 120/120 MATCH |
| A | amd64 container SESSIONS_DEBUG_NO_FAST=3: fixtures + dev | PASS | 36/36, dev MATCH |
| A | SESSIONS_DEBUG_HASH_BITS=4 | PASS |  |
| A | SESSIONS_DEBUG_CHUNK=97 | PASS |  |
| A | SESSIONS_DEBUG_PARTS=1 | PASS |  |
| A | SESSIONS_DEBUG_PARTS=4096 | PASS |  |
| A | SESSIONS_DEBUG_NO_FAST=1 | PASS |  |
| A | SESSIONS_DEBUG_HASH_BITS=0 | PASS |  |
| A | SESSIONS_DEBUG_PARTS=3 | PASS |  |
| A | SESSIONS_DEBUG_PARTS=255 | PASS |  |
| A | SESSIONS_DEBUG_CHUNK=1 | PASS |  |
| A | SESSIONS_DEBUG_CHUNK=4096 | PASS |  |
| A | reject SESSIONS_DEBUG_HASH_BITS=bad | PASS |  |
| A | reject SESSIONS_DEBUG_CHUNK=bad | PASS |  |
| A | reject SESSIONS_DEBUG_PARTS=bad | PASS |  |
| A | reject SESSIONS_DEBUG_PARTS=0 | PASS |  |
| A | reject SESSIONS_DEBUG_PARTS=4097 | PASS |  |
| A | empty output fixtures with default and one partition | PASS |  |
| A | deterministic canonical hash | PASS | 22 runs over 3 datasets |
| B | 60M peak memory <= 16 GB | PASS | peak footprint 6.24 GB; max RSS incl. file-backed pages 12.41 GB |
| B | 60M local wall <= 30 s | PASS | median 1.51 s |
| B | stdout < 1 MB | PASS | max 0 bytes |
| B | threads < 1000 | PASS | max 9 sampled (seed-43, NCPU=8) |
| B | writes only to output/scratch (read-only container run) | PASS | fixtures+dev in --read-only containers |
| B | image builds from clean | PASS | arm64 --no-cache in 38.7s |
| B | amd64 cascadelake builds from clean | PASS |  |
| B | 60M Linux runs within 22 GiB cgroup | PASS | cgroup peak 6.06 GiB |
| B | repo < 50 MB, no data | PASS | 2.61 MB tracked |
| C | gVisor 20M >= 5% faster and > 2x pooled stdev | FAIL | gVisor 20M 1.360s vs v5 1.910s = +28.8% (same session, 3+3 interleaved runs; 2sd 0.653s) |
| C | Linux 20M A/B | SUPPORTS | 0.4340s vs 0.7760s (+44.1%, 11 pairs) |
| C | Native: >= 5% faster than v5 (reference) | PASS | 2.316s vs 3.314s = +30.1% (estimated scorer, interleaved A/B in this eval) |
| C | Native: > 2x pooled stdev | PASS | delta 0.9985s vs 2sd 0.0900s |

## Correctness

- fixtures_native: 36/36
- fixtures_arm64: 36/36
- fixtures_amd64: 36/36
- dev_answer_native: MATCH
- dev_answer_arm64: MATCH
- dev_answer_amd64: MATCH

| Dataset | Kind | Result | user_daily rows | campaign_daily rows |
| --- | --- | --- | --- | --- |
| dev | oracle | MATCH | 118107 | 27449 |
| seed-2 | oracle | MATCH | 24869 | 19331 |
| seed-3 | oracle | MATCH | 25152 | 19261 |
| seed-4 | oracle | MATCH | 25056 | 19112 |
| seed-5 | oracle | MATCH | 24723 | 19160 |
| seed-6 | oracle | MATCH | 24833 | 18694 |
| seed-15 | oracle | MATCH | 37040 | 21986 |
| seed-62 | oracle | MATCH | 36986 | 22190 |
| seed-62-20m | oracle | MATCH | 2244415 | 28014 |
| seed-42 | oracle | MATCH | 2226091 | 28014 |
| seed-43 | consistency | invariants OK; no baseline yet (established now) | 6635538 | 28014 |

Fuzz (gen c681b1562f17, seeds 0..999): strict 852/852 MATCH, robust 148/148.

Fuzz `windows` focus (seeds 100000..100299): strict 227/227 MATCH, robust (off-midnight windows) 73/73.

Review suite `v3-review` (evals/insights/v3_review/run.py): 120/120 MATCH (cases.py 70/70 in 5.7s, cases_ts.py 50/50 in 10.3s).

amd64 container with `SESSIONS_DEBUG_NO_FAST=3`: fixtures 36/36, dev MATCH.

Determinism: dev same hash over 12 runs (files not byte-identical), seed-42 same hash over 6 runs (files not byte-identical), seed-43 same hash over 4 runs (files not byte-identical)

Debug knobs
- `SESSIONS_DEBUG_HASH_BITS=4`: pass
- `SESSIONS_DEBUG_CHUNK=97`: pass
- `SESSIONS_DEBUG_PARTS=1`: pass
- `SESSIONS_DEBUG_PARTS=4096`: pass
- `SESSIONS_DEBUG_NO_FAST=1`: pass
- `SESSIONS_DEBUG_HASH_BITS=0`: pass
- `SESSIONS_DEBUG_PARTS=3`: pass
- `SESSIONS_DEBUG_PARTS=255`: pass
- `SESSIONS_DEBUG_CHUNK=1`: pass
- `SESSIONS_DEBUG_CHUNK=4096`: pass
- `reject SESSIONS_DEBUG_HASH_BITS=bad`: pass
- `reject SESSIONS_DEBUG_CHUNK=bad`: pass
- `reject SESSIONS_DEBUG_PARTS=bad`: pass
- `reject SESSIONS_DEBUG_PARTS=0`: pass
- `reject SESSIONS_DEBUG_PARTS=4097`: pass
- `empty output fixtures with default and one partition`: pass

## Performance (native, NCPU=8)

| Dataset | Runs | Median | Min | p90 | Stdev | MB/s | Mev/s | CPU util | user/sys | Peak footprint | Max RSS (incl. file pages) | Noisy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dev (perf-1M) | 11 | 0.084s | 0.077s | 0.091s | 0.0046 | 1247.9 | 12.8 | 0.43 | 0.15/0.14 | 0.32 GB | 0.43 GB | yes |
| seed-42 (perf-20M) | 5 | 0.545s | 0.532s | 0.550s | 0.0067 | 3826.3 | 39.4 | 0.81 | 2.94/0.54 | 2.10 GB | 4.19 GB | no |
| seed-43 (perf-60M) | 3 | 1.507s | 1.501s | 1.546s | 0.0248 | 4099.1 | 42.6 | 0.87 | 9.27/1.29 | 6.24 GB | 12.41 GB | no |

Phases, dev (median of 11 runs):

| Phase | Wall | Share | CPU | CPU / wall |
| --- | --- | --- | --- | --- |
| lookups | 0.006s | 7% | n/a | n/a |
| events parsed | 0.013s | 16% | n/a | n/a |
| clicks parsed | 0.005s | 6% | n/a | n/a |
| events deduped | 0.001s | 1% | n/a | n/a |
| sessions + attribution | 0.013s | 16% | n/a | n/a |
| written | 0.016s | 19% | n/a | n/a |
| (after last mark: exit/unmap + spawn) | 0.030s | 36% | n/a | n/a |

Resources (median): page reclaims 25429, page faults 0, vol ctx sw 1, invol ctx sw 1857, peak footprint 0.30 GiB
Hardware counters (median): instructions/row 1,805.29, cycles/row 1,176.74, IPC 1.54

Phases, seed-42 (median of 5 runs):

| Phase | Wall | Share | CPU | CPU / wall |
| --- | --- | --- | --- | --- |
| lookups | 0.037s | 7% | n/a | n/a |
| events parsed | 0.236s | 43% | n/a | n/a |
| clicks parsed | 0.050s | 9% | n/a | n/a |
| events deduped | 0.033s | 6% | n/a | n/a |
| sessions + attribution | 0.074s | 14% | n/a | n/a |
| written | 0.038s | 7% | n/a | n/a |
| (after last mark: exit/unmap + spawn) | 0.076s | 14% | n/a | n/a |

Resources (median): page reclaims 254448, page faults 0, vol ctx sw 3, invol ctx sw 4386, peak footprint 1.96 GiB
Hardware counters (median): instructions/row 1,359.31, cycles/row 683.56, IPC 1.99

Phases, seed-43 (median of 3 runs):

| Phase | Wall | Share | CPU | CPU / wall |
| --- | --- | --- | --- | --- |
| lookups | 0.094s | 6% | n/a | n/a |
| events parsed | 0.692s | 46% | n/a | n/a |
| clicks parsed | 0.142s | 9% | n/a | n/a |
| events deduped | 0.142s | 9% | n/a | n/a |
| sessions + attribution | 0.226s | 15% | n/a | n/a |
| written | 0.078s | 5% | n/a | n/a |
| (after last mark: exit/unmap + spawn) | 0.145s | 10% | n/a | n/a |

Resources (median): page reclaims 756409, page faults 4, vol ctx sw 3, invol ctx sw 7987, peak footprint 5.81 GiB
Hardware counters (median): instructions/row 1,328.26, cycles/row 691.39, IPC 1.92

## Per-phase instructions and cycles (untimed probe runs, proc_pid_rusage at each mark)

dev (perf-1M, median of 3): 1,840 instr/row, 1,213 cycles/row, IPC 1.517

| Phase | Instr/row | Share | Cycles/row | IPC |
| --- | ---: | ---: | ---: | ---: |
| lookups | 124.3 | 6.8% | 112.0 | 1.11 |
| events parsed | 771.6 | 41.9% | 353.6 | 2.182 |
| clicks parsed | 150.9 | 8.2% | 71.4 | 2.114 |
| events deduped | 43.6 | 2.4% | 40.9 | 1.065 |
| sessions + attribution | 339.5 | 18.4% | 370.8 | 0.916 |
| written | 398.7 | 21.7% | 241.4 | 1.652 |
| (after last mark: exit/unmap) | 0.0 | 0.0% | 0.0 | None |

Fast-path share (`SESSIONS_DEBUG_STATS=1`): events 100.0% (1,071,465 fast / 429 split_fields), clicks 100.0% (255,021 fast / 126 split_fields), links 99.9% (44,878 fast / 28 split_fields)

seed-42 (perf-20M, median of 3): 1,358 instr/row, 680 cycles/row, IPC 1.999

| Phase | Instr/row | Share | Cycles/row | IPC |
| --- | ---: | ---: | ---: | ---: |
| lookups | 36.5 | 2.7% | 48.5 | 0.754 |
| events parsed | 768.0 | 56.5% | 363.8 | 2.111 |
| clicks parsed | 143.8 | 10.6% | 74.0 | 1.945 |
| events deduped | 35.8 | 2.6% | 46.4 | 0.772 |
| sessions + attribution | 239.5 | 17.6% | 103.6 | 2.312 |
| written | 132.0 | 9.7% | 43.3 | 3.052 |
| (after last mark: exit/unmap) | 0.0 | 0.0% | 0.0 | None |

Fast-path share (`SESSIONS_DEBUG_STATS=1`): events 100.0% (21,496,935 fast / 8,896 split_fields), clicks 100.0% (5,147,457 fast / 2,161 split_fields), links 100.0% (892,343 fast / 363 split_fields)

seed-43 (perf-60M, median of 2): 1,340 instr/row, 731 cycles/row, IPC 1.835

| Phase | Instr/row | Share | Cycles/row | IPC |
| --- | ---: | ---: | ---: | ---: |
| lookups | 34.9 | 2.6% | 45.5 | 0.767 |
| events parsed | 763.0 | 56.9% | 375.3 | 2.033 |
| clicks parsed | 141.7 | 10.6% | 77.7 | 1.824 |
| events deduped | 39.4 | 2.9% | 80.4 | 0.49 |
| sessions + attribution | 241.7 | 18.0% | 117.1 | 2.064 |
| written | 119.8 | 8.9% | 34.7 | 3.451 |
| (after last mark: exit/unmap) | 0.0 | 0.0% | 0.0 | None |

Fast-path share (`SESSIONS_DEBUG_STATS=1`): events 100.0% (64,120,670 fast / 26,764 split_fields), clicks 100.0% (15,239,361 fast / 6,318 split_fields), links 100.0% (2,667,503 fast / 1,093 split_fields)

## Growth per phase, 60M / 20M (event lines ×2.983)

| Phase | Wall 20M | Wall 60M | Wall ratio | Per event | CPU per event | Instr/row ratio | Cycles/row ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lookups | 0.037s | 0.094s | ×2.541 | ×0.852 | n/a | 0.95 | 0.94 |
| events parsed | 0.236s | 0.692s | ×2.932 | ×0.983 | n/a | 0.99 | 1.03 |
| clicks parsed | 0.050s | 0.142s | ×2.84 | ×0.952 | n/a | 0.98 | 1.05 |
| events deduped ⚠ | 0.033s | 0.142s | ×4.303 | ×1.443 | n/a | 1.10 | 1.73 |
| sessions + attribution | 0.074s | 0.226s | ×3.054 | ×1.024 | n/a | 1.01 | 1.13 |
| written | 0.038s | 0.078s | ×2.053 | ×0.688 | n/a | 0.91 | 0.80 |
| (after last mark: exit/unmap + spawn) | 0.076s | 0.145s | ×1.89 | ×0.634 | n/a | n/a | n/a |

⚠ = more than 15% slower per event at 60M. When instructions per row stay flat but cycles per row grow, the phase hit a cache or TLB cliff, not extra work.

## Linux and native 20M timing

| Runtime | Version | Runs | Median | Min | Minor faults / row | Major faults / row |
| --- | --- | --- | --- | --- | --- | --- |
| Linux arm64 | v7b | 11 | 0.434s | 0.425s | 0.000838 | 0.000000 |
| Linux arm64 | v5 | 11 | 0.776s | 0.762s | 0.000830 | 0.000000 |
| Native | v7b | 5 | 0.539s | 0.528s | n/a | n/a |
| Native | v5 | 5 | 0.993s | 0.979s | n/a | n/a |

Named volume, 8 CPUs, 24 GiB cgroup limit, THP madvise, page size 4096 B.

| Linux metric | Candidate median | Baseline median |
| --- | --- | --- |
| Minor faults | 18,019 | 17,856 |
| Major faults | 0 | 0 |
| System CPU (s) | 0.08 | 0.14 |
| Exit tail (s) | 0.007 | 0.016 |
| VM THP allocations | 1,037 | 1,050 |
| VM THP fallbacks | 0 | 0 |
| Peak sampled anonymous (GiB) | 1.943 | 1.982 |
| Peak sampled anonymous huge pages (GiB) | 1.941 | 1.98 |

60M Linux memory check under 22 GiB: 6.06 GiB peak.

## Thread scaling (seed-42)

| NCPU | Median | Speedup | Efficiency | P-core equivalents | Hybrid efficiency |
| --- | --- | --- | --- | --- | --- |
| 1 | 2.695s | 1.0 | 1.0 | 1.0 | 1.0 |
| 2 | 1.432s | 1.881 | 0.941 | 2.0 | 0.941 |
| 4 | 0.810s | 3.325 | 0.831 | 4.0 | 0.831 |
| 5 | 0.698s | 3.858 | 0.772 | 5.0 | 0.772 |
| 8 | 0.545s | 4.942 | 0.618 | 6.4 | 0.772 |

| Phase speedup vs NCPU=1 | 1 | 2 | 4 | 5 | 8 |
| --- | --- | --- | --- | --- | --- |
| lookups | 1.00 | 1.79 | 3.10 | 3.43 | 3.43 |
| events parsed | 1.00 | 1.99 | 3.71 | 4.65 | 6.36 |
| clicks parsed | 1.00 | 1.96 | 3.73 | 4.38 | 6.04 |
| events deduped | 1.00 | 1.84 | 2.89 | 3.24 | 4.12 |
| sessions + attribution | 1.00 | 1.92 | 3.57 | 4.20 | 5.78 |
| written | 1.00 | 1.82 | 3.00 | 3.46 | 3.55 |
| (after last mark: exit/unmap + spawn) | 1.00 | 0.70 | 0.81 | 0.71 | 0.74 |

## Size scaling

- perf-20M/perf-1M: time ×6.523 for events ×20.063
- perf-60M/perf-20M: time ×2.763 for events ×2.983
- perf-60M/perf-1M: time ×18.022 for events ×59.845
- perf-1M: 77.99 ns/event
- perf-20M: 25.36 ns/event
- perf-60M: 23.49 ns/event

## Container overhead (arm64, Docker Desktop)

- dev: container 0.248s vs native 0.084s (+0.164s, ×2.96)

## Cold cache

- unavailable: Unable to purge disk buffers: Operation not permitted

## Constraints and sizes

- threads max 9 (seed-43, NCPU=8); stdout max 0 bytes
- binary 4.88 MB; images arm64 143 MB, amd64 30 MB, amd64-cascadelake 30 MB
- repo tracked 2.61 MB
- native build 17.95s; image arm64 38.7s clean; image amd64 29.6s; image amd64-cascadelake 98.9s clean
- probe on seed-43: sampled RSS max 11.57 GiB

Baseline for Gate C: v5 (reference), 20M median 0.501s

## Notes

- v7b established the 60M consistency baseline in data/consistency/seed-43
