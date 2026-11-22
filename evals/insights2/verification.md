# Verification: v4 commits, rebuilt and re-counted

Analyst 2, 2026-11-21. Independent of Method's commit messages and of the first Analyst's `evals/insights/v4.md`.

Every binary below was compiled from `git archive` of that commit with the system Rust (`rustc 1.100.0`), `cargo build --release -j 2`, fat LTO as in `Cargo.toml`. The five binaries have five different sha256 hashes. Each build log contains `Compiling sessions` for that commit's tree, and `sessions.d` names that tree's `src/main.rs`.

| Commit | What it is | sha256 |
| --- | --- | --- |
| `29b64bf` | v3, the submitted baseline | `10247d17…cd219b30` |
| `e62060c` | v4 move 1, quote-aware fast path (G1) | `6cea8a76…3d8e5407` |
| `c9e1a0c` | v4 move 2, 16 B rows + counting sort (G2) | `19f9deaa…ae9775bf` |
| `d89e2b5` | category lookup only when `price > 0` | `edc022fa…7f967f6c` |
| `a019739` | parallel link components, from `89ad72c` | `84a98cbb…1a97d54d` |

Instruction counts are `/usr/bin/time -l`, "instructions retired", two runs, `NCPU=1`, nice 19, while Eval held the bench lock. The denominator is event lines from `data/stats`: dev **1,072,086**, seed-42 **21,507,843**. The first Analyst used 1,072,115. Those 29 lines move a per-line figure by 0.07 and do not explain any gap below.

The lower of the two runs is the steady count. The other run is in parentheses. Dev moves by up to 8 instructions per line between runs. Seed-42 moves by under 3.

## Measured, single-threaded

| Commit | Dev instructions | Per event line | Seed-42 instructions | Per event line |
| --- | ---: | ---: | ---: | ---: |
| `29b64bf` | 2.8010 G (2.8006 G) | **2,613** | 55.261 G (55.302 G) | **2,569** |
| `e62060c` | 2.0728 G (2.0815 G) | **1,933** | 40.985 G (40.985 G) | **1,906** |
| `c9e1a0c` | 1.9769 G (1.9858 G) | **1,844** | 37.510 G (37.493 G) | **1,744** |
| `d89e2b5` | 1.8549 G (1.8627 G) | **1,730** | 35.011 G (35.068 G) | **1,628** |
| `a019739` | 1.8265 G (1.8343 G) | **1,704** | 34.192 G (34.199 G) | **1,590** |

Deltas, steady run, instructions per event line:

| Step | Dev | Seed-42 (20M) |
| --- | ---: | ---: |
| G1 `29b64bf` → `e62060c` | **−679** | **−664** |
| G2 `e62060c` → `c9e1a0c` | **−89** | **−162** |
| Category `c9e1a0c` → `d89e2b5` | **−114** | **−116** |
| Links `d89e2b5` → `a019739` | **−27** | **−38** |
| v3 → current head | **−909** | **−980** |

## Eight threads, one run each

The scorer runs 8 threads, so the board predictor uses these. Seed-42 noise on the single-thread pair was under 3 per line, so one 8-thread run is enough there.

| Commit | Dev per line | Seed-42 per line | Seed-42 instructions |
| --- | ---: | ---: | ---: |
| `29b64bf` | 3,031 | **2,602** | 55.962 G |
| `c9e1a0c` | 2,246 | **1,766** | 37.993 G |
| `a019739` | 2,128 | **1,618** | 34.808 G |

Eight threads add about **+30 instructions per line at 20M** and about **+400 at dev**. The dev figure is thread overhead spread over 1.07M lines (about 450M extra instructions). Dev at `NCPU=8` is not a comparable metric. Seed-42 at `NCPU=8` is the one that lines up with Eval.

## What holds up

**v3 at 20M is the real baseline.** Eval's full eval recorded 2,598 instructions per event line and about 55.9 G instructions (`evals/results/v3.md`). This rebuild at `NCPU=8` is 2,602 and 55.962 G, 0.14% higher. The "before" binary is v3.

**G1 delivered −679 on dev, exactly the first Analyst's delta.** Their table was 2,641 → 1,962 → 1,869. Mine is 2,613 → 1,933 → 1,844. The steps are −679 and −89 against their −679 and −93. At 20M, G1 is −664.

**Method's 20M band for `c9e1a0c` is right.** The commit log and the orchestrator log say 1,772–1,795 against v3 at 2,610, about −31%. This rebuild at `NCPU=8` is 1,766 against 2,602, which is −32%.

**The category delta matches Method's message.** `d89e2b5` says dev `NCPU=1` went from 1,860 to 1,747 (−113). The rebuild is 1,844 → 1,730 (−114), and −116 at 20M. The absolute level sits about 16 per line under Method's; the step is the same.

**Explorer's parallel-links figure holds at 20M.** `evals/explore` and the log say −36 instructions per line at 20M. The rebuild is −38 (`d89e2b5` 1,628 → `a019739` 1,590).

**Eval's in-flight `c9e1a0c` binary is that commit.** The cached binary at `sessions-eval.noindex/bin/c9e1a0cb5497/sessions` scored 1,742 per line at 20M single-threaded, against 1,744 for this rebuild. Eval is not timing a stale v3 binary.

## Disagreements

**Method's "G1 saved 3 instructions per line" is a stale binary.** The orchestrator log records move 1 as 2,628 → about 2,625, and says the quote-aware path took 100% of lines while `split_fields` was never the cost. A from-source `e62060c` is −679 on dev and −664 at 20M. The first Analyst's correction stands. The endpoints Method quoted (v3 about 2,631, move 2 about 1,855) sit within 1% of this rebuild. The middle number does not.

I hit the same failure while building these. A shared `CARGO_TARGET_DIR` fingerprints the `sessions` unit by mtime. After v3 had been linked, `cargo build --manifest-path` of `e62060c` printed `Finished in 0.02s` and left a byte-identical binary, and it rewrote `sessions.d` to point at the new tree. Cargo will report a later commit as fresh when the binary on disk is newer than that commit's source mtimes. Deleting `target/release/build/sessions` and the `sessions` binary before each commit forced a real compile. Method and Eval should do that, or touch every `src/*.rs`, whenever one target directory serves more than one commit.

**Method's dev delta for parallel links (−12) is too small.** The `a019739` message says 1,747 → 1,735. The rebuild is −27 on dev and −38 at 20M. Use the 20M number. It matches Explorer.

**Sol's category model (−57 to −67) is about half the measured cut.** `evals/explore/unneeded-work.md` modeled −57 to −67 per event line from skipping 97.1% of lookups. `d89e2b5` measures −114 on dev and −116 at 20M. The first Analyst's "~100" is the closer estimate. The lookup was more expensive than the per-call model, or the branch removed work around the call as well as the call.

**G2 is −89 on dev and −162 at 20M.** The first Analyst measured −93 on dev and treated G2 as over-modelled, with the sessions kernel still the lever inside that phase. The dev step is confirmed (−89 against −93). At 20M the same commit saves −162, about 0.12 board seconds, the second-largest measured cut after G1. Dev understates G2 because the counting sort and the 16 B rows pay off as person runs get longer. Rank G2 by the 20M number.

**Absolute dev totals in `v4.md` are about 1% high.** 2.832 G, 2.104 G and 2.004 G against this rebuild's 2.801 G, 2.073 G and 1.977 G. That is +25 to +29 per line on every commit, so every delta survives. It is not the 8-thread dev inflation (+400). Later board math in this directory uses these rebuilds.

## Board time from these counts

The calibration formula is `instructions_per_row × 20e6 / 26.754e9`, with instructions per row equal to retired instructions divided by event lines. It reproduces v3's 1.9424 s from Eval's 2,598. Physical retirement on that run is `2,598 × 21.508e6 / 1.9424 s` = **28.77 G instructions/s**. Using 20e6 on one side and 21.51e6 on the other is consistent only if both sides stay paired. The 60M projection has to use 28.77 G/s and 64.15M event lines, or it double-counts the 20-vs-21.5 factor.

`NCPU=8`, seed-42, predicted practice-board time:

| Commit | Instr/line | Predicted board |
| --- | ---: | ---: |
| `29b64bf` | 2,602 | **1.945 s** (submitted 1.9424 s) |
| `c9e1a0c` | 1,766 | **1.321 s** |
| `a019739` | 1,618 | **1.210 s** |

One hundred instructions per line is 0.075 s on the 20M board and 0.223 s on the 60M final, at 28.77 G instructions/s.

`a019739` scaled by event lines only, with no cache cliff, is **3.61 s** at 60M. The leaders at 0.28 s are **0.84 s** if they scale the same way. The cliff is in `scorer-model.md`.
