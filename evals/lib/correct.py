"""Correctness checks: fixtures, exact diffs against cached oracle outputs, and the fuzz suite."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .common import (EVALS, FIXTURES, FUZZ_DATA, REPO, SCHEMAS, WORK, canonical, canonical_hash, diff_outputs,
                     load_table, log, read_json, reference_sha, run_reference, sha256_file, write_json)

DOCKER_RUN = REPO / "scripts" / "docker_run.sh"
WINDOWS_SEED0 = 100_000  # seeds from here get the "windows" focus (must match evals/fuzz/gen.py)
DEBUG_CASES = (
    ("SESSIONS_DEBUG_HASH_BITS", "4"),
    ("SESSIONS_DEBUG_CHUNK", "97"),
    ("SESSIONS_DEBUG_PARTS", "1"),
    ("SESSIONS_DEBUG_PARTS", "4096"),
    ("SESSIONS_DEBUG_NO_FAST", "1"),
)
EXTRA_DEBUG_CASES = (
    ("SESSIONS_DEBUG_HASH_BITS", "0"),
    ("SESSIONS_DEBUG_PARTS", "3"),
    ("SESSIONS_DEBUG_PARTS", "255"),
    ("SESSIONS_DEBUG_CHUNK", "1"),
    ("SESSIONS_DEBUG_CHUNK", "4096"),
)
DIALECT_ONLY = set(EXTRA_DEBUG_CASES[-2:])
INVALID_DEBUG_CASES = (
    ("SESSIONS_DEBUG_HASH_BITS", "bad"),
    ("SESSIONS_DEBUG_CHUNK", "bad"),
    ("SESSIONS_DEBUG_PARTS", "bad"),
    ("SESSIONS_DEBUG_PARTS", "0"),
    ("SESSIONS_DEBUG_PARTS", "4097"),
)


def docker_run_with_env(extra_env: dict) -> str:
    """scripts/docker_run.sh with `-e K=V` added to the candidate's docker run (flags stay the canonical ones)."""
    text = DOCKER_RUN.read_text()
    anchor = '  "$IMAGE"\n'
    if text.count(anchor) != 1 or not text.endswith(anchor):
        raise RuntimeError("scripts/docker_run.sh changed shape: cannot add debug env to the container run")
    for k, v in extra_env.items():
        if not k.replace("_", "").isalnum() or not str(v).replace("-", "").isalnum():
            raise ValueError(f"unsafe container env {k}={v}")
    flags = "".join(f"  -e {k}={v} \\\n" for k, v in extra_env.items())
    return text[: -len(anchor)] + flags + anchor


def runner_cmd(binary: Path | None, image: dict | None):
    """A callable (data, out, ncpu) -> CompletedProcess for a native binary or a container image."""
    def native(data: Path, out: Path, ncpu: int = 8, timeout: float = 120, extra_env: dict | None = None):
        with tempfile.TemporaryDirectory(dir=WORK / "tmp") as scratch:
            env = dict(os.environ, DATA_DIR=str(data), OUTPUT_DIR=str(out), SCRATCH_DIR=scratch, NCPU=str(ncpu),
                       MEM_GB="24")
            env = {k: v for k, v in env.items() if not k.startswith("SESSIONS_DEBUG_")}
            env.update(extra_env or {})
            return subprocess.run([str(binary)], env=env, capture_output=True, timeout=timeout)

    def container(data: Path, out: Path, ncpu: int = 8, timeout: float = 600, extra_env: dict | None = None):
        env = dict(os.environ, IMAGE=image["tag"], PLATFORM=image["platform"], CPUS=str(ncpu),
                   MEM=image.get("mem", "24g"))
        script = str(DOCKER_RUN)
        with tempfile.TemporaryDirectory(dir=WORK / "tmp") as tmp:
            if extra_env:
                script = str(Path(tmp) / "docker_run_env.sh")
                Path(script).write_text(docker_run_with_env(extra_env))
            return subprocess.run(["sh", script, str(data), str(out)], env=env, capture_output=True,
                                  timeout=timeout)

    (WORK / "tmp").mkdir(parents=True, exist_ok=True)
    return native if binary is not None else container


def _rows(df, table):
    return canonical(df, table).rows()


def run_fixtures(run, jobs: int = 8, label: str = "native") -> dict:
    cases = sorted(d.name for d in FIXTURES.iterdir() if (d / "expected").is_dir())
    log(f"fixtures ({label}): {len(cases)} cases, {jobs} parallel")

    def one(case: str):
        data = FIXTURES / case / "input"
        if not data.is_dir():
            data = FIXTURES / case / "data"
        with tempfile.TemporaryDirectory(dir=WORK / "tmp") as out:
            out = Path(out)
            try:
                p = run(data, out)
            except subprocess.TimeoutExpired:
                return case, "timeout"
            if p.returncode != 0:
                return case, f"exit {p.returncode}: {p.stderr.decode('utf-8', 'replace')[-300:]}"
            if p.stdout:
                return case, f"wrote {len(p.stdout)} bytes to stdout"
            for table in SCHEMAS:
                try:
                    exp = _rows(load_table(FIXTURES / case / "expected", table), table)
                    act = _rows(load_table(out, table), table)
                except Exception as e:  # noqa: BLE001
                    return case, f"{table}: {type(e).__name__}: {str(e)[:200]}"
                if exp != act:
                    return case, f"{table}: rows differ (expected {len(exp)}, got {len(act)})"
        return case, None

    with ThreadPoolExecutor(jobs) as pool:
        results = list(pool.map(one, cases))
    failed = [{"case": c, "error": e} for c, e in results if e]
    for f in failed:
        log(f"  FAIL {f['case']}: {f['error']}")
    log(f"fixtures ({label}): {len(cases) - len(failed)}/{len(cases)}")
    return {"passed": len(cases) - len(failed), "total": len(cases), "failed": failed}


def check_output(out: Path, expected_dir: Path, expected_hash: str | None) -> dict:
    """Exact comparison: fast path by canonical hash, full diff only on mismatch."""
    got = canonical_hash(out)
    res = {"hash": got["hash"], "rows": got["rows"]}
    if got.get("error"):
        res.update(match=False, error=got["error"])
        return res
    if expected_hash and got["hash"] == expected_hash:
        res["match"] = True
        return res
    d = diff_outputs(out, expected_dir)
    res["match"] = d["match"]
    res["diff"] = d
    return res


# ------------------------------------------------------------------ fuzz

def fuzz_gen_sha() -> str:
    return sha256_file(EVALS / "fuzz" / "gen.py")[:12]


def fuzz_dir() -> Path:
    return FUZZ_DATA / f"gen-{fuzz_gen_sha()}-ref-{reference_sha()[:8]}"


def ensure_fuzz_cases(seeds: range, jobs: int = 10) -> Path:
    """Generate each seed's case and cache the reference's output for it (once per generator/reference hash)."""
    base = fuzz_dir()
    todo = [s for s in seeds if not (base / str(s) / "case.json").exists()]
    if not todo:
        return base
    log(f"fuzz: generating {len(todo)} new cases + reference outputs into {base} ({jobs} parallel)")
    sys.path.insert(0, str(EVALS / "fuzz"))
    import gen  # noqa: E402

    def one(seed: int):
        d = base / str(seed)
        tmp = base / f".{seed}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        meta = gen.generate(seed, tmp / "input")
        run = run_reference(tmp / "input", tmp / "expected", timeout=300)
        if run["returncode"] != 0:
            meta["reference_error"] = run["stderr_tail"]
            meta["expected_hash"] = None
        else:
            meta["expected_hash"] = canonical_hash(tmp / "expected")["hash"]
        meta["reference_s"] = run["wall_s"]
        write_json(tmp / "case.json", meta)
        shutil.rmtree(d, ignore_errors=True)
        tmp.rename(d)

    done = 0
    with ThreadPoolExecutor(jobs) as pool:
        for _ in pool.map(one, todo):
            done += 1
            if done % 100 == 0:
                log(f"fuzz: {done}/{len(todo)} cases generated")
    return base


def run_fuzz(run, seeds: range, jobs: int = 8, *, record_hashes: dict | None = None,
             default_hashes: dict | None = None, focus: str | None = None) -> dict:
    base = ensure_fuzz_cases(seeds)
    selected = seeds if focus is None else [seed for seed in seeds
                                           if read_json(base / str(seed) / "case.json")["focus"] == focus]
    log(f"fuzz: running candidate on {len(selected)} cases (NCPU cycles 1,2,4,8)")

    def one(seed: int):
        d = base / str(seed)
        meta = read_json(d / "case.json")
        if meta.get("expected_hash") is None:
            return seed, meta, {"skipped": "reference failed: " + meta.get("reference_error", "")[-200:]}
        with tempfile.TemporaryDirectory(dir=WORK / "tmp") as out:
            out = Path(out)
            try:
                p = run(d / "input", out, ncpu=[1, 2, 4, 8][seed % 4], timeout=60)
            except subprocess.TimeoutExpired:
                return seed, meta, {"match": False, "error": "timeout"}
            if p.returncode != 0:
                return seed, meta, {"match": False,
                                    "error": f"exit {p.returncode}: {p.stderr.decode('utf-8', 'replace')[-300:]}"}
            res = check_output(out, d / "expected", meta["expected_hash"])
            if default_hashes is not None and res["match"] and default_hashes.get(seed) != res["hash"]:
                res.update(match=False, error="canonical hash differs from default run")
            if p.stdout:
                res["match"] = False
                res["error"] = f"stdout {len(p.stdout)} bytes"
            return seed, meta, res

    with ThreadPoolExecutor(jobs) as pool:
        results = list(pool.map(one, selected))
    summary = {"gen_sha": fuzz_gen_sha(), "cases_dir": str(base), "seeds": [seeds.start, seeds.stop],
               "focus": focus,
               "strict": {"total": 0, "passed": 0, "skipped": 0, "failed": []},
               "robust": {"total": 0, "passed": 0, "skipped": 0, "failed": []},
               "by_focus": {}, "failing_tags": {}}
    for seed, meta, res in results:
        group = summary["strict" if meta["strict"] else "robust"]
        group["total"] += 1
        f = summary["by_focus"].setdefault(meta["focus"], {"total": 0, "failed": 0})
        f["total"] += 1
        if res.get("skipped"):
            group["skipped"] += 1
            continue
        if res.get("match"):
            group["passed"] += 1
            if record_hashes is not None:
                record_hashes[seed] = res["hash"]
            continue
        f["failed"] += 1
        for t in meta["tags"]:
            summary["failing_tags"][t] = summary["failing_tags"].get(t, 0) + 1
        entry = {"seed": seed, "focus": meta["focus"], "tags": meta["tags"],
                 "robust_reasons": meta.get("robust_reasons", []), "error": res.get("error"),
                 "repro": f".venv/bin/python evals/fuzz/gen.py --seed {seed} --out /tmp/fz{seed}"}
        if "diff" in res:
            entry["diff"] = {t: {k: v for k, v in x.items() if k in ("rows_a", "rows_b", "only_a", "only_b",
                                                                       "sample_only_a", "sample_only_b", "error")}
                             for t, x in res["diff"]["tables"].items()}
        group["failed"].append(entry)
    for g in ("strict", "robust"):
        s = summary[g]
        log(f"fuzz {g}: {s['passed']}/{s['total'] - s['skipped']} MATCH"
            + (f", {s['skipped']} skipped" if s["skipped"] else "")
            + (f"; failing seeds {[x['seed'] for x in s['failed']][:15]}" if s["failed"] else ""))
    return summary
