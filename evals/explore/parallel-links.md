# Parallel link component construction

Prototype `explore/parallel-links` at `89ad72c`, based on v3 `29b64bf`.

## Hypothesis and change

V3 already parses links, sorts endpoint keys, looks up dense endpoint ranks, and inserts the result table in parallel. It traverses the edges to union components and scans for component names serially. The full v3 eval measured 54 ms in lookups at 20M and 216 ms at 60M. The phase also includes file setup and product and campaign lookups.

The drop-in loader in `src/links.rs` uses a concurrent hash index whose slots double as union-find nodes. That eliminates the endpoint sort, unique-key pass, and two binary searches per edge. Each successful union links a root to a strictly smaller ID by byte order, so a component's root is its exact name, including when an interned fallback ID wins. Compare-and-exchange retries a moved larger root. After all unions finish, workers resolve remappings and populate the existing link table. Link parsing uses chunks of at most 256 KiB to spread work across more workers.

## Correctness

The Rust differential test compares every ID in a synthetic graph with the serial v3 union and minimum-name scan. It covers interleaved long chains, a shared device, quote-normalized fields, malformed rows, repeated and reversed edges, and mixed packed and interned names at 1, 2 and 8 workers. All seven release unit tests and all 36 fixtures passed.

The quick profile matched the published dev answer, all 10 oracles, all 150 fuzz cases under defaults and every quick debug setting, and the 60M v1 consistency answer. Direct comparators also matched both output tables against v3 at dev, 20M and 60M. The quick profile leaves the amd64 runtime and clean build gates open.

## Timing

Native M5 Pro with eight threads. Eight alternating pairs at 20M and four at 60M.

| Size | Metric | v3 | Parallel links |
| --- | --- | ---: | ---: |
| 20M | Process wall (s) | 0.6740 | 0.6639 |
| 20M | User CPU (s) | 3.895 | 3.895 |
| 20M | System CPU (s) | 0.480 | 0.485 |
| 20M | Footprint (GB) | 2.039 | 2.049 |
| 20M | Lookup wall (ms) | 56.0 | 23.5 |
| 20M | Lookup CPU (ms) | 163.0 | 146.5 |
| 60M | Process wall (s) | 2.0179 | 1.8544 |
| 60M | User CPU (s) | 12.480 | 12.085 |
| 60M | System CPU (s) | 1.225 | 1.250 |
| 60M | Footprint (GB) | 5.721 | 5.741 |
| 60M | Lookup wall (ms) | 216.0 | 63.5 |
| 60M | Lookup CPU (ms) | 743.5 | 418.5 |

Lookup wall fell 58% at 20M and 71% at 60M. Process-wall medians improved 1.5% and 8.1%, respectively. The prototype won seven of eight 20M pairs and all four 60M pairs. Median paired savings were 29 ms and 178 ms. Initial host CPU busy was 15.3% and 12.8%, and neither native wall delta clears the framework’s significance rule. The standalone quick-profile 60M sample had 347,964 major faults and took 5.955 s. The interleaved run is the timing comparison.

Linux arm64 used the framework's named-volume probe with six alternating 20M pairs under the VM's THP `always` mode.

| Metric, median | v3 | Parallel links |
| --- | ---: | ---: |
| Process wall (s) | 0.5728 | 0.5436 |
| Lookup wall (ms) | 55.0 | 20.0 |
| Lookup CPU (ms) | 167 | 125 |
| Minor faults | 16,263 | 16,234 |
| Major faults | 0 | 0 |
| Max RSS (GB) | 4.04 | 4.02 |

The 5.1% Linux wall improvement falls short of the framework's dispersion threshold. The lookup phase showed the same reduction on both platforms.

## Recommendation

Port the module to v4 and run the full amd64 correctness and build gates before submission. It cuts the lookup phase by 30–35 ms on all 20M comparisons and about 153 ms at 60M while the public loader signature and runtime link table stay the same. The temporary construction index uses full key hashes, and the final table still honors v3's collision knob. The process-wall measurements support an incremental gain with limited timing confidence.

- [Quick eval](../results/parallel-links.md) and [result JSON](../results/parallel-links.json)
- [Native and Linux interleaved runs and exact differential hashes](../results/parallel-links-ab.json)
- [Framework comparison against the historical v3 full eval](../results/parallel-links-vs-v3.md)
