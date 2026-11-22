# x86 instruction counts (callgrind, x86-64-v2) vs ARM

## Headline (01:35 ET)

1. **The ARM rankings hold on x86 for v5.** Per phase, x86 is 0.94–1.10× ARM, and total instructions are 4% *lower* on x86. The SSSE3 packer and the SSE2 classify run, and no scalar fallback is taken.
2. **v7 `e693e18` has one x86-specific weak spot: `hex32()`.** It's a scalar 16-iteration table-and-shift-or loop costing **256 Ir per long ID** on x86, about 2× ARM, because x86 has no shifted-operand `orr`. It eats most of the `Ids::intern` saving on x86: events go **813 → 804 per line on x86, against 829 → 768 on ARM**. Fix: use the SSSE3 `digits()` kernel from `explore/gemini-hex32`, about 30 instructions. That's worth about **−70 per event line on x86** (events −56, clicks −14).
3. **`method/v8` @ `aca7078` is DIFFER on dev.** It writes 133,891 user_daily rows against 118,107, with 5,266 duplicate keys. Its parent `8bb8d43` is MATCH. This was flagged to the orchestrator at 01:33.
4. **Contention, not instructions, is what v7 fixes.** v5 makes 58,192 futex calls in events parse at 20M (8 threads), against 541 on dev, so the growth is superlinear. Ir barely moves (intern was 89 per event line on x86), but each of those futex calls is a sandbox round trip under gVisor.

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

v7 `e693e18` against v5 (`results/dev-table-v5-v7.md`):

| phase | v5 ARM | v5 x86 corr | v7 ARM | v7 x86 raw | v7 x86 corr | v7 x86/ARM |
|---|---:|---:|---:|---:|---:|---:|
| lookups | 119 | 52 | 121 | 54 | 51 | 0.42* |
| events | 829 | 813 | **768** | 804 | **804** | **1.05** |
| clicks | 171 | 162 | 148 | 150 | 150 | 1.01 |
| dedup | 39 | 49 | 40 | 106 | 49 | 1.20 |
| sessions | 302 | 333 | 244 | 277 | 253 | 1.04 |
| write | 181 | 171 | 179 | 186 | 174 | 0.97 |
| **total** | **1,642** | **1,579** | **1,501** | 1,577 | **1,480** | **0.99** |

What changed in v7's events phase on x86, by self Ir (v7 − v5):
- added: `hex32` +66.7M (**256 per call**), `LongTable::slot` +6.2M (24 per call), `Ids::long_key` +4.7M (18 per call)
- removed: foldhash −21.9M, hashbrown −20.8M, xxh3 −11.5M, `Ids::intern` −4.6M

The net is −13M on x86. On ARM it's −65M. Clicks show the same pattern: `hex32` +16.0M. `Ids::bytes` per output row goes from 68 to 89 Ir, because long keys are decoded with scalar code. That's small, about 2.4 per line.

v5 against v7-base `3671aeb` (before move 6, with move 4's writer):

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
| **v7 `e693e18` seed-42 20M, NCPU=8** | 106 | **79** | 73 | 59 | 108 | 75 |

**v7 removes the contention:** events futex calls drop from 58,192 to 79, and clicks from 5,843 to 73. Under strace, events parse falls from 28.4 s to 1.9 s of wall time (end of events 28.73 s → 2.08 s) and the whole run from 32.6 s to 4.5 s. Both runs use the same `--cpus=2` and 8 threads. The v7 binary is an arm64 Linux build from clean source.

- Lines grow 20× from dev to 20M, and futex calls in events grow **107×**. The shards get bigger, rehashes run under the lock, and hold times grow, so this is superlinear.
- Under strace, where each syscall is expensive (the same shape as gVisor), v5's 20M events parse took **28.4 s wall for 12 s of CPU**.
- `--cpus=2` with 8 threads exaggerates lock-holder preemption, so read the absolute count as indicative. The growth relative to dev is the finding.
- Lock-free long IDs (move 6) should take events and clicks back to roughly the NCPU=1 baseline.

## Predictions, 20M board

From the dev per-line figures. A full 20M callgrind takes about 25 min per commit under emulation and wasn't run. Intern Ir per call is flat in N apart from amortized rehash, so dev per line is representative for Ir.

| commit | x86 corr / event line (dev) | old model (28.77 G/s, no constant) | board fit 1.70 s + 0.000318 × instr/row |
| --- | ---: | ---: | ---: |
| v5 `5b7bcc2` | 1,579 | 1.18 s | 2.20 s (actual **2.146 s**) |
| v7-base `3671aeb` | 1,375 | 1.03 s | 2.14 s |
| v7 `e693e18` | 1,480 | 1.11 s | 2.17 s; not valid for v7 (below) |
| v7 + SSSE3 hex32 (est.) | ~1,410 | ~1.05 s | – |

The board fit's 1.70 s constant is mostly the intern contention under gVisor, and v7 removes exactly that. So the fit can't price v7. Use Eval's gVisor 20M run (`lib/gvisor.py`).

The old instruction-only model is dead (see `evals/insights/board-fit.md`). x86 counts don't rescue it: x86 retires about 4–7% *fewer* instructions than ARM for the same work, so it predicts slightly faster times, not slower. The gap to the board is contention plus sandbox cost, which Ir can't see. Use the gVisor reproduction for the board. Use these counts to rank pure-compute moves only.

## Submission gate: v7b `96af24b` and v8 head `2b9aecd` (01:50 ET)

| check | `96af24b` (v7 + no-purge + `_exit`) | `2b9aecd` (v8 head) |
| --- | --- | --- |
| x86-64-v2, valgrind, NCPU=1, new dev | **MATCH** (bin 5005cffe…) | **MATCH** (bin b09246f1…) |
| x86 NCPU=8 under valgrind `--fair-sched=yes` | **MATCH** | – |
| x86 NCPU=8 native under Rosetta, 2 runs | **MATCH**, MATCH | – |
| mimalloc option numbers | `purge_decommits` = 5 and `purge_delay` = 15 in the libmimalloc-sys 0.1.49 headers, v3 (default) and v2 | |
| exit dump | 54,915 → 3,518 Ir, so `_exit` is taken | |

x86 instructions per event line, dev, corrected (`results/dev-table-v7-v7b-v8.md`):

| phase | v7 `e693e18` | v7b `96af24b` | v8 `2b9aecd` | v8 ARM | v8 x86/ARM |
|---|---:|---:|---:|---:|---:|
| lookups | 51 | 51 | 50 | 119 | * |
| events | 804 | 804 | **753** | 737 | 1.02 |
| clicks | 150 | 149 | **106** | 107 | 0.99 |
| dedup | 49 | 48 | 48 | 34 | 1.41 |
| sessions | 253 | 253 | 253 | 236 | 1.08 |
| write | 174 | 173 | 173 | 178 | 0.97 |
| **total** | **1,480** | **1,480** | **1,384** | 1,411 | 0.98 |

- **v7b and v7 have identical Ir per phase**, which is expected: no-purge and `_exit` save syscalls and faults, not instructions.
- **v8 fixes the x86 `hex32` weak spot.**
  - The SSSE3 kernel replaces the scalar loop: the long-ID path goes from about 298 to about 90 Ir per ID. The SIMD hex part is about 48 Ir per call, against 256 before.
  - Events go 804 → 753 on x86. The x86/ARM ratio for events returns from 1.05 to 1.02.
  - The click column decoder (`columns.rs`, 41M) replaces the generic scan (`for_each_record` 25M plus `IdIndex::direct_slot` 15M plus `parse_click` 7M): clicks go 628 → 446 per click line on x86, 450 on ARM.
- Dedup's x86/ARM ratio of 1.41 is residual after the rep correction (48 against 34). It's small in absolute terms (14 per line).
