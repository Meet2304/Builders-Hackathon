# v19 hail-mary: sequential event staging and contiguous partitions

Parent: submitted v18-hailmary (`c4f5e54`). The user requested another attempt; v18 remains unchanged and tagged. No v18 scorer result was available when preparing this candidate.

## Change

The event decoder appends valid rows and all dedup entries into two sequential buffers. Linked-person resolution still uses v18's exact membership filter and batched lookups. At the end of each parse task, counting passes determine partition sizes. Two stable scatters write into one contiguous row allocation and one contiguous event-ID allocation, with prefix offsets exposing the same per-partition slices to downstream code.

This replaces up to 512 independently growing payload vectors per task at the default 256 partitions. Temporary parse buffers are reused across tasks handled by a Rayon map state. Completed outputs retain only exact-size partition payloads and offsets. Dedup can free each task's entire event-ID payload with one deallocation.

Valid-event references are remapped from temporary row indices into the original partition/sequence encoding. Invalid events retain the INVALID marker and still compete in dedup, preserving the rule that an earlier invalid copy defeats a later valid one. The scatters retain within-partition source order; exact IDs, timestamps, campaign attribution, and output encoders are unchanged. The existing dedup unit-test setup was adapted to the contiguous representation but was not executed.

## Rationale and limits

Prior x86 measurements identified event parsing as the main bottleneck. v18 overlapped destination prefetches, but its parser still wrote into hundreds of separate streams. This candidate isolates decoding from routing, reduces allocation fragmentation and excess capacity, and gives downstream phases compact partition storage. The approach extends the project's existing contiguous click-scatter design.

The tradeoff is extra sequential passes and transient buffers. It may improve memory stalls or regress from additional bandwidth use. No performance claim can be made without measurement.

## Validation

Native release compilation only (`cargo build --release --locked`), plus source/diff inspection. No tests, evals, benchmarks, candidate execution, container build, or x86 build, following the user's continuing no-eval/time-limit instruction. Correctness, peak memory, scorer speed and rank are unverified.
