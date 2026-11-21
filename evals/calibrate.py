#!/usr/bin/env python3
"""Fit evals/calibration.json from recorded board times and print current predictions."""
from lib.calibration import estimate, fit, report
from lib.common import EVALS, read_json, write_json
from lib.gates import perf_20m
from run import fmt_s, render_md


def refresh_ledger(model, estimates):
    path = EVALS / "ledger.md"
    if not path.exists():
        return
    lines = path.read_text().splitlines()
    columns = {}
    for i, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells[0] == "Date":
            columns = {name: j for j, name in enumerate(cells)}
            if "Board 20M (est.)" not in columns:
                return
        if not columns or len(cells) != len(columns):
            continue
        key = tuple(cells[columns[name]] for name in ("Date", "Version", "Commit"))
        if key in estimates:
            board = estimates[key]
        elif (wall := cells[columns["20M"]]).endswith("s"):
            board = estimate(model, float(wall.removesuffix("s")))
        else:
            continue
        cells[columns["Board 20M (est.)"]] = fmt_s(board)
        lines[i] = "| " + " | ".join(cells) + " |"
    path.write_text("\n".join(lines) + "\n")


def main():
    path = EVALS / "calibration.json"
    config = read_json(path)
    results = {}
    for result_path in sorted((EVALS / "results").glob("*.json")):
        result = read_json(result_path)
        if stats := perf_20m(result):
            results[result_path.stem] = (result_path, result, stats)
    for point in config["points"]:
        if point.get("local_20m_median_s") is None and point["version"] in results:
            point["local_20m_median_s"] = results[point["version"]][2].get("median")
    model = config["fit"] = fit(config["points"])
    write_json(path, config)
    if not model["method"]:
        print(f"No calibration from {model['points']} point(s): {model.get('reason', 'no board times')}")
        return
    print(f"{model['method']}: board = {model['intercept']:.6f} + {model['slope']:.6f} × local "
          f"({model['points']} point(s))")
    estimates = {}
    for version, (result_path, result, stats) in results.items():
        if not stats.get("n"):
            continue
        result["calibration"] = report(config, stats["median"])
        predicted = result["calibration"]["estimated_scorer_20m_s"]
        estimates[result["started"][:16], version, result["sha"][:8]] = predicted
        write_json(result_path, result)
        result_path.with_suffix(".md").write_text(render_md(result))
        if predicted is not None:
            print(f"{version}: estimated board time {predicted:.3f} s")
    refresh_ledger(model, estimates)


if __name__ == "__main__":
    main()
