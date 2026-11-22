# Candidate checks

Analyst 2, 2026-11-21. Each item is recorded as it was finished. Explorer 2 and Explorer 3 had not committed past the packer when this was written.

## 1. Sol's paired timestamps, `75f9993`

`explore/fast-timestamps-v4` @ `75f9993`, parent `20b8e79`. Sol: seed-43 events parse 820 → 731 per line, whole process 1,480 → 1,386.

Both binaries were compiled from `git archive` of that commit. The packer binary is the one already hashed in `packer-cliff.md` (`b7664eb1…`). The timestamp binary is `6c82a35d…`, and its `sessions.d` names `75f9993/src/main.rs`. Counts are the in-process lap (`instr=` on the stderr mark, added in `20b8e79`), divided by seed-43's 64,150,261 event lines, `NCPU=8`, after a discarded warmup so the input was resident. A busy machine moves these totals by tens of instructions per line, so the pair below is the quiet back-to-back run.

| | Events parse | Whole process |
| --- | ---: | ---: |
| `20b8e79` | 822 | 1,485 |
| `75f9993`, run 1 | 732 | 1,388 |
| `75f9993`, run 2 | 731 | 1,388 |
| Sol | 820 → 731 | 1,480 → 1,386 |
| Measured step | **−90** | **−97** |

The claim holds. The new binary matches Sol to the instruction on events parse and to 2 per line on the total. The baseline sits 2 and 5 above Sol's, which is the same warm-run noise as the packer check. Clicks also drop, 153 → 147 per event line, because a click has a timestamp too. Dedup, sessions, and Parquet stay put (36, 328, 117). The saving is in the decoders, not in a layout change.

Predicted board, same rate as `verification.md`: 1,388 per line is **1.04 s** at 20M-equivalent scaling of the instruction rate, and **3.10 s** at 60M if nothing else cliffs. That is `1,388 × 64.150e6 / 28.77e9`. The 20M practice set was not re-counted for this commit.

## 2. How v4 dedups, and whether subdividing it is legal

On `20b8e79` the dedup key is the packed `event_id`, not the person.

`parse_event` sends every parsed event, valid or not, to

```
q = bucket(mix(eid), nb)
```

`mix` is splitmix64. `bucket` is the high multiply into `0..nb` (256 unless `SESSIONS_DEBUG_PARTS` says otherwise). The row, if the line validated, goes to a different bucket, `bucket(mix(person), nb)`. An invalid line still appends an `EidEnt` and a ref of `INVALID`, so a bad copy can still win the id. `dedup_part` then builds one open-addressing table per eid bucket, keyed by `eid`. A strictly smaller `ingest` replaces the resident copy. An equal `ingest` leaves the first copy. The loser is dropped only if it had produced a row. Two copies with different users meet whenever they share an `event_id`, because the route does not look at the user.

That is the cross-user rule. `docs/rules.md` dedups before validation, keeps the smallest `ingest_ts`, and about 1 in 64 duplicates name a different user. Partitioning by person would keep both.

`explore/dedup-subdivide` @ `6da0cd2` (parent `20b8e79`) does not change that route. For a bucket of at least 131,072 entries, and only when the hash mask is the production `u64::MAX`, it splits the bucket into children by `(mix(eid) >> 24)` modulo a power of two. The same id has the same mix, so both users still land in the same child. The comparison is still a strictly smaller `ingest`. An equal ingest keeps the earlier copy. A child that is still over 32,768 entries is sorted by id and original position and reduced the same way, which is the one path that can change which of two equal-ingest copies survives. The spec says those copies are identical, so the output does not change. Narrow debug masks, small buckets, and a task/row index that does not fit in 32 bits all fall back to the flat table. A unit test checks the drops against that table.

Legal, for the cross-user rule. It is a second hash split of the event-id bucket so the table can fit in cache. It is not dedup-by-person. Not timed here. One performance note, not a correctness one: the outer bucket already consumes the high bits of `mix(eid)`, and the child index uses bits 24 and up, so the children can be uneven.

## 3. Explorer 2 and Explorer 3

`explore/gemini-fused` and `explore/gemini3-sort` both still point at `20b8e79`. Neither has a commit to check against the field rules, equal-timestamp order, or byte-wise ids. Nothing to accept or reject until one lands.
