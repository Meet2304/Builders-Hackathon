"""Gates A/B/C and the verdict, exactly as docs/orchestration/PROTOCOL.md defines them."""
from __future__ import annotations

from .common import EVALS, read_json
from .calibration import estimate
from .measure import pooled_sd

GB = 10**9
LIMITS = {
    "peak_mem_60m_bytes": 16 * GB,
    "wall_60m_s": 30.0,
    "stdout_bytes": 1_000_000,
    "threads": 1000,
    "repo_bytes": 50 * 10**6,
}
GATE_C_MIN_GAIN = 0.05
GATE_C_SIGMAS = 2.0
FAST_RUNS = 11
FAST_WALL_S = 0.5


def is_fast(stats: dict | None) -> bool:
    return bool(stats and stats.get("median", FAST_WALL_S) < FAST_WALL_S)


def check(name, status, detail=""):
    return {"name": name, "status": status, "detail": detail}


def _status(cond):
    return "not_run" if cond is None else ("pass" if cond else "fail")


def gate_a(r: dict) -> dict:
    c = r["correctness"]
    out = []

    def fixtures(key, label):
        f = c.get(key)
        if not f:
            return check(label, "not_run")
        return check(label, _status(f["passed"] == f["total"]), f"{f['passed']}/{f['total']}")

    def dev(key, label):
        d = c.get(key)
        if d is None:
            return check(label, "not_run")
        return check(label, _status(d.get("match")), "MATCH" if d.get("match") else d.get("error", "DIFFER"))

    out.append(fixtures("fixtures_native", "fixtures native 36/36"))
    out.append(fixtures("fixtures_amd64", "fixtures amd64 container 36/36"))
    out.append(dev("dev_answer_native", "dev MATCH native"))
    out.append(dev("dev_answer_amd64", "dev MATCH amd64 container"))
    diffs = c.get("differential", {})
    oracle = {k: v for k, v in diffs.items() if v.get("kind") == "oracle"}
    if not oracle:
        out.append(check("differential vs reference (all oracle datasets)", "not_run"))
    else:
        bad = [k for k, v in oracle.items() if not v.get("match")]
        missing = r.get("_suite_oracle_missing", [])
        status = "fail" if bad else ("not_run" if missing else "pass")
        detail = f"{len(oracle) - len(bad)}/{len(oracle)} MATCH" + (f"; DIFFER: {bad}" if bad else "") + (
            f"; not run: {missing}" if missing else "")
        out.append(check("differential vs reference (all oracle datasets)", status, detail))
    fz = c.get("fuzz")
    if not fz:
        out.append(check("fuzz/adversarial strict MATCH", "not_run"))
    else:
        s = fz["strict"]
        n = s["total"] - s["skipped"]
        out.append(check("fuzz/adversarial strict MATCH", _status(s["passed"] == n and n > 0),
                         f"{s['passed']}/{n} (seeds {fz['seeds'][0]}..{fz['seeds'][1] - 1})"
                         + (f"; failing seeds {[x['seed'] for x in s['failed']][:10]}" if s["failed"] else "")))
    det = c.get("determinism", {})
    knobs = c.get("debug_knobs", {})
    for name, item in knobs.items():
        if item["status"] != "n/a":
            out.append(check(name, item["status"]))
    if not det:
        out.append(check("deterministic canonical hash", "not_run"))
    else:
        bad = [k for k, v in det.items() if not v["deterministic"]]
        out.append(check("deterministic canonical hash", _status(not bad),
                         f"{sum(v['runs'] for v in det.values())} runs over {len(det)} datasets"
                         + (f"; NON-deterministic: {bad}" if bad else "")))
    return _gate(out)


def gate_b(r: dict) -> dict:
    p = r.get("perf", {}).get("datasets", {})
    k = r.get("constraints", {})
    out = []
    big = next((v for v in p.values() if v.get("role") == "perf-60M"), None)
    if not big or not big.get("summary", {}).get("wall_s", {}).get("n"):
        out.append(check("60M peak memory <= 16 GB", "not_run"))
        out.append(check("60M local wall <= 30 s", "not_run"))
    else:
        # "Peak memory" = macOS peak memory footprint (anonymous + dirty memory: what can OOM; the metric
        # docs/BENCH.md's 11.5 GB was measured with). Max RSS also counts clean file-backed pages of the
        # mmap'd input; it is reported as a warning, not gated (see README "Memory").
        fp = big["summary"].get("peak_footprint_bytes", {}).get("max")
        rss = big["summary"].get("max_rss_bytes", {}).get("max")
        out.append(check("60M peak memory <= 16 GB", _status(fp is not None and fp <= LIMITS["peak_mem_60m_bytes"]),
                         (f"peak footprint {fp / GB:.2f} GB" if fp else "no footprint")
                         + (f"; max RSS incl. file-backed pages {rss / GB:.2f} GB" if rss else "")))
        med = big["summary"]["wall_s"]["median"]
        out.append(check("60M local wall <= 30 s", _status(med <= LIMITS["wall_60m_s"]), f"median {med:.2f} s"))
    so = k.get("stdout_bytes_max")
    out.append(check("stdout < 1 MB", _status(None if so is None else so < LIMITS["stdout_bytes"]),
                     "" if so is None else f"max {so} bytes"))
    th = k.get("threads_max")
    out.append(check("threads < 1000", _status(None if th is None else th < LIMITS["threads"]),
                     "" if th is None else f"max {th} sampled ({k.get('threads_probe', '')})"))
    ro = k.get("readonly_container_ok")
    out.append(check("writes only to output/scratch (read-only container run)", _status(ro),
                     "fixtures+dev in --read-only containers" if ro else ""))
    img = k.get("clean_image_build_ok")
    out.append(check("image builds from clean", _status(img), k.get("clean_image_build_detail", "")))
    out.append(check("amd64 cascadelake builds from clean", _status(k.get("cascadelake_build_ok"))))
    memory = r.get("perf", {}).get("linux_60m_memory", {})
    peak = memory.get("sample", {}).get("cgroup_peak_bytes")
    mem_ok = None
    if memory.get("status") == "ok" and peak is not None:
        mem_ok = 0 < peak <= 22 * 2**30 and not memory["sample"].get("oom_kills")
    elif any(a.get("oom_kills") or a.get("returncode") == 137 for a in memory.get("attempts", [])):
        mem_ok = False
    out.append(check("60M Linux runs within 22 GiB cgroup", _status(mem_ok),
                     f"cgroup peak {peak / 2**30:.2f} GiB" if peak else memory.get("reason", "")))
    repo = k.get("repo", {})
    if repo:
        ok = repo["tracked_bytes"] < LIMITS["repo_bytes"] and not repo["data_files"]
        out.append(check("repo < 50 MB, no data", _status(ok),
                         f"{repo['tracked_bytes'] / 1e6:.2f} MB tracked" + (
                             f"; data files tracked: {repo['data_files'][:3]}" if repo["data_files"] else "")))
    else:
        out.append(check("repo < 50 MB, no data", "not_run"))
    g = _gate(out)
    if big and big.get("summary", {}).get("max_rss_bytes", {}).get("max", 0) > LIMITS["peak_mem_60m_bytes"]:
        g["warnings"] = [f"60M max RSS incl. file-backed (page-cache) pages is "
                         f"{big['summary']['max_rss_bytes']['max'] / GB:.2f} GB > 16 GB: page cache counts against "
                         f"the scorer's cgroup, so reclaim pressure is possible near 24 GB"]
    return g


def _gate(checks):
    if any(c["status"] == "fail" for c in checks):
        st = "fail"
    elif any(c["status"] == "not_run" for c in checks):
        st = "incomplete"
    else:
        st = "pass"
    return {"status": st, "checks": checks}


def best_baseline(exclude_version: str) -> dict | None:
    """Pick the best submitted version, or the fastest SUBMIT-READY local result."""
    subs = read_json(EVALS / "submissions.json", {"submissions": []}).get("submissions", [])
    pool = []
    if subs:
        for s in subs:
            res = read_json(EVALS / "results" / f"{s['version']}.json")
            if res:
                pool.append(("submitted", res, s.get("board_time_s")))
    else:
        for path in sorted((EVALS / "results").glob("*.json")):
            res = read_json(path)
            if res and res.get("verdict", {}).get("verdict") == "SUBMIT-READY" and res.get("version") != exclude_version:
                pool.append(("submit-ready", res, None))
    eligible = [(kind, res, board, s) for kind, res, board in pool if (s := perf_20m(res)) and s.get("n")]
    if not eligible:
        return None
    rank_by_board = all(board and board > 0 for _, _, board, _ in eligible)
    kind, res, board, s = min(eligible, key=lambda x: x[2] if rank_by_board else x[3]["median"])
    return {"kind": kind, "version": res["version"], "sha": res.get("sha"), "wall_s": s,
            "board_time_s": board}


def perf_20m(res: dict) -> dict | None:
    for v in res.get("perf", {}).get("datasets", {}).values():
        if v.get("role") == "perf-20M":
            return v.get("summary", {}).get("wall_s")
    return None


def native_gate_c(r: dict) -> dict:
    cand = perf_20m(r)
    base = r.get("baseline")
    if not cand or not cand.get("n"):
        return {"status": "incomplete", "checks": [check("20M median beats baseline", "not_run")], "baseline": base}
    minimum = FAST_RUNS if is_fast(cand) else 5
    if cand["n"] < minimum:
        return {"status": "incomplete",
                "checks": [check(f"20M median from >= {minimum} runs", "not_run", f"only {cand['n']} runs")],
                "baseline": base}
    if not base:
        return {"status": "pass", "baseline": None,
                "checks": [check("20M median beats baseline", "pass",
                                 "no submitted or SUBMIT-READY version yet: nothing to beat")]}
    # prefer an interleaved A/B measurement of the baseline taken in this same eval
    paired_b = base.get("ab_wall_s", {})
    paired_c = base.get("ab_candidate_wall_s", {})
    fast = any(is_fast(s) for s in (cand, base["wall_s"], paired_b, paired_c))
    paired_n = min(paired_b.get("n", 0), paired_c.get("n", 0))
    minimum_pairs = max(base.get("ab_required_pairs", 0), FAST_RUNS if fast else 0)
    if base.get("sha") != r.get("sha") and paired_n < minimum_pairs:
        return {"status": "incomplete", "baseline": base,
                "checks": [check(f"interleaved A/B with >= {minimum_pairs} runs per version", "not_run",
                                 f"only {paired_n} pairs")]}
    use_ab = paired_n >= 5
    b, c_ = (paired_b, paired_c) if use_ab else (base["wall_s"], cand)
    b_med, c_med = b["median"], c_["median"]
    sd = pooled_sd(b, c_)
    cal = r.get("calibration", {})
    b_est, c_est = estimate(cal, b_med), estimate(cal, c_med)
    metric = "local"
    if b_est is not None and c_est is not None:
        b_med, c_med = b_est, c_est
        sd *= cal["slope"]
        metric = "estimated scorer"
    delta = b_med - c_med
    gain = delta / b_med
    ok_gain = gain >= GATE_C_MIN_GAIN
    ok_sig = delta > GATE_C_SIGMAS * sd
    src = "interleaved A/B in this eval" if use_ab else "baseline's own result JSON"
    return {"status": "pass" if ok_gain and ok_sig else "fail", "baseline": base,
            "gain": round(gain, 4), "pooled_sd_s": round(sd, 5), "metric": metric,
            "checks": [check(f">= 5% faster than {base['version']} ({base['kind']})", _status(ok_gain),
                             f"{c_med:.3f}s vs {b_med:.3f}s = {gain * 100:+.1f}% ({metric}, {src})"),
                       check("> 2x pooled stdev", _status(ok_sig),
                             f"delta {delta:.4f}s vs 2sd {2 * sd:.4f}s")]}


def linux_signal(r: dict) -> dict:
    timing = r["perf"]["linux_timing"]
    b = timing.get("baseline_summary", {}).get("process_wall_s", {})
    c = timing.get("summary", {}).get("process_wall_s", {})
    minimum = max((r.get("baseline") or {}).get("ab_required_pairs", 5),
                  FAST_RUNS if is_fast(b) or is_fast(c) else 5)
    if (min(b.get("n", 0), c.get("n", 0)) < minimum or timing.get("warmup", {}).get("thp_mode") != "madvise"
            or timing.get("baseline_sha") != (r.get("baseline") or {}).get("sha")):
        return {"status": "unavailable", "detail": "no comparable paired Linux samples"}
    delta = b["median"] - c["median"]
    gain = delta / b["median"]
    sd = pooled_sd(b, c)
    significant = abs(delta) > GATE_C_SIGMAS * sd and abs(gain) >= GATE_C_MIN_GAIN
    status = ("supports" if delta > 0 else "regression") if significant else "inconclusive"
    return {"status": status, "gain": round(gain, 4), "pooled_sd_s": round(sd, 6), "pairs": b["n"],
            "detail": f"{c['median']:.4f}s vs {b['median']:.4f}s ({gain:+.1%}, {b['n']} pairs)"}


def gate_c(r: dict) -> dict:
    native = native_gate_c(r)
    if "linux_timing" not in r["perf"]:
        return native
    linux = linux_signal(r)
    result = {**native, "linux_ab": linux}
    if linux["status"] == "supports":
        result["status"] = "pass"
        result["checks"] = [check("Linux 20M gain >= 5% and > 2x pooled stdev", "pass", linux["detail"])]
        result["native"] = native
        result["metric"] = "linux arm64"
        result["gain"] = linux["gain"]
        result["pooled_sd_s"] = linux["pooled_sd_s"]
    return result


def verdict(r: dict) -> dict:
    v = _verdict(r)
    v["warnings"] = [w for g in r["gates"].values() for w in g.get("warnings", [])]
    return v


def _verdict(r: dict) -> dict:
    a, b, c = r["gates"]["A"], r["gates"]["B"], r["gates"]["C"]
    reasons = []
    for name, g in (("A", a), ("B", b)):
        reasons += [f"Gate {name} FAIL: {x['name']} ({x['detail']})" for x in g["checks"] if x["status"] == "fail"]
    if reasons:
        return {"verdict": "REJECT", "final": True, "reasons": reasons}
    missing = [f"Gate {n}: {x['name']} not run" for n, g in (("A", a), ("B", b)) for x in g["checks"]
               if x["status"] == "not_run"]
    if c["status"] == "fail":
        reasons += [f"Gate C: {x['name']} ({x['detail']})" for x in c["checks"] if x["status"] == "fail"]
        return {"verdict": "HOLD", "final": not missing, "reasons": reasons + missing}
    if missing or c["status"] != "pass":
        return {"verdict": "HOLD", "final": False,
                "reasons": ["incomplete evaluation (use --profile full)"] + missing
                + [f"Gate C: {x['name']} not run" for x in c["checks"] if x["status"] == "not_run"]}
    return {"verdict": "SUBMIT-READY", "final": True,
            "reasons": ["Gates A, B, C pass"] + [x["detail"] for x in c["checks"]]}
