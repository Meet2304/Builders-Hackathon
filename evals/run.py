#!/usr/bin/env python3
"""Evaluate one candidate version of the pipeline.

    .venv/bin/python evals/run.py --version v2 --rev method/v2 [--profile quick|full]

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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import gates  # noqa: E402
from lib.build import build_image, build_native, docker_info, repo_size, resolve  # noqa: E402
from lib.common import (CONSISTENCY, DATA, EVALS, EXPECTED, REPO, WORK, canonical_hash, dataset_stats,  # noqa: E402
                        diff_outputs, invariants, log, read_json, reference_sha, sha256_file, write_json)
from lib.correct import check_output, fuzz_gen_sha, run_fixtures, run_fuzz, runner_cmd  # noqa: E402
from lib.measure import load_snapshot, run_once, summarize, summarize_runs  # noqa: E402

SCHEMA_VERSION = 1
NOISY_BUSY_PCT = 12.0   # machine-wide CPU busy % in the 1 s before a timed block
NOISY_CV = 0.05

PROFILES = {
    "quick": {"runs": {"perf-1M": 3, "perf-20M": 5, "perf-60M": 1}, "warmup": {"perf-1M": 1, "perf-20M": 1,
                                                                              "perf-60M": 0},
              "fuzz_seeds": 150, "thread_scaling": False, "docker": False, "probe": "perf-1M", "ab": False},
    "full": {"runs": {"perf-1M": 5, "perf-20M": 5, "perf-60M": 3}, "warmup": {"perf-1M": 1, "perf-20M": 1,
                                                                            "perf-60M": 1},
             "fuzz_seeds": 1000, "thread_scaling": True, "docker": True, "probe": "perf-60M", "ab": True},
}
SCALING_NCPU = [1, 2, 4, 8]
SCALING_RUNS = 3
AB_RUNS = 5


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

    def correctness_small(self):
        c = self.r["correctness"]
        c["fixtures_native"] = run_fixtures(self.run, label="native")
        missing = []
        for name, d in self.suite.items():
            if d["kind"] != "oracle" or d.get("events", 0) >= 5_000_000:
                continue
            exp = read_json(EXPECTED / name / "meta.json")
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
        self.r["correctness"]["fuzz"] = run_fuzz(self.run, range(0, n))

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
        exp = read_json(EXPECTED / name / "meta.json") if self.suite[name]["kind"] == "oracle" else None
        for i in range(warmup + runs):
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
        s = summarize_runs(block["runs"])
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
        for role in ("perf-1M", "perf-20M", "perf-60M"):
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
        curve = {}
        for n in SCALING_NCPU:
            if n == 8:
                s = base["summary"]["wall_s"]
            else:
                b = self.perf_block("perf-20M", ncpu=n, runs=SCALING_RUNS, warmup=0, check=False, label=f"scaling NCPU={n}")
                if not b:
                    continue
                s = b["summary"]["wall_s"]
                curve[f"_block_{n}"] = {"cpu_util": b["summary"].get("cpu_util"), "phases": {
                    k: v.get("median") for k, v in b["summary"]["phases"].items()}}
            curve[str(n)] = {"median_s": s["median"], "stdev_s": s["stdev"], "n": s["n"]}
        t1 = curve.get("1", {}).get("median_s")
        for n in SCALING_NCPU:
            c = curve.get(str(n))
            if c and t1:
                c["speedup"] = round(t1 / c["median_s"], 3)
                c["efficiency"] = round(t1 / c["median_s"] / n, 3)
        blocks = {k: curve.pop(k) for k in list(curve) if k.startswith("_block_")}
        self.r["perf"]["thread_scaling"] = {"dataset": base["dataset"], "points": curve,
                                            "per_ncpu_detail": {k[7:]: v for k, v in blocks.items()}}

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
            self.container_overhead(run, info)
        amd = build_image(self.sha, "amd64")
        imgs["amd64"] = amd
        if amd["ok"]:
            run = runner_cmd(None, amd)
            c["fixtures_amd64"] = run_fixtures(run, jobs=6, label="amd64 container (emulated)")
            c["dev_answer_amd64"] = self.container_dev(run, "amd64")
            ro_ok &= c["fixtures_amd64"]["passed"] == c["fixtures_amd64"]["total"] and c["dev_answer_amd64"]["match"]
        else:
            c["fixtures_amd64"] = {"passed": 0, "total": 36, "failed": [{"case": "*", "error": "image build failed"}]}
            ro_ok = False
        self.r["constraints"]["readonly_container_ok"] = ro_ok

    def container_dev(self, run, arch):
        out = self.runs_dir / f"dev-{arch}"
        shutil.rmtree(out, ignore_errors=True)
        t = time.perf_counter()
        p = run(DATA / "dev", out)
        wall = time.perf_counter() - t
        if p.returncode != 0:
            res = {"match": False, "error": f"exit {p.returncode}: {p.stderr.decode()[-300:]}"}
        else:
            res = check_output(out, DATA / "dev-answer", self.answer_hash("dev-answer"))
            res.pop("hash", None)
        res["wall_s"] = round(wall, 3)
        log(f"dev in {arch} container: {'MATCH' if res.get('match') else 'DIFFER'} ({wall:.2f}s)")
        shutil.rmtree(out, ignore_errors=True)
        return res

    def container_overhead(self, run, info):
        out = self.runs_dir / "ovh"
        walls = []
        log("container overhead: arm64 container on dev, 1 warm-up + 5 runs")
        for i in range(6):
            shutil.rmtree(out, ignore_errors=True)
            t = time.perf_counter()
            p = run(DATA / "dev", out)
            if p.returncode == 0 and i:
                walls.append(time.perf_counter() - t)
        shutil.rmtree(out, ignore_errors=True)
        nat = self.r["perf"]["datasets"].get("perf-1M", {}).get("summary", {}).get("wall_s", {})
        s = summarize(walls)
        ovh = {"dev_container_wall_s": s, "dev_native_median_s": nat.get("median")}
        if nat.get("median") and s.get("n"):
            ovh["dev_overhead_s"] = round(s["median"] - nat["median"], 3)
            ovh["dev_ratio"] = round(s["median"] / nat["median"], 2)
        # informational: 20M in the container (Docker Desktop's virtiofs bind mounts are much slower than the
        # scorer's, so this mostly measures the VM file-sharing layer)
        name = self.role("perf-20M")
        if name and info.get("mem_bytes", 0) >= 12 * 2**30:
            walls = []
            mem = f"{min(24, info['mem_bytes'] // 2**30 - 1)}g"
            run20 = runner_cmd(None, {**self.r["build"]["images"]["arm64"], "mem": mem})
            log(f"container overhead: arm64 container on {name} x2 (MEM={mem}; informational)")
            for i in range(2):
                shutil.rmtree(out, ignore_errors=True)
                t = time.perf_counter()
                p = run20(DATA / name, out)
                if p.returncode == 0:
                    walls.append(time.perf_counter() - t)
                else:
                    ovh["20m_error"] = p.stderr.decode()[-300:]
            shutil.rmtree(out, ignore_errors=True)
            n20 = self.r["perf"]["datasets"].get("perf-20M", {}).get("summary", {}).get("wall_s", {})
            ovh["20m_container_wall_s"] = summarize(walls)
            if walls and n20.get("median"):
                ovh["20m_ratio"] = round(min(walls) / n20["median"], 2)
        self.r["perf"]["container_overhead"] = ovh
        log(f"  dev container median {s.get('median', 0):.3f}s vs native {nat.get('median') or 0:.3f}s")

    # -------------------------------------------------------------- baseline / A-B
    def baseline(self):
        base = gates.best_baseline(self.a.version)
        if base and base.get("sha") == self.sha:
            base["note"] = "baseline is the same commit"
        self.r["baseline"] = base
        if not base or not self.prof["ab"] or base.get("sha") == self.sha:
            return
        name = self.role("perf-20M")
        if not name:
            return
        try:
            bbin = Path(build_native(base["sha"])["binary"])
        except Exception as e:  # noqa: BLE001
            self.note(f"A/B: could not build baseline {base['version']}: {e}")
            return
        self.wait_quiet()
        log(f"A/B: interleaving {AB_RUNS} runs each of {self.a.version} and {base['version']} on {name}")
        out, scratch = self.runs_dir / "out", self.runs_dir / "scratch"
        cand, bl = [], []
        for i in range(AB_RUNS):
            for b, acc in ((self.binary, cand), (bbin, bl)) if i % 2 == 0 else ((bbin, bl), (self.binary, cand)):
                r = run_once(b, DATA / name, out, scratch, 8)
                if r["returncode"] == 0:
                    acc.append(r["wall_s"])
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
        ratio = cal.get("ratio")
        s = gates.perf_20m(self.r)
        self.r["calibration"] = {"ratio_scorer_over_local": ratio, "points": len(cal.get("points", [])),
                                 "estimated_scorer_20m_s": round(s["median"] * ratio, 3) if ratio and s and s.get(
                                     "n") else None}

    def finish(self):
        r = self.r
        # every oracle dataset in the suite must have been diffed for Gate A to pass
        r["_suite_oracle_missing"] = [n for n, d in self.suite.items() if d["kind"] == "oracle"
                                      and n not in r["correctness"]["differential"]]
        r["gates"] = {"A": gates.gate_a(r), "B": gates.gate_b(r), "C": gates.gate_c(r)}
        r.pop("_suite_oracle_missing", None)
        r["verdict"] = gates.verdict(r)
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

    def main(self):
        log(f"eval {self.a.version}: rev {self.a.rev} = {self.sha[:12]}, profile {self.a.profile}")
        self.step("build", self.build)
        if not hasattr(self, "binary"):
            self.r["verdict"] = {"verdict": "REJECT", "final": True, "reasons": ["native build failed"]}
            r = self.r
            r["gates"] = {}
            write_json(EVALS / "results" / f"{r['version']}.json", r)
            sys.exit(1)
        self.step("correctness", self.correctness_small)
        self.step("fuzz", self.fuzz)
        self.perf()
        self.step("probe", self.probe)
        if self.prof["thread_scaling"]:
            self.step("thread scaling", self.thread_scaling)
        self.step("size scaling", self.size_scaling)
        self.step("baseline", self.baseline)
        if self.prof["docker"]:
            self.step("containers", self.containers)
        self.step("constraints", self.constraints)
        self.step("calibration", self.calibration)
        self.finish()


# ------------------------------------------------------------------ reports

def fmt_s(x):
    return "n/a" if x is None else f"{x:.3f}s"


def render_md(r: dict) -> str:
    c, p = r["correctness"], r["perf"]
    L = [f"# Eval: {r['version']} ({r['sha'][:12]}, profile {r['profile']})", "",
         f"**Verdict: {r['verdict']['verdict']}**" + ("" if r["verdict"]["final"] else " (provisional)"), ""]
    L += [f"- {x}" for x in r["verdict"]["reasons"]]
    L += [f"- WARNING: {x}" for x in r["verdict"].get("warnings", [])]
    L += ["", f"Run {r['started']} → {r.get('finished')}, {r.get('duration_s')} s. Host: {r['host']['machine']}, "
               f"{r['host']['ncpu']} CPUs. Evaluator {r['evaluator']['eval_sha']}.", "", "## Gates", "",
          "| Gate | Check | Status | Detail |", "| --- | --- | --- | --- |"]
    for g, gate in r["gates"].items():
        for x in gate["checks"]:
            L.append(f"| {g} | {x['name']} | {x['status'].upper()} | {x['detail']} |")
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
    if c["determinism"]:
        L += ["", "Determinism: " + ", ".join(
            f"{k} {'same hash' if v['deterministic'] else 'DIFFERENT hashes'} over {v['runs']} runs"
            f"{'' if v.get('byte_identical_files') else ' (files not byte-identical)'}" for k, v in
            c["determinism"].items())]
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
              "| Phase | Median | Share |", "| --- | --- | --- |"]
        tot = b["summary"]["wall_s"].get("median") or 1
        for k, v in ph.items():
            L.append(f"| {k} | {fmt_s(v.get('median'))} | {100 * (v.get('median') or 0) / tot:.0f}% |")
        L += ["", f"Resources (median): page reclaims {b['summary'].get('page_reclaims', {}).get('median')}, "
                  f"page faults {b['summary'].get('page_faults', {}).get('median')}, vol ctx sw "
                  f"{b['summary'].get('vcsw', {}).get('median')}, invol ctx sw {b['summary'].get('ivcsw', {}).get('median')}, "
                  f"peak footprint {b['summary'].get('peak_footprint_bytes', {}).get('max', 0) / 2**30:.2f} GiB"]
    ts = p.get("thread_scaling")
    if ts:
        L += ["", f"## Thread scaling ({ts['dataset']})", "", "| NCPU | Median | Speedup | Efficiency |",
              "| --- | --- | --- | --- |"]
        for n, v in ts["points"].items():
            L.append(f"| {n} | {fmt_s(v['median_s'])} | {v.get('speedup', '')} | {v.get('efficiency', '')} |")
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
    if r.get("calibration", {}).get("estimated_scorer_20m_s"):
        L.append(f"Estimated scorer 20M: {r['calibration']['estimated_scorer_20m_s']} s")
    if r["notes"]:
        L += ["", "## Notes", ""] + [f"- {n}" for n in r["notes"]]
    if r["errors"]:
        L += ["", "## Framework errors", ""] + [f"- {e['stage']}: {e['error']}" for e in r["errors"]]
    return "\n".join(L) + "\n"


LEDGER_HEADER = ("| Date | Version | Commit | Profile | Fixtures n/arm/amd | dev | Diff | Fuzz | Det | 1M | 20M | 60M "
                 "| Footprint 60M | Verdict |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")


def append_ledger(r: dict):
    path = EVALS / "ledger.md"
    if not path.exists():
        path.write_text("# Eval ledger\n\nOne row per eval run (newest last). Details: `results/<version>.json`.\n\n"
                        + LEDGER_HEADER)
    c, p = r["correctness"], r["perf"]["datasets"]

    def fx(k):
        return f"{c[k]['passed']}" if c.get(k) else "-"

    def med(role):
        w = p.get(role, {}).get("summary", {}).get("wall_s", {})
        return f"{w['median']:.3f}s" if w.get("n") else "-"

    diffs = c["differential"]
    nd = sum(1 for d in diffs.values() if d.get("match"))
    fz = c.get("fuzz")
    fzs = f"{fz['strict']['passed']}/{fz['strict']['total'] - fz['strict']['skipped']}" if fz else "-"
    det = c["determinism"]
    rss = p.get("perf-60M", {}).get("summary", {}).get("peak_footprint_bytes", {}).get("max")
    dev = c.get("dev_answer_native", {}).get("match")
    row = (f"| {r['started'][:16]} | {r['version']} | {r['sha'][:8]} | {r['profile']} | "
           f"{fx('fixtures_native')}/{fx('fixtures_arm64')}/{fx('fixtures_amd64')} | "
           f"{'MATCH' if dev else ('DIFFER' if dev is False else '-')} | {nd}/{len(diffs)} | {fzs} | "
           f"{'yes' if det and all(v['deterministic'] for v in det.values()) else ('NO' if det else '-')} | "
           f"{med('perf-1M')} | {med('perf-20M')} | {med('perf-60M')} | "
           f"{f'{rss / 1e9:.1f} GB' if rss else '-'} | {r['verdict']['verdict']}"
           f"{'' if r['verdict']['final'] else ' (prov.)'} |\n")
    with open(path, "a") as f:
        f.write(row)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True, help="name for this candidate, e.g. v2")
    ap.add_argument("--rev", required=True, help="git ref to build (tag, branch, sha)")
    ap.add_argument("--profile", choices=list(PROFILES), default="quick")
    ap.add_argument("--fuzz-seeds", type=int, default=None, help="override the number of fuzz seeds")
    ap.add_argument("--no-docker", action="store_true", help="skip container gates even in the full profile")
    ap.add_argument("--no-ledger", action="store_true", help="don't append to evals/ledger.md")
    ap.add_argument("--rebuild", action="store_true", help="rebuild the native binary even if cached")
    a = ap.parse_args()
    Eval(a).main()


if __name__ == "__main__":
    main()
