#!/usr/bin/env python3
"""Timestamp-decoder cases for v3 @ 29b64bf (the window-local table decoder).

    .venv/bin/python evals/insights/v3_review/cases_ts.py OUT_DIR   # writes OUT_DIR/<case>/...

The decoder answers F1/F2 dates within window +-8 days from a table, and 13-digit F3
values with SWAR; everything else goes to v1's parse_ts. These cases pin every decoded
value to the millisecond, so an off-by-anything shows as a different output row:

* Event probes: the probe event sits between two anchors at t-30:00 and t+30:00, where t
  is the oracle's value. Anchors are 16-digit F3 (leading zeros), which skip the decoder.
  The three make one session only if the probe decodes to exactly t; a reject gives two
  sessions of one event, and any other value gives a split.
* Click probes: each probe has its own campaign, and its person has sessions starting at
  t and at t + 7 days. The click credits the first only if it decodes to <= t and the
  second only if it decodes to >= t.
* Ingest probes: late at exactly 24 h vs 24 h + 1 s, ingest dates off the table
  (before window - 8 days and after window + 8 days), and dedup order between a table
  ingest and a fallback ingest.

Probe strings: every day from window - 12 days to window + 12 days, several clocks, F1,
F2 with offsets that change the date, F3 of 12, 13 and 16 digits; then byte mutations of
a sample of them at every position. All within docs/rules.md except that probes may be
bad timestamps, which the rules expect.
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "reference"))
import cases as base  # noqa: E402
from reference import parse_ts as oracle_ts  # noqa: E402

DAY, MIN, SEC, WEEK, GAP = 86_400_000, 60_000, 1000, 7 * 86_400_000, 1_800_000
UTC = timezone.utc
MUT = list("0123456789:;/-+TtZz .") + ["\x00", "\udcff", "\x7f"]


def f3(ms: int) -> str:
    return f"{ms:016d}"


def utc(y, m, d, hh=0, mm=0, ss=0) -> int:
    return int(datetime(y, m, d, hh, mm, ss, tzinfo=UTC).timestamp() * 1000)


class TsCase(base.Case):
    def __init__(self, name, w0, w1):
        super().__init__(name)
        self.w0, self.w1 = w0, w1
        self.campaigns = []

    def write(self, root: Path):
        old = base.W0, base.W1
        base.W0, base.W1 = self.w0, self.w1
        try:
            super().write(root)
        finally:
            base.W0, base.W1 = old


def manifest_f1(ms: int) -> str:
    return base.f1(ms)


def probe_strings(w0: int, w1: int, rng: random.Random) -> list[str]:
    out: list[str] = []
    d0 = datetime.fromtimestamp(w0 / 1000, UTC).date() - timedelta(days=12)
    d1 = datetime.fromtimestamp(w1 / 1000, UTC).date() + timedelta(days=12)
    clocks = ["00:00:00", "00:29:59", "12:34:56", "23:59:59", "24:00:00", "12:60:00", "12:00:60", "09:5:300"]
    offs = ["Z", "+00:00", "-00:00", "+05:30", "-10:00", "+12:00", "+23:59", "-23:59", "+24:00", "+05:60", "+0530"]
    d = d0
    while d <= d1:
        for c in clocks:
            for o in offs:
                out.append(f"{d.isoformat()}T{c}{o}")
        dt = datetime(d.year, d.month, d.day, tzinfo=UTC)
        ms = int(dt.timestamp() * 1000) + rng.randrange(DAY)
        out += [str(ms), f"{ms:016d}", f"{ms:014d}", str(ms // 10), str(ms)[:-1] + "x"]
        d += timedelta(days=1)
    # impossible calendar values next to real ones, in the table's index space
    out += ["2028-02-29T10:00:00Z", "2027-02-29T10:00:00Z", "2028-02-30T10:00:00Z", "2026-09-31T10:00:00Z",
            "2026-10-00T10:00:00Z", "2026-10-32T10:00:00Z", "2026-10-3:T10:00:00Z", "2026-10-0:T10:00:00Z",
            "2026-1:-01T10:00:00Z", "2026-13-01T10:00:00Z", "2026-00-01T10:00:00Z",
            "0000000000000", "9999999999999", "00000000000000000000000000", "99999999999999999999"]
    seeds = rng.sample(out, 60)
    for s in seeds:
        for i in range(len(s)):
            for ch in rng.sample(MUT, 8):
                out.append(s[:i] + ch + s[i + 1:])
    return list(dict.fromkeys(out))


def oracle(s: str):
    return oracle_ts(s.encode("utf-8", "surrogateescape"))


def build(name: str, w0: int, w1: int, seed: int) -> TsCase:
    k = TsCase(name, w0, w1)
    rng = random.Random(seed)
    probes = probe_strings(w0, w1, rng)
    k.products = [("p1", "books")]
    ev_in, ck_in = 0, 0
    # ---- event probes
    for n, s in enumerate(probes):
        u = f"e{n}"
        k.e([f"pe{n}", u, s, base.f1(w0 + DAY), "view", "p1", ""])  # ingest early: never late
        t = oracle(s)
        if t is not None and w0 <= t < w1:
            ev_in += 1
            for j, a in enumerate((t - GAP, t + GAP)):
                if w0 <= a < w1:
                    k.e([f"pa{n}_{j}", u, f3(a), base.f1(w0 + DAY), "view", "p1", ""])
    # ---- click probes: each has its own campaign
    for n, s in enumerate(probes[::3]):
        u, camp = f"k{n}", f"c_{n + 1}"
        k.campaigns.append((camp, "search"))
        k.c([f"ck{n}", u, camp, s])
        t = oracle(s)
        if t is not None and w0 - WEEK <= t < w1:
            ck_in += 1
            for j, a in enumerate((t, t + WEEK)):
                if w0 <= a < w1:
                    k.e([f"ka{n}_{j}", u, f3(a), base.f1(w0 + DAY), "purchase", "p1", "100"])
    # ---- ingest probes (ingest is always valid F1 by the rules; dates off the table too)
    for n in range(200):
        u = f"i{n}"
        ts = w0 + rng.randrange(w1 - w0)
        ts -= ts % SEC
        lag = rng.choice([DAY, DAY + SEC, DAY - SEC, -10 * DAY, -9 * DAY, 9 * DAY, 30 * DAY, 0])
        k.e([f"pi{n}", u, f3(ts), base.f1(ts + lag), "cart", "p1", ""])
    # dedup across the table edge: the smaller ingest is off the table and invalid -> no rescue
    for n in range(100):
        u = f"j{n}"
        ts = w0 + rng.randrange(w1 - w0)
        ts -= ts % SEC
        small, big = sorted([ts - rng.choice([9, 10, 40]) * DAY, ts - rng.choice([0, 1, 7]) * DAY])
        bad_first = n % 2 == 0
        k.e([f"pj{n}", u, f3(ts), base.f1(small), "CART" if bad_first else "cart", "p1", ""])
        k.e([f"pj{n}", u, f3(ts), base.f1(big), "cart" if bad_first else "CART", "p1", ""], file="e1.csv")
    print(f"{name}: {len(probes)} probes, {ev_in} event and {ck_in} click probes in window", file=sys.stderr)
    return k


WINDOWS = [
    # (name, window_start, window_end): year end, leap day, off-midnight 30 days (table on),
    # 40 days (table off: fallback only), Sep/Oct/Nov month-parity edges
    ("ts_yearend", utc(2027, 12, 25), utc(2028, 1, 8)),
    ("ts_leap", utc(2028, 2, 22), utc(2028, 3, 7)),
    ("ts_offmidnight30", utc(2026, 10, 1, 5, 30), utc(2026, 10, 31, 5, 30)),
    ("ts_wide40", utc(2026, 10, 1), utc(2026, 11, 10)),
    ("ts_autumn", utc(2026, 9, 24), utc(2026, 10, 8)),
]

CASES = [lambda w=w, i=i: build(w[0], w[1], w[2], 100 + i) for i, w in enumerate(WINDOWS)]

if __name__ == "__main__":
    root = Path(sys.argv[1])
    for mk in CASES:
        c = mk()
        c.write(root)
        print(c.name)
