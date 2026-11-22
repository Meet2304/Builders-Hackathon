# Allocator bake-off on v2

The v2 pipeline at `953af43` has many short-lived bucket allocations. This experiment changes the global allocator to test how much of its Linux runtime comes from anonymous page faults and exit teardown.

| Variant | Prototype |
| --- | --- |
| System allocator | `953af43` (glibc on Linux, system malloc on macOS) |
| mimalloc 0.1.52 | `explore/allocator-mimalloc` at `3cf92b0` |
| tikv-jemallocator 0.6.1 | `explore/allocator-jemalloc` at `13a7847` |
| mimalloc with large OS pages enabled | Same mimalloc build, with `MIMALLOC_ALLOW_LARGE_OS_PAGES=1` at Linux runtime |

The jemalloc builder embeds `thp:always,metadata_thp:always` on Linux. macOS uses jemalloc's default configuration. The first jemalloc Linux build exposed a missing GNU Make binary in the slim Rust builder. The final commit installs Make in the build stage. [tikv/jemallocator build options](https://github.com/tikv/jemallocator/blob/main/jemalloc-sys/build.rs)

## Correctness and method

The two allocator builds passed `make fixtures-local` 36/36 and `make run-dev-local check-dev` matched the published answer. All three builds passed 10/10 framework oracles and 150/150 fuzz cases (129 strict and 21 robust) under each of five debug settings and under defaults. The native head-to-head used the same v2 source for all builds, 8 threads, and the seed-42 20M oracle and seed-43 60M consistency answer.

All four Linux variants matched dev. The Linux head-to-head used arm64 Docker Desktop with 8 CPUs, named-volume inputs, a read-only root, UID 1000, no network or capabilities, and a 24,000,000,000-byte cgroup cap with swap disabled. Linux wall includes the process exit. The tail is wall minus the final phase mark. RSS includes process-mapped pages. The cgroup peak can also include charged file cache and output tmpfs. The harness rotated allocator order and verified each THP setting. It restored the original mode before releasing the benchmark lock.

## Results

### Native macOS

Medians of six interleaved 20M samples and three 60M samples per allocator. The 20M and 60M hashes matched for all three builds.

| Size | Allocator | Wall (s) | Page reclaims | Page faults | Tail (ms) | RSS (GB) | Footprint (GB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 20M | system malloc | 1.629 | 416,669 | 1 | 90.8 | 6.46 | 4.08 |
| 20M | mimalloc | 1.574 | 359,620 | 0 | 85.5 | 5.89 | 3.97 |
| 20M | jemalloc | 1.734 | 401,876 | 3 | 156.5 | 6.25 | 4.33 |
| 60M | system malloc | 6.512 | 1,546,551 | 12,393 | 243.2 | 15.60 | 11.41 |
| 60M | mimalloc | 6.198 | 1,233,291 | 10,779 | 218.9 | 16.00 | 11.03 |
| 60M | jemalloc | 6.358 | 1,701,056 | 2,692 | 526.2 | 15.76 | 11.36 |

### Linux arm64

Medians of four interleaved warm samples per allocator and THP mode. All warm samples had zero major faults.

| Size / THP | Allocator | Wall (s) | Minor faults | Tail (ms) | RSS (GB) | Cgroup peak (GB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 20M / always | glibc | 2.083 | 818,685 | 141.2 | 5.67 | 3.79 |
| 20M / always | mimalloc | 1.647 | 21,067 | 10.4 | 5.99 | 4.09 |
| 20M / always | jemalloc | 1.666 | 30,332 | 10.6 | 6.70 | 4.81 |
| 20M / always | mimalloc + large pages | 1.688 | 22,748 | 10.8 | 5.99 | 4.09 |
| 20M / madvise | glibc | 2.134 | 967,341 | 161.0 | 5.69 | 3.81 |
| 20M / madvise | mimalloc | 1.595 | 21,130 | 10.5 | 5.99 | 4.08 |
| 20M / madvise | jemalloc | 1.575 | 30,808 | 11.1 | 6.71 | 4.81 |
| 20M / madvise | mimalloc + large pages | 1.598 | 21,204 | 10.5 | 5.99 | 4.09 |
| 60M / always | glibc | 14.591 | 2,193,469 | 698.6 | 16.27 | 10.64 |
| 60M / always | mimalloc | 10.717 | 96,132 | 118.1 | 17.02 | 11.38 |
| 60M / always | jemalloc | 9.877 | 1,062,358 | 172.8 | 18.16 | 12.71 |
| 60M / always | mimalloc + large pages | 10.413 | 89,980 | 102.0 | 17.03 | 11.39 |
| 60M / madvise | glibc | 11.363 | 2,847,140 | 516.4 | 16.26 | 10.64 |
| 60M / madvise | mimalloc | 8.309 | 90,636 | 69.8 | 17.05 | 11.39 |
| 60M / madvise | jemalloc | 8.599 | 218,877 | 78.1 | 18.50 | 13.00 |
| 60M / madvise | mimalloc + large pages | 8.432 | 84,896 | 75.6 | 17.05 | 11.39 |

Default mimalloc was 20.9% faster than glibc under `always` and 25.3% faster under `madvise` at 20M. Under `madvise`, it cut the system CPU median from 1.17 s to 0.115 s and the process tail from 161 ms to 11 ms. The framework's own `--profile linux` 20M run under `always` separately recorded 1.971 s for glibc, 1.553 s for mimalloc and 1.558 s for jemalloc.

The 60M warm timing blocks started at 21.8% and 18.2% host CPU busy, and the host was using swap. Across `always` samples, glibc ranged from 12.33 to 33.16 s and mimalloc from 6.73 to 12.01 s. The `madvise` ranges were 9.95 to 13.51 s and 8.14 to 10.73 s, respectively. Treat the 60M speed deltas as directional.

### 60M memory cap

Before each cold THP `madvise` run, `fincore` verified zero resident input bytes. All four runs completed under the 24 GB cap with zero cgroup OOM kills. This cold check lets the measured cgroup incur its own input page-cache charges.

| Allocator | Cold wall (s) | Cgroup peak (GB) | Headroom (GB) |
| --- | ---: | ---: | ---: |
| glibc | 15.238 | 16.38 | 7.62 |
| mimalloc | 12.365 | 17.13 | 6.87 |
| jemalloc | 11.122 | 18.74 | 5.26 |
| mimalloc + large pages | 11.936 | 17.12 | 6.88 |

The large-page option completed the dev MATCH and all timed runs with ordinary scorer privileges. The VM exposed zero reserved HugeTLB pages. This tests the option under those conditions. The experiment leaves performance with a configured HugeTLB pool unmeasured.

### Cascade Lake build checks

All three `linux/amd64` images built with `X86_CPU=cascadelake`. Build times were 93.7 s for glibc, 83.4 s for mimalloc and 99.6 s for jemalloc. Runtime comparisons used arm64 Linux.

## Recommendation

Keep default mimalloc in v3 as implemented in `8004f65`. It captures the 20M gain with lower Linux memory use and fewer faults than jemalloc in both THP modes. The large-page option added no consistent speedup in this setup. The 60M cold cap check leaves 6.87 GB of headroom with default mimalloc on the larger v2 pipeline.

- [Raw matrix, memory-cap checks and build records](../results/allocator-matrix.json)
- Framework Linux profiles for [glibc](../results/allocator-system.md), [mimalloc](../results/allocator-mimalloc.md) and [jemalloc](../results/allocator-jemalloc.md)
- Framework comparisons against v2 for [mimalloc](../results/allocator-mimalloc-vs-v2.md) and [jemalloc](../results/allocator-jemalloc-vs-v2.md)
