"""Fit the practice board's wall time as a function of local 20M wall time."""
from __future__ import annotations

import math
import statistics

BOARD_TARGET_S = 0.28


def fit(points: list[dict]) -> dict:
    pairs = [(p.get("local_20m_median_s"), p.get("board_s")) for p in points]
    valid = [(x, y) for x, y in pairs if all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0
                                          for v in (x, y))]
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


def estimate(model: dict, local_s: float | None) -> float | None:
    if local_s is None or not model.get("method"):
        return None
    predicted = model["intercept"] + model["slope"] * local_s
    return predicted if predicted > 0 else None


def report(config: dict, local_s: float | None) -> dict:
    model = fit(config.get("points", []))
    predicted = estimate(model, local_s)
    limits = model.get("local_range_s")
    return {**model, "estimated_scorer_20m_s": round(predicted, 6) if predicted is not None else None,
            "board_target_s": BOARD_TARGET_S,
            "beats_board_target": predicted < BOARD_TARGET_S if predicted is not None else None,
            "extrapolated": bool(limits and local_s is not None and not limits[0] <= local_s <= limits[1])}
