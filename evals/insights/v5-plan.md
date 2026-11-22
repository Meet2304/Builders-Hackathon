# v5 plan: first place on the 60M final

Analyst, 2026-11-22 00:30 ET. Base: v4 `a019739` (submitted) and the current head `20b8e79` (`method/v5`, SIMD ID packer).
Sources: `docs/rules.md`, Eval `evals/results/v4.md` (`6f270b2`), Analyst 2 `evals/insights2/`, Sol `evals/explore/cache-bound.md`,
Explorer 2 `evals/explore/gemini-scan.md` (`explore/gemini-scan`), Explorer 3 `evals/explore/gemini3-session-kernel.md`,
and new counts in §0, built from clean for this note.

**Deadline: today, Sunday 11:00 ET, about 10.5 hours away.** That rules out anything that can't be gated by about 08:00.

## The answer

- **Where we are.** The head retires **1,468 instructions per event line** at 20M (NCPU=1), about 1,500 at NCPU=8. At 64.15M lines and 28.77 G instr/s, that's **3.34 s** on the final, plus a 60M cache penalty of about **0.15 s** (not 0.3–0.6 s, see §2). Planning number: **≈ 3.5 s**, against **≈ 0.84 s** for a leader who scales linearly.
- **The spec's floor is ≈ 350 per line, ≈ 0.78 s on the final** (§1). That is the leaders' number. First place means reaching the floor in parse, sessions *and* output, with no 60M cliff.
- **Realistic tonight: ≈ 850–1,020 per line, ≈ 2.0–2.4 s on the final** (revised at 01:00 after `2e22d43`, §3a/§4). ≈ 680 per line and ≈ 1.55 s only if the per-column decoder, Sol's timestamps and the click port all land. The order in §4 gets the most seconds per hour. The rest is floor work that doesn't fit in 10 hours.
- **Partition conflict (§2):** Sol is right that more *global* partitions lose, because the cost is parse fan-out. Analyst 2 is right that the dedup *table* should fit L2, but the penalty was over-modelled. The fix is a second, local level: sub-bucket inside each **eid** partition. Never dedup inside person partitions: 1 in 64 duplicated events changes user between copies.
- **Explorer 2's ceiling (§3)** is real for classify → slices → strip. A per-column decoder that finds each field's end while decoding it never builds the mask stream, the bit walk, or the slices. Its front end should cost **≈ 150–200**, against ≈ 585 now.
- **No clean-room rewrite (§4).** It costs 10–14 agent-hours plus gates, and buys only ≈ 0.1–0.25 s over replacing modules. The fused decoder *is* the rewrite of the one part where the architecture blocks the floor.
- **New, measured, ready:** two Parquet writer settings take output from **112 → 56** per line. They MATCH dev and seed-42 and pass 36/36 fixtures. See `v5_plan/writer-settings.patch`.

## 0. The head, measured

All counts are `instr=` from the binary's own marks (`proc_pid_rusage`). Each tree was built from `git archive 20b8e79` into its own fresh `CARGO_TARGET_DIR`, so no shared-target staleness. Run on seed-42 (21,507,843 event lines), NCPU=1, `nice 5`.

| Binary | sha256 (first 16) |
| --- | --- |
| head `20b8e79` | `69b8dfbaf309301f` |
| head + sub-phase counters (`v5_plan/subphase-counters.patch`) | `708467f5dfac7bcb` |
| head + writer settings (`v5_plan/writer-settings.patch`) | `3666095384f51cb8` |

**Noise warning.** The machine was at load average 8 (other threads benchmarking). In 2 of 9 runs, one phase came out about 2.0 G higher: events parse 20.31 G against 18.30 G, which is +93 per line. The other phases matched to ±3 per line. **Take the minimum of at least 3 runs**, or count under the bench lock. A single count taken under load can invent a 90-instruction regression.

**Per phase, head `20b8e79`, NCPU=1, instructions per event line:**

| Phase | v4 (Eval, NCPU=8) | head (NCPU=1) | Head on the final (s) |
| --- | ---: | ---: | ---: |
| Events parse | 868 | **820** | 1.83 |
| Sessions + attribution | 326 | **322** | 0.72 |
| Clicks parse | 175 | **154** | 0.34 |
| Written (Parquet) | 129 | **112** | 0.25 |
| Dedup | 36 | **33** | 0.07 + cliff |
| Lookups (links) | 30 | **26** | 0.06 |
| 8-thread overhead | (in the above) | +≈ 28 (Analyst 2) | 0.06 |
| **Total** | **1,572** | **1,468 (+28)** | **3.34 + ≈ 0.15** |

The packer delta checks out: Analyst 2's `a019739` at NCPU=1 was 1,590, so `20b8e79` is −122. Method reported −90 on events plus about −23 on clicks.

**Inside sessions + attribution** (counters at six points in `process_part`, NCPU=1, one worker owns the process counter). The kept rows are 19,564,682 and the clicks 5,089,975.

| Sub-phase | Per event line | Per kept row | Note |
| --- | ---: | ---: | --- |
| Drop-ref bitmap | 1.7 | 1.8 | |
| Intern persons + count | 62.7 | 68.9 | hash probe per kept row |
| Counting-sort scatter | 37.9 | 41.7 | |
| Per-person ts sort | 44.3 | 48.7 | |
| **Click collect + sort** | **89.1** | 98.0 | **377 per click**: `sort_unstable_by` on 32 B `PCk` with a 3-key comparator that calls `ids.cmp` |
| **Walk** (sessionize, credit, assists, day flush) | **83.8** | 92.1 | |
| Sum | 319.5 | | phase total 322.3 |

**Correction:** "the sort is about 310 per kept row" is a v3 number (Explorer 3 measured on v3 `29b64bf`). G2 already replaced that sort. In v4 the per-person event sort is **≈ 49 per kept row**, and the whole group-and-sort is 159. The two largest session costs are now the **click sort** and the **walk**.

## 1. The minimal-work budget, from the spec

### What each column must do

**Events** (`event_id,user_id,ts,ingest_ts,event_type,product_id,price_cents`). Every line with a non-empty `event_id` takes part in dedup, invalid or not. A malformed line never does. So the structural check and `(eid, ingest)` are needed on almost every line, and everything else only on lines that can still be valid.

| Column | Needed for | Needed on | Can skip or defer | Floor (instr) |
| --- | --- | --- | --- | ---: |
| (structure) | 7 fields, quotes only around whole fields | every line with a non-empty eid | No. One stray `"` anywhere drops the line, so every byte is looked at once. An empty eid drops the line: skip to `\n`. | ≈ 30 |
| `event_id` | dedup key | every line | Must be exact (pack). Never decoded twice. | ≈ 20 |
| `ingest_ts` | dedup order, late check | every line | **Not deferrable.** The late check needs it on every valid row (0.5–1.5% are late). It is always valid F1 by contract, so decode it straight-line. Keep a cheap template check with the existing scalar fallback so behaviour off-contract is unchanged. | ≈ 12 |
| `event_type` | validity, price relevance | every line | Compare 4/8 bytes against `view`/`cart`/`purchase`. Check it **before** `ts`. | ≈ 5 |
| `ts` | validity, window, sessions | lines whose type, user and product passed | Skip the decode on lines already invalid. The field still needs its structural check. | ≈ 25 |
| `user_id` | person | valid rows only (already so) | Pack plus one link-table probe, prefetched. | ≈ 35 |
| `product_id` | non-empty for all; category for purchases | all / ≈ 3% | **Category only for purchases** (done, `d89e2b5`). For view/cart: non-empty and find its end, no packing, no hashing. | ≈ 5 |
| `price_cents` | purchases only | ≈ 3% | For view/cart the value is ignored. It only needs its structural check up to `\n`. | ≈ 5 |
| emit | dedup entry, row | every line / valid | One 16 B row, one dedup entry with its ref folded in. Hash the eid once, the person once. | ≈ 40 |

**Can rows that dedup drops skip full decoding? No.** Whether a copy loses is known only after every copy is seen. Copies sit in different files, shuffled. 1.47M rows at 20M (6.8%) lose. The gross ceiling for deferring their payload is 5–12 per line (`unneeded-work.md`). A two-pass scheme (pass 1: eid and ingest; pass 2: winners) re-scans every line, at ≥ 60 per line, to save that. Keep one pass and order the checks cheapest first.

**Clicks** (`click_id,user_id,campaign_id,ts`). Dedup is skipped, which is correct: copies are identical. Order the work: structure, `click_id` non-empty, campaign lookup (direct index, cheap fail), `ts` in the click window, then user pack and link probe. `click_id` matters only as the tie-break at equal `(person, ts)`. Pack it (≈ 20), or keep a source offset and compare bytes only on a tie (saves ≈ 3 per event line, low priority). Floor ≈ 110 per click line, which is **≈ 26 per event line** (0.239 click lines per event line).

**Links.** Both IDs packed, union-find, naming by the smallest ID. Floor ≈ 150 per link line, **≈ 6–8 per event line** (0.041 link lines per event line).

**Sessions.** Per kept row: dropped-copy test (2), person grouping (intern ≈ 15 plus scatter ≈ 8), per-person ts sort (≈ 25 at 29 rows per person, radix for whales), gap scan and day aggregate (≈ 12). Per session, 0.174 per row: credit and window upkeep, about 50, which is ≈ 9 per row. Per click, 0.26 per row: group and sort, about 40, which is ≈ 10 per row. Assists: 10.6 increments per session, which is ≈ 5 per row. Floor **≈ 85 per event line**.

**Output.** 0.104 `user_daily` rows per event line. Unpack the name (≈ 20), five values, plain-encoded column writes: about 50 per output row, which is **≈ 6 per event line**. `campaign_daily` (28K rows) is noise.

**Input bandwidth.** 5.7 GB of CSV at 60M. At about 30 GB/s for the slice, that's ≥ 0.18 s of pure streaming. It overlaps with parse, but it means nothing reaches 0.3 s on the final.

### Floors against what we have

| Phase | Head | Floor | Gap | Tonight's target | Floor on the final (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Events parse | 820 | ≈ 190 | 630 | ≈ 290 | 0.42 |
| Sessions + attribution | 322 | ≈ 85 | 237 | ≈ 190 | 0.19 |
| Clicks parse | 154 | ≈ 30 | 124 | ≈ 50 | 0.07 |
| Written | 112 | ≈ 6 | 106 | ≈ 56 | 0.01 |
| Dedup | 33 | ≈ 15 | 18 | ≈ 33 (cycle fix only) | 0.03 |
| Lookups | 26 | ≈ 8 | 18 | ≈ 26 | 0.02 |
| 8-thread overhead | ≈ 28 | ≈ 15 | 13 | ≈ 28 | 0.03 |
| **Total** | **≈ 1,496** | **≈ 350** | **≈ 1,150** | **≈ 673** | **≈ 0.78** |

Every 100 instructions per line is **0.223 s on the final** (64.15M lines ÷ 28.77 G/s).

## 2. The partition conflict, settled

### The facts

- **The dedup tables are bigger than either note says.** `dedup_part` sizes the table `(2n).next_power_of_two()` with 16 B slots. 20M has n ≈ 84K per eid partition, so a **4 MiB** table. 60M has n ≈ 251K, so an **8 MiB** table. Analyst 2's 1.68 / 5.0 MB left out the 2× load factor. So the table already misses a 1 MiB L2 by 4× **at 20M**, and the 28.77 G/s calibration was taken on a run that paid those misses. The 60M step doubles a table that already misses. It does not move a table from L2 to DRAM.
- **What 60M actually costs on the M5** (Eval v4): total cycles per row are 592 → 598 (+1%). Local wall grows ×2.888 for ×2.983 the lines. **Only dedup is superlinear**: 45.7 → 67.8 cycles per row, IPC 0.79 → 0.52, +0.043 s of 1.32 s. Sessions is +4%, lookups +3%.
- **Sol's adaptive global partitions** won exactly that dedup back (−38 ms, −22% dedup cycles). They paid for it everywhere else: +22 instructions and +26 cycles per line, +0.5 GB, Linux 60M +8.2%. The mechanism is fan-out. Each parse task writes 3 × nb streams (`e`, `rf`, `r`). At nb = 1,024–2,048 that's 3–6K live write streams per thread, against 512 L1D lines and 64 L1 DTLB entries on Cascade Lake. This is the textbook radix-partitioning limit. It will be at least as bad on the scorer.
- **Analyst 2's +0.3–0.6 s at 60M** is a model built on the undersized tables. It adds a cliff on top of a calibration that already prices L2 misses. My model for the scorer: dedup at 60M is DRAM-latency-bound with about 3 probes in flight per hyperthread, so 64.15M × ~90 ns / 24 ≈ **0.24 s**, against **0.08 s** priced by instructions. An L2-resident dedup at ≈ 25 instructions is ≈ 0.06 s. **Recoverable: ≈ 0.1–0.2 s on the final, planning 0.15 s.** Sessions might add a few tens of ms at 60M, from the 1.8 MB scatter target per partition. Lookups are prefetched and flat.

### Verdict and the fix

**Both are half right. Raise the table locality, not the partition count.** Keep 256 parse-time partitions. Add a second, local level inside `dedup_part`:

1. Stream the partition's `EidEnt`/`rf` entries once, **stably**, into 2^k sub-buckets by the next hash bits (bits below the 8 that chose the partition). Carry `(eid, ingest, t, i)`, so the drop encoding is unchanged. Fan-out 4–16 is trivially L1- and TLB-friendly.
2. Choose k so each sub-table is ≤ 512 KiB, leaving L2 room for the streaming input and the other hyperthread. With Sol's compact 8 B slots (key fingerprint and index) at load ≤ 0.5, n ≤ 32K per sub-bucket. That gives **k = 2 at 20M and k = 3 at 60M**, computed from n at run time. With 16 B slots, add one to k.
3. Probe each sub-bucket's table. Keep "first copy wins on equal ingest". Equal-ingest copies are identical by the spec, but stable order keeps the output deterministic.

Expected: about +5–8 instructions per line for the extra streaming pass, and −0.1–0.2 s of scorer time on the final. Locally about −30 to −40 ms on native 60M, close to Sol's measured −38 ms, without the +26 cycles per line elsewhere.

**Correctness trap:** "subdivide dedup inside each person partition" cannot be literal. For about 1 in 64 duplicated events, the later copies name a different user, so a different person, often in a different partition. That is about 9K events at 20M. Dedup by person partition would mismatch seed-42. The subdivision goes inside the **eid** partitions.

**Gate for this move:** Linux arm64 60M wall must improve by more than 2× the pooled stdev against the same head. Native 60M must not regress. Instructions per line may rise by at most +8. The dedup phase alone is not the gate. That is exactly what made the global version look good.

## 3. Explorer 2's ceiling, and the fused per-column decoder

### Why 300 is a real floor for the current shape

Classify (31) + bit walk (63) + seven slices (51) + quote strip (≈ 150) is what you pay to turn a line into generic `&[u8]` fields. Then each consumer re-reads its slice to pack, parse or compare it. The bit walk and the slices exist only to tell the consumers where each field is. The quote strip exists only because the slice is built before anyone knows what the field should contain.

### The design: each column decoder finds its own end

Parse the line left to right, one known column at a time. Each decoder reads its field from position `p`, decodes the value, and **proves where the field ends** by checking the terminator right after the value. The terminator is `,`, or `\n` for the last column. A quoted field is wrapped in `"`. Field ends fall out of decoding, so there's **no classify pass, no mask stream, no bit walk, and no slice array**. Line `n+1` starts right after line `n`'s `\n`, which the last column's decoder found.

**Quotes, branch-free.** At each field start, `q = (b[p] == '"') as usize; s = p + q`. After the value ends at `e`, the field is valid iff `b[e] == '"'` exactly when `q == 1`, and then `b[e + q] == ','` (or `\n`). An empty field is `e == s`. That covers both `,,` and `"",`. A `"` inside a value can never pass: every decoder's accepted alphabet excludes `"` and `,`, so the value stops there and the terminator check fails. There is no per-line quote mask. With 20% of fields quoted at random, any per-field *branch* on `q` mispredicts often, so keep `q` arithmetic.

**Column primitives**, shared by events, clicks and links:

| Primitive | Used by | Fast path | Floor |
| --- | --- | --- | ---: |
| `id_field` | event_id, user_id, click_id, link sides | One 16 B load. The symbol class mask (Method's `pshufb`/`tbl` nibble tables) gives the run length by `tzcnt` of non-symbols. Pack from the same registers. Then the terminator check. Length 0 means empty. Length > 10, or a non-symbol before the terminator, goes to the fallback. | ≈ 20 |
| `ts_field` | events `ts`, clicks `ts` | Dispatch on byte 4: `-` means F1/F2, a digit means F3. F1/F2: one 16 B template compare (digits and `-`, `T`, `:`), the date from a window-day table (Sol's decoder), clock digits by pairs, then `Z` (20 bytes) or `±HH:MM` (25 bytes). F3: the digit-run length by `tzcnt`, with 13–16 digits decoded in 128-bit lanes. Any template miss calls the **existing exact `parse_ts`** on the bounds found by `skip_field`. | ≈ 25 |
| `f1_trusted` | `ingest_ts` | 20 fixed bytes, with a cheap template check. A miss uses the existing scalar `parse_ts(...).unwrap_or(i64::MAX)`, the same as today. | ≈ 12 |
| `enum_field` | event_type | One 8 B load and length check against `view`, `cart`, `purchase`. Anything else is an invalid type, and the field still gets `skip_field`. | ≈ 5 |
| `skip_field` | product (view/cart), price (view/cart), and any field after the line turned invalid | Find the first of `,` `"` `\n` in 16 B steps. A `"` is allowed only at the start (then expect `"` plus terminator) and at the end. Report empty / non-empty. | ≈ 6 |
| `digits_field` | price (purchases) | Digit-run length plus a ≤ 8-digit decode, value 1..=10,000,000. Anything else is a bad price. | ≈ 10 |
| `cat_field` | product (purchases) | Today's `IdIndex` direct path. | ≈ 30 × 3% |

**Line flow, events.** `id_field` (eid; empty means skip to `\n` and drop), `id_field` (user, empty means invalid), `ts_field`, `f1_trusted`, `enum_field`, then product and price by type, and finally `\n` must follow. Decode speculatively and **commit only once `\n` is at field 7.** A line with a missing field puts, say, `event_type` where `ingest_ts` belongs. That decodes to garbage, fails a later terminator check, and is never committed. Once a line is invalid but well-formed, switch the remaining columns to `skip_field`: it still needs its dedup entry, but not `ts`, the user pack, or the price.

**The fallback is the current engine, unchanged.** Any deviation from the fast shapes hands the line, from its start, to today's `for_each_record` + `split_fields` + `parse_event`. Deviations include an over-long or non-packable ID, an unusual field length, a template miss that `parse_ts` can't settle from the bounds, a field ≥ 16 bytes where a short one is expected, or `\r`. The fast path is only allowed to agree with the slow path. It never decides anything new. Expect a fallback rate around 0.1–0.5% of lines (malformed 0.05%, bad timestamps 0.3–0.7% partly, odd IDs).

**Over-reads.** The 16 B loads can run up to 15 bytes past a field. Send each file's last 64 bytes, and any line that starts inside them, to the fallback path. Or copy that tail into a padded buffer. Never load past the mmap.

**Interface (the contract with Method).** The decoder emits a decoded record and nothing about buckets:
`EvRec { eid: u64, ingest: i64, valid: bool, user: u64, ts: i64, price: u32, cat: u32 }`, and the same idea for clicks (`ClkRec { cid, user, camp, ts }`, valid only).
Method's probe + emit (§4 row 2) consumes `EvRec` behind today's scanner first. Then the decoder swaps in as the producer with no merge conflict in `EvOut`/`flush`.

**Tests, before any timing:**
- Differential: the fast decoder against `split_fields` + `parse_event` on Method's G1 generator (1.2M random lines). Add a mutation fuzzer that, per line, inserts or deletes one `"`, `,` or `\r`, quotes or unquotes a field, empties a field, or truncates the line. Compare the accept/reject verdict and every decoded value.
- Then fixtures 36/36, dev MATCH, seed-42, the fuzz suite under `SESSIONS_DEBUG_NO_FAST=0/1/2/3`, and `cases_ts.py`.
- Run it on both NEON and the SSSE3 x86 path (amd64 container, `X86_CPU=x86-64-v2`).

**Acceptance:** events parse ≤ 450 per line (Orchestrator's target) as the first commit. **≤ 300 tonight** with Method's emit. Front-end floor ≈ 150.

**ISA note (corrects Analyst 2's licence table).** On Skylake-SP and Cascade Lake, the frequency licences are:
- **Licence 0:** scalar, all 128-bit SSE/AVX, and **light 256-bit AVX2**: integer compares, shuffles, `vpmovmskb`, adds.
- **Licence 1:** 256-bit *heavy* (FP, integer multiply including `vpmaddubsw`/`vpmaddwd`) and 512-bit light.
- **Licence 2:** 512-bit heavy.

So the decoder may use ymm compares and shuffles freely. Keep the `pmaddubsw`/`pmaddwd` digit and pack math at **128-bit**, and use no zmm. Eval's cascadelake disassembly should list any ymm/zmm `vpmul*`/`vpmadd*` and any zmm use in the hot functions, not only 512-bit opcodes.

### 3a. Addendum (01:00 ET): `explore/gemini-fused` @ `2e22d43` did not test this design

`2e22d43` measured 1,243 per line against 824. It is a **scalar splitter followed by the old decoders**, not a per-column decoder:

- `memchr` for `\n` on every line, then `take_col` walks **every byte** in a scalar loop (`c == ','`, `q += c == '"'`, `j += 1`). That is ~4–5 instructions per byte over ~75 bytes, ≈ 350 per line, replacing the 31-instruction SIMD classify.
- The slices it returns are then decoded by the **same** functions as before. `ids.key` → `pack_fast` reloads and re-classifies the bytes with a known length. `parse_ts` re-dispatches on slice length. `parse_price` and the type match are unchanged. End-finding and decoding stay two separate passes, so nothing is fused.
- So 1,243 ≈ 824 − 295 (old scan) + ≈ 710 (scalar walk and `memchr`). The result is right for what was built.

**The rule that makes it a per-column decoder:** no byte loop and no `memchr`. Each field is **one 16-byte SIMD load at the field start**. The decoder's own class mask gives the field length (`tzcnt` of the first byte outside the column's alphabet). The value is decoded from the same register, and the terminator is a single byte compare at `s + len (+q)`. Fixed-width formats (F1 20 B, F2 25 B, `view`, `cart`, `purchase`) check the terminator at a fixed offset and never search for it.

#### Spec for Explorer 2 (events; x86 SSSE3 instruction budgets per line, NEON about +2 per field for movemask)

Setup per line: `p` = line start. **Guard once per line:** if `p + 192 > map_end`, use the fallback for this line, so no per-field page checks (unlike `pack_fast`). `q(p)` = `(b[p] == '"') as usize` (3 instr). `term(e, q)`: `b[e] == '"'` iff `q`, and `b[e + q] == ','`, done branch-free into an `ok &=` accumulator (≈ 5 instr). Every field ends with `p = e + q + 1`.

| Column | What it does | Budget |
| --- | --- | ---: |
| `event_id` | `q`; `v = loadu(p+q)`; class bits = `pshufb(PK_LO, v & 15) & pshufb(PK_HI, v >> 4)` (the packer's tables); `bad = movemask(cmpeq(cls, 0))`; `len = tzcnt(bad \| 1<<10)`; `len == 0` means empty eid (drop the line, `memchr` to `\n`, which is rare); `len == 10` with a symbol at byte 10 means over-long → fallback; `live = cmpgt(len, IDX)`; then `pack_simd`'s code, merge and place unchanged; `term` | 38 |
| `user_id` | same as `event_id`; empty means invalid, and the rest of the line goes to skip mode | 38 |
| `ts` | `q`; `v0 = loadu(s)`. F1/F2 iff `b[s+4] == '-'`: a template compare of `v0` (digit mask by range, `-` `-` `T` `:` `:` at fixed lanes) plus `b[s+19]`. `Z` means len 20; `+`/`-` means a 6-byte offset check and len 25. Then the existing window-day and clock decode (Sol's paired decoder when merged). Otherwise F3: digit mask, `len = tzcnt(non-digit)`, len ≤ 16 decoded in lanes; longer goes to the fallback. A template miss runs `w.parse_ts` on the bounds `[s, s+len)`, which `skip_field` finds. `term` | 56 (≈ 85 with today's decoder) |
| `ingest_ts` | `q`; fixed 20 bytes: a cheap template check (digit range plus 5 separators plus `Z`); decode with no `Option` plumbing; a miss runs `parse_ts(...).unwrap_or(i64::MAX)` as today; `term` at `s+20` | 30 |
| `event_type` | `q`; 8-byte load; `view`/`cart` mean a 4-byte compare and terminator at `+4`; `purchase` means an 8-byte compare and `+8`; anything else is an invalid type, so `skip_field` and skip mode | 8 |
| `product_id` | view/cart: `skip_field`. Purchase: the same `id_field` length logic, then `lk.category` on `[s, s+len)` | 13 (+30 × 3%) |
| `price_cents` | view/cart: `skip_field` with the terminator `\n`. Purchase: digit mask, `len`, ≤ 8 digits, 1..=10,000,000 | 13 (+15 × 3%) |
| line end and commit | `ok` must be set and `b[p-1] == '\n'`; else `fallback(line)`. Commit: `push_valid`/`push_invalid` as today (Method's emit) | 6 |
| **Front end** | | **≈ 200** (≈ 290 with today's ts/ingest decoder) |

`skip_field(p)` is used for product and price on view/cart, and for every field after the line turns invalid. One 16 B load, `m = movemask(cmpeq ',' | cmpeq '"' | cmpeq '\n')`, `e = tzcnt(m)`. A `"` is allowed only at lane 0 (then rescan from 1 and require `"` plus the terminator). `m == 0` (a field of 16 B or more) goes to the fallback. About 12 instructions.

**Fallback:** the line, from its start, goes through `split_fields` + `parse_event`, exactly as today. Its rate must stay under 1%. Count it with `SESSIONS_DEBUG_STATS`.

**Test before timing:** the `fused_columns_match_split_fields` generator in `2e22d43`, but comparing the **decoded** `(eid, ingest, valid, user, ts, price, cat)` against `split_fields` + `parse_event`. Add the real-line mutations from §3 and the over-read guard at file tails.

**Go/no-go:** events parse ≤ 600 per line at 20M (NCPU=1, minimum of 3, fresh build) with fixtures, dev and seed-42 MATCH **by 06:00 ET**. If it misses, drop it.

#### Against the quote-mask route

| Route | Events parse (front end) | Clicks and links | Final s vs head | Risk |
| --- | ---: | --- | ---: | --- |
| Quote mask (classify + bit walk + prefix-xor validation + branch-free strip, slices kept) | 585 → ≈ 465 | also helped: the same `for_each_record`, ≈ −15 per line | **≈ −0.30** | low; Explorer 2 is on it now |
| Per-column (this spec) | 585 → ≈ 290 (≈ 200 with Sol's ts) | events only; clicks are a later port | **≈ −0.65 to −0.85** | medium; the fallback contains it |

The per-column decoder replaces about 295 of structure work with about 85 (seven quote and terminator checks plus two `skip_field`s), and it gets field lengths for free from the decoders. The quote-mask route keeps the ≈ 145 of classify, bit walk and slices.

## 4. Ranked moves in final-board seconds, with owners

Seconds are for the 60M final at 0.223 s per 100 instructions per line. "Tonight" is the realistic landing. Floor seconds are in §1. Every explorer **branches from `method/v5` and delivers a mergeable commit with its gates run**, not a recipe. With about 10 hours left, Method merges and does not re-implement.

| Rank | Move | Owner | Instr/line now → tonight | Final s | Hours | Risk |
| --- | --- | --- | --- | ---: | ---: | --- |
| 1a | **Quote-mask scan** (Explorer 2's current work; §3a): a commit by **02:30** or drop it | **Explorer 2** → Method | front end 585 → ≈ 465, clicks and links −15 | **−0.30** | 1.5 | low |
| 1b | **Per-column event decoder** (§3a spec), with Sol's decoder for `ts`/`ingest` when it lands. Go/no-go at **06:00** | **Explorer 2** after 1a; Method merges | ≈ 465 → ≈ 290 (≈ 200 with Sol's ts) | **−0.40 to −0.55** more | 3 | medium, contained by the fallback |
| 2 | **Probe + emit against `EvRec`**: no 56 B `PendEv` copy, the ref folded into the dedup entry, hash eid and person once, pushes without capacity checks | **Method** (in progress) | ≈ 235 → 90 | **−0.32** | 2–3 | low–medium |
| 3 | **Clicks through the per-column primitives**: only after 1b lands, otherwise 1a's share (−15) is all clicks get tonight | Explorer 2 → Method | clicks ≈ 140 → ≈ 60 | **−0.18** | 1 after 1b | medium; likely past the freeze |
| 4 | **Dedup sub-buckets inside eid partitions** (§2) | **Sol** (prototyping) | 33 → ≈ 38; cycles | **−0.10 to −0.20** (plan −0.15) | 2–3 | low–medium |
| 5 | **Click sort**: group clicks by the partition's person index (counting sort, as for events), then sort a u64 `ts_off << 32 \| index` per person. Re-sort only the rare equal-ts groups (boundary pairs and duplicate copies) by the exact `ids.cmp`, descending. Keep today's comparator when `wide`. | **Explorer 3** (switch now; the event sort is only 44) | 89 → 20 | **−0.15** | 1–2 | low |
| 6 | **Person grouping**: intern + count + scatter + run sort, 145 → 80. One `(loc, ts_off)` key, an intern table sized to the partition. Run-aware sort is unlikely to pay, because rows are shuffled across files, so per-person input order is random. Measure that in five minutes and drop it if so. | **Explorer 3** after #5 | 145 → 80 | **−0.145** | 2–3 | medium |
| 7 | **Writer settings** (measured): dictionary only on `top_category`/`channel`, statistics off | **Method** commits; **Eval** A/B on Linux 20M and 60M (bytes written rise 21 → 88 MB at 20M) | 112 → 56 | **−0.13** instr, ≈ −0.10 net | 0.25 | low |
| 8 | Walk: session setup, the day flush that zeros 20 categories every user-day, the credit write | Explorer 3, only if 5 and 6 are in | 84 → 50 | −0.08 | 2 | medium |
| 9 | Hand-rolled Parquet writer (plain encoding, no Arrow) | Explorer 3, not tonight unless everything above is in | 56 → 6 | −0.11 | 3–4 | medium–high (format) |
| 10 | 60M calibration and gates: v4's practice score as a second calibration point, v5-pre practice submissions, Linux 60M A/B for #4 and #7, disassembly for ymm/zmm multiplies | **Eval** | — | — | ongoing | — |

**Rows 1–7 together (revised after `2e22d43`):**

| Case | Per line | Final |
| --- | ---: | ---: |
| 1a only, no 1b or 3 | ≈ 1,020 | **≈ 2.4 s** |
| 1a and 1b | ≈ 840 | **≈ 2.0 s** |
| 1a, 1b with Sol's ts, and 3 | ≈ 680 | **≈ 1.55 s** |

The 01:00 estimate was ≈ 673 per line and ≈ 1.5 s. The floor is still ≈ 0.78 s.

**Don't do tonight:**
- Global adaptive partitions (§2).
- A 512-bit classifier.
- Skew scheduling: −4% at 20M, +0.6% at 60M on Linux.
- Deferred decoding of dedup losers (§1).
- The clean-room rewrite (below).

### Execution order and cutoffs (ET, Sunday)

| When | What |
| --- | --- |
| now → 00:45 | Eval A/B of #7 on Linux. Method commits #7 if it holds. Explorer 3 starts #5. Explorer 2 starts #1. Sol continues #4. Method continues #2. |
| ≈ 02:30 | **v5-pre1** = packer + #7 + #2 + #5 (≈ 1,250 per line). Eval quick profile, then a **practice submission** for a second board calibration point. |
| ≈ 05:00 | #1 merged. Then #4 if its Linux gate passes. **v5-pre2** practice submission. |
| ≈ 07:00 | #3 merged. #6 if gated. |
| **08:00** | **Feature freeze.** Eval full eval on the v5 candidate, including 60M Linux. |
| 09:30 | Practice board check of the candidate. |
| 10:30 | Final choice: v5 if SUBMIT-READY, else the best SUBMIT-READY pre, else v4. **Deadline 11:00.** |

A move that misses its gates by its slot is dropped, not rushed. v4 stays the safe answer.

### The clean-room rewrite: no

- **What it would be:** one fused pass from decoder to emit, a dedup and session kernel designed together, and a hand-written writer. That's about 1,800–2,500 lines. Getting to MATCH on fixtures, dev, seeds and fuzz takes **10–14 agent-hours**, plus about 2 hours of Eval gates. That doesn't fit before 11:00.
- **What it buys over modular replacement:** the intermediate copies go away (`PendEv`, the separate `rf` stream, process_part's two passes over the rows, drop routing). That's about 50–120 per line, **≈ 0.1–0.25 s** on the final.
- **Where the architecture actually blocks the floor:** only in parse, where generic slices are the cost (§3). Everywhere else the gap is in specific kernels (click sort, intern, walk, Arrow encoders) that can be replaced in place.

So the decoder is the rewrite, done as a strangler with the old path as its fallback. Revisit a full rewrite only after the hackathon.

## 5. Corrections to earlier notes

1. **Event sort ≈ 310 per kept row** (log, Explorer 3) is v3. In v4 it is **49**. The click sort (**98 per kept row, 377 per click**) and the walk (92) are the session costs now.
2. **Dedup tables are 4 MiB at 20M and 8 MiB at 60M**, not 1.68 and 5.0 MB (Analyst 2 omitted the 2× load factor). The 20M calibration already includes their L2 misses. The 60M cliff is **≈ 0.15 s**, not 0.3–0.6 s plus 6%.
3. **AVX2 light ops do not lower the clock** on Cascade Lake. 256-bit integer multiply-add and 512-bit ops do. (Analyst 2's table put all AVX2 in licence 1.)
4. **"Dedup inside each person partition"** would be wrong: cross-user duplicate copies (1 in 64). Subdivide the eid partitions.
5. **Single-run instruction counts under load can be +90 per line off.** Take the minimum of 3 or more, with each binary built from its own `git archive` in a fresh target directory and the sha256 recorded.

## 6. Reproduce

```sh
A=$PWD   # an `analysis` checkout
mkdir /tmp/head && git archive 20b8e79 | tar -x -C /tmp/head && cd /tmp/head
patch -p1 < $A/evals/insights/v5_plan/subphase-counters.patch   # or writer-settings.patch
CARGO_TARGET_DIR=/tmp/tgt cargo build --release
DATA_DIR=data/seed-42 OUTPUT_DIR=/tmp/o SCRATCH_DIR=/tmp/s NCPU=1 SUBDUMP=1 /tmp/tgt/release/sessions
```

`SUBDUMP=1` prints the six sub-phase instruction totals and the row, kept, click and person counts at exit. The writer patch was checked with `scripts/run_fixtures.py` (36/36) and `scripts/compare.py` against `data/dev-answer` and `data/expected/seed-42` (MATCH both).
