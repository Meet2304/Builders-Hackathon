#!/usr/bin/env python3
"""Fit evals/calibration.json from recorded board times and refresh every result's and ledger row's predictions.

Two predictors (lib/calibration.py): local 20M wall × ratio, and instructions/row × board rows / effective rate."""
from lib.calibration import estimate, estimate_instr, fit, fit_instr, ipr_20m, report, BOARD_ROWS, FIXED_PRIOR_S
from lib.common import EVALS, read_json, write_json
from lib.gates import perf_20m, prediction_line
from run import fmt_ipr, fmt_s, render_md

NEW_COLUMNS = ("Instr/row 20M", "Board 20M (instr.)")


def refresh_ledger(model, imodel, estimates):
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
            cells += [c for c in NEW_COLUMNS if c not in cells]
            columns = {name: j for j, name in enumerate(cells)}
            if "Board 20M (est.)" not in columns:
                return
            lines[i] = "| " + " | ".join(cells) + " |"
            continue
        if set(cells) <= {"---"}:
            lines[i] = "| " + " | ".join(["---"] * len(columns)) + " |"
            continue
        if not columns:
            continue
        cells += ["-"] * (len(columns) - len(cells))
        if len(cells) != len(columns):
            continue
        key = tuple(cells[columns[name]] for name in ("Date", "Version", "Commit"))
        if key in estimates:
            board, ipr, iboard = estimates[key]
        elif (wall := cells[columns["20M"]].removesuffix(" (noisy)")).endswith("s"):
            board, ipr, iboard = estimate(model, float(wall.removesuffix("s"))), None, None
        else:
            board, ipr, iboard = None, None, None
        cells[columns["Board 20M (est.)"]] = fmt_s(board)
        if ipr is not None or cells[columns["Instr/row 20M"]] in ("", "-"):
            cells[columns["Instr/row 20M"]] = fmt_ipr(ipr)
        cells[columns["Board 20M (instr.)"]] = fmt_s(iboard)
        lines[i] = "| " + " | ".join(cells) + " |"
    path.write_text("\n".join(lines) + "\n")


def main():
    path = EVALS / "calibration.json"
    config = read_json(path)
    results = {}
    for result_path in sorted((EVALS / "results").glob("*.json")):
        result = read_json(result_path)
        if (stats := perf_20m(result)) and result.get("sha"):
            results[result_path.stem] = (result_path, result, stats)
    for point in config["points"]:
        if point["version"] in results:
            _, res, stats = results[point["version"]]
            if point.get("local_20m_median_s") is None:
                point["local_20m_median_s"] = stats.get("median")
            if point.get("instructions_per_row") is None:
                point["instructions_per_row"] = ipr_20m(res)
    model = config["fit"] = fit(config["points"])
    imodel = config["instr_fit"] = fit_instr(config["points"], config.get("board_rows", BOARD_ROWS),
                                             config.get("fixed_prior_s", FIXED_PRIOR_S))
    write_json(path, config)
    if not model["method"] and not imodel["method"]:
        print(f"No calibration from {model['points']} point(s): {model.get('reason', 'no board times')}")
        return
    if model["method"]:
        print(f"wall   {model['method']}: board = {model['intercept']:.6f} + {model['slope']:.6f} × local "
              f"({model['points']} point(s))")
    if imodel["method"]:
        print(f"instr  {imodel['method']}: board = {imodel['fixed_s']:.4f} + instr/row × {imodel['board_rows']:,} / "
              f"{imodel['rate_instr_per_s'] / 1e9:.3f}e9 ({imodel['points']} point(s))")
    estimates = {}
    for version, (result_path, result, stats) in results.items():
        if not stats.get("n"):
            continue
        result["calibration"] = cal = report(config, stats["median"], ipr_20m(result))
        if result.get("verdict"):
            v = result["verdict"]
            v["reasons"] = [x for x in v.get("reasons", []) if not x.startswith("predicted board 20M:")]
            if line := prediction_line(cal):
                v["predictions"] = line
                v["reasons"].append(line)
        estimates[result["started"][:16], version, result["sha"][:8]] = (
            cal["estimated_scorer_20m_s"], cal["instructions_per_row"], cal["estimated_scorer_20m_instr_s"])
        write_json(result_path, result)
        if result.get("gates") and result.get("verdict"):
            result_path.with_suffix(".md").write_text(render_md(result))
        print(f"{version:28s} wall-model {fmt_s(cal['estimated_scorer_20m_s']):>8}  "
              f"instr-model {fmt_s(cal['estimated_scorer_20m_instr_s']):>8}  ({fmt_ipr(cal['instructions_per_row'])} instr/row)")
    tgt = report(config, None)["target"]
    print("target:", tgt["summary"])
    refresh_ledger(model, imodel, estimates)


if __name__ == "__main__":
    main()
