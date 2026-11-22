# Scorer cost model (Cascade Lake)

Analyst 2, 2026-11-21. Counts are the rebuilds in `verification.md`. Phase splits inside v3 are Eval's, from `evals/results/v3.md`. Phase splits inside v4 are those numbers minus the measured commit deltas, and they are marked as estimates. The totals are measured.

## The rate

v3 `29b64bf` scored **1.9424 s** on the practice board (BB-93D28A6B). Eval's 20M run retired 2,598 instructions per event line. With seed-42's 21,507,843 event lines that is 55.9 G instructions, so the box retired

**28.77 G instructions/s**

during that timed run. `evals/calibration.json` stores 26.75 G/s because it multiplies instructions-per-line by 20e6 instead of 21.51e6. Both formulas give the same board time. They must not be mixed. A 60M prediction uses 28.77 G/s and 64,150,261 event lines.

The M5 Pro retires the same instructions at IPC 3.17, about 4.7 GHz, about 15 G instructions/s per busy core. Eight such cores would be about 120 G/s. The scorer's 28.8 G/s is the whole box. Local wall time (the 3.10× ratio) hides that gap because this machine's 8 threads are not 8 performance cores. Instruction cuts are the metric. Cycle cuts measured here overstate what a memory phase still has to pay on the scorer, and understate a compute phase, because nothing here runs at IPC 1.2.

## The machine

Google's n2-standard-8 is 8 vCPUs of a Cascade Lake Xeon, Gold 6268CL class. Google counts one vCPU as one hyperthread, so this is **4 cores × 2 threads**, not 8 cores. Base clock is 2.8 GHz. All-core turbo on that SKU is quoted up to 3.4 GHz. The calibration picks a point inside that range: 4 cores at about 3.1 GHz retiring 2.3 instructions per cycle between the two threads, which is **1.16 IPC per vCPU**. That is a normal Cascade Lake number for branchy integer code. It is not a memory stall.

Hyperthreads share one core's ports, a halved ROB, and the 1 MiB L2. Cascade Lake's ROB is 224 entries, split to about 112 per thread, and the load and store buffers split the same way. Integer parse should see about **1.15×** from the second thread, not 1.3×: both threads compete for a 4-wide rename and for ports 0 and 5, which is where the SSE2 scan and the bit scans go. A phase that still hits L2 can lose when the second thread doubles the working set. A phase that has already missed L2 gains from the second thread, because the core's line-fill buffers overlap the misses. Dedup at 60M is that second case.

L2 is 1 MiB private per core. L3 is the socket's, about 1.375 MiB per core on Cascade Lake, shared with other tenants on the host. Eight vCPUs do not get a private 38 MiB. A 13 MB working set can still land in L3 when the host is quiet, at about 45–55 cycles, and it falls through to DRAM when the neighbor is busy. DRAM for an 8-vCPU slice is planned here at **30 GB/s**. That number is an assumption, not a measurement.

## Where each phase sits

Eval's v3 counters at 20M, and the v4 head `a019739` after subtracting measured deltas. v4's per-phase split is estimated. The `a019739` total, 1,618 per line at `NCPU=8`, is measured. Flat board seconds price every instruction at 28.77 G/s.

| Phase | v3 instr/line | v3 IPC on M5 | v3 board s | v4 instr/line (est.) | v4 board s | On Cascade Lake |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Events parse | 1,600 | 3.45 | 1.20 | 860 | 0.64 | Compute. SSE2 classify plus scalar decode. IPC per vCPU about 1.3–1.6. HT helps. This is the bulk of the 1.94 s. |
| Sessions | 522 | 3.04 | 0.39 | 400 | 0.30 | Compute at 20M on this Mac. The working set does not fit a 1 MiB L2 (below), so the scorer pays extra cycles the M5 does not. |
| Clicks | 241 | 3.51 | 0.18 | 161 | 0.12 | Same shape as parse, smaller. |
| Parquet | 130 | 3.17 | 0.10 | 130 | 0.10 | Unchanged since v3. Compress and copy. |
| Lookups | 69 | 2.25 | 0.05 | 31 | 0.02 | Pointer chase. M5 cycles/row already ×1.55 at 60M with flat instructions. Price these above the flat rate. |
| Dedup | 35 | 0.77 | 0.03 | 35 | 0.03 | Already missing on the M5 (IPC 0.50 at 60M). Flat instructions, ×1.51 cycles. The flat rate underprices it. |
| **Total** | **2,602** | **3.17** | **1.95** | **1,618** | **1.21** | v4 total is the measured `NCPU=8` count, not the sum of the estimates. |

The v4 estimates assign the measured seed-42 deltas as follows. G1's −664 splits into about −584 on the event scan (the first Analyst's stage bench, 875 → 291) and about −80 on clicks. The category commit's −116 comes out of events parse. G2's −162 splits into about −40 of emit traffic inside parse and −122 inside sessions. Links' −38 comes out of lookups. That assignment is the estimate. The commit totals are not.

Memory phases, costed above the flat rate. Dedup plus lookups are 9% of v3's cycles on the M5 and already stalled. At 20M the 1.7 MB partition misses the 1 MiB L2 and, when the host is quiet, hits L3 rather than DRAM. Doubling the flat price of those two phases adds about **0.05 s** at 20M. It does not move the ranking. Parse does.

At 60M the same tables are 5 MB per partition. Two hyperthreads make that about 10 MB per core, which is past Cascade Lake's L2 STLB (1,536 entries, 6 MB of reach at 4 KB pages) and past a quiet socket's leftover L3. The M5's ×1.5 cycles/row is the gentle version of that cliff: 16 KB pages there keep the TLB small. Without 2 MB pages, dedup at 60M is closer to **×1.8–2.3** cycles per row and lookups **×1.5–1.8**. mimalloc already asks for transparent huge pages, and the Linux v3 run got them. Keep that. Huge pages recover the page walks, not the L2 miss. Partition count is what brings the table back into L2.

## AVX-512 and AVX2

The classifier that runs on the scorer is the SSE2 one in `src/main.rs`: four 16-byte `pcmpeqb` + `pmovmskb` per 64 bytes, for newline, comma, and quote. `target-cpu=cascadelake` can still auto-vectorize other loops with AVX-512. Local amd64 images are built `x86-64-v2` and never execute that.

Replacing the classifier with AVX-512BW is on the order of 30 fewer instructions per 64-byte block, about **0.03 s** at 20M. The frequency licence takes that back. On this SKU class the all-core bins are about:

| Licence | What triggers it | All-core clock |
| --- | --- | --- |
| 0 | SSE2, no AVX | about 3.4 GHz |
| 1 | AVX2, or light AVX-512 (byte compares, shuffles, no 512-bit multiply) | about 3.0–3.1 GHz |
| 2 | 512-bit integer multiply or FP FMA | about 2.5–2.7 GHz |

The licence is hysteresis, not a duty cycle. One 512-bit instruction holds the lower bin for on the order of a millisecond, and a transition into it stalls the core for microseconds. Each vCPU handles a line in well under a microsecond, so a classifier that fires every line pins the lower bin for the whole parse, including the scalar pack and the timestamps. Licence 1 is a 9–12% clock cut against pure SSE2. Licence 2 is about 20%. Either one is larger than the classifier's instruction win.

`target-cpu=cascadelake` may already be emitting AVX2 or AVX-512 in other loops, which would pin Licence 1 for the whole run and make the 3.1 GHz calibration the AVX bin rather than the SSE bin. If the hot functions are actually SSE-only, the same instructions would retire at about 3.4 GHz, roughly 6–8% faster wall time, about 0.12 s at 20M. That is an experiment, not a fact: Eval disassembles the cascadelake binary and reports whether the parse and the session loop contain EVEX (512-bit) opcodes. Method does not add an AVX-512 classifier. If Eval finds 512-bit ops in the hot path, the next trial is compiling that path without AVX-512 and re-counting instructions, to see whether the clock bin is worth more than the vector code.

The scan rewrite the first Analyst described (302 → 70 instructions, line-at-a-time from the comma mask, no per-bit type test) is about **0.17 s** and does not need a new ISA.

## Wait, page cache, container start

**Working assumption: the 141 ms is outside the 1.9424 s.** The UI showed it as its own line. Nothing in `docs/rules.md` defines it. The starter README says build time is not timed and the run is timed.

Two consequences, kept side by side:

| Reading | Rate | Instructions per line for a 0.28 s board |
| --- | ---: | ---: |
| 141 ms outside the score | 28.8 G/s | about 375 |
| 141 ms inside the 1.9424 s | 31.0 G/s on the remaining 1.801 s | about 200, after subtracting 141 ms from 0.28 s |

The outside reading is the one to plan against. A 0.28 s entry that also ate 141 ms of fixed wait would have about 0.14 s of compute, near 110 instructions per line. That is below a scan-plus-decode of this spec. About a dozen teams sit between 0.28 and 0.31 s, which looks like a shared compute floor. The next submission settles it: if "wait" stays near 141 ms while the score moves, it is outside.

Container start is the same shape as that wait. Our own `docker run` on dev costs +0.165 s (`evals/results/v3.md`). That is outside the process. The process timer starts at `main`.

**Page cache is inside the process timer** when the kernel faults the input during the run. It is not the 141 ms line. v3 on Linux, warm, was 0.550 s against 0.626 s native, with 16k minor faults after mimalloc. This Mac is not fault-bound, so the 3.10× ratio is mostly IPC and clock. A cold read of 1.8 GB from the scorer's disk can still be 0.1–0.3 s inside the score. The final takes the median of three runs, so runs two and three are the warm ones. A single practice run can be the cold one. One submission cannot separate that. The 28.8 G/s rate absorbs whatever the scorer did that day. Treat ±0.1 s as the uncertainty on the fixed part, and keep ranking moves by instructions.

## The 60M final

Event lines grow ×2.983 from seed-42 to seed-43 (21.51M → 64.15M). Leaders at 0.28 s are **0.84 s** at 60M if their time scales with event lines. Some of them will have their own cliffs. 0.8–0.9 s is the band to plan against.

| | 20M board | 60M, instructions only | 60M, with the Mac's 6% extra wall |
| --- | ---: | ---: | ---: |
| v3 `29b64bf` | 1.94 s | 5.80 s | 6.1 s |
| v4 `c9e1a0c` | 1.32 s | 3.94 s | 4.2 s |
| v4 head `a019739` | 1.21 s | **3.61 s** | **3.8 s** |

The 6% is Eval's v3 wall ratio (1.970 / 0.624 = ×3.16) divided by the event-line ratio (×2.983). The instruction model misses it because dedup and lookups retire the same instructions and burn more cycles. On Cascade Lake the miss is larger, because the working set already exceeds L2 at 20M:

| Structure | Bytes | Per partition at 256, 20M | At 256, 60M | Partitions so each fits in 1 MiB |
| --- | ---: | ---: | ---: | ---: |
| Dedup (`EidEnt` 16 B + ref 4 B) | 20 B/event | 1.68 MB | 5.0 MB | about 430 at 20M, **about 1,280 at 60M** |
| Row (`Row16`) | 16 B/event | 1.34 MB | 4.0 MB | about 330 at 20M, about 980 at 60M |

Default `SESSIONS_DEBUG_PARTS` is 256. Both structures miss a 1 MiB L2 at 20M already, and they miss by 4–5× at 60M. This Mac's caches hide most of that, which is why the instruction count stays flat while the cycle count does not. Adding the Cascade Lake penalty on top of the Mac's cliff is about **+0.3 to +0.6 s** at 60M for `a019739`, on top of the 3.8 s. Planning number for the current head: **about 4.1 s** at 60M, against about 0.84 s for a linear leader.

What grows faster than the data, from Eval's v3 phase table, and what removes it:

| Phase | Wall 60M / 20M | Instructions | What it is | Who fixes the final |
| --- | ---: | --- | --- | --- |
| Lookups | ×4.00 | flat, cycles/row ×1.55 | Link table misses. Parallelism was 2.9–3.5. | Port is in `a019739` (−38/line at 20M, verified). Eval measures whether parallelism actually rose. The remaining cost is the table missing L2, which is Sol's partition and page-size work. |
| Dedup | ×4.15 | flat (×0.98), cycles/row ×1.51 | Hash table bigger than L2. | **Explorer Sol.** Raise the partition count with input bytes, toward ~1,280 at 60M, so each table fits in 1 MiB. |
| Sessions | ×3.58 | ×1.05, cycles/row ×1.05 | More work per event, plus runs that spill L2. | **Explorer 3** for the kernel (still ~400/line). **Sol** for the same partition scaling, because a person partition is 4 MB at 60M. |

Parse, clicks, and Parquet scale with the data. Cutting them helps 60M by the same factor as 20M. They are still most of the 3.6 s, so the linear cuts remain the way from 4 s to under a second. The partition scaling is what keeps a 0.28 s practice score from becoming a 1.1 s final.

## Moves from `a019739` (1,618/line, 1.21 s board, ~4.1 s final)

One hundred instructions per line is 0.075 s at 20M and 0.223 s at 60M. The final column includes the ×2.98 data growth and not the extra cache penalty, except Sol's row, which is the penalty.

| Move | From → to, instr/line | 20M board | 60M final | Owner |
| --- | --- | ---: | ---: | --- |
| Sessions kernel | 400 → 60 | 0.25 s | 0.76 s | Explorer 3 |
| Scan loop, no per-bit test | 302 → 70 inside parse | 0.17 s | 0.52 s | Explorer 2, after the packer |
| ID packer | ~160 on events | 0.12 s | 0.36 s | Explorer 2, already assigned |
| Probe + emit, drop the `PendEv` copy | the rest of parse above the scan and the pack | ~0.10 s | ~0.30 s | Method |
| Timestamps, straight-line F1 for ingest | ~100 | 0.07 s | 0.22 s | Explorer Sol, after partitions |
| Parquet | 130 → 10 | 0.09 s | 0.27 s | Explorer 3 |
| L2-sized partitions | cycles, not instructions | ~0.05 s | **0.3–0.6 s** | Explorer Sol, first for the final |
| AVX-512 classifier | ~30 instructions, clock licence on the whole parse | about −0.10 s if the licence sticks | worse at 60M | Do not schedule. AVX2 only if the scan rewrite needs it. |

Owned work that is already in the tree, and should not be redone: quote-aware scan (G1, −664/line at 20M), 16 B rows and the counting sort (G2, −162 at 20M), category only for purchases (−116), parallel links (−38). The next parse commit is the scan structure and the packer, measured against `a019739` at 1,618 per line, `NCPU=8`, seed-42.

## Review from Gemini 4 Neon

Asked on a fresh chat, model Gemini 4 Neon, thinking set to High. The brief was the calibration, the six phase IPCs, and four assumptions. Three of its corrections are in the sections above. One of its structural claims is a misread of which machine retired the instructions.

**Kept.**

- The AVX-512 licence is hysteresis, held for about a millisecond after the last 512-bit instruction. A per-line classifier pins the lower bin for the whole parse. The written conclusion (do not add AVX-512 to the scan) matches this. The licence table and the "disassemble the cascadelake binary" experiment came from this review.
- Parse gets about 1.15× from hyperthreading, not 1.25×. Dedup at 60M, once the table is far past L2, gets more from the second thread (about 1.2–1.3×) because misses overlap. The earlier "HT does not help dedup" line was only right for the 20M size, where two threads blow a near-L2 table out to 3.4 MB.
- At 20M a quiet socket serves the L2 miss from L3, about 45–55 cycles, not from DRAM. At 60M, 4 KB pages blow the STLB and the aggregate table blows L3. The ×1.8–2.3 cycle range for dedup, and the note that huge pages fix the walks and not the L2 miss, came from this review.
- The 1.16 IPC per vCPU is a wall-clock average over the whole 1.9424 s, including any idle tail. Busy phases run higher. There is no scorer profile to split them, so the phase table still prices instructions at the average rate.

**Not kept.**

- The review treats 55.9 G as instructions retired on Cascade Lake and 2,597 per line × 20e6 = 51.9 G as the M5 count, and calls the 7.6% gap an ISA difference (spills, kernel instructions, `PAUSE`). Both numbers are the Mac. 2,598 per line times seed-42's 21.51M event lines is 55.9 G. The 51.9 G figure is the same count times 20e6, which is the calibration file's row count, not a second machine. x86 instruction mix is unmeasured. Eval's cascadelake disassembly is the way to see spills and 512-bit ops. It is not evidence that the scorer retires 7.6% more instructions than this Mac.
