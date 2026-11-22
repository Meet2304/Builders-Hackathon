# V3 hot-path audit

Baseline `29b64bf`. The counter build is `explore/unneeded-work-counters` at `99889aa`. It adds counters to the existing parser and session loop and keeps v3's decisions. Use `NCPU=8` with seed-42 and seed-43 to reproduce. Counts cover actual inputs and are not extrapolated from generator rates.

## What the output needs

- All surviving event types affect session boundaries and the event count. Preserve the nonempty `product_id` check for all three types. For view and cart, the payload of `price_cents` and the product's category are irrelevant after structural CSV validation. Only purchases add category revenue.
- Every well-formed event with a nonempty ID participates in dedup, including invalid later payloads and the invalid earliest copy. A late or invalid winner must still suppress a later valid copy. Empty IDs emit neither a dedup entry nor a row reference.
- Click ID contents affect credit only as the byte-wise tiebreaker at equal timestamps. The nonempty-ID check applies to all clicks. V3 already exploits identical duplicate click values without a separate dedup pass. Campaign validation and the inclusive 7-day window still matter for both credit and assists.
- Link-only IDs can name a component. Keep links that connect IDs absent from events and clicks. Keep day and campaign attribution at the session start, including when purchases cross midnight.

## Measured opportunities

Each cell below is **measured occurrences or bytes / modeled instructions per physical event line**. The denominators are 21,507,843 and 64,150,261, including dirty lines. The estimates multiply the measured counts by the per-occurrence cost before replacement overhead. These are arm64 estimates. The actual counter results for parallel links are in its own report.

Isolated Rust optimized assembly anchors the category, assist and campaign merge costs. The direct category path ran about 28 instructions plus 10 per additional digit. A stratified sample across event files averaged 4.74 and 4.69 digits. The other values are hot-loop operation estimates and include the assumed instruction range in the normalization.

| Work in v3 | 20M count / insn per line | 60M count / insn per line | Cost model | Recommendation |
| --- | ---: | ---: | --- | --- |
| Category lookup on view/cart | 20,436,887 / 57–66.5 | 60,697,275 / 56.8–66.2 | Direct index at sampled digit lengths | Gate on positive price. Keep CSV and nonempty-product checks. |
| Dedup records for empty IDs | 1,809 / 0 | 5,338 / 0 | Already skipped | Keep the short circuit before key, ingest and row-reference handling. |
| Clicks discarded for missing surviving person | 224 / 0.000208–0.000417 | 708 / 0.000221–0.000441 | Buffer and scatter cost per discarded click | Keep the later filter. A presence check on every click would have little to remove. |
| Serial drop-ref routing | 1,472,624 / 0.822–1.37 | 4,033,896 / 0.755–1.26 | Copy cost per ref | 1.84 ms and 6.39 ms in the counter runs. Low priority. |
| Campaign slots above eight accumulators | 5,238,618 / 1.461 | 5,070,534 / 0.4742 | Vectorized merge per slot | Try worker-local accumulators without reducing task parallelism. |
| Repeated assist updates, identical window and day | 3,937,170 / 1.831 | 11,570,313 / 1.804 | Isolated arm64 loop per update | Batch identical-range runs and preserve inclusive bounds. |
| Category zeroing on no-purchase user-days | 1,851,938 / 0.861–1.72 | 5,505,224 / 0.858–1.72 | A short zeroing loop per user-day | Skip clearing when the sum vector is already zero. |
| Event visits repeated for category totals | 5,255,371 / 0.977–1.71 | 16,240,993 / 1.01–1.77 | Cost per repeated row visit | Compute the session day first and add categories during the scan. |
| Clicks already expired upon activation | 265,150 / 0.222–0.431 | 779,677 / 0.219–0.425 | Redundant add/remove pair | Skip directly past them while keeping inclusive boundary clicks. |
| Sorted clicks outside equal-time groups, at least | 4,565,575 / 8.49–14.9 | 13,613,341 / 8.49–14.9 | Typical click ID pack | Defer packing only with a compact way to retain exact source bytes. |
| Person-index bytes above ideal dense capacity | 1,090,133,728 / 0.792–3.17 | 2,435,731,616 / 0.593–2.37 | 1–4 instructions per 64 zeroed bytes | Test a growable or generation-tagged table against the extra probe cost. |
| Second timestamp in ordinary-window sort records | 24,654,657 / 1.15–2.29 | 73,480,257 / 1.15–2.29 | One materialized copy per sorted record | V4's compact event layout covers events. Retain the general-window path for clicks. |

## Additional measurements

- A positive-price gate skips 97.1% of the existing category lookups at both sizes. It adds a price test to each validated event. Purchases with an unmatched product still contribute to `unknown`.
- The expected outputs contain 36.03M and 102.16M assist increments, or 10.57 and 10.12 per session. The baseline loop accounts for an estimated 16.75 and 15.92 instructions per input event line. The five most-assisted campaigns account for 16.5% and 17.1% of those increments, respectively. Repeats on identical windows and days account for 10.9% and 11.3%, before batching overhead.
- V3 created 195 and 189 `Acc` values, each with 28,014 32-byte campaign slots. That is 174.8 MB and 169.4 MB of accumulator capacity plus a serial merge of every slot. Eight accumulators would take 7.17 MB at either size. Rayon scheduling can change the observed counts.
- Sorted clicks after a person's last session start numbered 3,967 and 11,776. That bounds the narrower “after the last surviving event” early-out. The 20–40 instruction buffer model caps the gross opportunity at 0.0074 and 0.0073 instructions per input line before added filtering.
- The 1.47M and 4.03M validated rows that lose dedup bound the work deferred validation could remove. Assuming 80–180 instructions per payload, the gross ceilings are 5.5–12.3 and 5.0–11.3 instructions per input line before replay or metadata costs. Global winner selection still needs every dedup candidate.

Both instrumented runs matched the cached exact output hashes. The wall measurements are diagnostic single samples. The [raw counts](../results/unneeded-work-counts.json) and the [partition skew report](partition-skew.md) include the inputs behind the estimates.
