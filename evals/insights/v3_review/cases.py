#!/usr/bin/env python3
"""Hand-built adversarial datasets for the v3 correctness review (evals/insights/v3-review.md).

    .venv/bin/python evals/insights/v3_review/cases.py OUT_DIR      # writes OUT_DIR/<case>/...

Each case targets one risk in v3's rewrite (packed IDs, dedup side stream, direct-index
lookups, SIMD line scan). Every probe uses its own users and days, so a wrong decision
shows up as a specific wrong output row. Cases marked ROBUST use inputs outside the
rules (no final newline); all others stay inside docs/rules.md.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

DAY, MIN, SEC = 86_400_000, 60_000, 1000
W0 = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp() * 1000)
W1 = W0 + 14 * DAY
EH = "event_id,user_id,ts,ingest_ts,event_type,product_id,price_cents"
CH = "click_id,user_id,campaign_id,ts"
LH = "user_id_a,user_id_b"


def f1(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ev(eid, user, ts, ingest=None, typ="view", prod="p1", price=""):
    ingest = ts + 10 * SEC if ingest is None else ingest
    return [eid, user, f1(ts) if isinstance(ts, int) else ts, f1(ingest), typ, prod, price]


def line(fields, quote=()):
    return ",".join(f'"{f}"' if i in quote else f for i, f in enumerate(fields))


class Case:
    def __init__(self, name):
        self.name = name
        self.events: dict[str, list[str]] = {"e0.csv": []}
        self.clicks: dict[str, list[str]] = {"c0.csv": []}
        self.links: dict[str, list[str]] = {"l0.csv": []}
        self.products = [("p1", "books")]
        self.campaigns = [("c_1", "search")]
        self.final_newline = True

    def e(self, fields, file="e0.csv", quote=()):
        self.events.setdefault(file, []).append(line(fields, quote) if isinstance(fields, list) else fields)

    def c(self, fields, file="c0.csv", quote=()):
        self.clicks.setdefault(file, []).append(line(fields, quote) if isinstance(fields, list) else fields)

    def l(self, a, b, file="l0.csv"):
        self.links.setdefault(file, []).append(f"{a},{b}")

    def write(self, root: Path):
        d = root / self.name
        for sub in ("events", "clicks", "links"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        (d / "manifest.json").write_text(json.dumps({"window_start": f1(W0), "window_end": f1(W1)}))
        (d / "products.csv").write_text("product_id,category\n" + "".join(f"{p},{c}\n" for p, c in self.products))
        (d / "campaigns.csv").write_text("campaign_id,channel\n" + "".join(f"{p},{c}\n" for p, c in self.campaigns))
        for sub, hdr, files in (("events", EH, self.events), ("clicks", CH, self.clicks), ("links", LH, self.links)):
            for fn, rows in files.items():
                body = hdr + "\n" + "".join(r + "\n" for r in rows)
                if not self.final_newline and rows:
                    body = body[:-1]
                (d / sub / fn).write_bytes(body.encode("utf-8", "surrogateescape"))


# ---------------------------------------------------------------- 1. ID shapes and order
def case_ids():
    k = Case("ids")
    comps = [
        ["abcdefghij", "abcdefghij0"],           # packed (10) is a prefix of fallback (11)
        ["abcdefghija", "abcdefghik"],            # fallback (11) sorts before packed (10)
        ["abcdefghijz", "abcdefghijA"],           # both fallback, differ at char 11
        ["Zz", "_a", "a", "é"],                   # 'Z' < '_' < 'a' < UTF-8
        ["zz", "~a"],                             # '~' (0x7e) is not packable and sorts after 'z'
        ["u1", " u1", "u1 "],                     # spaces are part of the ID
        ["0", "00", "000000000000"],              # zero padding vs a real '0'
        ["k9", "k10", "kk", "K", "k_"],
        ["ZZZZZZZZZZ", "ZZZZZZZZZZZ"],
        ["é1", "é2"],                             # both fallback
        ["m5", "!m"],                             # link-only smallest ('!' < '0'); "!m" has no events
        ["abcdefghijé", "abcdefghij"],       # 10 packable + UTF-8 tail
        ["a-b", "a_b", "a.b", "aZb"],             # '-' and '.' sort before digits
        ["9999999999", "99999999999", "A"],
        ["q1", "q2\r"],                           # \r inside an ID (quoted, mid-line)
    ]
    rng = random.Random(1)
    for ci, ids in enumerate(comps):
        order = ids[:]
        rng.shuffle(order)
        for a, b in zip(order, order[1:]):
            if rng.random() < 0.5:
                a, b = b, a
            k.l(f'"{a}"' if "\r" in a else a, f'"{b}"' if "\r" in b else b, file=f"l{ci % 3}.csv")
        for j, u in enumerate(ids):
            if u == "!m":
                continue
            t = W0 + ci * DAY // 2 + j * 7 * MIN
            k.e(ev(f"ev{ci}_{j}", u, t), file=f"e{j % 2}.csv", quote=(1,) if ("\r" in u or u.startswith(" ") or u.endswith(" ")) else ())
    # unlinked case variants stay two persons
    k.e(ev("evx1", "x", W0 + 10 * DAY))
    k.e(ev("evx2", "X", W0 + 10 * DAY))
    # click ts ties: smallest click_id wins (each probe its own person, day and campaigns)
    ties = [
        [("abcdefghij0", "c_11"), ("abcdefghij", "c_12")],      # -> c_12
        [("abcdefghija", "c_13"), ("abcdefghik", "c_14")],      # -> c_13
        [("é", "c_15"), ("z", "c_16")],                         # -> c_16
        [("Z9", "c_17"), ("_0", "c_18"), ("a", "c_19")],        # -> c_17
        [("abcdefghijz", "c_20"), ("abcdefghijA", "c_21")],     # -> c_21 (both fallback)
        [(" b", "c_22"), ("!b", "c_23"), ("b", "c_24")],        # -> c_22 (click_ids are global: no reuse)
    ]
    for c in range(11, 25):
        k.campaigns.append((f"c_{c}", f"ch{c}"))
    for ti, group in enumerate(ties):
        user = f"tie{ti}"
        s = W0 + (ti + 1) * DAY + 12 * 3600 * SEC
        k.e(ev(f"evt{ti}", user, s))
        for cid, camp in group:
            k.c([cid, user, camp, f1(s - 5 * MIN)], quote=(0,) if cid.startswith(" ") else ())
            k.c([cid, user, camp, f1(s - 5 * MIN)], file="c1.csv", quote=(0, 1, 2, 3))  # duplicate copy
    return k


# ---------------------------------------------------------------- 2. dedup
def case_dedup():
    k = Case("dedup")
    t = W0 + DAY
    I = t + 60 * SEC

    def probe(n):  # each probe on its own user and hour
        return f"du{n}", t + n * 3 * 3600 * SEC

    u, ts = probe(1)  # min-ingest copy has a bad ts -> no rescue
    k.e(ev("D1", u, ts, ts + 9 * SEC), file="e0.csv")
    k.e(ev("D1", u, "2026-10-02T25:00:00Z", ts + 5 * SEC), file="e1.csv")
    u, ts = probe(2)  # min-ingest copy is late -> no rescue
    k.e(ev("D2", u, ts, ts + DAY + SEC), file="e1.csv")
    k.e(ev("D2", u, ts + 60 * SEC, ts + DAY + 2 * SEC), file="e0.csv")
    k.e(ev("D2b", u, ts, ts + DAY), file="e2.csv")  # exactly 24 h: kept
    u, ts = probe(3)  # valid@5, invalid@3, valid@4 in three files
    k.e(ev("D3", u, ts, ts + 5 * SEC), file="e0.csv")
    k.e(ev("D3", u, ts, ts + 3 * SEC, typ="View"), file="e1.csv")
    k.e(ev("D3", u, ts, ts + 4 * SEC), file="e2.csv")
    u, ts = probe(4)  # identical copies, equal ingest, quoted differently
    for i, q in enumerate([(), (0, 1), (2, 3, 4, 5, 6)]):
        k.e(ev("D4", u, ts, ts + 7 * SEC, typ="purchase", prod="p1", price="250"), file=f"e{i}.csv", quote=q)
    u, ts = probe(5)  # later copies name a different user
    k.e(ev("D5", u, ts, ts + 2 * SEC, typ="purchase", price="100"), file="e2.csv")
    k.e(ev("D5", "du5other", ts, ts + 9 * SEC, typ="purchase", price="900"), file="e0.csv")
    k.e(ev("D5x", "du5other", ts + 3 * DAY), file="e1.csv")
    u, ts = probe(6)  # earliest copy has an empty user -> dropped
    k.e(ev("D6", "", ts, ts + SEC), file="e1.csv")
    k.e(ev("D6", u, ts, ts + 2 * SEC), file="e0.csv")
    k.e(ev("D6y", u, ts + 2 * DAY), file="e0.csv")
    u, ts = probe(7)  # earliest copy is malformed -> the next copy wins
    k.e(line(ev("D7", u, ts, ts + SEC)) + ",extra", file="e0.csv")
    k.e(ev("D7", u, ts, ts + 2 * SEC), file="e1.csv")
    u, ts = probe(8)  # min copy: purchase with a bad price
    k.e(ev("D8", u, ts, ts + SEC, typ="purchase", price="0"), file="e1.csv")
    k.e(ev("D8", u, ts, ts + 2 * SEC, typ="purchase", price="500"), file="e0.csv")
    k.e(ev("D8z", u, ts + 2 * DAY), file="e0.csv")
    u, ts = probe(9)  # fallback event IDs, and IDs that differ only by space / case
    for eid in ["eventid_long_1", "eventid_long_1", "é1", "é1", " e1", "e1", "E1", "e1 "]:
        k.e(ev(eid, u, ts, ts + 4 * SEC), file="e0.csv", quote=(0,))
    u, ts = probe(10)  # min copy outside the window
    k.e(ev("D10", u, W1 + MIN, ts + SEC), file="e1.csv")
    k.e(ev("D10", u, ts, ts + 2 * SEC), file="e0.csv")
    k.e(ev("D10z", u, ts + 3 * DAY), file="e0.csv")
    # bulk: many users, cross-partition losers (later copies to other users), random order
    rng = random.Random(7)
    rows = []
    for n in range(4000):
        user = f"bu{rng.randrange(600)}"
        ts = W0 + rng.randrange(13 * DAY)
        ing = ts + rng.randrange(0, 2 * DAY)  # some late
        typ = rng.choice(["view", "cart", "purchase", "purchase", "Cart"])
        price = str(rng.choice([0, 1, 250, 10_000_000, 10_000_001]))
        eid = f"b{n}" if rng.random() < 0.7 else f"bulk_event_{n:06d}"  # packed / fallback
        rows.append(ev(eid, user, ts, ing, typ, f"p{rng.randrange(1, 4)}", price))
        for _ in range(rng.choice([0, 0, 0, 1, 2, 3])):
            other = user if rng.random() < 0.6 else f"bu{rng.randrange(600)}"
            later = ing + rng.choice([0, SEC, 600 * SEC])
            rec = ev(eid, user if later == ing else other, ts if later == ing else ts + rng.randrange(-DAY, DAY),
                     later, typ if later == ing else rng.choice(["view", "purchase"]), rows[-1][5],
                     price if later == ing else "300")
            if later != ing and rng.random() < 0.2:
                rec[2] = "bad"
            rows.append(rec)
    rng.shuffle(rows)
    for i, r in enumerate(rows):
        k.e(r, file=f"b{i % 9}.csv", quote=(0,) if i % 5 == 0 else ())
    k.products += [("p2", "toys"), ("p3", "a")]
    return k


# ---------------------------------------------------------------- 3. direct-index lookups
def case_lookups():
    k = Case("lookups")
    prods = ["p0", "p00", "p07", "p7", "P7", "p4194303", "p4194304", "p9999999", "p10000000", "p", "p-1",
             "p 1", "p1 ", "p99999999999999999999", "p１", "pp7", "p+7"]
    k.products = [(p, f"cat_{i:02d}") for i, p in enumerate(prods)]
    refs = prods + ["p8", "p0007", "p01", "p4194305", "p000", "P0", "p1", "p٧"]
    for i, p in enumerate(refs):
        ts = W0 + i * 4 * 3600 * SEC
        k.e(ev(f"lp{i}", f"lu{i}", ts, typ="purchase", prod=p, price=str(100 + i)),
            quote=(5,) if p.startswith(" ") or p.endswith(" ") else ())
    camps = ["c_0", "c_00", "c_7", "c_07", "C_7", "c_4194304", "c_", "c_9999999", "c_1 ", "c_99999999999999999999",
             "c_4194303", "c__1"]
    k.campaigns = [(c, f"chan_{i:02d}") for i, c in enumerate(camps)]
    crefs = camps + ["c_8", "c_007", "c_4194305", "c_1", "c", "c_٣"]
    for i, c in enumerate(crefs):
        user = f"lc{i}"
        s = W0 + (i % 13) * DAY + (i // 13 + 1) * 3600 * SEC
        k.e(ev(f"lce{i}", user, s))
        k.c([f"lck{i}", user, c, f1(s - MIN)])
    return k


# ---------------------------------------------------------------- 4. SIMD scan / dialect
def case_scan(final_newline=True, name="scan", seed=11):
    k = Case(name)
    k.final_newline = final_newline
    k.products.append(("p2", "shoes"))
    k.campaigns.append(("c_2", "email"))
    rng = random.Random(seed)
    # CRLF: \r belongs to the last field
    k.e(line(ev("cr1", "cru1", W0 + DAY, typ="view", price="12")) + "\r")         # valid (price ignored)
    k.e(line(ev("cr2", "cru2", W0 + DAY, typ="purchase", price="1000")) + "\r")   # bad price
    k.e(ev("cr3", "cru3", W0 + 2 * DAY))
    k.c(line(["crk3", "cru3", "c_2", f1(W0 + 2 * DAY - MIN)]) + "\r")             # bad click ts
    k.e(ev("cr4", "cru4", W0 + 2 * DAY))
    k.c(line(["crk4", "cru4", "c_2", f1(W0 + 2 * DAY - MIN)]))
    k.l("cru5", "cru6\r")                                                          # "cru6\r" is another ID
    k.e(ev("cr5", "cru6", W0 + 3 * DAY))
    k.e(ev("cr6", "cru5", W0 + 3 * DAY))
    # malformed shapes (all dropped)
    for bad in ["", ",,,,,,", '"', '""""""', line(ev("m1", "mu", W0)) + ",", "," + line(ev("m2", "mu", W0)),
                line(ev("m3", 'm"u', W0 + DAY)), line(ev("m4", '"mu"x', W0 + DAY)), line(ev("m5", '""mu""', W0 + DAY)),
                line(ev("m6", "mu", W0 + DAY))[:-1].replace(",", ";", 1), "\r", '"m7"' + line(ev("", "mu", W0))[0:]]:
        k.e(bad)
    # quoted empty fields and quoted values
    k.e(line(ev("q1", "qu1", W0 + 4 * DAY, typ="purchase", price="0250"), quote=(0, 1, 2, 3, 4, 5, 6)))
    k.e('"q2","qu2","' + f1(W0 + 4 * DAY) + '","' + f1(W0 + 4 * DAY) + '","view","",""')  # empty product -> drop
    k.e(line(ev("q3", "qu3", W0 + 4 * DAY, typ="view", price='""')))
    # a NUL byte inside an ID
    k.e(ev("nul1", "nu\x00l", W0 + 5 * DAY))
    # lines straddling 64-byte blocks: pad the user ID so commas/quotes/newlines land on every offset
    for pad in range(0, 140):
        user = "s" + "x" * pad
        q = rng.choice([(), (), (1,), (0,), (6,), (5, 6)])
        typ = rng.choice(["view", "purchase"])
        k.e(ev(f"pad{pad}", user, W0 + 6 * DAY + pad * MIN, typ=typ, prod=rng.choice(["p1", "p2", "p9"]),
               price=rng.choice(["", "1", "77", '1"2', "1,2"])), quote=q, file=f"e{pad % 3}.csv")
        if pad % 7 == 0:
            k.e(line(ev(f"padbad{pad}", user, W0)) + '"', file=f"e{pad % 3}.csv")  # trailing quote: malformed
    # one very long line (> 64 B and > the CHUNK=97 debug chunk) and very long IDs
    k.e(ev("long1", "L" * 300, W0 + 7 * DAY, typ="purchase", prod="P" * 500, price="999"))
    k.l("L" * 300, "short")
    k.e(ev("long2", "short", W0 + 7 * DAY + MIN))
    k.c(["K" * 200, "short", "c_2", f1(W0 + 7 * DAY - MIN)])
    # header-only file
    k.events["empty.csv"] = []
    return k


# ---------------------------------------------------------------- 5. crash probes
def case_edges():
    k = Case("edges")  # no valid events at all, clicks and links only
    k.e(ev("x1", "", W0 + DAY))
    k.c(["k1", "u1", "c_1", f1(W0)])
    k.l("u1", "u2")
    return k


def case_whale():
    k = Case("whale")  # one person, many rows in one partition and one task; long chain
    ids = [f"w{i}" for i in range(400)]
    random.Random(3).shuffle(ids)
    for a, b in zip(ids, ids[1:]):
        k.l(a, b)
    rng = random.Random(4)
    for n in range(60_000):
        ts = W0 + rng.randrange(14 * DAY)
        k.e(ev(f"w{n}", rng.choice(ids), ts, typ=rng.choice(["view", "purchase"]), prod="p1", price="5"))
    for n in range(3000):
        k.c([f"wk{n}", rng.choice(ids), "c_1", f1(W0 - 7 * DAY + rng.randrange(21 * DAY))])
    return k


CASES = [case_ids, case_dedup, case_lookups, case_scan,
         lambda: case_scan(False, "scan_no_final_newline", 12), case_edges, case_whale]

if __name__ == "__main__":
    root = Path(sys.argv[1])
    for mk in CASES:
        c = mk()
        c.write(root)
        print(c.name)
