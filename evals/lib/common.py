"""Shared helpers for the eval framework: paths, logging, table loading,
canonical hashing and exact diffs. Independent of the candidate's own scripts,
so a candidate can never change how it is judged."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import polars as pl

EVALS = Path(__file__).resolve().parents[1]
REPO = EVALS.parent  # the eval worktree (fixtures, reference, scripts come from here)
ROOT = Path(os.environ.get(
    "SESSIONS_ROOT",
    "/Users/meet/Meet/Projects_Ad Astra/Project_3_Builders Hackathon/Builders-Hackathon"))
DATA = Path(os.environ.get("SESSIONS_DATA", ROOT / "data"))
EXPECTED = DATA / "expected"           # cached reference outputs, one dir per dataset
CONSISTENCY = DATA / "consistency"     # cached outputs of the best verified version (no oracle)
FUZZ_DATA = DATA / "fuzz"              # generated adversarial cases + their reference outputs
STATS = DATA / "stats"                 # cached dataset stats (bytes, lines)
# ".noindex": Spotlight must not index the run outputs (it competed for CPU during timed runs)
WORK = Path(os.environ.get("EVAL_WORK", Path.home() / ".cache" / "sessions-eval.noindex"))
PY = str(REPO / ".venv" / "bin" / "python") if (REPO / ".venv").exists() else sys.executable
REFERENCE = REPO / "reference" / "reference.py"
FIXTURES = REPO / "fixtures"
RUST_PATH = "/opt/homebrew/opt/rustup/bin"

SCHEMAS = {
    "user_daily": {"user_id": pl.String, "day": pl.Date, "sessions": pl.Int64, "events": pl.Int64,
                   "revenue_cents": pl.Int64, "top_category": pl.String},
    "campaign_daily": {"campaign_id": pl.String, "channel": pl.String, "day": pl.Date, "sessions": pl.Int64,
                       "purchasing_sessions": pl.Int64, "revenue_cents": pl.Int64,
                       "assisted_sessions": pl.Int64},
}
KEYS = {"user_daily": ["user_id", "day"], "campaign_daily": ["campaign_id", "day"]}

_T0 = time.time()


def log(msg: str) -> None:
    """Console progress log (stderr, timestamped from process start)."""
    print(f"[eval {time.time() - _T0:7.1f}s] {msg}", file=sys.stderr, flush=True)


def sh(cmd, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def write_json(path: Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n")
    tmp.replace(path)


# ------------------------------------------------------------------ datasets

def dataset_files(ds: Path):
    """Every input file of a dataset, relative path -> size."""
    out = {}
    for p in sorted(ds.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(ds))] = p.stat().st_size
    return out


def dataset_fingerprint(ds: Path) -> str:
    """Cheap identity of a dataset: manifest + names and sizes of all files."""
    h = hashlib.sha256()
    h.update((ds / "manifest.json").read_bytes())
    for name, size in dataset_files(ds).items():
        h.update(f"{name}\0{size}\n".encode())
    return h.hexdigest()[:16]


def dataset_stats(ds: Path) -> dict:
    """Input bytes and data-line counts per table (cached under data/stats/)."""
    ds = Path(ds)
    fp = dataset_fingerprint(ds)
    cache = STATS / f"{ds.name}.json"
    got = read_json(cache)
    if got and got.get("fingerprint") == fp:
        return got
    stats = {"fingerprint": fp, "bytes": 0, "files": 0}
    for table in ("events", "clicks", "links"):
        lines = files = nbytes = 0
        for p in sorted((ds / table).glob("*.csv")):
            files += 1
            nbytes += p.stat().st_size
            n = 0
            with open(p, "rb") as f:
                for block in iter(lambda: f.read(1 << 24), b""):
                    n += block.count(b"\n")
            lines += max(n - 1, 0)  # minus the header
        stats[f"{table}_lines"] = lines
        stats[f"{table}_files"] = files
        stats[f"{table}_bytes"] = nbytes
        stats["bytes"] += nbytes
        stats["files"] += files
    for small in ("products.csv", "campaigns.csv", "manifest.json"):
        if (ds / small).is_file():
            stats["bytes"] += (ds / small).stat().st_size
            stats["files"] += 1
    stats["manifest"] = read_json(ds / "manifest.json")
    write_json(cache, stats)
    return stats


# ------------------------------------------------------------------ tables

def _load_csv(path: Path, schema) -> pl.DataFrame:
    df = pl.read_csv(path, schema_overrides={k: (pl.String if v == pl.Date else v) for k, v in schema.items()})
    if df.height == 0:
        return pl.DataFrame(schema=schema)
    return df.with_columns(pl.col("day").str.to_date()).select(list(schema)).cast(schema)


def _load_parquet_dir(folder: Path, schema) -> pl.DataFrame:
    """Load one output table the way the scorer reads it (rules.md: Outputs).
    Raises ValueError on any schema violation."""
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError(f"expected an output directory: {folder}")
    frames = []
    for path in sorted(folder.glob("*.parquet")):
        if path.name.startswith((".", "_")) or path.is_symlink() or not path.is_file():
            continue
        frame = pl.read_parquet(path)
        if set(frame.columns) != set(schema) or len(frame.columns) != len(schema):
            raise ValueError(f"{path.name}: expected columns {list(schema)}, got {frame.columns}")
        for column, expected in schema.items():
            actual = frame.schema[column]
            if expected == pl.Int64 and actual.is_integer():
                continue
            if expected == pl.String and actual.base_type() in (pl.String, pl.Categorical, pl.Enum):
                continue
            if actual != expected:
                raise ValueError(f"{path.name}: {column} has type {actual}, expected {expected}")
        frames.append(frame.select(list(schema)).cast(schema))
    if not frames:
        raise ValueError(f"no parquet in {folder}")
    return pl.concat(frames)


def load_table(folder: Path, table: str) -> pl.DataFrame:
    """A table from an output dir (parquet folder) or an answer dir (table.csv)."""
    folder = Path(folder)
    schema = SCHEMAS[table]
    if (folder / f"{table}.csv").is_file():
        return _load_csv(folder / f"{table}.csv", schema)
    return _load_parquet_dir(folder / table, schema)


def canonical(df: pl.DataFrame, table: str) -> pl.DataFrame:
    cols = list(SCHEMAS[table])
    return df.select(cols).sort(cols, nulls_last=True)


def canonical_hash(out_dir: Path) -> dict:
    """sha256 of each table after sorting all rows by all columns (order- and
    file-layout-insensitive). Returns {"hash", "rows": {table: n}} or {"error"}."""
    h = hashlib.sha256()
    rows = {}
    try:
        for table in SCHEMAS:
            df = canonical(load_table(out_dir, table), table)
            rows[table] = df.height
            h.update(table.encode() + b"\0")
            h.update(df.write_csv().encode())
    except Exception as e:  # noqa: BLE001 - any load failure is a correctness failure
        return {"hash": None, "rows": rows, "error": f"{type(e).__name__}: {e}"[:500]}
    return {"hash": h.hexdigest(), "rows": rows}


def diff_outputs(a_dir: Path, b_dir: Path, show: int = 5) -> dict:
    """Exact, order-insensitive diff (same semantics as scripts/compare.py)."""
    result = {"match": True, "tables": {}}
    for table, schema in SCHEMAS.items():
        try:
            a = load_table(a_dir, table)
            b = load_table(b_dir, table)
        except Exception as e:  # noqa: BLE001
            result["match"] = False
            result["tables"][table] = {"error": f"{type(e).__name__}: {e}"[:500]}
            continue
        keys = KEYS[table]
        only_a = a.join(b, on=list(schema), how="anti", nulls_equal=True)
        only_b = b.join(a, on=list(schema), how="anti", nulls_equal=True)
        t = {"rows_a": a.height, "rows_b": b.height, "only_a": only_a.height, "only_b": only_b.height,
             "dup_keys_a": a.height - a.n_unique(subset=keys), "dup_keys_b": b.height - b.n_unique(subset=keys)}
        # multiset check: same distinct rows but different multiplicities
        if not (only_a.height or only_b.height) and a.height != b.height:
            t["multiplicity_mismatch"] = True
        if only_a.height or only_b.height or t["dup_keys_a"] or t["dup_keys_b"] or a.height != b.height:
            result["match"] = False
            t["sample_only_a"] = [list(map(str, r)) for r in only_a.sort(keys).head(show).rows()]
            t["sample_only_b"] = [list(map(str, r)) for r in only_b.sort(keys).head(show).rows()]
        result["tables"][table] = t
    return result


def invariants(out_dir: Path) -> dict:
    """The rules' self-check: sessions and revenue sums equal across tables,
    summed assisted >= credited non-organic sessions; plus key uniqueness and
    value sanity."""
    try:
        ud = load_table(out_dir, "user_daily")
        cd = load_table(out_dir, "campaign_daily")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:500]}
    s_ud, s_cd = int(ud["sessions"].sum() or 0), int(cd["sessions"].sum() or 0)
    r_ud, r_cd = int(ud["revenue_cents"].sum() or 0), int(cd["revenue_cents"].sum() or 0)
    assisted = int(cd["assisted_sessions"].sum() or 0)
    credited_nonorg = int(cd.filter(pl.col("campaign_id") != "organic")["sessions"].sum() or 0)
    checks = {
        "sessions_equal": s_ud == s_cd,
        "revenue_equal": r_ud == r_cd,
        "assisted_ge_credited_nonorganic": assisted >= credited_nonorg,
        "user_daily_keys_unique": ud.height == ud.n_unique(subset=KEYS["user_daily"]),
        "campaign_daily_keys_unique": cd.height == cd.n_unique(subset=KEYS["campaign_daily"]),
        "sessions_positive": bool((ud["sessions"] >= 1).all()) if ud.height else True,
        "events_ge_sessions": bool((ud["events"] >= ud["sessions"]).all()) if ud.height else True,
        "purchasing_le_sessions": bool((cd["purchasing_sessions"] <= cd["sessions"]).all()) if cd.height else True,
        "organic_channel": bool((cd.filter(pl.col("campaign_id") == "organic")["channel"] == "organic").all()),
        "organic_never_assists": int(cd.filter(pl.col("campaign_id") == "organic")["assisted_sessions"].sum() or 0) == 0,
        "top_category_null_iff_no_revenue": bool(((ud["revenue_cents"] == 0) == ud["top_category"].is_null()).all())
        if ud.height else True,
    }
    return {"ok": all(checks.values()), "checks": checks,
            "sums": {"sessions": s_ud, "revenue_cents": r_ud, "assisted": assisted,
                     "credited_non_organic": credited_nonorg}}


def run_reference(ds: Path, out: Path, timeout: int | None = None) -> dict:
    """Run the Python oracle (single-threaded) and time it."""
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, DATA_DIR=str(ds), OUTPUT_DIR=str(out))
    t = time.time()
    p = subprocess.run(["/usr/bin/time", "-l", PY, str(REFERENCE)], env=env, capture_output=True, text=True,
                       timeout=timeout)
    wall = time.time() - t
    rss = None
    for line in p.stderr.splitlines():
        if "maximum resident set size" in line:
            rss = int(line.split()[0])
    return {"returncode": p.returncode, "wall_s": round(wall, 3), "max_rss_bytes": rss,
            "stderr_tail": p.stderr[-1500:] if p.returncode else ""}


def reference_sha() -> str:
    return sha256_file(REFERENCE)[:16]
