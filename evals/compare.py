#!/usr/bin/env python3
"""Per-metric comparison of two eval results, with noise-aware significance.

    .venv/bin/python evals/compare.py A B [--md]

A and B are version names (evals/results/<name>.json) or paths. Deltas are B
relative to A. A timing delta is called significant when it exceeds 2× the
pooled standard deviation of the two sample sets, the Welch |t| > 3 and the change is >= 1 %
(both need ≥ 2 samples); otherwise it is shown as `~` (noise).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import EVALS  # noqa: E402
from lib.measure import pooled_sd, summarize_runs, welch_t  # noqa: E402


def load(x: str) -> dict:
    p = Path(x)
    if not p.exists():
        p = EVALS / "results" / f"{x}.json"
    return json.loads(p.read_text())


def sig(a: dict, b: dict, lower_is_better=True) -> tuple[str, float | None]:
    """'better'/'worse' (B vs A) when significant, else '~'."""
    if not a or not b or not a.get("n") or not b.get("n"):
        return "?", None
    d = b["median"] - a["median"]
    t = welch_t(b, a)
    sd = pooled_sd(a, b)
    rel = abs(d) / a["median"] if a["median"] else 0
    if a["n"] >= 2 and b["n"] >= 2 and abs(d) > 2 * sd and t is not None and abs(t) > 3 and rel >= 0.01:
        return ("better" if (d < 0) == lower_is_better else "worse"), t
    return "~", t


def fmt(v, unit):
    if v is None:
        return "n/a"
    if unit == "s":
        return f"{v:.4f}s"
    if unit == "GiB":
        return f"{v / 2**30:.2f}GiB"
    if unit == "MB":
        return f"{v / 1e6:.2f}MB"
    if unit == "x":
        return f"{v:.3f}"
    if isinstance(v, (int, float)) and abs(v) >= 100:
        return f"{v:,.0f}"
    return f"{v:.3g}" if isinstance(v, float) else f"{v}"


def row(rows, name, a, b, unit="s", stat="median", lower_is_better=True):
    av = a.get(stat) if isinstance(a, dict) else a
    bv = b.get(stat) if isinstance(b, dict) else b
    if av is None and bv is None:
        return
    delta = pct = ""
    if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
        delta = bv - av
        pct = f"{100 * delta / av:+.1f}%" if av else ""
        delta = fmt(delta, unit) if unit != "s" else f"{delta:+.4f}s"
    s, t = sig(a, b, lower_is_better) if stat == "median" and isinstance(a, dict) and isinstance(b, dict) and "samples" in a \
        else ("", None)
    rows.append((name, fmt(av, unit), fmt(bv, unit), str(delta), pct, s + (f" (t={t:.1f})" if t is not None and s else "")))


def dataset_summary(block: dict) -> dict:
    summary = block.get("summary", {})
    if "instructions_per_row" not in summary and block.get("events_lines"):
        # Older results only recorded raw counters.
        return {**summarize_runs(block.get("runs", []), block["events_lines"]), **summary}
    return summary


def compare(A: dict, B: dict) -> list[tuple[str, list]]:
    sections = []
    rows = [("verdict", A["verdict"]["verdict"], B["verdict"]["verdict"], "", "", ""),
            ("sha", A["sha"][:10], B["sha"][:10], "", "", ""), ("profile", A["profile"], B["profile"], "", "", "")]
    ca, cb = A["correctness"], B["correctness"]
    for k in ("fixtures_native", "fixtures_arm64", "fixtures_amd64"):
        if ca.get(k) or cb.get(k):
            rows.append((k, f"{ca.get(k, {}).get('passed', '-')}/{ca.get(k, {}).get('total', '-')}",
                         f"{cb.get(k, {}).get('passed', '-')}/{cb.get(k, {}).get('total', '-')}", "", "", ""))
    for name in sorted(set(ca["differential"]) | set(cb["differential"])):
        m = lambda c: {True: "MATCH", False: "DIFFER", None: "-"}[c["differential"].get(name, {}).get("match")]  # noqa: E731
        rows.append((f"diff {name}", m(ca), m(cb), "", "", ""))
    fa, fb = ca.get("fuzz"), cb.get("fuzz")
    f = lambda z: f"{z['strict']['passed']}/{z['strict']['total'] - z['strict']['skipped']}" if z else "-"  # noqa: E731
    rows.append(("fuzz strict", f(fa), f(fb), "", "", ""))
    sections.append(("Correctness", rows))

    pa, pb = A["perf"]["datasets"], B["perf"]["datasets"]
    for role in [r for r in ("perf-1M", "perf-20M", "perf-60M") if r in pa or r in pb]:
        sa, sb = dataset_summary(pa.get(role, {})), dataset_summary(pb.get(role, {}))
        rows = []
        row(rows, "wall median", sa.get("wall_s", {}), sb.get("wall_s", {}))
        row(rows, "wall min", sa.get("wall_s", {}), sb.get("wall_s", {}), stat="min")
        row(rows, "wall p90", sa.get("wall_s", {}), sb.get("wall_s", {}), stat="p90")
        row(rows, "user", sa.get("user_s", {}), sb.get("user_s", {}))
        row(rows, "sys", sa.get("sys_s", {}), sb.get("sys_s", {}))
        row(rows, "cpu util", sa.get("cpu_util", {}), sb.get("cpu_util", {}), unit="x")
        row(rows, "peak footprint", sa.get("peak_footprint_bytes", {}), sb.get("peak_footprint_bytes", {}), "GiB", "max")
        row(rows, "max RSS", sa.get("max_rss_bytes", {}), sb.get("max_rss_bytes", {}), "GiB", "max")
        row(rows, "page reclaims", sa.get("page_reclaims", {}), sb.get("page_reclaims", {}), "n")
        row(rows, "invol ctx sw", sa.get("ivcsw", {}), sb.get("ivcsw", {}), "n")
        row(rows, "instructions", sa.get("instructions", {}), sb.get("instructions", {}), "n")
        row(rows, "instructions/row", sa.get("instructions_per_row"), sb.get("instructions_per_row"), "n")
        row(rows, "cycles/row", sa.get("cycles_per_row"), sb.get("cycles_per_row"), "n")
        row(rows, "IPC", sa.get("ipc"), sb.get("ipc"), "x", lower_is_better=False)
        ta, tb = pa.get(role, {}).get("throughput", {}), pb.get(role, {}).get("throughput", {})
        row(rows, "MB/s", ta.get("mb_per_s"), tb.get("mb_per_s"), "n")
        for ph in list(dict.fromkeys(list(sa.get("phases", {})) + list(sb.get("phases", {})))):
            row(rows, f"phase: {ph}", sa.get("phases", {}).get(ph, {}), sb.get("phases", {}).get(ph, {}))
        noisy = [x for x, p in (("A", pa.get(role)), ("B", pb.get(role))) if p and p.get("noisy")]
        name = (pa.get(role) or pb.get(role))["dataset"]
        sections.append((f"{name} ({role})" + (f" — NOISY in {noisy}" if noisy else ""), rows))

    ta, tb = A["perf"].get("thread_scaling", {}).get("points", {}), B["perf"].get("thread_scaling", {}).get("points", {})
    if ta or tb:
        rows = []
        for n in sorted(set(ta) | set(tb), key=int):
            row(rows, f"NCPU={n} median", ta.get(n, {}).get("median_s"), tb.get(n, {}).get("median_s"))
            row(rows, f"NCPU={n} efficiency", ta.get(n, {}).get("efficiency"), tb.get(n, {}).get("efficiency"), "x")
            row(rows, f"NCPU={n} hybrid efficiency", ta.get(n, {}).get("hybrid_efficiency"),
                tb.get(n, {}).get("hybrid_efficiency"), "x")
        sections.append(("Thread scaling (20M)", rows))
    ka, kb = A.get("constraints", {}), B.get("constraints", {})
    rows = []
    row(rows, "binary size", ka.get("binary_bytes"), kb.get("binary_bytes"), "MB")
    for arch in sorted(set(ka.get("image_bytes") or {}) | set(kb.get("image_bytes") or {})):
        row(rows, f"image {arch}", (ka.get("image_bytes") or {}).get(arch), (kb.get("image_bytes") or {}).get(arch), "MB")
    row(rows, "threads max", ka.get("threads_max"), kb.get("threads_max"), "n")
    row(rows, "stdout bytes", ka.get("stdout_bytes_max"), kb.get("stdout_bytes_max"), "n")
    oa = A["perf"].get("container_overhead", {}).get("dev_overhead_s")
    ob = B["perf"].get("container_overhead", {}).get("dev_overhead_s")
    row(rows, "container overhead (dev)", oa, ob)
    row(rows, "estimated board 20M", A.get("calibration", {}).get("estimated_scorer_20m_s"),
        B.get("calibration", {}).get("estimated_scorer_20m_s"))
    sections.append(("Resources and sizes", rows))
    return sections


def render(A, B, sections, md: bool) -> str:
    out = [f"{'# ' if md else ''}{A['version']} (A) → {B['version']} (B)", ""]
    head = ("Metric", "A", "B", "Δ", "Δ%", "significance")
    for title, rows in sections:
        out.append(f"{'## ' if md else '== '}{title}")
        if md:
            out += ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
            out += ["| " + " | ".join(map(str, r)) + " |" for r in rows]
        else:
            w = [max(len(str(x)) for x in col) for col in zip(head, *rows)]
            out.append("  ".join(str(h).ljust(n) for h, n in zip(head, w)))
            out += ["  ".join(str(x).ljust(n) for x, n in zip(r, w)) for r in rows]
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--md", action="store_true", help="Markdown tables")
    x = ap.parse_args()
    A, B = load(x.a), load(x.b)
    print(render(A, B, compare(A, B), x.md))


if __name__ == "__main__":
    main()
