#!/bin/sh
# Build the engine at <commit> for linux/amd64, target-cpu=x86-64-v2, with line tables
# (debug info only: codegen is unchanged) for callgrind attribution.
# Output: $OUT/bin/<sha12>/sessions   (OUT defaults to ~/.cache/insights3)
# Usage: evals/insights3/build.sh <commit>
set -eu
c=${1:?commit}
REPO=$(git rev-parse --show-toplevel)
sha=$(git -C "$REPO" rev-parse "$c" | cut -c1-12)
OUT=${OUT:-$HOME/.cache/insights3}
dst="$OUT/bin/$sha"
[ -x "$dst/sessions" ] && { echo "$dst/sessions (cached)"; exit 0; }
src="$OUT/src/$sha"; rm -rf "$src"; mkdir -p "$src" "$dst"
git -C "$REPO" archive "$sha" Cargo.toml Cargo.lock src | tar -x -C "$src"
nice -n 19 docker run --rm --platform linux/amd64 --cpus=2 \
  -v insights3-cargo:/usr/local/cargo/registry -v insights3-target:/target \
  -v "$src":/work:ro -v "$dst":/out insights3-cg:latest sh -c '
    set -e
    # copy + touch: the shared target dir fingerprints by mtime, and git archive keeps
    # commit-time mtimes, so a later build of an older-dated commit would be "fresh".
    rm -rf /build && cp -r /work /build && cd /build && touch src/*.rs
    export CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUSTFLAGS="-C target-cpu=x86-64-v2"
    export CARGO_PROFILE_RELEASE_DEBUG=line-tables-only CARGO_PROFILE_RELEASE_STRIP=none
    cargo build --release --locked --target x86_64-unknown-linux-gnu 2>&1 | tail -3
    cp /target/x86_64-unknown-linux-gnu/release/sessions /out/sessions'
echo "$sha" > "$dst/commit"
h=$(shasum -a 256 "$dst/sessions" | cut -d' ' -f1); echo "$h" > "$dst/sha256"
for o in "$OUT"/bin/*/sha256; do
  [ "$o" = "$dst/sha256" ] && continue
  if [ "$(cat "$o")" = "$h" ]; then echo "STALE: same binary as $(dirname "$o")"; rm -f "$dst/sessions"; exit 1; fi
done
echo "$h  $dst/sessions"
