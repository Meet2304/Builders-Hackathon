# Native arm64 Linux + strace, to count futex syscalls (lock contention) per phase with NCPU=8.
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends strace && rm -rf /var/lib/apt/lists/*
