# CLAUDE.md

Hackathon entry, Builders Buildathon, Databricks "Shopping Sessions" track. The spec is `docs/rules.md` and always wins. The plan is `docs/PLAN.md`.

- **Score = container wall-clock time on 8 vCPU / 24 GB / no network. Output must be exactly right or there's no score.** Every perf change must keep `make fixtures-local` at 36/36 and `make run-dev-local check-dev` at MATCH.
- The engine is Rust in `src/main.rs`. The Python oracle is in `reference/reference.py` and favours clarity over speed.
- Rust is installed via Homebrew rustup: if `cargo` is not found, `export PATH="/opt/homebrew/opt/rustup/bin:$PATH"`.
- Python tooling lives in `.venv` (`.venv/bin/python`). Never install test deps into the image.
- Runtime constraints: root fs is read-only (write only to `$OUTPUT_DIR`, `$SCRATCH_DIR`, and 64 MB `/tmp`). The process runs as uid 1000, with at most 4,096 threads. stdout is capped at 50 MB, so log with `eprintln!`.
- Local amd64 images are built with `X86_CPU=x86-64-v2` because emulation has no AVX-512. The scorer build uses the Dockerfile default, `cascadelake`. Never make a build script depend on the CPU flag.
- `data/` (dev set, dev answer, extra seeds) is gitignored. The repo must stay under 50 MB with no data.
- Databricks is the sponsor only. Nothing here runs on a Databricks workspace.
