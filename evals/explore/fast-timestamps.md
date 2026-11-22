# Timestamp decoding on v4

Base `method/v4` at `a019739`. The production prototype is on `explore/fast-timestamps`.

The dedicated ingest decoder trusts the valid F1 clock promised by the input contract and routes calendar misses to the scalar parser. The event and click decoder returns an out-of-window sentinel and checks exact date and clock syntax, offsets, and digit ranges. The hourly prototype precomputes calendar-hour and numeric-prefix contributions and uses ASCII-pair lookups for the remaining clock fields.

## Correctness

The hourly prototype at `bc79f76` passed all 50 timestamp review comparisons (five datasets across ten settings), all 36 fixtures, published dev MATCH, and 150/150 framework fuzz cases. The timestamp tests cover leap days and year changes, invalid clock and offset fields, wide windows, and ingest times outside the cache.

## Stagebench

The harness uses the Analyst's 200 MB seed-42 sample and compares mode 8 against mode 7. Only the decoder and the two timestamp call sites change. Retired instructions and cycles are normalized by parsed records. Scratch-only ablations are marked as such in the raw file.

[Mode samples and separate clock ablations](../results/fast-timestamps-stage.json)
