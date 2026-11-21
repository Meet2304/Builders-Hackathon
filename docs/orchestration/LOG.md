# Orchestrator log

Newest entries at the bottom. Each entry records who did what, on which branch or commit, the numbers, and the decision taken.

## Version ledger

| Version | Commit | Branch | 20M median | 60M | Peak mem 60M | Verdict | Submitted | Board time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ref | d170ffe | main | 236 s (1 thread) | n/a | 17 GB at 20M | oracle | no | n/a |
| v1 | 3e48662 | main (tag v1) | 1.72 s (1 run) | 9.6–11.1 s | 11.5 GB | pending formal eval | no | n/a |

## Thread registry

| Thread | Role | Branch / worktree | Status |
| --- | --- | --- | --- |
| Orchestrator | coordination, merges, log | main / project root | active |
| [Eval: framework + scoring](t3-thread://v2/555287a9-b949-4858-929b-ee0115137bee/mcp:launch:89ba2159fefcb9d132aac87119da7af32599350130f935c6869fa5fd8158d759) | evaluation framework | eval/framework (worktree from origin/main @ 7f27b6a) | running: building framework v0 + full eval of v1 |

## Entries

### 2026-11-21: setup
- **Orchestrator:** `5226746` infra skeleton, `d170ffe` Python reference (36/36, dev MATCH), `3e48662` Rust v1 (36/36 fixtures native + arm64 + amd64 containers, dev MATCH, diff MATCH on seeds 2–6, 15, 62 and 42). Pushed `main`, tagged `v1`.
- **Orchestrator:** wrote PROTOCOL.md (roles, loop, submission gate). The next step is launching the Eval thread, which builds the framework and formally evaluates v1.
- **Orchestrator:** pointed the T3 project at the git repo so threads get worktrees. Launched the **Eval** thread with the brief: framework v0 (correctness, fuzz, perf, resources, scaling, artifacts, Gates A/B/C verdict, compare tool), then a full eval of `v1`. The machine is reserved for Eval benchmarks until it reports.
- **Orchestrator:** fetched the leaderboard (51 rows shown, 320 teams). **The best practice time is 0.28 s** (APK, Flare, Team Buck); about 12 teams are between 0.28 and 0.31 s. The baseline is 170.69 s. Final scoring rebuilds the team's **best** (or chosen) commit on about 60M events: median of 3 runs, each capped at 3 min. Practice: 2 submissions per hour, and a rejected one doesn't change the best. **Target: < 0.28 s on practice.** v1 is about 1.7 s locally on 20M, so we need roughly 6× more speed.
