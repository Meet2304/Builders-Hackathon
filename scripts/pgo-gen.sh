#!/bin/sh
# Regenerate pgo/x86.profdata for the current src/ (run after any engine change).
#
# 1. Builds an instrumented linux/amd64 binary (-Cprofile-generate) in the same pinned
#    rust image the Dockerfile uses, at target-cpu=x86-64-v2 (local emulation has no AVX-512).
# 2. Runs it on the dev set and a 20M seed at NCPU=8 and NCPU=1 (SESSIONS_EXIT=normal:
#    the default _exit would skip the atexit hook that writes the profile).
# 3. Merges the raw profiles with that toolchain's llvm-profdata -> pgo/x86.profdata.
#
# The build paths (/src, /src/target, /usr/local/cargo) match the Dockerfile's, so
# function names in the profile match the scorer build. Cargo 1.100 does not hash
# RUSTFLAGS into -Cmetadata, so the different target-cpu / profile flags don't rename symbols.
#
# Usage: scripts/pgo-gen.sh [DATA_ROOT]   (DATA_ROOT holds dev/ and seed-42/; default ./data)
#   PGO_SETS="dev seed-42" overrides the datasets; PGO_NCPUS="8 1" the thread counts.
set -eu
REPO=$(cd "$(dirname "$0")/.." && pwd)
DATA_ROOT=$(cd "${1:-$REPO/data}" && pwd)
SETS=${PGO_SETS:-dev seed-42}
NCPUS=${PGO_NCPUS:-8 1}
IMAGE_RUST=$(sed -n 's/^FROM \(rust:[^ ]*\) AS build$/\1/p' "$REPO/Dockerfile")
[ -n "$IMAGE_RUST" ] || { echo "cannot find the rust FROM line in Dockerfile" >&2; exit 1; }
work=$(mktemp -d "${TMPDIR:-/tmp}/pgo-gen.XXXXXX")
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/src" "$work/raw" "$REPO/pgo"
# Copy exactly what the Dockerfile builds from.
cp -R "$REPO/Cargo.toml" "$REPO/Cargo.lock" "$REPO/src" "$work/src/"
set --   # data mounts as positional args: DATA_ROOT may contain spaces
for s in $SETS; do set -- "$@" -v "$DATA_ROOT/$s:/data/$s:ro"; done
echo "pgo-gen: $IMAGE_RUST, sets: $SETS, ncpus: $NCPUS" >&2
docker run --rm --platform linux/amd64 \
  -v pgo-x86-cargo:/usr/local/cargo/registry -v pgo-x86-target:/src/target \
  -v "$work/src":/in:ro -v "$work/raw":/raw -v "$REPO/pgo":/pgo "$@" \
  -e SETS="$SETS" -e NCPUS="$NCPUS" \
  "$IMAGE_RUST" sh -ec '
    cd /src && rm -rf src && cp -R /in/Cargo.toml /in/Cargo.lock /in/src . && touch src/main.rs
    rustup component add llvm-tools >/dev/null 2>&1
    PROFDATA=$(rustc --print sysroot)/lib/rustlib/x86_64-unknown-linux-gnu/bin/llvm-profdata
    export CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUSTFLAGS="-C target-cpu=x86-64-v2 -Cprofile-generate=/raw"
    t0=$(date +%s)
    cargo build --release --locked --target x86_64-unknown-linux-gnu 2>&1 | tail -2
    echo "instrumented build: $(( $(date +%s) - t0 ))s" >&2
    bin=/src/target/x86_64-unknown-linux-gnu/release/sessions
    for s in $SETS; do for n in $NCPUS; do
      rm -rf /tmp/o /tmp/s && mkdir -p /tmp/o /tmp/s
      t0=$(date +%s)
      LLVM_PROFILE_FILE=/raw/$s-$n-%p-%m.profraw DATA_DIR=/data/$s OUTPUT_DIR=/tmp/o SCRATCH_DIR=/tmp/s \
        NCPU=$n MEM_GB=24 SESSIONS_EXIT=normal $bin >/dev/null
      echo "ran $s NCPU=$n: $(( $(date +%s) - t0 ))s" >&2
    done; done
    rm -rf /tmp/o /tmp/s
    $PROFDATA merge -o /pgo/x86.profdata /raw/*.profraw
    $PROFDATA show /pgo/x86.profdata | tail -4 >&2'
ls -l "$REPO/pgo/x86.profdata"
