# allocator-system (A) → allocator-jemalloc (B)

## Correctness
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| verdict | HOLD | HOLD |  |  |  |
| sha | 953af436f8 | 13a78473ff |  |  |  |
| profile | linux | linux |  |  |  |
| fixtures_native | 36/36 | 36/36 |  |  |  |
| diff dev | MATCH | MATCH |  |  |  |
| diff seed-15 | MATCH | MATCH |  |  |  |
| diff seed-2 | MATCH | MATCH |  |  |  |
| diff seed-3 | MATCH | MATCH |  |  |  |
| diff seed-4 | MATCH | MATCH |  |  |  |
| diff seed-42 | MATCH | MATCH |  |  |  |
| diff seed-5 | MATCH | MATCH |  |  |  |
| diff seed-6 | MATCH | MATCH |  |  |  |
| diff seed-62 | MATCH | MATCH |  |  |  |
| diff seed-62-20m | MATCH | MATCH |  |  |  |
| fuzz strict | 129/129 | 129/129 |  |  |  |

## seed-42 (perf-20M) — NOISY in ['A']
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| wall median | 1.6560s | 1.5995s | -0.0565s | -3.4% | ~ (t=-1.3) |
| wall min | 1.6122s | 1.5496s | -0.0626s | -3.9% |  |
| wall p90 | 1.8751s | 1.7496s | -0.1255s | -6.7% |  |
| user | 10.2700s | 9.7300s | -0.5400s | -5.3% | better (t=-3.3) |
| sys | 0.8800s | 0.7800s | -0.1000s | -11.4% | ~ (t=-1.2) |
| cpu util | 0.836 | 0.825 | -0.012 | -1.4% | ~ (t=-0.8) |
| peak footprint | 3.81GiB | 4.06GiB | 0.25GiB | +6.5% |  |
| max RSS | 6.03GiB | 5.85GiB | -0.18GiB | -3.0% |  |
| page reclaims | 415,342 | 402,041 | -13,301 | -3.2% | better (t=-27.1) |
| invol ctx sw | 10,931 | 3,706 | -7,225 | -66.1% | ~ (t=-1.5) |
| instructions | 91,887,091,612 | 91,515,803,523 | -371,288,089 | -0.4% | ~ (t=-1.8) |
| instructions/row | 4,272 | 4,255 | -17.3 | -0.4% | ~ (t=-1.8) |
| cycles/row | 2,175 | 2,065 | -110 | -5.1% | ~ (t=-2.4) |
| IPC | 1.964 | 2.062 | 0.097 | +4.9% | ~ (t=2.6) |
| MB/s | 1,157 | 1,198 | 40.9 | +3.5% |  |
| phase: lookups | 0.1030s | 0.1030s | +0.0000s | +0.0% | ~ (t=-0.9) |
| phase: events parsed | 0.7170s | 0.6810s | -0.0360s | -5.0% | ~ (t=-3.1) |
| phase: clicks parsed | 0.1540s | 0.1390s | -0.0150s | -9.7% | ~ (t=-3.7) |
| phase: events deduped | 0.2180s | 0.1770s | -0.0410s | -18.8% | ~ (t=-2.1) |
| phase: sessions + attribution | 0.3110s | 0.2940s | -0.0170s | -5.5% | ~ (t=-1.3) |
| phase: written | 0.0450s | 0.0450s | +0.0000s | +0.0% | ~ (t=-0.2) |
| phase: (after last mark: exit/unmap + spawn) | 0.0988s | 0.1515s | +0.0527s | +53.3% | ~ (t=2.4) |

## Resources and sizes
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| binary size | 3.82MB | 4.12MB | 0.30MB | +8.0% |  |
| image arm64 | 141.92MB | 142.63MB | 0.71MB | +0.5% |  |
| stdout bytes | 0 | 0 | 0 |  |  |

## Linux arm64 (20M)
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| inside-container wall | 1.9711s | 1.5580s | -0.4130s | -21.0% | better (t=-5.7) |
| minor faults / row | 0.038 | 0.001 | -0.037 | -96.3% | better (t=-562.3) |
| major faults / row | 0.000 | 0.000 | 0.000 |  | ~ (t=0.0) |
