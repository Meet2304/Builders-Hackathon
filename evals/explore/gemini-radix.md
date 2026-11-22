# Counting sort by local person id

Prototype `explore/gemini-radix` at `37103bf` (sort introduced in `c99960e`, then merged onto v3 `29b64bf`).

## Hypothesis and change

v3 sessionizes by comparison-sorting each person partition on a packed `(person, ts)` u64. The local person id is a dense `0..n_persons` integer, so a counting scatter can group a partition in one pass. Each person's run is then insertion-sorted up to 24 rows, `sort_unstable` up to 512, and an LSD radix on the timestamp after that. A partition that is too large for the scatter (more than 2^20 people, or more than 8 MB) uses the LSD radix on the whole key instead.

Clicks use the same grouping. Within a person they are ordered by timestamp ascending, then `click_id` descending via `Ids::cmp`, so an interned id still compares as bytes. Gemini 4 Neon (Neon High) specified a u128 key for the all-packed click case. This port uses the tie-fixup path Neon also described, for every click: radix or comparison sort by timestamp, then `Ids::cmp` only on equal timestamps. Packed ids take the u64 fast path inside `Ids::cmp`.

The spare buffers and the offset array live on the per-thread `Scratch` and are reused across partitions.

## Correctness

On `37103bf`, the linux profile passed 36/36 native fixtures, dev MATCH, all 10 oracle diffs including seed-62-20m, and 129/129 strict plus 21/21 robust fuzz seeds under the default and the five debug settings. A unit test checks the counting sort and the radix fallback against the old comparison order, including interned click ids, wide keys, empty input, and a one-row pack. Container gates were not part of this profile.

## Instructions, then time

Judge the change by instructions. The only difference from v3 `29b64bf` is this sort, so the whole-program instruction delta is the sessions-phase delta. Counts are median instructions per physical event line at 20M (seed-42, 21,507,843 lines), from the framework counters. v3's session share uses its full-eval counters: session CPU 0.875 s / (user 3.72 + sys 0.43) × 2,598.38 = 548, which is the 550 in the v3 per-line split.

| | v3 `29b64bf` | This sort | Δ |
| --- | ---: | ---: | ---: |
| Instructions / row | 2,598.38 | 2,390.93 | **−207 (−8.0%)** |
| Instruction-counter sd | 68e6 total (~3 / row) | 13 / row | |
| Sessions instructions / row | 548 | **341** | −207 |
| Native 20M wall, interleaved A/B (5 pairs) | 0.672 s | 0.669 s | −0.4%, not significant (delta 0.003 s vs 2 sd 0.034 s) |
| Linux arm64 20M process wall (5 pairs) | 0.571 s | 0.551 s | −3.5%, inconclusive |
| Linux minor faults | 16,247 | 16,283 | unchanged |

The absolute native block in this eval was noisy (load 5.2, session wall 0.107 s vs 0.110 s, CPU 0.805 s vs 0.875 s). Do not use that wall time. The instruction counter did not move with the noise.

Local wall time stays flat because the M5 retires these instructions at IPC 3.2, and 207 rows' worth is about 0.02 s inside the A/B noise. The practice board took 1.942 s for the same 2,598 instructions/row, about 97 ns/row. At that rate, −207 instructions/row is about **−0.15 s** on the 20M practice run (1.79 s instead of 1.94 s) if the scorer stays instruction-throughput bound. It does not move the program toward the 300–375 instructions/row the 0.28 s leaders need.

## Verdict and v4 port

Port it. The sort is correct, it removes 207 instructions per row from a 548-instruction session phase, and the Linux faults do not change. Do not expect a local wall-time win on the M5, and do not spend a submission on this alone.

Copy `sort_events_counting`, `sort_clicks_counting`, the radix helpers, and the three `Scratch` buffers from `37103bf` into the v4 `process_part`. Keep the wide-key path and the `Ids::cmp` tie break. The unit test `counting_sort_matches_comparison_sort` is the differential check.

Gemini 4 Neon supplied the counting-sort design, the per-run size tiers, the large-partition radix fallback, and the interned-id trap. The tie-fixup click path, the merge onto `29b64bf`, and all measurement are local.
