# v3 (A) → parallel-links (B)

## Correctness
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| verdict | SUBMIT-READY | HOLD |  |  |  |
| sha | 29b64bfce1 | 89ad72cab9 |  |  |  |
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
| diff seed-62-20m | MATCH | MATCH |  |  |  |
| fuzz strict | 854/854 | 129/129 |  |  |  |

## dev (perf-1M) — NOISY in ['B']
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| wall median | 0.0790s | 0.0802s | +0.0012s | +1.5% | ~ (t=1.2) |
| wall min | 0.0774s | 0.0760s | -0.0014s | -1.8% |  |
| wall p90 | 0.0794s | 0.0818s | +0.0024s | +3.0% |  |
| user | 0.1900s | 0.1900s | +0.0000s | +0.0% | ~ (t=1.5) |
| sys | 0.1100s | 0.1200s | +0.0100s | +9.1% | ~ (t=2.7) |
| cpu util | 0.484 | 0.481 | -0.003 | -0.7% | ~ (t=-0.3) |
| peak footprint | 0.30GiB | 0.31GiB | 0.01GiB | +3.1% |  |
| max RSS | 0.39GiB | 0.40GiB | 0.01GiB | +2.3% |  |
| page reclaims | 25,184 | 25,813 | 629 | +2.5% | ~ (t=2.6) |
| invol ctx sw | 1,808 | 2,013 | 205 | +11.3% | ~ (t=2.3) |
| instructions | 3,149,782,822 | 3,168,668,401 | 18,885,579 | +0.6% | ~ (t=1.9) |
| instructions/row | 2,938 | 2,956 | 17.6 | +0.6% | ~ (t=1.9) |
| cycles/row | 1,215 | 1,281 | 66.1 | +5.4% | ~ (t=4.2) |
| IPC | 2.420 | 2.313 | -0.107 | -4.4% | ~ (t=-4.5) |
| MB/s | 1,218 | 1,200 | -18.3 | -1.5% |  |
| phase: lookups | 0.0060s | 0.0050s | -0.0010s | -16.7% | ~ (t=-0.4) |
| phase: events parsed | 0.0170s | 0.0170s | +0.0000s | +0.0% | ~ (t=0.3) |
| phase: clicks parsed | 0.0050s | 0.0050s | +0.0000s | +0.0% | ~ (t=-0.4) |
| phase: events deduped | 0.0010s | 0.0010s | +0.0000s | +0.0% | ~ (t=0.0) |
| phase: sessions + attribution | 0.0110s | 0.0120s | +0.0010s | +9.1% | ~ (t=3.1) |
| phase: written | 0.0140s | 0.0200s | +0.0060s | +42.9% | worse (t=4.8) |
| phase: (after last mark: exit/unmap + spawn) | 0.0240s | 0.0197s | -0.0043s | -17.9% | ~ (t=-0.1) |

## seed-42 (perf-20M) — NOISY in ['A']
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| wall median | 0.6238s | 0.6756s | +0.0518s | +8.3% | ~ (t=1.6) |
| wall min | 0.6129s | 0.6188s | +0.0059s | +1.0% |  |
| wall p90 | 0.6694s | 0.6800s | +0.0106s | +1.6% |  |
| user | 3.7200s | 3.8300s | +0.1100s | +3.0% | ~ (t=2.6) |
| sys | 0.4300s | 0.5200s | +0.0900s | +20.9% | worse (t=5.1) |
| cpu util | 0.816 | 0.811 | -0.005 | -0.6% | ~ (t=0.1) |
| peak footprint | 1.92GiB | 1.93GiB | 0.01GiB | +0.6% |  |
| max RSS | 3.71GiB | 3.72GiB | 0.01GiB | +0.3% |  |
| page reclaims | 242,234 | 242,699 | 465 | +0.2% | ~ (t=0.4) |
| invol ctx sw | 3,350 | 7,607 | 4,257 | +127.1% | ~ (t=2.7) |
| instructions | 55,885,597,710 | 55,238,101,404 | -647,496,306 | -1.2% | better (t=-14.9) |
| instructions/row | 2,598 | 2,568 | -30.1 | -1.2% | better (t=-14.9) |
| cycles/row | 820 | 843 | 22.9 | +2.8% | ~ (t=2.1) |
| IPC | 3.171 | 3.047 | -0.123 | -3.9% | worse (t=-3.4) |
| MB/s | 3,071 | 2,835 | -236 | -7.7% |  |
| phase: lookups | 0.0540s | 0.0250s | -0.0290s | -53.7% | better (t=-42.7) |
| phase: events parsed | 0.2910s | 0.3090s | +0.0180s | +6.2% | worse (t=3.2) |
| phase: clicks parsed | 0.0470s | 0.0500s | +0.0030s | +6.4% | ~ (t=1.9) |
| phase: events deduped | 0.0330s | 0.0340s | +0.0010s | +3.0% | ~ (t=-0.1) |
| phase: sessions + attribution | 0.1100s | 0.1190s | +0.0090s | +8.2% | worse (t=4.1) |
| phase: written | 0.0360s | 0.0360s | +0.0000s | +0.0% | ~ (t=0.1) |
| phase: (after last mark: exit/unmap + spawn) | 0.0598s | 0.0953s | +0.0355s | +59.4% | ~ (t=2.4) |

## seed-43 (perf-60M) — NOISY in ['A']
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| wall median | 1.9704s | 5.9546s | +3.9842s | +202.2% | ~ |
| wall min | 1.9322s | 5.9546s | +4.0224s | +208.2% |  |
| wall p90 | 2.0752s | 5.9546s | +3.8794s | +186.9% |  |
| user | 11.9100s | 12.3700s | +0.4600s | +3.9% | ~ |
| sys | 1.2900s | 5.1100s | +3.8200s | +296.1% | ~ |
| cpu util | 0.834 | 0.367 | -0.467 | -56.0% | ~ |
| peak footprint | 5.24GiB | 5.58GiB | 0.34GiB | +6.5% |  |
| max RSS | 10.81GiB | 10.62GiB | -0.19GiB | -1.7% |  |
| page reclaims | 706,904 | 465,811 | -241,093 | -34.1% | ~ |
| invol ctx sw | 10,799 | 354,383 | 343,584 | +3181.6% | ~ |
| instructions | 167,574,315,546 | 179,793,736,519 | 12,219,420,973 | +7.3% | ~ |
| instructions/row | 2,612 | 2,803 | 190 | +7.3% | ~ |
| cycles/row | 866 | 1,120 | 254 | +29.4% | ~ |
| IPC | 3.017 | 2.502 | -0.515 | -17.1% | ~ |
| MB/s | 2,893 | 957 | -1,936 | -66.9% |  |
| phase: lookups | 0.2160s | 0.0960s | -0.1200s | -55.6% | ~ |
| phase: events parsed | 0.8610s | 3.9530s | +3.0920s | +359.1% | ~ |
| phase: clicks parsed | 0.1360s | 0.8620s | +0.7260s | +533.8% | ~ |
| phase: events deduped | 0.1370s | 0.2340s | +0.0970s | +70.8% | ~ |
| phase: sessions + attribution | 0.3940s | 0.5060s | +0.1120s | +28.4% | ~ |
| phase: written | 0.0780s | 0.0770s | -0.0010s | -1.3% | ~ |
| phase: (after last mark: exit/unmap + spawn) | 0.1584s | 0.2266s | +0.0682s | +43.1% | ~ |

## Thread scaling (20M)
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| NCPU=1 median | 3.4989s | n/a |  |  |  |
| NCPU=1 efficiency | 1.000 | n/a |  |  |  |
| NCPU=1 hybrid efficiency | 1.000 | n/a |  |  |  |
| NCPU=2 median | 1.9058s | n/a |  |  |  |
| NCPU=2 efficiency | 0.918 | n/a |  |  |  |
| NCPU=2 hybrid efficiency | 0.918 | n/a |  |  |  |
| NCPU=4 median | 1.0026s | n/a |  |  |  |
| NCPU=4 efficiency | 0.872 | n/a |  |  |  |
| NCPU=4 hybrid efficiency | 0.872 | n/a |  |  |  |
| NCPU=5 median | 0.8830s | n/a |  |  |  |
| NCPU=5 efficiency | 0.793 | n/a |  |  |  |
| NCPU=5 hybrid efficiency | 0.793 | n/a |  |  |  |
| NCPU=8 median | 0.6238s | n/a |  |  |  |
| NCPU=8 efficiency | 0.701 | n/a |  |  |  |
| NCPU=8 hybrid efficiency | 0.876 | n/a |  |  |  |

## Resources and sizes
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| binary size | 3.98MB | 4.00MB | 0.02MB | +0.6% |  |
| image amd64 | 29.80MB | n/a |  |  |  |
| image amd64-cascadelake | 29.87MB | n/a |  |  |  |
| image arm64 | 142.26MB | n/a |  |  |  |
| threads max | 9 | 9 | 0 | +0.0% |  |
| stdout bytes | 0 | 0 | 0 |  |  |
| container overhead (dev) | 0.1650s | n/a |  |  |  |
