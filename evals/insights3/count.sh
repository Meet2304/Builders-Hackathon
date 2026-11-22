#!/bin/sh
# Callgrind Ir per phase for a built commit on a dataset (x86-64-v2, NCPU=1).
# --dump-before=getrusage cuts a profile at every `lap()` phase mark, so the dumps are:
#   .1 startup+lookups  .2 events parsed  .3 clicks parsed  .4 dedup  .5 sessions  .6 written  (final: exit)
# Usage: evals/insights3/count.sh <commit> <dataset dir> <label> [cache]
set -eu
c=${1:?commit}; ds=${2:?dataset}; label=${3:?label}; cache=${4:-}
REPO=$(git rev-parse --show-toplevel)
sha=$(git -C "$REPO" rev-parse "$c" | cut -c1-12)
OUT=${OUT:-$HOME/.cache/insights3}
bin="$OUT/bin/$sha"; [ -x "$bin/sessions" ] || { echo "build $c first"; exit 1; }
run="$OUT/cg/$sha-$label${cache:+-cache}"; rm -rf "$run"; mkdir -p "$run/out"
ds=$(cd "$ds" && pwd -P)
sim=""
# Cascade Lake per-core: L1d 32K 8-way, L1i 32K 8-way, L2 1 MiB 16-way (callgrind's "LL" = L2 here).
[ -n "$cache" ] && sim="--cache-sim=yes --I1=32768,8,64 --D1=32768,8,64 --LL=1048576,16,64"
nice -n 19 docker run --rm --platform linux/amd64 --cpus=2 --memory=${MEM:-8g} \
  -v "$ds":/data:ro -v "$bin":/bin-x:ro -v "$run":/run-x \
  -e NCPU=1 -e DATA_DIR=/data -e OUTPUT_DIR=/run-x/out insights3-cg:latest sh -c "
    valgrind --tool=callgrind --dump-before=getrusage $sim \
      --callgrind-out-file=/run-x/callgrind.out /bin-x/sessions 2> /run-x/stderr.txt
    tail -4 /run-x/stderr.txt"
# out/ kept for a MATCH check against the answer
echo "$run"
