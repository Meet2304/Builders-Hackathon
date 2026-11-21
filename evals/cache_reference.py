#!/usr/bin/env python3
"""Cache the Python reference's output for every oracle dataset in the suite.

    .venv/bin/python evals/cache_reference.py [DATASET ...] [--force] [-j N]

Writes data/expected/<dataset>/{user_daily,campaign_daily}/ and meta.json
(dataset fingerprint, reference.py sha, canonical hash, row counts, reference
wall time and peak RSS). A cache entry is reused while the dataset fingerprint
and the reference.py hash both match. The 20M dataset takes ~4 min and ~17 GB.
For `dev` the cached output is also checked against the published answer.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import (DATA, EVALS, EXPECTED, canonical_hash, dataset_fingerprint, dataset_stats,  # noqa: E402
                        diff_outputs, log, read_json, reference_sha, run_reference, write_json)


def suite():
    return read_json(EVALS / "suite.json")["datasets"]


def cached_ok(name: str) -> dict | None:
    meta = read_json(EXPECTED / name / "meta.json")
    ds = DATA / name
    if not meta or not ds.is_dir():
        return None
    if meta.get("fingerprint") != dataset_fingerprint(ds) or meta.get("reference_sha") != reference_sha():
        return None
    return meta


def cache_one(name: str, force: bool = False) -> dict:
    ds = DATA / name
    if not ds.is_dir():
        raise SystemExit(f"dataset missing: {ds}")
    if not force and (meta := cached_ok(name)):
        log(f"reference cache hit: {name} ({meta['canonical']['hash'][:12]})")
        return meta
    stats = dataset_stats(ds)
    log(f"reference: running on {name} ({stats['events_lines']:,} event lines, "
        f"{stats['bytes'] / 1e6:,.0f} MB); this is single-threaded Python")
    tmp = EXPECTED / f".{name}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    run = run_reference(ds, tmp)
    if run["returncode"] != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise SystemExit(f"reference failed on {name}:\n{run['stderr_tail']}")
    canon = canonical_hash(tmp)
    meta = {"dataset": name, "fingerprint": dataset_fingerprint(ds), "reference_sha": reference_sha(),
            "canonical": canon, "reference_run": run, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    entry = suite().get(name, {})
    if entry.get("answer"):
        d = diff_outputs(tmp, DATA / entry["answer"])
        meta["matches_published_answer"] = d["match"]
        if not d["match"]:
            raise SystemExit(f"reference does NOT match the published answer on {name}: {d}")
    write_json(tmp / "meta.json", meta)
    dest = EXPECTED / name
    shutil.rmtree(dest, ignore_errors=True)
    tmp.rename(dest)
    log(f"reference cached: {name} in {run['wall_s']:.1f}s, peak RSS {run['max_rss_bytes'] / 2**30:.1f} GiB, "
        f"rows {canon['rows']}")
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("datasets", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("-j", type=int, default=4, help="parallel reference runs for small datasets")
    a = ap.parse_args()
    names = a.datasets or [n for n, d in suite().items() if d["kind"] == "oracle"]
    big = [n for n in names if suite().get(n, {}).get("events", 0) >= 5_000_000]
    small = [n for n in names if n not in big]
    with ThreadPoolExecutor(a.j) as pool:
        futures = [pool.submit(cache_one, n, a.force) for n in small]
        for n in big:  # big ones one at a time (memory), alongside the small pool
            cache_one(n, a.force)
        for f in futures:
            f.result()


if __name__ == "__main__":
    main()
