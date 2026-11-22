# allocator-system (A) → allocator-mimalloc (B)

## Correctness
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| verdict | HOLD | HOLD |  |  |  |
| sha | 953af436f8 | 3cf92b0336 |  |  |  |
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

## seed-42 (perf-20M) — NOISY in ['A', 'B']
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| wall median | 1.6560s | 1.6012s | -0.0548s | -3.3% | ~ (t=-0.4) |
| wall min | 1.6122s | 1.5522s | -0.0600s | -3.7% |  |
| wall p90 | 1.8751s | 1.8950s | +0.0199s | +1.1% |  |
| user | 10.2700s | 10.0800s | -0.1900s | -1.9% | ~ (t=-0.2) |
| sys | 0.8800s | 0.9000s | +0.0200s | +2.3% | ~ (t=0.0) |
| cpu util | 0.836 | 0.852 | 0.015 | +1.8% | ~ (t=1.0) |
| peak footprint | 3.81GiB | 3.71GiB | -0.10GiB | -2.7% |  |
| max RSS | 6.03GiB | 5.50GiB | -0.53GiB | -8.8% |  |
| page reclaims | 415,342 | 360,225 | -55,117 | -13.3% | better (t=-135.0) |
| invol ctx sw | 10,931 | 8,817 | -2,114 | -19.3% | ~ (t=-0.4) |
| instructions | 91,887,091,612 | 90,732,068,843 | -1,155,022,769 | -1.3% | better (t=-7.4) |
| instructions/row | 4,272 | 4,219 | -53.7 | -1.3% | better (t=-7.4) |
| cycles/row | 2,175 | 2,143 | -31.6 | -1.5% | ~ (t=-0.2) |
| IPC | 1.964 | 1.968 | 0.004 | +0.2% | ~ (t=-0.2) |
| MB/s | 1,157 | 1,196 | 39.6 | +3.4% |  |
| phase: lookups | 0.1030s | 0.1060s | +0.0030s | +2.9% | ~ (t=0.7) |
| phase: events parsed | 0.7170s | 0.6930s | -0.0240s | -3.3% | ~ (t=-0.2) |
| phase: clicks parsed | 0.1540s | 0.1440s | -0.0100s | -6.5% | ~ (t=-0.8) |
| phase: events deduped | 0.2180s | 0.2070s | -0.0110s | -5.0% | ~ (t=-1.6) |
| phase: sessions + attribution | 0.3110s | 0.3060s | -0.0050s | -1.6% | ~ (t=-0.2) |
| phase: written | 0.0450s | 0.0420s | -0.0030s | -6.7% | ~ (t=-2.3) |
| phase: (after last mark: exit/unmap + spawn) | 0.0988s | 0.1096s | +0.0108s | +10.9% | ~ (t=-0.3) |

## Resources and sizes
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| binary size | 3.82MB | 3.95MB | 0.13MB | +3.4% |  |
| image arm64 | 141.92MB | 142.22MB | 0.30MB | +0.2% |  |
| stdout bytes | 0 | 0 | 0 |  |  |

## Linux arm64 (20M)
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| inside-container wall | 1.9711s | 1.5528s | -0.4182s | -21.2% | better (t=-7.2) |
| minor faults / row | 0.038 | 0.001 | -0.037 | -97.4% | better (t=-804.8) |
| major faults / row | 0.000 | 0.000 | 0.000 |  | ~ (t=0.0) |
