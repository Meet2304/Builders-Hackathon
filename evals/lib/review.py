"""Analyst-written adversarial review suites (evals/insights/*/run.py), run as part of Gate A.

Each suite is a runner script plus one or more case scripts, configured in evals/suite.json under
"review_suites". The runner prints one line per (case, knob):

    <case> [<knob>]: MATCH | MISMATCH ... | CRASH ...
    <case>: reference failed ...
    FAILURES <n>

The framework only invokes the runner and parses that output; the cases stay the Analyst's.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from .common import PY, REPO, log

LINE = re.compile(r"^(?P<case>[^\s\[:]+)(?: \[(?P<knob>[^\]]*)\])?: (?P<status>MATCH|MISMATCH|CRASH|reference failed)")
FAILURES = re.compile(r"^FAILURES (\d+)$", re.MULTILINE)


def run_suite(spec: dict, binary: Path, work: Path, timeout: float = 1200) -> dict:
    """Run every case script of one review suite against `binary`; never raises on candidate failure."""
    runner = REPO / spec["runner"]
    res = {"runner": spec["runner"], "scripts": {}, "total": 0, "passed": 0, "failed": []}
    if not runner.exists():
        res["status"] = "not_run"
        res["error"] = f"{spec['runner']} not found in the eval checkout"
        return res
    for script in spec["cases"]:
        wd = work / Path(script).stem
        shutil.rmtree(wd, ignore_errors=True)
        wd.mkdir(parents=True)
        log(f"review {spec['name']}: {script} under every knob")
        t = time.time()
        try:
            p = subprocess.run([PY, str(runner), str(binary), str(wd), script], capture_output=True, text=True,
                               timeout=timeout, cwd=REPO)
            out, rc = p.stdout, p.returncode
        except subprocess.TimeoutExpired as e:
            out, rc = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), "timeout"
        item = {"wall_s": round(time.time() - t, 1), "returncode": rc, "total": 0, "passed": 0, "failed": []}
        for line in out.splitlines():
            m = LINE.match(line)
            if not m:
                continue
            item["total"] += 1
            if m["status"] == "MATCH":
                item["passed"] += 1
            else:
                item["failed"].append(line[:600])
        reported = FAILURES.search(out)
        if rc != 0 and not item["failed"]:
            tail = (p.stderr if rc != "timeout" else "")[-400:] if rc != "timeout" else "timeout"
            item["failed"].append(f"runner exit {rc}: {tail}")
        if reported and int(reported.group(1)) != len(item["failed"]):
            item["failed"].append(f"runner reported FAILURES {reported.group(1)}, parsed {len(item['failed'])}")
        if item["total"] == 0:
            item["failed"].append("runner produced no case results")
        res["scripts"][script] = item
        res["total"] += item["total"]
        res["passed"] += item["passed"]
        res["failed"] += [f"{script}: {f}" for f in item["failed"]]
        log(f"review {spec['name']} {script}: {item['passed']}/{item['total']} MATCH in {item['wall_s']}s")
        shutil.rmtree(wd, ignore_errors=True)
    res["status"] = "pass" if res["total"] and not res["failed"] else "fail"
    return res
