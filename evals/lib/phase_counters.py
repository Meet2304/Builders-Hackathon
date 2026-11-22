"""Per-phase hardware counters on macOS without changing the candidate.

The candidate prints cumulative phase marks on stderr (`[  1.234s] phase ...`, unbuffered). This module runs it
with stderr on a pipe and, the moment each mark line arrives, reads the child's cumulative retired instructions and
cycles with `proc_pid_rusage(pid, RUSAGE_INFO_V4)` (all threads, the counters `/usr/bin/time -l` reports). The final
totals are read from the zombie after a kqueue NOTE_EXIT, before reaping, so the exit tail is counted too.

Attribution error: a mark is read about 0.1 ms after it is printed, so up to 0.1 ms × NCPU of the next phase's
work lands in the previous one, well under 1% for phases of 10 ms or more. These are untimed probe runs, never mixed
with the timed samples. The probe is skipped if `proc_pid_rusage` is not available on this host.
"""
from __future__ import annotations

import ctypes
import os
import select
import subprocess
import threading
import time
from pathlib import Path

from .measure import PHASE_RE, clean_dir, parse_phases, phase_key

_FIELDS = ["ri_user_time", "ri_system_time", "ri_pkg_idle_wkups", "ri_interrupt_wkups", "ri_pageins", "ri_wired_size",
           "ri_resident_size", "ri_phys_footprint", "ri_proc_start_abstime", "ri_proc_exit_abstime",
           "ri_child_user_time", "ri_child_system_time", "ri_child_pkg_idle_wkups", "ri_child_interrupt_wkups",
           "ri_child_pageins", "ri_child_elapsed_abstime", "ri_diskio_bytesread", "ri_diskio_byteswritten",
           "ri_cpu_time_qos_default", "ri_cpu_time_qos_maintenance", "ri_cpu_time_qos_background",
           "ri_cpu_time_qos_utility", "ri_cpu_time_qos_legacy", "ri_cpu_time_qos_user_initiated",
           "ri_cpu_time_qos_user_interactive", "ri_billed_system_time", "ri_serviced_system_time",
           "ri_logical_writes", "ri_lifetime_max_phys_footprint", "ri_instructions", "ri_cycles", "ri_billed_energy",
           "ri_serviced_energy", "ri_interval_max_phys_footprint", "ri_runnable_time"]
RUSAGE_INFO_V4 = 4


class _RusageV4(ctypes.Structure):
    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in _FIELDS]


try:
    _LIB = ctypes.CDLL("/usr/lib/libproc.dylib")
except OSError:  # not macOS
    _LIB = None


def available() -> bool:
    return _LIB is not None and hasattr(select, "kqueue")


def _read(pid: int) -> tuple[int, int, int] | None:
    ru = _RusageV4()
    if _LIB.proc_pid_rusage(pid, RUSAGE_INFO_V4, ctypes.byref(ru)) != 0:
        return None
    return ru.ri_instructions, ru.ri_cycles, ru.ri_phys_footprint


def probe_once(binary: Path, data: Path, out: Path, scratch: Path, ncpu: int = 8, timeout: float = 600,
               extra_env: dict | None = None) -> dict:
    """One untimed run; returns per-phase instruction and cycle deltas (and the exit tail)."""
    clean_dir(out)
    clean_dir(scratch)
    env = {k: v for k, v in os.environ.items() if k != "RAYON_NUM_THREADS" and not k.startswith("SESSIONS_DEBUG_")}
    env.update({"DATA_DIR": str(data), "OUTPUT_DIR": str(out), "SCRATCH_DIR": str(scratch), "NCPU": str(ncpu),
                "MEM_GB": "24"})
    env.update(extra_env or {})
    p = subprocess.Popen([str(binary)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=str(scratch))
    kq = select.kqueue()
    kq.control([select.kevent(p.pid, filter=select.KQ_FILTER_PROC, flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
                              fflags=select.KQ_NOTE_EXIT)], 0)
    marks: list[tuple[str, tuple | None]] = []
    lines: list[str] = []

    def pump():
        for raw in p.stderr:
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if PHASE_RE.match(line):
                marks.append((line, _read(p.pid)))
            lines.append(line)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    t0 = time.monotonic()
    final = None
    try:
        events = kq.control(None, 1, timeout)
        if events:
            reader.join(5)
            final = _read(p.pid)  # zombie: counters are final, process not yet reaped
    finally:
        kq.close()
    if final is None:
        p.kill()
    rc = p.wait()
    reader.join(5)
    wall = time.monotonic() - t0
    phases = parse_phases("\n".join(line for line, _ in marks))
    out_phases, prev = [], (0, 0)
    for ph, (_, cnt) in zip(phases, marks):
        if cnt is None:
            out_phases = []
            break
        out_phases.append({"key": ph["key"], "instructions": cnt[0] - prev[0], "cycles": cnt[1] - prev[1]})
        prev = cnt[:2]
    res = {"returncode": rc, "wall_s": round(wall, 4), "phases": out_phases,
           "stats_lines": [x for x in lines if x.startswith("stats:")]}
    if final and out_phases:
        res["phases"].append({"key": "(after last mark: exit/unmap)", "instructions": final[0] - prev[0],
                              "cycles": final[1] - prev[1]})
    if final:
        res["instructions"], res["cycles"], res["phys_footprint_bytes"] = final
    return res


def summarize(runs: list[dict], event_lines: int) -> dict:
    """Median per phase across runs: instructions/row, cycles/row, IPC, share of all instructions."""
    ok = [r for r in runs if r.get("returncode") == 0 and r.get("phases")]
    if not ok or not event_lines:
        return {"n": 0}
    keys = [ph["key"] for ph in ok[0]["phases"]]
    med = lambda xs: sorted(xs)[len(xs) // 2]  # noqa: E731
    total = med([r["instructions"] for r in ok if r.get("instructions")]) if any(r.get("instructions") for r in ok) else None
    phases = {}
    for k in keys:
        ins = [ph["instructions"] for r in ok for ph in r["phases"] if ph["key"] == k]
        cyc = [ph["cycles"] for r in ok for ph in r["phases"] if ph["key"] == k]
        if len(ins) != len(ok):
            continue  # phase missing in some run (renamed/conditional): skip rather than misattribute
        i, c = med(ins), med(cyc)
        phases[k] = {"instructions": i, "cycles": c, "instr_per_row": round(i / event_lines, 2),
                     "cycles_per_row": round(c / event_lines, 2), "ipc": round(i / c, 3) if c else None,
                     "share": round(i / total, 4) if total else None}
    out = {"n": len(ok), "event_lines": event_lines, "phases": phases}
    if total:
        out["instructions"] = total
        out["instr_per_row"] = round(total / event_lines, 2)
        cyc = med([r["cycles"] for r in ok if r.get("cycles")])
        out["cycles_per_row"] = round(cyc / event_lines, 2)
        out["ipc"] = round(total / cyc, 3) if cyc else None
    return out


__all__ = ["available", "probe_once", "summarize", "phase_key"]
