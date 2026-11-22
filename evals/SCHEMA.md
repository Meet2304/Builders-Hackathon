# Result JSON schema (`evals/results/<version>.json`, `schema_version` 1)

Written by `evals/run.py`. Times are seconds, sizes bytes, unless the key says otherwise.
A **summary** object (`S` below) is `{n, median, mean, min, max, p90, stdev, cv, samples[]}`
(`p90` is nearest-rank; `cv` = stdev/median). Fields may be missing when a stage did not run
(quick profile) or failed. Framework crashes are listed in `errors[]` and never pass silently.

```jsonc
{
  "schema_version": 1,
  "version": "v1", "rev": "v1", "sha": "<full commit sha>", "profile": "quick|full|linux",
  "started": "ISO-8601", "finished": "ISO-8601", "duration_s": 612.3,
  "host": {"machine", "ncpu", "perf_cores", "eff_cores", "mem_bytes", "os", "python", "polars"},
  "evaluator": {"eval_sha": "<eval worktree HEAD>[+dirty]", "reference_sha": "<sha256[:16] of reference.py>",
                "fuzz_gen_sha": "<sha256[:12] of fuzz/gen.py>", "scorer_flags_script": "scripts/docker_run.sh"},

  "build": {
    "native": {"binary", "build_s", "binary_bytes", "rustc", "rustflags", "cached", "src"},
    "docker": {"available", "ncpu", "mem_bytes", "server_version"},           // full only
    "images": {"arm64": {"tag", "platform", "no_cache": true, "build_s", "ok", "image_bytes"},   // clean build
               "amd64": {"tag", "platform", "no_cache": false, "build_s", "ok", "image_bytes", "x86_cpu"}}
  },

  "correctness": {
    "fixtures_native" | "fixtures_arm64" | "fixtures_amd64": {"passed", "total", "failed": [{"case", "error"}]},
    "dev_answer_native" | "dev_answer_arm64" | "dev_answer_amd64": {"match", "diff"?, "wall_s"?},
    "differential": {
      "<dataset>": {                                   // kind "oracle": vs cached Python reference output
        "kind": "oracle", "match", "hash", "rows": {"user_daily", "campaign_daily"}, "against",
        "diff"?: {"match", "tables": {"<table>": {"rows_a", "rows_b", "only_a", "only_b", "dup_keys_a",
                                                  "dup_keys_b", "sample_only_a", "sample_only_b"}}}},
      "seed-43": {                                     // kind "consistency": no oracle at 60M
        "kind": "consistency", "match", "hash", "rows",
        "invariants": {"ok", "checks": {"sessions_equal", "revenue_equal", "assisted_ge_credited_nonorganic",
                       "user_daily_keys_unique", "campaign_daily_keys_unique", "sessions_positive",
                       "events_ge_sessions", "purchasing_le_sessions", "organic_channel",
                       "organic_never_assists", "top_category_null_iff_no_revenue"}, "sums"},
        "baseline_version": "v1" | null, "baseline_match": true|false|null, "baseline_established"?: true}
    },
    "fuzz": {"gen_sha", "cases_dir", "seeds": [start, stop), "focus"?: "<selected focus>"|null,
             "strict": {"total", "passed", "skipped", "failed": [{"seed", "focus", "tags", "robust_reasons",
                                                                  "error", "repro", "diff"?}]},
             "robust": { ...same... }, "by_focus": {"<focus>": {"total", "failed"}}, "failing_tags": {"<tag>": n}},
    "debug_knobs": {"<SESSIONS_DEBUG variable=value>": {"status": "n/a|pass|fail|not_run",
                    "dev"?: {"match", "hash"?, "rows"?, "error"?, "diff"?}, "fuzz"?: { ...same as fuzz... }},
                    "<rejection case>": {"status", "returncode", "stderr_tail"},
                    "<empty-output check>": {"status", "cases": {"<fixture>": {"expected", "hashes"}}}},
    "fuzz_windows"?: { ...same as fuzz, seeds [100000, 100000 + N)... },
    "review_suites"?: {"<suite name>": {"runner", "status": "pass|fail|not_run", "total", "passed",
                       "failed": ["<script>: <runner line>"], "error"?,
                       "scripts": {"<cases script>": {"wall_s", "returncode", "total", "passed", "failed"}}}},
    "amd64_knobs"?: {"SESSIONS_DEBUG_NO_FAST=3": {"fixtures": { ...as fixtures_amd64... }, "dev": { ...as dev_answer_amd64... }}},
    "determinism": {"<dataset>": {"runs", "hashes": [...], "deterministic", "byte_identical_files"}},
    "row_counts": {"<dataset>": {"user_daily", "campaign_daily"}}
  },

  "perf": {
    "datasets": {
      "perf-1M" | "perf-20M" | "perf-60M": {
        "dataset", "role", "ncpu", "events_lines", "input_bytes",
        "load_before": {"load1", "load5", "load15", "cpu_busy_pct", "top": [{"pcpu", "comm"}]},
        "warmup": [RUN], "runs": [RUN],
        "summary": {"wall_s": S, "user_s": S, "sys_s": S, "cpu_util": S, "max_rss_bytes": S,
                    "peak_footprint_bytes": S, "page_reclaims": S, "page_faults": S, "vcsw": S, "ivcsw": S,
                    "instructions": S, "cycles": S, "stdout_bytes": S, "last_mark_s": S,
                    "instructions_per_row"?: S, "cycles_per_row"?: S, "ipc"?: S,
                    "phases": {"<phase key>": { ...S, "cpu_s"?: S, "parallelism"?: S },
                               "(after last mark: exit/unmap + spawn)": S}},
        "throughput": {"mb_per_s", "events_per_s", "ns_per_event"},
        "noisy": bool, "noisy_reasons": [...]
      }
    },
    "probe": {"dataset", "wall_s", "threads_max", "rss_sampled_max_bytes", "timeline": [[t_s, threads, rss_bytes]]},
    "thread_scaling": {"dataset", "points": {"1"|"2"|"4"|"5"|"8": {"median_s", "stdev_s", "n",
                        "speedup", "efficiency", "p_core_equivalents"?, "hybrid_efficiency"?}},
                       "per_ncpu_detail": {"<n>": {"cpu_util": S, "phases": {"<key>": median},
                                                  "phase_speedup": {"<key>": wall speedup vs 1}}}},
    "size_scaling": {"points": {"<role>": {"events", "median_s", "ns_per_event"}},
                     "ratios": {"perf-20M/perf-1M": {"time_ratio", "events_ratio"}, ...}},
    "container_overhead": {"dev_container_wall_s": S, "dev_native_median_s", "dev_overhead_s", "dev_ratio"},
    "linux_proxy": {"status": "ok|unavailable", "mem_gib", "dataset"?, "input_storage", "thp_policy",
                    "reason"?, "attempts": [{"dataset", "error"}], "warmup"?: LINUX_RUN, "sample"?: LINUX_RUN,
                    "cold"?: {"status", "dataset"?, "sample"?: LINUX_RUN, "resident_input_bytes_before"?,
                              "attempts": [{"dataset", "error"}]}},
    "linux_timing": {"status": "ok|unavailable", "dataset"?, "mem_gib"?, "thp_policy"?, "input_storage"?,
                     "load_before"?, "event_lines"?, "warmup"?: LINUX_RUN, "runs"?: [LINUX_RUN],
                     "baseline_version"?, "baseline_sha"?, "baseline_warmup"?: LINUX_RUN,
                     "baseline_runs"?: [LINUX_RUN], "summary"?: LINUX_STATS, "baseline_summary"?: LINUX_STATS,
                     "reason"?, "baseline_error"?, "attempts"?: [{"dataset", "error"}]},
    "cold_cache": {"status": "ok|failed|unavailable", "dataset"?, "load_before"?, "reason"?,
                   "warm_median_s"?, "run"?: RUN}
  },

  "constraints": {"stdout_bytes_max", "threads_max", "threads_probe", "readonly_container_ok",
                  "clean_image_build_ok", "clean_image_build_detail", "binary_bytes", "image_bytes": {"<arch>"},
                  "repo": {"tracked_bytes", "tracked_files", "data_files", "largest": [{"path", "bytes"}]}},

  "baseline": null | {"kind": "submitted|submit-ready", "version", "sha", "wall_s": S,
                      "board_time_s"?, "instructions_per_row"?: S, "ab_load_before"?, "ab_required_pairs"?, "ab_wall_s"?: S, "ab_candidate_wall_s"?: S},
  "calibration": {"method": "linear|ratio"|null, "points", "intercept"?, "slope"?, "local_range_s"?,
                  "reason"?, "estimated_scorer_20m_s", "extrapolated", "board_target_s", "beats_board_target",
                  // instruction model (primary when counters exist): board = fixed_s + ipr * board_rows / rate
                  "instr_model": {"method": "rate|linear"|null, "points", "board_rows", "fixed_s"?, "rate_instr_per_s"?,
                                  "ns_per_instr_row"?, "ipr_range"?, "reason"?},
                  "instructions_per_row": float|null, "estimated_scorer_20m_instr_s": float|null,
                  "primary": "instructions|wall"|null, "predicted_board_s": float|null,
                  "target": {"board_target_s", "ns_per_row", "instructions_per_row_max"?: {"fixed X.XXs": n}, "summary"}},

  "gates": {"A" | "B" | "C": {"status": "pass|fail|incomplete",
                              "checks": [{"name", "status": "pass|fail|not_run", "detail"}],
                              "warnings"?: [...]}},       // C also has baseline, gain, pooled_sd_s, metric
  // Gate C extras: "linux_ab"?: {"status": "supports|regression|inconclusive|unavailable", ...},
  //   "instructions": {"status": "pass|fail|unavailable", "gain"?, "checks"}, "wall"? (when the instruction route passed)
  "amendments"?: [{"at", "stages": ["review"|"windows"|"amd64-knobs"|"linux-ab"], "eval_sha", "duration_s"}],
  "verdict": {"verdict": "REJECT|HOLD|SUBMIT-READY", "final": bool, "reasons": [...], "warnings": [...],
              "predictions"?: "predicted board 20M: <instr model>; <wall model>. Target: ..."},
  "notes": [...], "errors": [{"stage", "error", "trace"}]
}
```

**RUN** (one execution, `lib/measure.run_once`):
`{returncode, wall_s, ncpu, stdout_bytes, stderr_bytes, phases: [{key, label, at_s, dur_s, cpu_s?, parallelism?}], time_real_s, user_s,
sys_s, cpu_util, max_rss_bytes, peak_footprint_bytes, page_reclaims, page_faults, vcsw, ivcsw, instructions, cycles,
block_in, block_out, canonical_hash?, rows?, files_sha?, stderr_tail?}`.

- `wall_s` is measured by the runner around the process (includes spawn and exit); `time_real_s` is `/usr/bin/time`'s.
- `cpu_util` = (user + sys) / (wall × NCPU).
- `phases`: parsed from stderr marks `[  1.234s] name (detail)`. The key drops the parenthesised detail and numbers
  (`lookups (3.6M linked ids)` → `lookups`); a repeated key gets ` #2`, ` #3`. New or renamed phases become new keys.
  CPU time uses the difference between consecutive cumulative marks with CPU values, and parallelism is CPU / wall.
- `canonical_hash`: sha256 over both tables after sorting all rows by all columns (layout- and order-insensitive).
  `files_sha` hashes the raw output files (byte identity, informational).

**LINUX_RUN** uses GNU time for `process_wall_s`, `minor_faults`, `major_faults`, and `max_rss_bytes`.
The host measures `container_wall_s` including container setup. The sample also records `phases`,
`thp_mode`, and `page_bytes`.
New Linux timing runs use an inside-container wall clock around GNU time for `process_wall_s`.
Timed samples include `minor_faults_per_row` and `major_faults_per_row` using physical event rows as
the denominator. **LINUX_STATS** maps both wall times, both fault counts and both fault rates to summary objects.

**Gate C Linux A/B** is `gates.C.linux_ab`, with `status` (`supports|regression|inconclusive|unavailable`),
`detail`, and, when comparable, `gain`, `pooled_sd_s`, and `pairs`. A qualifying Linux improvement can pass Gate C
and retains the native result under `gates.C.native`.

New timed samples record `load_before` (host load averages and contamination wait duration).
Linux samples also include `user_s`, `sys_s`, `exit_tail_s`, `peak_anon_bytes`, `peak_anon_huge_bytes`,
`cgroup_peak_bytes`, `oom_kills`, and VM-wide `thp_fault_alloc` and `thp_fault_fallback` deltas when accessible.
The Linux results record `thp_previous`, `thp_policy`, and `thp_restored`. The 60M cap check is stored in
`perf.linux_60m_memory` with the same single-sample shape as the Linux fault probe. The clean scorer-target build
is recorded in `build.images.amd64-cascadelake` and checked via `constraints.cascadelake_build_ok`.

**Verdict:** `REJECT` if any Gate A or B check fails; otherwise `HOLD` if Gate C fails or anything is `not_run`
(then `final: false`, i.e. provisional, e.g. the quick profile); otherwise `SUBMIT-READY`.
