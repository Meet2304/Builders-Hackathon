# Orchestration protocol

This is how the threads work together to improve the pipeline, one version at a time, until we lead the board.
Spec: [../rules.md](../rules.md). Benchmarks so far: [../BENCH.md](../BENCH.md). Running log: [LOG.md](LOG.md).

## Roles

| Thread | Owns (writes only here) | Branch | Job |
| --- | --- | --- | --- |
| **Orchestrator** | `docs/orchestration/`, merges to `main` | `main` | Runs the loop, merges, keeps the log, applies the submission gate, talks to the user |
| **Eval** | `evals/`, the `eval*` Makefile targets | `eval/framework` | Builds and grows the evaluation framework; evaluates each candidate; writes result JSON |
| **Analyst** | `evals/insights/` | `analysis` | Reads results and writes insights: wins, failures, next method moves, framework gaps |
| **Method** | `src/`, `Cargo.*`, `Dockerfile`, `docker/` | `method/vN` | Builds the next pipeline version from the insights |

Never edit another role's files. If you need a change there, say so in your final message, and the Orchestrator routes it.
Only the Orchestrator merges into `main` or pushes `main`. Commit to your own branch. All worktrees share one `.git`, so there's no need to push branches.

## Shared resources (absolute paths)

```
ROOT=/Users/meet/Meet/Projects_Ad Astra/Project_3_Builders Hackathon/Builders-Hackathon
$ROOT/data/      datasets + cached expected answers (gitignored). Only Eval creates or changes datasets.
$ROOT/.venv/     Python with polars + pyarrow
$ROOT/tools/generator/target/release/generate
```
In a worktree, link them in: `ln -s "$ROOT/data" data; ln -s "$ROOT/.venv" .venv`. Rust: `export PATH="/opt/homebrew/opt/rustup/bin:$PATH"`.

## The loop (strictly sequential, so benchmarks run on a quiet machine)

```
Method builds vN on method/vN  ──►  Orchestrator: smoke check (fixtures + dev MATCH), tag candidate
        ▲                                         │
        │                                         ▼
Orchestrator sends insights            Eval runs the full suite on vN → evals/results/vN.json + verdict
        ▲                                         │
        │                                         ▼
Analyst writes evals/insights/vN.md  ◄──  Orchestrator merges results, logs, applies the gate
```
Only Eval runs timed benchmarks, and only while no other thread is building or testing. The Orchestrator enforces this by never running two loop stages at once.

## Stderr phase-timing contract (Method must keep it)
The pipeline prints cumulative phase marks to stderr: `[  1.234s] phase name (optional detail)`. Eval parses these. Method may rename, add or split phases, but must keep the format. **Nothing goes to stdout.**

## Submission gate

The eval framework computes the verdict and writes it to the result JSON.

**Gate A, correctness (all required):**
- 36/36 fixtures, native **and** in the amd64 container
- dev MATCH, native **and** in the amd64 container
- Differential MATCH against the Python reference on every dataset in the suite, including the Feb 29 2028 seeds and the 20M seed
- Fuzz/adversarial suite MATCH (once Eval has built it)
- Deterministic: the canonicalized output hash is identical across runs

**Gate B, constraints (all required; set by the scorer's limits, with margin):**
- 60M peak memory ≤ 16 GB. The box has 24 GB with no swap, and page cache counts against the cgroup.
- 60M local wall time ≤ 30 s. The hard cap is 180 s and the scorer is about the same speed.
- stdout < 1 MB, threads < 1,000, writes only to the output and scratch dirs (enforced by the read-only container)
- Image builds from clean. Repo < 50 MB with no data in it.

**Gate C, worth spending a submission (2 per hour):**
- The 20M median (≥ 5 runs) beats the current best *submitted* version by ≥ 5% **and** by more than 2× the pooled standard deviation. Until anything has been submitted, compare against the best SUBMIT-READY version.

**Verdict:**
- `REJECT`: A or B fails. Never merged as the default.
- `HOLD`: correct, but not enough faster.
- `SUBMIT-READY`: all three gates pass. The Orchestrator notifies the user. **Only the user submits.**

**Target to beat (as of 2026-11-21):** 0.28 s on the 20M practice board. The final uses the team's *best* (or chosen) commit, so extra correct submissions never hurt.

Once real board times exist, Eval calibrates a local→scorer ratio, and Gate C plus the "beat the board" target use estimated scorer time.
