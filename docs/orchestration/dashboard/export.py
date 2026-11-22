#!/usr/bin/env python3
"""Export a compact snapshot of project progress for the live claude.ai dashboard.

Stdlib only. Tolerant of missing files: anything absent is just left out.

    python3 docs/orchestration/dashboard/export.py                 # write snapshot
    python3 docs/orchestration/dashboard/export.py --plan DIR      # also print the ArtifactData batch

Outputs (gitignored):
    docs/orchestration/dashboard/snapshot.json     every document, one file
    docs/orchestration/dashboard/snapshot/<id>.json one file per document (used as batch `file_path`)

The dashboard reads one store collection, COLLECTION below. Each document has a `kind`:
headline, version, phase, thread, log, insights, git. See SYNC.md.

`--plan DIR` takes the directory that `ArtifactData list ... out_dir=DIR` wrote (the current
documents in the store) and prints the batch writes: `set` for new or changed documents
(pinned with `if_version` when the document exists), `delete` for documents no longer in the
snapshot. Unchanged documents are skipped. Batches are split at 50 writes.
"""
import argparse
import datetime as dt
import json
import math
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT_DEFAULT = HERE.parents[2]
COLLECTION = "data/board/rows"
ARTIFACT_URL_FILE = HERE / "ARTIFACT_URL"
LOG_ENTRIES = 12
BATCH_MAX = 50
DEFAULT_TARGET = 0.28
# Fields that change on every export; ignored when deciding whether a document changed.
VOLATILE = {"synced_at"}


# ---------------------------------------------------------------- helpers
def read(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def read_json(path):
    try:
        return json.loads(read(path))
    except ValueError:
        return None


def get(obj, *keys):
    for k in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return v if math.isfinite(v) else None


def rnd(v, nd=4):
    v = num(v)
    return round(v, nd) if v is not None else None


def parse_float(text):
    m = re.search(r"-?\d+(?:\.\d+)?", text or "")
    return float(m[0]) if m else None


def plain(text):
    """Markdown inline -> plain text: links to their label, drop emphasis and backticks."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text or "")
    text = re.sub(r"\*\*|__|`", "", text)
    return re.sub(r"\s+", " ", text).strip()


def section(source, title):
    m = re.search(rf"^## {re.escape(title)}\s*$\n(.*?)(?=^## |\Z)", source, re.M | re.S)
    return m[1] if m else ""


def md_rows(source):
    header = None
    for line in source.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if header is None:
            header = cells
        elif len(cells) == len(header) and not all(re.fullmatch(r":?-+:?", c) for c in cells):
            yield dict(zip(header, cells))


def version_order(name):
    m = re.search(r"(\d+)(?:\D+(\d+))?", name or "")
    return int(m[1]) * 1000 + int(m[2] or 0) if m else 10**9


def slug(text):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", text.lower()).strip("-")[:60] or "x"


def git(root, *args):
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def gb(v):
    v = num(v)
    return round(v / 1e9, 2) if v is not None else None


def ratio(block):
    if not isinstance(block, dict):
        return None
    p, t = block.get("passed"), block.get("total")
    return f"{p}/{t}" if num(p) is not None and num(t) is not None else None


def match(block):
    if not isinstance(block, dict) or "match" not in block:
        return None
    return "MATCH" if block["match"] is True else "DIFF"


# ---------------------------------------------------------------- versions
def from_result(r):
    c = r.get("correctness") or {}
    ds = get(r, "perf", "datasets") or {}

    def med(size, key="wall_s"):
        return rnd(get(ds, f"perf-{size}", "summary", key, "median"))

    diff = c.get("differential") or {}
    diff_n = [v.get("match") for v in diff.values() if isinstance(v, dict) and "match" in v]
    fz = get(c, "fuzz") or {}
    fz_tot = sum(num(get(fz, k, "total")) or 0 for k in ("strict", "robust"))
    fz_ok = sum(num(get(fz, k, "passed")) or 0 for k in ("strict", "robust"))
    det = [v.get("deterministic") for v in (c.get("determinism") or {}).values() if isinstance(v, dict)]
    devs = [match(c.get(f"dev_answer_{a}")) for a in ("native", "arm64", "amd64")]
    devs = [d for d in devs if d]
    verdict = get(r, "verdict", "verdict")
    final = get(r, "verdict", "final")
    return {
        "version": r.get("version"),
        "sha": (r.get("sha") or "")[:8] or None,
        "profile": r.get("profile"),
        "date": (r.get("finished") or r.get("started") or "")[:16].replace("T", " ") or None,
        "verdict": verdict + ("" if final in (True, None) else " (provisional)") if verdict else None,
        "fixtures_native": ratio(c.get("fixtures_native")),
        "fixtures_arm64": ratio(c.get("fixtures_arm64")),
        "fixtures_amd64": ratio(c.get("fixtures_amd64")),
        "dev": ("MATCH" if all(d == "MATCH" for d in devs) else "DIFF") if devs else None,
        "diff": f"{sum(x is True for x in diff_n)}/{len(diff_n)}" if diff_n else None,
        "fuzz": f"{int(fz_ok)}/{int(fz_tot)}" if fz_tot else None,
        "deterministic": ("yes" if all(det) else "no") if det else None,
        "median_1m_s": med("1M"),
        "median_20m_s": med("20M"),
        "median_60m_s": med("60M"),
        "sd_20m_s": rnd(get(ds, "perf-20M", "summary", "wall_s", "stdev")),
        "runs_20m": get(ds, "perf-20M", "summary", "wall_s", "n"),
        "peak_mem_60m_gb": gb(get(ds, "perf-60M", "summary", "peak_footprint_bytes", "median")),
        "max_rss_60m_gb": gb(get(ds, "perf-60M", "summary", "max_rss_bytes", "median")),
        "cpu_util_20m": rnd(get(ds, "perf-20M", "summary", "cpu_util", "median"), 3),
        "est_scorer_20m_s": rnd(get(r, "calibration", "estimated_scorer_20m_s")),
        "warnings": len(get(r, "verdict", "warnings") or []),
        "source": "evals/results",
    }


def from_ledger_row(row):
    fx = (row.get("Fixtures n/arm/amd") or "").split("/")
    fx = fx + [None] * (6 - len(fx))
    fxs = [f"{fx[i]}/36" if fx[i] and fx[i].isdigit() else None for i in range(3)]
    mem = parse_float(row.get("Footprint 60M"))
    return {
        "version": row.get("Version"),
        "sha": (row.get("Commit") or "")[:8] or None,
        "profile": row.get("Profile"),
        "date": (row.get("Date") or "").replace("T", " ") or None,
        "verdict": row.get("Verdict") or None,
        "fixtures_native": fxs[0], "fixtures_arm64": fxs[1], "fixtures_amd64": fxs[2],
        "dev": row.get("dev") or None, "diff": row.get("Diff") or None, "fuzz": row.get("Fuzz") or None,
        "deterministic": row.get("Det") or None,
        "median_1m_s": parse_float(row.get("1M")),
        "median_20m_s": parse_float(row.get("20M")),
        "median_60m_s": parse_float(row.get("60M")),
        "peak_mem_60m_gb": mem,
        "source": "evals/ledger.md",
    }


def from_log_row(row):
    return {
        "version": row.get("Version"),
        "sha": (row.get("Commit") or "")[:8] or None,
        "verdict": plain(row.get("Verdict")) or None,
        "median_20m_s": parse_float(row.get("20M median")),
        "median_60m_s": parse_float(row.get("60M")),
        "source": "docs/orchestration/LOG.md",
    }


def load_versions(root, log):
    versions = {}

    def merge(rec):
        name = (rec.get("version") or "").strip()
        if not name or name.startswith("_") or name.lower() in {"ref", "reference"}:
            return
        cur = versions.setdefault(name, {})
        for k, v in rec.items():
            if v is not None and cur.get(k) is None:
                cur[k] = v
    # Highest-fidelity source first; later ones only fill gaps.
    for p in sorted((root / "evals/results").glob("*.json")):
        r = read_json(p)
        if isinstance(r, dict) and r.get("version"):
            merge(from_result(r))
    ledger = list(md_rows(read(root / "evals/ledger.md")))
    for row in reversed(ledger):  # newest row wins
        merge(from_ledger_row(row))
    for row in md_rows(section(log, "Version ledger")):
        merge(from_log_row(row))

    subs = get(read_json(root / "evals/submissions.json"), "submissions") or []
    for s in subs if isinstance(subs, list) else []:
        if isinstance(s, dict) and s.get("version") in versions:
            v = versions[s["version"]]
            v["submitted"] = "yes"
            bt = num(s.get("board_time_s"))
            if bt is not None and (v.get("board_time_s") is None or bt < v["board_time_s"]):
                v["board_time_s"] = bt
            v["submitted_at"] = s.get("submitted_at")
    # Chronological order: eval date first (experiments such as "window-timestamps" sit between
    # the vN they were measured against), version number as the tie-break.
    ranked = sorted(versions, key=lambda n: (versions[n].get("date") or "9999", version_order(n), n))
    for i, name in enumerate(ranked):
        versions[name].setdefault("submitted", "no")
        versions[name]["order"] = i
    return versions


# ---------------------------------------------------------------- other parts
def load_phases(root, versions):
    """Phase medians at 20M for the newest version that has them."""
    for name in sorted(versions, key=lambda n: versions[n]["order"], reverse=True):
        r = read_json(root / f"evals/results/{name}.json")
        phases = get(r, "perf", "datasets", "perf-20M", "summary", "phases")
        wall = get(r, "perf", "datasets", "perf-20M", "summary", "wall_s", "median")
        if isinstance(phases, dict) and phases:
            out = []
            for i, (k, s) in enumerate(phases.items()):
                m = rnd(get(s, "median"))
                if m is None:
                    continue
                label = "exit / teardown" if k.startswith("(after last mark") else k
                out.append({"version": name, "dataset": "20M", "order": i, "phase": label,
                            "median_s": m, "share": rnd(m / wall, 3) if num(wall) else None})
            return out
    return []


def load_threads(log):
    out = []
    for i, row in enumerate(md_rows(section(log, "Thread registry"))):
        name = plain(row.get("Thread"))
        if not name:
            continue
        out.append({"order": i, "thread": name, "role": plain(row.get("Role")),
                    "branch": plain(row.get("Branch / worktree")), "status": plain(row.get("Status"))})
    return out


def load_log(log):
    body = section(log, "Entries")
    entries, day = [], None
    for line in body.splitlines():
        h = re.match(r"^###\s+(.*)", line)
        if h:
            day = plain(h[1])
            continue
        b = re.match(r"^\s*-\s+(.*)", line)
        if b and not line.startswith("  "):
            text = plain(b[1])
            who = None
            m = re.match(r"^([^:]{1,60}?):\s+(.*)", text)
            if m and b[1].lstrip().startswith("**"):
                who, text = m[1].strip(), m[2]
            entries.append({"index": len(entries), "day": day, "who": who, "text": text})
        elif entries and line.strip() and not h:
            entries[-1]["text"] += " " + plain(line)
    return entries[-LOG_ENTRIES:]


def load_insights(root):
    files = sorted((root / "evals/insights").glob("*.md"),
                   key=lambda p: (p.stat().st_mtime, p.name)) if (root / "evals/insights").is_dir() else []
    if not files:
        return {"available": False, "file": None, "title": "No insights yet",
                "headline": "The Analyst has not written an insights file yet.", "summary": None}
    p = files[-1]
    text = read(p)
    title = next((plain(l.lstrip("# ")) for l in text.splitlines() if l.startswith("# ")), p.stem)
    # Headline: a "Headline"/"TL;DR"/"Summary" section, else a bold-led paragraph such as
    # "**Recommendation: ...**" or "**Verdict: ...**", else the first paragraph.
    paras = [b.strip() for b in text.split("\n\n") if b.strip()]
    m = re.search(r"^#{2,3}\s*(headline|tl;?dr|summary|bottom line)[^\n]*\n(.*?)(?=^#|\Z)", text, re.I | re.M | re.S)
    keys = ("headline", "tl;dr", "tldr", "recommendation", "bottom line", "verdict")
    led = {}
    for b in paras:
        k = re.match(r"^\*\*\s*([A-Za-z;: ]+?)\s*:", b)
        if k and k[1].lower() in keys and k[1].lower() not in led:
            led[k[1].lower()] = b
    body = [b for b in paras if not b.startswith("#") and not b.startswith("|")]
    if m:
        picks = [b.strip() for b in m[2].split("\n\n") if b.strip()]
    elif led:
        picks = [led[k] for k in keys if k in led]
    else:
        picks = body[:2]
    picks = [plain(re.sub(r"^\s*[-*]\s+", "", b, flags=re.M)) for b in picks]
    headline = picks[0] if picks else ""
    summary = " ".join(picks[1:])[:1200] or None
    return {"available": True, "file": f"evals/insights/{p.name}", "title": title,
            "headline": headline[:600], "summary": summary}


def load_git(root):
    commits = git(root, "log", "--oneline", "-15", "main")
    branches = git(root, "for-each-ref", "--sort=-committerdate", "--format=%(refname:short) %(objectname:short) %(committerdate:format:%Y-%m-%d %H:%M)", "refs/heads")
    return {"main_head": git(root, "rev-parse", "--short", "main") or None,
            "commits": commits or None, "branches": branches or None}


def target_s(root):
    t = read(root / "docs/orchestration/PROTOCOL.md")
    m = re.search(r"Target to beat[^\n]*?([0-9]+\.[0-9]+)\s*s\b", t)
    return float(m[1]) if m else DEFAULT_TARGET


def headline(versions, target, now, git_info):
    def m20(v):
        return v.get("median_20m_s")
    ready = [v for v in versions.values() if (v.get("verdict") or "").startswith("SUBMIT-READY") and m20(v)]
    pool = ready or [v for v in versions.values() if m20(v) and not (v.get("verdict") or "").startswith("REJECT")]
    best = min(pool, key=m20) if pool else None
    latest = max(versions.values(), key=lambda v: v["order"]) if versions else None
    boards = [v["board_time_s"] for v in versions.values() if num(v.get("board_time_s")) is not None]
    out = {"synced_at": now, "target_s": target, "versions": len(versions),
           "submitted": sum(v.get("submitted") == "yes" for v in versions.values()),
           "best_board_s": min(boards) if boards else None, "main_head": git_info.get("main_head")}
    if best:
        est = best.get("est_scorer_20m_s")
        basis = est if est is not None else m20(best)
        out.update({"best_version": best["version"], "best_verdict": best.get("verdict"),
                    "best_median_20m_s": m20(best), "best_est_scorer_20m_s": est,
                    "basis": "estimated scorer time" if est is not None else "local 20M median",
                    "gap_s": round(basis - target, 4), "gap_x": round(basis / target, 2)})
        out["status"] = "ahead of target" if basis < target else "behind target"
    if latest:
        out.update({"latest_version": latest["version"], "latest_verdict": latest.get("verdict")})
    return out


# ---------------------------------------------------------------- snapshot
def build(root):
    log = read(root / "docs/orchestration/LOG.md")
    now = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    versions = load_versions(root, log)
    gi = load_git(root)
    docs = {"headline": {"kind": "headline", **headline(versions, target_s(root), now, gi)}}
    for name, v in versions.items():
        docs[f"version-{slug(name)}"] = {"kind": "version", **v}
    for p in load_phases(root, versions):
        docs[f"phase-{p['order']:02d}"] = {"kind": "phase", **p}
    for t in load_threads(log):
        docs[f"thread-{slug(t['thread'])}"] = {"kind": "thread", **t}
    for e in load_log(log):
        docs[f"log-{e['index']:04d}"] = {"kind": "log", **e}
    docs["insights"] = {"kind": "insights", **load_insights(root)}
    docs["git"] = {"kind": "git", **gi}
    # Drop nulls: the store keeps them, and absent reads the same on the page.
    return {k: {f: x for f, x in d.items() if x is not None} for k, d in docs.items()}


def write_snapshot(docs, out_json, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.json"):
        old.unlink()
    for doc_id, d in docs.items():
        (out_dir / f"{doc_id}.json").write_text(json.dumps(d, indent=1, sort_keys=True) + "\n")
    out_json.write_text(json.dumps({"collection": COLLECTION, "docs": docs}, indent=1, sort_keys=True) + "\n")


# ---------------------------------------------------------------- sync plan
LISTING_RE = re.compile(r'^-\s+"([A-Za-z0-9_\-.~:@+]+)"\s+\d+\s+bytes\s+version\s+(\d+)', re.M)


def load_listing(path):
    """Parse the text of an `ArtifactData list` result: lines like `- "git"  1164 bytes  version 3  "..."`.

    The files that `out_dir` writes carry no version, and every write to an existing document needs
    one (`if_version`), so the listing text is the source of versions."""
    return {m.group(1): int(m.group(2)) for m in LISTING_RE.finditer(read(path))}


def load_existing(directory):
    """Read docs saved by `ArtifactData list ... out_dir=DIR`: DIR/<collection>/<id>.json.

    Accepts a bare document, or a wrapper {id, version, data}; also {documents:[{id, version, data}]}."""
    existing = {}
    if not directory:
        return existing
    d = Path(directory)
    files = list((d / COLLECTION).glob("*.json")) if (d / COLLECTION).is_dir() else list(d.rglob("*.json"))
    for p in files:
        obj = read_json(p)
        if not isinstance(obj, dict):
            continue
        items = obj.get("documents") if isinstance(obj.get("documents"), list) else [obj]
        for it in items:
            if not isinstance(it, dict):
                continue
            wrapped = isinstance(it.get("data"), dict)
            doc_id = (it.get("id") or it.get("doc_id")) if wrapped else (p.stem if items == [obj] else None)
            # A bare document (what `out_dir` writes) has no store version; its own fields, such as a
            # version row's `version: "v1"`, are data. Versions come from the listing text.
            version = it.get("version") if wrapped and isinstance(it.get("version"), int) else None
            data = it["data"] if wrapped else it
            if doc_id:
                existing[doc_id] = {"version": version, "data": data}
    return existing


def plan(docs, existing, snap_dir):
    def same(a, b):
        strip = lambda x: {k: v for k, v in (x or {}).items() if k not in VOLATILE}
        return json.dumps(strip(a), sort_keys=True) == json.dumps(strip(b), sort_keys=True)
    writes = []
    for doc_id, d in docs.items():
        cur = existing.get(doc_id)
        if cur and same(cur["data"], d) and doc_id != "headline":
            continue
        w = {"op": "set", "collection": COLLECTION, "doc_id": doc_id, "file_path": str(snap_dir / f"{doc_id}.json")}
        if cur and cur.get("version"):
            w["if_version"] = cur["version"]
        writes.append(w)
    for doc_id, cur in sorted(existing.items()):
        if doc_id not in docs:
            w = {"op": "delete", "collection": COLLECTION, "doc_id": doc_id}
            if cur.get("version"):
                w["if_version"] = cur["version"]
            writes.append(w)
    # headline last, so a partial failure never shows a fresh headline over stale rows
    writes.sort(key=lambda w: w["doc_id"] == "headline")
    return [writes[i:i + BATCH_MAX] for i in range(0, len(writes), BATCH_MAX)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=ROOT_DEFAULT, help="repository to read (default: this checkout)")
    ap.add_argument("--plan", metavar="DIR", nargs="?", const="", default=None,
                    help="print ArtifactData batch writes; DIR = out_dir of a list of the store (omit DIR for a first sync)")
    ap.add_argument("--listing", type=Path, default=HERE / "existing" / "listing.txt",
                    help="text of the ArtifactData list result (ids + versions); renamed to *.used after use")
    a = ap.parse_args()
    root = a.root.resolve()
    docs = build(root)
    out_json, snap_dir = HERE / "snapshot.json", HERE / "snapshot"
    write_snapshot(docs, out_json, snap_dir)
    kinds = {}
    for d in docs.values():
        kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
    print(f"snapshot: {len(docs)} docs {kinds} -> {out_json}", file=sys.stderr)
    if a.plan is not None:
        existing = load_existing(a.plan)
        versions = load_listing(a.listing) if a.listing.is_file() else {}
        for doc_id, v in versions.items():
            existing.setdefault(doc_id, {"version": None, "data": None})["version"] = v
        missing = [k for k, cur in existing.items() if not cur.get("version")]
        if missing:
            sys.exit(f"no version for {len(missing)} stored docs (e.g. {missing[0]}): save the list result text "
                     f"to {a.listing} first (see SYNC.md)")
        if a.listing.is_file():
            a.listing.rename(a.listing.with_suffix(".used"))
        batches = plan(docs, existing, snap_dir)
        url = read(ARTIFACT_URL_FILE).strip() or "<ARTIFACT_URL>"
        print(f"existing docs read: {len(existing)}; batches: {len(batches)}", file=sys.stderr)
        print(json.dumps({"url": url, "batches": batches}, indent=1))


if __name__ == "__main__":
    main()
