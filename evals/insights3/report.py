#!/usr/bin/env python3
"""Per-phase x86 (callgrind) vs ARM (macOS instr=) table, with the rep-string correction.

Usage: report.py <dataset dir> <label> <commit>... [--cache DIR]
Reads $OUT/cg/<sha12>-<label>/summary.json (from parse_cg.py) and results/arm-<commit>-<label>.json.
Writes results/x86-<commit>-<label>.json and prints markdown.

rep correction: valgrind counts every iteration of `rep stosb` (glibc memset-vec-unaligned-erms.S:336)
and `rep movsb` (memmove-vec-unaligned-erms.S:598) as one instruction, i.e. one Ir per byte. Hardware
retires the string op at ~32-64 B/cycle. `corr` replaces those Ir with bytes/32 (one AVX2 store per
32 B, about what the ARM libc's stp/dc zva loop retires), so `corr` is comparable to the ARM count.
"""
import json, os, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("OUT", os.path.expanduser("~/.cache/insights3"))
PH = ["lookups", "events", "clicks", "dedup", "sessions", "write"]
REP = ("memset-vec-unaligned-erms.S:336", "memmove-vec-unaligned-erms.S:598")

def lines(ds, d):
    n = 0
    for f in os.listdir(os.path.join(ds, d)):
        if f.endswith(".csv"):
            with open(os.path.join(ds, d, f), "rb") as fh:
                n += sum(1 for _ in fh) - 1
    return n

def sha12(c):
    return subprocess.check_output(["git", "rev-parse", c], cwd=here, text=True).strip()[:12]

def incl(r, pat):
    return sum(v for k, v in r["focus_incl"].items() if pat in k)

def calls(r, pat):
    return sum(v for k, v in r["focus_calls"].items() if k.endswith(pat))

def main():
    ds, label, commits = sys.argv[1], sys.argv[2], sys.argv[3:]
    nl = {d: lines(ds, d) for d in ("events", "clicks", "links")}
    print(f"dataset {ds}: events {nl['events']:,} clicks {nl['clicks']:,} links {nl['links']:,} lines\n")
    rows = {}
    for c in commits:
        s = sha12(c)
        summ = json.load(open(os.path.join(OUT, "cg", f"{s}-{label}", "summary.json")))
        armf = os.path.join(here, "results", f"arm-{c}-{label}.json")
        arm = json.load(open(armf)) if os.path.exists(armf) else {}
        out = {"commit": c, "sha": s, "lines": nl, "phases": {}}
        for ph in PH:
            r = summ[ph]
            raw = r["totals"][0]
            rep = sum(v for k, v in r["memlines"].items() if k in REP)
            corr = raw - rep + rep / 32
            it = incl(r, "<sessions::Ids>::intern")
            out["phases"][ph] = {
                "raw": raw, "rep_bytes": rep, "corr": corr, "arm": arm.get(ph),
                "intern_incl": it, "intern_calls": calls(r, "-> <sessions::Ids>::intern"),
                "rustc_entry_incl": incl(r, "rustc_entry"), "rehash_incl": incl(r, "reserve_rehash<") + incl(r, "reserve_rehash::<hashbrown::map::make_hasher<&[u8]"),
                "ids_bytes_incl": incl(r, "<sessions::Ids>::bytes"), "ids_bytes_calls": calls(r, "-> <sessions::Ids>::bytes"),
                "self": dict(list(r["self"].items())[:20]),
            }
        rows[c] = out
        json.dump(out, open(os.path.join(here, "results", f"x86-{c}-{label}.json"), "w"), indent=1)
    E = nl["events"]
    print("| phase | " + " | ".join(f"{c} ARM | {c} x86 raw | {c} x86 corr | x86/ARM" for c in commits) + " |")
    print("|---|" + "---:|" * (4 * len(commits)))
    tot = {c: [0, 0, 0] for c in commits}
    for ph in PH:
        cells = []
        for c in commits:
            p = rows[c]["phases"][ph]
            a = p["arm"]
            tot[c][0] += a or 0; tot[c][1] += p["raw"]; tot[c][2] += p["corr"]
            cells.append(f"{a / E:,.0f}" if a else "–")
            cells.append(f"{p['raw'] / E:,.0f}")
            cells.append(f"{p['corr'] / E:,.0f}")
            cells.append(f"{p['corr'] / a:.2f}" if a else "–")
        print(f"| {ph} | " + " | ".join(cells) + " |")
    cells = []
    for c in commits:
        a, rw, co = tot[c]
        cells += [f"{a / E:,.0f}" if a else "–", f"{rw / E:,.0f}", f"{co / E:,.0f}", f"{co / a:.2f}" if a else "–"]
    print("| **total** | " + " | ".join(cells) + " |")
    print("\n(all per event line; own-line rates: events/event line, clicks/click line)\n")
    for c in commits:
        P = rows[c]["phases"]
        print(f"{c}: events/event-line x86 {P['events']['corr'] / E:,.0f} (ARM {P['events']['arm'] / E if P['events']['arm'] else 0:,.0f}); "
              f"clicks/click-line x86 {P['clicks']['corr'] / nl['clicks']:,.0f} (ARM {(P['clicks']['arm'] or 0) / nl['clicks']:,.0f})")
        for ph in ("lookups", "events", "clicks"):
            p = P[ph]
            if p["intern_calls"]:
                print(f"   {ph}: Ids::intern {p['intern_calls']:,} calls, {p['intern_incl']:,} Ir incl = {p['intern_incl'] / p['intern_calls']:.0f}/call, "
                      f"{p['intern_incl'] / E:.1f} per event line; of which HashMap entry {p['rustc_entry_incl']:,}, rehash {p['rehash_incl']:,}")
        for ph in ("lookups", "sessions", "write"):
            p = P[ph]
            if p["ids_bytes_calls"] or p["ids_bytes_incl"]:
                print(f"   {ph}: Ids::bytes {p['ids_bytes_incl']:,} Ir incl ({p['ids_bytes_calls']:,} calls from user_batch)")
        print(f"   rep-string bytes counted as Ir: " + ", ".join(f"{ph} {P[ph]['rep_bytes'] / 1e6:.1f}M" for ph in PH if P[ph]['rep_bytes'] > 1e5))

if __name__ == "__main__":
    main()
