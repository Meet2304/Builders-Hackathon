#!/bin/sh
# Builds the release binary and copies it to /sessions.
# On amd64, X86_CPU tunes codegen (default cascadelake: the scorer's Xeons have AVX-512).
# The flag is passed per-target, so build scripts stay generic and run under emulation.
set -eu
if [ "${TARGETARCH:-}" = "amd64" ]; then
  export CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUSTFLAGS="-C target-cpu=${X86_CPU:-cascadelake}"
  cargo build --release --locked --target x86_64-unknown-linux-gnu
  out=target/x86_64-unknown-linux-gnu/release
else
  cargo build --release --locked
  out=target/release
fi
[ "${1:-}" = "--deps-only" ] || cp "$out/sessions" /sessions
