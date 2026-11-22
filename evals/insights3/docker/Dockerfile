# x86 instruction-count tooling: Rust toolchain + valgrind (callgrind) on linux/amd64.
# Built and run under emulation on the Mac; wall time is meaningless, Ir counts are not.
FROM --platform=linux/amd64 rust:1-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends valgrind python3 binutils git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
ENV CARGO_TARGET_DIR=/target
WORKDIR /work
