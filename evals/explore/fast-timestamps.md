# Timestamp decoding on v4

The paired decoder is `0cb55ae` on `explore/fast-timestamps-pair`. The same change is ready to cherry-pick as `75f9993` on `explore/fast-timestamps-v4`, based on Method's SIMD packer at `20b8e79`.

The dedicated ingest decoder uses the spec's valid-F1 guarantee. For a same-day F1 event, the pair shares a midnight lookup and decodes both clocks with ASCII-pair tables. The event clock still checks every digit, separator and range. Other event and click timestamps use the checked hour and numeric-prefix caches or the scalar parser. Invalid results return `i64::MAX`, which the half-open window check rejects.

## Correctness

The SIMD-packer port passed 50/50 timestamp review comparisons (five datasets across ten settings), 36/36 fixtures, published dev MATCH, and 150/150 framework fuzz cases. The review covers leap days and year changes, invalid clock and offset fields, wide windows, and ingest dates outside the cache.

## Stagebench

The harness uses the Analyst's 200 MB seed-42 sample and subtracts mode 7 from mode 8. The costs below cover both timestamps per parsed record.

| Decoder | Instructions/record | Cycles/record |
| --- | ---: | ---: |
| v4 before the paired change | 152.32 | 26.12 |
| Dedicated ingest and sentinel | 102.12 | 20.26 |
| Hour cache and numeric prefix | 86.02 | 18.96 |
| Paired, table pointer as shipped | 74.38 | 16.36 |

The paired decoder reduces instruction cost by 51%. It misses the original 60-instruction target by 14.38 instructions per record.

[Mode samples and separate clock ablations](../results/fast-timestamps-stage.json)

## Whole events-parse phase against the SIMD packer

Separate clean release targets for baseline `20b8e79` and paired decoder `75f9993`. The native per-phase probe counts all eight workers and divides by the number of event input lines, including duplicate and invalid records.

| Input | Event lines | Events-parse instructions/line | Events-parse cycles/line | Whole-process instructions/line |
| --- | ---: | ---: | ---: | ---: |
| Seed-42 (20M, warm) | 21,507,843 | 824.67 → 733.32 | 305.35 → 284.72 | 1,516.65 → 1,411.73 |
| Seed-43 (60M) | 64,150,261 | 820.31 → 730.82 | 288.60 → 279.69 | 1,480.05 → 1,385.56 |

Events parse saves 91.35 instructions per input line at 20M (11.1%) and 89.49 at 60M (10.9%). Both binaries match the cached 20M oracle and 60M consistency hashes. The native counter samples took 0.555 → 0.473 s at 20M and 1.435 → 1.439 s at 60M. An initial cold-baseline 20M probe overstated the savings. The warm comparison uses a fresh build, binary SHA-256 and a warmup for each revision.

[Whole-process and phase counters](../results/timestamps-v4.json)

## Port into v5

Cherry-pick `75f9993` onto `method/v5` after the SIMD packer. Method applied the change at `2cbdb2b`. For changes to the event loop, carry over the decoder tables, `Win::parse_pair` and the timestamp review assertions. Compute `(ts, ingest)` once per eligible event and pass both to `validate`. Keep ingest on invalid-event dedup entries so the earliest copy can still suppress a later valid copy. Use the sentinel-aware single decoder for clicks and retain the scalar debug path. Re-run the timestamp review on the combined branch.
