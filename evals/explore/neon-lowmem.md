# Neon: v14 dedup (branch `explore/v14-neon`, on `integ/v13.1` @ `1262b3e`)

x86 callgrind, `x86-64-v2` amd64 container, NCPU=1, dev (1,071,894 event lines), private
target volume `neon-x86-target`. "corr" replaces `rep stosb`/`rep movsb` Ir (counted per byte
by valgrind) with bytes/32, as `evals/insights3/report.py` does.

| commit | change | raw Ir/line | corr Ir/line | corr vs 1262b3e | dedup corr |
|---|---|---:|---:|---:|---:|
| v8 `2bfb034` | champion (board 1.0844 s) | 1,315.7 | 1,218.5 | +19.1% | 48.5 |
| `1262b3e` | v13.1 base | 1,109.0 | 1,023.1 | 0 | 49.2 |
| `0e57f01` | generation-tagged locators (no per-partition table clear), multiplicative hash | 1,037.2 | 1,007.2 | −1.56% | 33.2 |
| `3202850` | `EidEnt` carries `rf`: one 24 B push per event instead of two Vecs | 1,024.6 | 994.5 | −2.80% | 30.4 |
| `fbfaa11` | fresh zeroed table on growth, pre-sized drop Vecs | 1,023.7 | 993.2 | −2.93% | 29.1 |
| **`c9b6fa6`** | inner loop: pre-scaled byte offsets, running locator | **1,018.5** | **988.0** | **−3.44%** | **23.9** |

- `1262b3e`'s dedup phase was 114.7M raw Ir, 63.8M of it `rep stosb` from `tab.resize` per
  partition. Most of the raw gain (−8.2%) is that artifact; the corrected gain is −3.44%.
- `3202850` also cuts the events phase by 10.6 Ir/line (503.8 → 493.2): one fewer push.
- `c9b6fa6`: `(rot32(h) & hmask & m) << 4 == rot36(h) & ((m & hmask) << 4)`. Probing still
  walks with `m`, so `SESSIONS_DEBUG_HASH_BITS=0` still terminates.

Gates on `c9b6fa6`, all pass: fixtures 36/36; dev MATCH under NO_FAST 0–3 (native and x86);
seed-42 (native and x86); long-ID 240/240 (40 seeds); seed-535 PARTS=4096 NCPU=8 ×10; the x86
callgrind run's output also MATCHes.

2-bit-counter prefilter (scout): not done. A unique insert is now ~20 instructions, while the
prefilter's two passes cost ~18 per entry plus the exact pass on ~7%, so it saves ≤ 2–3 Ir/line
on instruction count. Its win is cache (1 B counters instead of 16 B slots), i.e. wall time at
60M, not Ir.
