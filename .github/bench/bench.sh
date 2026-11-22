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

# Check perf availability
HAVE_PERF=0
if command -v perf &>/dev/null; then
  # Try a quick perf stat to see if the kernel allows it
  if perf stat -e instructions true 2>/dev/null; then HAVE_PERF=1; fi
fi
echo "HAVE_PERF=$HAVE_PERF"

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
run_perf() { # cfg image datadir
  local cfg=$1 img=$2 datadir=$3; shift 3
  if [ $HAVE_PERF = 0 ]; then echo "SKIP perf: not available"; return; fi
  local out=$(mktemp -d) scr=$(mktemp -d); chmod 777 $out $scr
  local envs=(-e DATA_DIR=/data -e OUTPUT_DIR=/output -e SCRATCH_DIR=/scratch -e HOME=/scratch -e NCPU=$CPUS)
  # perf stat wrapping the entire docker run (includes container overhead)
  sudo perf stat -e instructions,cycles,branch-misses,cache-misses,page-faults \
    docker run --rm --runtime=runc --network none --read-only --tmpfs /tmp:rw,size=64m,mode=1777 \
    --cap-drop ALL --security-opt no-new-privileges --pids-limit 4096 \
    --cpus $CPUS --memory $MEM --memory-swap $MEM --user 1000:1000 \
    -v $datadir:/data:ro -v $out:/output -v $scr:/scratch "${envs[@]}" ss:$img \
    > logs/perf-$cfg.out 2> logs/perf-$cfg.err
  echo "--- perf stat $cfg ---"
  cat logs/perf-$cfg.err | tail -20
  sudo rm -rf $out $scr
}

# Container start/stop floor
for rep in 1 2 3; do
  t0=$(date +%s%N); docker run --rm --runtime=runc --network none --read-only --user 1000:1000 -v $DATA20:/data:ro ss:v15 /bin/true; t1=$(date +%s%N)
  printf '{"cfg":"true-runc","img":"v15","rt":"runc","rep":%d,"wall":%.4f,"rc":0,"hash":"","nfiles":0,"env":""}\n' $rep $(echo "($t1-$t0)/1000000000" | bc -l) | tee -a results.jsonl
done

# Decide images: use cascadelake if AVX-512, else v3 fallback
if [ $AVX = 1 ]; then
  IMGS="v15 v16"
else
  # Use x86-64-v3 builds if no AVX-512
  IMGS="v15v3 v16v3"
  echo "WARNING: no AVX-512, using x86-64-v3 builds"
fi

# Warm up page cache
docker run --rm --runtime=runc -v $DATA20:/data:ro ss:${IMGS%% *} sh -c 'cat /data/*/* > /dev/null 2>/dev/null; cat /data/*.csv /data/*.json > /dev/null 2>/dev/null' || true

echo "== main matrix: 20M, runc, $REPS reps"
for rep in $(seq 1 $REPS); do
  for img in $IMGS; do
    run ${img}-20m $img $rep $DATA20
  done
done

echo "== PGO A/B: 20M"
for rep in $(seq 1 $REPS); do
  run pgo-20m pgo $rep $DATA20
  run pgooff-20m pgooff $rep $DATA20
done

echo "== 60M runs"
# Warm cache for 60M
docker run --rm --runtime=runc -v $DATA60:/data:ro ss:${IMGS%% *} sh -c 'cat /data/*/* > /dev/null 2>/dev/null; cat /data/*.csv /data/*.json > /dev/null 2>/dev/null' || true
for rep in $(seq 1 3); do
  for img in $IMGS; do
    run ${img}-60m $img $rep $DATA60
  done
done

echo "== levers on v16 (20M)"
V16IMG=${IMGS##* }
for rep in $(seq 1 $REPS); do
  run ${V16IMG}-ncpu2x $V16IMG $rep $DATA20 NCPU=$((2*CPUS))
  run ${V16IMG}-free0 $V16IMG $rep $DATA20 SESSIONS_FREE=0
  run ${V16IMG}-free3 $V16IMG $rep $DATA20 SESSIONS_FREE=3
  run ${V16IMG}-exit $V16IMG $rep $DATA20 SESSIONS_EXIT=normal
done

echo "== perf stat"
for img in $IMGS; do
  run_perf ${img}-20m-perf $img $DATA20
done
run_perf pgo-20m-perf pgo $DATA20

echo "== done"
