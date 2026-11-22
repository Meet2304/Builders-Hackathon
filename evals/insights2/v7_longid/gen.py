"""Adversarial inputs for v7 move 6 (lock-free long IDs), Analyst 2.

Every ID is drawn from a universe built to stress byte-wise ordering across the
three key kinds (packed <= 10 symbols, long = packable prefix + 32 lowercase hex,
interned = anything else):

- long IDs over a small digit pool reused under several prefixes (same digits,
  other prefix), digit strings sharing 28-31 leading digits, all-0 and all-f
- short packable IDs that are byte-prefixes of long ones (`u` + d[:k]) or diverge
  right after the shared part (`u` + d[:k] + 'z' / '0' / 'A' / '_')
- uppercase hex (whole, or one digit) and one-char case flips: exact fallback,
  sort before lowercase
- 31/32/34-digit and non-hex (`g`) near misses, and unpackable prefixes `-`, `.`

Persons get 1-5 IDs joined by links (some IDs appear only in links), clicks share
the session-start millisecond in groups (click_id tie-breaks across kinds), event
IDs repeat across copies with later ingest (and sometimes another user).

Usage: gen.py SEED OUTDIR
"""
import json
import os
import random
import sys

HEX = "0123456789abcdef"
B36 = "0123456789abcdefghijklmnopqrstuvwxyz"
DAY = 86_400_000
START = 1_790_812_800_000  # 2026-10-01T00:00:00Z
END = START + 14 * DAY


def iso(ms):
    import datetime as dt

    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def universe(r, n_digits):
    base = []
    for _ in range(n_digits):
        base.append("".join(r.choice(HEX) for _ in range(32)))
    # near neighbours: long shared runs, last-digit neighbours, extremes
    for d in list(base[: n_digits // 2]):
        k = r.choice([28, 30, 31])
        base.append(d[:k] + "".join(r.choice(HEX) for _ in range(32 - k)))
    base += ["0" * 32, "f" * 32, "0" * 31 + "1", "f" * 31 + "e", "9" * 32, "a" * 32]
    ids = set()
    prefixes = "uueeckU_0Z"
    for d in base:
        for p in r.sample(prefixes, r.randint(1, 4)):
            ids.add(p + d)  # long (or the exact fallback when p is 'U'/'Z'? no: packable -> long)
        p = r.choice("uec")
        k = r.randint(1, 9)
        ids.add(p + d[:k])  # packable byte-prefix of a long ID
        ids.add(p + d[:k] + r.choice("z0A_"))  # diverges right after the shared part
        if r.random() < 0.3:
            ids.add(p + d.upper())  # uppercase hex: exact fallback
        if r.random() < 0.3:
            j = r.randrange(32)
            ids.add(p + d[:j] + d[j].upper() + d[j + 1 :])  # one flipped digit
        if r.random() < 0.2:
            ids.add(p.upper() + d)  # uppercase prefix: still long (packable)
        if r.random() < 0.15:
            ids.add(p + d[:31])  # 32 bytes
        if r.random() < 0.15:
            ids.add(p + d + r.choice(HEX))  # 34 bytes
        if r.random() < 0.1:
            ids.add(p + d[:20] + "g" + d[21:])  # non-hex digit
        if r.random() < 0.1:
            ids.add(r.choice("-.") + d)  # unpackable prefix
    for _ in range(n_digits):
        ids.add(r.choice("uec") + "".join(r.choice(B36) for _ in range(r.randint(1, 10))))
    return sorted(ids)


def main():
    seed, out = int(sys.argv[1]), sys.argv[2]
    r = random.Random(seed)
    ids = universe(r, r.choice([20, 60, 150]))
    r.shuffle(ids)
    # persons: disjoint ID groups
    persons, i = [], 0
    while i < len(ids):
        n = r.choice([1, 1, 2, 2, 3, 5])
        persons.append(ids[i : i + n])
        i += n
    # each event / click ID is a fresh string from the same alphabet games, drawn from
    # the persons' pool too (an event_id may equal some user_id: different columns)
    ev_pool = universe(random.Random(seed * 7 + 1), 40)
    ck_pool = universe(random.Random(seed * 7 + 2), 40)
    r.shuffle(ev_pool)
    r.shuffle(ck_pool)
    links, events, clicks = [], [], []
    for grp in persons:
        for j in range(1, len(grp)):
            a, b = grp[r.randrange(j)], grp[j]
            links.append((a, b) if r.random() < 0.5 else (b, a))
            if r.random() < 0.1:
                links.append((b, a))
    # some persons use only some of their IDs: the rest live only in links
    t_choices = [START + d * DAY + h * 3_600_000 for d in range(1, 13) for h in range(0, 24, 5)]
    for grp in persons:
        used = grp[: max(1, len(grp) - (1 if len(grp) > 2 and r.random() < 0.5 else 0))]
        for _ in range(r.randint(1, 3)):
            if not ev_pool:
                break
            t0 = r.choice(t_choices)
            for e in range(r.randint(1, 3)):
                if not ev_pool:
                    break
                eid = ev_pool.pop()
                ts = t0 + e * 60_000
                user = r.choice(used)
                typ = r.choice(["view", "cart", "purchase"])
                price = str(r.randint(100, 5000)) if typ == "purchase" else ""
                prod = r.choice(["p1", "p2", "p3"])
                ing = ts + 1000
                events.append((eid, user, iso(ts), iso(ing), typ, prod, price))
                if r.random() < 0.25:  # later copy, maybe another user (dedup keeps first)
                    other = r.choice(r.choice(persons))
                    events.append((eid, other if r.random() < 0.3 else user, iso(ts + 5000), iso(ing + 60_000), typ, prod, price))
                if r.random() < 0.1:  # earlier-ingested invalid copy: kills the event
                    events.append((eid, user, "bad", iso(ing - 500), typ, prod, price))
            # clicks tied at the session start, across key kinds, plus one an hour before
            for _ in range(r.choice([0, 1, 2, 4])):
                if not ck_pool:
                    break
                camp = r.choice(["c_1", "c_2", "c_3"])
                clicks.append((ck_pool.pop(), r.choice(used), camp, iso(t0)))
            if ck_pool and r.random() < 0.5:
                clicks.append((ck_pool.pop(), r.choice(used), r.choice(["c_1", "c_2"]), iso(t0 - 3_600_000)))
    for c in list(clicks):
        if r.random() < 0.1:
            clicks.append(c)  # identical copy
    r.shuffle(events)
    r.shuffle(clicks)
    r.shuffle(links)
    for sub in ("events", "clicks", "links"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)

    def write(path, header, rows, nparts):
        parts = [[] for _ in range(nparts)]
        for row in rows:
            parts[r.randrange(nparts)].append(row)
        for k, rows_k in enumerate(parts):
            with open(os.path.join(out, path, f"part-{k:05d}.csv"), "w") as f:
                f.write(header + "\n")
                for row in rows_k:
                    f.write(",".join(row) + "\n")

    write("events", "event_id,user_id,ts,ingest_ts,event_type,product_id,price_cents", events, r.randint(1, 4))
    write("clicks", "click_id,user_id,campaign_id,ts", clicks, r.randint(1, 3))
    write("links", "user_id_a,user_id_b", links, r.randint(1, 3))
    with open(os.path.join(out, "products.csv"), "w") as f:
        f.write("product_id,category\np1,shoes\np2,books\np3,toys\n")
    with open(os.path.join(out, "campaigns.csv"), "w") as f:
        f.write("campaign_id,channel\nc_1,search\nc_2,social\nc_3,email\n")
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump({"window_start": iso(START), "window_end": iso(END)}, f)


if __name__ == "__main__":
    main()
