#!/usr/bin/env bash
# Run a local Linux/arm64 ELF or an existing arm64 timing image against a dataset.
set -euo pipefail
if [[ $# != 2 ]]; then
  echo "Usage: $0 <linux-arm64-binary-or-timing-image> <dataset-directory>" >&2
  exit 2
fi
here=$(cd "$(dirname "$0")" && pwd)
test -f "$2/manifest.json" || { echo "Missing $2/manifest.json" >&2; exit 1; }
base=${RUNSC_TIMING_IMAGE:-sessions-eval:5b7bcc239556-arm64-faults}
bundle=${GVISOR_DIR:-/tmp/builders-gvisor-20261116}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
if [[ ! -x "$bundle/runsc" ]]; then
  url=https://storage.googleapis.com/gvisor/releases/release/20261116/aarch64
  mkdir -p "$work/bundle"
  (
    cd "$work/bundle"
    curl -fsSLO "$url/gvisor.tar.zstd"
    curl -fsSLO "$url/gvisor.tar.zstd.sha512"
    shasum -a 512 -c gvisor.tar.zstd.sha512 >&2
    tar -xf gvisor.tar.zstd
  )
  # Publish only the complete bundle, keeping the temporary copy if another invocation won.
  mkdir -p "$(dirname "$bundle")"
  if [[ ! -e "$bundle" ]]; then mv "$work/bundle" "$bundle"; else bundle="$work/bundle"; fi
fi
if [[ -f "$1" ]]; then
  desc=$(file -b "$1")
  if [[ "$desc" != *ELF* || "$desc" != *aarch64* ]]; then
    echo "Expected a Linux/arm64 ELF. file reports: $desc" >&2
    exit 2
  fi
  image="critpath-timing:$(shasum -a 256 "$1" | cut -c1-24)"
  mkdir "$work/image"
  cp "$1" "$work/image/sessions"
  printf 'ARG BASE=sessions-eval:5b7bcc239556-arm64-faults\nFROM ${BASE}\nCOPY --chmod=0755 sessions /app/sessions\n' > "$work/image/Dockerfile"
  docker build --platform linux/arm64 --build-arg "BASE=$base" -t "$image" "$work/image" >&2
else
  image=$1
  docker image inspect "$image" >/dev/null
fi
python3 "$here/probe.py" --image "$image" --data "$2" --gvisor "$bundle" \
  --pairs "${RUNSC_PAIRS:-3}" | tee "${RUNSC_JSONL:-$work/runs.jsonl}" | python3 -u "$here/summary.py"
