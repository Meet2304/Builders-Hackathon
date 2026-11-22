# Largest-first person partition scheduling

Prototype `explore/skew-schedule` at `67276cc`, based on v4 `c9e1a0c`.

Assign each partition a weight equal to surviving event rows plus buffered clicks. Persistent workers claim the largest remaining weight from a shared queue. The dynamic queue also limits the primary campaign accumulators and output batches to one per worker. A natural-order queue control isolates ordering from that accumulator change.

For heavy partitions, split attribution near the midpoint only at a boundary between whole linked people, with at least one eighth of event work on both sides. Both branches keep independent attribution scratch and campaign counts. A lone whale person stays in one task, and the split happens after per-person event sort and the partition click sort.

## Correctness and native results

36/36 fixtures, published dev MATCH, and 150/150 framework fuzz cases. All four configurations matched the seed-42 oracle and seed-43 consistency outputs. The final split branch also passed 150 fuzz cases with splitting forced, one partition and 97-byte chunks.

| Size | Variant | Instructions / line | Cycles / line | Session wall (ms) | Process wall (s) |
| --- | --- | ---: | ---: | ---: | ---: |
| 20M | v4 | 1769.6 | 638.5 | 84.0 | 0.5586 |
| 20M | natural-queue | 1746.1 | 621.9 | 83.5 | 0.5121 |
| 20M | schedule-only | 1746.4 | 621.1 | 82.5 | 0.5069 |
| 20M | candidate | 1745.4 | 620.8 | 82.0 | 0.5067 |
| 60M | v4 | 1749.9 | 672.2 | 283.5 | 1.6117 |
| 60M | natural-queue | 1735.9 | 673.8 | 320.5 | 1.6607 |
| 60M | schedule-only | 1737.8 | 675.9 | 331.5 | 1.6543 |
| 60M | candidate | 1734.7 | 674.5 | 299.5 | 1.6316 |

At 20M, most of the instruction delta already appears in the natural-order queue. Using the same queue, largest-first improved median wall from 0.5122 s to 0.5069 s, and splitting changed it to 0.5067 s. At 60M the split improved the largest-first queue by 23 ms and still trailed v4 by 20 ms. Limiting accumulators changes Parquet batch count as well as scheduling.

## Linux replay

| Size | v4 (s) | Largest-first and split (s) | Change |
| --- | ---: | ---: | ---: |
| 20M | 0.4547 | 0.4356 | −4.2% |
| 60M | 1.4735 | 1.4822 | +0.6% |

Both datasets exercised four whole-person splits. The original Linux build attempt failed during Docker registry DNS resolution. The retry used successful local image tags and recorded host load at each sample boundary. It proceeded without the strict host-idle guard after the GUI and Docker VM kept that guard blocked. Treat these Linux results as directional. Hardware counters were available only on native macOS.

**Recommendation:** Keep the worker queue as a candidate for 20M, where fewer accumulators account for most of the measured instruction win. Rework the 60M schedule before porting it as a default. Whole-person splitting recovered some time at 60M, while the combined 60M prototype still trailed v4 on both platforms.

[Raw paired runs, profiling counters and exact output hashes](../results/skew-schedule-matrix.json)
