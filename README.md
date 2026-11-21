# Builders Hackathon: Shopping Sessions (Databricks track)

This repo is our entry for the [Shopping Sessions](https://www.joinbuilders.org/buildathon/tracks/shopping-sessions) track. The pipeline turns dirty click-stream CSVs into two exact daily Parquet tables. **Score = container run time.**

- Spec: [docs/rules.md](docs/rules.md) (rules.md wins over everything else)
- Plan: [docs/PLAN.md](docs/PLAN.md)
- Engine: Rust (`src/main.rs`). The `CMD` is the binary, run with no arguments.

## Setup (once)

```sh
brew install rustup && rustup default stable      # Rust toolchain
make setup                                        # .venv for test scripts, builds generator, makes data/dev
unzip ../context/dev-answer.zip -d data/          # the published dev answer → data/dev-answer/
```

## Loops

| Command | What it does |
| --- | --- |
| `make fixtures-local` | Native binary on all 36 fixtures (fastest loop) |
| `make run-dev-local check-dev` | Native binary on the 1M dev set, timed, then an exact diff with the answer |
| `make build-native fixtures-native` | arm64 image with the scorer's docker flags |
| `make fixtures` | **amd64** image (emulated, slow). Run it before every submission |
| `make run-dev` / `make run-dev-native` | Image on the dev set, timed |
| `make gen SEED=7 EVENTS=200000` | Extra dataset → `data/seed-7` |
| `make diff-seed SEED=7` | Rust vs the Python reference on that seed |
| `make ref-fixtures` / `make ref-dev` | Check the reference itself |

Docker Desktop: give it at least 26 GB of memory (Settings → Resources) before you run full-size data with `MEM=24g`.

## Layout

```
src/main.rs            the pipeline
reference/             plain-Python correctness oracle (phase 1)
fixtures/              the organizers' 36 edge cases (input/ + expected/)
scripts/               run_fixtures.py, compare.py, docker_run.sh (from the starter)
tools/generator/       the organizers' dataset generator (Rust)
docker/cargo-build.sh  build helper used by the Dockerfile
data/                  gitignored: dev/, dev-answer/, seed-N/
```

## Submitting

1. Make sure the repo is public, the Dockerfile is at the root, there's no data, and it's under 50 MB.
2. `make fixtures` (amd64): 36/36. `make run-dev check-dev`: MATCH.
3. Push and submit the commit SHA on the track page. You get 2 practice submissions per hour.
