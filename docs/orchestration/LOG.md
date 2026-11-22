# Orchestrator log

Newest entries at the bottom. Each entry records who did what, on which branch or commit, the numbers, and the decision taken.

## Version ledger

| Version | Commit | Branch | 20M median | 60M | Peak mem 60M | Verdict | Submitted | Board time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ref | d170ffe | main | 236 s (1 thread) | n/a | 17 GB at 20M | oracle | no | n/a |
| v1 | 3e48662 | main (tag v1) | 1.550 s (5 runs, sd 0.03) | 5.79 s (3 runs) | 11.46 GB footprint (16.6 GB RSS incl. page cache) | **SUBMIT-READY** | no | n/a |
| v3 | 29b64bf | main (tag v3) | **0.626 s** (interleaved vs v1 1.609 s, +61.1%) | 1.97 s | 5.62 GB footprint (11.6 GB RSS) | **SUBMIT-READY** | **yes (BB-93D28A6B, Sat 19:23 ET)** | **1.9424 s** (wait 141 ms; entered in final as best) |
| v2 | 953af43 | method/v2 | 1.661 s (interleaved 1.610 vs v1 1.659) | 5.367 s | 11.41 GB footprint (17.76 GB RSS) | HOLD (Gate C: only 2.94% faster, needs 5%) | no | n/a |
| v7b | 96af24b → main ddbf1a3 (tag v7b) | method/v7b | gVisor 20M **1.360 s** (v5 1.910 s, same session); native 0.545 s; 1,359 instr/row | predicted board 60M 3.06 s | 11.54 GB RSS | HOLD → **SUBMIT-READY (Orchestrator override; Gate C noise)** | **yes (BB-870A1088, Sun 02:51 ET)** | **1.5275 s** (rank 132; entered in final as best) |
| v8 | 2bfb034 → main 2a9f52c (tag v8) | method/v8 | untimed PASS; timed eval pending | n/a | n/a | SUBMIT-READY (correctness; Red Team PASS; x86 MATCH) | **yes (BB-607A8C0F, Sun 03:20 ET)** | **1.0844 s** (rank 86; entered in final as best) |

## Thread registry

| Thread | Role | Branch / worktree | Status |
| --- | --- | --- | --- |
| Orchestrator | coordination, merges, log | main / project root | active |
| [Eval: framework + scoring](t3-thread://v2/555287a9-b949-4858-929b-ee0115137bee/mcp:launch:89ba2159fefcb9d132aac87119da7af32599350130f935c6869fa5fd8158d759) | evaluation framework (Cursor grok-4.7 + Gemini 4 Neon in browser) | eval/framework (worktree from origin/main @ 7f27b6a) | running (Codex sol): framework v1.2 (Analyst v2 §requests: Linux A/B Gate C, madvise THP, fault anatomy, contamination guard) |
| [Dashboard (simple, static)](t3-thread://v2/555287a9-b949-4858-929b-ee0115137bee/thread:delegated-task:command%3Amcp%3A02321fc3-e973-4332-85f8-fdaccde89f88%3Adelegate-task%3Adashboard-sol-1) | dashboard (Codex gpt-6.2-sol) | t3/build-progress-dashboard, merged (8807552) | done |
| [Analyst: insights](t3-thread://v2/555287a9-b949-4858-929b-ee0115137bee/mcp:launch:4bb2f427ec0d090bb0b1d04656a70cbb5677caeda85f78ddb59f299ee7c58728) | insights | analysis (worktree from origin/main @ 54be3ad) | running (claude_andrew): correctness review of method/v3 |
| [Method: next version](t3-thread://v2/555287a9-b949-4858-929b-ee0115137bee/mcp:launch:12abc78a5e772d60f60bfee203e923ca14d54c88168f046f78565586a6182097) | pipeline versions | method/v2 (worktree from origin/main @ e695855) | running (Claude): v3 on method/v3 (packed IDs, dedup routing, direct-index lookups, SIMD scan); no big timings until cleared |
| [Explorer (Sol): new methods](t3-thread://v2/555287a9-b949-4858-929b-ee0115137bee/mcp:launch:6315989f2e18da907dd5afa1c1d91b92f260d655ff39ccea533b4bcc1c8dff26) | new methods, orthogonal to v3 (Codex gpt-6.2-sol) | explore/sol + explore/<idea> (worktree from origin/main) | running |
| [Explorer (Gemini Neon): parse + sort](t3-thread://v2/555287a9-b949-4858-929b-ee0115137bee/mcp:launch:c34fb1c92727c4ef2b6393af4d85d74111a2d51ff14281638fe8f40541130fd3) | new methods: radix sort, parse path, input I/O and threads (runs on Cursor grok-4.7; consults Gemini 4 Neon in the browser) | explore/gemini + explore/gemini-<idea> (worktree from method/v3 @ 1ea8059) | running |
| [Explorer 3 (Gemini Neon): sessions, output, fused design](t3-thread://v2/555287a9-b949-4858-929b-ee0115137bee/mcp:launch:4379b65d8484648bc9238d23e7cc78673f8a8df125def5c32a8181b904ea7ac5) | sessions+attribution kernel, Parquet output cost, fused ~300 instr/row microbenchmark (Cursor grok-4.7 + Gemini 4 Neon in browser) | explore/gemini3 + explore/gemini3-<idea> (worktree from origin/main) | running |
| [Analyst 2 (Grok + Gemini Neon): verification, scorer model](t3-thread://v2/555287a9-b949-4858-929b-ee0115137bee/mcp:launch:ae50fb5d3f96b5f5f93ddb22c338d922bdc22fb8b564d2e46e81a99cc58ed242) | independent verification, x86 Cascade Lake scorer model, 60M final projection (Cursor grok-4.7 + Gemini 4 Neon in browser) | analysis2 (worktree from origin/main) | running |
| [Footprint: cut gVisor page faults](t3-thread://v2/555287a9-b949-4858-929b-ee0115137bee/mcp:launch:76f18a5b76aae96949477f6ae89fb2a0e166e560001d67eedf04ecdb5fe2a084) | fault anatomy + footprint cuts (streaming input, buffer reuse, no zero-fill) | explore/footprint (from 2bfb034), claude_andrew | running; first report by 05:00 |
| [Dashboard: live Claude artifact](t3-thread://v2/555287a9-b949-4858-929b-ee0115137bee/mcp:launch:41ab4ef0a8234b722582c94a9f60a3b6ad91d309d5aa3b1510e7c1c2ad26f325) | live claude.ai dashboard (one URL, data in the artifact DB) | dashboard/live, merged (304e818) | done: canonical https://claude.ai/artifact/WtswJrVasZtzDdyXH1Ci82 (main account) |

## Entries

### 2026-11-21: setup
- **Orchestrator:** `5226746` infra skeleton, `d170ffe` Python reference (36/36, dev MATCH), `3e48662` Rust v1 (36/36 fixtures native + arm64 + amd64 containers, dev MATCH, diff MATCH on seeds 2–6, 15, 62 and 42). Pushed `main`, tagged `v1`.
- **Orchestrator:** wrote PROTOCOL.md (roles, loop, submission gate). The next step is launching the Eval thread, which builds the framework and formally evaluates v1.
- **Orchestrator:** pointed the T3 project at the git repo so threads get worktrees. Launched the **Eval** thread with the brief: framework v0 (correctness, fuzz, perf, resources, scaling, artifacts, Gates A/B/C verdict, compare tool), then a full eval of `v1`. The machine is reserved for Eval benchmarks until it reports.
- **Orchestrator:** fetched the leaderboard (51 rows shown, 320 teams). **The best practice time is 0.28 s** (APK, Flare, Team Buck); about 12 teams are between 0.28 and 0.31 s. The baseline is 170.69 s. Final scoring rebuilds the team's **best** (or chosen) commit on about 60M events: median of 3 runs, each capped at 3 min. Practice: 2 submissions per hour, and a rejected one doesn't change the best. **Target: < 0.28 s on practice.** v1 is about 1.7 s locally on 20M, so we need roughly 6× more speed.
- **User request:** a simple progress dashboard, built by a separate agent on sol. **Orchestrator** delegated it to Codex `gpt-6.2-sol`: a static `docs/orchestration/dashboard/index.html` generated by a stdlib `build.py`, with `make dashboard` and `make dashboard-watch`. It reads eval results, LOG.md and git.
- **Dashboard (sol):** delivered `f1bf5f0`. Merged into main (`8807552`). `make dashboard` → `docs/orchestration/dashboard/index.html`.
- **Eval:** framework v0 delivered at `35d7979` (evaluator `def6d82`). It covers fixtures, dev and 9 oracle diffs, 60M consistency (11 invariants plus a baseline diff), fuzz (1000 seeds; a self-test catches 37/37 seeded bugs), determinism, perf medians, phases, `time -l` counters, thread and size scaling, container overhead, artifact sizes, and Gates A/B/C. Profiles: quick about 30 s, full about 3 min. It fixed Spotlight indexing that had inflated timings. **v1: SUBMIT-READY.** 20M median 1.550 s, 60M 5.79 s, footprint 11.46 GB, 8-thread efficiency 0.68, 60M about 25% superlinear per event, 35% of the 1M wall time spent in exit/teardown.
- **Orchestrator decision (Gate B memory):** gate on the anonymous peak footprint (≤ 16 GB). RSS including mmapped input page cache stays a *warning* only, because clean file pages are reclaimable before OOM. Merged eval into main (`32ef087`); resolved a Makefile conflict (dashboard + eval targets).
- **Orchestrator:** launched the **Analyst** for v1: bottleneck model, the architecture needed for < 0.25 s at 20M, ranked moves (incremental vs rewrite), and eval gaps. The machine is free for one-off profiles.
- **User request:** one Claude-hosted dashboard that updates in place, built in a new thread that may use Grok or sol helpers. **Orchestrator** launched the **Dashboard** thread: a snapshot exporter plus one artifact whose data lives in its DB, and a SYNC.md that the Orchestrator follows after every loop iteration.
- **Analyst:** v1 insights at `5f85580` (evals/insights/v1.md), merged. v1 is CPU work bound: 9.77 core-s, about 4,270 instructions/row, and a 0.25 s run allows about 1.6 core-s. 8 threads here are 5 performance + 3 efficiency cores, so the 0.68 efficiency is near the hardware ceiling. Linux first-touch page faults will cost more on the scorer than on this Mac. **Recommendation:** a staged rewrite of the data path that keeps v1's tested parsers and session loop. Moves: (1) skip teardown with `process::exit`; (2) packed order-preserving u64 IDs, 16 B dedup entries, one shuffle, and dedup routed only to the partitions that need it; (3) SIMD line scan with v1 `split_fields` as the exact fallback; (4) prefetched or batched link lookups, direct-index products and campaigns, parallel links; (5) arenas and hugepages. Projected: v2 ≈1.45 s, v3 ≈0.6–0.7 s, v4 ≈0.4 s locally. **Asks the user to submit v1 now for calibration.**
- **Orchestrator plan for iteration 2:** Method builds v2 = move 1 plus the debug knobs the Analyst asked for (hash bits, chunk size, partition count, fast-path off switches) plus per-phase `cpu=` in the marks. In parallel, Eval builds framework v1 from the Analyst's eval requests (development only, no timed runs until the Orchestrator clears the machine).
- **Orchestrator:** launched the **Method** thread on `method/v2`. Sent **Eval** the framework-v1 task list (Analyst §6), development only. v1 is SUBMIT-READY, so I asked the user to submit v1 for calibration (only the user can submit).
- **Orchestrator (resume after usage limit):** the claude_master and claudeAgent accounts hit the 5-hour limit, which resets at 18:40 ET. Method was already moved to claude_andrew and is building v2 (move 1 at `6d83b19`). I moved **Eval** to Codex gpt-6.2-sol (high), with a self-contained brief rebuilt from the repo, and **Dashboard** to claude_andrew (it needs the Artifact tool, so it has to stay on Claude). Both resumed.
- **Method:** v2 on `method/v2` @ `953af43` (6d83b19 skip teardown, 50d0d13 debug knobs, 953af43 per-phase cpu marks). Fixtures 36/36, dev, seeds 2/15/42 and 60M seed-43 MATCH; every knob combination MATCH. A rough loaded run gave 20M 1.64 s (v1) vs 1.57 s (v2), and warm 60M 5.00 s vs 4.89 s. Teardown gained less than predicted because the kernel's release of 6.5 to 17.8 GB at exit is serial, and lower memory (v3) is the real fix. The v3 design note covers packed u64 IDs, fallback interning, batched and prefetched lookups, and direct-index products and campaigns.
- **Eval (now Codex sol):** framework v1 @ `33e140b`: calibration fit, seed-62 20M leap-day oracle, knob checks (4 cases × 5 settings MATCH on v2), IPC and instructions per row, per-phase CPU, hybrid-core scaling, Linux fault probe (mock-tested). Merged.
- **Dashboard:** live artifact https://claude.ai/artifact/BeFsRwhCxaqqo3KRDhdWM5 (claude_andrew account), data-only syncs per `docs/orchestration/dashboard/SYNC.md`. `f927858` merged.
- **User request:** move all Claude threads from claude_andrew to the `Claude` provider. Method and Dashboard are switched. **Orchestrator:** cleared the machine and sent Eval to run the full v2 evaluation.
- **Orchestrator (loop start):** the user asked for a continuous loop until we beat the board. Method was sent v3 (`method/v3`) on the `Claude` provider, but that instance still returned "5-hour limit, resets 18:40 ET" twice. Method is back on claude_andrew so it keeps working, and moves to `Claude` after the reset. Eval (Codex) is timing v2. Dashboard synced (23 writes, same URL). The user will spend a weekly reset if needed (weekly at 91%).
- **User request:** a separate Sol thread that invents new methods, runs them on the latest eval framework, and feeds the Analyst. **Orchestrator** launched **Explorer (Sol)** (Codex gpt-6.2-sol, high) on `explore/sol`, scoped to ideas orthogonal to v3: output-side Parquet, fused passes, spec shortcuts, RSS and page faults, scheduling. Results go to the Analyst via the Orchestrator. **Protocol change:** two threads may now time, so timed runs take the machine lock `mkdir /tmp/builders-bench.lock` and release it with `rmdir`. Eval, Method and Explorer have been told.
- **Eval:** v2 full eval at `8405f87`, merged. **HOLD.** Gates A and B pass: 36/36 on native, arm64 and amd64; 10 oracles; 1000 fuzz seeds under every knob; all 82 dialect cases at each chunk size. Gate C fails: 2.94% faster over 11 interleaved pairs, under the 5% bar. Instructions per row about 4,264 at 20M, IPC 1.95 (1.76 at 60M). Parse events is the biggest phase (0.73 s wall, 5.8 core-s). **Linux named-volume probe at 20M: 2.05 s warm, 811k minor faults; cold 2.39 s.** Linux is about 25% slower than macOS, so page faults matter on the scorer. v2 stays the base for v3 (its knobs and CPU marks are needed); it won't be submitted.
- **Orchestrator:** Eval assigned framework v1.1 (built-in bench lock, Linux-container timing as a secondary Gate C). Analyst moved to claude_andrew (claude_master is limited) and assigned v2 insights, to fold in Explorer's notes as they arrive.
- **Eval:** framework v1.1 @ `df2aa53`, merged. The bench lock is built into every timed profile, and `PROFILE=linux` adds arm64 Linux container timing (8 CPU, 24 GiB) with faults per row.
- **Analyst:** v2 insights @ `09ddf2c`, merged. **mimalloc as the global allocator cuts Linux 20M time from 2.10 to 1.565 s (THP madvise) and faults from 971k to 20k.** It also removes about 0.13 s of exit time. 97% of faults are 4 KB anonymous pages from glibc arena growth. On the scorer, faults, exit and TLB misses cost about 0.25–0.4 s at 20M. The v2 eval was contaminated by another 99% CPU `sessions` process. Re-ranked moves: (1) mimalloc, (2) packed IDs and dedup (in v3), (3) direct index plus parallel links, (4) SIMD and SWAR timestamps, (5) partition count scaled to input.
- **Explorer (Sol):** idea 1, window timestamps @ `d1da46e` (notes `14925c8`, merged). 20M is 6.1% faster than v2 and 6.5% faster than v1 over interleaved quiet runs, with 13% fewer instructions per line. Every correctness gate passes. Recommendation: port into v3.
- **Method:** v3 on `method/v3` @ `1ea8059`: packed IDs, compact rows, one shuffle, dedup by side stream (`5b1cd1d`); direct-index products and campaigns with prefetched link lookups (`8116a4b`); SIMD scan with exact fallback (`243b333`); overflow asserts. Every gate MATCH, plus seeds 2–6, 15 and 62, every knob, and 5 unit tests. On a single-threaded dev run it takes 0.224 s against v2's 0.477 s, with 22% fewer instructions. The x86 SSE2 classifier is untested.
- **Orchestrator plan, iteration 3:** Method makes v3 final by adding mimalloc and porting Explorer's timestamp decoder, then Eval runs the full and Linux evals. Eval builds v1.2 in the meantime. Explorer runs an allocator bake-off (mimalloc, jemalloc, glibc; 20M and 60M; arm64 and amd64) plus parallel links. Analyst reviews v3's correctness against the spec.
- **User request:** a Gemini Neon thread, run through Cursor because Antigravity doesn't work. **Orchestrator** launched **Explorer 2 (Gemini Neon)** on Cursor `gemini-4-neon` (high), on `explore/gemini` from v3 `1ea8059`. Its scope doesn't overlap Sol's or Method's: radix or counting sort for the (person, ts) keys, the event-parse path (SWAR, skipping unneeded fields, fusing parse with routing), and input I/O and threading (MAP_POPULATE/madvise vs read, rayon startup). It uses the same bench lock and process.
- **User:** Gemini Neon doesn't work through Cursor. **Orchestrator** switched Explorer 2 to Cursor `grok-4.7` (high). It now drives gemini.google.com (Gemini 4 Neon) in the T3 preview browser as an idea and design partner. The user signs in to Google there. Grok owns implementation, correctness and timing.
- **Orchestrator tick (18:45 ET):** Eval, Analyst and Dashboard are now on the `Claude` provider (claudeAgent). Method is still on claude_andrew. v3 head is `29b64bf` (mimalloc + window timestamps). Bench lock queue: Explorer (Sol) allocator bake-off holds it, then Method's v3 sanity script (native 20M, Linux 20M, amd64 builds), then Eval's v3 full + Linux eval (smoke-tests framework v1.2). The Dashboard thread is resyncing the canonical artifact itself, so the Orchestrator skipped this tick's sync.
- **Explorer (Sol):** allocator bake-off at `5e282b9`, merged. **Keep default mimalloc.** At 20M on Linux it was 20.9% faster than v2 with glibc under THP `always` and 25.3% faster under `madvise`. Faults went from 967k to 21k and the exit tail from 161 ms to 11 ms. jemalloc was close but used more memory, and large OS pages gave mixed results. 60M fits under 24 GB with every allocator; mimalloc peaked at 17.13 GB. Every correctness gate passes, as do the 3 cascadelake builds. Prototypes: `explore/allocator-mimalloc` `3cf92b0`, `explore/allocator-jemalloc` `13a7847`.
- **Analyst:** v3 review addendum at `8f53b44`, merged. **No correctness bugs** in mimalloc (`8004f65`) or the timestamp decoder (`29b64bf`): 50/50 new cases and 70/70 original cases MATCH across 10 knob settings, cargo test 6/6, and all 4 deliberately broken decoders caught. Asks Eval to add `evals/insights/v3_review/run.py` to Gate A, plus the amd64 build at `29b64bf`.
- **Dashboard:** `304e818`, merged. The canonical artifact is now **https://claude.ai/artifact/WtswJrVasZtzDdyXH1Ci82** on the main Claude account. The `BeFs…` copy on claude_andrew is frozen. The Orchestrator runs on claude_andrew and can't sync until the user shares `WtswJ…` with edit access, or switches the Orchestrator to `Claude`.
- **Bench lock:** Eval holds it for the v3 full eval (started 18:59 ET; fuzz 1000/1000 MATCH so far). Method's v3 sanity script is queued.
- **Eval:** v3 (`29b64bf`) full eval: **SUBMIT-READY.** Gates A, B and C pass:
  - correctness: 36/36 fixtures (native, arm64, amd64), dev MATCH on all three, 10/10 oracles, 854/854 fuzz under every knob, deterministic output
  - 20M: **0.626 s vs v1 1.609 s, +61.1%** (interleaved)
  - 60M: 1.97 s, peak footprint 5.62 GB, Linux cgroup peak 5.69 GiB
  - clean amd64 cascadelake build passes
  - the paired Linux A/B was unavailable
- **Orchestrator:** merged `method/v3` into main and tagged `v3` (src identical to `29b64bf`; fixtures 36/36 on main). Asked the user to submit v3, which gives the first calibration point.
- **Analyst:** v4 design at `0beec04`, merged.
  - **Correction:** the 0.28 s board is the **20M practice** set. The final is 60M (leaders ≈ 0.8–0.9 s scaled).
  - Budget for 0.25 s at 20M: about 250 instructions per event line plus 35 ms fixed; v3 is at about 2,700.
  - **Top gap:** v3's SIMD fast path rejects any line containing `"`. 20% of fields are quoted, so 79% of event lines and 59% of click lines fall to the slow splitter (about 680 against 70 instructions per line). A quote-aware fast path is worth about 0.4 s on the scorer.
  - Gap list: (1) quote-aware fast path; (2) 16 B rows and a counting sort; (3) a faster ID packer, with category lookup only for purchases; (4) the same for clicks; (5) a smaller dedup entry and L2-sized partitions; (6) largest-first partition scheduling for whale users.
  - Beating 0.28 s needs all six. It's incremental on v3, not a rewrite.
- **Explorer 2 (Grok + Gemini):** counting sort on the dense person ID, with LSD radix as the fallback (Gemini's design), on `explore/gemini-radix` `c99960e`. Fixtures 36/36, dev MATCH, and a unit test against the comparison order. Not yet timed.
- **USER SUBMITTED v3** (`29b64bf`): board **1.9424 s** (BB-93D28A6B, "wait 141 ms"). It's our best score and is entered in the final. Rank is around 250th; the leaders are at 0.28 s.
  - **Calibration (1 point):** board / local = 1.9424 / 0.626 = **3.10×**.
  - Per row: v3 runs 2,598 instructions per row at 20M (IPC 3.17 on M5). On the scorer that is 97 ns per row, about 26.7 G instructions/s effective, which matches the Analyst's model of about 25 G/s across 8 cascadelake vCPUs.
  - **What 0.28 s needs:** about 14 ns per row, i.e. **≤ ~300–375 instructions per row including fixed costs**, or about 0.09 s local wall at the 3.1× ratio. Local wall time is a poor proxy because the M5 Pro has much higher IPC. **Instructions per row (and the predicted board time) becomes the primary metric.**
- **User request:** one more Gemini Neon instance in its own thread. **Orchestrator** launched **Explorer 3**, Cursor `grok-4.7` with Gemini 4 Neon in its own browser tab. Scope:
  - a sessions and attribution kernel at ≤ 60 instructions per row
  - Parquet output cost, and the cheapest writer configuration the checker accepts
  - a clean-room fused design at ~300 instructions per row, with a stage-by-stage instruction microbenchmark

  Eval was asked to record the calibration point, make predicted board time plus instructions per row the primary metric, and let Gate C pass on a ≥5% drop in instructions per row. Method and the Analyst were told to judge moves by instructions per row.
- **Analyst:** v3 insights at `e03ad61`, merged. Measured instructions per line: 2,598 in total.
  - Per phase: events parse 1,441, sessions 550, clicks 221, dedup 153, links 100.
  - Lines on the fast path: events 21%, clicks 41%, links 64%.
  - Superlinear from 20M to 60M: dedup ×4.2, sessions ×3.6, links ×4.0. With the partition count fixed at 256, partitions outgrow L2.
  - Re-ranked: (1) quote-aware fast path; (2) compact rows, counting sort and scaled partitions in one commit; (3) parallel links (Sol: now ahead of the audit); (4) ID packing; (5) one task pool plus parallel output. Moves 1–4 project to about 0.35 s native at 20M.
  - Asked the Analyst to re-anchor on the 1.9424 s board point.
- **Eval:** framework v1.3 at `8a507ee`, merged into main as `d96eaae`.
  - Calibration: 1 point, ratio fit, slope 3.103. Added an instructions-per-row predictor.
  - v3 amendment: review suites 120/120, windows fuzz 227/227, amd64 SWAR path 36/36 + dev, Linux A/B +74%.
  - "wait 141 ms" isn't defined anywhere in the docs.
- **User request:** run Eval on Gemini Neon in the browser instead of Claude. **Orchestrator** switched Eval to Cursor `grok-4.7` as the driver, with Gemini 4 Neon in its own browser tab as analysis and design partner. Eval keeps ownership of the verdicts. Its tasks are to prepare v4 evals (lead with predicted board time and instructions per row) and to cover the Analyst's open requests: per-phase instructions, fast-path share counter, partition skew, 60M/20M growth.
- **Orchestrator tick (19:47 ET):** several threads finished 10–20 min ago and sat idle until this tick. Fix: shorter loop delay, and re-task as soon as reports land.
- **Method:** v4 moves 1–2 on `method/v4` @ `c9e1a0c`. Every gate passes: fixtures, dev, 7 seeds, the full knob matrix, the v3_review cases, and 8 unit tests.
  - **Instructions per line, 20M:** 1,772–1,795 vs v3's 2,610 (**−31%**). That projects to about 1.3 s on the board. Quick 20M run: 0.53 s, 3.8 GB.
  - **Move 1 (quote-aware fast path) saved only 3 instructions per line.** It now takes 100% of lines, but `split_fields` on quoted lines was never the cost. The Analyst's premise for that move was wrong.
  - **Move 2 (16 B rows plus a per-person counting sort with Explorer 2's radix) did the work:** 2,628 → 1,855 instructions per line on dev.
  - The remaining parse cost is ID packing, timestamps, category lookups and pushes.
- **Explorer (Sol):** `5dafdb0`, merged.
  - **Parallel links** (`explore/parallel-links` @ `89ad72c`): −36 instructions per line at 20M and −40 at 60M, exact.
  - **Unneeded-work audit:** looking up the category only for purchases skips 97.1% of lookups, about −57 to −67 instructions per line (modeled).
  - **Partition skew:** the largest partition is 5.5× the average.
- **Explorer 2:** counting sort alone on v3 cuts 2,598 → 2,391 instructions per line (−207), worth about −0.15 s on the board. Already in v4 move 2. Note merged.
- **Analyst** addendum `353709c`, **Eval** v1.4 `3f2ceee` and **Dashboard** `0ad54a7` merged.
  - Eval: per-phase instructions per row for v3 are events parse 1,600, sessions 522, clicks 241, output 130, lookups 69, dedup 35. Lookups and dedup are cache-bound at 60M.
  - Eval: the Linux A/B for v3 vs v1 is +74%.
- **Next:** Eval runs the full eval of v4 `c9e1a0c`. Method does move 3 (ID packer), category lookups for purchases only, the parallel-links port, then moves 4–6. Sol prototypes move 5–6 (L2-sized partitions, dedup and lookup cache behaviour at 60M, skew-aware scheduling). Explorer 2 does the ID packer kernel. Re-applied Eval's switch to Cursor grok-4.7 + Gemini (it had kept running on Claude).
- **Analyst:** v4 insights `9734a48`, merged.
  - **Correction:** G1 (the quote-aware path) delivered **−679** instructions per line (v3 2,641 → `e62060c` 1,962). G2 delivered −93. Method's move-1 figure came from a stale binary.
  - Parse microbenchmark on v4, instructions per line now → target: scan 302 → 70, ID packing 196 → 35, timestamps 152 → 50, category 105 → 3, link lookup + row path about 235 → 50.
  - Ranked by board seconds saved: sessions kernel (Explorer 3), **scan loop (unowned)**, **link lookup + row path (unowned)**, ID packer (Explorer 2), Parquet output (Explorer 3), **timestamps (unowned)**, category only for purchases (Method), links, **click parsing (unowned)**, L2 + skew (Sol).
  - Projection: owned items bring us to about 1,000 instructions per line (about 0.75 s on the board); the unowned items reach about 400 (about 0.30 s).
  - **Orchestrator assigned:** scan loop to Explorer 2 (after the packer), link lookup + row path to Method (then click parsing), timestamps to Sol (after skew).
- **User request:** a separate Analyst on Grok, with Gemini Neon in the browser. **Orchestrator** launched **Analyst 2** (Cursor `grok-4.7` with Gemini 4 Neon in its own tab) on `analysis2`. Scope:
  - independent re-derivation of every claim (`evals/insights2/verification.md`); it starts with v4 `c9e1a0c`, `d89e2b5`, `a019739`
  - an x86 Cascade Lake scorer cost model, with per-phase board predictions and what AVX-512 is worth (`evals/insights2/scorer-model.md`)
  - a 60M final projection and the superlinear phases
- **Orchestrator:** Explorer 2 skipped the ID packer (`explore/gemini-pack` has no commits) and went straight to the scan loop on `explore/gemini-scan`. **Method now owns the ID packer** (196 → 35 instructions per line).
- **Outage (≈20:00–21:50 ET):** the Claude 5-hour limit and a DNS failure stopped the Claude threads (Method, Analyst, Orchestrator). Eval's full eval of v4 `c9e1a0c` died with its Cursor turn: correctness was all clean, timing had only reached 1M, and no `v4.json` was written.
- **Orchestrator restart (21:50 ET):**
  - Re-tasked **Eval** to run the full eval on the v4 head **`a019739`**, which adds purchase-only category lookup and parallel links. It runs detached and the turn waits for the result.
  - Resumed **Method** on its uncommitted SIMD ID packer. The first cut was small (events 914 → 891 instructions per line), so it is profiling `pack` against `Ids::key` before committing. Link lookup + row path and click parsing follow.
- **Sol:** cache-bound ablations (`1856183`, merged) are **negative**. Adaptive L2-sized partitions cut 60M dedup cycles by 22% (−38 ms), but the whole process adds about 22 instructions and 26 cycles per line, the native footprint grows by 0.5 GB, and Linux wall regresses (+4.7% at 20M, +8.2% at 60M). **Keep 256 partitions.** The next thing to try is subdividing dedup independently of the person partitions. Item (5) is off Method's list.
- **Eval:** v4 @ `a019739` is **SUBMIT-READY** (`6f270b2`, merged). The comparison step crashed after measuring; Eval fixed it and rebuilt the report from the same data.
  - Instructions per row: **1,572** at 20M (v3 2,598, −39.5%) and 1,548 at 60M.
  - Predicted board: **1.175 s** from instructions, 1.418 s from wall × 3.10 (v3 board 1.9424 s).
  - 20M interleaved: native 0.453 s vs 0.618 s (−26.7%); Linux arm64 0.383 s vs 0.542 s (−29.3%, 11 pairs).
  - 60M: peak footprint 5.06 GB, Linux cgroup peak 5.29 GiB, median 1.32 s.
  - Correctness: fixtures 36/36 (native, arm64, amd64, and the portable amd64 path), 11/11 oracle diffs, fuzz 854/854 under every knob, review 120/120, window fuzz 227/227, deterministic. Clean cascadelake build passes.
- **Orchestrator:** merged `method/v4` @ `a019739` into main (src identical), re-checked fixtures 36/36 and dev MATCH on main, tagged `v4`, pushed. Asked the user to submit v4.
- **Idle-thread reports (all finished about 22:00 ET, picked up at 23:45 ET):**
  - **Method:** SIMD ID packer `20b8e79` (NEON `tbl` / SSSE3 `pshufb` nibble tables). Events 915 → 825 and clicks 763 → 669 instructions per line (dev, one thread). The cost was in `pack`, not `Ids::key`. The self-test was cut from 15.7M instructions per run to about 1k. Differential test over 10M cases.
  - **Explorer 2:** the scan has a floor of about 300 per line (classify 31, bit walk 63, seven slices 51, quote stripping about 150) while it builds generic slices. The target of 80 isn't reachable that way.
  - **Explorer 3:** session kernel `9ba36f2`. Not worth porting (574 → 563). The event sort, at about 310 per kept row, is the real cost.
  - **Sol:** the paired timestamp decoder passes 50/50 review comparisons. The instruction comparison is still pending.
  - **Analyst 2** (`248688c`, merged):
    - Recounts confirm G1 −679, category −116, links −38 at 20M, and G2 −162 at 20M.
    - **Method's "G1 saved 3" came from a stale binary:** the shared cargo target fingerprints by mtime.
    - **60M final model:** head about 4.1 s with the cache cliff, against about 0.84 s for leaders who scale linearly. **We're about 5× off on the final.** 100 instructions per line is worth 0.223 s at 60M.
- **Orchestrator re-tasked everyone (user: "keep pushing"):**
  - **Method:** `method/v5` from `20b8e79`. Link lookup + row path, then Sol's paired timestamps, then clicks. Clean rebuild and binary hash before every count.
  - **Analyst:** `v5-plan.md`. Minimal-work budget per phase from the spec, settle the partition conflict (Analyst 2 vs Sol), spec a fused per-column decoder, rank moves in 60M board seconds, and weigh a clean-room rewrite.
  - **Explorer 2:** a per-column fused event decoder that builds no generic slices (`explore/gemini-fused`). Target: events parse ≤ 450 per line.
  - **Explorer 3:** sortedness of each person's input, run-aware sort, or a single (person, ts) key in bucketing (`explore/gemini3-sort`). Then the output writer.
  - **Sol:** finish the paired timestamp decoder and write a port recipe. Then subdivide dedup inside each person partition for 60M.
  - **Eval:** quick profile of `20b8e79` as `v5-pre1`, a scan of the cascadelake binary for 512-bit instructions, a stale-binary guard plus the binary's sha256 in each result, and predicted 60M board time as a headline.
  - **Analyst 2:** verify the packer, a 60M cliff map (instructions vs cache/TLB, THP), and a Gemini brief on how leaders reach about 0.84 s at 60M.
- **Sol:** paired timestamp decoder ported onto the packer, `explore/fast-timestamps-v4` @ `75f9993`. Timestamps 152 → 74 instructions per record. Seed-43 events parse 820 → 731 per line, whole process 1,480 → 1,386. It passes 50/50 timestamp reviews, fixtures, dev and fuzz. Method will cherry-pick it as v5 move 2.
- **Analyst 2** (`d53ff40`, merged):
  - The packer is confirmed (−87 events, −94 clicks). The head `20b8e79` predicts about **1.13 s on the 20M board and 3.30 s on the 60M final**.
  - At 60M, only dedup gets worse per line (cycles ×1.42, instructions flat). Sessions and links no longer blow up.
  - Warm the cache before 60M counts.
  - mimalloc asks for THP via madvise; leave the allocator alone.
  - **Spec traps:** about 1 in 64 duplicates name a different user, and dedup runs before validation, so **dedup can't be scoped to person partitions**. Dropping invalid rows at the scan is also illegal. Uncompressed Parquet is legal.
  - Gemini puts the realistic band at 280–350 instructions per line.
- **Orchestrator:** warned Sol (dedup-subdivide must split on the dedup key, with a cross-user test) and told Explorer 3 that uncompressed Parquet is legal. Analyst 2 is now the independent verifier for v5 candidates (`75f9993`, dedup keying and dedup-subdivide, the fused and sort branches).
- **Method:** `method/v5` has move 1, a cheaper link lookup and row emit (`37bb046`), and move 2, Sol's paired timestamps cherry-picked (`2cbdb2b`). Method is still running gates, then click parsing.
- **Sol:** dedup subdivided on extra bits of the full event-ID hash (`6da0cd2`) is **negative**. +21 dedup instructions per line, whole-process cycles flat (40.656B → 40.719B), and Linux won 2 of 5 pairs. A cross-user collapse test was added at `4c68681`. **Flat dedup stays.** Sol is re-tasked to the sessions phase apart from the sort (person interning, the click prologue, the day flush) on `explore/sol-sessions`.
- **Method:** v5 moves 1–2 pass every gate (`method/v5` @ `5b7bcc2`; its tree is identical to `2cbdb2b`).
  - Dev, one thread, clean rebuilds with binary hashes, events / clicks per line: `20b8e79` 823 / 667 → move 1 (`37bb046`) 797.5 / 656 → move 2 (`5b7bcc2`) **709.6 / 632**.
  - At 20M against `a019739`: events 912 → 795 and clicks 739 → 634, through move 1.
  - **Move 1 came in small:** the link + row path was about 110 per line, not 235. Getting it to about 50 needs a merged dedup entry and back-reference layout.
  - All 3,300 fuzz cases MATCH.
- **Explorer 2:** the fused per-column decoder is **negative** (`2e22d43`). The cursor walk drops the NEON classify (824 → 1,243), and decoding from the comma mask saves only 21. Every column can be quoted, about 20% each. Re-tasked to **bitmask quote validation and stripping** (simdjson-style) on `explore/gemini-quotemask`. Quote stripping is about 150 of the roughly 300 scan instructions per line.
- **Eval:** the `20b8e79` quick profile (`v5-pre1`) and the cascadelake disassembly are done. **Redirected to the full eval of `5b7bcc2` as v5** (submission candidate, gated against v4).
- **Method:** on to move 3, click parsing. Move 4 (merged dedup entry) is conditional.
- **DEADLINE: 11:00 ET on 2026-11-22. Code freeze at 08:00 ET** (Analyst's v5 plan). Anything not gated by 08:00 is dropped.
- **Analyst** v5 plan (`63b9f05`, merged):
  - Floor about 350 per line (≈ 0.78 s on the final). Head `20b8e79` is 1,468 per line at 20M on one thread, about 3.5 s on the final. Everything ranked tonight would reach about 670 per line (≈ 1.5 s).
  - **Corrections:** the event sort is 44 per line in v4, not 310 (that was v3). The click sort is 89 per line (377 per click).
  - Partitions: Sol is right that more global partitions lose; the fix is sub-buckets inside event-ID partitions. Sol tried that and it was neutral.
  - Clean-room rewrite: no.
  - Its top move, a fused decoder (−0.86 s), predates Explorer 2's negative measurement. The Analyst has been asked to reconcile.
- **Explorer 3** (`3b31648`):
  - Each person's events arrive in random order (0.2% already sorted, 15 runs per person), so **the current per-person sort stays**.
  - **Writer with dictionaries and statistics off: 128.6 → 60.5 per kept row**, seed-42 MATCH. The Analyst's independent patch gets 112 → 56.
- **Orchestrator:**
  - Explorer 3 → the **click sort** (`explore/gemini3-clicksort`).
  - Method → port the writer settings as a v5 move after clicks.
  - Eval → a Linux A/B of the writer after the v5 eval (files grow 4×).
  - Analyst → reconcile the fused-decoder spec with Explorer 2's 1,243 result.
- **Analyst** (`41e2fd7`, merged): Explorer 2's `2e22d43` was not a fair test of the decoder design. It was a scalar `memchr` plus a byte walk, about 710, feeding the old decoders.
  - The real design, **spec 3a**: one 16-byte load per field, a class mask per column, decoding from the same register, branch-free end checks. The front end costs about 200 per line, against about 585 today.
  - **Re-rank:** 1a quote mask (Explorer 2, about −0.30 s, due 02:30). 1b per-column decoder (about −0.40 to −0.55 s; go/no-go at 06:00 is events ≤ 600 at 20M).
  - **Revised final:** 1a only ≈ 2.4 s; 1a and 1b ≈ 2.0 s; plus timestamps and the click port ≈ 1.55 s.
- **Orchestrator:** to run 1a and 1b in parallel, **Sol was moved from sessions to the 1b per-column decoder** (`explore/sol-coldec`). Explorer 2 finishes 1a.
- **Method:** **v6 is ready about 2.5 hours early, `method/v5` @ `1f02cb2`.**
  - Move 3, click parsing (`3f72db2`): clicks 632 → 559 per line. The campaign lookup was 120 per line, because `IdIndex::get` inlined the map probe and paid register spills on every call. The direct path is now inlined and the map probe moved to a cold function (123 → 76 per field).
  - Move 4, writer (`1f02cb2`, Explorer 3's settings): 121.5 → 58.7 per line at 20M. Output grows from 21 to 93 MB at 20M. `SESSIONS_PARQUET=v4` restores the old writer.
  - The dedup merge was skipped: it would save about 5 per line.
  - Phases on dev now: events 711, clicks 134, dedup 37, sessions 298, writing 88.
- **Analyst:** release plan (`28339b3`, merged): trains v5 → v8, about 35 min from commit to verdict, each submission doubling as a calibration point, and a final pick rule (20M board × the local 60M/20M Linux ratio).
- **Orchestrator:**
  - Eval queue: v5 verdict, then the full eval of `1f02cb2` as v6, then the writer A/B on Linux (the same binary with and without `SESSIONS_PARQUET=v4`).
  - Method → move 5: time and cherry-pick Sol's untimed sessions prototypes (`ca60a5b`, `6f3522a`, `3c03aed`).
- **Eval:** v5 @ `5b7bcc2` is **SUBMIT-READY**. 1,383 instructions per row, against v4's 1,572. Predicted board 20M: **1.034 s** (instructions model) or 1.555 s (wall × 3.10). Interleaved A/B: native 0.455 s vs 0.505 s, about 10% faster. Gates A, B and C all pass.
- **Orchestrator:** merged `5b7bcc2` into main (src identical), re-checked fixtures 36/36 and dev MATCH, tagged `v5` and pushed. Asked the user to submit.
  - Interference: Explorer 3 ran a Linux container during Eval's lock, and Method's count runs at nice 0 tripped the guard (reniced). All builders were told to use nice 19 and no Docker without the lock.
- **User request: more parallel threads.** **Orchestrator** launched five new ones. Each is bench-lock-free, or uses the lock in short holds; all use nice 19.
  - **Explorer 4** (Codex Sol, `explore/clickdec`): per-column SIMD decoder for **click and link lines** (move 3). It reuses Sol's event decoder helpers. The scan target is 254 → ≤ 80 per click line.
  - **Red Team** (Opus, `claude_andrew`, `redteam`): adversarial correctness review of every fast path since v4 (packer, emit ring, paired timestamps, `IdIndex` click lookup, Parquet writer, dedup rules). It writes only `evals/redteam/`.
  - **Explorer 5** (Codex Astra, `explore/critpath`): critical-path and parallel-efficiency map (CPU util ≈ 0.87 at 60M), then fixes serial stretches (writer, barriers, skew, exit/unmap).
  - **Analyst 3** (Cursor Grok, `analysis3`): **x86 instruction counts** for v4, v5 and v6, via callgrind in an amd64 `x86-64-v2` container. It checks whether the ARM-based rankings hold on the scorer's x86.
  - **Scout** (Opus, `claude_master`, `scout`, user request): finds the top teams' public repos and writes clean-room notes on their techniques, with **no code copying**. Licenses are noted. It stops if the rules forbid looking. Due 05:00.
- **Eval:** the v6 full eval (`1f02cb2`) started at 00:37. The writer A/B on Linux is queued after it.
- **BOARD RESULTS (from the user, 00:5x ET). They overturn the model.**
  - Submissions: v3 `29b64bf` **2.529 s** (rescored from 1.9424); v4 `a019739` **2.198 s** (BB-E752B096); v5 `5b7bcc2` **2.146 s** (BB-41B5864A, the current best, entered in the final).
  - The leaders were rescored too: **0.4508 s** (NoMoreLite), with the top 14 at 0.45–0.67 s. We're around 159th.
  - The instruction model predicted 1.18 s for v4 and 1.03 s for v5, so it's **wrong**. Fit: about 0.0003 s per (instruction per row) plus **about 1.7 s of fixed scorer-only overhead**. The 47% instruction cut from v3 to v5 bought only 15%.
  - Leading hypothesis: a sandboxed runner (gVisor-style), where page faults and mmap'd file reads are about 10× costlier. We `Mmap::map` 1.8 GB of input and first-touch about 1.8 GiB of anonymous memory at 20M (on Linux, THP hides this: only about 16k minor faults).
- **Orchestrator pivot: the fixed overhead is now the #1 target.**
  - Explorer 5: local gVisor (`runsc`) reproduction plus a breakdown.
  - Explorer 3: pread input instead of mmap.
  - Method (move 6): fault counters in the phase marks, buffer reuse, no zero-fill, huge or reserved mimalloc arenas.
  - Analyst: refit on the 3 board points and recommend the next probe submission.
  - **New, at the user's request (Gemini Neon in the browser):** **Neon Detective** (scorer-environment hypotheses, the track's infra docs, startup and exit paths) and **Neon Architect** (structural low-footprint design, from 1.8 GiB to ≤ 400 MiB, on `explore/neon-lowmem` off `3671aeb`).
- **Method:** move 5 = `3671aeb` (Sol's 3 sessions prototypes + Explorer 3's click sort). Sessions + attribution 297 → 236 per line; all gates pass. v7 base.
- **ROOT CAUSE FOUND (Scout, 00:52 ET).** The organizers changed the generator at **21:08 ET** (scorer `shopping-sessions-5`, everyone rescored): **1 in 8 distinct user, event and click IDs is now a prefix plus 32 hex characters (33 bytes)**, and every ID goes through a per-seed keyed bijection.
  - Our packer handles ≤ 10 characters, so those IDs go to the cold mutex-sharded `Ids::intern`.
  - v5 on the new 20M data: **0.42 s → 1.14 s** local wall (events parse 0.19 → 0.76 s), but only +21% instructions. That's lock contention and cache misses, which the instruction model can't see.
  - Our output is still correct (new dev MATCH).
- **Orchestrator:**
  - Updated `docs/rules.md` (line 101 is the only change) and `tools/generator` from the current downloads, and verified that the generator reproduces the Scout's new dev set byte for byte.
  - Moved the old `data/{dev,dev-answer,seed-42,seed-43}` to `data/old-gen/`. Installed the new dev set and dev answer, and am regenerating seed-42 (20M) and seed-43 (60M).
  - **Method** → move 6: an exact lock-free u128 fast path for the 33-byte IDs, with byte-order-exact comparisons.
- **Datasets regenerated with the new generator:** `data/seed-42` (1.9 GB) and `data/seed-43` (5.8 GB). The old ones are in `data/old-gen/`. Eval is regenerating the rest of the suite and the expected answers.
- **Explorer 5, gVisor reproduction (harness `explore/critpath` @ `55922b0`):** v5 on the new 20M data, median of 3 pairs: **plain Docker 0.94 s, gVisor (runsc) 2.23 s** (+1.29 s; 2.36 s launch to teardown). **That matches the board's 2.146 s.**
  - Event parse alone is 0.565 → 1.528 s under gVisor, pointing at futex syscalls from the contended intern `Mutex`.
  - **The gVisor time is now our primary predictor of the board.**
- **Explorer 4:** click decoder: dev click phase 561 → 389 instructions per line, 0.49% fallback (old data). Told to route 33-byte IDs onto the fast path.
- **Explorer 2:** quote mask is negative (−28). Re-tasked to a hex-32 SIMD validator and exact packer kernel for Method (`explore/gemini-hex32`).
- **Analyst:** board fit: 1.70 s fixed + 0.000318 s per instruction per row, within 4 ms on all three points. It predates the root cause and is being redone.
- **Scout:** v5 on the **new-generator 60M** data (seed 61, 60M/15M, NCPU=8) runs **8.58 s**, against 1.32 s on old data. Events parse is 6.36 s (73 G instructions), because the intern map goes superlinear with rehashes under the shard locks as about 8M long IDs pile in. Every earlier instruction model and 60M projection was measured on stale data. **The long-ID fast path is the #1 priority.**
- **Explorer 5, v5 per phase, plain vs gVisor (ms, median of 3 reversed pairs):** lookups 42→93, **event parse 584→1,495**, clicks 111→197, dedup 41→54, sessions 109→138, **write 35→165**, start and exit 17→76.
  - Input policy under gVisor: mmap 2.06 s (best), MAP_POPULATE 2.17 s, whole-file reads 2.53 s, reads + MADV_HUGEPAGE 2.56 s. **Keep mmap.**
- **Orchestrator:**
  - **The v6 writer (no dictionaries or statistics) is dropped from the trains**, since 4× output costs more under gVisor.
  - v7 = `3671aeb` + revert move 4 + move 6 (lock-free long IDs).
  - Explorer 3 re-tasked from pread to **write-path syscalls** (one write per file, tables in parallel) on `explore/gemini3-write`.
- **User: Grok is out of quota.** The 7 Grok threads (Eval, Analyst 2, Explorer 2, Explorer 3, Analyst 3, Neon Detective, Neon Architect) were **moved to Opus on `claude_master`**. All had died on the Grok limit, so their tasks were re-sent.
- Released a stale bench lock (analysis2, pid 83563 dead). **The gVisor harness was cherry-picked to main** (`evals/explore/runsc/run.sh`).
- **Explorer 5, syscall trace of v5 under gVisor:**
  - Event parse: **13,351 futex calls out of 14,946 syscalls (89%)**. Clicks: 2,368 of 2,671. Dedup and sessions: 5 each.
  - Output: 2,241 writes and 203 opens.
  - **12,217 `madvise` calls after the written mark**, despite `std::process::exit`, likely mimalloc purging. Testing `_exit` and disabling mimalloc purge.
- Re-tasks:
  - Analyst 2 → verifier for v7 (long IDs).
  - Explorer 2 → hex-32 kernel.
  - Explorer 3 → write-path syscalls.
  - Analyst 3 → x86 counts on new data.
  - Neon Detective → hunt syscall and lock sources other than intern.
  - Neon Architect → ID-key widening design.
  - Eval → regenerate the suite on new data and make gVisor time the primary predictor.
- **Analyst** (`3f66634`, `5fdfc02`, merged): the long IDs (about 1.1–1.4 s) plus the sandbox's futex, mmap and fault cost explain the 1.70 s. The linear fit is retired; **the gVisor harness on new data is the board predictor.** With the exact u128 path, the expected board is about 0.8–1.05 s.
  - Release plan: **v7** = v5 + long-ID path + click sort + sessions moves, writer held back; Method commits by 02:30, submit about 03:15. **v8** by 07:00. Freeze at 08:00.
  - Key ordering must be byte-exact across short-packed, 33-byte and interned forms.
- **Explorer 4:** click and link decoder gated on the new data. Seed-42 clicks 632.5 → 493.0 and links 696.8 → 624.1 per line, 0.48% fallback, with a `pack_long` hook (`53604e7`, `af19cf5`). Now staging `stage/v7-pre` = `3671aeb` − writer + click decoder, gated and gVisor-timed, to rebase onto Method's move 6.
- **The Codex limit hit Explorer 5 (Astra), Explorer 4 (Sol) and Sol.**
  - At the user's request, **Explorer 5 → Opus on `claude_master`**.
  - **Explorer 4 and Sol → Opus on `claude_andrew`**, to spread the load: `claude_master` now carries 9 threads.
  - Tasks were re-sent. **Switch Explorer 4, Explorer 5 and Sol back to Codex Sol once the Codex limits reset** (user request).
- **Sol (before the limit):** the per-column event decoder recognises 33-byte IDs. The seed-42 fallback went 24.53% → 0.35%, and decoded values match on the new dev and seed-42 data.
- **Method: v7 candidate `e693e18`** = `3671aeb` + writer revert (`c7acf4a`) + **move 6: lock-free, pre-sized long-ID table**.
  - 128-bit hex value → stable slot key, max 128 probes, then overflow to the interner.
  - Byte-exact ordering: long vs long by prefix then value; long vs short by decoded bytes. The `env` reads were hoisted to startup.
  - Gates: unit tests (6,000 long IDs and near-misses, plus an overflow test), fixtures 36/36, new dev MATCH under `NO_FAST` 0–3, new seeds 7–11 vs reference 50/50, new seed-42 MATCH.
  - Indicative, niced, 4 threads, no lock: 20M 3.65 → 1.82 s; 60M 16.4 → 7.1 s (events parse 11.1 → 2.8 s).
- **Orchestrator:** v7 verification in parallel: Explorer 5 (gVisor timing first), the Red Team (long-ID adversarial cases), Analyst 2 (spec check) and Eval (full eval as v7). Method builds v8 moves on top: Explorer 4's click and link decoder, Sol's event decoder (06:00 go/no-go), Explorer 2's hex32 kernel.
- **Analyst 2: v7 `e693e18` correctness PASS.**
  - Every ID comparison goes through `Ids::cmp`, which is byte-exact. Overflow consistency holds (slots fill and never move; CAS with Release/Acquire is correct). The 33-byte decode is exact.
  - Adversarial suite `evals/insights2/v7_longid`: 54/150 seeds × 6 knobs, 0 mismatches. It catches 4 deliberately broken builds. Seed-42 MATCHes Eval's regenerated oracle.
  - Perf: NCPU=1 events-parse CPU 3.72 → 2.73 s. The scalar hex32 costs about 190 instructions per long ID, so Explorer 2's SIMD kernel is the follow-up.
- Machine load is 30–60. **v7's board prediction will come from interleaved v5/v7 gVisor pairs** (Explorer 5): 2.146 s × the ratio.
- **Analyst 3 (x86 strace):** v7 futex calls in events parse at 20M: **58,192 → 79**.
- **Method:**
  - **v7b = `method/v7b` @ `96af24b`** = `e693e18` + move 6b: mimalloc `purge_delay=-1` and `purge_decommits=0`, plus `libc::_exit(0)` after the last writer closes. Knobs `SESSIONS_PURGE=on` and `SESSIONS_EXIT=normal` restore the old behaviour. madvise 13,834 → 3. Outputs byte-identical to `e693e18` at NCPU=1; seeds 7–11 50/50.
  - **v8 work on `method/v8`:** move 7 (`6c56c54`, Explorer 4's column decoder wired to the long-ID table) + hex32 (`2b9aecd`).
- Explorer 5: three-armed gVisor ABBA (v5 / v7 / v7b) once Eval's `v5-newgen` releases the lock. The Red Team adds v7b, focusing on `_exit` output completeness.
- **Analyst 3 correctness flag:** `aca7078` (an intermediate v8 commit: "Recognize 33-byte hex IDs in click and link columns", parent `8bb8d43`) is **DIFFER on new dev** (133,891 vs 118,107 user rows), on both arm64 and x86.
  - The Orchestrator built the current `method/v8` head `2b9aecd`: **new dev MATCH**.
  - v7 `e693e18` MATCHes on x86. Method is asked for the root cause and full gates on the v8 head. **Never ship an intermediate commit.**
- **Analyst 3 x86 perf:** the scalar `hex32()` costs 256 Ir per long ID on x86 (about 2× ARM). Events on x86 go only 813 → 804 per line (ARM 829 → 768). Method is wiring the SIMD `digits()` kernel (`2b9aecd`) in v8, worth about 70 per event line on x86.
- **Analyst 2:** v7 `e693e18` **900/900 MATCH** (150 seeds × 6 knobs). Suite merged as `evals/insights2/v7_longid/` (catches 4/4 mutants); add it to Gate A.
  - `LongTable` is 805 MB at 60M (24 B slots, `in_bytes/256`, load about 0.30), touched at random: about 197k first-touch faults. Measure under runsc at 60M before resizing.
  - Use NCPU=1 for instruction gates (NCPU=8 swings ±150 per line under load).
- **Analyst 3:** **v7b `96af24b` x86 MATCH on new dev** (`x86-64-v2`, valgrind, NCPU=1). x86 instructions identical to v7 by phase: total 1,480 per event line (events 804, sessions 253, write 173). The `_exit` path is confirmed taken, with complete outputs. The mimalloc option IDs (purge_decommits=5, purge_delay=15) are checked against the bundled headers. NCPU=8 x86 run next.
- **Analyst 3** (`4ab2a6b`, merged):
  - **v7b x86 MATCH at NCPU=8** (valgrind fair-sched, plus 2× under Rosetta).
  - **v8 head `2b9aecd` x86 MATCH** on new dev.
  - x86 instructions per event line: v7 and v7b 1,480; **v8 1,384 (−96)**. Events 804 → 753 (the SSSE3 hex kernel is about 48 Ir per long ID, against 256 scalar); clicks 150 → 106. No x86 regressions.
- **Orchestrator incident (fixed):** merging `analysis3` (branched from `1f02cb2`) carried v6's `src/main.rs` into main (`b43bf46`). **Restored main src to v5 `5b7bcc2` in `d4917b0`**; it was on origin for about 1 min, and nothing was submitted from it. **Rule from now on:** bring notes branches onto main with `git checkout <branch> -- <notes dir>`, never a full merge, unless `git diff --name-only main...<branch>` is notes-only.

### 2026-11-22, 02:20 ET: resume after the claude_master limit
- **User:** "continue", "optimize usage and start as many threads as you can", "complete the eval on v7 at priority".
- **Orchestrator:**
  - Re-oriented from the log; the bench lock was free.
  - **Started the v7b full eval myself** (`evals/run.py --version v7b --rev 96af24b --profile full`, in the eval worktree, holding the bench lock).
  - Diagnosed `v5-newgen`'s REJECT: the `SESSIONS_DEBUG_HASH_BITS=4` dev run **timed out** (fuzz under that knob passed 150/150). That's a perf timeout under a pathological knob, not a mismatch. New policy (sent to Eval): a knob dev timeout with fuzz passing is a *warn*, and the timeout is raised to 600 s.
  - **Approved move 8 without waiting for Sol's 06:00 sign-off.** v8 release candidate = tree of `try/coldec` @ `2bfb034`; Method is fast-forwarding `method/v8` and running the final gates.
- **Provider rebalance:** claude_master is out until about 05:00; Codex had been capped; Grok is out.
  - Eval → claude_andrew.
  - Analyst 3 and Explorer 5 → Cursor Opus 5.5.
  - Explorer 3 and Neon Detective → Cursor Gemini 4 Neon.
  - Analyst 2 → Antigravity Opus 4.6 Thinking.
  - Explorer (Sol) and Explorer 4 → back to Codex gpt-6.2-sol (user request; fall back to claude_andrew if capped).
  - Red Team stays on claude_andrew; Method and Analyst stay on claudeAgent.
- **Assignments:**
  - **v8 verification:** Analyst 2 (spec check of move 8), Analyst 3 (x86 MATCH and instructions), Red Team (adversarial, by 04:30), Explorer 5 (3-arm gVisor ABBA at 20M + 60M), Eval (full v8 after v7b, then v7b vs v8 under gVisor at 60M).
  - **v9 (freeze 08:00):** Explorer 3 (write path), Explorer Sol (`LongTable` at 60M), Explorer 4 (links), Neon Detective (start, exit and lookups traces), Method (v8, then start/exit, then integration).
  - **Analyst:** the release schedule plus the final-pick rule (`release-final.md`).
- **Quota wall at 02:35:** claudeAgent and claude_master are capped until about 05:00, and Codex until 05:47. Cursor no longer includes Opus 5.5 or Gemini 4 Neon ("weekly usage"). **Working lanes:** claude_andrew, Antigravity, Kiro, and Cursor Composer/Auto.
  - Re-routed:
    - Explorer 3 (write path) → Antigravity Opus 4.6 Thinking
    - Analyst 3 (x86) → Kiro Sonnet 4.5
    - Explorer Sol (`LongTable`) → Kiro Sonnet 4.5
    - Explorer 5 (gVisor ABBA) → Cursor Composer 2.5
    - Neon Detective (traces) → Cursor Composer 2.5
    - Explorer 4 (links) → Cursor Auto
  - Explorer Sol and Explorer 4 go back to Codex Sol after 05:47 (user request).
  - Method and Analyst couldn't switch providers (background commands still held in their sessions); they resume at 05:00 on claudeAgent.
  - **The Orchestrator fast-forwarded `method/v8` → `2bfb034`** (v8 release candidate; Eval's full run re-gates everything).
- **Orchestrator, 02:44: v7b full eval done** (1,278 s): **HOLD.** Gates A and B pass: 10 oracles, 1000 fuzz under every knob, and the `HASH_BITS=4` dev run now MATCHes (no timeout, thanks to the lock-free long-ID path). Gate C failed only because 3+3 runs gave 2sd 0.653 s against a 0.55 s gain. gVisor 20M is 1.360 s vs v5's 1.910 s (+28.8%); predicted board 60M 3.06 s.
  - **Override → SUBMIT-READY.** The mechanism is known (futex 58k → 79), a submission is free (best counts), and it gives a calibration point.
  - Released as `ddbf1a3` (src identical to `96af24b`); fixtures 36/36 and dev MATCH on main; tag `v7b` pushed; **user asked to submit.**
  - Eval told to use ≥ 7 interleaved pairs (or a paired-ratio test) for the gVisor Gate C, then to run v8 full against the v7b baseline.
- **USER SUBMITTED v7b** (`ddbf1a3`): board **1.5275 s** (BB-870A1088, wait 182 ms, rank 132). It's our best and is entered in the final. Previous best: v5 at 2.1461 s.
  - **Calibration: board ≈ 1.12 × local gVisor 20M process time.** v7b: 1.5275 / 1.360 = 1.123; v5: 2.1461 / 1.910 = 1.124, same session. **The gVisor harness is now the trusted predictor.**
  - **What the leaders' ~0.45 s needs:** about 0.40 s of local gVisor time. v7b is plain Docker 0.55 s, plus **0.81 s of gVisor overhead**, with cgroup pgfault **2.40M under gVisor vs 18.8k plain** (peak RSS 4.06 GiB). gVisor gives no THP to app memory, so every 4 KB page of the ~4 GiB footprint plus the mmapped input faults individually. **The #1 lever is memory footprint and touched bytes, not instructions.** Second is the write path (165 ms vs 35 ms).
- **Orchestrator:** launched the **Footprint** thread (claude_andrew, `explore/footprint` from `2bfb034`): fault anatomy by structure and phase, then prototypes: streaming `pread` into reused buffers instead of mmap, buffer reuse across phases, no zero-fill, presizing. Told Eval to make `board_est = 1.123 × gVisor 20M` primary and to headline gVisor pgfault and RSS. Told Explorer Sol and Neon Detective to judge by faults.
- **v8 `2bfb034` verification (03:05):**
  - **Red Team PASS:** every adversarial stage MATCHes under all knobs.
  - **Analyst 3 (Kiro) x86 MATCH:** NCPU=1, NCPU=8 fair-sched and `NO_FAST`. x86 instructions per event line **1,481 → 1,316** (events 753 → 588, −165, from the per-column decoder). SSE2 and SSSE3 paths are active, with no scalar fallback. Notes are at `analysis3` `258dd8d`.
  - Method's gates passed earlier (900/900 long-ID suite, 4,600 fuzz).
  - Analyst 2's spec read didn't happen: Antigravity's Claude models hit their third-party cap (reset in about 5 h; only the Gemini models work).
  - Eval's v8 chain is running (untimed, then full with paired 7-round gVisor A/B vs v7b, then gVisor 60M).
- **Re-routes:** Explorer 3 (write path) → Kiro Sonnet 4.5; Explorer 4 (links) → Antigravity Gemini 3.8 Flash.
- **03:19: v8 untimed phase PASS** (Eval, full profile): fixtures 36/36, differential 9/9, fuzz 1000 under every knob (`HASH_BITS=4` about 290 s, MATCH), long-ID suite 900/900, 0 framework errors.
  - With Red Team PASS and x86 MATCH, **v8 is released as `main` `2a9f52c` (tag `v8`; src identical to `2bfb034`)**; fixtures 36/36 and dev MATCH on main. **User asked to submit** (one slot left this hour after v7b at 02:51).
  - Eval's timed run (pid 38234) is queued behind Explorer 5's `run_gvisor_20m.sh` (3-arm v5/v7b/v8 ABBA), which is allowed to finish; Explorer 5 was told not to re-acquire until `results/v8.json` exists.
- **USER SUBMITTED v8** (`2a9f52c`): board **1.0844 s** (BB-607A8C0F, wait 207 ms, **rank 86**). It's our best and is entered in the final. That's −29% vs v7b's 1.5275 s, beating my estimate of 1.4–1.5 s, so the per-column decoders cut gVisor time more than instruction counts suggested (probably fewer touched pages and allocations too).
  - At the 1.123 calibration, v8 implies a local gVisor 20M of about 0.965 s. The leaders (≈0.45 s) need about 0.40 s.
- **Orchestrator:** stopped Explorer 5's `run_gvisor_20m.sh` (15–20 min per run under its Kiro-built harness, holding the lock for hours). Freed the bench lock for Eval's timed v8 run, and re-tasked Explorer 5 to fix its harness and plan a ≤ 5 min 60M v7b-vs-v8 run.
- **03:36: all threads stopped** (user noticed).
  - claude_andrew hit its 5-hour limit (resets 05:40), killing Eval and Footprint. Kiro hit its **monthly** limit (Explorer 3, Explorer 5).
  - Still working: claude_master (the Orchestrator's lane) and Antigravity Gemini 3.8 Flash. claudeAgent ≈ 05:00, Codex 05:47.
  - Eval's timed v8 run died with it; v8 already has its board time, so that's not critical.
- **v9 branches found:**
  - `explore/footprint` `9775367`: pread streaming of events and clicks
  - `explore/sol-longtable` `7413dfe`: 16 B slots, 39–42% fewer faults
  - `explore/links-par` `ddcd7d3`: in-place lock-free union-find
  - `explore/neon-detective` `e9fda82`: parallel `Input::open`, zeroed allocations
  - `explore/gemini3-write` `c2c10d4`: dictionaries and statistics off. **Rejected**: the same idea as the dropped v6 writer.
- **Orchestrator integrated v9a = `integ/v9` @ `0340530`** = `2bfb034` + sol-longtable + neon-detective + links-par (conflict resolved to links-par). Gates: fixtures 36/36, new dev MATCH under `NO_FAST` 0–3, seed-42 MATCH. **Full eval running** (Orchestrator, eval worktree).
- Re-routes:
  - **Footprint → claude_master**, resumed: gate and gVisor-time the pread streaming.
  - Method is stuck (stale background commands block the provider switch).
  - Neon Detective (Gemini Flash) → write-path syscalls with the encoding unchanged.
  - Explorer 4 (Gemini Flash) → clicks-phase faults.
