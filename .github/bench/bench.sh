#!/bin/bash
# Scorer-like runs: docker_run flags, warm page cache, interleaved reps.
set -u
CPUS=$(nproc); MEM=$(( $(free -g | awk '/Mem:/{print $2}') - 2 ))g
DATA=$PWD/data/seed-42
REPS=${REPS:-3}
mkdir -p logs; : > results.jsonl
AVX=$(grep -q -w avx512f /proc/cpuinfo && echo 1 || echo 0)
RTS="runc runsc"; docker info --format '{{json .Runtimes}}' | grep -q runsc-kvm && RTS="$RTS runsc-kvm"
echo "CPUS=$CPUS MEM=$MEM AVX512=$AVX RTS=$RTS"

run() { # cfg image runtime rep [env...]
  local cfg=$1 img=$2 rt=$3 rep=$4; shift 4
  local out=$(mktemp -d) scr=$(mktemp -d); chmod 777 $out $scr
  local envs=(-e DATA_DIR=/data -e OUTPUT_DIR=/output -e SCRATCH_DIR=/scratch -e HOME=/scratch -e NCPU=$CPUS -e SESSIONS_DEBUG_FAULTS=1)
  for e in "$@"; do envs+=(-e "$e"); done
  local t0=$(date +%s%N)
  docker run --rm --runtime=$rt --network none --read-only --tmpfs /tmp:rw,size=64m,mode=1777 \
    --cap-drop ALL --security-opt no-new-privileges --pids-limit 4096 \
    --cpus $CPUS --memory $MEM --memory-swap $MEM --user 1000:1000 \
    -v $DATA:/data:ro -v $out:/output -v $scr:/scratch "${envs[@]}" ss:$img \
    > logs/$cfg.$rep.out 2> logs/$cfg.$rep.err
  local rc=$? t1=$(date +%s%N)
  local h=$(cd $out && find . -type f | sort | xargs cat 2>/dev/null | md5sum | cut -c1-12)
  local n=$(find $out -type f | wc -l)
  printf '{"cfg":"%s","img":"%s","rt":"%s","rep":%d,"wall":%.4f,"rc":%d,"hash":"%s","nfiles":%d,"env":"%s"}\n' \
    $cfg $img $rt $rep $(echo "($t1-$t0)/1000000000" | bc -l) $rc $h $n "$*" | tee -a results.jsonl
  sudo rm -rf $out $scr
}

# Container start/stop floor: /bin/true in the debian image.
for rep in 1 2 3; do for rt in $RTS; do
  t0=$(date +%s%N); docker run --rm --runtime=$rt --network none --read-only --user 1000:1000 -v $DATA:/data:ro ss:v13 /bin/true; t1=$(date +%s%N)
  printf '{"cfg":"true-%s","img":"v13","rt":"%s","rep":%d,"wall":%.4f,"rc":0,"hash":"","nfiles":0,"env":""}\n' $rt $rt $rep $(echo "($t1-$t0)/1000000000" | bc -l) | tee -a results.jsonl
done; done

IMGS="v8 v13 v13_1"; [ $AVX = 1 ] && IMGS="$IMGS v13_1cl"
# Warm-up (page cache + image layers), not recorded.
docker run --rm --runtime=runc -v $DATA:/data:ro ss:v13 sh -c 'cat /data/* > /dev/null'

echo "== main matrix"
for rep in $(seq 1 $REPS); do
  for img in $IMGS; do for rt in $RTS; do run $img-$rt $img $rt $rep; done; done
done
echo "== levers (lab = v13 src + SESSIONS_INPUT knob), runsc"
for rep in $(seq 1 $REPS); do
  run lab-runsc lab runsc $rep
  run lab-ncpu2x lab runsc $rep NCPU=$((2*CPUS))
  run lab-populate lab runsc $rep SESSIONS_INPUT=populate
  run lab-read lab runsc $rep SESSIONS_INPUT=read
  run lab-largepages lab runsc $rep MIMALLOC_ALLOW_LARGE_OS_PAGES=1
  run lab-eagercommit lab runsc $rep MIMALLOC_ARENA_EAGER_COMMIT=1
  run labstatic-runsc labstatic runsc $rep
  run lab-runc lab runc $rep
  run lab-read-runc lab runc $rep SESSIONS_INPUT=read
done
echo "== cold page cache, runsc"
for rep in 1 2; do
  sync; echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null; run cold-v13_1-runsc v13_1 runsc $rep
  sync; echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null; run cold-lab-read lab runsc $rep SESSIONS_INPUT=read
done
