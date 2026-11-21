#!/usr/bin/env python3
"""Mutation self-test: how many plausible bugs do the fixtures and the fuzz suite catch?

    .venv/bin/python evals/fuzz/selftest.py [--seeds N]

Each mutant is reference/reference.py with one rule bent the way a fast
implementation might get it wrong. A mutant is *killed* if any fixture or any
strict fuzz case's output differs from the true reference. `control` mutants
are equivalent by the rules (e.g. which of two identical copies is kept) and
must survive; a killed control means the fuzz cases break a rules invariant.
Writes evals/results/_selftest.json and .md.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.common import EVALS, PY, REFERENCE, WORK, log, read_json, write_json  # noqa: E402
from lib.correct import check_output, ensure_fuzz_cases, run_fixtures  # noqa: E402

# (name, [(old, new), ...], control?)
MUTANTS = [
    ("gap >= 30 min splits", [("e[0] - prev > GAP_MS", "e[0] - prev >= GAP_MS")], False),
    ("late cutoff >= 24 h", [("ingest - ts > DAY_MS", "ingest - ts >= DAY_MS")], False),
    ("click exactly 7 d before excluded", [("start - WEEK_MS <= c[0] <= start", "start - WEEK_MS < c[0] <= start")], False),
    ("click at session start excluded", [("start - WEEK_MS <= c[0] <= start", "start - WEEK_MS <= c[0] < start")], False),
    ("tie click -> largest click_id", [("min(window, key=lambda c: (-c[0], c[1]))", "max(window, key=lambda c: (c[0], c[1]))")], False),
    ("dedup keeps latest ingest", [("ingest < prev[0]", "ingest > prev[0]")], False),
    ("dedup after validation", [("            if prev is None or ingest < prev[0]:\n                kept[eid] = (ingest, row)",
                                 "            _ts = parse_ts(row[2])\n            if _ts is None or not (ws <= _ts < we):\n                continue\n            if prev is None or ingest < prev[0]:\n                kept[eid] = (ingest, row)")], False),
    ("F3 wraps at 2^64", [("        return int(b)\n    if len(b) == 20", "        return int(b) % 2**64\n    if len(b) == 20")], False),
    ("F3 wraps at 2^63", [("        return int(b)\n    if len(b) == 20", "        return int(b) % 2**63\n    if len(b) == 20")], False),
    ("F3 longer than 19 chars rejected", [("    if is_digits(b):  # F3", "    if is_digits(b) and len(b) > 19:\n        return None\n    if is_digits(b):  # F3")], False),
    ("offset hour 24 accepted", [("if oh > 23 or om > 59", "if oh > 24 or om > 59")], False),
    ("offset minute 60 accepted", [("if oh > 23 or om > 59", "if oh > 23 or om > 60")], False),
    ("offset sign inverted", [("return base - off if b[19:20] == b\"+\" else base + off", "return base + off if b[19:20] == b\"+\" else base - off")], False),
    ("lowercase z accepted", [("b[19:20] == b\"Z\"", "b[19:20] in (b\"Z\", b\"z\")")], False),
    ("hour 24 accepted", [("h > 23 or mi > 59 or s > 59", "h > 24 or mi > 59 or s > 59")], False),
    ("second 60 accepted", [("h > 23 or mi > 59 or s > 59", "h > 23 or mi > 59 or s > 60")], False),
    ("no leap years", [("return 29 if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0 else 28", "return 28")], False),
    ("price wraps at 2^32", [("return v if 1 <= v <= 10_000_000 else None", "v %= 2**32\n    return v if 1 <= v <= 10_000_000 else None")], False),
    ("price 0 accepted", [("return v if 1 <= v <= 10_000_000 else None", "return v if 0 <= v <= 10_000_000 else None")], False),
    ("price max exclusive", [("return v if 1 <= v <= 10_000_000 else None", "return v if 1 <= v < 10_000_000 else None")], False),
    ("\\r treated as line ending", [("lines = data.split(b\"\\n\")", "lines = data.replace(b\"\\r\", b\"\").split(b\"\\n\")")], False),
    ("inner quotes tolerated", [("or b'\"' in f[1:-1]", "or False")], False),
    ("half-quoted field tolerated", [("if len(f) < 2 or f[0:1] != b'\"' or f[-1:] != b'\"' or b'\"' in f[1:-1]:\n                return None\n            f = f[1:-1]",
                                      "f = f.strip(b'\"')")], False),
    ("person named by largest ID", [("if rb < ra:  # keep", "if rb > ra:  # keep")], False),
    ("user IDs case-folded", [("by_person[person(uid)]", "by_person[person(uid.lower())]")], False),
    ("user IDs trimmed", [("by_person[person(uid)]", "by_person[person(uid.strip())]")], False),
    ("links ignored", [("            dsu.union(a, b)", "            pass")], False),
    ("only direct links (no transitivity)", [("        root = x\n        while p[root] != root:\n            root = p[root]",
                                               "        root = p[x]")], False),
    ("top category tie -> largest", [("key=lambda kv: (-kv[1], kv[0]))[0]", "key=lambda kv: (-kv[1], bytes(255 - x for x in kv[0])))[0]")], False),
    ("assists counted per click", [("for camp in {c[2] for c in window}:", "for camp in [c[2] for c in window]:")], False),
    ("event window end inclusive", [("if ts is None or not (ws <= ts < we):\n            continue\n        if etype", "if ts is None or not (ws <= ts <= we):\n            continue\n        if etype")], False),
    ("click window start exclusive", [("not (ws - WEEK_MS <= ts < we)", "not (ws - WEEK_MS < ts < we)")], False),
    ("day = last event's date", [("day = start // DAY_MS", "day = s[-1][0] // DAY_MS")], False),
    ("header line parsed as data", [("for line in lines[1:]:", "for line in lines:")], False),
    ("unknown product -> empty category", [("products.get(pid, b\"unknown\")", "products.get(pid, b\"\")")], False),
    ("view/cart need a valid price", [("        price = 0\n        if etype == b\"purchase\":", "        price = 0\n        if parse_price(price_b) is None and etype != b\"purchase\":\n            continue\n        if etype == b\"purchase\":")], False),
    ("unknown campaign clicks kept", [("if uid is None or camp not in campaigns:", "if uid is None or camp is None:")], False),
    # controls: equivalent under the rules, must survive
    ("CONTROL dedup ties keep last copy", [("ingest < prev[0]", "ingest <= prev[0]")], True),
    ("CONTROL clicks keep last copy", [("            if cid is None or cid in seen_clicks:\n                continue\n            seen_clicks.add(cid)",
                                        "            if cid is None:\n                continue")], True),
]


def make_mutant(src: str, edits, dest: Path) -> bool:
    for old, new in edits:
        if src.count(old) != 1:
            return False
        src = src.replace(old, new)
    dest.write_text(src)
    return True


def runner(script: Path):
    def run(data: Path, out: Path, ncpu: int = 8, timeout: float = 120):
        env = dict(os.environ, DATA_DIR=str(data), OUTPUT_DIR=str(out))
        return subprocess.run([PY, str(script)], env=env, capture_output=True, timeout=timeout)
    return run


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("-j", type=int, default=12)
    a = ap.parse_args()
    base = ensure_fuzz_cases(range(a.seeds))
    strict = [s for s in range(a.seeds) if read_json(base / str(s) / "case.json")["strict"]]
    src = REFERENCE.read_text()
    work = WORK / "mutants"
    work.mkdir(parents=True, exist_ok=True)
    (WORK / "tmp").mkdir(parents=True, exist_ok=True)
    results = []
    for name, edits, control in MUTANTS:
        script = work / (name.replace(" ", "_").replace("/", "_").replace("\\", "") + ".py")
        if not make_mutant(src, edits, script):
            results.append({"mutant": name, "control": control, "status": "BROKEN (edit did not apply)"})
            log(f"mutant {name!r}: edit did not apply")
            continue
        run = runner(script)
        fx = run_fixtures(run, jobs=a.j, label=f"mutant {name}")
        killed_by_fixtures = fx["passed"] < fx["total"]

        def one(seed):
            d = base / str(seed)
            meta = read_json(d / "case.json")
            with tempfile.TemporaryDirectory(dir=WORK / "tmp") as out:
                p = run(d / "input", Path(out))
                if p.returncode != 0:
                    return seed, True
                return seed, not check_output(Path(out), d / "expected", meta["expected_hash"])["match"]

        kills = []
        with ThreadPoolExecutor(a.j) as pool:
            for i in range(0, len(strict), 48):  # batches, stop at the first batch with a kill
                kills += [s for s, k in pool.map(one, strict[i:i + 48]) if k]
                if kills:
                    break
        res = {"mutant": name, "control": control, "killed_by_fixtures": killed_by_fixtures,
               "fixtures_failed": fx["total"] - fx["passed"], "killed_by_fuzz": bool(kills),
               "first_fuzz_kills": kills[:5]}
        res["status"] = "killed" if (killed_by_fixtures or kills) else "survived"
        results.append(res)
        log(f"mutant {name!r}: fixtures {'KILL' if killed_by_fixtures else 'miss'}, "
            f"fuzz {'KILL ' + str(kills[:3]) if kills else 'miss'}")
    real = [r for r in results if not r["control"] and "BROKEN" not in r["status"]]
    ctrl = [r for r in results if r["control"]]
    summary = {
        "fuzz_seeds": a.seeds, "strict_cases": len(strict), "mutants": len(real),
        "killed_total": sum(r["status"] == "killed" for r in real),
        "killed_by_fixtures": sum(bool(r.get("killed_by_fixtures")) for r in real),
        "killed_by_fuzz": sum(bool(r.get("killed_by_fuzz")) for r in real),
        "fuzz_only": [r["mutant"] for r in real if r.get("killed_by_fuzz") and not r.get("killed_by_fixtures")],
        "survivors": [r["mutant"] for r in real if r["status"] == "survived"],
        "controls_ok": all(r["status"] == "survived" for r in ctrl),
        "broken": [r["mutant"] for r in results if "BROKEN" in r["status"]],
        "results": results,
    }
    write_json(EVALS / "results" / "_selftest.json", summary)
    L = ["# Fuzz mutation self-test", "",
         f"{summary['killed_total']}/{summary['mutants']} mutants killed; fixtures alone kill "
         f"{summary['killed_by_fixtures']}, fuzz ({len(strict)} strict cases) kills {summary['killed_by_fuzz']}. "
         f"Controls {'survive (OK)' if summary['controls_ok'] else 'KILLED: a fuzz case breaks a rules invariant'}.",
         "", "| Mutant | Fixtures | Fuzz | First killing seeds |", "| --- | --- | --- | --- |"]
    for r in results:
        if "BROKEN" in r["status"]:
            L.append(f"| {r['mutant']} | broken | broken | |")
            continue
        L.append(f"| {r['mutant']} | {'kill' if r['killed_by_fixtures'] else '—'} | "
                 f"{'kill' if r['killed_by_fuzz'] else '—'} | {r['first_fuzz_kills']} |")
    (EVALS / "results" / "_selftest.md").write_text("\n".join(L) + "\n")
    log(f"selftest: {summary['killed_total']}/{summary['mutants']} killed (fixtures {summary['killed_by_fixtures']}, "
        f"fuzz {summary['killed_by_fuzz']}); survivors {summary['survivors']}; controls ok {summary['controls_ok']}; "
        f"broken {summary['broken']}")


if __name__ == "__main__":
    main()
