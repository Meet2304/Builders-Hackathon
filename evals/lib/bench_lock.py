"""Machine-wide benchmark lock shared with Explorer's mkdir protocol."""
from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from contextlib import contextmanager, suppress
from pathlib import Path

from .common import REPO, log

LOCK_PATH = Path("/tmp/builders-bench.lock")
RETRY_S = 60
_active_lock = None


def branch_name() -> str:
    p = subprocess.run(["git", "-C", str(REPO), "symbolic-ref", "--quiet", "--short", "HEAD"],
                       capture_output=True, text=True)
    return p.stdout.strip() or "(detached)"


def _owner_or_reap(path: Path) -> tuple[str, bool]:
    """Return the owner description and whether the directory just disappeared."""
    try:
        directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return "", True
    try:
        try:
            owner_fd = os.open("owner", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        except FileNotFoundError:
            # Explorer can hold a lock without metadata. An empty directory may also be mid-acquire.
            return "owner unknown", False
        try:
            owner = os.read(owner_fd, 4096).decode(errors="replace").strip()
        finally:
            os.close(owner_fd)
        match = re.search(r"(?im)^\s*(?:pid\s*[:=]?\s*)?(\d+)\b", owner)
        pid = int(match.group(1)) if match else 0
        if 0 < pid <= 2**31 - 1:
            try:
                os.kill(pid, 0)
            except PermissionError:
                pass  # A process owned by another user is still alive.
            except ProcessLookupError:
                try:
                    # Only the reaper that unlinks this stale inode may remove the directory.
                    os.unlink("owner", dir_fd=directory)
                except FileNotFoundError:
                    return "another waiter is recovering a stale lock", False
                try:
                    path.rmdir()
                except FileNotFoundError:
                    pass
                log(f"benchmark lock: removed stale owner pid={pid}")
                return "", True
        return owner.replace("\n", " ") or "owner unknown", False
    finally:
        os.close(directory)


@contextmanager
def benchmark_lock(branch: str | None = None, *, path: Path = LOCK_PATH, retry_s: float = RETRY_S):
    global _active_lock
    if _active_lock == path:
        yield  # The standalone Linux probe also runs inside a timed profile.
        return

    branch = branch or branch_name()
    pid = os.getpid()
    held = critical = False
    interrupted = 0

    def stop(signum, _frame):
        nonlocal interrupted
        if interrupted:
            return
        interrupted = signum
        if not critical:
            raise SystemExit(128 + signum)

    handlers = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        while not held:
            # Defer signal exit across mkdir and owner publication so cleanup always knows it owns the lock.
            critical = True
            try:
                try:
                    path.mkdir()
                except FileExistsError:
                    owner, retry_now = _owner_or_reap(path)
                else:
                    held = True
                    _active_lock = path
                    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                    (path / "owner").write_text(f"pid={pid}\nbranch={branch}\nstarted={started}\n")
            finally:
                critical = False
            if interrupted:
                raise SystemExit(128 + interrupted)
            if not held and not retry_now:
                log(f"benchmark lock: pid={pid} branch={branch} waiting for {owner}; retry in {retry_s:g}s")
                time.sleep(retry_s)
        log(f"benchmark lock: acquired by pid={pid} branch={branch}")
        yield
    finally:
        critical = True
        try:
            if held:
                _active_lock = None
                with suppress(FileNotFoundError):
                    (path / "owner").unlink(missing_ok=True)
                    path.rmdir()
                log(f"benchmark lock: released by pid={pid} branch={branch}")
        finally:
            for signum, handler in handlers.items():
                signal.signal(signum, handler)
        if interrupted:
            raise SystemExit(128 + interrupted)
