#!/usr/bin/env python3
"""Render the orchestration dashboard from local files and Git."""
import argparse
from html import escape
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD = Path("docs/orchestration/dashboard/index.html")
TARGET = 0.28
SIZES = ("1M", "20M", "60M")
ARCHES = ("native", "arm64", "amd64")
NA = "n/a"


def read(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def read_json(path):
    try:
        return json.loads(read(path))
    except ValueError:
        return None


def mapping(value):
    return value if isinstance(value, dict) else {}


def get(record, *keys):
    for key in keys:
        record = mapping(record).get(key)
    return record


def number(value):
    if type(value) in (float, int) and 0 <= value < math.inf:
        return value
    return None


def metric(value, spec):
    return format(value, spec) if number(value) is not None else NA


def ratio(passed, total):
    return f"{passed}/{total}" if all(number(x) is not None for x in (passed, total)) else NA


def matches(values):
    if not values or all(value is None for value in values):
        return NA
    count = sum(value is True for value in values)
    return f"{count}/{len(values)} pass"


def markdown_rows(source):
    header = None
    for line in source.splitlines():
        if not line.strip().startswith("|"):
            header = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
        elif len(cells) == len(header) and not all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            yield dict(zip(header, cells))


def section(source, title):
    match = re.search(rf"^## {re.escape(title)}\s*$\n(.*?)(?=^## |\Z)", source, re.M | re.S)
    return match[1].strip() if match else ""


def display(value):
    return value if value not in (None, "", "-", "n/a") else NA


def update(row, **fields):
    row.update({key: value for key, value in fields.items() if display(value) != NA})


def summary(result, size):
    return mapping(get(result, "perf", "datasets", f"perf-{size}", "summary"))


def apply_result(row, result):
    correctness = mapping(result.get("correctness"))
    fixtures = [ratio(get(correctness, f"fixtures_{arch}", "passed"),
                      get(correctness, f"fixtures_{arch}", "total")) for arch in ARCHES]
    dev = [get(correctness, f"dev_answer_{arch}", "match") for arch in ARCHES]
    diff = mapping(correctness.get("differential"))
    fuzz = mapping(get(correctness, "fuzz", "strict"))
    total, skipped = number(fuzz.get("total")), number(fuzz.get("skipped"))
    verdict = get(result, "verdict", "verdict")
    if verdict and get(result, "verdict", "final") is False:
        verdict += " (provisional)"
    footprint = number(get(summary(result, "60M"), "peak_footprint_bytes", "max"))
    if footprint is None:
        footprint = number(get(summary(result, "60M"), "max_rss_bytes", "max"))
    update(row, commit=result.get("sha"), date=result.get("started"), verdict=verdict,
           fixtures=" / ".join(fixtures) if any(cell != NA for cell in fixtures) else NA,
           dev=matches(dev), diff=matches([get(case, "match") for case in diff.values()]),
           fuzz=ratio(fuzz.get("passed"), total - (skipped or 0) if total is not None else None),
           memory=f"{footprint / 1e9:.2f} GB" if footprint is not None else NA,
           cpu=metric(get(summary(result, "20M"), "cpu_util", "median"), ".1%"))
    for size in SIZES:
        median = number(get(summary(result, size), "wall_s", "median"))
        if median is not None:
            row[size] = f"{median:.3f} s"
            if size == "20M":
                row["median"] = median
    row["correct"] = get(result, "gates", "A", "status") == "pass"
    row["result"] = result


def load_versions(evals, log):
    rows = {}
    for item in markdown_rows(section(log, "Version ledger")):
        version = item.get("Version")
        if not version:
            continue
        memory = item.get("Peak mem 60M")
        if memory and "at 20M" in memory:
            memory = None
        rows[version] = {"version": version, "commit": item.get("Commit"),
                         "20M": item.get("20M median"), "60M": item.get("60M"),
                         "memory": memory, "verdict": item.get("Verdict"),
                         "submitted": item.get("Submitted"), "board": item.get("Board time")}

    for item in markdown_rows(read(evals / "ledger.md")):
        version = item.get("Version")
        if not version:
            continue
        row = rows.setdefault(version, {"version": version})
        fields = {"date": "Date", "commit": "Commit", "fixtures": "Fixtures n/arm/amd",
                  "dev": "dev", "diff": "Diff", "fuzz": "Fuzz",
                  "memory": "Footprint 60M", "verdict": "Verdict"}
        update(row, **{key: item.get(column) for key, column in fields.items()})
        update(row, **{size: item.get(size) for size in SIZES})
        match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*s", item.get("20M", ""))
        row["median"] = float(match[1]) if match else None
        row["correct"] = item.get("Verdict") in ("HOLD", "SUBMIT-READY")

    results = []
    for path in sorted((evals / "results").glob("*.json")):
        if path.name.startswith("_"):
            continue
        result = mapping(read_json(path))
        if result:
            results.append((result.get("started") or "", path.stem, result))
    for _, stem, result in sorted(results, key=lambda item: item[:2]):
        version = result.get("version") or stem
        apply_result(rows.setdefault(version, {"version": version}), result)

    submissions = get(read_json(evals / "submissions.json"), "submissions")
    if isinstance(submissions, list):
        for submission in submissions:
            version = get(submission, "version")
            if not version:
                continue
            row = rows.setdefault(version, {"version": version})
            sha = get(submission, "sha")
            commit = row.get("commit")
            if sha and commit and not (sha.startswith(commit) or commit.startswith(sha)):
                continue
            update(row, commit=commit or sha, submitted="yes")
            board = number(get(submission, "board_time_s"))
            if board is not None:
                row["board"] = f"{board:.3f} s"

    return sorted(rows.values(), key=lambda row: row.get("date") or "")


def html(value):
    return escape(str(display(value)))


def table(headers, rows):
    if not rows:
        return "<p>n/a</p>"
    head = "".join(f"<th scope='col'>{html(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{html(cell)}</td>" for cell in row) + "</tr>"
                   for row in rows)
    return f'<div class="table"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def chart(rows):
    points = [(row["version"], row["median"]) for row in rows if number(row.get("median")) is not None]
    if not points:
        return "<p>n/a</p>"
    scale = 300 / max(TARGET, *(median for _, median in points))
    height = 24 * len(points) + 28
    target_x = 110 + TARGET * scale
    parts = [f'<svg viewBox="0 0 485 {height}" width="485" role="img" aria-label="20M medians by version in seconds">']
    for index, (version, median) in enumerate(points):
        y = index * 24
        parts.append(f'<text x="100" y="{y + 16}" text-anchor="end">{html(version)}</text>'
                     f'<rect x="110" y="{y + 4}" width="{median * scale:.2f}" height="16"/>'
                     f'<text x="{116 + median * scale:.2f}" y="{y + 16}">{median:.3f} s</text>')
    parts.append(f'<path d="M {target_x:.2f} 0 V {height - 25}" stroke-dasharray="4 3"/>'
                 f'<text x="{target_x:.2f}" y="{height - 7}" text-anchor="middle">0.28 s target</text></svg>')
    return "".join(parts)


def git(root, *args):
    try:
        return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL,
                                       text=True, timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def render(evals, log_root):
    log = read(log_root / "docs/orchestration/LOG.md")
    versions = load_versions(evals, log)
    best = min((row for row in versions if row.get("correct") and number(row.get("median")) is not None),
               key=lambda row: row["median"], default={})
    latest = next((row for row in reversed(versions) if row["version"] != "ref"), {})
    result = latest.get("result", {})
    phases = []
    wall = number(get(summary(result, "20M"), "wall_s", "median"))
    for name, stats in mapping(summary(result, "20M").get("phases")).items():
        seconds = number(get(stats, "median"))
        phases.append((name, metric(seconds, ".3f"),
                       metric(seconds / wall, ".1%") if wall and seconds is not None else NA))
    gap = f'{best["median"] / TARGET:.2f}× target' if best else NA
    registry = list(markdown_rows(section(log, "Thread registry")))
    thread_columns = ("Thread", "Role", "Branch / worktree", "Status")
    thread_rows = [[re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", item.get(key, ""))
                    for key in thread_columns] for item in registry]
    entries = section(log, "Entries").splitlines()
    recent = "\n".join([line for line in entries if line.strip()][-10:])
    insight_files = sorted((evals / "insights").glob("*.md"))
    # The newest edited insight can have a name unrelated to a version.
    def modified(path):
        try:
            return path.stat().st_mtime
        except OSError:
            return 0

    insight = max(insight_files, key=modified, default=None)
    excerpt = "\n".join(read(insight).splitlines()[:15]) if insight else ""
    cols = ("version", "commit", "date", "verdict", "fixtures", "dev", "diff", "fuzz",
            *SIZES, "memory", "cpu", "submitted", "board")
    version_rows = [[row.get(key) for key in cols] for row in versions]
    for cells in version_rows:
        if cells[1]:
            cells[1] = cells[1][:12]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Hackathon progress</title>
<style>
:root {{ color-scheme: light dark; --ink: #222; --paper: #fff; --line: #aaa; --bar: #3072ac; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --ink: #eee; --paper: #171717; --line: #666; --bar: #639cd1; }}
}}
body {{ margin: 1.5rem auto; padding: 0 1rem; max-width: 90rem; font: 1rem/1.45 system-ui, sans-serif;
       color: var(--ink); background: var(--paper); }}
.table {{ overflow-x: auto; }}
table {{ border-collapse: collapse; font-size: .9rem; }}
th, td {{ text-align: left; vertical-align: top; padding: .35rem .5rem; border-bottom: 1px solid var(--line); }}
pre {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
svg {{ max-width: 100%; height: auto; font-size: 13px; }}
svg text {{ fill: currentColor; }}
svg rect {{ fill: var(--bar); }}
svg path {{ stroke: currentColor; fill: none; }}
</style>
</head>
<body>
<h1>Hackathon progress</h1>
<p>Best correct version <strong>{html(best.get("version"))}</strong> · 20M median
<strong>{html(best.get("20M"))}</strong> · Gap to 0.28 s <strong>{html(gap)}</strong></p>
<p>Current verdict <strong>{html(latest.get("verdict"))}</strong> ({html(latest.get("version"))})</p>
<h2>Versions</h2>
{table(("Version", "Commit", "Date", "Verdict", "Fixtures (native / arm64 / amd64)", "Dev", "Diff", "Fuzz (strict)", "1M", "20M", "60M", "Peak memory (60M)", "CPU (20M)", "Submitted", "Board time"), version_rows)}
<h2>20M medians</h2>
{chart(versions)}
<h2>20M phase breakdown · {html(latest.get("version"))}</h2>
{table(("Phase", "Median seconds", "Share of median wall time"), phases)}
<h2>Thread registry</h2>
{table(thread_columns, thread_rows)}
<h2>Recent log entries</h2>
<pre>{html(recent)}</pre>
<h2>Recent commits on main</h2>
<pre>{html(git(log_root, "log", "--oneline", "-15", "refs/heads/main"))}</pre>
<h2>Local branches</h2>
<pre>{html(git(log_root, "for-each-ref", "--format=%(refname:short) %(objectname:short) %(subject)", "refs/heads"))}</pre>
<h2>Latest insights</h2>
{f"<p>{html(insight.name)}</p>" if excerpt else ""}
<pre>{html(excerpt)}</pre>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository containing evals")
    parser.add_argument("--log-root", type=Path, help="repository containing LOG.md and Git (defaults to --root)")
    parser.add_argument("--output", type=Path, default=ROOT / DASHBOARD,
                        help="output file (defaults to index.html beside this script)")
    args = parser.parse_args()
    page = render(args.root / "evals", args.log_root or args.root)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Publish a whole page even when the browser refreshes during a rebuild.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            file.write(page)
            file.close()
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
    print(output)


if __name__ == "__main__":
    main()
