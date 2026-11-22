# Board fit: about 1.7 s of our time is not compute

Analyst, 2026-11-22. Board: v3 **2.529 s**, v4 **2.198 s**, v5 **2.146 s** (20M, current scoring). Leaders **0.4508 s**. Local data: Eval `evals/results/v3,v4,v5.json` on `eval/framework`.

## 1. The fit

`board = a + b·x`, three points (two degrees of freedom, so this is a sanity fit, not proof):

| x (local, 20M) | v3 / v4 / v5 | a (s) | b | rms resid |
| --- | --- | ---: | ---: | ---: |
| **instructions per row** | 2,598 / 1,572 / 1,383 | **1.703** | **0.000318 s per instr/row** | **0.003 s** |
| user CPU s (M5) | 3.72 / 2.60 / 2.51 | 1.385 | 0.308 | 0.010 |
| cycles per row | 820 / 592 / 596 | 1.235 | 0.00158 | 0.024 |
| native wall | 0.624 / 0.457 / 0.501 | 1.115 | 2.23 | 0.063 |

- **Instructions per row explain the variable part almost exactly.** Cycles do not: v4 → v5 is +4 cycles per row and −0.052 s on the board.
- **The slope is too cheap for compute.** 0.000318 s per instr/row × 21.5M lines works out to **68 G (arm64) instructions/s**. That is 2–3× what an 8-vCPU Cascade Lake can retire (25–35 G/s). Only part of each instruction cut reaches the board, which is what you see when compute overlaps something slower.
- **What can't be told apart:** every "fixed" metric was the same in v3, v4 and v5. Input bytes, output bytes (21 MB), minor faults (Linux: 16.3K / 16.8K / 16.7K), peak RSS (≈ 3.9 GB, of which ≈ 1.9 GB anon), and thread count (8) all match. Any of them could be the 1.7 s. With three points, no local metric can single one out. **Only a probe that changes one of them can.**
- **Our 1.7 s is specific to us.** The leaders run the same data in 0.45 s total. The rescore added +0.17 s to the leaders and **+0.59 s to v3**. Whatever changed in the scorer hits our program 3.5× harder than theirs.

Old model (28.77 G/s, no constant): dead. Use `board ≈ 1.70 + 0.000318 × instr/row` until a probe moves `a`. v6 at about 1,200 per row predicts **≈ 2.08 s**. Instruction work alone cannot get below 1.70 s.

**At 60M:** if `a` scales with the input (I/O), it becomes about 5 s, and we finish about 5–6 s against the leaders' ~1.3 s. **`a` is now the whole race.**

## 2. Hypotheses

| Hypothesis | For | Against | Cheapest local test | Board probe that decides it |
| --- | --- | --- | --- | --- |
| **H1. mmap input is slow on the scorer** (sandbox like gVisor or a VM filesystem, cold page cache, a fault per 4–128 KB, mm-lock serialization) | `a` ≈ 1.9 GB ÷ 1.1 GB/s. The slope says compute is hidden behind something. We use `memmap2` for every input. The leaders read the same bytes in < 0.45 s. The rescore hurt us 3.5× more. | Local Linux (named volume, warm) shows 16K faults and no problem. | Linux VM, input on a **bind mount from macOS (virtiofs)** instead of the named volume, and with `drop_caches` before the run. Time mmap against `pread` into buffers. | **P1: v5 with `pread` input** (below). If `a` drops by > 0.5 s, it's H1. |
| **H2. Anonymous memory faults are expensive** (≈ 1.9 GB anon, no THP on the scorer, so ≈ 480K faults) | The same constant in v3–v5. A sandbox makes page faults cost µs each. | Spread over 8 threads, ≈ 480K × 2–3 µs ≈ 0.15–0.2 s, which is short of 1.7 s unless faults serialize. | Linux with THP `never` against `madvise`: count the anon faults and the time. | P2: v5 with the event and row buffers pre-faulted in parallel (`MAP_POPULATE`), or about half the anon footprint. Only if P1 leaves `a` > 0.8 s. |
| **H3. Wrong CPU count** (`NCPU` unset → `available_parallelism()`, which reads affinity and cgroup `cpu.max`) | A host-sized count (e.g. 64) under an 8-CPU quota spins rayon threads and gets CFS-throttled. | **The slope argues against it.** Too few threads (2–4) would make the slope 3–10× *steeper*. Throttling makes CPU cost more, not a flat constant. | `docker run --cpus=8 --cpuset-cpus=` with a host-wide affinity; log `available_parallelism`. | P3: v5 with `NCPU` defaulting to `min(avail, 8)`. Cheap, but last; expect no change. |
| **H4. Output on slow storage** | v6's writer change makes the files 4× larger. | Output is only 21 MB, the same for every version. The leaders write the same rows in 0.45 s, so storage must be ≥ 100 MB/s. | Linux: write `$OUTPUT_DIR` to a bind mount against tmpfs. | The **v6 writer change probes it for free, but at a cost**. Keep v6 **without** the writer settings until H1 is settled (§3). |
| **H5. Container start or image pull in the timer** | The "wait" values vary (165 ms, 20 ms, 5 m 51 s). | That would hit every team equally, yet the leaders are at 0.45 s. Our amd64 image is 30 MB. | — | None needed. It isn't team-specific. |
| **H6. Exit teardown of ≈ 4 GB of mappings** | It scales with RSS, which is constant across v3–v5. | Local exit tail 0.01–0.02 s. | Linux: time `munmap` of the input. | It goes away together with P1 (no file mapping) or P2. |

**Most likely:** H1. It's the only one that fits all three facts: a large constant, an overly cheap compute slope (overlap), and a rescore penalty that grows with how we read input.

## 3. Next board probe

**P1 = v5 `5b7bcc2` with only the input path changed: `pread` into buffers, no mmap.** Same parse code on `&[u8]`.
- Read each file in ~8 MB chunks, in parallel on the rayon pool, into one buffer per file. That's ≈ 1.9 GB anon at 20M and ≈ 5.7 GB at 60M, within 24 GB at 60M. Check the peak against the 22 GiB cgroup gate.
- Use `posix_fadvise(SEQUENTIAL)` per file.
- Gates: fixtures 36/36 and dev MATCH. Nothing else changes, so it's a ~30-minute Method job plus a quick Eval.

Reading the result:
- **`a` drops by ≥ 0.5 s:** H1 holds. Make streamed `pread` the default in every train, and better still, parse chunks as they arrive so reading overlaps parsing. Re-rank everything: instruction moves are worth 0.00032 s per instr/row only until `a` is gone.
- **No change:** H1 is out. Submit P2 (pre-faulted anon memory and halved buffers) in the same hour, then P3.

Meanwhile:
- **Hold the writer settings out of v6** (submit v6 = v5 + click sort only). If H4 is even partly true, 4× the bytes adds time. Also, a change there muddles the P1 reading.
- **Eval:** run the virtiofs bind-mount test plus `drop_caches` on mmap against `pread` locally. It's the cheapest local reproduction of H1 and can run while P1 is being built.

## 4. Addendum (00:55 ET): root cause found, re-fit

Two new facts:
- **The generator changed at 21:08** (`docs/rules.md` line 101): 1 in 8 IDs is now 33 bytes, which goes past the 10-character packer into the mutex-sharded `Ids::intern`.
- **Explorer 5 reproduced the board:** v5 on the new 20M data runs in 0.94 s under plain Docker and **2.23 s under gVisor (runsc)**, against a board of **2.146 s**. That puts the scorer in a gVisor-class sandbox, where every futex, mmap and page fault is a slow trip into the sandbox.

**How much of the 1.70 s the long IDs explain:**
- Scout's local cost is +0.72 s on the M5 (v5: 0.42 → 1.14 s).
- If contention on Cascade Lake is 1.5–2× worse, the long IDs account for **≈ 1.1–1.4 s** of the 1.70 s.
- The rest is gVisor's syscall cost: futex wake/wait on the contended `Mutex`, plus page faults and mmap. In the harness that is parse 0.565 → 1.528 s.
- Together they explain **essentially all of the 1.70 s**.
- They also explain the fit's odd shape. v3, v4 and v5 all share the same intern path, so it showed up as a constant. A serialized lock acts as a floor (Amdahl's law), so instruction cuts elsewhere only partly reached the board. That's the "68 G/s" slope. H1 was the right *shape* with the wrong cause.

**The model from here:**
- **Retire the linear fit.** The local gVisor time (Explorer 5's harness, new data) is the predictor of the board. Check it against each submission. For v5, the harness is +0.08 s above the board.
- **Predicted board after an exact, lock-free long-ID path: ≈ 0.8–1.05 s.** That's v5 at 2.146 s, minus 1.1–1.4 s, plus the new path's own cost. The harness will give the real number before we submit.
- **All instruction figures in `v5-plan.md` are from the old data.** Lines are now about 8% longer, and 1 in 8 IDs takes the long path. Re-count on the new seed-42 before ranking anything by instructions.

**P1 (`pread`) loses its board slot to the long-ID fix.** mmap faults are still expensive under gVisor, so test it **in the gVisor harness, not on the board**: mmap against `pread` on new seed-42, under runsc. It earns a board slot only if the harness shows ≥ 0.1 s. Run these harness checks too, ranked by likely size:
1. mimalloc purging (`madvise` calls). Try `MIMALLOC_PURGE_DELAY=-1` / `mi_option_set` at startup.
2. Anonymous page faults on about 1.9 GB (gVisor gives no THP). Try pre-faulting or reusing buffers.
3. Rayon park/wake futexes at phase barriers.
4. Output `write` sizes.

Every engine change is now gated on **gVisor time** as well as plain-Linux time.

**Correctness traps for the u128 long-ID path (Method):**
- Keys must order byte for byte **across forms**: short-packed against 33-byte against interned. Links name a person by the smallest ID, and click ties go to the smallest `click_id`, so a long ID can sort between two short ones that share a prefix.
- Don't assume the prefix letters, the hex case, or the length. Only an exact 33-byte, lowercase-hex shape takes the fast path; upper-cased variants and every other length fall back to `intern`.
- Test with mixed-form links and with click ties at equal `ts` across forms.
