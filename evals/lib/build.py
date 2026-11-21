"""Isolated builds of a candidate git ref.

Source: `git archive <sha> | tar -x` into $EVAL_WORK/src/<sha12>/ (never touches
any worktree). Native binary: cargo with one shared CARGO_TARGET_DIR
($EVAL_WORK/target) so dependency artifacts are reused across revs; the result
is copied to $EVAL_WORK/bin/<sha12>/sessions. A file lock serialises builds.
Images: tagged sessions-eval:<sha12>-<arch>, never shopping-sessions:*."""
from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from .common import REPO, RUST_PATH, WORK, log


def resolve(rev: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", f"{rev}^{{commit}}"], check=True,
                          capture_output=True, text=True).stdout.strip()


@contextmanager
def locked(name: str):
    WORK.mkdir(parents=True, exist_ok=True)
    with open(WORK / f"{name}.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def source_tree(sha: str) -> Path:
    dest = WORK / "src" / sha[:12]
    if (dest / ".complete").exists():
        return dest
    with locked("src"):
        if (dest / ".complete").exists():
            return dest
        tmp = dest.with_name(dest.name + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        archive = subprocess.Popen(["git", "-C", str(REPO), "archive", sha], stdout=subprocess.PIPE)
        subprocess.run(["tar", "-x", "-C", str(tmp)], stdin=archive.stdout, check=True)
        if archive.wait() != 0:
            raise RuntimeError(f"git archive {sha} failed")
        (tmp / ".complete").write_text(sha + "\n")
        shutil.rmtree(dest, ignore_errors=True)
        tmp.rename(dest)
    return dest


def repo_size(sha: str) -> dict:
    """Size of the tracked tree at sha (what a clone checks out) and a data/ check."""
    files = subprocess.run(["git", "-C", str(REPO), "ls-tree", "-r", "-l", sha], check=True, capture_output=True,
                           text=True).stdout.splitlines()
    total, biggest, data_files = 0, [], []
    for line in files:
        meta, path = line.split("\t", 1)
        size = meta.split()[3]
        size = int(size) if size.isdigit() else 0
        total += size
        biggest.append((size, path))
        if path.startswith("data/"):
            data_files.append(path)
    biggest.sort(reverse=True)
    return {"tracked_bytes": total, "tracked_files": len(files), "data_files": data_files[:20],
            "largest": [{"path": p, "bytes": s} for s, p in biggest[:5]]}


def rust_env() -> dict:
    env = dict(os.environ)
    env["PATH"] = RUST_PATH + ":" + env.get("PATH", "")
    env["CARGO_TARGET_DIR"] = str(WORK / "target")
    return env


def build_native(sha: str, rebuild: bool = False) -> dict:
    src = source_tree(sha)
    out = WORK / "bin" / sha[:12] / "sessions"
    meta_path = out.with_name("build.json")
    if out.exists() and meta_path.exists() and not rebuild:
        import json
        meta = json.loads(meta_path.read_text())
        meta["cached"] = True
        return meta
    env = rust_env()
    with locked("cargo"):
        log(f"build: cargo build --release --locked for {sha[:12]} (shared target dir)")
        t = time.time()
        p = subprocess.run(["cargo", "build", "--release", "--locked"], cwd=src, env=env, capture_output=True,
                           text=True)
        dt = time.time() - t
        if p.returncode != 0:
            raise RuntimeError(f"cargo build failed for {sha[:12]}:\n{p.stderr[-4000:]}")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(env["CARGO_TARGET_DIR"]) / "release" / "sessions", out)
    rustc = subprocess.run(["rustc", "--version"], env=env, capture_output=True, text=True).stdout.strip()
    meta = {"binary": str(out), "build_s": round(dt, 2), "binary_bytes": out.stat().st_size, "rustc": rustc,
            "rustflags": env.get("RUSTFLAGS", ""), "cached": False, "src": str(src)}
    import json
    meta_path.write_text(json.dumps(meta, indent=2))
    log(f"build: done in {dt:.1f}s, binary {meta['binary_bytes'] / 1e6:.2f} MB")
    return meta


def image_tag(sha: str, arch: str) -> str:
    return f"sessions-eval:{sha[:12]}-{arch}"


def build_image(sha: str, arch: str, no_cache: bool = False, x86_cpu: str = "x86-64-v2") -> dict:
    """docker buildx build of the candidate's own Dockerfile. arch: arm64 | amd64."""
    src = source_tree(sha)
    tag = image_tag(sha, arch)
    cmd = ["docker", "buildx", "build", "--platform", f"linux/{arch}", "--build-arg", f"X86_CPU={x86_cpu}",
           "--load", "-t", tag, str(src)]
    if no_cache:
        cmd.insert(3, "--no-cache")
    log(f"docker: building {tag}{' (clean, --no-cache)' if no_cache else ''}")
    t = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.time() - t
    res = {"tag": tag, "platform": f"linux/{arch}", "no_cache": no_cache, "build_s": round(dt, 1),
           "ok": p.returncode == 0, "x86_cpu": x86_cpu if arch == "amd64" else None}
    if p.returncode != 0:
        res["stderr_tail"] = p.stderr[-3000:]
        log(f"docker: build FAILED for {tag}")
        return res
    insp = subprocess.run(["docker", "image", "inspect", tag, "--format", "{{.Size}}"], capture_output=True,
                          text=True)
    res["image_bytes"] = int(insp.stdout.strip() or 0)
    log(f"docker: {tag} built in {dt:.1f}s, {res['image_bytes'] / 1e6:.0f} MB")
    return res


def docker_info() -> dict:
    p = subprocess.run(["docker", "info", "--format", "{{.NCPU}} {{.MemTotal}} {{.ServerVersion}}"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        return {"available": False}
    ncpu, mem, ver = p.stdout.split()
    return {"available": True, "ncpu": int(ncpu), "mem_bytes": int(mem), "server_version": ver}
