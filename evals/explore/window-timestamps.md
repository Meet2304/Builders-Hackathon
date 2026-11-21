# Window-local timestamp decoding

Prototype `explore/window-timestamps` at `d1da46e`, based on v2 `953af43`.

## Hypothesis and change

The full v2 eval spent 0.731 s (44%) parsing events and 0.153 s parsing clicks at 20M. Parquet took 0.045 s (3%). The parser decodes up to two timestamps per event, and the input window lets most rows reuse the same small set of Gregorian dates.

Build an 8 KiB date table from the manifest once. F1 and F2 check the complete date against the table and decode the clock byte lanes in parallel. F2 still validates and applies the signed offset. The 13-digit F3 fast path validates and reduces digits in parallel. The scalar parser handles calendar misses and other F3 lengths, including long numbers and leading zeros. Dedup still sees the exact ingest timestamp before event validation. `SESSIONS_DEBUG_NO_FAST=1` uses the scalar parser throughout.

## Correctness

`make fixtures-local` passed 36/36, and `make run-dev-local check-dev` matched the published answer. Eval quick matched all 10 oracles, including the 20M leap-day dataset, and all 150 fuzz seeds (129 strict, 21 robust) under defaults and each of the five debug settings. Seed-43 matched v1 at 60M and passed the invariants. A standalone differential check matched on 163,659 cases, including calendar boundary dates and all byte values substituted at individual positions in F1, F2 and F3. Quick profile leaves container checks outstanding.

## Results

Quiet 20M comparison on the M5 Pro, NCPU=8. The harness used Eval's `run_once` and `summarize_runs`, with one warm-up per version and all six execution orders of v1, v2 and the prototype. The host was 3.5% busy before the block.

| Metric, median | v1 | v2 | Prototype | Δ vs v2 |
| --- | ---: | ---: | ---: | ---: |
| Wall time (s) | 1.6058 | 1.5983 | 1.5015 | −6.1% |
| Wall SD (s) | 0.0094 | 0.0381 | 0.0248 | |
| User CPU (s) | 9.985 | 9.975 | 9.435 | −5.4% |
| System CPU (s) | 0.815 | 0.800 | 0.785 | −1.9% |
| Instructions per input event line | 4,270 | 4,264 | 3,711 | −13.0% |
| Cycles per input event line | 2,113 | 2,105 | 2,000 | −5.0% |
| IPC | 2.02 | 2.03 | 1.86 | |
| Peak footprint (GB) | 4.079 | 4.089 | 4.074 | |

The prototype beat both baselines in all six rounds. The median difference within rounds was 90.7 ms versus v2. The overall median fell 6.5% against v1. Both wall-time comparisons meet Eval's significance rule (Welch \(|t|\) 4.55 vs v2 and 9.07 vs v1).

| Phase, median (s) | v1 wall | v2 wall | Prototype wall | v2 CPU | Prototype CPU |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lookups | 0.095 | 0.097 | 0.098 | 0.116 | 0.117 |
| Events parsed | 0.698 | 0.706 | 0.641 | 5.528 | 5.026 |
| Clicks parsed | 0.147 | 0.146 | 0.140 | 1.085 | 1.046 |
| Events deduped | 0.207 | 0.210 | 0.209 | 1.473 | 1.466 |
| Sessions and attribution | 0.292 | 0.296 | 0.285 | 2.260 | 2.249 |
| Parquet phase | 0.045 | 0.043 | 0.044 | 0.275 | 0.276 |
| Exit, unmap and spawn | 0.116 | 0.089 | 0.079 | — | — |

The standalone quick profile measured 0.133 s at 1M (11 runs), 1.584 s at 20M (5 runs) and 9.591 s at 60M (one run without warm-up). The 60M sample had 347,988 major page faults and 8.77 s system CPU, so treat it as a fault-heavy correctness run. The first interleaved 20M block began at 13.5% host CPU busy with a concurrent Rust build. In that block the prototype was 2.4% faster than v2 by median with a nonsignificant wall delta. Instruction savings were 13.0% in both blocks.

- [Quick eval](../results/window-timestamps.md) and [result JSON](../results/window-timestamps.json)
- [Both interleaved blocks, raw samples and summaries](../results/window-timestamps-ab.json)
- Framework comparisons against historical [v2](../results/window-timestamps-vs-v2.md) and [v1](../results/window-timestamps-vs-v1.md)

## Verdict and v3 port

Port as a follow-up to the v3 parser and measure the incremental gain on its branch. The quiet result saves about 0.10 s at 20M and 0.50 core-s during event parsing. The trial does not measure the calendar and F3 changes independently, and the quick profile has no amd64 or Linux timing.

Copy the self-contained `TimestampDecoder` and its parsing helpers from `d1da46e`. Build it from the manifest bounds and pass it to the event payload, ingest and click timestamp call sites in v3. Keep the general decoder for manifest timestamps and cache misses. Keep v3's existing offset conversions after decode and wire the fast-path debug switch through the decoder. Compare v3 with and without the port under the benchmark lock, then run the leap-day oracle, fuzz and the amd64 scorer build before using the change.
