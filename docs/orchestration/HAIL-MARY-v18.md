# v18 hail-mary submission

Based on v17 (`bf93837`), the strongest recorded submission at 0.8900 s. The earlier champion v8 (`2bfb034`, 1.0844 s) is retained in history. This is an unmeasured candidate, not a claim of a new best or first place.

## Context used

Read the orchestration history through v17, the v4 partition-skew and scheduling studies, the current parser, ID, dedup, sessions and writer implementations, and the existing scout repository notes (`scout:evals/scout/repos.md`). The public-method notes identify two-bit duplicate filters (Epsilon, crypto-kidz, VibDiv), membership filtering (Polaris), packed IDs, half-hour session bins, custom Parquet, and persistent work queues. No competitor source was copied. Earlier PGO and thread/chunk/huge-page trials did not produce an x86 win; those settings remain as in v17.

## Implementation

- Link membership: one bit per home slot, constructed during the existing final link-resolution pass. A clear bit bypasses both the large-table prefetch and lookup. Set bits retain exact key probing. The parallel load completes before events or clicks read the filter.
- Event scatter: 64-row batches resolve persons and prefetch destination storage before a second pass emits rows, preserving the batch order and exact reference indices. Click batch size remains 16.
- Dedup: two-bit saturating counters exclude provably singleton hash buckets. Repeated buckets use the existing exact event-ID/min-ingest algorithm with a table sized to candidate rows. Hash collisions produce extra work, never dropped candidates. Invalid rows still participate, and original source locators advance for every row.
- Sessions: persistent workers claim largest-first partitions from an atomic queue. Each worker retains its own scratch, campaign totals and user output, avoiding repeated accumulator creation and mutex borrowing. People stay entirely within their original partitions.

## Validation and status

User explicitly requested a sub-nine-minute attempt with no tests or evals. Only native `cargo build --release --locked` and source/diff inspection were performed. Release compilation succeeded. No candidate execution, fixture run, benchmark, container build, x86 build, or final evaluation was performed. Correctness, memory use, speed and final rank are unverified. The larger batches, extra filter passes and larger output batches can regress performance on the scorer; v17 remains available unchanged as fallback.

Submission is by the user, using the v18-hailmary tag or its commit SHA.
