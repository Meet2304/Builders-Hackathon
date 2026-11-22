# x86 instruction counts (callgrind, x86-64-v2) vs ARM

Analyst 3, 2026-11-22. **New-generator data only** (1 in 8 IDs is 33 bytes). Dev = `data/dev` (1,071,894 event / 255,147 click / 44,906 link lines). Everything here is `NCPU=1`. The one exception is the futex section.

## Method (reproducible)

```sh
evals/insights3/build.sh <commit>                  # linux/amd64, target-cpu=x86-64-v2, line tables, sha256 guard
evals/insights3/count.sh <commit> data/dev dev     # callgrind, one dump per lap() mark (--dump-before=getrusage)
python3 evals/insights3/parse_cg.py ~/.cache/insights3/cg/<sha12>-dev <(git show <commit>:src/main.rs)
.venv/bin/python evals/insights3/arm_counts.py <macOS binary> data/dev 5 > results/arm-<commit>-dev.json
python3 evals/insights3/report.py data/dev dev <commit>...
evals/insights3/futex.sh <linux-arm64 binary> <dataset> <label> 8   # futex syscalls per phase (strace)
```

- **Tooling:** `docker/Dockerfile` is rust:1-slim-bookworm (amd64) plus valgrind 3.19. It runs under Rosetta, at `--cpus=2` and nice 19, one container at a time. Wall time under emulation means nothing. Ir counts are deterministic.
- **Correctness:** the x86 output under valgrind is MATCH against `data/dev-answer` for both commits.
- **Phase attribution:** each `lap()` calls `getrusage`, so `--dump-before=getrusage` gives exact per-phase totals. Inside a phase, `src/main.rs` lines map to their enclosing `fn` by brace matching, which works through fat-LTO inlining because DWARF line tables keep the inlined file:line. Library code is bucketed by source file. `Ids::intern` is `#[cold]`, so it remains a real symbol, and its inclusive cost and call count are exact.
- **Stale-binary trap, hit and fixed:** the shared cargo target dir fingerprints by mtime, and `git archive` keeps commit-time mtimes. Building `3671aeb` after `5b7bcc2` first produced the *same* binary. `build.sh` now copies and touches the source, and refuses any binary whose sha256 matches another commit's.
- **ARM side:** `instr=` lap field, macOS, min of 5 runs. `a019739` (v4) predates the field, so v4 has no ARM baseline on new data.

## rep-string artifact (x86 only)

Valgrind counts every iteration of `rep stosb` (glibc `memset-vec-unaligned-erms.S:336`) and `rep movsb` (`memmove-vec-unaligned-erms.S:598`) as one instruction, so 1 Ir per byte. The hardware retires the string op at 32–64 B/cycle. The `corr` column replaces those Ir with bytes/32, one AVX2 store per 32 B, which is roughly what the ARM libc loop retires. It affects:

| phase | v5 bytes zeroed or copied by `rep stos/movs` |
| --- | ---: |
| dedup | 64.3 MB: `tab.resize(cap, (0,0))` per partition, 256 × ~250 KB |
| sessions | 25.6 MB |
| write | 13.9 MB (19.7 MB with the move-4 writer) |

Raw callgrind therefore shows dedup at 107 per line on x86 against 39 on ARM. That gap is not a real x86 weakness. The corrected figure is 49.

## Per-phase table, dev, instructions per event line, NCPU=1

| phase | v5 `5b7bcc2` ARM | v5 x86 raw | v5 x86 corr | x86/ARM | v7-base `3671aeb` ARM | x86 raw | x86 corr | x86/ARM |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lookups | 119 | 55 | 52 | 0.43* | 118 | 53 | 50 | 0.43* |
| events | 829 | 816 | 813 | 0.98 | 823 | 809 | 806 | 0.98 |
| clicks | 171 | 163 | 162 | 0.95 | 154 | 146 | 145 | 0.94 |
| dedup | 39 | 107 | 49 | 1.23 | 39 | 107 | 49 | 1.25 |
| sessions | 302 | 356 | 333 | 1.10 | 244 | 277 | 254 | 1.04 |
| write | 181 | 184 | 171 | 0.95 | 95 | 89 | 71 | 0.75 |
| **total** | **1,642** | 1,680 | **1,579** | **0.96** | **1,473** | 1,481 | **1,375** | **0.93** |

\* The ARM lookups figure includes process start (dyld and exec) and kernel work for mapping the inputs. The x86 count is user-mode only. These two are not comparable.

Own-line rates: v5 events are **813 per event line on x86 against 829 on ARM** (710 on the old data). Clicks are 681 per click line on x86 against 720 on ARM. v7-base clicks are 611 against 648.

**Verdict: the ARM rankings hold on x86.** The SSSE3 twins are not weak:
- The SSSE3 packer runs, and the scalar path is not taken. `pack_fast + pk_place + pack_simd` cost 27 per event line, `Ids::key_slow` is never called, and `pack` costs 0.3 per line.
- The SSE2 classify (`classify_simd`) costs 26 per event line.

The only phase where x86 runs above ARM is **sessions, at +10% on v5 (+31 per line) and +4% on v7-base**. That's sort and compare code (`core-sort`, `cmp.rs`, `ptr`), which is small.

## `Ids::intern`: the long-ID cost, x86, dev

v5 and v7-base are identical here. Move 6 hasn't landed yet.

| caller phase | calls | Ir incl | per call | per event line |
| --- | ---: | ---: | ---: | ---: |
| lookups (links) | 11,111 | 4.6M | 411 | 4.3 |
| **events** | **260,402** | **95.4M** | **366** | **89.0** (11% of the phase) |
| clicks | 62,428 | 16.6M | 266 | 15.5 |

The events per-call cost of 366 breaks down like this:

| part | per call | what it is |
| --- | ---: | --- |
| intern self | 133 | xxh3_64 over 33 bytes, inlined, for shard selection; Mutex lock + unlock fast path (`lock cmpxchg` / `xchg`); `strs.push` |
| `HashMap::rustc_entry` self | 81 | |
| `foldhash::hash_bytes_long` | 40 | a second hash of the same 33 bytes |
| `reserve_rehash` | 55 amortized | |
| memcmp + memcpy | ~24 | |

Structural costs visible in the counts:
1. **Every 33-byte ID is hashed twice**: once with xxh3 for the shard, once with foldhash inside hashbrown.
2. **The shard maps start at capacity 0** (`new_map(0)`). Rehash is 25% of intern's Ir on dev, and the rehash runs while the shard lock is held.
3. **Every call takes a lock.** That is one uncontended `lock cmpxchg` (about 18–20 cycles on Cascade Lake) per long ID even at `NCPU=1`. Under contention it's a futex.
4. `Ids::bytes` also locks, once per output row: 118k calls in write and 20k in lookups, 68 Ir per call.

## Contention (futex syscalls, native arm64 Linux, strace, `--cpus=2`)

Rust's std `Mutex` enters the kernel only when contended (`FUTEX_WAIT_BITSET` / `FUTEX_WAKE`), on x86 and arm64 alike. Each such call is a sandbox round trip under gVisor.

| run | lookups | **events** | clicks | dedup | sessions | write |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| v5 dev, NCPU=1 | 32 | 7 | 7 | 10 | 5 | 3 |
| v5 dev, NCPU=8 | 95 | 541 | 135 | 63 | 50 | 71 |
| **v5 seed-42 20M, NCPU=8** | 615 | **58,192** | 5,843 | 20 | 90 | 99 |

- Lines grow 20× from dev to 20M, and futex calls in events grow **107×**. The shards get bigger, rehashes run under the lock, and hold times grow, so this is superlinear.
- Under strace, where each syscall is expensive (the same shape as gVisor), v5's 20M events parse took **28.4 s wall for 12 s of CPU**.
- `--cpus=2` with 8 threads exaggerates lock-holder preemption, so read the absolute count as indicative. The growth relative to dev is the finding.
- Lock-free long IDs (move 6) should take events and clicks back to roughly the NCPU=1 baseline.

## Predictions, 20M board

Pending the full seed-42 callgrind; see below. The dev per-line figures give:

| commit | x86 corr / event line (dev) | old model (28.77 G/s, no constant) | board fit 1.70 s + 0.000318 × instr/row |
| --- | ---: | ---: | ---: |
| v5 `5b7bcc2` | 1,579 | 1.18 s | 2.20 s (actual **2.146 s**) |
| v7-base `3671aeb` | 1,375 | 1.03 s | 2.14 s |

The old instruction-only model is dead (see `evals/insights/board-fit.md`). x86 counts don't rescue it: x86 retires about 4–7% *fewer* instructions than ARM for the same work, so it predicts slightly faster times, not slower. The gap to the board is contention plus sandbox cost, which Ir can't see. Use the gVisor reproduction for the board. Use these counts to rank pure-compute moves only.
