#!/bin/sh
# Builds the release binary and copies it to /sessions.
# On amd64, X86_CPU tunes codegen (default cascadelake: the scorer's Xeons have AVX-512).
# The flag is passed per-target, so build scripts stay generic and run under emulation.
# On amd64 the build also uses the committed x86 PGO profile (pgo/x86.profdata, made by
# scripts/pgo-gen.sh) unless PGO=off. Functions whose code changed since the profile was
# taken just get no profile data (mismatch warnings are silenced), so output never depends
# on it. arm64 (local Mac loop) builds without PGO.
set -eu
if [ "${TARGETARCH:-}" = "amd64" ]; then
  flags="-C target-cpu=${X86_CPU:-cascadelake}"
  if [ "${PGO:-on}" != "off" ] && [ -f /src/pgo/x86.profdata ]; then
    flags="$flags -Cprofile-use=/src/pgo/x86.profdata -Cllvm-args=-no-pgo-warn-mismatch"
  fi
  export CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUSTFLAGS="$flags"
  cargo build --release --locked --target x86_64-unknown-linux-gnu
  out=target/x86_64-unknown-linux-gnu/release
else
  cargo build --release --locked
  out=target/release
fi
[ "${1:-}" = "--deps-only" ] || cp "$out/sessions" /sessions
