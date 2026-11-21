# v2 (A) → window-timestamps (B)

## Correctness
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| verdict | HOLD | HOLD |  |  |  |
| sha | 953af436f8 | d1da46eb91 |  |  |  |
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

## dev (perf-1M)
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| wall median | 0.1337s | 0.1330s | -0.0007s | -0.5% | ~ (t=-1.6) |
| wall min | 0.1313s | 0.1289s | -0.0024s | -1.8% |  |
| wall p90 | 0.1348s | 0.1347s | -0.0001s | -0.1% |  |
| user | 0.3700s | 0.3600s | -0.0100s | -2.7% | ~ (t=-3.8) |
| sys | 0.1000s | 0.1100s | +0.0100s | +10.0% | ~ (t=6.0) |
| cpu util | 0.441 | 0.450 | 0.009 | +2.0% | ~ (t=2.0) |
| peak footprint | 0.32GiB | 0.32GiB | 0.01GiB | +2.5% |  |
| max RSS | 0.51GiB | 0.52GiB | 0.01GiB | +1.8% |  |
| page reclaims | 38,199 | 39,125 | 926 | +2.4% | ~ (t=2.7) |
| invol ctx sw | 1,812 | 1,991 | 179 | +9.9% | ~ (t=4.9) |
| instructions | 4,956,124,694 | 4,445,006,698 | -511,117,996 | -10.3% | better (t=-48.1) |
| instructions/row | 4,623 | 4,146 | -477 | -10.3% | better (t=-48.1) |
| cycles/row | 1,902 | 1,902 | 0.0573 | +0.0% | ~ (t=0.4) |
| IPC | 2.434 | 2.182 | -0.251 | -10.3% | worse (t=-18.7) |
| MB/s | 720 | 723 | 3.8 | +0.5% |  |
| phase: lookups | 0.0060s | 0.0060s | +0.0000s | +0.0% | ~ (t=0.0) |
| phase: events parsed | 0.0250s | 0.0240s | -0.0010s | -4.0% | ~ (t=-4.3) |
| phase: clicks parsed | 0.0080s | 0.0070s | -0.0010s | -12.5% | ~ (t=-1.5) |
| phase: events deduped | 0.0100s | 0.0120s | +0.0020s | +20.0% | worse (t=3.1) |
| phase: sessions + attribution | 0.0140s | 0.0150s | +0.0010s | +7.1% | ~ (t=2.6) |
| phase: written | 0.0190s | 0.0190s | +0.0000s | +0.0% | ~ (t=1.6) |
| phase: (after last mark: exit/unmap + spawn) | 0.0513s | 0.0507s | -0.0006s | -1.2% | ~ (t=-2.6) |

## seed-42 (perf-20M) — NOISY in ['A']
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| wall median | 1.6613s | 1.5844s | -0.0769s | -4.6% | ~ (t=-1.9) |
| wall min | 1.6137s | 1.5032s | -0.1105s | -6.8% |  |
| wall p90 | 2.0202s | 1.6300s | -0.3902s | -19.3% |  |
| user | 10.3300s | 9.6400s | -0.6900s | -6.7% | ~ (t=-3.6) |
| sys | 0.8400s | 0.8300s | -0.0100s | -1.2% | ~ (t=-1.1) |
| cpu util | 0.837 | 0.835 | -0.002 | -0.3% | ~ (t=-0.1) |
| peak footprint | 3.80GiB | 3.85GiB | 0.05GiB | +1.4% |  |
| max RSS | 6.02GiB | 6.02GiB | -0.00GiB | -0.1% |  |
| page reclaims | 414,303 | 414,966 | 663 | +0.2% | ~ (t=1.1) |
| invol ctx sw | 9,475 | 11,072 | 1,597 | +16.9% | ~ (t=-0.9) |
| instructions | 91,702,529,516 | 79,824,286,790 | -11,878,242,726 | -13.0% | better (t=-113.3) |
| instructions/row | 4,264 | 3,711 | -552 | -13.0% | better (t=-113.3) |
| cycles/row | 2,190 | 2,070 | -121 | -5.5% | ~ (t=-3.0) |
| IPC | 1.947 | 1.795 | -0.152 | -7.8% | ~ (t=-2.0) |
| MB/s | 1,153 | 1,209 | 56 | +4.9% |  |
| phase: lookups | 0.1050s | 0.1030s | -0.0020s | -1.9% | ~ (t=-0.3) |
| phase: events parsed | 0.7310s | 0.6720s | -0.0590s | -8.1% | ~ (t=-2.7) |
| phase: clicks parsed | 0.1530s | 0.1400s | -0.0130s | -8.5% | ~ (t=-1.6) |
| phase: events deduped | 0.2170s | 0.2050s | -0.0120s | -5.5% | ~ (t=-2.1) |
| phase: sessions + attribution | 0.3020s | 0.2920s | -0.0100s | -3.3% | ~ (t=-1.9) |
| phase: written | 0.0450s | 0.0540s | +0.0090s | +20.0% | ~ (t=1.9) |
| phase: (after last mark: exit/unmap + spawn) | 0.0892s | 0.1110s | +0.0218s | +24.4% | ~ (t=0.2) |

## seed-43 (perf-60M) — NOISY in ['A']
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| wall median | 5.3672s | 9.5905s | +4.2233s | +78.7% | ~ |
| wall min | 5.3469s | 9.5905s | +4.2436s | +79.4% |  |
| wall p90 | 5.3690s | 9.5905s | +4.2215s | +78.6% |  |
| user | 35.2500s | 35.2700s | +0.0200s | +0.1% | ~ |
| sys | 2.3500s | 8.7700s | +6.4200s | +273.2% | ~ |
| cpu util | 0.876 | 0.574 | -0.302 | -34.5% | ~ |
| peak footprint | 10.63GiB | 10.74GiB | 0.11GiB | +1.0% |  |
| max RSS | 16.54GiB | 15.15GiB | -1.39GiB | -8.4% |  |
| page reclaims | 1,131,957 | 1,370,538 | 238,581 | +21.1% | ~ |
| invol ctx sw | 30,232 | 507,415 | 477,183 | +1578.4% | ~ |
| instructions | 278,918,410,944 | 264,962,470,754 | -13,955,940,190 | -5.0% | ~ |
| instructions/row | 4,348 | 4,130 | -218 | -5.0% | ~ |
| cycles/row | 2,468 | 2,866 | 398 | +16.1% | ~ |
| IPC | 1.763 | 1.441 | -0.322 | -18.2% | ~ |
| MB/s | 1,062 | 594 | -468 | -44.0% |  |
| phase: lookups | 0.3520s | 0.3550s | +0.0030s | +0.9% | ~ |
| phase: events parsed | 2.4510s | 5.1440s | +2.6930s | +109.9% | ~ |
| phase: clicks parsed | 0.5180s | 1.0410s | +0.5230s | +101.0% | ~ |
| phase: events deduped | 0.6810s | 1.5890s | +0.9080s | +133.3% | ~ |
| phase: sessions + attribution | 1.0380s | 1.1240s | +0.0860s | +8.3% | ~ |
| phase: written | 0.1080s | 0.1110s | +0.0030s | +2.8% | ~ |
| phase: (after last mark: exit/unmap + spawn) | 0.1940s | 0.2265s | +0.0325s | +16.8% | ~ |

## Thread scaling (20M)
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| NCPU=1 median | 9.3077s | n/a |  |  |  |
| NCPU=1 efficiency | 1.000 | n/a |  |  |  |
| NCPU=1 hybrid efficiency | 1.000 | n/a |  |  |  |
| NCPU=2 median | 4.6653s | n/a |  |  |  |
| NCPU=2 efficiency | 0.998 | n/a |  |  |  |
| NCPU=2 hybrid efficiency | 0.998 | n/a |  |  |  |
| NCPU=4 median | 2.5756s | n/a |  |  |  |
| NCPU=4 efficiency | 0.903 | n/a |  |  |  |
| NCPU=4 hybrid efficiency | 0.903 | n/a |  |  |  |
| NCPU=5 median | 2.1456s | n/a |  |  |  |
| NCPU=5 efficiency | 0.868 | n/a |  |  |  |
| NCPU=5 hybrid efficiency | 0.868 | n/a |  |  |  |
| NCPU=8 median | 1.6613s | n/a |  |  |  |
| NCPU=8 efficiency | 0.700 | n/a |  |  |  |
| NCPU=8 hybrid efficiency | 0.875 | n/a |  |  |  |

## Resources and sizes
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| binary size | 3.82MB | 3.82MB | 0.00MB | +0.0% |  |
| image amd64 | 29.72MB | n/a |  |  |  |
| image arm64 | 141.92MB | n/a |  |  |  |
| threads max | 9 | 9 | 0 | +0.0% |  |
| stdout bytes | 0 | 0 | 0 |  |  |
| container overhead (dev) | 0.2060s | n/a |  |  |  |
