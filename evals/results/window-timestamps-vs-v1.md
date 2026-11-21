# v1 (A) → window-timestamps (B)

## Correctness
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| verdict | SUBMIT-READY | HOLD |  |  |  |
| sha | 3e4866243a | d1da46eb91 |  |  |  |
| profile | full | quick |  |  |  |
| fixtures_native | 36/36 | 36/36 |  |  |  |
| fixtures_arm64 | 36/36 | -/- |  |  |  |
| fixtures_amd64 | 36/36 | -/- |  |  |  |
| diff dev | MATCH | MATCH |  |  |  |
| diff seed-15 | MATCH | MATCH |  |  |  |
| diff seed-2 | MATCH | MATCH |  |  |  |
| diff seed-3 | MATCH | MATCH |  |  |  |
| diff seed-4 | MATCH | MATCH |  |  |  |
| diff seed-42 | MATCH | MATCH |  |  |  |
| diff seed-43 | MATCH | MATCH |  |  |  |
| diff seed-5 | MATCH | MATCH |  |  |  |
| diff seed-6 | MATCH | MATCH |  |  |  |
| diff seed-62 | MATCH | MATCH |  |  |  |
| diff seed-62-20m | - | MATCH |  |  |  |
| fuzz strict | 842/842 | 129/129 |  |  |  |

## dev (perf-1M)
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| wall median | 0.1318s | 0.1330s | +0.0012s | +0.9% | ~ (t=0.4) |
| wall min | 0.1296s | 0.1289s | -0.0007s | -0.5% |  |
| wall p90 | 0.1339s | 0.1347s | +0.0008s | +0.6% |  |
| user | 0.3800s | 0.3600s | -0.0200s | -5.3% | better (t=-7.7) |
| sys | 0.1100s | 0.1100s | +0.0000s | +0.0% | ~ (t=1.0) |
| cpu util | 0.465 | 0.450 | -0.015 | -3.2% | ~ (t=-3.1) |
| peak footprint | 0.32GiB | 0.32GiB | 0.00GiB | +0.5% |  |
| max RSS | 0.51GiB | 0.52GiB | 0.00GiB | +0.9% |  |
| page reclaims | 38,412 | 39,125 | 713 | +1.9% | ~ (t=0.6) |
| invol ctx sw | 1,955 | 1,991 | 36 | +1.8% | ~ (t=1.9) |
| instructions | 5,031,531,925 | 4,445,006,698 | -586,525,227 | -11.7% | better (t=-32.2) |
| instructions/row | 4,693 | 4,146 | -547 | -11.7% | better (t=-32.2) |
| cycles/row | 1,983 | 1,902 | -80.3 | -4.1% | better (t=-4.4) |
| IPC | 2.371 | 2.182 | -0.188 | -7.9% | worse (t=-10.5) |
| MB/s | 730 | 723 | -6.6 | -0.9% |  |
| phase: lookups | 0.0060s | 0.0060s | +0.0000s | +0.0% | ~ (t=0.0) |
| phase: events parsed | 0.0260s | 0.0240s | -0.0020s | -7.7% | better (t=-4.5) |
| phase: clicks parsed | 0.0080s | 0.0070s | -0.0010s | -12.5% | ~ (t=-1.4) |
| phase: events deduped | 0.0110s | 0.0120s | +0.0010s | +9.1% | ~ (t=1.8) |
| phase: sessions + attribution | 0.0150s | 0.0150s | +0.0000s | +0.0% | ~ (t=1.4) |
| phase: written | 0.0190s | 0.0190s | +0.0000s | +0.0% | ~ (t=-0.1) |
| phase: (after last mark: exit/unmap + spawn) | 0.0468s | 0.0507s | +0.0039s | +8.3% | ~ (t=1.1) |

## seed-42 (perf-20M)
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| wall median | 1.5499s | 1.5844s | +0.0345s | +2.2% | ~ (t=0.2) |
| wall min | 1.5468s | 1.5032s | -0.0436s | -2.8% |  |
| wall p90 | 1.6087s | 1.6300s | +0.0213s | +1.3% |  |
| user | 9.7700s | 9.6400s | -0.1300s | -1.3% | ~ (t=-0.7) |
| sys | 0.7700s | 0.8300s | +0.0600s | +7.8% | ~ (t=2.4) |
| cpu util | 0.845 | 0.835 | -0.011 | -1.3% | ~ (t=-0.6) |
| peak footprint | 3.81GiB | 3.85GiB | 0.05GiB | +1.3% |  |
| max RSS | 6.02GiB | 6.02GiB | -0.01GiB | -0.1% |  |
| page reclaims | 415,411 | 414,966 | -445 | -0.1% | ~ (t=0.1) |
| invol ctx sw | 3,979 | 11,072 | 7,093 | +178.3% | worse (t=3.3) |
| instructions | 91,809,116,756 | 79,824,286,790 | -11,984,829,966 | -13.1% | better (t=-214.5) |
| instructions/row | 4,269 | 3,711 | -557 | -13.1% | better (t=-214.5) |
| cycles/row | 2,088 | 2,070 | -18 | -0.9% | ~ (t=-0.8) |
| IPC | 2.044 | 1.795 | -0.249 | -12.2% | worse (t=-11.5) |
| MB/s | 1,236 | 1,209 | -26.9 | -2.2% |  |
| phase: lookups | 0.0950s | 0.1030s | +0.0080s | +8.4% | ~ (t=1.8) |
| phase: events parsed | 0.6860s | 0.6720s | -0.0140s | -2.0% | ~ (t=-1.3) |
| phase: clicks parsed | 0.1460s | 0.1400s | -0.0060s | -4.1% | ~ (t=-0.8) |
| phase: events deduped | 0.1960s | 0.2050s | +0.0090s | +4.6% | worse (t=5.4) |
| phase: sessions + attribution | 0.2920s | 0.2920s | +0.0000s | +0.0% | ~ (t=1.0) |
| phase: written | 0.0430s | 0.0540s | +0.0110s | +25.6% | ~ (t=2.0) |
| phase: (after last mark: exit/unmap + spawn) | 0.1098s | 0.1110s | +0.0012s | +1.1% | ~ (t=-1.3) |

## seed-43 (perf-60M)
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| wall median | 5.7928s | 9.5905s | +3.7977s | +65.6% | ~ |
| wall min | 5.7079s | 9.5905s | +3.8826s | +68.0% |  |
| wall p90 | 5.9057s | 9.5905s | +3.6848s | +62.4% |  |
| user | 34.4100s | 35.2700s | +0.8600s | +2.5% | ~ |
| sys | 3.6100s | 8.7700s | +5.1600s | +142.9% | ~ |
| cpu util | 0.820 | 0.574 | -0.246 | -30.0% | ~ |
| peak footprint | 10.74GiB | 10.74GiB | -0.00GiB | -0.0% |  |
| max RSS | 15.49GiB | 15.15GiB | -0.34GiB | -2.2% |  |
| page reclaims | 1,431,187 | 1,370,538 | -60,649 | -4.2% | ~ |
| invol ctx sw | 56,214 | 507,415 | 451,201 | +802.6% | ~ |
| instructions | 283,041,824,902 | 264,962,470,754 | -18,079,354,148 | -6.4% | ~ |
| instructions/row | 4,412 | 4,130 | -282 | -6.4% | ~ |
| cycles/row | 2,514 | 2,866 | 352 | +14.0% | ~ |
| IPC | 1.755 | 1.441 | -0.314 | -17.9% | ~ |
| MB/s | 984 | 594 | -390 | -39.6% |  |
| phase: lookups | 0.3230s | 0.3550s | +0.0320s | +9.9% | ~ |
| phase: events parsed | 2.3740s | 5.1440s | +2.7700s | +116.7% | ~ |
| phase: clicks parsed | 0.5000s | 1.0410s | +0.5410s | +108.2% | ~ |
| phase: events deduped | 1.0280s | 1.5890s | +0.5610s | +54.6% | ~ |
| phase: sessions + attribution | 1.1090s | 1.1240s | +0.0150s | +1.4% | ~ |
| phase: written | 0.1000s | 0.1110s | +0.0110s | +11.0% | ~ |
| phase: (after last mark: exit/unmap + spawn) | 0.3538s | 0.2265s | -0.1273s | -36.0% | ~ |

## Thread scaling (20M)
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| NCPU=1 median | 8.3693s | n/a |  |  |  |
| NCPU=1 efficiency | 1.000 | n/a |  |  |  |
| NCPU=2 median | 4.3101s | n/a |  |  |  |
| NCPU=2 efficiency | 0.971 | n/a |  |  |  |
| NCPU=4 median | 2.4155s | n/a |  |  |  |
| NCPU=4 efficiency | 0.866 | n/a |  |  |  |
| NCPU=8 median | 1.5499s | n/a |  |  |  |
| NCPU=8 efficiency | 0.675 | n/a |  |  |  |

## Resources and sizes
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| binary size | 3.80MB | 3.82MB | 0.02MB | +0.5% |  |
| image amd64 | 120.19MB | n/a |  |  |  |
| image arm64 | 141.91MB | n/a |  |  |  |
| threads max | 9 | 9 | 0 | +0.0% |  |
| stdout bytes | 0 | 0 | 0 |  |  |
| container overhead (dev) | 0.2090s | n/a |  |  |  |
