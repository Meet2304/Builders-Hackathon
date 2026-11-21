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

## Entries

### 2026-11-21: setup
- **Orchestrator:** `5226746` infra skeleton, `d170ffe` Python reference (36/36, dev MATCH), `3e48662` Rust v1 (36/36 fixtures native + arm64 + amd64 containers, dev MATCH, diff MATCH on seeds 2–6, 15, 62 and 42). Pushed `main`, tagged `v1`.
- **Orchestrator:** wrote PROTOCOL.md (roles, loop, submission gate). The next step is launching the Eval thread, which builds the framework and formally evaluates v1.
