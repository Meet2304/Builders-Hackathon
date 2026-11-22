# V3 person partition skew

One instrumented native run per size with eight workers and v3's default 256 person partitions. Counts include every surviving event after dedup. Both runs matched the cached expected output exactly. Skew is measured on v3 `29b64bf`; the diagnostic source is `explore/unneeded-work-counters` at `99889aa`.

| Size | Surviving events | Average per partition | Largest partition | Largest / average | Slowest observed task |
| --- | ---: | ---: | ---: | ---: | --- |
| 20M | 19,564,682 | 76,425 | 421,509 (#51) | 5.52× | 18.0 ms (#42) |
| 60M | 58,449,132 | 228,317 | 1,204,818 (#94) | 5.28× | 105.6 ms (#94) |

| Rank | 20M partition | Rows / average | 60M partition | Rows / average |
| --- | ---: | ---: | ---: | ---: |
| 1 | 51 | 421,509 / 5.52× | 94 | 1,204,818 / 5.28× |
| 2 | 42 | 413,788 / 5.41× | 117 | 1,148,012 / 5.03× |
| 3 | 53 | 324,724 / 4.25× | 96 | 932,871 / 4.09× |
| 4 | 23 | 291,005 / 3.81× | 102 | 905,726 / 3.97× |
| 5 | 246 | 268,878 / 3.52× | 194 | 856,725 / 3.75× |

The two largest partitions hold only about 2.1% of surviving events each, but a slow block can determine the tail when scheduled late. The biggest 20M partition and slowest 20M task differ, so event count alone is an imperfect cost estimate. Click count and assist activity are additional weights to test. The single task-wall observations include instrumentation and scheduling.

Test largest-first processing before splitting a person across tasks. It should change critical-path wall time while leaving per-row instructions approximately unchanged. At 256 partitions, a model of eight instructions per comparison and roughly `256 × log₂(256)` comparisons puts the order sort near 0.0008 instructions per physical input event line at 20M and 0.0003 at 60M, excluding size collection. A production run should measure the whole-pipeline counter delta.

[Raw counts and exact output hashes](../results/unneeded-work-counts.json)
