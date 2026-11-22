# Packer check, the 60M cliff, and what a 0.84 s final can skip

Analyst 2, 2026-11-21. Binaries rebuilt from `git archive` of each commit, `cargo build --release`, the `sessions` unit deleted first so a shared target directory could not keep the previous binary. `a019739` came out byte-identical to the binary verified in `verification.md` (`84a98cbb…`). `20b8e79` is a different hash (`b7664eb1…`). Phase counts are `proc_pid_rusage` at each stderr mark, the same counters as `/usr/bin/time -l`.

## The packer claim holds

Method, `20b8e79`: dev, one thread, lap instructions divided by that file's line count, events 915 → 825 and clicks 763 → 669.

Steady run (the second; the first is within 2):

| | Events, per event line | Clicks, per click line |
| --- | ---: | ---: |
| `a019739` | 912 | 762 |
| `20b8e79` | **825** | **668** |
| Method | 915 → 825 | 763 → 669 |
| Measured step | **−87** | **−94** |
| Method's step | −90 | −94 |

The endpoints sit 3 under Method's. That is the run-to-run noise on this counter. The steps match. Eight threads, same step, at both sizes:

| | Events / event line | Clicks / click line | All phases / event line |
| --- | ---: | ---: | ---: |
| 20M `a019739` | 914 | 741 | 1,625 |
| 20M `20b8e79` | 825 | 647 | **1,511** |
| 60M `a019739`, warm | 910 | 733 | 1,597 |
| 60M `20b8e79`, warm | 819 | 641 | **1,478** |

The saving does not shrink with size: about −90 per event line and −93 per click line at 20M and at 60M. In event-line units the click saving is another −23, so the whole pipeline drops **−114 per event line at 20M** and **−119 at 60M**. Sessions, dedup, and Parquet do not move.

Predicted practice board, same formula as `verification.md`: **1.13 s** for `20b8e79`, against 1.21 s for `a019739`. About 0.08 s. At 60M, instructions only, **3.30 s** against 3.56 s. The first Analyst's "160 per event line" was the events-only target; the measured cut is 90 there plus 93 on each click.

One trap. The first 60M run of `a019739` was a cold page cache and reported 1,077 instructions per event line in the parse, against 910 once the files were resident. Fault work inside the process was landing in the parse phase. The packer did not get cheaper on a warm cache. A 60M instruction count is only comparable after the input has been read once.

## Where 60M costs more per line

v3's wall ratios, from `evals/results/v3.md`: dedup ×4.15, sessions ×3.58, lookups ×4.00, against event lines ×2.983. Those are wall times on the old pipeline. On `20b8e79`, eight threads, warm cache, per event line:

| Phase | Instr 20M | Instr 60M | Instr ratio | Cycles 20M | Cycles 60M | Cycle ratio | What grew |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Lookups | 26.6 | 23.2 | 0.87 | 29.7 | 27.8 | 0.93 | nothing |
| Events parse | 825 | 819 | 0.99 | 315 | 289 | 0.92 | nothing |
| Clicks parse | 155 | 152 | 0.98 | 59.0 | 55.4 | 0.94 | nothing |
| **Dedup** | **35.8** | **35.1** | **0.98** | **52.6** | **74.7** | **1.42** | **cycles, not instructions** |
| Sessions | 331 | 324 | 0.98 | 147 | 138 | 0.93 | nothing |
| Parquet | 131 | 119 | 0.91 | 44.5 | 34.7 | 0.78 | nothing, it gets cheaper |

Dedup is the only phase that costs more per line at 60M. Instructions stay flat (the hash work does not grow). Cycles per line rise ×1.42 and IPC falls from 0.68 to 0.47. That is the cache and TLB, not extra algorithm work. Times the ×2.983 data growth, dedup's wall is about ×4.2, the same multiplier v3 showed. The other two v3 multipliers do not survive this code. Sessions and lookups are slightly cheaper per line at 60M than at 20M, so their wall should track the data, a bit under ×3. Parallel links and the 16 B counting sort removed the sessions and link cliffs on this machine. They did not remove the dedup cliff.

Total cycles grew ×2.84 while event lines grew ×2.98. The dedup premium is real and it is a small share of the run: about 1.4 billion extra cycles on this Mac, a few hundredths of a second here, and more on a 1 MiB L2 where the 5 MB partition already misses. It is not a second full pass.

## Huge pages

mimalloc 0.1, the global allocator in `src/main.rs`, does two different things:

- `mi_option_allow_thp` defaults to **1** (0 only on Android). While it is on, mimalloc does not `prctl` THP off for the process, and on large aligned allocations it calls `madvise(MADV_HUGEPAGE)`. That is a request. The kernel grants a 2 MB page only when transparent huge pages are `madvise` or `always`.
- `mi_option_allow_large_os_pages` defaults to **0**. We do not `mmap` `MAP_HUGETLB`. There is no hugetlb pool to ask for, and the scorer is unlikely to have one for uid 1000. The bake-off's explicit large-page switch did not pay.

Eval's Linux runs showed the madvise path working: about 1,000 THP allocations and the anonymous fault count collapsing. That was our container, with THP set to `madvise`.

The scorer is a GCE n2 host running our container. THP is a host setting the container cannot turn on. Ubuntu and Container-Optimized OS images on GCE ship it as `madvise`, which is exactly the mode `MADV_HUGEPAGE` needs. That is likely, not confirmed. If their sysfs says `never`, every advise is a no-op and we stay on 4 KB pages.

What a granted 2 MB page fixes is the TLB walk on **anonymous** memory: the dedup table, the link table, the session rows, the output buffers. It does not fix an L2 capacity miss, and it does not cover the input, which is a file mapping. Parse and clicks are already flat in both instructions and cycles, so huge pages do nothing measurable there. Dedup is the phase they touch. Gemini's earlier note, kept in `scorer-model.md`, was that huge pages recover about a third of a 60M TLB regression and leave the L2 miss. Partition count is still what brings a 5 MB dedup table back under 1 MiB. **Explorer Sol** owns that. **Method** should leave the allocator on the default; do not flip `allow_large_os_pages` on the strength of the bake-off.

## What Gemini thinks a 0.84 s final looks like

Gemini 4 Neon, High. The brief gave it the spec's obligations, our phase costs, and both rates: 28.8 G instructions/s (about 380 per line for 0.84 s) and the 8 G/s rate that would make 100 per line enough. It rejected 100 per line for a correct pipeline. The reachable band it gave is **280–350 per line at our measured rate**, which is 0.62–0.78 s of compute inside 0.84 s. That matches the budget in `scorer-model.md`. Its phase targets: parse 95–130, sessions 35–60, clicks 15–30, dedup 15–25, Parquet 30–75.

Checked against `docs/rules.md`. Kept only what the spec allows.

**Legal, and already the shape of the pipeline.** Transitive union-find. Quote handling with a fast path and an exact fallback. A packed integer row and a counting sort by person. Category only where a purchase reads it. Aggregated Parquet, not one row per event: `user_daily` is one row per person per day, `campaign_daily` likewise, and any integer width and any string encoding is accepted. Uncompressed or LZ4 Parquet is legal. The spec does not name a codec, so "drop compression" is not dropping an output.

**Illegal, and it said so in the caveats. Do not build these.**

- Dedup inside the person partition. Dedup is step 2 and validation is step 3: the kept copy is the one with the smallest `ingest_ts`, and if that copy is invalid the event is gone. About 1 in 64 duplicated events name a different user (`docs/rules.md`, the dirt table). Those two copies are different people until the ingest time picks one. Scattering by person first keeps both, or keeps the wrong one.
- Dropping invalid rows in the scan, before that dedup. Malformed lines (wrong fields, bad quotes, empty `event_id`) are dropped at parse. A bad timestamp, a bad type, an empty user, or a late event is dropped only on the copy dedup kept.
- A 64-bit hash standing in for an ID. IDs compare as bytes. The person is named by the byte-wise smallest ID, and a tied click is named by the byte-wise smallest `click_id`. A hash collides, and it does not order.
- A 4-byte timestamp in seconds. The gap is 1,800,000 ms, and F3 is epoch milliseconds. A u32 millisecond offset from the window fits, which is what `Row16` already stores. Seconds do not.
- First-seen dedup. Copies are not ordered; the smallest `ingest_ts` wins.
- Bloom-filter dedup, one click per user, or dropping assists. Assists are every qualifying campaign in the 7 days, once each, including the credited click.

**Wrong about this dataset, so it would not pay.** An unquoted-only SIMD fast path. The generator quotes 20% of fields, and the first Analyst measured a quote on 79% of event lines. v3's fast path already lost on that rule; v4's quote-aware path is the one that matches the spec. The spec also says no value contains a comma or a quote, so a general RFC-4180 unescape is more parser than the checker will ever feed.

Its instruction budget is the right target shape if the illegal dedup move is replaced by the global dedup we already have, sized to L2. Parse toward 100, sessions toward 60, and Parquet toward 40, on top of the packer that just landed, is how 1,511 becomes about 350. Nobody gets to skip a phase. The phases get smaller.
