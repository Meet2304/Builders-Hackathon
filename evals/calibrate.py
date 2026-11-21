#!/usr/bin/env python3
"""Fit evals/calibration.json from recorded board times and print current predictions."""
from lib.calibration import estimate, fit
from lib.common import EVALS, read_json, write_json
from lib.gates import perf_20m


def main():
    path = EVALS / "calibration.json"
    config = read_json(path)
    results = {p.stem: perf_20m(read_json(p)) for p in sorted((EVALS / "results").glob("*.json"))}
    for point in config["points"]:
        local = results.get(point["version"])
        if point.get("local_20m_median_s") is None and local:
            point["local_20m_median_s"] = local.get("median")
    model = config["fit"] = fit(config["points"])
    write_json(path, config)
    if not model["method"]:
        print(f"No calibration from {model['points']} point(s): {model.get('reason', 'no board times')}")
        return
    print(f"{model['method']}: board = {model['intercept']:.6f} + {model['slope']:.6f} × local "
          f"({model['points']} point(s))")
    for version, local in results.items():
        predicted = estimate(model, local.get("median") if local else None)
        if predicted is not None:
            print(f"{version}: estimated board time {predicted:.3f} s")


if __name__ == "__main__":
    main()
