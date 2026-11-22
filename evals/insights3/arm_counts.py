#!/usr/bin/env python3
"""ARM (macOS native) per-phase instructions from the `instr=` field of each lap mark.
Runs the binary N times with NCPU=1 at nice 19 and keeps the minimum per phase delta
(the macOS counter picks up page-fault/kernel noise on cold runs).
Usage: arm_counts.py <sessions binary> <dataset> [runs=5]  -> JSON on stdout
"""
import json, os, re, subprocess, sys, tempfile, shutil
binp, ds = sys.argv[1], sys.argv[2]; runs = int(sys.argv[3]) if len(sys.argv) > 3 else 5
names = ["lookups", "events", "clicks", "dedup", "sessions", "write"]
best = None
for _ in range(runs):
    out = tempfile.mkdtemp()
    env = dict(os.environ, NCPU="1", DATA_DIR=ds, OUTPUT_DIR=out)
    err = subprocess.run(["nice", "-n", "19", binp], env=env, capture_output=True, text=True).stderr
    shutil.rmtree(out, ignore_errors=True)
    cum = [float(x) * 1e9 for x in re.findall(r"instr=([\d.]+)G", err)]
    if len(cum) != 6:
        sys.exit("no instr= marks (needs a macOS build with the instr lap field):\n" + err)
    d = [cum[0]] + [b - a for a, b in zip(cum, cum[1:])]
    best = d if best is None else [min(a, b) for a, b in zip(best, d)]
print(json.dumps(dict(zip(names, best))))
