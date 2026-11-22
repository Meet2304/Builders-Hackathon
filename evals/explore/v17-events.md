# v17 events-phase micro-cuts (x86 callgrind)

Method: `evals/insights3/build.sh` + `count.sh` from branch `analysis3`. linux/amd64, `target-cpu=x86-64-v2`, NCPU=1, `data/dev` (1,071,894 event lines). The events phase is dump `.3`. Per-instruction costs came from `--dump-instr=yes` joined with `objdump -l`.

| commit | change | events Ir | /event line | total Ir |
|---|---|---:|---:|---:|
| `d5e9ee3` v16 | base | 528.95M | 493.5 | 978.25M |
| `9a489c7` | short-ID path skips `FieldId::is_empty` re-tests; `ingest <= ts + DAY_MS` instead of `saturating_sub` | 525.52M | 490.3 | 974.83M |
| `5054f57` | line tail generic over `SHORT`, emit from the decoder (closure got outlined: **regression**) | 545.08M | 508.5 | 994.38M |
| `6960fba` | `EvSink` trait, always inlined, replaces the closure | 506.23M | 472.3 | 955.54M |
| `16364f7` | test `view`/`cart` before `purchase` (57% / 7% / 2% of lines) | 501.99M | 468.3 | 951.28M |
| `70d21b6` | `other_id_pair` `#[inline(always)]` (34% of lines take it) | 494.65M | 461.5 | 943.95M |
| **`53ce778`** | long IDs: `hex32::digits` validates and parses once in `Column::id`; the key reuses the value (`Ids::pack_long_parsed`) | **477.17M** | **445.2** | **926.47M** |

The net result is events −9.8% (−48 Ir per line) and total −5.3%. The clicks, sessions and write phases are unchanged.

## Tried and dropped (x86 Ir got worse)

| change | events Ir |
|---|---:|
| drop `#[cold]` on `other_id_pair` / `other_timestamps` | +0.9M |
| inline `other_timestamps` | +3.3M |
| inline `EvOut::flush` | +11M |
| inline `pack_long_parsed` | +2.2M |

## Where the rest goes (`53ce778`, Ir per event line)

- Main loop: 332. The largest single source line is `terminate`, about 29, at about 7 instructions per field delimiter.
- `EvOut::flush`: 61. That's about 55 instructions per row: the link probe, two bucket reductions, two `Vec` pushes, and spills.
- `other_timestamps`: 23.
- `pack_long_parsed`: 13.

## Gates (`53ce778`)

- fixtures 36/36
- `data/dev` MATCH under `SESSIONS_DEBUG_NO_FAST` 0–3
- seed-42 MATCH
- long-ID 240/240 (arm64)
- long-ID on the x86-64-v2 binary through docker: 240/240 (40 seeds × 6 knobs)
- x86 seed-42 MATCH
- amd64 (x86-64-v2) container dev MATCH
- x86 callgrind output MATCH
