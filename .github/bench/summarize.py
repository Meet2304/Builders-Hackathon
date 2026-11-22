import json, re, sys, statistics as st, collections as C
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
by = C.OrderedDict()
for r in rows: by.setdefault(r["cfg"], []).append(r)
LOGS = sys.argv[2] if len(sys.argv) > 2 else "logs"
LAP = re.compile(r"^\[\s*([\d.]+)s\] (.+?) \((.*)\)\s*$")
def laps(cfg, rep):
    out = []
    try: lines = open(f"{LOGS}/{cfg}.{rep}.err").read().splitlines()
    except OSError: return out
    for l in lines:
        m = LAP.match(l)
        if not m: continue
        kv = dict(re.findall(r"(\w+)=([\d.]+)", m.group(3)))
        out.append((m.group(2), float(m.group(1)), float(kv.get("cpu", 0)), int(float(kv.get("minflt", 0))), float(kv.get("maxrss", 0))))
    return out
ref = next((r["hash"] for r in rows if r["cfg"].startswith("v15") and r["hash"]), "")
print("## Wall (s): median [min..max] over reps\n\n| cfg | median | min | max | engine last lap | overhead | rc | hash match |\n|---|---|---|---|---|---|---|---|")
for cfg, rs in by.items():
    w = [r["wall"] for r in rs]
    eng = [laps(cfg, r["rep"]) for r in rs]; eng = [e[-1][1] for e in eng if e]
    em = st.median(eng) if eng else float("nan")
    h = rs[0]["hash"]
    hm = "" if not h else ("ref" if h == ref else f"≠ {h}")
    print(f"| {cfg} | {st.median(w):.3f} | {min(w):.3f} | {max(w):.3f} | {em:.3f} | {st.median(w)-em:.3f} | {','.join(str(r['rc']) for r in rs)} | {hm} |")
print("\n## Phases: mean wall ms per phase (cpu-s in parens, minflt k) \n")
cfgs = [c for c in by if not c.startswith("true-")]
phase = C.OrderedDict(); data = {}
for cfg in cfgs:
    acc = C.defaultdict(list)
    for r in by[cfg]:
        L = laps(cfg, r["rep"]); pw = pc = pf = 0
        for name, w, c, f, rss in L:
            phase.setdefault(name, 1); acc[name].append((w - pw, c - pc, f - pf, rss)); pw, pc, pf = w, c, f
    data[cfg] = acc
print("| phase | " + " | ".join(cfgs) + " |\n|---|" + "---|" * len(cfgs))
for p in phase:
    cells = []
    for cfg in cfgs:
        v = data[cfg].get(p)
        if not v: cells.append(""); continue
        cells.append(f"{1000*st.mean(x[0] for x in v):.0f} ({st.mean(x[1] for x in v):.2f}c, {st.mean(x[2] for x in v)/1000:.0f}kf)")
    print(f"| {p} | " + " | ".join(cells) + " |")
print("\n## peak RSS (MB, last lap)\n")
for cfg in cfgs:
    L = laps(cfg, by[cfg][0]["rep"])
    if L: print(f"- {cfg}: {L[-1][4]:.0f} MB, cpu total {L[-1][2]:.2f}s, minflt {L[-1][3]}")
