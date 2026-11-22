#!/bin/bash
# Scorer-like runs: runc only (the scorer uses real Linux, not gVisor).
# v15, v16, PGO on/off. Interleaved reps. perf stat if available.
set -u
CPUS=$(nproc); MEM=$(( $(free -g | awk '/Mem:/{print $2}') - 2 ))g
DATA20=$PWD/data/seed-42
DATA60=$PWD/data/seed-99
REPS=${REPS:-5}
mkdir -p logs; : > results.jsonl
AVX=$(grep -q -w avx512f /proc/cpuinfo && echo 1 || echo 0)
echo "CPUS=$CPUS MEM=$MEM AVX512=$AVX REPS=$REPS"

run() { # cfg image rep datadir [env...]
  local cfg=$1 img=$2 rep=$3 datadir=$4; shift 4
  local out=$(mktemp -d) scr=$(mktemp -d); chmod 777 $out $scr
  local envs=(-e DATA_DIR=/data -e OUTPUT_DIR=/output -e SCRATCH_DIR=/scratch -e HOME=/scratch -e NCPU=$CPUS -e SESSIONS_DEBUG_FAULTS=1)
  for e in "$@"; do envs+=(-e "$e"); done
  local t0=$(date +%s%N)
  docker run --rm --runtime=runc --network none --read-only --tmpfs /tmp:rw,size=64m,mode=1777 \
    --cap-drop ALL --security-opt no-new-privileges --pids-limit 4096 \
    --cpus $CPUS --memory $MEM --memory-swap $MEM --user 1000:1000 \
    -v $datadir:/data:ro -v $out:/output -v $scr:/scratch "${envs[@]}" ss:$img \
    > logs/$cfg.$rep.out 2> logs/$cfg.$rep.err
  local rc=$? t1=$(date +%s%N)
  local h=$(cd $out && find . -type f | sort | xargs cat 2>/dev/null | md5sum | cut -c1-12)
  local n=$(find $out -type f | wc -l)
  printf '{"cfg":"%s","img":"%s","rt":"runc","rep":%d,"wall":%.4f,"rc":%d,"hash":"%s","nfiles":%d,"env":"%s"}\n' \
    $cfg $img $rep $(echo "($t1-$t0)/1000000000" | bc -l) $rc $h $n "$*" | tee -a results.jsonl
  sudo rm -rf $out $scr
}

# perf stat wrapper (runs perf stat around the docker run; requires privileged)

echo "== round 3: v16 vs v17pre, 20M, $REPS interleaved reps"
REPS=8
docker run --rm --runtime=runc -v $DATA20:/data:ro ss:v16 sh -c 'cat /data/*/* > /dev/null 2>/dev/null; cat /data/*.csv /data/*.json > /dev/null 2>/dev/null' || true
for rep in $(seq 1 $REPS); do
  run v16-20m v16 $rep $DATA20
  run v17pre-20m v17pre $rep $DATA20
done
echo "== 60M"
docker run --rm --runtime=runc -v $DATA60:/data:ro ss:v16 sh -c 'cat /data/*/* > /dev/null 2>/dev/null; cat /data/*.csv /data/*.json > /dev/null 2>/dev/null' || true
for rep in 1 2 3 4; do
  run v16-60m v16 $rep $DATA60
  run v17pre-60m v17pre $rep $DATA60
done
echo DONE
