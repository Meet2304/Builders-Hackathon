# Benchmarks

Local machine: Apple M-series, run natively with `NCPU=8`. Local times don't match the scorer's; the board's times are the ones that count.
Datasets come from the organizers' generator.
- `dev`: seed 1, 1M events, 92 MB
- `seed-42`: 20M events, 1.8 GB
- `seed-43`: 60M events, 5.4 GB

| Date | Commit | What | dev 1M | 20M | 60M | Peak mem (60M) | Board |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-21 | (ref) | Python reference, 1 thread | 8.8 s | 236 s | n/a | 17 GB at 20M | n/a |
| 2026-11-21 | v1 | Rust v1: parallel parse, hash-bucket dedup, per-person sliding window | 0.17 s | 1.72 s | 9.6–11.1 s | 11.5 GB | not submitted |

## v1 phase breakdown (60M)
| Phase | Time |
| --- | --- |
| lookups + links (3.6M linked IDs) | 0.4 s |
| events parse | 2.9 s |
| clicks parse | 0.7–1.2 s |
| **events dedup** | **2.8–4.2 s** (biggest target) |
| sessions + attribution | 1.7–2.0 s |
| write | 0.14 s |

## Correctness for v1
- 36/36 fixtures pass natively, in the arm64 container and in the amd64 container (emulated, `X86_CPU=x86-64-v2`).
- The dev set MATCHes the published answer natively and in both containers.
- Rust and the reference MATCH on seeds 2, 3, 4, 5 and 6 (200k events each), on seeds 15 and 62 (300k events, windows that include Feb 29 2028), and on seed 42 (20M events).
