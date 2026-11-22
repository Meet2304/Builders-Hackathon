"""Predict the practice board's time from local measurements, two ways.

1. Wall model: board = intercept + slope × local 20M median wall (one point: a pure ratio).
2. Instruction model: board = fixed_s + instructions_per_row × board_rows / rate. Instructions per row comes
   from the local 20M run (retired instructions / event lines). One point fixes the effective rate with
   fixed_s at its prior (0 s); two or more points fit fixed_s and rate by linear regression.

The M5 Pro retires far more instructions per cycle than the scorer's Cascade Lake, so local wall time
understates gains from cutting instructions; the instruction model is the primary predictor.
"""
from __future__ import annotations

import math
import statistics

BOARD_TARGET_S = 0.28
BOARD_ROWS = 20_000_000       # practice board: about 20M events
FIXED_PRIOR_S = 0.0           # instruction model's fixed cost with a single calibration point
TARGET_FIXED_RANGE_S = (0.05, 0.0)  # the target in instructions/row is quoted for these fixed costs


def _num(v):
    return isinstance(v, (int, float)) and math.isfinite(v) and v > 0


def fit(points: list[dict]) -> dict:
    pairs = [(p.get("local_20m_median_s"), p.get("board_s")) for p in points]
    valid = [(x, y) for x, y in pairs if _num(x) and _num(y)]
    model = {"points": len(valid), "method": None}
    if len(valid) == 1:
        x, y = valid[0]
        model.update(method="ratio", intercept=0.0, slope=y / x)
    elif len(valid) >= 2:
        xs, ys = zip(*valid)
        if len(set(xs)) == 1:
            model["reason"] = "local times are identical"
        else:
            slope, intercept = statistics.linear_regression(xs, ys)
            if slope > 0 and all(map(math.isfinite, (slope, intercept))):
                model.update(method="linear", intercept=intercept, slope=slope,
                             local_range_s=[min(xs), max(xs)])
            else:
                model["reason"] = "fit does not give increasing board time"
    return model


def fit_instr(points: list[dict], rows: int = BOARD_ROWS, fixed_prior_s: float = FIXED_PRIOR_S) -> dict:
    pairs = [(p.get("instructions_per_row"), p.get("board_s")) for p in points]
    valid = [(x, y) for x, y in pairs if _num(x) and _num(y)]
    model = {"points": len(valid), "method": None, "board_rows": rows}
    if len(valid) == 1:
        x, y = valid[0]
        if y > fixed_prior_s:
            rate = x * rows / (y - fixed_prior_s)
            model.update(method="rate", fixed_s=fixed_prior_s, rate_instr_per_s=rate)
        else:
            model["reason"] = "board time not above the fixed-cost prior"
    elif len(valid) >= 2:
        xs, ys = zip(*valid)
        if len(set(xs)) == 1:
            model["reason"] = "instructions per row are identical"
        else:
            slope, intercept = statistics.linear_regression(xs, ys)
            if slope > 0 and all(map(math.isfinite, (slope, intercept))):
                model.update(method="linear", fixed_s=intercept, rate_instr_per_s=rows / slope,
                             ipr_range=[min(xs), max(xs)])
            else:
                model["reason"] = "fit does not give increasing board time"
    if model.get("rate_instr_per_s"):
        model["ns_per_instr_row"] = round(1e9 / model["rate_instr_per_s"], 6)
    return model


def estimate(model: dict, local_s: float | None) -> float | None:
    if local_s is None or not model.get("method"):
        return None
    predicted = model["intercept"] + model["slope"] * local_s
    return predicted if predicted > 0 else None


def estimate_instr(model: dict, ipr: float | None) -> float | None:
    if ipr is None or not model.get("method"):
        return None
    predicted = model["fixed_s"] + ipr * model["board_rows"] / model["rate_instr_per_s"]
    return predicted if predicted > 0 else None


def target(model: dict, board_s: float = BOARD_TARGET_S) -> dict:
    """What the board target means per row: ns/row, and instructions/row for a range of fixed costs."""
    rows = model.get("board_rows", BOARD_ROWS)
    out = {"board_target_s": board_s, "ns_per_row": round(board_s / rows * 1e9, 2)}
    rate = model.get("rate_instr_per_s")
    if rate:
        fixed = sorted({*TARGET_FIXED_RANGE_S, round(model.get("fixed_s", 0.0), 4)}, reverse=True)
        out["instructions_per_row_max"] = {f"fixed {f:.2f}s": round(max(board_s - f, 0) * rate / rows)
                                           for f in fixed if f < board_s}
        vals = list(out["instructions_per_row_max"].values())
        out["summary"] = (f"{board_s:.2f} s ⇒ {out['ns_per_row']:.0f} ns/row ⇒ ≤ {min(vals)}–{max(vals)} "
                          f"instructions/row (fixed {max(fixed):.2f}–{min(fixed):.2f} s, "
                          f"{rate / 1e9:.1f} G instr/s effective)")
    else:
        out["summary"] = f"{board_s:.2f} s ⇒ {out['ns_per_row']:.0f} ns/row"
    return out


def report(config: dict, local_s: float | None, ipr: float | None = None) -> dict:
    model = fit(config.get("points", []))
    imodel = fit_instr(config.get("points", []), config.get("board_rows", BOARD_ROWS),
                       config.get("fixed_prior_s", FIXED_PRIOR_S))
    predicted = estimate(model, local_s)
    ipred = estimate_instr(imodel, ipr)
    limits = model.get("local_range_s")
    primary = ipred if ipred is not None else predicted
    return {**model, "estimated_scorer_20m_s": round(predicted, 6) if predicted is not None else None,
            "instr_model": imodel, "instructions_per_row": round(ipr, 2) if ipr else None,
            "estimated_scorer_20m_instr_s": round(ipred, 6) if ipred is not None else None,
            "primary": "instructions" if ipred is not None else ("wall" if predicted is not None else None),
            "predicted_board_s": round(primary, 6) if primary is not None else None,
            "board_target_s": BOARD_TARGET_S, "target": target(imodel),
            "beats_board_target": primary < BOARD_TARGET_S if primary is not None else None,
            "extrapolated": bool(limits and local_s is not None and not limits[0] <= local_s <= limits[1])}


def ipr_20m(res: dict) -> float | None:
    for v in res.get("perf", {}).get("datasets", {}).values():
        if v.get("role") == "perf-20M":
            return v.get("summary", {}).get("instructions_per_row", {}).get("median")
    return None
