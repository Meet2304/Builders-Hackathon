#!/usr/bin/env python3
"""
Shopping Sessions: plain-Python reference (correctness oracle).

Follows docs/rules.md literally and favours clarity over speed. Everything is
handled as bytes, so "byte-wise" comparisons are exactly Python bytes ordering.

Reads  $DATA_DIR  (or argv[-2]), writes $OUTPUT_DIR (or argv[-1]).
"""
import json
import os
import sys
from collections import defaultdict

import pyarrow as pa
import pyarrow.parquet as pq

DAY_MS = 86_400_000
GAP_MS = 1_800_000
WEEK_MS = 7 * DAY_MS
DIGITS = b"0123456789"


# ---------------------------------------------------------------- CSV dialect
def read_rows(path, nfields):
    """Yield parsed rows (list of bytes-or-None) of one CSV file, header skipped.
    Malformed lines are dropped here."""
    with open(path, "rb") as f:
        data = f.read()
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":  # the text after the final \n is not a line
        lines.pop()
    for line in lines[1:]:  # first line is the header
        row = parse_line(line, nfields)
        if row is not None:
            yield row


def parse_line(line, nfields):
    if line == b"":
        return None  # an empty line is malformed
    fields = line.split(b",")
    if len(fields) != nfields:
        return None
    out = []
    for f in fields:
        if b'"' in f:
            if len(f) < 2 or f[0:1] != b'"' or f[-1:] != b'"' or b'"' in f[1:-1]:
                return None
            f = f[1:-1]
        out.append(f if f != b"" else None)
    return out


def csv_files(folder):
    if not os.path.isdir(folder):
        return []
    return sorted(
        os.path.join(folder, n)
        for n in os.listdir(folder)
        if n.endswith(".csv") and os.path.isfile(os.path.join(folder, n))
    )


# ---------------------------------------------------------------- timestamps
def is_digits(b):
    return len(b) > 0 and all(c in DIGITS for c in b)


def days_from_civil(y, m, d):
    y -= m <= 2
    era = y // 400
    yoe = y - era * 400
    doy = (153 * ((m + 9) % 12) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def days_in_month(y, m):
    if m == 2:
        return 29 if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0 else 28
    return 31 if m in (1, 3, 5, 7, 8, 10, 12) else 30


def parse_datetime(b):
    """b[0:19] = YYYY-MM-DDTHH:MM:SS -> epoch ms, or None."""
    if b[4:5] != b"-" or b[7:8] != b"-" or b[10:11] != b"T" or b[13:14] != b":" or b[16:17] != b":":
        return None
    parts = (b[0:4], b[5:7], b[8:10], b[11:13], b[14:16], b[17:19])
    if not all(is_digits(p) for p in parts):
        return None
    y, mo, d, h, mi, s = (int(p) for p in parts)
    if not (1 <= mo <= 12) or not (1 <= d <= days_in_month(y, mo)) or h > 23 or mi > 59 or s > 59:
        return None
    return ((days_from_civil(y, mo, d) * 24 + h) * 60 + mi) * 60_000 + s * 1000


def parse_ts(b):
    """F1 / F2 / F3 -> epoch ms (may be out of any window), or None if bad."""
    if b is None:
        return None
    if is_digits(b):  # F3: digits only, arbitrary length (Python int is unbounded)
        return int(b)
    if len(b) == 20 and b[19:20] == b"Z":  # F1
        return parse_datetime(b)
    if len(b) == 25 and b[19:20] in (b"+", b"-") and b[22:23] == b":":  # F2
        base = parse_datetime(b)
        oh, om = b[20:22], b[23:25]
        if base is None or not is_digits(oh) or not is_digits(om):
            return None
        oh, om = int(oh), int(om)
        if oh > 23 or om > 59:
            return None
        off = (oh * 60 + om) * 60_000
        return base - off if b[19:20] == b"+" else base + off
    return None


def parse_price(b):
    if b is None or not is_digits(b):
        return None
    v = int(b)
    return v if 1 <= v <= 10_000_000 else None


# ---------------------------------------------------------------- union-find
class DSU:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        p = self.parent
        if x not in p:
            p[x] = x
            return x
        root = x
        while p[root] != root:
            root = p[root]
        while p[x] != root:
            p[x], x = root, p[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if rb < ra:  # keep the byte-wise smallest ID as the root: it is the name
                ra, rb = rb, ra
            self.parent[rb] = ra


def main():
    data = os.environ.get("DATA_DIR") or sys.argv[-2]
    out = os.environ.get("OUTPUT_DIR") or sys.argv[-1]

    with open(os.path.join(data, "manifest.json")) as f:
        manifest = json.load(f)
    ws = parse_ts(manifest["window_start"].encode())
    we = parse_ts(manifest["window_end"].encode())

    products = {r[0]: r[1] for r in read_rows(os.path.join(data, "products.csv"), 2)}
    campaigns = {r[0]: r[1] for r in read_rows(os.path.join(data, "campaigns.csv"), 2)}

    # Links
    dsu = DSU()
    for path in csv_files(os.path.join(data, "links")):
        for a, b in read_rows(path, 2):
            if a is None or b is None:
                continue
            dsu.union(a, b)
    person = dsu.find  # root == smallest ID of the component (or the ID itself)

    # Events: parse, dedup (smallest ingest_ts), validate, drop late
    kept = {}  # event_id -> (ingest_ms, row)
    for path in csv_files(os.path.join(data, "events")):
        for row in read_rows(path, 7):
            eid = row[0]
            if eid is None:
                continue
            ingest = parse_ts(row[3])
            prev = kept.get(eid)
            if prev is None or ingest < prev[0]:
                kept[eid] = (ingest, row)

    by_person = defaultdict(list)  # person -> [(ts, is_purchase, price, category)]
    for ingest, (_, uid, ts_b, _, etype, pid, price_b) in kept.values():
        if uid is None or pid is None:
            continue
        ts = parse_ts(ts_b)
        if ts is None or not (ws <= ts < we):
            continue
        if etype not in (b"view", b"cart", b"purchase"):
            continue
        price = 0
        if etype == b"purchase":
            price = parse_price(price_b)
            if price is None:
                continue
        if ingest - ts > DAY_MS:
            continue
        cat = products.get(pid, b"unknown")
        by_person[person(uid)].append((ts, etype == b"purchase", price, cat))

    # Clicks: parse, dedup, validate
    seen_clicks = set()
    clicks = defaultdict(list)  # person -> [(ts, click_id, campaign)]
    for path in csv_files(os.path.join(data, "clicks")):
        for cid, uid, camp, ts_b in read_rows(path, 4):
            if cid is None or cid in seen_clicks:
                continue
            seen_clicks.add(cid)
            if uid is None or camp not in campaigns:
                continue
            ts = parse_ts(ts_b)
            if ts is None or not (ws - WEEK_MS <= ts < we):
                continue
            clicks[person(uid)].append((ts, cid, camp))

    # Sessions, attribution, aggregation
    user_daily = {}  # (person, day) -> [sessions, events, revenue, {cat: cents}]
    camp_daily = {}  # (campaign, day) -> [sessions, purchasing, revenue, assisted]

    def camp_row(c, day):
        return camp_daily.setdefault((c, day), [0, 0, 0, 0])

    for p, evs in by_person.items():
        evs.sort(key=lambda e: e[0])
        sessions = []
        prev = None
        for e in evs:
            if prev is None or e[0] - prev > GAP_MS:
                sessions.append([])
            sessions[-1].append(e)
            prev = e[0]
        pclicks = clicks.get(p, [])
        for s in sessions:
            start = s[0][0]
            day = start // DAY_MS
            n_events = len(s)
            revenue = sum(e[2] for e in s if e[1])
            purchased = any(e[1] for e in s)

            u = user_daily.setdefault((p, day), [0, 0, 0, defaultdict(int)])
            u[0] += 1
            u[1] += n_events
            u[2] += revenue
            for e in s:
                if e[1]:
                    u[3][e[3]] += e[2]

            window = [c for c in pclicks if start - WEEK_MS <= c[0] <= start]
            if window:
                best = min(window, key=lambda c: (-c[0], c[1]))
                credited = best[2]
                for camp in {c[2] for c in window}:
                    camp_row(camp, day)[3] += 1
            else:
                credited = b"organic"
            r = camp_row(credited, day)
            r[0] += 1
            r[1] += 1 if purchased else 0
            r[2] += revenue

    # Write
    def top(cats):
        if not cats:
            return None
        return min(cats.items(), key=lambda kv: (-kv[1], kv[0]))[0].decode()

    ud = sorted(user_daily.items())
    ud_table = pa.table(
        {
            "user_id": pa.array([k[0].decode() for k, _ in ud], pa.string()),
            "day": pa.array([k[1] for k, _ in ud], pa.int32()).cast(pa.date32()),
            "sessions": pa.array([v[0] for _, v in ud], pa.int64()),
            "events": pa.array([v[1] for _, v in ud], pa.int64()),
            "revenue_cents": pa.array([v[2] for _, v in ud], pa.int64()),
            "top_category": pa.array([top(v[3]) for _, v in ud], pa.string()),
        }
    )
    cd = sorted(camp_daily.items())
    cd_table = pa.table(
        {
            "campaign_id": pa.array([k[0].decode() for k, _ in cd], pa.string()),
            "channel": pa.array(
                [("organic" if k[0] == b"organic" else campaigns[k[0]].decode()) for k, _ in cd], pa.string()
            ),
            "day": pa.array([k[1] for k, _ in cd], pa.int32()).cast(pa.date32()),
            "sessions": pa.array([v[0] for _, v in cd], pa.int64()),
            "purchasing_sessions": pa.array([v[1] for _, v in cd], pa.int64()),
            "revenue_cents": pa.array([v[2] for _, v in cd], pa.int64()),
            "assisted_sessions": pa.array([v[3] for _, v in cd], pa.int64()),
        }
    )
    for name, table in (("user_daily", ud_table), ("campaign_daily", cd_table)):
        os.makedirs(os.path.join(out, name), exist_ok=True)
        pq.write_table(table, os.path.join(out, name, "part-0.parquet"))
    print(f"reference: {len(ud)} user_daily rows, {len(cd)} campaign_daily rows", file=sys.stderr)


if __name__ == "__main__":
    main()
