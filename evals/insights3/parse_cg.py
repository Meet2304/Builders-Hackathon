#!/usr/bin/env python3
"""Attribute callgrind self-Ir per phase dump to source functions / library buckets.

Usage: parse_cg.py <run dir> <src/main.rs of that commit> [--lines N_events N_clicks N_links]
Writes <run dir>/summary.json and prints a table.

src/main.rs lines are mapped to their enclosing `fn` by brace matching (works through LTO
inlining because DWARF line tables keep the inlined function's file:line). Code from other
files is bucketed by file path (hashbrown, std mutex/futex, xxhash, parquet/arrow, ...).
Inclusive cost of each symbol (fn=) is also accumulated from call records.
"""
import json, os, re, sys, glob, collections

def fn_map(path):
    src = open(path, encoding="utf-8", errors="replace").read()
    lines = src.split("\n")
    # tokenizer-lite: strip comments/strings/char literals, keep braces and newlines
    out = []; i = 0; n = len(src)
    while i < n:
        ch = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i); i = n if j < 0 else j; continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2); seg = src[i:j + 2]; out.append("\n" * seg.count("\n")); i = j + 2; continue
        if ch == '"' or (ch == 'b' and src.startswith('b"', i)) or (ch == 'r' and re.match(r'r#*"', src[i:i+4])):
            m = re.match(r'b?r(#*)"', src[i:i+5])
            if m:
                close = '"' + m.group(1); j = src.find(close, i + len(m.group(0)))
                seg = src[i:j + len(close)]; out.append("\n" * seg.count("\n")); i = j + len(close); continue
            j = i + (2 if ch == 'b' else 1)
            while j < n and src[j] != '"':
                j += 2 if src[j] == '\\' else 1
            seg = src[i:j + 1]; out.append("\n" * seg.count("\n")); i = j + 1; continue
        m = re.match(r"b?'(\\.[^']*|[^\\'])'", src[i:i+12])
        if m and (i == 0 or not (src[i-1].isalnum() or src[i-1] == '_')):
            i += len(m.group(0)); out.append(" "); continue
        out.append(ch); i += 1
    clean = "".join(out).split("\n")
    # walk: track impl blocks and fn bodies
    owner = [None] * (len(clean) + 2)
    stack = []  # (kind, name, depth_at_open)
    depth = 0; pending = None; brk = 0
    for ln, text in enumerate(clean, 1):
        m = re.search(r'\bfn\s+([A-Za-z_][A-Za-z0-9_]*)', text)
        mi = re.match(r'\s*(?:pub\s+)?impl\b(?:<[^>]*>)?\s*(?:([A-Za-z_][\w:]*)(?:<[^{]*>)?\s+for\s+)?([A-Za-z_][\w]*)', text)
        if mi and pending is None:
            pending = ("impl", (mi.group(1) + " for " if mi.group(1) else "") + mi.group(2) if False else mi.group(2), ln)
        if m and pending is None or (m and pending and pending[0] == "impl" and pending[2] != ln):
            imp = [s[1] for s in stack if s[0] == "impl"]
            fns = [s[1] for s in stack if s[0] == "fn"]
            base = (imp[-1] + "::" if imp else "") + m.group(1)
            if fns:
                base = fns[-1] + "::" + m.group(1)
            pending = ("fn", base, ln)
        for ch in text:
            if ch in "([":
                brk += 1
            elif ch in ")]":
                brk -= 1
            elif ch == "{":
                depth += 1
                if pending:
                    stack.append((pending[0], pending[1], depth)); pending = None
            elif ch == "}":
                if stack and stack[-1][2] == depth:
                    stack.pop()
                depth -= 1
            elif ch == ";" and brk == 0 and pending and pending[0] == "fn":
                pending = None  # trait method declaration
        fns = [s[1] for s in stack if s[0] == "fn"]
        owner[ln] = fns[0] if fns else (pending[1] if pending and pending[0] == "fn" else None)
        # top-level owner: outermost fn (closures/nested fns roll up into it)
    return owner

def bucket_lib(f, sym):
    s = f or ""
    if "hashbrown" in s: return "lib:hashbrown"
    if "foldhash" in s: return "lib:foldhash"
    if "xxhash" in s or "xxh3" in s: return "lib:xxh3"
    if re.search(r"sync/(mutex|poison)|sys/sync|futex", s): return "lib:std-mutex"
    if "parquet" in s or "arrow" in s or "thrift" in s: return "lib:parquet/arrow"
    if "rayon" in s or "crossbeam" in s: return "lib:rayon"
    if "mimalloc" in s or "libmimalloc" in sym: return "lib:mimalloc"
    if "memchr" in s: return "lib:memchr"
    if "serde" in s: return "lib:serde"
    if "core/src/slice/sort" in s: return "lib:core-sort"
    if "stdarch" in s: return "simd:" + os.path.basename(s)
    if "/core/src/" in s or "/alloc/src/" in s or "/std/src/" in s:
        m = re.search(r"/(core|alloc|std)/src/(.*)", s); return "std:" + m.group(2).split("/")[0]
    if not s or s == "???":
        if re.search(r"mem(cpy|move|set|cmp)|__memcpy|__memset|__memmove", sym): return "libc:mem*"
        if "mi_" in sym or "_mi_" in sym: return "lib:mimalloc"
        return "other:" + (sym.split("(")[0][:40] if sym else "?")
    return "file:" + os.path.basename(s)

def parse(path, owner):
    names = {"fl": {}, "fn": {}, "ob": {}}
    def name(kind, v):
        m = re.match(r"\((\d+)\)\s*(.*)", v)
        if not m: return v.strip()
        k, rest = m.group(1), m.group(2)
        tbl = names["fn" if kind in ("fn", "cfn") else "fl" if kind in ("fl", "fi", "fe", "cfl", "cfi") else "ob"]
        if rest: tbl[k] = rest
        return tbl.get(k, "?")
    events = None; self_cost = collections.Counter(); bysym = collections.Counter(); incl = collections.Counter()
    calls = collections.Counter(); totals = None; memlines = collections.Counter()
    fl = fi = fn = cfn = None; last = 0; pending_call = None
    with open(path) as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line: continue
            c0 = line[0]
            if c0.isdigit() or c0 in "+-*":
                parts = line.split()
                p = parts[0]
                if p == "*": pos = last
                elif p[0] in "+-": pos = last + int(p)
                else: pos = int(p)
                last = pos
                vals = [int(x) for x in parts[1:]] + [0] * (len(events) - len(parts) + 1)
                if pending_call is not None:
                    tgt, cnt = pending_call; pending_call = None
                    incl[fn] += vals[0]  # inclusive of callee, recorded at caller
                    if tgt != fn:
                        calls[(fn, tgt)] += cnt
                    continue
                f = fi or fl
                if f and f.endswith("src/main.rs") and 0 < pos < len(owner) and owner[pos]:
                    b = "main:" + owner[pos]
                else:
                    b = bucket_lib(f, fn or "")
                self_cost[b] += vals[0]
                if f and re.search(r"mem(set|move|cpy)-vec", f):
                    memlines[(os.path.basename(f), pos)] += vals[0]
                bysym[fn] += vals[0]
                incl[fn] += vals[0]
                for i, e in enumerate(events[1:], 1):
                    self_cost[(b, e)] += vals[i]
                continue
            k, _, v = line.partition("=")
            if k == "fl": fl = name("fl", v); fi = None
            elif k in ("fi", "fe"): fi = name(k, v)
            elif k == "fn": fn = name("fn", v); fi = None
            elif k == "cfn": cfn = name("cfn", v)
            elif k in ("cfl", "cfi", "cob", "ob"): name(k, v)
            elif k == "calls":
                pending_call = (cfn, int(v.split()[0]))
            elif line.startswith("events:"):
                events = line.split()[1:]
            elif line.startswith("summary:") or line.startswith("totals:"):
                totals = [int(x) for x in line.split()[1:]]
    return events, totals, self_cost, bysym, incl, calls, memlines

FOCUS = re.compile(r"Ids>::intern|Ids>::bytes|Ids>::cmp|rustc_entry|reserve_rehash|xxh3|futex|Mutex|lock_contended|memset|memcpy|memmove|memcmp|syscall")

def main():
    run, srcf = sys.argv[1], sys.argv[2]
    owner = fn_map(srcf)
    files = sorted(glob.glob(os.path.join(run, "callgrind.out*")),
                   key=lambda p: int(p.rsplit(".", 1)[1]) if p.rsplit(".", 1)[1].isdigit() else 99)
    labels = {1: "lookups", 2: "events", 3: "clicks", 4: "dedup", 5: "sessions", 6: "write", 99: "exit"}
    res = {}
    for p in files:
        suf = p.rsplit(".", 1)[1]; idx = int(suf) if suf.isdigit() else 99
        ev, tot, sc, bysym, incl, calls, memlines = parse(p, owner)
        lab = labels.get(idx, f"dump{idx}")
        res[lab] = {
            "events": ev, "totals": tot,
            "self": {k: v for k, v in sc.most_common() if isinstance(k, str)},
            "self_ev": {f"{k[0]}|{k[1]}": v for k, v in sc.items() if isinstance(k, tuple) and v},
            "sym_self": dict(bysym.most_common(60)),
            "sym_incl": dict(incl.most_common(60)),
            "calls": {f"{a} -> {b}": c for (a, b), c in calls.most_common(80)},
            "memlines": {f"{a}:{b}": v for (a, b), v in memlines.most_common(12)},
            "focus_incl": {k: v for k, v in incl.items() if k and FOCUS.search(k)},
            "focus_self": {k: v for k, v in bysym.items() if k and FOCUS.search(k)},
            "focus_calls": {f"{a} -> {b}": c for (a, b), c in calls.items() if (a and FOCUS.search(a)) or (b and FOCUS.search(b))},
        }
    json.dump(res, open(os.path.join(run, "summary.json"), "w"), indent=1)
    for lab, r in res.items():
        print(f"== {lab}: Ir={r['totals'][0] if r['totals'] else '?':,}")
        for k, v in list(r["self"].items())[:14]:
            print(f"   {v:>14,}  {k}")

if __name__ == "__main__":
    main()
