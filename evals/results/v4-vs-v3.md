# v3 (A) → v4 (B)

## Headline
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| predicted board 20M (instructions, primary) | 1.9424s | 1.1750s | -0.7674s | -39.5% |  |
| predicted board 20M (wall ratio) | 1.9356s | 1.4183s | -0.5172s | -26.7% |  |
| instructions/row 20M | 2,598 | 1,572 | -1,027 | -39.5% | better (t=-661.9) |
| cycles/row 20M | 820 | 592 | -228 | -27.8% | better (t=-28.1) |
| IPC 20M (M5) | 3.171 | 2.656 | -0.514 | -16.2% | worse (t=-16.7) |

## Same-session timing (B's eval re-timed v3 interleaved)
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| native 20M, interleaved A/B | 0.6177s | 0.4530s | -0.1647s | -26.7% | better (t=-18.1) |
| Linux arm64 20M, interleaved A/B | 0.5416s | 0.3827s | -0.1588s | -29.3% | better (t=-76.5) |
| Linux minor faults | 16,303 | 16,461 | +158 | +1.0% | ~ (t=14.8) |

## Per-phase counters, 20M (untimed probes)
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| lookups instr/row | 69.1 | 29.9 | -39.2 | -56.8% |  |
| lookups cycles/row | 30.8 | 27.4 | -3.33 | -10.8% |  |
| events parsed instr/row | 1,600 | 868 | -731 | -45.7% |  |
| events parsed cycles/row | 464 | 290 | -173 | -37.4% |  |
| clicks parsed instr/row | 241 | 175 | -65.2 | -27.1% |  |
| clicks parsed cycles/row | 68.6 | 56 | -12.6 | -18.4% |  |
| events deduped instr/row | 35.4 | 36 | +0.56 | +1.6% |  |
| events deduped cycles/row | 46.1 | 45.7 | -0.47 | -1.0% |  |
| sessions + attribution instr/row | 522 | 326 | -196 | -37.6% |  |
| sessions + attribution cycles/row | 172 | 123 | -48.2 | -28.1% |  |
| written instr/row | 130 | 129 | -1.2 | -0.9% |  |
| written cycles/row | 41 | 39.8 | -1.16 | -2.8% |  |
| (after last mark: exit/unmap) instr/row | 2.42 | 7.09 | +4.67 | +193.0% |  |
| (after last mark: exit/unmap) cycles/row | 0.97 | 2.17 | +1.2 | +123.7% |  |
| fast-path share clicks | n/a | 1.000 |  |  |  |
| fast-path share events | n/a | 1.000 |  |  |  |
| fast-path share links | n/a | 1.000 |  |  |  |

## Correctness
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| verdict | SUBMIT-READY | SUBMIT-READY |  |  |  |
| sha | 29b64bfce1 | a0197396f5 |  |  |  |
| profile | full | full |  |  |  |
| fixtures_native | 36/36 | 36/36 |  |  |  |
| fixtures_arm64 | 36/36 | 36/36 |  |  |  |
| fixtures_amd64 | 36/36 | 36/36 |  |  |  |
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
| fuzz strict | 854/854 | 854/854 |  |  |  |

## dev (perf-1M) — NOISY in ['B']
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| wall median | 0.0790s | 0.0788s | -0.0002s | -0.3% | ~ (t=-1.1) |
| wall min | 0.0774s | 0.0709s | -0.0065s | -8.4% |  |
| wall p90 | 0.0794s | 0.0790s | -0.0004s | -0.5% |  |
| user | 0.1900s | 0.1400s | -0.0500s | -26.3% | better (t=-42.5) |
| cpu util | 0.484 | 0.411 | -0.073 | -15.0% | better (t=-8.6) |
| peak footprint | 0.30GiB | 0.28GiB | -0.02GiB | -6.4% |  |
| max RSS | 0.39GiB | 0.37GiB | -0.02GiB | -4.8% |  |
| page reclaims | 25,184 | 23,700 | -1,484 | -5.9% | better (t=-6.4) |
| invol ctx sw | 1,808 | 1,174 | -634 | -35.1% | ~ (t=-2.0) |
| instructions | 3,149,782,822 | 2,164,619,549 | -985,163,273 | -31.3% | better (t=-137.5) |
| instructions/row | 2,938 | 2,019 | -919 | -31.3% | better (t=-137.5) |
| sys CPU | 0.1100s | 0.1100s | +0.0000s | +0.0% | ~ (t=0.5) |
| minor faults (page reclaims) | 25,184 | 23,700 | -1,484 | -5.9% | better (t=-6.4) |
| cycles/row | 1,215 | 1,016 | -199 | -16.4% | better (t=-13.0) |
| IPC | 2.420 | 1.987 | -0.433 | -17.9% | worse (t=-16.9) |
| MB/s | 1,218 | 1,221 | +3 | +0.2% |  |
| phase: lookups | 0.0060s | 0.0050s | -0.0010s | -16.7% | better (t=-3.1) |
| phase: events parsed | 0.0170s | 0.0110s | -0.0060s | -35.3% | better (t=-21.5) |
| phase: clicks parsed | 0.0050s | 0.0040s | -0.0010s | -20.0% | better (t=-4.9) |
| phase: events deduped | 0.0010s | 0.0010s | +0.0000s | +0.0% | ~ (t=-0.4) |
| phase: sessions + attribution | 0.0110s | 0.0110s | +0.0000s | +0.0% | ~ (t=-0.6) |
| phase: written | 0.0140s | 0.0140s | +0.0000s | +0.0% | ~ (t=-0.6) |
| phase: (after last mark: exit/unmap + spawn) | 0.0240s | 0.0320s | +0.0080s | +33.3% | worse (t=6.0) |

## seed-42 (perf-20M) — NOISY in ['A', 'B']
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| wall median | 0.6238s | 0.4571s | -0.1667s | -26.7% | better (t=-13.3) |
| wall min | 0.6129s | 0.4513s | -0.1616s | -26.4% |  |
| wall p90 | 0.6694s | 0.4989s | -0.1705s | -25.5% |  |
| user | 3.7200s | 2.6000s | -1.1200s | -30.1% | better (t=-39.9) |
| cpu util | 0.816 | 0.831 | +0.015 | +1.9% | ~ (t=0.1) |
| peak footprint | 1.92GiB | 1.81GiB | -0.11GiB | -5.7% |  |
| max RSS | 3.71GiB | 3.60GiB | -0.11GiB | -3.0% |  |
| page reclaims | 242,234 | 234,317 | -7,917 | -3.3% | better (t=-18.5) |
| invol ctx sw | 3,350 | 3,057 | -293 | -8.7% | ~ (t=-1.4) |
| instructions | 55,885,597,710 | 33,807,223,576 | -22,078,374,134 | -39.5% | better (t=-661.9) |
| instructions/row | 2,598 | 1,572 | -1,027 | -39.5% | better (t=-661.9) |
| sys CPU | 0.4300s | 0.4400s | +0.0100s | +2.3% | ~ (t=0.6) |
| minor faults (page reclaims) | 242,234 | 234,317 | -7,917 | -3.3% | better (t=-18.5) |
| cycles/row | 820 | 592 | -228 | -27.8% | better (t=-28.1) |
| IPC | 3.171 | 2.656 | -0.514 | -16.2% | worse (t=-16.7) |
| MB/s | 3,071 | 4,191 | +1,120 | +36.5% |  |
| phase: lookups | 0.0540s | 0.0220s | -0.0320s | -59.3% | better (t=-58.6) |
| phase: events parsed | 0.2910s | 0.1920s | -0.0990s | -34.0% | better (t=-29.0) |
| phase: clicks parsed | 0.0470s | 0.0390s | -0.0080s | -17.0% | better (t=-7.4) |
| phase: events deduped | 0.0330s | 0.0340s | +0.0010s | +3.0% | ~ (t=-0.1) |
| phase: sessions + attribution | 0.1100s | 0.0850s | -0.0250s | -22.7% | better (t=-16.4) |
| phase: written | 0.0360s | 0.0320s | -0.0040s | -11.1% | better (t=-3.4) |
| phase: (after last mark: exit/unmap + spawn) | 0.0598s | 0.0532s | -0.0066s | -11.0% | ~ (t=-0.2) |

## seed-43 (perf-60M) — NOISY in ['A']
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| wall median | 1.9704s | 1.3202s | -0.6502s | -33.0% | better (t=-14.6) |
| wall min | 1.9322s | 1.3130s | -0.6192s | -32.0% |  |
| wall p90 | 2.0752s | 1.3608s | -0.7144s | -34.4% |  |
| user | 11.9100s | 8.2100s | -3.7000s | -31.1% | better (t=-27.1) |
| cpu util | 0.834 | 0.875 | +0.041 | +5.0% | worse (t=4.0) |
| peak footprint | 5.24GiB | 4.71GiB | -0.53GiB | -10.1% |  |
| max RSS | 10.81GiB | 10.25GiB | -0.56GiB | -5.2% |  |
| page reclaims | 706,904 | 668,240 | -38,664 | -5.5% | better (t=-11.2) |
| invol ctx sw | 10,799 | 3,872 | -6,927 | -64.1% | better (t=-3.5) |
| instructions | 167,574,315,546 | 99,276,811,025 | -68,297,504,521 | -40.8% | better (t=-513.6) |
| instructions/row | 2,612 | 1,548 | -1,065 | -40.8% | better (t=-513.6) |
| sys CPU | 1.2900s | 1.1400s | -0.1500s | -11.6% | ~ (t=-2.9) |
| minor faults (page reclaims) | 706,904 | 668,240 | -38,664 | -5.5% | better (t=-11.2) |
| cycles/row | 866 | 596 | -270 | -31.2% | better (t=-24.2) |
| IPC | 3.017 | 2.597 | -0.419 | -13.9% | worse (t=-10.5) |
| MB/s | 2,893 | 4,318 | +1,425 | +49.3% |  |
| phase: lookups | 0.2160s | 0.0630s | -0.1530s | -70.8% | better (t=-19.4) |
| phase: events parsed | 0.8610s | 0.5620s | -0.2990s | -34.7% | better (t=-26.3) |
| phase: clicks parsed | 0.1360s | 0.1120s | -0.0240s | -17.6% | better (t=-6.1) |
| phase: events deduped | 0.1370s | 0.1440s | +0.0070s | +5.1% | ~ (t=0.0) |
| phase: sessions + attribution | 0.3940s | 0.2660s | -0.1280s | -32.5% | better (t=-17.0) |
| phase: written | 0.0780s | 0.0690s | -0.0090s | -11.5% | better (t=-3.1) |
| phase: (after last mark: exit/unmap + spawn) | 0.1584s | 0.1192s | -0.0392s | -24.7% | ~ (t=-2.6) |

## Thread scaling (20M)
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| NCPU=1 median | 3.4989s | 2.3189s | -1.1800s | -33.7% |  |
| NCPU=1 efficiency | 1.000 | 1.000 | 0.000 | +0.0% |  |
| NCPU=1 hybrid efficiency | 1.000 | 1.000 | 0.000 | +0.0% |  |
| NCPU=2 median | 1.9058s | 1.2308s | -0.6750s | -35.4% |  |
| NCPU=2 efficiency | 0.918 | 0.942 | +0.024 | +2.6% |  |
| NCPU=2 hybrid efficiency | 0.918 | 0.942 | +0.024 | +2.6% |  |
| NCPU=4 median | 1.0026s | 0.7398s | -0.2628s | -26.2% |  |
| NCPU=4 efficiency | 0.872 | 0.784 | -0.088 | -10.1% |  |
| NCPU=4 hybrid efficiency | 0.872 | 0.784 | -0.088 | -10.1% |  |
| NCPU=5 median | 0.8830s | 0.6099s | -0.2731s | -30.9% |  |
| NCPU=5 efficiency | 0.793 | 0.760 | -0.033 | -4.2% |  |
| NCPU=5 hybrid efficiency | 0.793 | 0.760 | -0.033 | -4.2% |  |
| NCPU=8 median | 0.6238s | 0.4571s | -0.1667s | -26.7% |  |
| NCPU=8 efficiency | 0.701 | 0.634 | -0.067 | -9.6% |  |
| NCPU=8 hybrid efficiency | 0.876 | 0.793 | -0.083 | -9.5% |  |

## Resources and sizes
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| binary size | 3.98MB | 4.05MB | +0.07MB | +1.9% |  |
| image amd64 | 29.80MB | 29.82MB | +0.01MB | +0.0% |  |
| image amd64-cascadelake | 29.87MB | 29.88MB | +0.01MB | +0.0% |  |
| image arm64 | 142.26MB | 142.36MB | +0.10MB | +0.1% |  |
| threads max | 9 | 9 | 0 | +0.0% |  |
| stdout bytes | 0 | 0 | 0 |  |  |
| container overhead (dev) | 0.1650s | 0.1680s | +0.0030s | +1.8% |  |
| predicted board 20M (instructions, primary) | 1.9424s | 1.1750s | -0.7674s | -39.5% |  |
| predicted board 20M (local wall) | 1.9356s | 1.4183s | -0.5172s | -26.7% |  |

## Linux arm64 (20M)
| Metric | A | B | Δ | Δ% | significance |
| --- | --- | --- | --- | --- | --- |
| inside-container wall | 0.5503s | 0.3827s | -0.1676s | -30.5% | better (t=-42.7) |
| sys CPU | 0.1200s | 0.0600s | -0.0600s | -50.0% | better (t=-4.0) |
| minor faults | 16,312 | 16,461 | +149 | +0.9% | ~ (t=11.1) |
| exit tail | 0.0107s | 0.0143s | +0.0036s | +33.6% | worse (t=7.2) |
| peak sampled anonymous | 1.94GiB | 1.82GiB | -0.12GiB | -6.2% | better (t=-11.9) |
| peak sampled anonymous huge pages | 1.94GiB | 1.82GiB | -0.12GiB | -6.2% | better (t=-12.0) |
| THP allocations (VM) | 1,001 | 933 | -68 | -6.8% | better (t=-19.0) |
| THP fallbacks (VM) | 0 | 0 | 0 |  | ~ (t=0.0) |
| minor faults / row | 0.001 | 0.001 | +0.000 | +0.9% | ~ (t=13.0) |
| major faults / row | 0.000 | 0.000 | 0.000 |  | ~ (t=0.0) |
