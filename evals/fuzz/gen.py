#!/usr/bin/env python3
"""Adversarial dataset generator for differential testing (candidate vs reference).

    .venv/bin/python evals/fuzz/gen.py --seed N --out DIR      # writes DIR/{manifest.json,...}, prints case.json

Every case is small (tens to a few thousand rows) and dense in the corner cases
of docs/rules.md. A seed picks a *focus* (dialect, timestamps, sessions, clicks,
links, dedup, files, overflow, window, mixed, id-shapes) that raises the rate of that
family; every family still appears at a base rate. Seeds >= WINDOWS_SEED0 (100000) all take the
`windows` focus instead: year-end, new-year, leap-day and month-end windows (some off midnight),
timestamps at the window and click-window edges, at local midnights via F2 offsets, and at
window -/+ 8 days, the edges of a date-table timestamp decoder. Seeds below it are unchanged.

Cases are `strict` (everything stays inside rules.md: these gate a submission)
unless they use an out-of-spec input, which makes them `robust` (reported, not
gating): 0-byte CSVs, a missing final newline, non-.csv files in the input
folders, header variants, and windows that are not 14 days from a midnight.

Invariants kept so the reference oracle stays well-defined:
  * every well-formed event line with a non-empty event_id has a valid F1 ingest_ts;
  * event copies with equal ingest_ts have identical values (quoting may differ);
  * click copies have identical values (quoting may differ);
  * products.csv / campaigns.csv are clean with unique IDs, no category is `unknown`.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

DAY = 86_400_000
GAP = 1_800_000
WEEK = 7 * DAY
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
WINDOWS_SEED0 = 100_000  # must match evals/lib/correct.py
FOCI = ["dialect", "timestamps", "sessions", "clicks", "links", "dedup", "files", "overflow", "window", "mixed"]
ARABIC = "٠١٢٣٤٥٦٧٨٩"
FULLWIDTH = "０１２３４５６７８９"
CATEGORIES = ["books", "Books", "shoes", "toys", "a", "b", "zz", "électro", "Unknown", "unknowN", "garden"]
CHANNELS = ["search", "social", "email", "display", "affiliate"]
EVENT_HEADER = "event_id,user_id,ts,ingest_ts,event_type,product_id,price_cents"
CLICK_HEADER = "click_id,user_id,campaign_id,ts"
LINK_HEADER = "user_id_a,user_id_b"


def to_dt(ms: int) -> datetime:
    return EPOCH + timedelta(milliseconds=ms)


def from_dt(dt: datetime) -> int:
    return (dt - EPOCH) // timedelta(milliseconds=1)


class Gen:
    def __init__(self, seed: int):
        self.seed = seed
        self.r = random.Random(seed * 7919 + 17)
        r = self.r
        self.focus = FOCI[seed % len(FOCI)] if seed < 10 * len(FOCI) else r.choice(FOCI)
        if seed % 20 == 10:
            self.focus = "id-shapes"
        if seed >= WINDOWS_SEED0:
            self.focus = "windows"
        self.tags: set[str] = {self.focus}
        self.robust: list[str] = []
        f = self.focus
        # base rates, raised by the focus
        self.p_quote = 0.2 if f != "dialect" else 0.5
        self.p_malformed = 0.01 if f != "dialect" else 0.08
        self.p_crlf = 0.005 if f != "dialect" else 0.06
        self.p_empty_line = 0.003 if f != "dialect" else 0.03
        self.p_bad_ts = {"timestamps": 0.15, "windows": 0.06}.get(f, 0.01)
        self.p_edge_ts = 0.05 if f != "timestamps" else 0.3
        self.p_overflow = 0.003 if f != "overflow" else 0.08
        self.p_dup = 0.04 if f != "dedup" else 0.35
        self.p_bad_type = 0.003 if f != "dialect" else 0.02
        self.p_bad_price = 0.05
        self.p_late = 0.01 if f != "timestamps" else 0.05
        self.p_bad_user = 0.003
        self.p_unknown_product = 0.01
        self.p_edge_gap = 0.05 if f != "sessions" else 0.5
        self.n_files_events = r.choice([1, 2, 3, 5, 8]) if f != "files" else r.choice([40, 120, 250])
        self.n_files_clicks = r.choice([1, 2, 4]) if f != "files" else r.choice([20, 80])
        self.n_files_links = r.choice([1, 2, 3]) if f != "files" else r.choice([10, 60])
        self.events: list[tuple[str, int]] = []  # (line, file hint or -1)
        self.clicks: list[str] = []
        self.links: list[str] = []
        self.session_starts: list[tuple[list[str], int]] = []  # (person ids, intended start)
        self._window()
        self._catalog()

    # ------------------------------------------------------------ setup
    def _window(self):
        r = self.r
        if self.focus == "windows":
            return self._windows_window()
        if self.focus == "window" and r.random() < 0.5:
            self.tags.add("leap")
            start = datetime(2028, 2, r.randint(14, 29), tzinfo=timezone.utc)
        elif self.focus == "window" and r.random() < 0.4:
            self.tags.add("year-end")
            start = datetime(r.choice([2025, 2026, 2027]), 12, r.randint(20, 28), tzinfo=timezone.utc)
        elif r.random() < 0.12:
            self.tags.add("leap")  # windows holding Feb 29 2028 (and Feb 28/Mar 1 edges)
            start = datetime(2028, 2, r.randint(14, 29), tzinfo=timezone.utc)
        else:
            start = datetime(r.randint(2025, 2028), r.randint(1, 12), r.randint(1, 28), tzinfo=timezone.utc)
        length = 14
        if self.focus == "window" and r.random() < 0.3:
            # out of spec for the generator, still a legal manifest: robust only
            length = r.choice([1, 2, 3, 20])
            self.robust.append(f"window-{length}d")
        if self.focus == "window" and r.random() < 0.15:
            start = start + timedelta(hours=r.randint(1, 23), minutes=r.randint(0, 59), seconds=r.randint(0, 59))
            self.robust.append("window-not-midnight")
        self.ws = from_dt(start)
        self.we = self.ws + length * DAY

    def _windows_window(self):
        r = self.r
        kind = r.choice(["year-end", "new-year", "leap", "leap-after", "non-leap-feb", "month-end"])
        self.tags.add(kind)
        if kind == "year-end":
            start = datetime(r.choice([2025, 2026, 2027]), 12, r.randint(17, 31), tzinfo=timezone.utc)
        elif kind == "new-year":
            start = datetime(r.choice([2026, 2027, 2028]), 1, r.randint(1, 8), tzinfo=timezone.utc)
        elif kind == "leap":
            start = datetime(2028, 2, r.randint(14, 29), tzinfo=timezone.utc)
        elif kind == "leap-after":
            start = datetime(2028, 3, r.randint(1, 9), tzinfo=timezone.utc)  # Feb 29 in the click lookback
        elif kind == "non-leap-feb":
            start = datetime(r.choice([2025, 2026, 2027]), 2, r.randint(14, 28), tzinfo=timezone.utc)
        else:
            y, m = r.randint(2025, 2028), r.randint(1, 12)
            last = ((datetime(y + m // 12, m % 12 + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)).day)
            start = datetime(y, m, r.randint(last - 3, last), tzinfo=timezone.utc)
        if r.random() < 0.25:
            # not a midnight: out of spec for the generator, still a legal manifest, so robust only
            start += timedelta(hours=r.randint(0, 23), minutes=r.randint(0, 59), seconds=r.randint(1, 59))
            self.robust.append("window-not-midnight")
            self.tags.add("not-midnight")
        self.ws = from_dt(start)
        self.we = self.ws + 14 * DAY

    def window_probes(self) -> list[int]:
        """Instants at the edges a window-relative timestamp decoder could get wrong."""
        ws, we, r = self.ws, self.we, self.r
        pts = [ws, ws - 1000, ws + 1000, ws - 1, ws + 1, we, we - 1000, we - 1, we + 1000,
               ws - WEEK, ws - WEEK - 1000, ws - WEEK + 1000, ws - WEEK - 1, ws - WEEK + 1,
               ws - 8 * DAY, ws - 8 * DAY - 1000, ws - 8 * DAY + 1000, we + 8 * DAY, we + 8 * DAY - 1000,
               ws - 9 * DAY, we + 9 * DAY]
        # every UTC midnight in and around the window, and a second either side
        first = ws - ws % DAY
        for d in range(-9, 24):
            m = first + d * DAY
            pts += [m, m - 1000, m + 1000]
        # year boundaries and Feb 29 / Mar 1 near the window
        for y in {to_dt(ws - 9 * DAY).year, to_dt(we + 9 * DAY).year}:
            pts += [from_dt(datetime(y, 1, 1, tzinfo=timezone.utc)) + k for k in (-1000, 0, 1000)]
            pts += [from_dt(datetime(y, 3, 1, tzinfo=timezone.utc)) + k for k in (-DAY, -1000, 0)]
        r.shuffle(pts)
        return pts

    def render_probe(self, ms: int) -> str:
        """A valid rendering of ms; F2 offsets put the local date on another day (or year) than UTC."""
        r = self.r
        if ms % 1000:
            return self._f3(ms)
        x = r.random()
        if x < 0.3:
            return self.f1(ms)
        if x < 0.8:
            off = r.choice([1, 59, 60, 13 * 60 + 45, 14 * 60, 23 * 60 + 59, 0])
            sign = r.choice("+-")
            local = to_dt(ms) + timedelta(minutes=off if sign == "+" else -off)
            return local.strftime("%Y-%m-%dT%H:%M:%S") + f"{sign}{off // 60:02d}:{off % 60:02d}"
        return self._f3(ms)

    def emit_window_probes(self):
        """One fresh person per probe, so a wrong decode or bound shows as its own wrong row."""
        r = self.r
        product = next(iter(self.products))
        for n, t in enumerate(self.window_probes()):
            uid = f"wp{n}"
            ts = self.render_probe(t)
            ingest = self.f1(max(t, 0) - max(t, 0) % 1000 + 1000 * r.randint(0, 5))
            typ = r.choice(["view", "cart", "purchase"])
            self.events.append((f"we{n},{uid},{ts},{ingest},{typ},{product},{r.randint(1, 5000)}", -1))
            if r.random() < 0.5:
                # a click at the probe instant, crediting (or not) a session that starts at a window edge
                anchor = r.choice([self.ws, self.ws + 1000, t + WEEK, t + WEEK - 1000, t + WEEK + 1000, t + 1000])
                if self.ws <= anchor < self.we:
                    self.events.append((f"wa{n},{uid},{self.render_probe(anchor - anchor % 1000)},"
                                        f"{self.f1(anchor - anchor % 1000)},view,{product},", -1))
                self.clicks.append(f"wk{n},{uid},{r.choice(self.camp_ids)},{self.render_probe(t)}")
        self.tags.add("window-probes")

    def _catalog(self):
        r = self.r
        cats = r.sample(CATEGORIES, r.randint(2, 6))
        self.products = {f"p{i}": r.choice(cats) for i in range(1, r.randint(3, 40))}
        self.campaigns = {f"c_{i}": r.choice(CHANNELS) for i in range(1, r.randint(2, 30))}
        if self.focus == "id-shapes" and len(self.campaigns) == 1:
            self.campaigns["c_2"] = "email"
        self.camp_ids = list(self.campaigns)

    # ------------------------------------------------------------ ids
    def new_id(self, kind="u") -> str:
        r = self.r
        x = r.random()
        base = kind + "".join(r.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(r.randint(1, 6)))
        if x < 0.02:
            return base.upper()
        if x < 0.03:
            return " " + base
        if x < 0.04:
            return base + " "
        if x < 0.05:
            return base + "ü"
        if x < 0.055:
            return "日本" + base
        if x < 0.06:
            return base + "\r" + "x"  # a \r inside a value is an ordinary character
        if x < 0.062:
            return base * 40  # long ID
        if x < 0.064:
            return "user_id_a" if kind == "u" else base  # collides with the link header text
        return base

    # ------------------------------------------------------------ timestamps
    def f1(self, ms: int) -> str:
        return to_dt(ms).strftime("%Y-%m-%dT%H:%M:%SZ")

    def ts_valid(self, ms: int) -> str:
        """Render a valid timestamp; any ms value must use F3."""
        r = self.r
        if ms % 1000:
            return self._f3(ms)
        x = r.random()
        if self.focus == "windows":
            return self.render_probe(ms)
        if x < 0.55:
            return self.f1(ms)
        if x < 0.75:
            return self._f2(ms)
        return self._f3(ms)

    def _f3(self, ms: int) -> str:
        r = self.r
        z = r.random()
        if z < 0.15:
            return "0" * r.randint(1, 4) + str(ms)
        if z < 0.18 + self.p_overflow:
            self.tags.add("f3-long-zeros")
            return "0" * r.randint(8, 40) + str(ms)  # longer than 19 digits, still in range
        return str(ms)

    def _f2(self, ms: int) -> str:
        r = self.r
        x = r.random()
        if x < 0.1:
            off = 0
            sign = r.choice("+-")
        elif x < 0.2:
            off, sign = 23 * 60 + 59, r.choice("+-")
        else:
            off, sign = r.choice([60, 120, 240, 270, 330, 345, 480, 540, 600, 720, 765, 13 * 60 + 45]), r.choice("+-")
        local = to_dt(ms) + timedelta(minutes=off if sign == "+" else -off)
        return local.strftime("%Y-%m-%dT%H:%M:%S") + f"{sign}{off // 60:02d}:{off % 60:02d}"

    def ts_bad(self, ms: int) -> str:
        r = self.r
        sec = ms - ms % 1000
        d = to_dt(sec)
        f1 = self.f1(sec)
        y = d.year
        forms = [
            "",
            f1[:-1] + f".{ms % 1000:03d}Z",
            f1[:-1] + ".0Z",
            f1[:-1] + "z",
            f1.replace("T", "t"),
            f1.replace("T", " "),
            f1[:-1],
            f1[:-1] + "+0200",
            f1[:-1] + "+24:00",
            f1[:-1] + "+05:60",
            f1[:-1] + "+2:00",
            f1[:-1] + "+02:0",
            f1[:-1] + "+02:00:00",
            f1 + "+02:00",
            f1[:-1] + "-24:30",
            f"{y}-13-01T10:00:00Z",
            f"{y}-00-10T10:00:00Z",
            f"{y}-02-30T10:00:00Z",
            f"{y}-04-31T10:00:00Z",
            f"{y}-01-32T10:00:00Z",
            f"{y}-01-00T10:00:00Z",
            "2027-02-29T10:00:00Z", "2026-02-29T10:00:00Z", "2100-02-29T10:00:00Z",
            f1[:11] + "24:00:00Z",
            f1[:11] + "23:60:00Z",
            f1[:11] + "23:59:60Z",
            str(ms) + ".0",
            f"{ms / 1e3:.3e}",
            "-5",
            "+" + str(ms),
            " " + str(ms),
            str(ms) + " ",
            " " + f1,
            f1 + " ",
            f1 + "\r",
            str(ms) + "\r",
            str(ms).translate(str.maketrans("0123456789", ARABIC)),
            str(ms).translate(str.maketrans("0123456789", FULLWIDTH)),
            FULLWIDTH[2] + f1[1:],
            f1[:5] + ARABIC[1] + f1[6:],
            f1.replace("-", "/"),
            f1[2:],
            f"{y}-1-05T10:00:00Z",
            str(ms) + "Z",
            "0x" + format(ms, "x"),
            "1e12",
            "NaN",
            "null",
            "T",
        ]
        return r.choice(forms)

    def ts_overflow(self, ms: int) -> str:
        """Digits-only values that wrap to `ms` (or another in-window value) in fixed-width arithmetic."""
        r = self.r
        self.tags.add("overflow")
        return r.choice([
            str(2**64 + ms), str(2**63 + ms), str(2**65 + ms), str(10**19 + ms), str(2**64 * 7 + ms),
            "9223372036854775807", "9223372036854775808", "18446744073709551615", "18446744073709551616",
            "9" * r.randint(20, 40), str(ms) + "0" * r.randint(1, 8),
        ])

    def render_ts(self, ms: int, bad_rate: float) -> str:
        r = self.r
        x = r.random()
        if x < bad_rate:
            return self.ts_bad(ms)
        if x < bad_rate + self.p_overflow:
            return self.ts_overflow(ms)
        return self.ts_valid(ms)

    # ------------------------------------------------------------ csv lines
    def q(self, v: str) -> str:
        return f'"{v}"' if self.r.random() < self.p_quote else v

    def line(self, fields: list[str], last_crlf_ok=True) -> str:
        r = self.r
        s = ",".join(self.q(f) for f in fields)
        if r.random() < self.p_malformed:
            s = self.malform(fields)
            self.tags.add("malformed")
        if last_crlf_ok and r.random() < self.p_crlf:
            s += "\r"
            self.tags.add("crlf")
        return s

    def malform(self, fields: list[str]) -> str:
        r = self.r
        k = r.randrange(len(fields))
        f = list(fields)
        choice = r.randrange(11)
        if choice == 0:
            f.append(r.choice(["", "x"]))           # one field too many
        elif choice == 1:
            f.pop(k)                                 # one too few
        elif choice == 2:
            f[k] = '"' + f[k]                        # unbalanced quote
        elif choice == 3:
            f[k] = f[k] + '"'
        elif choice == 4:
            f[k] = f[k][:1] + '"' + f[k][1:] if f[k] else 'a"b'  # quote inside
        elif choice == 5:
            f[k] = '"' + f[k] + '"x'                 # junk after closing quote
        elif choice == 6:
            f[k] = '""' + f[k] + '""'                # doubled quotes
        elif choice == 7:
            f[k] = '"'                               # a lone quote
        elif choice == 8:
            return ",".join(f) + ","                 # trailing comma
        elif choice == 9:
            return "\r"                              # a line holding only \r (1 field)
        else:
            f[k] = f'"{f[k]}"' + '"'                 # triple quote at end
        return ",".join(f)

    # ------------------------------------------------------------ people
    def build_people(self):
        r = self.r
        n_people = (r.randint(3, 25) if self.focus != "links" else r.randint(10, 60)) * r.choice([1, 1, 2, 4, 8])
        self.people: list[list[str]] = []
        for _ in range(n_people):
            k = r.choices([1, 2, 3, 4, 6, 8], [45, 30, 13, 6, 4, 2])[0]
            ids = [self.new_id() for _ in range(k)]
            self.people.append(ids)
        # IDs only ever in links (can be the person's name)
        for ids in self.people:
            if r.random() < 0.08:
                ids.append(r.choice(["!", "0", "A", "Z", "_", " "]) + self.new_id())
        # long chains
        if self.focus == "links" or r.random() < 0.1:
            n = r.randint(50, 600) if self.focus == "links" else r.randint(20, 120)
            self.people.append([self.new_id("v") for _ in range(n)])
            self.tags.add("long-chain")
        self.used_only = {i for p in self.people for i in p[-1:] if p[-1][:1] in "!0AZ_ "}

    def emit_links(self):
        r = self.r
        lines = []
        for ids in self.people:
            if len(ids) == 1:
                if r.random() < 0.05:
                    lines.append([ids[0], ids[0]])  # self-link
                continue
            if len(ids) > 30:
                order = ids[:]
                r.shuffle(order)
                pairs = [(order[i], order[i + 1]) for i in range(len(order) - 1)]  # a chain, linked one after the next
            else:
                pairs = [(ids[i], ids[r.randrange(i)]) for i in range(1, len(ids))]  # a tree
            for a, b in pairs:
                if r.random() < 0.5:
                    a, b = b, a
                lines.append([a, b])
                if r.random() < 0.08:
                    lines.append([b, a] if r.random() < 0.5 else [a, b])  # repeats, either way round
                if r.random() < 0.01:
                    lines.append([a, a])
        # shared device: one ID linking several people into one
        if self.focus in ("links", "mixed") or r.random() < 0.1:
            dev = self.new_id("d")
            for ids in r.sample(self.people, min(len(self.people), r.randint(2, 8))):
                lines.append([dev, r.choice(ids)])
            self.tags.add("shared-device")
        # dirt: empty sides, upper-cased sides (split a person), header-like row
        for _ in range(r.randint(0, 4)):
            p = r.choice(self.people)
            lines.append([r.choice(p), ""] if r.random() < 0.5 else ["", r.choice(p)])
        for _ in range(r.randint(0, 2)):
            p = r.choice(self.people)
            lines.append([r.choice(p).upper(), r.choice(p)])
        if r.random() < 0.3:
            lines.append(["user_id_a", "user_id_b"])
            self.tags.add("header-like")
        r.shuffle(lines)
        self.links = [self.line(l) for l in lines]

    # ------------------------------------------------------------ events
    def next_gap(self, within: bool) -> int:
        r = self.r
        if r.random() < self.p_edge_gap:
            self.tags.add("edge-gap")
            if within:
                return r.choice([0, 0, 1, GAP - 1, GAP, GAP, 999, 1000])
            return r.choice([GAP + 1, GAP + 1, GAP + 2, GAP + 1000, DAY, WEEK, WEEK + 1])
        if within:
            return r.choice([0, 1000 * r.randint(1, 600), r.randint(1, GAP)])
        return r.choice([GAP + 1000 * r.randint(1, 3600), 3_600_000 * r.randint(1, 30), r.randint(GAP + 1, 3 * DAY)])

    def session_anchor(self) -> int:
        r = self.r
        x = r.random()
        span = self.we - self.ws
        if self.focus == "windows" and x < 0.5:
            return r.choice(self.window_probes()[:8])
        if x < 0.1:
            return self.ws + r.choice([0, 1, -1, -1000, 1000])
        if x < 0.2:
            return self.we + r.choice([-1, -1000, 0, 1, -GAP])
        if x < 0.35:
            # just before a midnight inside the window (sessions crossing midnight)
            d = r.randrange(max(span // DAY, 1))
            return self.ws + (d + 1) * DAY - r.choice([1, 1000, 60_000, GAP, GAP - 1])
        return self.ws + r.randrange(span)

    def emit_events(self):
        r = self.r
        eid_n = 0
        all_ids = [i for p in self.people for i in p]
        for ids in self.people:
            used = [i for i in ids if i not in self.used_only] or ids
            n_sessions = r.choices([0, 1, 2, 3, 5, 8], [5, 30, 25, 20, 12, 8])[0]
            if len(ids) > 30:
                n_sessions = r.randint(5, 20)
            t = self.session_anchor()
            for _ in range(n_sessions):
                n_ev = r.choices([1, 2, 3, 5, 10, 25], [25, 25, 20, 15, 10, 5])[0]
                self.session_starts.append((ids, t))
                for j in range(n_ev):
                    if j:
                        t += self.next_gap(True)
                    eid_n += 1
                    eid = self.event_id(eid_n)
                    self.emit_event(eid, r.choice(used), t, all_ids)
                t += self.next_gap(False)
                if r.random() < 0.3:
                    t = self.session_anchor()

    def event_id(self, n: int) -> str:
        r = self.r
        x = r.random()
        base = f"e{n}"
        if x < 0.01:
            return base.upper()
        if x < 0.015:
            return base + " "
        if x < 0.02:
            return ""  # empty event_id: dropped
        return base

    def emit_event(self, eid: str, uid: str, ts: int, all_ids: list[str]):
        r = self.r
        etype = r.choices(["view", "cart", "purchase"], [60, 25, 15])[0]
        if r.random() < self.p_bad_type:
            etype = r.choice(["Purchase", "VIEW", "cart ", " view", "", "purchased", "Cart", "view\r"])
            self.tags.add("bad-type")
        pid = r.choice(list(self.products))
        if r.random() < self.p_unknown_product:
            pid = r.choice(["p99999", pid.upper(), " " + pid, pid + " ", "", "unknown"])
        price = self.price(etype)
        user = uid if r.random() >= self.p_bad_user else r.choice(["", uid.upper()])
        ts_s = self.render_ts(ts, self.p_bad_ts)
        ingest = self.ingest_for(ts)
        fields = [eid, user, ts_s, self.f1(ingest), etype, pid, price]
        orig = self.line(fields)
        self.events.append((orig, -1))
        # duplicates
        if r.random() < self.p_dup and eid:
            self.tags.add("dup")
            kind = r.random()
            if kind < 0.25:
                # equal ingest: identical values, quoted differently
                copy = ",".join(f'"{f}"' if r.random() < 0.5 else f for f in fields)
                self.events.append((copy + ("\r" if orig.endswith("\r") else ""), -1))
            elif kind < 0.5:
                # later copies, possibly with a different user (earliest copy wins)
                later = ingest
                for k in range(r.randint(1, 3)):
                    later += 1000 * r.randint(1, 600)  # strictly increasing: no equal-ingest copies
                    u2 = r.choice(all_ids) if r.random() < 0.3 else user
                    t2 = self.render_ts(ts + r.choice([0, 0, 1000, -GAP - 1]), self.p_bad_ts)
                    self.events.append((self.line([eid, u2, t2, self.f1(later), etype, pid, price]), -1))
            elif kind < 0.7:
                # the earliest copy is invalid (bad ts / type / price / user): the event is dropped,
                # a later valid copy must NOT rescue it
                bad = list(fields)
                which = r.randrange(4)
                if which == 0:
                    bad[2] = self.ts_bad(ts)
                elif which == 1:
                    bad[4] = "Purchase"
                elif which == 2:
                    bad[1] = ""
                else:
                    bad[4], bad[6] = "purchase", "0"
                earlier = ingest - 1000 * r.randint(1, 600)
                bad[3] = self.f1(earlier)
                self.events.append((self.line(bad), -1))
                self.tags.add("dup-invalid-first")
            elif kind < 0.85:
                # a malformed earlier copy is dropped at parse, so the later one is kept
                earlier = list(fields)
                earlier[3] = self.f1(ingest - 1000 * r.randint(1, 600))
                self.events.append((self.malform(earlier), -1))
            else:
                # an earlier copy with a different user, listed after the original
                earlier = list(fields)
                earlier[3] = self.f1(ingest - 1000 * r.randint(1, 600))
                earlier[1] = r.choice(all_ids)
                self.events.append((self.line(earlier), -1))

    def price(self, etype: str) -> str:
        r = self.r
        if etype != "purchase":
            return r.choice(["", "", "100", "-5", "1.5", "abc", "0", "99999999999"])
        x = r.random()
        if x < self.p_bad_price:
            self.tags.add("bad-price")
            return r.choice(["", "0", "00", "-5", "+5", "1.5", "10000001", "19.99", " 100", "100 ",
                             "٢٥٠", "２５０", "1e3", "100\r", "0x10"])
        if x < self.p_bad_price + self.p_overflow:
            self.tags.add("overflow")
            return r.choice([str(2**64 + 100), str(2**32 + 100), str(2**63 + 1), "9" * 25, str(2**31 + 5),
                             "0" * 30 + "250"])
        if x < 0.15:
            return r.choice(["1", "10000000", "0250", "0001", "0" * 20 + "10000000", "9999999"])
        if x < 0.35:
            return r.choice(["100", "500", "1000", "2500"])  # round prices: top_category ties
        return str(r.randint(1, 50_000))

    def ingest_for(self, ts: int) -> int:
        """A valid F1 (whole-second) ingest_ts near ts, with lateness edge cases."""
        r = self.r
        x = r.random()
        if x < self.p_late:
            self.tags.add("late")
            delta = r.choice([DAY, DAY, DAY + 1000, DAY - 1000, DAY + 1, DAY - 1, 2 * DAY, 5 * DAY])
        elif x < self.p_late + 0.05:
            delta = -1000 * r.randint(1, 3600)  # ingested before ts: kept
        else:
            delta = 1000 * r.randint(0, 600)
        t = ts + delta
        # whole seconds: round toward ts+delta in either direction, so ms ts give 24h +- <1s
        return t - t % 1000 if r.random() < 0.5 else t - t % 1000 + (1000 if t % 1000 else 0)

    # ------------------------------------------------------------ clicks
    def emit_clicks(self):
        r = self.r
        cid_n = 0

        def click(uid: str, ts: int, camp: str | None = None, cid: str | None = None, bad_rate=None):
            nonlocal cid_n
            cid_n += 1
            cid = cid if cid is not None else f"k{cid_n}"
            if r.random() < 0.005:
                cid = ""
            camp = camp or r.choice(self.camp_ids)
            if r.random() < 0.01:
                camp = r.choice(["c_9999", camp.upper(), " " + camp, "", "organic", "C_1"])
            user = uid if r.random() >= self.p_bad_user else r.choice(["", uid.upper()])
            fields = [cid, user, camp, self.render_ts(ts, self.p_bad_ts if bad_rate is None else bad_rate)]
            s = ",".join(self.q(f) for f in fields)
            if r.random() < self.p_malformed:
                s = self.malform(fields)
            crlf = r.random() < self.p_crlf
            if crlf:
                s += "\r"  # the ts becomes ...\r: a bad ts
            self.clicks.append(s)
            if cid and r.random() < (0.03 if self.focus != "dedup" else 0.3):
                # identical values (same trailing \r), quoted differently
                for _ in range(r.randint(1, 2)):
                    self.clicks.append(",".join(f'"{f}"' if r.random() < 0.5 else f for f in fields)
                                       + ("\r" if crlf else ""))
                self.tags.add("click-dup")

        edge = 0.3 if self.focus == "clicks" else 0.08
        for ids, start in self.session_starts:
            if r.random() < 0.4:
                continue
            for _ in range(r.randint(1, 3)):
                uid = r.choice(ids)
                if r.random() < edge:
                    self.tags.add("edge-click")
                    off = r.choice([0, 0, 1, -1, WEEK, WEEK, WEEK + 1, WEEK - 1, 1000, GAP, DAY])
                    t = start - off
                    click(uid, t, bad_rate=0.0)
                    if r.random() < 0.4:
                        # same-ms tie: credit goes to the byte-wise smallest click_id
                        a, b = r.choice([("k10", "k9"), ("K1", "k1"), ("k1", "k1 "), ("a", "b"), ("k2", "k10"),
                                         ("k1", "k1\u00e9")])
                        # "~n" keeps tie IDs unique and apart from the plain k<n> IDs
                        click(r.choice(ids), t, cid=f"{a}~{cid_n}", bad_rate=0.0)
                        click(r.choice(ids), t, cid=f"{b}~{cid_n}", bad_rate=0.0)
                        self.tags.add("tie-click")
                else:
                    click(uid, start - r.randint(0, WEEK + DAY))
        # click-window boundaries
        any_ids = [i for p in self.people for i in p]
        for t in (self.ws - WEEK, self.ws - WEEK - 1, self.ws - WEEK + 1, self.we, self.we - 1, self.ws):
            if r.random() < 0.5:
                click(r.choice(any_ids), t, bad_rate=0.0)
        # clicks of IDs with no events (only links), and random noise
        for _ in range(r.randint(0, 10)):
            click(self.new_id(), self.ws + r.randrange(self.we - self.ws))
        if r.random() < 0.2:
            self.clicks.append("click_id,user_id,campaign_id,ts")
            self.tags.add("header-like")

    # ------------------------------------------------------------ ID shape
    def emit_id_shapes(self):
        prefix = "abcdefghij"
        owners = (prefix, prefix + "x", prefix + "y", "A_bcdefghi")
        # Leave the two suffix variants unlinked so truncation would merge distinct people.
        self.links.append(f"{owners[0]},{owners[3]}")
        ts = self.f1(self.ws + DAY)
        product = next(iter(self.products))
        for i, (eid, uid) in enumerate(zip(("0123456789", "0123456789x", "0123456789y", "_Z01234567"), owners)):
            self.events.append((f"{eid},{uid},{ts},{ts},purchase,{product},{100 + i}", -1))
        # Two campaigns at the same instant, with the winning ID differing after char 10.
        first, second = list(self.campaigns)[:2]
        self.clicks.extend([f"9876543210y,{owners[0]},{second},{ts}",
                            f"9876543210x,{owners[3]},{first},{ts}",
                            f"9876543210,{owners[2]},{second},{ts}"])

    # ------------------------------------------------------------ files
    def write(self, out: Path):
        r = self.r
        out.mkdir(parents=True, exist_ok=True)
        (out / "manifest.json").write_text(json.dumps({"window_start": self.f1(self.ws), "window_end": self.f1(self.we)}))
        (out / "products.csv").write_text("product_id,category\n" + "".join(f"{p},{c}\n" for p, c in self.products.items()))
        (out / "campaigns.csv").write_text("campaign_id,channel\n" + "".join(f"{c},{h}\n" for c, h in self.campaigns.items()))
        ev_lines = [l for l, _ in self.events]
        r.shuffle(ev_lines)
        for table, header, lines, nfiles in (("events", EVENT_HEADER, ev_lines, self.n_files_events),
                                             ("clicks", CLICK_HEADER, self.clicks, self.n_files_clicks),
                                             ("links", LINK_HEADER, self.links, self.n_files_links)):
            d = out / table
            d.mkdir(exist_ok=True)
            if table != "events":
                lines = lines[:]
                r.shuffle(lines)
            # empty lines (malformed)
            for _ in range(int(len(lines) * self.p_empty_line) + (1 if r.random() < 0.2 else 0)):
                lines.insert(r.randrange(len(lines) + 1), "")
                self.tags.add("empty-line")
            # Zipf-ish split into files, some header-only
            weights = [1 / (i + 1) for i in range(nfiles)]
            r.shuffle(weights)
            buckets: list[list[str]] = [[] for _ in range(nfiles)]
            for l in lines:
                buckets[r.choices(range(nfiles), weights)[0]].append(l)
            if nfiles > 1 and r.random() < 0.5:
                buckets.append([])  # a header-only file
            names = r.sample(range(10_000), len(buckets))
            for i, b in zip(names, buckets):
                body = header + "\n" + "".join(l + "\n" for l in b)
                (d / f"part-{i:05d}.csv").write_text(body, encoding="utf-8", newline="")
            # out-of-spec extras: robust only
            if self.focus == "files" and r.random() < 0.3:
                (d / "empty-0-bytes.csv").write_bytes(b"")
                self.robust.append("zero-byte-csv")
            if self.focus == "files" and r.random() < 0.2:
                (d / "notes.txt").write_text(header + "\n" + (lines[0] if lines else "") + "\n")
                (d / "part.csv.bak").write_text(header + "\n")
                self.robust.append("non-csv-files")
            if self.focus == "files" and r.random() < 0.2 and b:
                p = d / f"part-{names[-1]:05d}.csv"
                p.write_bytes(p.read_bytes().rstrip(b"\n"))
                self.robust.append("no-final-newline")
            if self.focus == "dialect" and r.random() < 0.1:
                p = d / "zz-header-crlf.csv"
                p.write_text(header + "\r\n", newline="")
                self.robust.append("header-crlf")

    def generate(self, out: Path) -> dict:
        self.build_people()
        self.emit_links()
        self.emit_events()
        self.emit_clicks()
        if self.focus == "id-shapes":
            self.emit_id_shapes()
        if self.focus == "windows":
            self.emit_window_probes()
        self.write(out)
        return {"seed": self.seed, "focus": self.focus, "tags": sorted(self.tags),
                "strict": not self.robust, "robust_reasons": sorted(set(self.robust)),
                "rows": {"events": len(self.events), "clicks": len(self.clicks), "links": len(self.links)},
                "window": [self.f1(self.ws), self.f1(self.we)]}


def generate(seed: int, out: Path) -> dict:
    return Gen(seed).generate(Path(out))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    print(json.dumps(generate(a.seed, Path(a.out)), indent=2))


if __name__ == "__main__":
    main()
