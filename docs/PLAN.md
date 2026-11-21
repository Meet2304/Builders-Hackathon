# Plan: Shopping Sessions (Databricks track)

**Score = wall-clock run time of the container. Lower wins, ties go to the earlier submission.**
Every row must be exactly right, or there is no score at all. Spec: [rules.md](rules.md).

- Baseline: 170.69 s (PySpark starter). Final: about 60M events (about 5.5 GB of CSV). A run over 3 min gets no score. Aim for well under 10 s.
- Practice: about 20M events, 2 submissions per team per hour. Final: retimed 3×, and the top 10 are retimed 9×.
- Box: 8 vCPU (Xeon, AVX-512), 24 GB RAM, no swap, no network at run time.
- **Deadline: Sun 11:00 AM EST.** Check the date on the track page.

## Why Rust and not Spark or Databricks

The judge only times a Docker container on their box, so nothing runs on Databricks. JVM or Spark startup alone costs seconds. DuckDB and Polars CSV readers don't follow the dialect (quotes, `\r`, malformed lines), so you end up re-parsing by hand anyway. A hand-written Rust pipeline can be both exact and the fastest option.

## Phases

### Phase 0: Infra (done)
- Rust crate that writes both tables, empty, with the exact schema. Multi-stage Dockerfile, amd64 build tuned with `target-cpu=cascadelake`.
- Makefile: native loop, Docker loop with the scorer's flags, generator, dev set, differential tests.
- The organizers' 36 fixtures, the dev answer, and the generator are built in.

### Phase 1: Correctness oracle (`reference/reference.py`), about 1–2 h
Plain Python that follows rules.md literally, line by line, with no cleverness. It must pass `make ref-fixtures` (36/36) and `make ref-dev` (MATCH).
The oracle lets us test any seed (`make diff-seed SEED=n`). Seed 1's window is Dec 2027 and never hits Feb 29 2028, the shared devices only appear at full size, and so on.

### Phase 2: Correct Rust pipeline, about 3–4 h → **submit as soon as it passes**
Data flow:
1. **Read:** mmap every CSV file. Split big files at `\n` boundaries into roughly 8–16 MB chunks, then parse with rayon on all cores.
2. **CSV:** byte-level and exact. Each field is either fully quoted or contains no `"`, the field count must be exact, `\r` is data, an empty line is malformed, and `""` means null.
3. **Timestamps:** hand-rolled F1/F2/F3 → i64 ms, with full calendar and offset checks. F3 must be ASCII digits only, leading zeros are allowed, and anything that overflows 64 bits counts as out of window.
4. **Interning:** user IDs → u32 (hash map; per-thread maps merged, or a sharded map). Keep the bytes so names can be compared.
5. **Links:** union-find over interned IDs. The person name is the byte-wise smallest ID in each component. Links mentioning IDs that never appear in a row still count.
6. **Events:** dedup on `event_id` (keep the smallest `ingest_ts`) **before** validation. Partition by hash(event_id) so each thread dedups its own shard. Then validate, drop late events (`ingest_ts - ts > 86_400_000`), and map to the person.
7. **Sessionize:** sort `(person, ts)` with a radix sort on a packed u64/u128 key. Do a linear scan: gap > 1_800_000 ms starts a new session, equal timestamps share one. The day is the start's UTC date.
8. **Clicks:** dedup on `click_id`, validate (campaign known, ts in `[start-7d, end)`), then sort by `(person, ts, click_id)`. For each session, binary-search the window `[start-7d, start]`. Credit = latest ts, then the smallest click_id. Assists = the distinct campaigns in that window.
9. **Aggregate:** user_daily keyed by (person, day): sessions, events, revenue, and per-category purchase sums → top category (ties go to the byte-wise smallest). campaign_daily keyed by (campaign, day).
10. **Write:** Parquet with arrow-rs, uncompressed, `day` as Date32.

### Phase 3: Make it fast (iterate against the 20M practice board)
- Generate a 60M set locally (`make gen SEED=42 EVENTS=60000000 CLICKS=15000000`) and profile it (`cargo flamegraph`/`samply`).
- Fuse parse, validate, and partition into one pass. Don't allocate per row, and avoid `String`.
- Hash IDs once, using a fast hasher (FxHash/ahash), then compare bytes only when hashes collide.
- Store event_id/click_id only as hashes plus offsets into the mmap. Never copy strings.
- Use SIMD newline/comma scanning (`memchr`) and mimalloc. Watch the 4,096-thread limit and the 24 GB memory limit.
- Keep the output files small and write them in parallel.

### Guardrails
- Every change must stay at 36/36 fixtures, MATCH on dev, and MATCH on 3–5 extra seeds, including one with Feb 29 2028 in the window.
- Run `make fixtures` on the **amd64** image (emulated) before each submission.
- The repo must stay under 50 MB with no data (`data/` is gitignored).
- Log to stderr only (stdout is capped at 50 MB).
