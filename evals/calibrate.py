#!/usr/bin/env python3
"""Recompute evals/calibration.json's ratio = median(board_s / local_20m_median_s) over its points.
Points missing local_20m_median_s are filled from evals/results/<version>.json."""
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import EVALS, read_json, write_json  # noqa: E402
from lib.gates import perf_20m  # noqa: E402

cal = read_json(EVALS / "calibration.json")
ratios = []
for p in cal["points"]:
    if p.get("local_20m_median_s") is None:
        s = perf_20m(read_json(EVALS / "results" / f"{p['version']}.json", {}))
        p["local_20m_median_s"] = s and s.get("median")
    if p.get("board_s") and p.get("local_20m_median_s"):
        p["ratio"] = round(p["board_s"] / p["local_20m_median_s"], 4)
        ratios.append(p["ratio"])
cal["ratio"] = round(statistics.median(ratios), 4) if ratios else None
write_json(EVALS / "calibration.json", cal)
print(f"ratio = {cal['ratio']} from {len(ratios)} point(s)")
