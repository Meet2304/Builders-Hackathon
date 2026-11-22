"""Running a candidate binary and measuring it: wall time, rusage (via
/usr/bin/time -l on macOS), stderr phase marks, stdout bytes, and an optional
probe mode that samples threads and RSS over time."""
from __future__ import annotations

import math
import os
import re
import shutil
import signal
import statistics
import subprocess
import threading
import time
from contextlib import suppress
from pathlib import Path

PHASE_RE = re.compile(r"^\[\s*([0-9]+(?:\.[0-9]+)?)s\]\s+(.*?)\s*$")
TIME_KEYS = {
    "maximum resident set size": "max_rss_bytes",
    "page reclaims": "page_reclaims",
    "page faults": "page_faults",
    "voluntary context switches": "vcsw",
    "involuntary context switches": "ivcsw",
    "instructions retired": "instructions",
    "cycles elapsed": "cycles",
    "peak memory footprint": "peak_footprint_bytes",
    "block input operations": "block_in",
    "block output operations": "block_out",
}


def phase_key(label: str) -> str:
    """Stable phase name: drop a parenthesised detail and any numbers, so
    'lookups (3.6M linked ids)' -> 'lookups'. Tolerant of renames/additions:
    unknown phases are simply new keys."""
    s = re.sub(r"\(.*?\)", "", label)
    s = re.sub(r"[0-9][0-9.,_]*[kKMG]?", "", s)
    s = re.sub(r"[^A-Za-z+/& -]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s or "phase"


CPU_RE = re.compile(r"( \(|, | )cpu=([0-9]+(?:\.[0-9]+)?)s(\)?)$")


def parse_phases(stderr: str) -> list[dict]:
    """Cumulative marks '[  1.234s] phase (detail) cpu=X.XXXs' -> per-phase durations.

    The optional CPU value is cumulative process CPU time (user+sys).
    A phase needs CPU at both ends of its interval to calculate a delta."""
    out, prev, prev_cpu, seen = [], 0.0, 0.0, {}
    for line in stderr.splitlines():
        m = PHASE_RE.match(line)
        if not m:
            continue
        t, label = float(m.group(1)), m.group(2)
        # Method puts the CPU time inside the existing detail parentheses.
        c = CPU_RE.search(label)
        cpu = float(c.group(2)) if c else None
        if c:
            label = label[:c.start()] + (c.group(3) if c.group(1) == ", " else "")
        key = phase_key(label)
        if key in seen:  # repeated names (e.g. per-file marks) get a suffix
            seen[key] += 1
            key = f"{key} #{seen[key]}"
        else:
            seen[key] = 1
        ph = {"key": key, "label": label, "at_s": t, "dur_s": round(max(t - prev, 0.0), 6)}
        if cpu is not None and prev_cpu is not None and cpu >= prev_cpu:
            ph["cpu_s"] = round(cpu - prev_cpu, 6)
            ph["parallelism"] = round(ph["cpu_s"] / ph["dur_s"], 3) if ph["dur_s"] > 0 else None
        out.append(ph)
        prev, prev_cpu = t, cpu
    return out


def parse_time_l(text: str) -> dict:
    got = {}
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^([0-9.]+)\s+real\s+([0-9.]+)\s+user\s+([0-9.]+)\s+sys$", line)
        if m:
            got["time_real_s"], got["user_s"], got["sys_s"] = map(float, m.groups())
            continue
        m = re.match(r"^(\d+)\s+(.+)$", line)
        if m and m.group(2) in TIME_KEYS:
            got[TIME_KEYS[m.group(2)]] = int(m.group(1))
    return got


def _split_time_output(stderr: str) -> tuple[str, str]:
    """/usr/bin/time -l appends its report after the program's stderr."""
    idx = stderr.rfind(" real ")
    if idx < 0:
        return stderr, ""
    start = stderr.rfind("\n", 0, idx) + 1
    return stderr[:start], stderr[start:]


def clean_dir(d: Path):
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)


class ContaminatedSample(RuntimeError):
    pass


FOREIGN_PCPU = 20.0        # a foreign process above this postpones the sample ...
NICED_MIN = 10             # ... unless it runs at nice >= 10 (PROTOCOL.md: builds under the lock use nice -n 19)
NICED_BUDGET_PCPU = 150.0  # and all such niced work together stays under 1.5 CPUs
SAMPLE_WAIT_S = 180.0


def foreign_load(processes: list[tuple[int, int, int, float, str]], me: int) -> tuple[list[dict], list[dict]]:
    """Split processes outside `me`'s tree into (blocking, tolerated niced) lists. Rows: pid, ppid, nice, pcpu, comm."""
    owned = {me}
    while True:
        children = {pid for pid, ppid, _, _, _ in processes if ppid in owned}
        if children <= owned:
            break
        owned.update(children)
    busy = [{"pid": pid, "nice": ni, "pcpu": cpu, "comm": comm} for pid, _, ni, cpu, comm in processes
            if pid not in owned and cpu > FOREIGN_PCPU]
    niced = [x for x in busy if x["nice"] >= NICED_MIN]
    blocking = [x for x in busy if x["nice"] < NICED_MIN]
    if sum(x["pcpu"] for x in niced) > NICED_BUDGET_PCPU:
        blocking += niced
        niced = []
    return blocking, niced


def _ps() -> list[tuple[int, int, int, float, str]]:
    p = subprocess.run(["ps", "-Ao", "pid=,ppid=,nice=,pcpu=,comm="], check=True, capture_output=True, text=True,
                       env=dict(os.environ, LC_ALL="C"))
    rows = []
    for line in p.stdout.splitlines():
        parts = line.split(None, 4)
        if len(parts) == 5:
            try:
                rows.append((int(parts[0]), int(parts[1]), int(parts[2]), float(parts[3]), parts[4]))
            except ValueError:
                continue
    return rows


def sample_load(max_wait_s: float = SAMPLE_WAIT_S) -> dict:
    """Wait for a sample boundary without a foreign process over 20% of a CPU.

    Niced foreign work (nice >= 10, at most 1.5 CPUs in total) is tolerated and recorded, because the protocol
    lets other threads build with `nice -n 19 -j 2` while the bench lock is held."""
    begin = time.monotonic()
    logged = False
    while True:
        blocking, niced = foreign_load(_ps(), os.getpid())
        waited = time.monotonic() - begin
        if not blocking:
            l1, l5, l15 = os.getloadavg()
            out = {"load1": round(l1, 2), "load5": round(l5, 2), "load15": round(l15, 2),
                   "contamination_wait_s": round(waited, 3)}
            if niced:
                out["niced_background_pcpu"] = round(sum(x["pcpu"] for x in niced), 1)
                out["niced_background"] = [f"{x['comm'].rsplit('/', 1)[-1]} pid={x['pid']} {x['pcpu']:g}%"
                                           for x in niced][:5]
            return out
        culprit = max(blocking, key=lambda p: p["pcpu"])
        message = f"{culprit['comm']} pid={culprit['pid']} nice={culprit['nice']} at {culprit['pcpu']:g}% CPU"
        if waited >= max_wait_s:
            raise ContaminatedSample(f"postponed sample for {waited:.1f}s: {message}")
        if not logged:
            from .common import log
            log(f"postponing sample: {message}")
            logged = True
        time.sleep(min(2, max_wait_s - waited))


def run_once(binary: Path, data: Path, out: Path, scratch: Path, ncpu: int, timeout: float = 600,
             probe: bool = False, extra_env: dict | None = None) -> dict:
    """One run of the binary with the scorer's env vars. Output and scratch dirs are emptied first."""
    clean_dir(out)
    clean_dir(scratch)
    env = {k: v for k, v in os.environ.items() if k != "RAYON_NUM_THREADS" and not k.startswith("SESSIONS_DEBUG_")}
    env.update({"DATA_DIR": str(data), "OUTPUT_DIR": str(out), "SCRATCH_DIR": str(scratch), "NCPU": str(ncpu),
                "MEM_GB": "24", "HOME": str(scratch)})
    if extra_env:
        env.update(extra_env)
    stdout_path = scratch.parent / f".{scratch.name}.stdout"
    cmd = [str(binary)] if probe else ["/usr/bin/time", "-l", str(binary)]
    samples = []
    load = sample_load()
    with open(stdout_path, "wb") as so:
        t0 = time.perf_counter()
        p = subprocess.Popen(cmd, env=env, stdout=so, stderr=subprocess.PIPE, cwd=str(scratch),
                             start_new_session=True)
        stop = threading.Event()
        err_chunks = []

        def drain():
            for chunk in iter(lambda: p.stderr.read(65536), b""):
                err_chunks.append(chunk)

        drainer = threading.Thread(target=drain, daemon=True)
        drainer.start()
        sampler = None
        if probe:
            def sample():
                while not stop.is_set():
                    try:
                        # `ps -M` prints a header plus one line per thread; RSS (KiB) comes from a plain `ps`
                        th = subprocess.run(["ps", "-M", "-p", str(p.pid)], capture_output=True, text=True,
                                            timeout=2).stdout.splitlines()
                        rss = subprocess.run(["ps", "-o", "rss=", "-p", str(p.pid)], capture_output=True, text=True,
                                             timeout=2).stdout.strip()
                        if len(th) > 1 and rss.isdigit():
                            samples.append((round(time.perf_counter() - t0, 3), len(th) - 1, int(rss) * 1024))
                    except Exception:  # noqa: BLE001
                        pass
                    stop.wait(0.05)
            sampler = threading.Thread(target=sample, daemon=True)
            sampler.start()
        try:
            try:
                rc = p.wait(timeout=timeout)
            except BaseException as exc:
                # The time wrapper and candidate share this group. Reap the run before unlocking.
                with suppress(ProcessLookupError):
                    os.killpg(p.pid, signal.SIGKILL)
                p.wait()
                if not isinstance(exc, subprocess.TimeoutExpired):
                    raise
                rc = -signal.SIGKILL
            wall = time.perf_counter() - t0
        finally:
            stop.set()
            drainer.join()
            if sampler:
                sampler.join()
    stderr = b"".join(err_chunks).decode("utf-8", "replace")
    prog_err, time_err = _split_time_output(stderr) if not probe else (stderr, "")
    res = {"returncode": rc, "wall_s": round(wall, 4), "ncpu": ncpu,
           "load_before": load,
           "stdout_bytes": stdout_path.stat().st_size, "stderr_bytes": len(prog_err.encode()),
           "phases": parse_phases(prog_err)}
    stdout_path.unlink(missing_ok=True)
    res.update(parse_time_l(time_err))
    if "user_s" in res:
        res["cpu_util"] = round((res["user_s"] + res["sys_s"]) / (wall * ncpu), 4) if wall > 0 else None
    if samples:
        res["threads_max"] = max(s[1] for s in samples)
        res["rss_sampled_max_bytes"] = max(s[2] for s in samples)
        step = max(1, len(samples) // 200)
        res["timeline"] = [list(s) for s in samples[::step]]  # [t_s, threads, rss_bytes]
    if rc != 0:
        res["stderr_tail"] = prog_err[-3000:]
    return res


# ------------------------------------------------------------------ stats

def summarize(xs: list[float]) -> dict:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0}
    s = sorted(xs)
    n = len(s)
    med = statistics.median(s)
    sd = statistics.stdev(s) if n > 1 else 0.0
    p90 = s[min(n - 1, math.ceil(0.9 * n) - 1)]
    return {"n": n, "median": round(med, 6), "mean": round(statistics.fmean(s), 6), "min": round(s[0], 6),
            "max": round(s[-1], 6), "p90": round(p90, 6), "stdev": round(sd, 6),
            "cv": round(sd / med, 4) if med else None, "samples": [round(x, 6) for x in xs]}


def pooled_sd(a: dict, b: dict) -> float:
    na, nb = a.get("n", 0), b.get("n", 0)
    if na + nb <= 2:
        return max(a.get("stdev", 0), b.get("stdev", 0))
    return math.sqrt(((na - 1) * a["stdev"] ** 2 + (nb - 1) * b["stdev"] ** 2) / (na + nb - 2))


def welch_t(a: dict, b: dict) -> float | None:
    """Welch t statistic for a difference in means (for compare.py's significance column)."""
    na, nb = a.get("n", 0), b.get("n", 0)
    if na < 2 or nb < 2:
        return None
    se = math.sqrt(a["stdev"] ** 2 / na + b["stdev"] ** 2 / nb)
    return (a["mean"] - b["mean"]) / se if se > 0 else (math.inf if a["mean"] != b["mean"] else 0.0)


def summarize_runs(runs: list[dict], event_lines: int = 0) -> dict:
    ok = [r for r in runs if r.get("returncode") == 0]
    out = {"wall_s": summarize([r["wall_s"] for r in ok])}
    for k in ("user_s", "sys_s", "cpu_util", "max_rss_bytes", "peak_footprint_bytes", "page_reclaims",
              "page_faults", "vcsw", "ivcsw", "instructions", "cycles", "stdout_bytes"):
        vals = [r[k] for r in ok if r.get(k) is not None]
        if vals:
            out[k] = summarize(vals)
    counters = {
        "instructions_per_row": [r["instructions"] / event_lines for r in ok if event_lines and r.get("instructions")],
        "cycles_per_row": [r["cycles"] / event_lines for r in ok if event_lines and r.get("cycles")],
        "ipc": [r["instructions"] / r["cycles"] for r in ok if r.get("instructions") and r.get("cycles")],
    }
    out.update({key: summarize(values) for key, values in counters.items() if values})
    # phases: median duration per key, in first-seen order
    order, per, cpu, par = [], {}, {}, {}
    for r in ok:
        for ph in r.get("phases", []):
            if ph["key"] not in per:
                order.append(ph["key"])
                per[ph["key"]], cpu[ph["key"]], par[ph["key"]] = [], [], []
            per[ph["key"]].append(ph["dur_s"])
            if ph.get("cpu_s") is not None:
                cpu[ph["key"]].append(ph["cpu_s"])
                par[ph["key"]].append(ph.get("parallelism"))
    phases = {k: summarize(per[k]) for k in order}
    for k in order:  # per-phase CPU (from cpu= marks), when the candidate prints them
        if cpu[k]:
            phases[k]["cpu_s"] = summarize(cpu[k])
            phases[k]["parallelism"] = summarize(par[k])
    if ok and phases:
        last = [r["phases"][-1]["at_s"] for r in ok if r.get("phases")]
        tail = [r["wall_s"] - r["phases"][-1]["at_s"] for r in ok if r.get("phases")]
        phases["(after last mark: exit/unmap + spawn)"] = summarize(tail)
        out["last_mark_s"] = summarize(last)
    out["phases"] = phases
    return out


def load_snapshot() -> dict:
    l1, l5, l15 = os.getloadavg()
    top = []
    try:
        r = subprocess.run(["ps", "-Ao", "pcpu=,comm=", "-r"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines()[:5]:
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                top.append({"pcpu": float(parts[0]), "comm": os.path.basename(parts[1])[:40]})
    except Exception:  # noqa: BLE001
        pass
    busy = None
    try:  # instantaneous: the second `top` sample covers the last 1 s (load averages lag by minutes)
        r = subprocess.run(["top", "-l", "2", "-s", "1", "-n", "0"], capture_output=True, text=True, timeout=10)
        lines = [l for l in r.stdout.splitlines() if l.startswith("CPU usage")]
        m = re.search(r"([0-9.]+)% idle", lines[-1])
        busy = round(100 - float(m.group(1)), 1)
    except Exception:  # noqa: BLE001
        pass
    return {"load1": round(l1, 2), "load5": round(l5, 2), "load15": round(l15, 2), "cpu_busy_pct": busy, "top": top}
