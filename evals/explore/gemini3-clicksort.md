# Click sort: counting sort by person, then a small run

Branch `explore/gemini3-clicksort` at the commit below, from method/v5 `5b7bcc2`. Binary sha256 `475760e02ac7443e345876ebf1981f2d72e5c413434f4d736f47542c096dfe40`, rebuilt after deleting `target/release/sessions` and the sessions fingerprint.

## Click read order

Clicks are grouped by the dense person id with a stable counting sort, so each person's run is still the order they were read. A run is a stretch already in the required order: timestamp ascending, and at an equal timestamp a descending click id (the last click at that timestamp is the smallest id, which is the one the window credits).

| | seed-42 | seed-43 |
| --- | ---: | ---: |
| Persons with a kept click | 432,974 | 1,298,799 |
| Already in order | 8.73% | 9.27% |
| Click rows | 5,089,975 | 15,031,125 |
| Rows in an already-ordered person | 1.67% | 1.79% |
| Runs per person | 6.35 | 6.27 |

Mean clicks per such person are about 12. A random permutation of 12 items has `(n+1)/2 ≈ 6.5` runs. Clicks are as unsorted as events. On seed-42, 2.82M of 5.09M clicks sit in persons with 9 or more runs.

## Instructions, seed-42, one thread

5,089,975 kept clicks. 21,507,843 event lines. The counter wraps the whole click collect and sort. `SESSIONS_CLICK_SORT=old` is v5's one `sort_unstable_by` over every click in the partition. Two samples.

| | insn per click | insn per event line |
| --- | ---: | ---: |
| v5 sort, sample A | 371.9 | 88.0 |
| v5 sort, sample B | 372.2 | 88.1 |
| Counting sort + per-person sort, A | 172.5 | 40.8 |
| Counting sort + per-person sort, B | 172.8 | 40.9 |

That is the analyst's 89 per line and 377 per click, cut to about 41 and 173. The sessions phase moves from 320 to 273 instructions per event line. The comparator is unchanged: earlier timestamp first, and at the same timestamp the byte-wise larger click id first, with packed ids compared as the integer the packer already ordered.

Runs of 64 or fewer use insertion sort. Longer runs, the whales, use `sort_unstable_by` with the same order. Sorting during the initial bucket was not a further win: the person id is only known after the link lookup, and the read order is random, so the bucket would still sort.

## Correctness

Fixtures 36/36. Dev MATCH, and dev matches the old sort. Fuzz seeds 0–149: 150/150. Seed-42 and seed-43 MATCH the old sort on both tables.

## How to port

Replace the partition-wide `cks.sort_unstable_by` with `sort_clicks_counted`: one pass that resolves the dense person id, a counting sort into person order, then `sort_click_run`. Keep `k` as `loc << 40` (or `loc` in the wide layout) so the session walk's person scan does not change.
