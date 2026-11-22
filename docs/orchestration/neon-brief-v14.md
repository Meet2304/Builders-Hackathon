# Brief for Gemini Neon: plan the version after v13 (v14)

Repo: https://github.com/Meet2304/Builders-Hackathon (public). Key files:
- `docs/rules.md` — the full spec (inputs, dedup/validation/sessionization/attribution rules, outputs). Always wins.
- `src/main.rs`, `src/event_columns.rs`, `src/columns.rs`, `src/links.rs` — the Rust engine (current release v10.1 = tag `v10.1`, commit `3c3c653`, src identical to `be41e2e`).
- `docs/orchestration/LOG.md` — the full run log: every version, measurement, and dead end.
- `evals/` — eval framework (`evals/run.py`), results (`evals/results/*.json|md` on branch `eval/framework`), explorer notes (`evals/explore/*.md`), x86 counts (`evals/insights3/` on branch `analysis3`).
- `reference/reference.py` — the Python oracle (exact expected output).

## The task and scoring
- Process event/click/link CSVs (20M events practice board, **60M final**) into two Parquet tables. Output must be exactly right or there is no score.
- Score = container wall-clock on **8 vCPU Intel Cascade Lake (x86), 24 GB, no network**, read-only fs; runtime behaves like **gVisor**.
- Deadline 11:00 ET today; we need candidates gated by ~09:30.

## Board history (20M practice board, seconds)
| version | what changed | x86 instr / event line (NCPU=1 callgrind) | board |
|---|---|---:|---:|
| v4 a019739 | SIMD fast path, counting sort | 1,986 | 2.198 |
| v5 5b7bcc2 | SIMD ID packer, paired timestamps | 1,680 | 2.146 |
| v7b 96af24b | lock-free 33-byte long-ID table (killed 58k futex calls), mimalloc no-purge + `_exit` | 1,577 | 1.5275 |
| v8 2bfb034 | per-column SIMD decoders for events/clicks/links | 1,316 | **1.0844** (best) |
| v10.1 be41e2e | parallel links union-find, one write per Parquet file, 24 B click rows, 8 MiB rayon stack | 1,316 | 1.0852 |

Leaders are at ~0.45 s. We are rank ~86.

## What we learnt (important)
1. **The board tracks x86 retired instructions per row** (fit R² 0.87–0.91, ≈ 1.8–2.6 ms of board per 1 instr/event line), **plus 8-thread lock contention** (v5 was +0.35–0.49 s above its instruction prediction because of futex contention on a mutex interner; removing it gave v7b −29%).
2. **Page-fault / syscall / RSS reductions do NOT move the board**, even though our local gVisor harness rewarded them (v10.1 was +5.5% in local gVisor, 0% on board; v11/v11a/v11b/v12 all failed).
3. The data generator (changed mid-contest) makes **1 in 8 IDs a 33-byte `[uec]` + 32 lowercase hex** string; the rest short base-36. IDs are opaque byte strings; ordering must be byte-exact (smallest click id wins ties, smallest ID names a person).
4. Correctness traps we hit: dedup must be global on event_id (≈1 in 64 duplicates name a different user), dedup happens **before** validation, an invalid earliest copy suppresses later valid copies; lock-free table races (two keys for one ID); a 256 KiB rayon stack overflowed nondeterministically.
5. Things that were slower: pread instead of mmap; fused scalar cursor decoders (lost the SIMD classify); 16 B LongTable; 4 B dedup offsets with re-scan.

## Where x86 instructions go now (v10.1, per event line, total 1,316)
| phase | Ir/line |
|---|---:|
| events parse (decode, ID pack/long-ID table, timestamps, row emit, partition push, dedup insert) | **585** |
| sessions + attribution (per-person sort, session walk, click-window attribution, day credits) | 279 |
| Parquet write (arrow/parquet encoding, dictionaries, statistics) | 187 |
| clicks parse | 108 |
| dedup | 107 |
| lookups (links/products/campaigns) | 22 |

In flight now (v13): Sol is cutting the events phase; Explorer 4 is cutting sessions + write. v14 should be **beyond** those.

## What we want from you (high reasoning)
A concrete **plan for v14**: the 2–3 changes most likely to cut **x86 instructions per row by ≥ 10%** (or remove remaining cross-thread contention) while staying exactly correct, ranked by expected board gain per hour of work. For each: the mechanism, the expected Ir/line saving with reasoning, exactness risks and how to test them, and an implementation sketch specific enough for a Rust engineer (functions/structures to change). Also: are there architectural shortcuts the leaders (~0.45 s) likely use that we are missing — e.g. skipping work for rows that can't affect output, fewer passes over data, cheaper Parquet writing (uncompressed and dictionary-free output is legal but made files 4× larger), or a different sessionization/attribution formulation?
