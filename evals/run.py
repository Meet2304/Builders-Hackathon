#!/usr/bin/env python3
"""Evaluate one candidate version of the pipeline.

    .venv/bin/python evals/run.py --version v2 --rev method/v2 [--profile quick|full|linux]

Builds the candidate from REV in an isolated dir (git archive; never touches a
worktree), measures correctness, performance and constraints, applies Gates
A/B/C from docs/orchestration/PROTOCOL.md, and writes
    evals/results/<version>.json   (schema: evals/SCHEMA.md)
    evals/results/<version>.md     (human summary)
    evals/ledger.md                (one appended row)
Progress is logged to stderr. See evals/README.md.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cache_reference import cached_ok  # noqa: E402
from lib import gates  # noqa: E402
from lib.bench_lock import benchmark_lock  # noqa: E402
from lib.build import build_image, build_native, docker_info, repo_size, resolve  # noqa: E402
from lib.calibration import ipr_20m, report as calibration_report  # noqa: E402
from lib.common import (CONSISTENCY, DATA, EVALS, EXPECTED, FIXTURES, REPO, WORK, canonical_hash, dataset_stats,  # noqa: E402
                        diff_outputs, invariants, log, read_json, reference_sha, sha256_file, write_json)
from lib.correct import (DEBUG_CASES, DIALECT_ONLY, EXTRA_DEBUG_CASES, INVALID_DEBUG_CASES, check_output,  # noqa: E402
                         WINDOWS_SEED0, fuzz_gen_sha, run_fixtures, run_fuzz, runner_cmd)
from lib.linux_proxy import probe_linux  # noqa: E402
from lib.review import run_suite  # noqa: E402
from lib.measure import ContaminatedSample, load_snapshot, run_once, sample_load, summarize, summarize_runs  # noqa: E402

SCHEMA_VERSION = 1
NOISY_BUSY_PCT = 12.0   # machine-wide CPU busy % in the 1 s before a timed block
NOISY_CV = 0.03

PROFILES = {
    "quick": {"runs": {"perf-1M": 3, "perf-20M": 5, "perf-60M": 1}, "warmup": {"perf-1M": 1, "perf-20M": 1,
                                                                              "perf-60M": 0},
              "fuzz_seeds": 150, "windows_seeds": 60, "thread_scaling": False, "docker": False, "probe": "perf-1M",
              "ab": False},
    "full": {"runs": {"perf-1M": 5, "perf-20M": 5, "perf-60M": 3}, "warmup": {"perf-1M": 1, "perf-20M": 1,
                                                                            "perf-60M": 1},
             "fuzz_seeds": 1000, "windows_seeds": 300, "thread_scaling": True, "docker": True, "probe": "perf-60M",
             "ab": True},
    "linux": {"runs": {"perf-20M": 5}, "warmup": {"perf-20M": 1}, "fuzz_seeds": 150, "windows_seeds": 60,
              "thread_scaling": False, "docker": False, "probe": None, "ab": True},
}
AMEND_STAGES = {"review": "review", "windows": "fuzz_windows", "amd64-knobs": "amd64_knobs", "linux-ab": "linux_ab"}
SCALING_NCPU = [1, 2, 4, 5, 8]
SCALING_RUNS = 3
AB_RUNS = 5
AMD64_KNOBS = (("SESSIONS_DEBUG_NO_FAST", "3"),)  # portable SWAR classifier on x86
EFF_CORE_RATIO = (6.4 - 5) / 3  # Analyst's M5 estimate for an E-core relative to a P-core.


def host_info() -> dict:
    def sysctl(k):
        try:
            return subprocess.run(["sysctl", "-n", k], capture_output=True, text=True).stdout.strip()
        except OSError:
            return ""
    import polars
    return {"machine": sysctl("machdep.cpu.brand_string") or platform.processor(), "ncpu": os.cpu_count(),
            "perf_cores": sysctl("hw.perflevel0.physicalcpu"), "eff_cores": sysctl("hw.perflevel1.physicalcpu"),
            "mem_bytes": int(sysctl("hw.memsize") or 0), "os": platform.platform(), "python": platform.python_version(),
            "polars": polars.__version__}


def eval_sha() -> str:
    try:
        sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "evals/"], capture_output=True,
                               text=True).stdout.strip()
        return sha[:12] + ("+dirty" if dirty else "")
    except OSError:
        return "unknown"


class Eval:
    def __init__(self, a):
        self.a = a
        self.prof = dict(PROFILES[a.profile])
        if a.fuzz_seeds is not None:
            self.prof["fuzz_seeds"] = a.fuzz_seeds
        if a.no_docker:
            self.prof["docker"] = False
        self.suite = read_json(EVALS / "suite.json")["datasets"]
        self.sha = resolve(a.rev)
        self.runs_dir = WORK / "runs" / f"{a.version}-{os.getpid()}"
        self.r = {"schema_version": SCHEMA_VERSION, "version": a.version, "rev": a.rev, "sha": self.sha,
                  "profile": a.profile, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                  "host": host_info(),
                  "evaluator": {"eval_sha": eval_sha(), "reference_sha": reference_sha(),
                                "fuzz_gen_sha": fuzz_gen_sha(), "scorer_flags_script": "scripts/docker_run.sh"},
                  "build": {}, "correctness": {"differential": {}, "determinism": {}, "row_counts": {}},
                  "perf": {"datasets": {}}, "constraints": {}, "notes": [], "errors": []}
        self.stdout_max = 0
        self.t0 = time.time()

    # -------------------------------------------------------------- helpers
    def role(self, role):
        for name, d in self.suite.items():
            if d.get("role") == role and (DATA / name).is_dir():
                return name
        return None

    def note(self, msg):
        log("NOTE " + msg)
        self.r["notes"].append(msg)

    def step(self, name, fn, *args):
        """Run one stage; a crash in the framework is recorded, not fatal."""
        try:
            return fn(*args)
        except ContaminatedSample as e:
            self.note(f"{name}: {e}")
            return None
        except Exception as e:  # noqa: BLE001
            log(f"ERROR in {name}: {type(e).__name__}: {e}")
            self.r["errors"].append({"stage": name, "error": f"{type(e).__name__}: {e}",
                                     "trace": traceback.format_exc()[-2000:]})
            return None

    # -------------------------------------------------------------- stages
    def build(self):
        b = build_native(self.sha, rebuild=self.a.rebuild)
        self.r["build"]["native"] = b
        self.binary = Path(b["binary"])
        self.run = runner_cmd(self.binary, None)

    def correctness_untimed(self):
        c = self.r["correctness"]
        c["fixtures_native"] = run_fixtures(self.run, label="native")
        missing = []
        for name, d in self.suite.items():
            if d["kind"] != "oracle" or d.get("role") == "perf-20M":
                continue
            exp = cached_ok(name)
            if not (DATA / name).is_dir() or not exp:
                missing.append(name)
                continue
            out = self.runs_dir / "diff" / name
            shutil.rmtree(out, ignore_errors=True)
            out.mkdir(parents=True)
            p = self.run(DATA / name, out, ncpu=8, timeout=300)
            self.stdout_max = max(self.stdout_max, len(p.stdout))
            if p.returncode != 0:
                res = {"match": False, "error": f"exit {p.returncode}: {p.stderr.decode()[-300:]}"}
            else:
                res = check_output(out, EXPECTED / name, exp["canonical"]["hash"])
            res["kind"] = "oracle"
            res["against"] = f"data/expected/{name} (reference {exp['reference_sha'][:8]})"
            c["differential"][name] = res
            c["row_counts"][name] = res.get("rows")
            log(f"differential {name}: {'MATCH' if res.get('match') else 'DIFFER'}")
            if d.get("answer"):
                ans = check_output(out, DATA / d["answer"], self.answer_hash(d["answer"]))
                c["dev_answer_native"] = {"match": ans.get("match"), **({"diff": ans["diff"]} if "diff" in ans else {})}
                log(f"dev vs published answer: {'MATCH' if ans.get('match') else 'DIFFER'}")
            shutil.rmtree(out, ignore_errors=True)
        if missing:
            self.note(f"oracle datasets missing or uncached: {missing} (run evals/cache_reference.py)")

    def review(self):
        """Analyst review suites from suite.json["review_suites"]: oracle vs candidate under every knob."""
        specs = read_json(EVALS / "suite.json").get("review_suites", [])
        out = self.r["correctness"]["review_suites"] = {}
        for spec in specs:
            out[spec["name"]] = run_suite(spec, self.binary, self.runs_dir / "review" / spec["name"])

    def fuzz_windows(self):
        """Window-edge fuzz focus (year end, leap day, off-midnight windows, decoder-table edges)."""
        n = self.prof.get("windows_seeds", 0)
        if n <= 0:
            return
        seeds = range(WINDOWS_SEED0, WINDOWS_SEED0 + n)
        self.r["correctness"]["fuzz_windows"] = run_fuzz(self.run, seeds)

    def answer_hash(self, answer):
        cache = DATA / "stats" / f"{answer}.hash.json"
        got = read_json(cache)
        if got:
            return got["hash"]
        h = canonical_hash(DATA / answer)["hash"]
        write_json(cache, {"hash": h})
        return h

    def fuzz(self):
        n = self.prof["fuzz_seeds"]
        if n <= 0:
            return
        self.fuzz_hashes = {}
        self.r["correctness"]["fuzz"] = run_fuzz(self.run, range(n), record_hashes=self.fuzz_hashes)

    def debug_knobs(self):
        c = self.r["correctness"]
        # The release executable contains the names it looks up at runtime, even after stripping.
        binary = self.binary.read_bytes()
        checks = c["debug_knobs"] = {}
        seeds = range(max(self.prof["fuzz_seeds"], 0))
        full = self.a.profile == "full"
        for key, value in DEBUG_CASES + (EXTRA_DEBUG_CASES if full else ()):
            label = f"{key}={value}"
            if key.encode() not in binary:
                checks[label] = {"status": "n/a"}
                continue
            log(f"debug correctness: {label}")
            run = partial(self.run, extra_env={key: value})
            item = checks[label] = {"status": "not_run"}
            dialect_only = (key, value) in DIALECT_ONLY
            expected = c["differential"].get("dev", {})
            if not dialect_only and expected.get("match"):
                out = self.runs_dir / "debug-dev"
                shutil.rmtree(out, ignore_errors=True)
                out.mkdir(parents=True)
                try:
                    p = run(DATA / "dev", out, timeout=300)
                    self.stdout_max = max(self.stdout_max, len(p.stdout))
                    if p.returncode:
                        item["dev"] = {"match": False, "error": p.stderr.decode(errors="replace")[-300:]}
                    else:
                        result = check_output(out, EXPECTED / "dev", expected["hash"])
                        result["match"] &= result["hash"] == expected["hash"] and not p.stdout
                        item["dev"] = result
                except subprocess.TimeoutExpired:
                    item["dev"] = {"match": False, "error": "timeout"}
                finally:
                    shutil.rmtree(out, ignore_errors=True)
            if seeds and hasattr(self, "fuzz_hashes"):
                item["fuzz"] = run_fuzz(run, seeds, default_hashes=self.fuzz_hashes,
                                       focus="dialect" if dialect_only else None)
            strict = item.get("fuzz", {}).get("strict", {})
            dev = item.get("dev", {})
            if dev.get("match") is False or strict.get("failed"):
                item["status"] = "fail"
            elif (dialect_only or dev.get("match")) and strict and strict["passed"] > 0 and not strict["skipped"]:
                item["status"] = "pass"
        if full:
            for key, value in INVALID_DEBUG_CASES:
                if key.encode() not in binary:
                    continue
                log(f"debug correctness: rejecting {key}={value}")
                out = self.runs_dir / "debug-invalid"
                out.mkdir(parents=True, exist_ok=True)
                label = f"reject {key}={value}"
                checks[label] = self.reject_knob(key, value, out)
        if full and b"SESSIONS_DEBUG_PARTS" in binary:
            self.empty_outputs(checks)

    def reject_knob(self, key, value, out):
        p = self.run(FIXTURES / "E5" / "input", out, extra_env={key: value})
        # A release build can use panic=abort. Python reports the signal as a negative exit status.
        status = "pass" if p.returncode != 0 and f"{key}={value}:".encode() in p.stderr else "fail"
        return {"status": status, "returncode": p.returncode, "stderr_tail": p.stderr.decode(errors="replace")[-400:]}

    def empty_outputs(self, checks):
        cases = ("E5", "E13")
        modes = ({}, {"SESSIONS_DEBUG_PARTS": "1"})
        item = checks["empty output fixtures with default and one partition"] = {"status": "not_run", "cases": {}}
        for case in cases:
            expected = canonical_hash(FIXTURES / case / "expected")
            hashes = []
            for mode in modes:
                for _ in range(2):
                    out = self.runs_dir / "debug-empty"
                    shutil.rmtree(out, ignore_errors=True)
                    out.mkdir(parents=True)
                    p = self.run(FIXTURES / case / "input", out, extra_env=mode)
                    hashes.append(canonical_hash(out)["hash"] if p.returncode == 0 and not p.stdout else None)
            item["cases"][case] = {"expected": expected["hash"], "hashes": hashes}
        item["status"] = "pass" if all(v["expected"] and set(v["hashes"]) == {v["expected"]}
                                       for v in item["cases"].values()) else "fail"

    def perf_block(self, role, ncpu=8, runs=None, warmup=None, check=True, label=None):
        name = self.role(role)
        if not name:
            self.note(f"no dataset for {role}")
            return None
        ds = DATA / name
        st = dataset_stats(ds)
        runs = self.prof["runs"][role] if runs is None else runs
        warmup = self.prof["warmup"][role] if warmup is None else warmup
        out, scratch = self.runs_dir / "out", self.runs_dir / "scratch"
        load = self.wait_quiet()
        log(f"perf {label or role}: {name} NCPU={ncpu}, {warmup} warm-up + {runs} timed runs "
            f"(cpu busy {load.get('cpu_busy_pct')}%, load1 {load['load1']})")
        block = {"dataset": name, "role": role, "ncpu": ncpu, "events_lines": st["events_lines"],
                 "input_bytes": st["bytes"], "load_before": load, "warmup": [], "runs": []}
        hashes = []
        exp = cached_ok(name) if self.suite[name]["kind"] == "oracle" else None
        i = 0
        while i < warmup + runs:
            res = run_once(self.binary, ds, out, scratch, ncpu, timeout=600)
            self.stdout_max = max(self.stdout_max, res["stdout_bytes"])
            if res["returncode"] != 0:
                log(f"  run {i}: FAILED rc={res['returncode']}: {res.get('stderr_tail', '')[-300:]}")
            if check and res["returncode"] == 0:
                h = canonical_hash(out)
                res["canonical_hash"] = h["hash"]
                res["rows"] = h["rows"]
                res["files_sha"] = self.files_sha(out)
                hashes.append(h["hash"])
                if i == 0:
                    self.r["correctness"]["row_counts"][name] = h["rows"]
                    if self.suite[name]["kind"] == "oracle" and exp:
                        d = check_output(out, EXPECTED / name, exp["canonical"]["hash"]) \
                            if h["hash"] != exp["canonical"]["hash"] else {"match": True, "hash": h["hash"],
                                                                            "rows": h["rows"]}
                        d["kind"] = "oracle"
                        d["against"] = f"data/expected/{name} (reference {exp['reference_sha'][:8]})"
                        self.r["correctness"]["differential"][name] = d
                        log(f"  differential {name}: {'MATCH' if d['match'] else 'DIFFER'}")
                    elif self.suite[name]["kind"] == "consistency":
                        self.consistency(name, out, h)
            (block["warmup"] if i < warmup else block["runs"]).append(res)
            log(f"  {'warm-up' if i < warmup else 'run'} {i - warmup if i >= warmup else i}: "
                f"{res['wall_s']:.3f}s, RSS {res.get('max_rss_bytes', 0) / 2**30:.2f} GiB, "
                f"cpu {res.get('cpu_util', 0) or 0:.2f}")
            i += 1
            if i == warmup + runs and runs < gates.FAST_RUNS:
                wall = summarize([r["wall_s"] for r in block["runs"] if r["returncode"] == 0])
                if gates.is_fast(wall):
                    runs = gates.FAST_RUNS
                    log(f"  median under {gates.FAST_WALL_S}s; extending to {runs} timed runs")
        s = summarize_runs(block["runs"], st["events_lines"])
        block["summary"] = s
        w = s["wall_s"]
        if w.get("n"):
            block["throughput"] = {"mb_per_s": round(st["bytes"] / 1e6 / w["median"], 1),
                                   "events_per_s": round(st["events_lines"] / w["median"]),
                                   "ns_per_event": round(w["median"] * 1e9 / max(st["events_lines"], 1), 2)}
        reasons = []
        if (load.get("cpu_busy_pct") or 0) > NOISY_BUSY_PCT:  # still busy after wait_quiet's 30 s
            reasons.append(f"CPU {load['cpu_busy_pct']}% busy before the block (> {NOISY_BUSY_PCT}%)")
        if w.get("cv") and w["cv"] > NOISY_CV and w["n"] >= 3:
            reasons.append(f"wall CV {w['cv']:.3f} > {NOISY_CV}")
        block["noisy"] = bool(reasons)
        block["noisy_reasons"] = reasons
        if check and hashes:
            self.r["correctness"]["determinism"].setdefault(name, {"runs": 0, "hashes": []})
            det = self.r["correctness"]["determinism"][name]
            det["runs"] += len(hashes)
            det["hashes"] = sorted(set(det["hashes"]) | set(hashes))
            det["deterministic"] = len(det["hashes"]) == 1
            fs = {r.get("files_sha") for r in block["warmup"] + block["runs"] if r.get("files_sha")}
            det["byte_identical_files"] = len(fs) == 1
        if w.get("n"):
            log(f"  => median {w['median']:.3f}s  min {w['min']:.3f}  p90 {w['p90']:.3f}  sd {w['stdev']:.4f}"
                + ("  [NOISY]" if reasons else ""))
        shutil.rmtree(out, ignore_errors=True)
        return block

    @staticmethod
    def wait_quiet(max_wait_s: float = 30.0) -> dict:
        """Wait (up to max_wait_s) until the machine is quiet. After a big run the kernel keeps
        reclaiming the freed memory for a few seconds, which slows the next run."""
        t = time.time()
        while True:
            load = load_snapshot()  # takes ~1 s
            if (load.get("cpu_busy_pct") or 0) <= NOISY_BUSY_PCT or time.time() - t > max_wait_s:
                load["waited_s"] = round(time.time() - t, 1)
                return load

    @staticmethod
    def files_sha(out: Path) -> str:
        import hashlib
        h = hashlib.sha256()
        for p in sorted(out.rglob("*")):
            if p.is_file():
                h.update(str(p.relative_to(out)).encode() + b"\0" + bytes.fromhex(sha256_file(p)))
        return h.hexdigest()[:16]

    def consistency(self, name, out, h):
        inv = invariants(out)
        res = {"kind": "consistency", "invariants": inv}
        res.update(hash=h["hash"], rows=h["rows"])
        base = read_json(CONSISTENCY / name / "meta.json")
        if base:
            res["baseline_version"] = base["version"]
            if h["hash"] == base["hash"]:
                res["baseline_match"] = True
            else:
                d = diff_outputs(out, CONSISTENCY / name)
                res["baseline_match"] = d["match"]
                res["diff"] = d
            res["match"] = inv["ok"] and res["baseline_match"]
        else:
            res["baseline_version"] = None
            res["baseline_match"] = None
            res["match"] = inv["ok"]
            # keep this output: it becomes the baseline if the version passes Gate A
            keep = WORK / "consistency-candidate" / name
            shutil.rmtree(keep, ignore_errors=True)
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(out, keep)
            self._consistency_candidate = (name, keep, h)
        log(f"  consistency {name}: invariants {'OK' if inv['ok'] else 'FAIL'}"
            f", vs baseline {res['baseline_version'] or '(none yet)'}: "
            f"{ {True: 'MATCH', False: 'DIFFER', None: 'n/a'}[res['baseline_match']] }")
        self.r["correctness"]["differential"][name] = res

    def perf(self):
        p = self.r["perf"]["datasets"]
        for role in self.prof["runs"]:
            b = self.step(f"perf {role}", self.perf_block, role)
            if b:
                p[role] = b

    def probe(self):
        role = self.prof["probe"]
        name = self.role(role)
        if not name:
            return
        log(f"probe: {name} once, sampling threads + RSS every 50 ms (untimed)")
        res = run_once(self.binary, DATA / name, self.runs_dir / "out", self.runs_dir / "scratch", 8, probe=True)
        self.stdout_max = max(self.stdout_max, res["stdout_bytes"])
        self.r["perf"]["probe"] = {"dataset": name, "wall_s": res["wall_s"], "threads_max": res.get("threads_max"),
                                   "rss_sampled_max_bytes": res.get("rss_sampled_max_bytes"),
                                   "timeline": res.get("timeline", []), "returncode": res["returncode"]}
        self.r["constraints"]["threads_max"] = res.get("threads_max")
        self.r["constraints"]["threads_probe"] = f"{name}, NCPU=8"
        log(f"  threads max {res.get('threads_max')}, sampled RSS max "
            f"{(res.get('rss_sampled_max_bytes') or 0) / 2**30:.2f} GiB")
        shutil.rmtree(self.runs_dir / "out", ignore_errors=True)

    def thread_scaling(self):
        base = self.r["perf"]["datasets"].get("perf-20M")
        if not base:
            return
        curve, detail = {}, {}
        host = self.r["host"]
        is_m5 = "M5" in host["machine"] and host["perf_cores"] == "5" and int(host["eff_cores"] or 0) >= 3
        for n in SCALING_NCPU:
            block = base if n == 8 else self.perf_block("perf-20M", ncpu=n, runs=SCALING_RUNS, warmup=0,
                                                       check=False, label=f"scaling NCPU={n}")
            if not block or not (s := block["summary"]["wall_s"]).get("n"):
                continue
            detail[str(n)] = {"cpu_util": block["summary"].get("cpu_util"),
                              "phases": {k: v["median"] for k, v in block["summary"]["phases"].items()}}
            curve[str(n)] = {"median_s": s["median"], "stdev_s": s["stdev"], "n": s["n"]}
        if "1" in curve:
            for key, point in curve.items():
                n = int(key)
                speedup = curve["1"]["median_s"] / point["median_s"]
                point.update(speedup=round(speedup, 3), efficiency=round(speedup / n, 3))
                if is_m5:
                    ceiling = min(n, 5) + max(n - 5, 0) * EFF_CORE_RATIO
                    point.update(p_core_equivalents=round(ceiling, 3), hybrid_efficiency=round(speedup / ceiling, 3))
                detail[key]["phase_speedup"] = {phase: round(detail["1"]["phases"][phase] / sec, 3)
                                               for phase, sec in detail[key]["phases"].items()
                                               if sec > 0 and phase in detail["1"]["phases"]}
        self.r["perf"]["thread_scaling"] = {"dataset": base["dataset"], "points": curve,
                                            "per_ncpu_detail": detail}

    def size_scaling(self):
        p = self.r["perf"]["datasets"]
        pts = {}
        for role in ("perf-1M", "perf-20M", "perf-60M"):
            b = p.get(role)
            if b and b["summary"]["wall_s"].get("n"):
                pts[role] = {"events": b["events_lines"], "median_s": b["summary"]["wall_s"]["median"],
                             "ns_per_event": b["throughput"]["ns_per_event"]}
        ratios = {}
        for a, b in (("perf-1M", "perf-20M"), ("perf-20M", "perf-60M"), ("perf-1M", "perf-60M")):
            if a in pts and b in pts:
                ratios[f"{b}/{a}"] = {"time_ratio": round(pts[b]["median_s"] / pts[a]["median_s"], 3),
                                      "events_ratio": round(pts[b]["events"] / pts[a]["events"], 3)}
        self.r["perf"]["size_scaling"] = {"points": pts, "ratios": ratios}

    # -------------------------------------------------------------- containers
    def containers(self):
        info = docker_info()
        self.r["build"]["docker"] = info
        if not info.get("available"):
            self.note("docker not available: container gates not run")
            return
        c = self.r["correctness"]
        imgs = self.r["build"].setdefault("images", {})
        # arm64: clean build (timed), fixtures, dev, overhead vs native
        arm = build_image(self.sha, "arm64", no_cache=True)
        imgs["arm64"] = arm
        self.r["constraints"]["clean_image_build_ok"] = arm["ok"]
        self.r["constraints"]["clean_image_build_detail"] = f"arm64 --no-cache in {arm['build_s']}s" if arm["ok"] \
            else "arm64 --no-cache build failed"
        ro_ok = True
        if arm["ok"]:
            run = runner_cmd(None, arm)
            c["fixtures_arm64"] = run_fixtures(run, jobs=6, label="arm64 container")
            c["dev_answer_arm64"] = self.container_dev(run, "arm64")
            ro_ok &= c["fixtures_arm64"]["passed"] == c["fixtures_arm64"]["total"] and c["dev_answer_arm64"]["match"]
            self.step("container overhead", self.container_overhead, run)
            self.step("Linux timing", self.linux_timing, arm, info, self.r.get("baseline"))
            if self.r["perf"].get("linux_timing", {}).get("status") != "ok":
                self.step("Linux proxy", self.linux_proxy, arm, info)
            self.step("Linux 60M memory cap", self.linux_memory, arm, info)
        amd = build_image(self.sha, "amd64")
        imgs["amd64"] = amd
        if amd["ok"]:
            run = runner_cmd(None, amd)
            c["fixtures_amd64"] = run_fixtures(run, jobs=6, label="amd64 container (emulated)")
            c["dev_answer_amd64"] = self.container_dev(run, "amd64")
            ro_ok &= c["fixtures_amd64"]["passed"] == c["fixtures_amd64"]["total"] and c["dev_answer_amd64"]["match"]
            self.step("amd64 SWAR knob", self.amd64_knobs, run)
        else:
            c["fixtures_amd64"] = {"passed": 0, "total": 36, "failed": [{"case": "*", "error": "image build failed"}]}
            ro_ok = False
        cascadelake = build_image(self.sha, "amd64", no_cache=True, x86_cpu="cascadelake")
        imgs["amd64-cascadelake"] = cascadelake
        self.r["constraints"]["cascadelake_build_ok"] = cascadelake["ok"]
        self.r["constraints"]["readonly_container_ok"] = ro_ok

    def amd64_knobs(self, run=None):
        """amd64 container fixtures + dev with the portable SWAR classifier (NO_FAST=3), next to the SSE2 default."""
        if run is None:
            amd = self.r["build"].get("images", {}).get("amd64")
            if not amd or not amd.get("ok"):
                amd = self.r["build"].setdefault("images", {})["amd64"] = build_image(self.sha, "amd64")
            if not amd["ok"]:
                raise RuntimeError("amd64 image build failed")
            run = runner_cmd(None, amd)
        c = self.r["correctness"]
        for key, value in AMD64_KNOBS:
            if key.encode() not in self.binary.read_bytes():
                continue
            label = f"{key}={value}"
            knob_run = partial(run, extra_env={key: value})
            fx = run_fixtures(knob_run, jobs=6, label=f"amd64 container {label}")
            dev = self.container_dev(knob_run, f"amd64 {label}")
            c.setdefault("amd64_knobs", {})[label] = {"fixtures": fx, "dev": dev}

    def container_dev(self, run, arch):
        out = self.runs_dir / f"dev-{arch}".replace(" ", "_").replace("=", "_")
        shutil.rmtree(out, ignore_errors=True)
        p = run(DATA / "dev", out)
        if p.returncode != 0:
            res = {"match": False, "error": f"exit {p.returncode}: {p.stderr.decode()[-300:]}"}
        else:
            res = check_output(out, DATA / "dev-answer", self.answer_hash("dev-answer"))
            res.pop("hash", None)
        log(f"dev in {arch} container: {'MATCH' if res.get('match') else 'DIFFER'}")
        shutil.rmtree(out, ignore_errors=True)
        return res

    def container_overhead(self, run):
        out = self.runs_dir / "ovh"
        walls, loads = [], []
        log("container overhead: arm64 container on dev, 1 warm-up + 5 runs")
        for i in range(6):
            shutil.rmtree(out, ignore_errors=True)
            load = sample_load()
            t = time.perf_counter()
            p = run(DATA / "dev", out)
            if p.returncode == 0 and i:
                walls.append(time.perf_counter() - t)
                loads.append(load)
        shutil.rmtree(out, ignore_errors=True)
        nat = self.r["perf"]["datasets"].get("perf-1M", {}).get("summary", {}).get("wall_s", {})
        s = summarize(walls)
        ovh = {"dev_container_wall_s": s, "dev_native_median_s": nat.get("median"), "sample_loads": loads}
        if nat.get("median") and s.get("n"):
            ovh["dev_overhead_s"] = round(s["median"] - nat["median"], 3)
            ovh["dev_ratio"] = round(s["median"] / nat["median"], 2)
        self.r["perf"]["container_overhead"] = ovh
        log(f"  dev container median {s.get('median', 0):.3f}s vs native {nat.get('median') or 0:.3f}s")

    def linux_proxy(self, image, info):
        perf = self.r["perf"]
        datasets = []
        for role in ("perf-20M", "perf-1M"):
            if name := self.role(role):
                footprint = perf["datasets"].get(role, {}).get("summary", {}).get("peak_footprint_bytes", {})
                datasets.append((name, footprint.get("max", 0)))
        perf["linux_proxy"] = probe_linux(image, info, datasets)

    def linux_profile(self):
        try:
            info = docker_info()
        except FileNotFoundError:
            info = {"available": False}
        self.r["build"]["docker"] = info
        if not info.get("available"):
            self.r["perf"]["linux_timing"] = {"status": "unavailable", "reason": "Docker unavailable"}
            return
        arm = build_image(self.sha, "arm64")
        self.r["build"]["images"] = {"arm64": arm}
        self.linux_timing(arm, info, gates.best_baseline(self.a.version))

    def linux_timing(self, image, info, baseline):
        perf = self.r["perf"]
        name = self.role("perf-20M")
        if not name or not image["ok"]:
            perf["linux_timing"] = {"status": "unavailable", "reason": "20M dataset or arm64 image unavailable"}
            return
        base_image = None
        if baseline and baseline["sha"] and baseline["sha"] != self.sha:
            built = build_image(baseline["sha"], "arm64")
            if built["ok"]:
                base_image = built
            else:
                self.note(f"Linux timing: arm64 baseline image failed for {baseline['version']}")
        footprint = perf["datasets"].get("perf-20M", {}).get("summary", {}).get("peak_footprint_bytes", {})
        result = probe_linux(image, info, [(name, footprint.get("max", 0))],
                             timed_runs=self.a.ab_runs or AB_RUNS, event_lines=dataset_stats(DATA / name)["events_lines"],
                             baseline_image=base_image, before_timing=self.wait_quiet)
        if baseline:
            result["baseline_version"] = baseline["version"]
            result["baseline_sha"] = baseline["sha"]
        result["noisy"] = any((result.get(key, {}).get("process_wall_s", {}).get("cv") or 0) > NOISY_CV
                              for key in ("summary", "baseline_summary"))
        perf["linux_timing"] = result

    def linux_ab(self):
        """Paired Linux 20M A/B against the Gate C baseline, on its own (used by --amend linux-ab)."""
        info = docker_info()
        self.r["build"]["docker"] = info
        if not info.get("available"):
            raise RuntimeError("Docker unavailable")
        arm = build_image(self.sha, "arm64")
        self.linux_timing(arm, info, self.r.get("baseline") or gates.best_baseline(self.a.version))

    def linux_memory(self, image, info):
        name = self.role("perf-60M")
        if not name:
            return
        self.r["perf"]["linux_60m_memory"] = probe_linux(image, info, [(name, 0)], memory_check=True)

    def cold_cache(self):
        perf = self.r["perf"]
        cold = perf["cold_cache"] = {"status": "unavailable"}
        name = self.role("perf-20M")
        purge = shutil.which("purge")
        if not name or not purge:
            cold["reason"] = "20M dataset or macOS purge is unavailable"
            return
        cold.update(dataset=name, load_before=self.wait_quiet())
        try:
            p = subprocess.run([purge], capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            cold["reason"] = str(e)
            return
        if p.returncode:
            cold["reason"] = p.stderr.strip() or f"purge exited {p.returncode}"
            return
        log(f"cold cache: one run on {name} after purge")
        out, scratch = self.runs_dir / "out", self.runs_dir / "scratch"
        run = run_once(self.binary, DATA / name, out, scratch, 8)
        shutil.rmtree(out, ignore_errors=True)
        self.stdout_max = max(self.stdout_max, run["stdout_bytes"])
        cold.update(status="ok" if run["returncode"] == 0 else "failed", run=run)
        cold["warm_median_s"] = (gates.perf_20m(self.r) or {}).get("median")

    # -------------------------------------------------------------- baseline / A-B
    def baseline(self):
        base = gates.best_baseline(self.a.version)
        if base and base.get("sha") == self.sha:
            base["note"] = "baseline is the same commit"
        self.r["baseline"] = base
        if not base or base.get("sha") == self.sha:
            return
        fast = gates.is_fast(gates.perf_20m(self.r)) or gates.is_fast(base["wall_s"])
        if not fast and not self.prof["ab"]:
            return
        name = self.role("perf-20M")
        if not name:
            return
        try:
            bbin = Path(build_native(base["sha"])["binary"])
        except Exception as e:  # noqa: BLE001
            self.note(f"A/B: could not build baseline {base['version']}: {e}")
            return
        out, scratch = self.runs_dir / "out", self.runs_dir / "scratch"
        base["ab_load_before"] = self.wait_quiet()
        for binary in (self.binary, bbin):
            r = run_once(binary, DATA / name, out, scratch, 8)
            self.stdout_max = max(self.stdout_max, r["stdout_bytes"])
        cand, bl = [], []
        base["ab_sample_loads"] = []
        runs = max(self.a.ab_runs or AB_RUNS, gates.FAST_RUNS if fast else AB_RUNS)
        if self.a.ab_runs:
            base["ab_required_pairs"] = self.a.ab_runs
        log(f"A/B: interleaving {runs} runs each of {self.a.version} and {base['version']} on {name}")
        i = 0
        while i < runs:
            order = (self.binary, bbin) if i % 2 == 0 else (bbin, self.binary)
            pair = {}
            loads = {}
            for b in order:
                r = run_once(b, DATA / name, out, scratch, 8)
                self.stdout_max = max(self.stdout_max, r["stdout_bytes"])
                if r["returncode"] == 0:
                    pair[b] = r["wall_s"]
                    loads[b] = r["load_before"]
            if len(pair) == 2:
                cand.append(pair[self.binary])
                bl.append(pair[bbin])
                base["ab_sample_loads"].append({"candidate": loads[self.binary], "baseline": loads[bbin]})
            i += 1
            if i == AB_RUNS and not fast and any(gates.is_fast(summarize(x)) for x in (cand, bl)):
                runs = max(runs, gates.FAST_RUNS)
                log(f"  A/B median under {gates.FAST_WALL_S}s; extending to {runs} pairs")
        shutil.rmtree(out, ignore_errors=True)
        base["ab_wall_s"] = summarize(bl)
        base["ab_candidate_wall_s"] = summarize(cand)
        log(f"  A/B medians: candidate {base['ab_candidate_wall_s'].get('median')}s, "
            f"baseline {base['ab_wall_s'].get('median')}s")

    # -------------------------------------------------------------- finish
    def constraints(self):
        k = self.r["constraints"]
        for b in self.r["perf"]["datasets"].values():
            for run in b.get("runs", []) + b.get("warmup", []):
                self.stdout_max = max(self.stdout_max, run.get("stdout_bytes", 0))
        k["stdout_bytes_max"] = self.stdout_max
        k["repo"] = repo_size(self.sha)
        k["binary_bytes"] = self.r["build"].get("native", {}).get("binary_bytes")
        k["image_bytes"] = {a: i.get("image_bytes") for a, i in self.r["build"].get("images", {}).items()}

    def calibration(self):
        cal = read_json(EVALS / "calibration.json", {})
        stats = gates.perf_20m(self.r) or {}
        self.r["calibration"] = calibration_report(cal, stats.get("median"), ipr_20m(self.r))

    def finish(self):
        r = self.r
        # every oracle dataset in the suite must have been diffed for Gate A to pass
        r["_suite_oracle_missing"] = [n for n, d in self.suite.items() if d["kind"] == "oracle"
                                      and n not in r["correctness"]["differential"]]
        r["gates"] = {"A": gates.gate_a(r), "B": gates.gate_b(r), "C": gates.gate_c(r)}
        r.pop("_suite_oracle_missing", None)
        r["verdict"] = gates.verdict(r)
        if not r.get("calibration", {}).get("points"):
            self.note("Calibration has no board times. Record the next submitted candidate via make eval-calibrate.")
        if r["errors"]:
            r["verdict"]["reasons"].append(f"{len(r['errors'])} framework error(s): see errors[]")
            if r["verdict"]["verdict"] == "SUBMIT-READY":
                r["verdict"].update(verdict="HOLD", final=False)
        # a version that passes Gate A becomes the 60M consistency baseline if none exists yet
        cc = getattr(self, "_consistency_candidate", None)
        if cc and r["gates"]["A"]["status"] == "pass":
            name, keep, h = cc
            dest = CONSISTENCY / name
            shutil.rmtree(dest, ignore_errors=True)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(keep), str(dest))
            write_json(dest / "meta.json", {"version": r["version"], "sha": self.sha, "hash": h["hash"],
                                            "rows": h["rows"], "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                            "why": "first version to pass Gate A; baseline for 60M consistency"})
            r["correctness"]["differential"][name]["baseline_established"] = True
            self.note(f"{r['version']} established the 60M consistency baseline in data/consistency/{name}")
        r["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        r["duration_s"] = round(time.time() - self.t0, 1)
        out = EVALS / "results"
        write_json(out / f"{r['version']}.json", r)
        (out / f"{r['version']}.md").write_text(render_md(r))
        if not self.a.no_ledger:
            append_ledger(r)
        shutil.rmtree(self.runs_dir, ignore_errors=True)
        log(f"VERDICT {r['verdict']['verdict']}{'' if r['verdict']['final'] else ' (provisional)'}: "
            + "; ".join(r["verdict"]["reasons"][:6]))
        log(f"wrote evals/results/{r['version']}.json and .md in {r['duration_s']:.0f}s")

    @benchmark_lock()
    def amend(self, stages):
        """Add stages to an existing result for the same commit, then recompute gates, verdict, report, ledger."""
        path = EVALS / "results" / f"{self.a.version}.json"
        old = read_json(path)
        if not old:
            raise SystemExit(f"--amend: {path} does not exist")
        if old["sha"] != self.sha:
            raise SystemExit(f"--amend: {path} is for {old['sha'][:12]}, not {self.sha[:12]}")
        self.r = old
        self.r.setdefault("errors", [])
        self.r.setdefault("notes", [])
        self.prof = dict(PROFILES[old["profile"]])
        if self.a.fuzz_seeds is not None:
            self.prof["fuzz_seeds"] = self.a.fuzz_seeds
        log(f"amend {self.a.version} @ {self.sha[:12]} (profile {old['profile']}): {', '.join(stages)}")
        self.step("build", self.build)
        if not hasattr(self, "binary"):
            raise SystemExit("--amend: native build failed")
        for stage in stages:
            self.step(stage, getattr(self, AMEND_STAGES[stage]))
        r = self.r
        r["_suite_oracle_missing"] = [n for n, d in self.suite.items() if d["kind"] == "oracle"
                                      and n not in r["correctness"]["differential"]]
        r["gates"] = {"A": gates.gate_a(r), "B": gates.gate_b(r), "C": gates.gate_c(r)}
        r.pop("_suite_oracle_missing", None)
        r["verdict"] = gates.verdict(r)
        if r["errors"]:
            r["verdict"]["reasons"].append(f"{len(r['errors'])} framework error(s): see errors[]")
            if r["verdict"]["verdict"] == "SUBMIT-READY":
                r["verdict"].update(verdict="HOLD", final=False)
        r.setdefault("amendments", []).append({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "stages": stages,
                                               "eval_sha": eval_sha(),
                                               "duration_s": round(time.time() - self.t0, 1)})
        write_json(path, r)
        (EVALS / "results" / f"{r['version']}.md").write_text(render_md(r))
        if not self.a.no_ledger:
            append_ledger(r, replace=True)
        shutil.rmtree(self.runs_dir, ignore_errors=True)
        log(f"VERDICT {r['verdict']['verdict']}{'' if r['verdict']['final'] else ' (provisional)'}: "
            + "; ".join(r["verdict"]["reasons"][:6]))
        log(f"amended evals/results/{r['version']}.json and .md")

    @benchmark_lock()
    def main(self):
        log(f"eval {self.a.version}: rev {self.a.rev} = {self.sha[:12]}, profile {self.a.profile}")
        self.step("build", self.build)
        if not hasattr(self, "binary"):
            self.r["verdict"] = {"verdict": "REJECT", "final": True, "reasons": ["native build failed"]}
            r = self.r
            r["gates"] = {}
            write_json(EVALS / "results" / f"{r['version']}.json", r)
            sys.exit(1)
        self.step("correctness", self.correctness_untimed)
        self.step("fuzz", self.fuzz)
        self.step("debug knobs", self.debug_knobs)
        self.step("review suites", self.review)
        self.step("fuzz windows", self.fuzz_windows)
        if self.a.profile == "linux":
            self.step("Linux timing", self.linux_profile)
        self.perf()
        if self.prof["probe"]:
            self.step("probe", self.probe)
        if self.prof["thread_scaling"]:
            self.step("thread scaling", self.thread_scaling)
        self.step("size scaling", self.size_scaling)
        self.step("baseline", self.baseline)
        if self.prof["docker"]:
            self.step("containers", self.containers)
        if self.a.profile == "full":
            self.step("cold cache", self.cold_cache)
        self.step("constraints", self.constraints)
        self.step("calibration", self.calibration)
        self.finish()


# ------------------------------------------------------------------ reports

def fmt_s(x):
    return "n/a" if x is None else f"{x:.3f}s"


def fmt_ipr(x):
    return "-" if x is None else f"{x:,.0f}"


def fmt_number(x):
    return "n/a" if x is None else f"{x:,.2f}"


def render_prediction(cal: dict) -> list[str]:
    """Primary metric: predicted practice-board time from both models, next to instructions per row and the target."""
    if not cal:
        return []
    L = ["", "## Predicted board time (20M practice)", "",
         "| Predictor | Predicted board | Input | Model |", "| --- | --- | --- | --- |"]
    im = cal.get("instr_model") or {}
    if cal.get("estimated_scorer_20m_instr_s") is not None:
        L.append(f"| instructions (primary) | **{cal['estimated_scorer_20m_instr_s']:.3f} s** | "
                 f"{cal['instructions_per_row']:,.0f} instr/row | {im['fixed_s']:.3f} s + instr/row × "
                 f"{im['board_rows'] / 1e6:.0f}M / {im['rate_instr_per_s'] / 1e9:.2f} G/s ({im['method']}, "
                 f"{im['points']} point(s)) |")
    elif cal.get("instructions_per_row"):
        L.append(f"| instructions | n/a | {cal['instructions_per_row']:,.0f} instr/row | no board points |")
    if cal.get("estimated_scorer_20m_s") is not None:
        L.append(f"| local wall | {cal['estimated_scorer_20m_s']:.3f} s"
                 + (" (extrapolated)" if cal.get("extrapolated") else "") + f" | 20M median | "
                 f"{cal.get('intercept', 0):.3f} s + {cal['slope']:.3f} × local ({cal['method']}, {cal['points']} point(s)) |")
    t = cal.get("target") or {}
    if t:
        L += ["", f"Target: {t['summary']}."]
        if cal.get("beats_board_target") is not None:
            L.append(f"Primary prediction {'beats' if cal['beats_board_target'] else 'is above'} the "
                     f"{t['board_target_s']:.2f} s target.")
    return L


def render_md(r: dict) -> str:
    c, p = r["correctness"], r["perf"]
    L = [f"# Eval: {r['version']} ({r['sha'][:12]}, profile {r['profile']})", "",
         f"**Verdict: {r['verdict']['verdict']}**" + ("" if r["verdict"]["final"] else " (provisional)"), ""]
    L += [f"- {x}" for x in r["verdict"]["reasons"]]
    L += [f"- WARNING: {x}" for x in r["verdict"].get("warnings", [])]
    L += render_prediction(r.get("calibration") or {})
    L += ["", f"Run {r['started']} → {r.get('finished')}, {r.get('duration_s')} s. Host: {r['host']['machine']}, "
               f"{r['host']['ncpu']} CPUs. Evaluator {r['evaluator']['eval_sha']}.", "", "## Gates", "",
          "| Gate | Check | Status | Detail |", "| --- | --- | --- | --- |"]
    for g, gate in r["gates"].items():
        for x in gate["checks"]:
            L.append(f"| {g} | {x['name']} | {x['status'].upper()} | {x['detail']} |")
        if linux := gate.get("linux_ab", gate.get("linux_secondary")):
            L.append(f"| {g} | Linux 20M A/B | {linux['status'].upper()} | {linux['detail']} |")
        if native := gate.get("native"):
            for x in native["checks"]:
                L.append(f"| {g} | Native: {x['name']} | {x['status'].upper()} | {x['detail']} |")
    L += ["", "## Correctness", ""]
    for k in ("fixtures_native", "fixtures_arm64", "fixtures_amd64"):
        if c.get(k):
            L.append(f"- {k}: {c[k]['passed']}/{c[k]['total']}"
                     + (f" — failed {[f['case'] for f in c[k]['failed']]}" if c[k]["failed"] else ""))
    for k in ("dev_answer_native", "dev_answer_arm64", "dev_answer_amd64"):
        if c.get(k):
            L.append(f"- {k}: {'MATCH' if c[k].get('match') else 'DIFFER'}")
    L += ["", "| Dataset | Kind | Result | user_daily rows | campaign_daily rows |", "| --- | --- | --- | --- | --- |"]
    for name, d in c["differential"].items():
        rows = d.get("rows") or {}
        if d["kind"] == "oracle":
            res = "MATCH" if d.get("match") else "DIFFER"
        else:
            inv = "invariants OK" if d["invariants"]["ok"] else "invariants FAIL"
            bl = {True: f"MATCH vs {d.get('baseline_version')}", False: f"DIFFER vs {d.get('baseline_version')}",
                  None: "no baseline yet" + (" (established now)" if d.get("baseline_established") else "")}[
                d.get("baseline_match")]
            res = f"{inv}; {bl}"
        L.append(f"| {name} | {d['kind']} | {res} | {rows.get('user_daily', '')} | {rows.get('campaign_daily', '')} |")
    fz = c.get("fuzz")
    if fz:
        s, rb = fz["strict"], fz["robust"]
        L += ["", f"Fuzz (gen {fz['gen_sha']}, seeds {fz['seeds'][0]}..{fz['seeds'][1] - 1}): strict "
                  f"{s['passed']}/{s['total'] - s['skipped']} MATCH, robust {rb['passed']}/{rb['total'] - rb['skipped']}."]
        for f in (s["failed"] + rb["failed"])[:10]:
            L.append(f"- seed {f['seed']} ({f['focus']}{', robust' if f['robust_reasons'] else ''}): "
                     f"{f.get('error') or 'DIFFER'} — `{f['repro']}`")
    fw = c.get("fuzz_windows")
    if fw:
        s, rb = fw["strict"], fw["robust"]
        L += ["", f"Fuzz `windows` focus (seeds {fw['seeds'][0]}..{fw['seeds'][1] - 1}): strict "
                  f"{s['passed']}/{s['total'] - s['skipped']} MATCH, robust (off-midnight windows) "
                  f"{rb['passed']}/{rb['total'] - rb['skipped']}."]
        for f in (s["failed"] + rb["failed"])[:10]:
            L.append(f"- seed {f['seed']} ({', '.join(f['tags'][:6])}{', robust' if f['robust_reasons'] else ''}): "
                     f"{f.get('error') or 'DIFFER'} — `{f['repro']}`")
    for name, rv in c.get("review_suites", {}).items():
        per = ", ".join(f"{k} {v['passed']}/{v['total']} in {v['wall_s']}s" for k, v in rv.get("scripts", {}).items())
        L += ["", f"Review suite `{name}` ({rv['runner']}): {rv['passed']}/{rv['total']} MATCH"
                  + (f" ({per})" if per else "") + (f"; {rv['error']}" if rv.get("error") else "") + "."]
        L += [f"- {x}" for x in rv["failed"][:10]]
    for label, item in c.get("amd64_knobs", {}).items():
        f, d = item["fixtures"], item["dev"]
        L += ["", f"amd64 container with `{label}`: fixtures {f['passed']}/{f['total']}, dev "
                  f"{'MATCH' if d.get('match') else d.get('error', 'DIFFER')}."]
    if r.get("amendments"):
        L += ["", "Amendments: " + "; ".join(f"{a['at']} added {', '.join(a['stages'])} (evaluator {a['eval_sha'][:12]})"
                                            for a in r["amendments"])]
    if c["determinism"]:
        L += ["", "Determinism: " + ", ".join(
            f"{k} {'same hash' if v['deterministic'] else 'DIFFERENT hashes'} over {v['runs']} runs"
            f"{'' if v.get('byte_identical_files') else ' (files not byte-identical)'}" for k, v in
            c["determinism"].items())]
    knobs = c.get("debug_knobs", {})
    if knobs:
        L += ["", "Debug knobs"]
        if all(v["status"] == "n/a" for v in knobs.values()):
            L.append("- n/a")
        else:
            L.extend(f"- `{name}`: {item['status']}" for name, item in knobs.items())
    L += ["", "## Performance (native, NCPU=8)", "",
          "| Dataset | Runs | Median | Min | p90 | Stdev | MB/s | Mev/s | CPU util | user/sys | Peak footprint | Max RSS (incl. file pages) | Noisy |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for role, b in p["datasets"].items():
        s = b["summary"]
        w = s["wall_s"]
        if not w.get("n"):
            L.append(f"| {b['dataset']} | 0 | failed | | | | | | | | | | |")
            continue
        t = b.get("throughput", {})
        L.append(f"| {b['dataset']} ({role}) | {w['n']} | {fmt_s(w['median'])} | {fmt_s(w['min'])} | {fmt_s(w['p90'])} "
                 f"| {w['stdev']:.4f} | {t.get('mb_per_s')} | {t.get('events_per_s', 0) / 1e6:.1f} "
                 f"| {s.get('cpu_util', {}).get('median', 0):.2f} "
                 f"| {s.get('user_s', {}).get('median', 0):.2f}/{s.get('sys_s', {}).get('median', 0):.2f} "
                 f"| {s.get('peak_footprint_bytes', {}).get('max', 0) / 1e9:.2f} GB "
                 f"| {s.get('max_rss_bytes', {}).get('max', 0) / 1e9:.2f} GB | {'yes' if b['noisy'] else 'no'} |")
    for role, b in p["datasets"].items():
        ph = b["summary"].get("phases", {})
        if not ph:
            continue
        L += ["", f"Phases, {b['dataset']} (median of {b['summary']['wall_s'].get('n')} runs):", "",
              "| Phase | Wall | Share | CPU | CPU / wall |", "| --- | --- | --- | --- | --- |"]
        tot = b["summary"]["wall_s"].get("median") or 1
        for k, v in ph.items():
            cpu = fmt_s(v.get("cpu_s", {}).get("median"))
            parallelism = fmt_number(v.get("parallelism", {}).get("median"))
            L.append(f"| {k} | {fmt_s(v.get('median'))} | {100 * (v.get('median') or 0) / tot:.0f}% | "
                     f"{cpu} | {parallelism} |")
        L += ["", f"Resources (median): page reclaims {b['summary'].get('page_reclaims', {}).get('median')}, "
                  f"page faults {b['summary'].get('page_faults', {}).get('median')}, vol ctx sw "
                  f"{b['summary'].get('vcsw', {}).get('median')}, invol ctx sw {b['summary'].get('ivcsw', {}).get('median')}, "
                  f"peak footprint {b['summary'].get('peak_footprint_bytes', {}).get('max', 0) / 2**30:.2f} GiB"]
        counters = [("instructions/row", "instructions_per_row"), ("cycles/row", "cycles_per_row"), ("IPC", "ipc")]
        L.append("Hardware counters (median): " + ", ".join(
            f"{label} {fmt_number(b['summary'].get(key, {}).get('median'))}" for label, key in counters))
    if timing := p.get("linux_timing"):
        L += ["", "## Linux and native 20M timing", ""]
        if timing["status"] == "ok":
            L += ["| Runtime | Version | Runs | Median | Min | Minor faults / row | Major faults / row |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
            base = r.get("baseline") or {}
            for label, stats, version in (
                ("Linux arm64", timing["summary"], r["version"]),
                ("Linux arm64", timing.get("baseline_summary", {}), timing.get("baseline_version")),
                ("Native", {"process_wall_s": base.get("ab_candidate_wall_s") or gates.perf_20m(r)}, r["version"]),
                ("Native", {"process_wall_s": base.get("ab_wall_s")}, base.get("version")),
            ):
                if not (wall := stats.get("process_wall_s")) or not wall.get("n"):
                    continue
                faults = [stats.get(f"{kind}_faults_per_row", {}).get("median") for kind in ("minor", "major")]
                minor, major = ("n/a" if fault is None else f"{fault:.6f}" for fault in faults)
                L.append(f"| {label} | {version} | {wall['n']} | {fmt_s(wall['median'])} | {fmt_s(wall['min'])} "
                         f"| {minor} | {major} |")
            first = timing["warmup"]
            L += ["", f"Named volume, 8 CPUs, {timing['mem_gib']} GiB cgroup limit, "
                       f"THP {first['thp_mode'] or 'unknown'}, page size {first['page_bytes'] or 'unknown'} B."]
            if timing.get("baseline_error"):
                L.append("Linux baseline timing unavailable. See the result JSON for details.")
            if timing.get("noisy"):
                L.append("Linux wall-time CV exceeded 3% for at least one version.")
            L += ["", "| Linux metric | Candidate median | Baseline median |", "| --- | --- | --- |"]
            for key, label, scale in (
                ("minor_faults", "Minor faults", 1), ("major_faults", "Major faults", 1),
                ("sys_s", "System CPU (s)", 1), ("exit_tail_s", "Exit tail (s)", 1),
                ("thp_fault_alloc", "VM THP allocations", 1), ("thp_fault_fallback", "VM THP fallbacks", 1),
                ("peak_anon_bytes", "Peak sampled anonymous (GiB)", 2**30),
                ("peak_anon_huge_bytes", "Peak sampled anonymous huge pages (GiB)", 2**30),
            ):
                vals = [s.get(key, {}).get("median") for s in (timing["summary"], timing.get("baseline_summary", {}))]
                a, b = ("n/a" if v is None else f"{v / scale:,.3f}".rstrip("0").rstrip(".") for v in vals)
                L.append(f"| {label} | {a} | {b} |")
        else:
            detail = timing.get("reason") or "; ".join(a.get("error", "") for a in timing.get("attempts", []))
            L.append("Unavailable. " + detail.strip().replace("\n", " "))
    if memory := p.get("linux_60m_memory"):
        peak = memory.get("sample", {}).get("cgroup_peak_bytes")
        detail = f"{peak / 2**30:.2f} GiB peak" if peak else (memory.get("reason") or memory["status"])
        L += ["", f"60M Linux memory check under 22 GiB: {detail}."]
    ts = p.get("thread_scaling")
    if ts:
        L += ["", f"## Thread scaling ({ts['dataset']})", "",
              "| NCPU | Median | Speedup | Efficiency | P-core equivalents | Hybrid efficiency |",
              "| --- | --- | --- | --- | --- | --- |"]
        for n, v in ts["points"].items():
            L.append(f"| {n} | {fmt_s(v['median_s'])} | {v.get('speedup', '')} | {v.get('efficiency', '')} "
                     f"| {v.get('p_core_equivalents', '')} | {v.get('hybrid_efficiency', '')} |")
        scaling = {n: detail["phase_speedup"] for n, detail in ts["per_ncpu_detail"].items()
                   if "phase_speedup" in detail}
        if scaling:
            L += ["", "| Phase speedup vs NCPU=1 | " + " | ".join(scaling) + " |",
                  "| --- " * (len(scaling) + 1) + "|"]
            for phase in scaling.get("1", {}):
                L.append(f"| {phase} | " + " | ".join(fmt_number(s.get(phase)) for s in scaling.values()) + " |")
    ss = p.get("size_scaling", {})
    if ss.get("ratios"):
        L += ["", "## Size scaling", ""] + [f"- {k}: time ×{v['time_ratio']} for events ×{v['events_ratio']}"
                                            for k, v in ss["ratios"].items()]
        L += [f"- {k}: {v['ns_per_event']} ns/event" for k, v in ss["points"].items()]
    co = p.get("container_overhead")
    if co:
        L += ["", "## Container overhead (arm64, Docker Desktop)", "",
              f"- dev: container {fmt_s(co['dev_container_wall_s'].get('median'))} vs native "
              f"{fmt_s(co.get('dev_native_median_s'))} (+{co.get('dev_overhead_s')}s, ×{co.get('dev_ratio')})"]
        if co.get("20m_container_wall_s", {}).get("n"):
            L.append(f"- 20M (informational, virtiofs-bound): best {fmt_s(co['20m_container_wall_s']['min'])}, "
                     f"×{co.get('20m_ratio')} native")
    if proxy := p.get("linux_proxy"):
        L += ["", "## Linux page-fault proxy", ""]
        if proxy["status"] == "ok":
            s = proxy["sample"]
            L.append(f"- {proxy['dataset']}, named volume, {proxy['mem_gib']} GiB limit, "
                     f"THP {s['thp_mode'] or 'unavailable'}, page size {s['page_bytes'] or 'unknown'} B. "
                     f"Process {fmt_s(s['process_wall_s'])}, {s['minor_faults']:,} minor and {s['major_faults']:,} major faults.")
        elif proxy.get("reason"):
            L.append(f"- Unavailable: {proxy['reason'].splitlines()[-1]}")
        else:
            L.append("- Unavailable")
        for attempt in proxy["attempts"]:
            L.append(f"- {attempt['dataset']}: {attempt['error'].strip().splitlines()[-1] if attempt['error'].strip() else 'unavailable'}")
        if cold_linux := proxy.get("cold"):
            if cold_linux["status"] == "ok":
                s = cold_linux["sample"]
                L.append(f"- Linux cold {cold_linux['dataset']}: {fmt_s(s['process_wall_s'])}, "
                         f"{s['minor_faults']:,} minor and {s['major_faults']:,} major faults. "
                         f"`fincore` reported {cold_linux['resident_input_bytes_before']:,} resident input bytes before launch.")
            else:
                L.append("- Linux cold sample unavailable.")
    if cold := p.get("cold_cache"):
        L += ["", "## Cold cache", ""]
        if cold["status"] == "ok":
            L.append(f"- {cold['dataset']} after purge: {fmt_s(cold['run']['wall_s'])}, "
                     f"warm median {fmt_s(cold['warm_median_s'])}.")
        else:
            L.append(f"- {cold['status']}: {cold.get('reason', cold.get('run', {}).get('stderr_tail', '')).strip()}")
    pr = p.get("probe")
    k = r["constraints"]
    L += ["", "## Constraints and sizes", "",
          f"- threads max {k.get('threads_max')} ({k.get('threads_probe')}); stdout max {k.get('stdout_bytes_max')} bytes",
          f"- binary {(k.get('binary_bytes') or 0) / 1e6:.2f} MB; images "
          + ", ".join(f"{a} {(v or 0) / 1e6:.0f} MB" for a, v in (k.get("image_bytes") or {}).items()),
          f"- repo tracked {(k.get('repo', {}).get('tracked_bytes') or 0) / 1e6:.2f} MB",
          f"- native build {r['build'].get('native', {}).get('build_s')}s"
          + (" (cached)" if r["build"].get("native", {}).get("cached") else "")
          + "".join(f"; image {a} {i.get('build_s')}s{' clean' if i.get('no_cache') else ''}"
                    for a, i in r["build"].get("images", {}).items())]
    if pr:
        L.append(f"- probe on {pr['dataset']}: sampled RSS max {(pr.get('rss_sampled_max_bytes') or 0) / 2**30:.2f} GiB")
    base = r.get("baseline")
    if base:
        L += ["", f"Baseline for Gate C: {base['version']} ({base['kind']}), 20M median {fmt_s(base['wall_s']['median'])}"]
    if r["notes"]:
        L += ["", "## Notes", ""] + [f"- {n}" for n in r["notes"]]
    if r["errors"]:
        L += ["", "## Framework errors", ""] + [f"- {e['stage']}: {e['error']}" for e in r["errors"]]
    return "\n".join(L) + "\n"


LEDGER_HEADER = ("| Date | Version | Commit | Profile | Fixtures n/arm/amd | dev | Diff | Fuzz | Det | 1M | 20M | 60M "
                 "| Footprint 60M | Verdict | Board 20M (est.) | Linux 20M | Instr/row 20M | Board 20M (instr.) |\n"
                 + "| --- " * 18 + "|\n")


def append_ledger(r: dict, replace: bool = False):
    """Append r's row; with replace, overwrite the newest row for the same version and commit instead."""
    path = EVALS / "ledger.md"
    if not path.exists():
        path.write_text("# Eval ledger\n\nOne row per eval run (newest last). Details: `results/<version>.json`.\n\n"
                        + LEDGER_HEADER)
    c, p = r["correctness"], r["perf"]["datasets"]

    def fx(k):
        return f"{c[k]['passed']}" if c.get(k) else "-"

    def med(role):
        block = p.get(role, {})
        w = block.get("summary", {}).get("wall_s", {})
        if not w.get("n"):
            return "-"
        return f"{w['median']:.3f}s" + (" (noisy)" if block.get("noisy") else "")

    diffs = c["differential"]
    nd = sum(1 for d in diffs.values() if d.get("match"))
    fz = c.get("fuzz")
    fzs = f"{fz['strict']['passed']}/{fz['strict']['total'] - fz['strict']['skipped']}" if fz else "-"
    det = c["determinism"]
    rss = p.get("perf-60M", {}).get("summary", {}).get("peak_footprint_bytes", {}).get("max")
    dev = c.get("dev_answer_native", {}).get("match")
    estimate = r.get("calibration", {}).get("estimated_scorer_20m_s")
    linux_timing = r["perf"].get("linux_timing", {})
    linux_wall = linux_timing.get("summary", {}).get("process_wall_s", {})
    linux = fmt_s(linux_wall.get("median")) + (" (noisy)" if linux_timing.get("noisy") and linux_wall.get("n") else "")
    row = (f"| {r['started'][:16]} | {r['version']} | {r['sha'][:8]} | {r['profile']} | "
           f"{fx('fixtures_native')}/{fx('fixtures_arm64')}/{fx('fixtures_amd64')} | "
           f"{'MATCH' if dev else ('DIFFER' if dev is False else '-')} | {nd}/{len(diffs)} | {fzs} | "
           f"{'yes' if det and all(v['deterministic'] for v in det.values()) else ('NO' if det else '-')} | "
           f"{med('perf-1M')} | {med('perf-20M')} | {med('perf-60M')} | "
           f"{f'{rss / 1e9:.1f} GB' if rss else '-'} | {r['verdict']['verdict']}"
           f"{'' if r['verdict']['final'] else ' (prov.)'} | {fmt_s(estimate)} | {linux} | "
           f"{fmt_ipr(ipr_20m(r))} | {fmt_s(r.get('calibration', {}).get('estimated_scorer_20m_instr_s'))} |\n")
    lines = path.read_text().splitlines(keepends=True)
    key = f"| {r['version']} | {r['sha'][:8]} |"
    hits = [i for i, line in enumerate(lines) if key in line]
    if replace and hits:
        lines[hits[-1]] = row
        path.write_text("".join(lines))
        return
    with open(path, "a") as f:
        f.write(row)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True, help="name for this candidate, e.g. v2")
    ap.add_argument("--rev", required=True, help="git ref to build (tag, branch, sha)")
    ap.add_argument("--profile", choices=list(PROFILES), default="quick")
    ap.add_argument("--fuzz-seeds", type=int, default=None, help="override the number of fuzz seeds")
    ap.add_argument("--ab-runs", type=int, help="minimum interleaved A/B pairs in the full or linux profile")
    ap.add_argument("--no-docker", action="store_true", help="skip container gates even in the full profile")
    ap.add_argument("--no-ledger", action="store_true", help="don't append to evals/ledger.md")
    ap.add_argument("--rebuild", action="store_true", help="rebuild the native binary even if cached")
    ap.add_argument("--amend", metavar="STAGES",
                    help=f"comma-separated stages to add to the existing results/VERSION.json for the same commit "
                         f"(gates, report and ledger row are recomputed): {', '.join(AMEND_STAGES)}")
    a = ap.parse_args()
    if a.amend:
        stages = [x for x in a.amend.split(",") if x]
        bad = [x for x in stages if x not in AMEND_STAGES]
        if bad:
            ap.error(f"unknown --amend stage(s) {bad}; choose from {list(AMEND_STAGES)}")
        Eval(a).amend(stages)
        return
    if a.ab_runs is not None and (a.profile == "quick" or a.ab_runs < AB_RUNS):
        ap.error(f"--ab-runs requires the full or linux profile and at least {AB_RUNS} pairs")
    if a.profile == "linux" and a.no_docker:
        ap.error("the linux profile requires Docker")
    Eval(a).main()


if __name__ == "__main__":
    main()
