# Cache-sized dedup tables at 60M

Prototype `explore/dedup-subdivide` at `6da0cd2`, based on v4 `20b8e79`. Commit `4c68681` adds the targeted cross-person regression test. The earlier global partition increase reduced dedup cycles but made parse and session work more expensive. This prototype keeps 256 person partitions and subdivides only the existing event-ID partitions during dedup.

The outer dedup partition uses the high bits of `mix(event_id)`. Its children use middle bits of the same hash and probe on the low bits. The table compares the full event ID. A row's person partition appears in the drop reference that identifies the losing row. Invalid events enter the same dedup stream with no output row reference.

The child target is 24,576 rows. Each routed record carries the full ID, the low hash bits for probing and a packed source position. At 16 bytes per slot, each child table is capped at 1 MiB. An overfull child sorts by ID and source order and selects the earliest ingest, with source order breaking ties. Small partitions, forced hash masks and source references too wide to pack use baseline dedup.

## Correctness

Fixtures 36/36, published dev MATCH, and framework fuzz 150/150. Both native 60M binaries and the Linux prototype with one and eight workers match the cached seed-43 hash `5121c6474473be5a073e6bc293b2966dcd09bd7d9646c0004bf259297b65c5bd`.

The differential test matches the flat dedup drop multiset, including a child over the cap, ties, invalid rows and duplicates with different destinations. The targeted test parses two copies of the same ID with different users and asserts that they route to distinct person buckets in the valid case. It activates the real split and checks the exact drop for the later-ingested copy, which appears first in input order. Replacing the earliest copy's timestamp with an invalid one still suppresses the valid copy.

## Native counters

One eight-worker counter probe per revision, each built from a fresh release target. The denominator is 64,150,261 event input lines.

| Metric | v4 | Subdivided | Change |
| --- | ---: | ---: | ---: |
| Dedup instructions/line | 36.44 | 57.30 | +57.2% |
| Dedup cycles/line | 76.45 | 63.71 | −16.7% |
| Dedup IPC | 0.477 | 0.899 | +88.5% |
| Whole-process instructions/line | 1,483.83 | 1,506.22 | +1.5% |
| Whole-process cycles/line | 633.76 | 634.74 | +0.2% |
| Whole-process cycles | 40.656B | 40.719B | +0.2% |
| Sample wall time (s) | 1.715 | 1.534 | −10.6% |

The extra routing pass buys 12.74 cycles per event line inside dedup at a cost of 20.86 more dedup instructions. Total cycles are effectively flat over these two probes. The individual wall samples give context for the PMU readings.

## Linux 60M

Five interleaved warm pairs in clean Linux arm64 images with eight vCPUs, a 24 GiB cap, THP `madvise` and seed-43 staged in a named volume. The host-load guard stayed enabled. This Linux guest exposes no hardware PMU, so instruction and cycle counts come from the native probes.

| Median metric | v4 | Subdivided | Change |
| --- | ---: | ---: | ---: |
| Dedup wall (ms) | 148 | 128 | −13.5% |
| Whole-process wall (s) | 1.2354 | 1.3821 | +11.9% |
| User CPU time (s) | 8.85 | 9.79 | +10.6% |
| Minor faults | 57,593 | 75,719 | +31.5% |
| Peak cgroup memory (GiB) | 5.18 | 5.29 | +2.2% |

The prototype won two of five whole-process pairs. Dedup itself was faster in all five. Keep flat dedup in v5. The test confirms that independent child tables improve dedup locality, but the extra routing pass raises instruction count and the Linux measurements provide no whole-process speedup.

[Raw comparison and output hashes](../results/dedup-subdivide-v4.json)
