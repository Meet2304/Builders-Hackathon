# Critical path on the regenerated shopping-sessions input

## v5 under gVisor

On the new seed-42, v5 took **0.94 s in plain Linux and 2.23 s inside gVisor**. Including sandbox creation and destruction, the respective medians were 0.942 s and 2.361 s. Event parsing accounted for 911 ms of the 1,290 ms process gap. The scorer's reported 2.146 s is close to this gVisor measurement. A single matched version and size cannot identify the scorer runtime or establish a predictor across candidates.

These results use ELF SHA-256 `05faef768b7acf9c8648c7c1e5cc950968d164ec1a433a99a67c00ac935dc109` from v5 `5b7bcc2`. Both modes used an 8-CPU, 22-GiB Docker cgroup on Linux/arm64, disabled swap and networking, named-volume input, and tmpfs output. The official 20261116 arm64 runsc bundle ran rootless inside the outer container. Each pair used the same newly staged input, and order reversed on alternate pairs. The largest new event file was 377,969,798 bytes. Both modes produced 2,226,091 user rows. Output equality is tested separately from timing.

| v5 phase, median of 3 | Plain ms | runsc ms | Difference ms |
|---|---:|---:|---:|
| Startup, maps and lookups | 42 | 93 | +51 |
| Events parse | 584 | 1,495 | +911 |
| Clicks parse | 111 | 197 | +86 |
| Dedup and release | 41 | 54 | +13 |
| Sessions and attribution | 109 | 138 | +29 |
| Reduce and write both outputs | 35 | 165 | +130 |
| Process startup and exit outside internal marks | 17 | 76 | +59 |
| Process total | 940 | 2,230 | +1,290 |

Plain samples were 0.92, 0.94, 0.95 s. Sandbox samples were 2.27, 2.13, 2.23 s. The per-phase medians need not sum to the median total. GNU time resolves process wall to 10 ms. Plain median getrusage reported 17,879 minor and zero major faults. Guest getrusage returned zero for both, including at all diagnostic phase boundaries.

## Input-policy experiment

These medians use diagnostic v5 ELF SHA-256 `d000c6d784c4e3df843e487171494b10d7076622180f2b5880a99d3cca986209`. Each policy was measured in three reversed-order plain/runsc pairs. All four used the same parallel file-open implementation and differed through an environment variable. Policies ran in consecutive batches. Outer cgroup faults include the runtime, loader, Sentry and helpers. They count actual kernel events across that outer cgroup and cannot distinguish anonymous from file faults within the guest.

| Input policy | Plain s | runsc s | Plain cgroup faults | runsc cgroup faults |
|---|---:|---:|---:|---:|
| mmap | 0.89 | 2.06 | 18,299 | 2,178,863 |
| mmap with MAP_POPULATE | 0.95 | 2.17 | 18,313 | 2,102,763 |
| Read into one private mapping per file | 0.90 | 2.53 | 42,729 | 2,766,829 |
| Same with MADV_HUGEPAGE | 0.93 | 2.56 | 42,889 | 2,579,820 |

Reducing cgroup faults by about 76,000 through MAP_POPULATE did not improve process time. Eager whole-file copies made both the runsc process and its teardown slower. The read modes retain their buffers because fallback keys borrow input bytes. A bounded per-worker pread design requires its own measurement.

The v5 and v6 baselines both already call `std::process::exit(0)` after every writer closes. Neither invokes Rust destructors for the input mappings after the last mark. Linux still has to release the address space.

## Reproduction

Use `evals/explore/runsc/run.sh <linux-arm64-ELF-or-timing-image> data/seed-42`. Set `RUNSC_JSONL` to retain raw records. The script prints executable hashes, sample times, and median phase deltas. See the adjacent runsc README for low-level commands and fault diagnostics.
