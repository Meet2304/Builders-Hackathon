#!/usr/bin/env python3
"""Run the v3-review cases: Python oracle vs a candidate binary under every debug knob.

    .venv/bin/python evals/insights/v3_review/run.py BINARY WORK_DIR
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))  # evals/
from lib.common import diff_outputs, run_reference  # noqa: E402

KNOBS = [{}, {"SESSIONS_DEBUG_NO_FAST": "1"}, {"SESSIONS_DEBUG_NO_FAST": "2"}, {"SESSIONS_DEBUG_NO_FAST": "3"},
         {"SESSIONS_DEBUG_PARTS": "1"}, {"SESSIONS_DEBUG_PARTS": "3"}, {"SESSIONS_DEBUG_CHUNK": "1"},
         {"SESSIONS_DEBUG_CHUNK": "97"}, {"SESSIONS_DEBUG_HASH_BITS": "0"}, {"NCPU": "1"}]


def main():
    binary, work = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    cases = work / "cases"
    names = subprocess.run([sys.executable, str(HERE / "cases.py"), str(cases)], check=True,
                           capture_output=True, text=True).stdout.split()
    failures = 0
    for name in names:
        ds, ref = cases / name, work / "ref" / name
        r = run_reference(ds, ref)
        if r.get("returncode", 0):
            print(f"{name}: reference failed {r}")
            failures += 1
            continue
        for knob in KNOBS:
            tag = ",".join(f"{k}={v}" for k, v in knob.items()) or "default"
            out = work / "out" / name / tag.replace("=", "_").replace(",", "+")
            subprocess.run(["rm", "-rf", str(out)])
            out.mkdir(parents=True)
            env = {**os.environ, "NCPU": "8", "DATA_DIR": str(ds), "OUTPUT_DIR": str(out), **knob}
            p = subprocess.run([str(binary)], env=env, capture_output=True, text=True, timeout=300)
            if p.returncode:
                failures += 1
                print(f"{name} [{tag}]: CRASH rc={p.returncode}: {p.stderr.strip().splitlines()[-1:]}")
                continue
            d = diff_outputs(ref, out)
            if not d["match"]:
                failures += 1
                print(f"{name} [{tag}]: MISMATCH {json.dumps(d['tables'])[:1500]}")
            else:
                print(f"{name} [{tag}]: MATCH")
    print("FAILURES", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
