"""Informational Linux page-fault probe with input staged on a Docker volume."""
from __future__ import annotations

import re
import subprocess
import time
import uuid

from .common import DATA, log
from .measure import parse_phases

GIB = 2**30
TIMING = re.compile(r"^eval_time ([0-9.]+) (\d+) (\d+) (\d+)$", re.MULTILINE)
PROBE_SCRIPT = """\
if [ -r /sys/kernel/mm/transparent_hugepage/enabled ]; then
    printf 'eval_thp '
    cat /sys/kernel/mm/transparent_hugepage/enabled
fi
printf 'eval_page_bytes '
getconf PAGESIZE
exec /usr/bin/time -f 'eval_time %e %R %F %M' /app/sessions
"""
COLD_PREP = """\
set -eu
sync -f /data
find /data -type f -exec sh -ec '
  for file do dd if="$file" iflag=nocache count=0 status=none; done
' sh {} +
resident=$(find /data -type f -exec fincore -b -n -o RES {} +)
printf '%s\n' "$resident" | awk '{bytes += $1} END {printf "%.0f\n", bytes}'
"""


def probe_linux(image: dict, docker: dict, candidates: list[tuple[str, int]], *, cold: bool = False) -> dict:
    """Try candidate datasets in descending size, falling back when the VM cannot run one."""
    budget_gib = min(24, docker["mem_bytes"] // GIB - 1)
    result = {"status": "unavailable", "mem_gib": budget_gib, "attempts": [],
              "input_storage": "Docker named volume", "thp_policy": "VM default"}
    if budget_gib < 2 or not candidates:
        result["reason"] = "insufficient Docker VM memory or no datasets"
        return result

    def call(*args, timeout=180, **kw):
        return subprocess.run(["docker", *args], timeout=timeout, capture_output=True, text=True, **kw)

    tag = image["tag"] + "-faults"
    dockerfile = (f"FROM {image['tag']}\nUSER root\n"
                  "RUN apt-get update && apt-get install -y --no-install-recommends time "
                  "&& rm -rf /var/lib/apt/lists/*\n")
    try:
        log("Linux proxy: preparing GNU time image")
        build = call("build", "--platform", image["platform"], "-t", tag, "-", input=dockerfile, timeout=300)
        if build.returncode != 0:
            result["reason"] = build.stderr[-1500:]
            return result
    except (OSError, subprocess.TimeoutExpired) as e:
        result["reason"] = str(e)
        return result

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
                     "--entrypoint", "/bin/sh", tag, "-c", PROBE_SCRIPT]
            def sample():
                start = time.perf_counter()
                run = call(*flags, timeout=120)
                wall = time.perf_counter() - start
                match = TIMING.search(run.stderr)
                if run.returncode or not match:
                    return {"error": f"exit {run.returncode}: {run.stderr[-600:]}"}
                elapsed, minor, major, rss = match.groups()
                thp = re.search(r"^eval_thp (.+)$", run.stdout, re.MULTILINE)
                active = re.search(r"\[([^]]+)\]", thp.group(1)) if thp else None
                page = re.search(r"^eval_page_bytes (\d+)$", run.stdout, re.MULTILINE)
                return {"process_wall_s": float(elapsed), "container_wall_s": round(wall, 4),
                        "minor_faults": int(minor), "major_faults": int(major), "max_rss_bytes": int(rss) * 1024,
                        "thp_mode": active.group(1) if active else None,
                        "page_bytes": int(page.group(1)) if page else None, "phases": parse_phases(run.stderr)}

            if cold:
                # The staging files belong to root. Run fincore as their owner to get real residency.
                prep = call("run", "--rm", "--platform", image["platform"], "--name", stage, "--network", "none",
                            "--read-only", "--mount", mount + ",readonly", "--entrypoint", "/bin/sh", tag,
                            "-c", COLD_PREP, timeout=120, check=True)
                resident_bytes = int(prep.stdout.strip())
                if resident_bytes:
                    return {"error": f"{resident_bytes} input bytes still resident after eviction"}
                run = sample()
                return run if "error" in run else {"sample": run, "resident_input_bytes_before": resident_bytes}
            warmup = sample()
            if "error" in warmup:
                return warmup
            run = sample()
            return run if "error" in run else {"warmup": warmup, "sample": run}
        except subprocess.CalledProcessError as e:
            return {"error": (e.stderr or str(e))[-800:]}
        except (OSError, subprocess.TimeoutExpired) as e:
            return {"error": str(e)}
        finally:
            # Also remove containers left running by a timed-out Docker client.
            for args in (("rm", "-f", stage, container), ("volume", "rm", token)):
                try:
                    call(*args, timeout=20)
                except (OSError, subprocess.TimeoutExpired) as e:
                    log(f"Linux proxy cleanup for {token}: {e}")

    for dataset, footprint in candidates:
        if footprint + GIB > budget_gib * GIB:
            result["attempts"].append({"dataset": dataset, "error": "native footprint leaves <1 GiB headroom"})
            continue
        log(f"Linux proxy: staging {dataset} in a named volume (memory limit {budget_gib} GiB)")
        attempt = stage_and_run(dataset)
        if "sample" in attempt:
            result.update(status="ok", dataset=dataset, **attempt)
            break
        result["attempts"].append({"dataset": dataset, **attempt})
    return result
