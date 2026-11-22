#!/bin/sh
# Futex syscalls per phase (native arm64 Linux, strace) for a Linux arm64 binary.
# Lock contention is architecture-neutral at the syscall level: Rust's std Mutex only enters
# the kernel (futex WAIT/WAKE) when contended, on x86 and arm64 alike. Under gVisor each such
# syscall is a trip into the sandbox, which is why it matters for the board.
# Usage: evals/insights3/futex.sh <linux-arm64 sessions binary> <dataset> <label> [ncpu=8]
set -eu
bin=$(cd "$(dirname "$1")" && pwd -P)/$(basename "$1"); ds=$(cd "$2" && pwd -P); label=$3; ncpu=${4:-8}
OUT=${OUT:-$HOME/.cache/insights3}; run="$OUT/futex/$label"; rm -rf "$run"; mkdir -p "$run/out"
nice -n 19 docker run --rm --cpus=2 --memory=12g --cap-add=SYS_PTRACE --security-opt seccomp=unconfined \
  -v "$ds":/data:ro -v "$bin":/sessions:ro -v "$run":/run-x -e NCPU=$ncpu -e DATA_DIR=/data -e OUTPUT_DIR=/run-x/out \
  insights3-strace:latest sh -c 'strace -f -qq -e trace=futex,write -e signal=none -o /run-x/trace.txt /sessions 2> /run-x/stderr.txt'
rm -rf "$run/out"
python3 - "$run" <<'PY'
import re, sys, collections, json
run = sys.argv[1]
names = ["lookups", "events", "clicks", "dedup", "sessions", "write"]
ph = 0; cnt = collections.Counter(); addrs = collections.defaultdict(collections.Counter); ops = collections.defaultdict(collections.Counter)
for line in open(f"{run}/trace.txt", errors="replace"):
    if " write(2," in line and "s] " in line:
        ph += 1; continue
    m = re.search(r"futex\((0x[0-9a-f]+), (FUTEX_\w+)", line)
    if m and "resumed" not in line:
        p = names[ph] if ph < len(names) else "exit"
        cnt[p] += 1; addrs[p][m.group(1)] += 1; ops[p][m.group(2)] += 1
res = {p: {"futex": cnt[p], "distinct_addrs": len(addrs[p]), "ops": dict(ops[p]),
           "top_addrs": addrs[p].most_common(3)} for p in names + ["exit"]}
json.dump(res, open(f"{run}/futex.json", "w"), indent=1)
for p, r in res.items():
    print(f"{p:9s} futex={r['futex']:>8,} addrs={r['distinct_addrs']:>4} {r['ops']}")
PY
