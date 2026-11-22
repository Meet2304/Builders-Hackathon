"""Informational Linux page-fault probe with input staged on a Docker volume."""
from __future__ import annotations

import re
import subprocess
import time
import uuid
from contextlib import contextmanager

from .bench_lock import benchmark_lock
from .common import DATA, log
from .gates import FAST_RUNS, is_fast
from .measure import ContaminatedSample, parse_phases, sample_load, summarize

GIB = 2**30
TIMING = re.compile(r"^eval_time ([0-9.]+) (\d+) (\d+) (\d+) ([0-9.]+) ([0-9.]+)$", re.MULTILINE)
WALL_NS = re.compile(r"^eval_wall_ns (\d+)$", re.MULTILINE)
THP_PATH = "/sys/kernel/mm/transparent_hugepage/enabled"
THP_MODE = re.compile(r"\[(always|madvise|never)\]")
THP_CONTROL_IMAGE = "debian:bookworm-slim"
PROBE_SCRIPT = r"""
if [ -r /sys/kernel/mm/transparent_hugepage/enabled ]; then
    printf 'eval_thp '
    cat /sys/kernel/mm/transparent_hugepage/enabled
fi
printf 'eval_page_bytes '
getconf PAGESIZE
vmstat() {
    awk '$1 == "thp_fault_alloc" || $1 == "thp_fault_fallback" {print "'"$1"'", $1, $2}' /proc/vmstat
}
vmstat eval_vm_before
pid_file=/scratch/eval_pid
peak_file=/scratch/eval_peak
# Use a wrapper that reports its own PID before exec, so smaps is sampled for the candidate.
start=$(date +%s%N)
/usr/bin/time -f 'eval_time %e %R %F %M %U %S' /bin/sh -c 'echo "$$" > "$1"; exec /app/sessions' sh "$pid_file" &
timer=$!
(
    while [ ! -s "$pid_file" ] && kill -0 "$timer" 2>/dev/null; do sleep 0.01; done
    [ -s "$pid_file" ] || exit 0
    read -r pid < "$pid_file"
    anon=0; huge=0
    while kill -0 "$pid" 2>/dev/null && [ -r "/proc/$pid/smaps_rollup" ]; do
        values=$(awk '/^Anonymous:/ {a=$2; found=1} /^AnonHugePages:/ {h=$2}
                     END {if (found) print a+0, h+0}' "/proc/$pid/smaps_rollup" 2>/dev/null) || break
        [ -n "$values" ] || break
        set -- $values
        [ "$1" -le "$anon" ] || anon=$1
        [ "$2" -le "$huge" ] || huge=$2
        printf 'eval_smaps %s %s\n' "$anon" "$huge" > "$peak_file"
        sleep 0.1
    done
) &
sampler=$!
wait "$timer"
status=$?
end=$(date +%s%N)
wait "$sampler"
printf 'eval_wall_ns %s\n' "$((end - start))" >&2
[ ! -s "$peak_file" ] || cat "$peak_file"
vmstat eval_vm_after
if [ -r /sys/fs/cgroup/memory.peak ]; then
    printf 'eval_cgroup_peak '
    cat /sys/fs/cgroup/memory.peak
    awk '$1 == "oom_kill" {print "eval_oom_kills", $2}' /sys/fs/cgroup/memory.events
fi
exit "$status"
"""
COLD_PREP = r"""
set -eu
sync -f /data
find /data -type f -exec sh -ec '
  for file do dd if="$file" iflag=nocache count=0 status=none; done
' sh {} +
resident=$(find /data -type f -exec fincore -b -n -o RES {} +)
printf '%s\n' "$resident" | awk '{bytes += $1} END {printf "%.0f\n", bytes}'
"""


@contextmanager
def thp_madvise(call, platform, result):
    prefix = ("run", "--rm", "--platform", platform, "--privileged", "--network", "none",
              "--entrypoint", "/bin/sh", THP_CONTROL_IMAGE, "-c")

    def control(mode=None):
        script = 'if [ "$#" -gt 1 ]; then printf "%s\n" "$2" > "$1" || exit; fi; cat "$1"'
        p = call(*prefix, script, "sh", THP_PATH, *([mode] if mode else []), timeout=30, check=True)
        match = THP_MODE.search(p.stdout)
        if not match or (mode and match.group(1) != mode):
            raise RuntimeError(f"could not verify Docker VM THP mode {mode or ''}")
        return match.group(1)

    previous = control()
    result["thp_previous"] = previous
    try:
        control("madvise")
        result["thp_policy"] = "madvise"
        yield
    finally:
        try:
            result["thp_restored"] = control(previous)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            log(f"ERROR: Docker VM THP restoration to {previous} failed")
            raise


@benchmark_lock()
def probe_linux(image: dict, docker: dict, candidates: list[tuple[str, int]], *, cold: bool = False,
                timed_runs: int | None = None, event_lines: int = 0, baseline_image: dict | None = None,
                before_timing=None, memory_check: bool = False) -> dict:
    """Try candidate datasets in descending size, falling back when the VM cannot run one."""
    vm_budget_gib = min(24, docker["mem_bytes"] // GIB - 1)
    budget_gib = 22 if memory_check else (24 if timed_runs else vm_budget_gib)
    result = {"status": "unavailable", "mem_gib": budget_gib, "attempts": [],
              "input_storage": "Docker named volume", "thp_policy": "VM default"}
    if vm_budget_gib < (22 if memory_check else 2) or not candidates:
        result["reason"] = "insufficient Docker VM memory or no datasets"
        return result

    def call(*args, timeout=180, **kw):
        return subprocess.run(["docker", *args], timeout=timeout, capture_output=True, text=True, **kw)

    def time_image(base):
        tag = base["tag"] + "-faults"
        dockerfile = (f"FROM {base['tag']}\nUSER root\n"
                      "RUN apt-get update && apt-get install -y --no-install-recommends time "
                      "&& rm -rf /var/lib/apt/lists/*\n")
        log(f"Linux timing: preparing GNU time image based on {base['tag']}")
        p = call("build", "--platform", base["platform"], "-t", tag, "-", input=dockerfile, timeout=300)
        if p.returncode:
            raise RuntimeError(p.stderr[-1500:])
        return tag

    try:
        tag = time_image(image)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
        result["reason"] = str(e)
        return result
    baseline_tag = None
    if baseline_image:
        try:
            baseline_tag = time_image(baseline_image)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
            result["baseline_error"] = str(e)

    def stage_and_run(dataset):
        token = f"sessions-eval-proxy-{uuid.uuid4().hex[:12]}"
        container, stage = f"{token}-run", f"{token}-stage"
        mount = f"type=volume,src={token},dst=/data"
        try:
            call("volume", "create", token, check=True)
            incoming = f"type=bind,src={(DATA / dataset).resolve()},dst=/incoming,readonly"
            call("run", "--rm", "--platform", image["platform"], "--name", stage, "--network", "none",
                 "--mount", mount, "--mount", incoming, "--entrypoint", "/bin/cp", tag,
                 "-r", "/incoming/.", "/data/", timeout=300, check=True)
            flags = ["run", "--rm", "--name", container, "--platform", image["platform"], "--network", "none",
                     "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                     "--pids-limit", "4096", "--cpus", "8", "--memory", f"{budget_gib}g",
                     "--memory-swap", f"{budget_gib}g", "--user", "1000:1000", "--mount", mount + ",readonly",
                     "--tmpfs", "/output:mode=1777", "--tmpfs", "/scratch:mode=1777",
                     "--tmpfs", "/tmp:size=64m,mode=1777",
                     "-e", "DATA_DIR=/data", "-e", "OUTPUT_DIR=/output", "-e", "SCRATCH_DIR=/scratch",
                     "-e", "HOME=/scratch", "-e", "NCPU=8", "-e", f"MEM_GB={budget_gib}", "-e", "LC_ALL=C",
                     "--entrypoint", "/bin/sh"]

            def sample(run_tag):
                load = sample_load()
                start = time.perf_counter()
                run = call(*flags, run_tag, "-c", PROBE_SCRIPT, timeout=120)
                wall = time.perf_counter() - start
                match = TIMING.search(run.stderr)
                cgroup = re.search(r"^eval_cgroup_peak (\d+)$", run.stdout, re.MULTILINE)
                oom = re.search(r"^eval_oom_kills (\d+)$", run.stdout, re.MULTILINE)
                if run.returncode or not match:
                    return {"error": f"exit {run.returncode}: {run.stderr[-600:]}", "returncode": run.returncode,
                            "oom_kills": int(oom.group(1)) if oom else None, "load_before": load}
                elapsed, minor, major, rss, user, sys = match.groups()
                ns = WALL_NS.search(run.stderr)
                if timed_runs and not ns:
                    return {"error": "missing inside-container wall clock"}
                thp = re.search(r"^eval_thp (.+)$", run.stdout, re.MULTILINE)
                active = THP_MODE.search(thp.group(1)) if thp else None
                if not active or active.group(1) != "madvise":
                    return {"error": "sample did not run under THP madvise"}
                page = re.search(r"^eval_page_bytes (\d+)$", run.stdout, re.MULTILINE)
                smaps = re.search(r"^eval_smaps (\d+) (\d+)$", run.stdout, re.MULTILINE)
                vmstat = {(step, name): int(value) for step, name, value in re.findall(
                    r"^eval_vm_(before|after) (thp_fault_\w+) (\d+)$", run.stdout, re.MULTILINE)}
                phases = parse_phases(run.stderr)
                process_s = int(ns.group(1)) / 1e9 if ns else float(elapsed)
                return {"process_wall_s": process_s, "load_before": load, "user_s": float(user), "sys_s": float(sys),
                        "container_wall_s": round(wall, 4),
                        "minor_faults": int(minor), "major_faults": int(major), "max_rss_bytes": int(rss) * 1024,
                        "thp_mode": active.group(1), "cgroup_peak_bytes": int(cgroup.group(1)) if cgroup else None,
                        "peak_anon_bytes": int(smaps.group(1)) * 1024 if smaps else None,
                        "peak_anon_huge_bytes": int(smaps.group(2)) * 1024 if smaps else None,
                        "oom_kills": int(oom.group(1)) if oom else None,
                        "exit_tail_s": max(process_s - phases[-1]["at_s"], 0) if phases else None,
                        **{key: vmstat["after", key] - vmstat["before", key]
                           for key in ("thp_fault_alloc", "thp_fault_fallback")
                           if ("before", key) in vmstat and ("after", key) in vmstat},
                        "page_bytes": int(page.group(1)) if page else None, "phases": phases}

            if memory_check:
                run = sample(tag)
                return run if "error" in run else {"sample": run}
            if cold:
                # The staging files belong to root. Run fincore as their owner to get real residency.
                prep = call("run", "--rm", "--platform", image["platform"], "--name", stage, "--network", "none",
                            "--read-only", "--mount", mount + ",readonly", "--entrypoint", "/bin/sh", tag,
                            "-c", COLD_PREP, timeout=120, check=True)
                resident_bytes = int(prep.stdout.strip())
                if resident_bytes:
                    return {"error": f"{resident_bytes} input bytes still resident after eviction"}
                run = sample(tag)
                return run if "error" in run else {"sample": run, "resident_input_bytes_before": resident_bytes}
            load = before_timing() if before_timing else None
            warmup = sample(tag)
            if "error" in warmup:
                return warmup
            if not timed_runs:
                run = sample(tag)
                return run if "error" in run else {"warmup": warmup, "sample": run}
            return timed_samples(sample, tag, baseline_tag, warmup, timed_runs, event_lines, load)
        except subprocess.CalledProcessError as e:
            return {"error": (e.stderr or str(e))[-800:]}
        except (OSError, subprocess.TimeoutExpired, ContaminatedSample) as e:
            return {"error": str(e)}
        finally:
            # Also remove containers left running by a timed-out Docker client.
            for args in (("rm", "-f", stage, container), ("volume", "rm", token)):
                try:
                    call(*args, timeout=20)
                except (OSError, subprocess.TimeoutExpired) as e:
                    log(f"Linux proxy cleanup for {token}: {e}")

    try:
        with thp_madvise(call, image["platform"], result):
            for dataset, footprint in candidates:
                if footprint + GIB > vm_budget_gib * GIB:
                    result["attempts"].append({"dataset": dataset, "error": "native footprint leaves <1 GiB headroom"})
                    continue
                log(f"Linux proxy: staging {dataset} in a named volume (memory limit {budget_gib} GiB)")
                attempt = stage_and_run(dataset)
                if "sample" in attempt or "runs" in attempt:
                    result.update(status="ok", dataset=dataset, **attempt)
                    break
                result["attempts"].append({"dataset": dataset, **attempt})
    except (OSError, RuntimeError, subprocess.SubprocessError) as e:
        if result.get("thp_previous") and not result.get("thp_restored"):
            raise RuntimeError(f"could not restore Docker VM THP mode to {result['thp_previous']}") from e
        result.update(status="unavailable", reason=str(e))
    return result


def timed_samples(sample, candidate, baseline, warmup, runs, event_lines, load):
    result = {"warmup": warmup, "load_before": load, "event_lines": event_lines}
    if baseline:
        result["baseline_warmup"] = sample(baseline)
        if "error" in result["baseline_warmup"]:
            result["baseline_error"] = result["baseline_warmup"]["error"]
            baseline = None
    samples = {tag: [] for tag in (candidate, baseline) if tag}
    target = runs
    for i in range(max(runs, FAST_RUNS)):
        if i >= target:
            break
        order = list(samples) if i % 2 == 0 else list(reversed(samples))
        pair = {tag: sample(tag) for tag in order}
        if any("error" in run for run in pair.values()):
            if "error" in pair[candidate]:
                return pair[candidate]
            # Continue measuring the candidate, but the incomplete baseline series is unpaired.
            result["baseline_error"] = pair[baseline]["error"]
            del samples[baseline]
            baseline = None
        for tag in samples:
            run = pair[tag]
            if event_lines:
                for metric in ("minor_faults", "major_faults"):
                    run[f"{metric}_per_row"] = run[metric] / event_lines
            samples[tag].append(run)
        if i + 1 == runs and any(is_fast(summarize([s["process_wall_s"] for s in series]))
                                 for series in samples.values()):
            target = max(runs, FAST_RUNS)

    def summary(series):
        keys = ("process_wall_s", "container_wall_s", "minor_faults", "major_faults", "sys_s", "exit_tail_s",
                "minor_faults_per_row", "major_faults_per_row", "thp_fault_alloc", "thp_fault_fallback",
                "peak_anon_bytes", "peak_anon_huge_bytes", "cgroup_peak_bytes")
        return {key: summarize([sample[key] for sample in series if key in sample]) for key in keys}

    result.update(runs=samples[candidate], summary=summary(samples[candidate]))
    if baseline:
        result.update(baseline_runs=samples[baseline], baseline_summary=summary(samples[baseline]))
    return result
