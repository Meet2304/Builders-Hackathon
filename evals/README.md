# Evaluation framework

Measures each candidate version of the pipeline: is it exactly right, how fast is it and why, does it fit the
scorer's limits, and is it worth a submission. Owned by the Eval thread. Gates and roles are defined in
[../docs/orchestration/PROTOCOL.md](../docs/orchestration/PROTOCOL.md); the result schema is in [SCHEMA.md](SCHEMA.md).

## Quick start

```sh
make eval VERSION=v2 REV=method/v2                 # quick profile, ~1 min (≤ 3 min)
make eval VERSION=v2 REV=method/v2 PROFILE=full    # everything, incl. containers, ~10–15 min
make eval VERSION=v2-linux REV=method/v2 PROFILE=linux # Linux first, plus native 20M comparison
make eval-compare A=v1 B=v2                        # per-metric deltas with significance
make eval-selftest                                 # mutation test of the fixtures + fuzz suite
make eval-cache-ref                                # one-time reference caching (already done)
```

or directly: `.venv/bin/python evals/run.py --version NAME --rev GIT_REF [--profile quick|full|linux] [--fuzz-seeds N]
[--no-docker] [--no-ledger] [--rebuild] [--amend STAGES]`.

`--amend review,windows,amd64-knobs,linux-ab,counters,growth` adds stages to an existing `results/NAME.json` for the same commit
without re-timing anything. It holds the bench lock, uses the original profile's settings, recomputes Gates
A/B/C and the verdict, rewrites `NAME.md`, replaces that version's ledger row, and logs the change under `amendments[]`.
Use it when a new Gate A check lands after a candidate's eval:
`make eval-amend VERSION=v3 REV=29b64bf STAGES=review,windows`.

Outputs: `results/NAME.json` (machine-readable), `results/NAME.md` (summary), one row appended to
[ledger.md](ledger.md). Progress is logged to stderr. Re-running a version name overwrites its result files
and appends a new ledger row.

**Only run timed evals on a quiet machine.** Each sample records host load and waits if a process outside
the evaluator's process tree uses more than 20% of one CPU. Niced work (nice ≥ 10, at most 1.5 CPUs in total) is
tolerated and recorded as `niced_background_pcpu`, because PROTOCOL.md lets other threads build with
`nice -n 19 -j 2` while the lock is held. A block postponed for 180 seconds stops sampling and records the blocker. Blocks with wall-time CV over 3% are marked noisy in the ledger, with raw values
available in the result files. Native blocks also flag the host's existing 12% aggregate pre-block threshold.

## Shared benchmark lock

`quick`, `full`, `linux`, and the standalone `probe_linux` helper acquire `/tmp/builders-bench.lock` with
an atomic `mkdir`. Launch these directly so they can acquire the lock themselves. The lock covers builds and
all timing within the profile, including interleaved A/B and container runs. The `owner` file records the
holder's PID, branch and start time. A waiter logs its identity and the known holder every 60 seconds.

The runner removes `owner` and releases the directory with `rmdir` on completion, error, SIGINT or SIGTERM.
It can recover a stale lock when the owner PID is confirmed dead. An ownerless directory may be held by
Explorer or may be in the middle of acquisition, so the runner waits for it. Correctness-only commands such
as `eval-selftest` do not acquire the benchmark lock. The orchestration protocol specifies
`nice -n 19 cargo build --release -j 2` for builds outside a timed profile while another thread holds the lock.

## Isolation

- Sources come from `git archive <sha>` into `~/.cache/sessions-eval.noindex/src/<sha12>/`. No worktree is touched.
- Native builds use one shared `CARGO_TARGET_DIR` (`~/.cache/sessions-eval.noindex/target`), so dependencies are reused
  across revs. A file lock serialises builds, and each binary is copied to `bin/<sha12>/sessions` (cached per sha;
  `--rebuild` forces a rebuild).
- Images are tagged `sessions-eval:<sha12>-<arch>` and never overwrite `shopping-sessions:*`.
- Run outputs go to `~/.cache/sessions-eval.noindex/runs/` and are deleted afterwards. Set `EVAL_WORK` to move all of this.
  The `.noindex` suffix keeps Spotlight from indexing run outputs; `mds_stores` was taking up to 60 % of a core
  during timed runs before that change.
- Fixtures, the reference, `scripts/docker_run.sh` and the comparison code come from the **eval** worktree, not from
  the candidate, so a candidate can never change how it is judged.

## Profiles

| Stage | quick | full |
| --- | --- | --- |
| native build (cached per sha) | ✓ | ✓ |
| fixtures, native (36) | ✓ | ✓ |
| differential vs cached reference: dev (+ published answer), seeds 2–6, 15, 62, and seed-62-20m | ✓ | ✓ |
| fuzz/adversarial suite, also under supported debug knobs | 150 seeds | 1000 seeds plus boundary and rejection checks |
| fuzz `windows` focus (seeds 100000+) | 60 seeds | 300 seeds |
| Analyst review suites (`suite.json` `review_suites`), every case × 10 knobs | ✓ | ✓ |
| 1M (dev) timing | 1 warm-up + 3 | 1 + 5 |
| 20M (seed-42) timing + oracle diff + determinism | 1 + 5 | 1 + 5 |
| 60M (seed-43) timing + invariants + consistency + determinism | 0 + 1 | 1 + 3 |
| probe run: threads and RSS sampled every 50 ms | on dev | on 60M |
| thread scaling NCPU = 1, 2, 4, 5, 8 on 20M | | ✓ |
| interleaved A/B vs the Gate C baseline on 20M | 11 pairs if fast | 5 pairs, or 11 if fast |
| arm64 image clean build (`--no-cache`, timed), fixtures + dev in the container, container overhead | | ✓ |
| amd64 image (emulated, `X86_CPU=x86-64-v2`), fixtures + dev in the container | | ✓ |
| the same amd64 fixtures + dev under `SESSIONS_DEBUG_NO_FAST=3` (portable SWAR classifier, not SSE2) | | ✓ |
| clean amd64 `cascadelake` build and 60M Linux memory cap check | | ✓ |
| Linux named-volume 20M timing, or informational fallback probe | | ✓ |
| cold-cache run | | ✓ (where available) |

A quick run can REJECT, but it can't say SUBMIT-READY, because the container gates are `not_run`. Its verdict is
marked provisional.

The `linux` profile runs native correctness checks and 150 fuzz seeds, then measures 20M on arm64 Linux before
measuring the same dataset natively. It includes native A/B when a baseline is available. It omits the 60M
constraints and amd64 correctness gates, so its verdict is provisional when the measured gates pass.

## Metrics

**Correctness**
- Fixtures pass count: native, arm64 container, amd64 container (scorer flags via `scripts/docker_run.sh`, `--read-only`).
- dev: exact diff against the published answer (native and in both containers).
- Differential: an exact, order-insensitive diff against **cached reference outputs** in `data/expected/<dataset>/`.
  Each entry's `meta.json` records the dataset fingerprint, the `reference.py` hash, the canonical hash, row counts,
  and the reference's own wall time and RSS. If the dataset or the reference changes, the entry goes stale and is
  regenerated by `make eval-cache-ref`. The fast path compares canonical hashes, and a full row diff (with samples)
  runs only on mismatch.
- The second full-size oracle, `seed-62-20m`, spans 2028-02-21 through 2028-03-06 and covers Feb 29.
  To recreate it, run `tools/generator/target/release/generate --seed 62 --events 20000000 --clicks 5000000 --output data/seed-62-20m`
  and then `.venv/bin/python evals/cache_reference.py seed-62-20m`.
- 60M **consistency** (not an oracle; the reference is too heavy at 60M):
  1. The rules' invariants: sessions and revenue sums are equal across the two tables, and assisted ≥ credited
     non-organic. Also unique keys, events ≥ sessions, purchasing ≤ sessions, organic has channel `organic` and
     never assists, and `top_category` is null iff revenue is 0.
  2. An exact diff against `data/consistency/seed-43/`: the output of the first version that passed Gate A
     (v1 established it).
- Determinism: the canonical hash must be identical across every timed run (1M, 20M, 60M). Byte-identical files
  are reported too, but don't gate.
- Output row counts per dataset.
- Fuzz/adversarial suite (below).

**Performance** (native, NCPU=8, warm page cache)
- Wall time per dataset: median, min, p90, stdev, CV, and all samples. Timing blocks extend to 11 samples when
  the initial median is below 0.5 s.
- Per-phase times from the stderr marks `[  1.234s] phase (detail)`. Keys are normalised (details and numbers
  dropped), so renamed or added phases just become new keys. Also reported: the time after the last mark (exit,
  unmapping, freeing). Cumulative `cpu=X.XXXs` marks also give per-phase CPU time and CPU seconds per wall second.
- Throughput: input MB/s, events/s, ns/event.
- `/usr/bin/time -l`: user and sys, CPU utilisation = (user+sys)/(wall×NCPU), max RSS, **peak memory footprint**,
  page reclaims, page faults, voluntary and involuntary context switches, instructions, cycles.
  Per-run instructions and cycles are also normalized by physical event data lines, including dirty rows.
  IPC is instructions divided by cycles for the same sample. Missing or zero hardware counters are omitted.
- Thread scaling shows wall and per-phase speedup at NCPU 1, 2, 4, 5 and 8. On the 5P M5 host it also shows
  efficiency against an estimated ceiling of 6.4 P-core equivalents at NCPU=8. This estimate assumes
  the first five workers use P-cores. Worker residency is not measured.
- Data-size scaling: time ratios 1M→20M→60M against event ratios, and ns/event per size.
- Container overhead: arm64 container vs native on dev.
- Linux timing (`linux` and `full`) measures the candidate process and its exit from inside the container,
  with 8 CPUs, a 24 GiB cgroup limit and swap disabled. Staging into a named input volume and Docker startup
  are outside the process clock. It takes one warm-up and five samples per version on the same 20M volume,
  interleaved with the Gate C baseline when available. It extends to 11 pairs for sub-0.5 s medians, and
  `--ab-runs` can request more pairs. The report puts these medians and minima next to the native data.
  GNU time measures minor and major faults. Both are divided by physical event data lines, including dirty rows.
  Under the benchmark lock a privileged setup container switches the VM to THP `madvise` and verifies restoration
  of the previous policy in cleanup. Candidate containers retain the usual read-only, network-disabled limits.
  Samples include VM-wide THP fault-allocation and fallback deltas, anonymous and anonymous-huge-page peaks
  sampled every 100 ms from `smaps_rollup`, system CPU, and the wall time after the last phase mark.
  The full profile runs 60M once with a 22 GiB limit and checks cgroup peak memory, including file cache.
- The Linux probe stages input in a temporary Docker named volume and uses GNU time for process wall time,
  minor and major faults, and RSS. The proxy tries 20M with VM memory headroom and falls back to dev (1M).
  It reports one warm-up and one measured run. Each process still incurs first-touch faults with warm input.
  The auxiliary image installs GNU time during setup. The report records verified THP mode and page size.
- The cold-cache probe attempts macOS `purge` without sudo and records one informational 20M run if successful.
  Permission errors are recorded as unavailable. For a Linux follow-up, `probe_linux(..., cold=True)` evicts
  each input file from the named-volume page cache and checks zero resident input bytes with `fincore` before
  launching the candidate. See the v2 report for both measurements.
- Binary size, image sizes, clean image build time, native build time, tracked repo size, stdout bytes, max threads.

## Memory: which number is gated

macOS reports two peaks. **Peak memory footprint** counts anonymous and dirty memory, which is what can OOM.
It is the number `docs/BENCH.md` quotes (11.5 GB for v1 at 60M). **Max RSS** also counts the clean, file-backed
pages of the mmap'd input, about 5.4 GB more at 60M. Gate B's "60M peak memory ≤ 16 GB" is checked on the
**footprint**. When max RSS exceeds 16 GB, that is raised as a **warning**: on the scorer, page cache counts
against the cgroup, so reclaim pressure is possible near the 24 GB limit (clean pages are reclaimed, not OOM-killed).

## Fuzz / adversarial suite

`fuzz/gen.py --seed N --out DIR` writes a small dataset (tens to a few thousand rows) dense in the corner cases
of `docs/rules.md`. Each seed has a focus (dialect, timestamps, sessions, clicks, links, dedup, files, overflow,
window, mixed). Every family still appears at a base rate:

- **Dialect:** quotes around whole fields, `""`, unbalanced, inner, doubled and lone quotes, junk after a closing
  quote, `\r` at line ends and inside values, empty lines, a line of only `\r`, wrong field counts, trailing commas,
  header-like rows mid-file (a `user_id_a,user_id_b` link row really joins two IDs), many tiny files,
  header-only files.
- **Timestamps:** F1, F2 and F3 forms; offsets ±23:59 and `-00:00`, some changing the date; F3 with leading zeros,
  including more than 19 digits; every bad form (fractional, `z`, `t`, a space, no zone, `+0200`, `+24:00`,
  `+05:60`, month 13, Feb 30, Feb 29 outside leap years, hour 24, second 60, Arabic-Indic and full-width digits,
  hex, exponent, sign, surrounding spaces).
- **Overflow traps:** F3 and prices that wrap to in-window or valid values in u64, i64 or u32 arithmetic
  (`2^64 + ts`, `2^32 + 100`).
- **Sessions:** gaps of exactly 30:00.000, 30:00.001 and 29:59.999; equal timestamps; sessions crossing midnight;
  window edges; lateness of exactly 24 h, 24 h ± 1 ms and ± 1 s; ingest before ts.
- **Clicks:** exactly 7 d, 7 d ± 1 ms, at the session start, 1 ms after it; same-ms ties with byte-order traps
  (`k10`/`k9`, `K1`/`k1`, `k1`/`k1 `, UTF-8); the click-window edges; unknown and case-variant campaigns; copies
  quoted differently.
- **Links:** trees, chains of 50–600 IDs in random order, self-links, repeats either way round, empty sides,
  upper-cased sides, shared devices merging people, link-only IDs that become the name, long, UTF-8 and
  space-padded IDs.
- **Dedup:** copies with later ingest and a different user, an invalid earliest copy (bad ts, type, user or price)
  that must not be rescued, a malformed earlier copy, and equal-ingest identical copies.
- **Windows:** Feb 29 2028 and year-end windows.

Cases are **strict** (inside the rules; they gate) unless they use an out-of-spec input. Those are **robust**
cases, reported but not gating: 0-byte CSVs, a missing final newline, non-`.csv` files in the input folders, a
header ending in `\r`, windows that aren't 14 days, and a window start that isn't midnight.
The generator keeps the reference well-defined: a valid F1 `ingest_ts` on every parseable event, identical values
for equal-ingest event copies, and identical values for click copies.

Cases and their reference outputs are cached in `data/fuzz/gen-<gen sha>-ref-<reference sha>/<seed>/`. Editing
`gen.py` or `reference.py` starts a new directory automatically. Each seed is run with NCPU cycling 1, 2, 4, 8.
A failure lists the seed, focus, tags, row-diff samples and a repro command.
The ID-shape focus includes exact 10- and 11-character IDs, separate IDs with the same ten-character prefix,
and a linked person with lowercase and uppercase/underscore IDs. It covers event dedup, person naming, and click ties.

**`windows` focus.** Seeds from 100000 (`WINDOWS_SEED0`) take a focus that ordinary seeds never get, so the
existing seeds generate byte-identical cases. Windows start at year end, new year, around Feb 29 2028 (in the
event window or only in the click lookback), in a non-leap February, or at a month end. A quarter of them start
off midnight, which is out of the generator's spec, so those cases count as robust and don't gate. Each case adds one
fresh person per probe instant. Probes sit at the event and click window edges (±1 ms, ±1 s), at window − 8 days
and window_end + 8 days (the date-table edges of v3's decoder), at every UTC midnight from −9 to +23 days, and at
nearby Jan 1 and Mar 1 boundaries. They render as F1, as F3 with leading zeros, and as F2 with offsets up to
±23:59, so the local date differs from the UTC date. About half the probes also get a click at the same instant,
and some get a session start that the click may or may not credit.

**Review suites.** `suite.json` `review_suites` lists Analyst-written adversarial suites. Each one has a runner and
its case scripts, for example `evals/insights/v3_review/run.py` with `cases.py` and `cases_ts.py`. Eval only invokes
the runner on the candidate binary and parses its `<case> [<knob>]: MATCH|MISMATCH|CRASH` lines. Every listed suite
must be all MATCH for Gate A. The cases stay the Analyst's.

For binaries that expose the debug environment variables, Eval reruns dev and the selected fuzz suite for each setting.
The settings force 4-bit hashes, 97-byte chunks, 1 and 4,096 partitions, and disable fast paths. Each setting must
match the default canonical hash on dev and strict cases. Debug variables absent from the release binary are marked
`n/a`. The v2 fast-path switch is currently a no-op pending the first fast path.
The full profile also tests 0-bit hashes, 3 and 255 partitions, 1- and 4,096-byte chunks on the dialect subset,
and rejection of malformed numeric knob values and out-of-range partition counts. It reads both empty-output
fixtures twice each under default and one-partition settings and compares their canonical hashes to the published fixture answers.

**Self-test** (`make eval-selftest`, results in `results/_selftest.md`): 37 one-line mutants of the reference,
each a plausible fast-path bug, plus 2 equivalent "control" mutants. With 300 seeds the fuzz suite kills all 37,
and the fixtures alone kill 24. Both controls survive, which confirms the generated cases keep the rules'
invariants.

## Gates and verdict (PROTOCOL.md, implemented in `lib/gates.py`)

- **A, correctness:** fixtures 36/36 native and amd64; dev MATCH native and amd64; differential MATCH on every
  oracle dataset in `suite.json` (including both 20M oracles); fuzz strict all MATCH (default and `windows`
  focus); every review suite all MATCH; deterministic hash. Supported debug knobs must also match on dev and strict
  fuzz. In the full profile, amd64 fixtures and dev must also match under `SESSIONS_DEBUG_NO_FAST=3` (SWAR) when
  the binary supports it.
  The 60M consistency check is reported, but it isn't part of Gate A's oracle list.
- **B, constraints:** 60M peak footprint ≤ 16 GB; 60M median ≤ 30 s; stdout < 1 MB; threads < 1000; the
  read-only container runs succeed; arm64 and scorer-target amd64 `cascadelake` build with `--no-cache`;
  the 60M Linux run completes within 22 GiB; tracked repo < 50 MB with no `data/`.
- **C, worth a submission:** the 20M median (≥ 5 runs) is ≥ 5 % faster than the baseline **and** the gap is
  > 2 × the pooled stdev. The baseline is the best version in `submissions.json`. If nothing has been submitted,
  it is the best SUBMIT-READY result in `results/`. Submitted versions are ranked by board time when available
  for all eligible results, otherwise by local median. If neither baseline exists, Gate C passes.
  In the full profile the baseline binary is re-run interleaved with the candidate, so both are measured under
  the same conditions. If either median is below 0.5 s, Gate C needs 11 successful interleaved pairs, and a
  candidate below 0.5 s needs 11 primary timed samples.
  Use `--ab-runs 11` with `evals/run.py --profile full` or `--profile linux` to require 11 pairs at slower times.
  Paired Linux A/B under THP `madvise` uses the same baseline, gain threshold, and pooled deviation test.
  Gate C passes when either the native or Linux comparison passes. The ledger includes a separate Linux 20M column.
  **Instructions route:** Gate C also passes when 20M instructions/row are ≥ 5 % below the baseline's, the drop
  exceeds 2 × the pooled stdev, and 20M wall doesn't regress significantly. "Regress" means the candidate's A/B
  median is more than 2 × pooled stdev slower, or the Linux A/B shows a significant regression. This keeps
  instruction wins that barely show on the M5. When every route fails, the failing instruction checks are listed
  as `or (instructions route): …`.
- **Verdict:** REJECT (A or B fails) / HOLD (C fails, or something wasn't run: provisional) / SUBMIT-READY.

**Comparison with the reference (v3).** `suite.json` `reference_version` is `v3`, the submitted version and the
current board best. Every new eval ends with two steps, both under the bench lock:
1. **Reference refresh.** If the framework has gained untimed stages since the reference was evaluated (review
   suites, the `windows` fuzz, phase counters, growth, amd64 knobs), they run on the reference's own binary via
   `--amend`, so both sides carry the same metric set. Timed metrics aren't re-used across sessions. The
   candidate's eval re-times v3 interleaved, natively and on Linux, because v3 is the Gate C baseline.
2. **Comparison.** `results/<version>-vs-v3.md` holds the full `compare.py` table. The report also gets a
   "Compared with v3" section, right after the headline: predicted board (both models), instructions, cycles and
   IPC per row, same-session native and Linux A/B, and per-phase instructions and cycles plus fast-path share.

**Headline.** Every report starts with a headline table: the predicted board time (instruction model first, then
the wall ratio), 20M instructions per row, the target and how far there is to go, Linux arm64 20M (the primary
local timing, because it has no macOS exit tail), and native 20M with and without the exit tail.

**Per-phase instructions and cycles** (`lib/phase_counters.py`). These are untimed probe runs (full: 1M ×3, 20M ×3,
60M ×2; quick and linux: 20M ×2). The candidate runs with stderr on a pipe. When each `[ t s] phase` mark arrives,
Eval reads the child's cumulative retired instructions and cycles with macOS `proc_pid_rusage(RUSAGE_INFO_V4)`.
These are the same counters `time -l` reports, over all threads. The final totals are read from the zombie after a
kqueue `NOTE_EXIT`, before reaping, so the exit tail is counted. The candidate doesn't change. Each read lands
about 0.1 ms after the mark, which misattributes well under 1% for phases of 10 ms or more. Per-phase sums match
`time -l` totals to within 1%. The probes report instructions and cycles per row, IPC and share per phase.
If the binary knows `SESSIONS_DEBUG_STATS`, one more run per dataset parses every `stats:` line:
`stats: <kind> lines fast=F split_fields=S` becomes a fast-path share per input kind, and any
`stats: <name> k=v …` line is kept, including partition skew once the candidate prints `rows_max=`/`rows_mean=`.
That run's output hash must equal the default run's. `--amend counters,growth` adds all of this to an older result.

**Growth per phase, 60M/20M.** Wall time, CPU per event, and instructions and cycles per row, each as a ratio.
⚠ marks phases more than 15% slower per event at 60M. Flat instructions with rising cycles means a cache or TLB
cliff, not extra work. For v3, lookups and dedup have flat instructions and ×1.5 cycles per row.

**Primary metric: predicted board time.** Every report opens with a "Predicted board time (20M practice)" table, and
every verdict carries a `predicted board 20M: …` reason line. Two predictors are reported side by side:

| Predictor | Model | v3 calibration (1 point: v3 board 1.9424 s) |
| --- | --- | --- |
| instructions (primary) | `board = fixed_s + instr/row × 20M / rate` | rate 26.75 G instr/s, fixed 0 s (97 ns/row) |
| local wall | `board = intercept + slope × local 20M median` | ×3.10 |

Instructions per row are retired instructions divided by event lines on the local 20M run, so they are counted on
arm64. The M5 Pro's IPC (3.2 for v3) is much higher than Cascade Lake's, so local wall time understates gains from
cutting instructions. The instruction model is primary whenever the candidate has counters. The target is shown in
every report: **0.28 s ⇒ 14 ns/row ⇒ ≤ about 308–375 instructions/row** for 0.05–0 s of fixed cost.

**Calibration:** after a submission, add `{version, board_s, submission, board_note}` to `calibration.json` (and
the version to `submissions.json`), then run `make eval-calibrate`. It fills each point's local 20M median and
instructions per row from `results/`. With one point, the wall model is a ratio, and the instruction model fixes the
rate with `fixed_s = fixed_prior_s` (0). With two or more points, each model is a least-squares line, which fits the
fixed cost for the instruction model. The command refreshes both predictions in every result's JSON and Markdown,
in the verdict line, and in the ledger's `Board 20M (est.)`, `Instr/row 20M` and `Board 20M (instr.)` columns.
Recorded verdicts don't change. Native Gate C uses estimated scorer seconds from the wall model when both estimates
are positive.

**Board note "wait 141 ms" (v3, BB-93D28A6B).** `docs/rules.md`, `../context/rules.md` and the starter README and
scripts don't define it. The starter README only says build time is never timed and only the run is timed. It is
recorded verbatim in `calibration.json`. The likeliest readings are (a) scorer-side time before or after the
container's process, such as a queue, container create/start or teardown, that isn't in the score, or (b) a component
of the score, such as container start-to-exit minus process time. Locally, `docker run` on dev costs +0.165 s
over native (container overhead in `results/v3.md`), and Linux process wall at 20M was 0.545 s with exit included.
If (b) is right, about 0.14 s of the 1.94 s is fixed, and it would consume half of the 0.28 s target. Then the
instruction model's fixed cost should be about 0.14 s, giving roughly 26.75 → 28.8 G instr/s and about 200 instr/row
at the target. A second board point will separate the two readings: the fixed cost is the intercept, and the wait
note will either stay the same or scale.

## Files

```
evals/run.py              runner (stages, report, ledger)
evals/compare.py          A vs B per metric, significance = |Δ| > 2·pooled sd, Welch |t| > 3 and ≥ 1 %
evals/cache_reference.py  one-time reference caching into data/expected/
evals/calibrate.py        local-to-scorer fit and estimates
evals/suite.json          the dataset suite (kind oracle/consistency, roles perf-1M/20M/60M, generator args)
evals/submissions.json    what the user submitted (Gate C baseline)
evals/calibration.json    board-time points + ratio
evals/fuzz/gen.py         adversarial generator;  evals/fuzz/selftest.py  mutation test
evals/lib/                common (paths, tables, hashes, diffs, invariants), build, measure, correct, gates
evals/results/            <version>.json + .md, _selftest.*
evals/ledger.md           one row per eval
```

Adding a dataset: generate it (`make gen SEED=… EVENTS=… CLICKS=…`; only Eval writes `data/`), add it to
`suite.json`, then run `make eval-cache-ref`.
