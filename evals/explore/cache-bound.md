# Cache-sized work partitions

Prototype `explore/cache-bound` at `140262a`, based on v4 `c9e1a0c`.

The fixed 256-way split makes a typical 60M dedup hash table about 8 MiB. The prototype sizes partitions at roughly 3 MiB of event input each, rounded up to a power of two within 64–4096. Seed-42 uses 1,024 partitions and seed-43 uses 2,048. The uniform-key model targets 0.75–1.5 MiB hash tables. Large person partitions can still exceed that target.

The dedup table uses separate 8-byte key and 4-byte winner arrays, down from 16 bytes per slot. The winner encodes task and row indexes with widths derived from the partition's actual shape. Wider references use the original path. Prefetching works in batches of 16 and preserves input order for equal-ingest copies. The emitted dedup stream still stores its full timestamp and key.

The native matrix isolates adaptive sizing, compact slots and prefetching. Debug partition overrides remain exact. The Linux Docker Desktop guest exposes no hardware CPU event source, so Linux results use process wall and page-fault counters. Native retired instructions and cycles use physical event input lines, including dirty rows.

## Correctness

The candidate passed 36/36 fixtures, published dev MATCH, 150/150 framework fuzz cases, and the same fuzz seeds with 3 partitions, 4-bit hashes, and the scalar path forced. Each measured configuration matched both output tables on seed-42 and seed-43 before timing.

## Native counters and wall time

Five rotated samples per configuration. Phase hardware counters are separate probes, with three baseline and full-prototype samples and one sample for each ablation.

| Size | Variant | Instructions / line | Cycles / line | Dedup instructions / line | Dedup cycles / line | Dedup IPC | Wall (s) | Dedup wall (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20M | v4 | 1768.512 | 642.562 | 36.260 | 53.130 | 0.682 | 0.517 | 35.000 |
| 20M | adaptive only | 1803.807 | 699.087 | 42.160 | 57.080 | 0.739 | 0.569 | 35.000 |
| 20M | compact only | 1771.966 | 655.918 | 38.610 | 49.020 | 0.788 | 0.557 | 32.000 |
| 20M | adaptive + compact | 1805.401 | 692.374 | 43.560 | 49.320 | 0.883 | 0.571 | 34.000 |
| 20M | adaptive + compact + prefetch | 1821.990 | 692.975 | 51.950 | 52.580 | 0.988 | 0.569 | 34.000 |
| 60M | v4 | 1747.637 | 661.522 | 35.080 | 68.980 | 0.509 | 1.603 | 149.000 |
| 60M | adaptive only | 1769.423 | 687.509 | 38.190 | 53.510 | 0.714 | 1.667 | 111.000 |
| 60M | compact only | 1749.243 | 666.482 | 38.410 | 73.880 | 0.520 | 1.593 | 143.000 |
| 60M | adaptive + compact | 1774.741 | 688.658 | 41.040 | 54.490 | 0.753 | 1.710 | 106.000 |
| 60M | adaptive + compact + prefetch | 1785.066 | 707.927 | 52.180 | 53.790 | 0.970 | 1.716 | 115.000 |

At 60M, adaptive sizing alone lowered dedup cycles per event line by 22.4% and dedup wall by 38 ms. The whole pipeline added 22 retired instructions and 26 cycles per event line. Raising the global partition count also grows the parser and task bucket arrays. Native peak footprint rose from 5.24 GB for v4 to 5.78 GB under adaptive sizing alone.

Batch prefetch on the compact adaptive layout added about 11 dedup instructions per event line at 60M and saved less than one cycle in the separate phase probes. Whole-process measurement favored the simpler layout. Compact slots at 256 partitions saved dedup cycles at 20M, but increased them at 60M.

## Linux wall time

Five paired process-wall samples on named volumes. The Linux arm64 guest lacks hardware instructions and cycles counters.

| Size | v4 (s) | Full prototype (s) | Change |
| --- | ---: | ---: | ---: |
| 20M | 0.4540 | 0.4753 | +4.7% |
| 60M | 1.4030 | 1.5176 | +8.2% |

**Recommendation:** Keep the 256-way layout for now. Test independent dedup subdivision before changing person partition counts. The 60M dedup cycle drop confirms a locality gain, while whole-process cycles and Linux wall time regress with the bundled layout.

[Raw matrix and exact output hashes](../results/cache-bound-matrix.json)
