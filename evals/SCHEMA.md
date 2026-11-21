# Result JSON schema (`evals/results/<version>.json`, `schema_version` 1)

Written by `evals/run.py`. Times are seconds, sizes bytes, unless the key says otherwise.
A **summary** object (`S` below) is `{n, median, mean, min, max, p90, stdev, cv, samples[]}`
(`p90` is nearest-rank; `cv` = stdev/median). Fields may be missing when a stage did not run
(quick profile) or failed. Framework crashes are listed in `errors[]` and never pass silently.

```jsonc
{
  "schema_version": 1,
  "version": "v1", "rev": "v1", "sha": "<full commit sha>", "profile": "quick|full",
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
    "fuzz": {"gen_sha", "cases_dir", "seeds": [start, stop),
             "strict": {"total", "passed", "skipped", "failed": [{"seed", "focus", "tags", "robust_reasons",
                                                                  "error", "repro", "diff"?}]},
             "robust": { ...same... }, "by_focus": {"<focus>": {"total", "failed"}}, "failing_tags": {"<tag>": n}},
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
                    "phases": {"<phase key>": S, "(after last mark: exit/unmap + spawn)": S}},
        "throughput": {"mb_per_s", "events_per_s", "ns_per_event"},
        "noisy": bool, "noisy_reasons": [...]
      }
    },
    "probe": {"dataset", "wall_s", "threads_max", "rss_sampled_max_bytes", "timeline": [[t_s, threads, rss_bytes]]},
    "thread_scaling": {"dataset", "points": {"1"|"2"|"4"|"8": {"median_s", "stdev_s", "n", "speedup", "efficiency"}},
                       "per_ncpu_detail": {"<n>": {"cpu_util": S, "phases": {"<key>": median}}}},
    "size_scaling": {"points": {"<role>": {"events", "median_s", "ns_per_event"}},
                     "ratios": {"perf-20M/perf-1M": {"time_ratio", "events_ratio"}, ...}},
    "container_overhead": {"dev_container_wall_s": S, "dev_native_median_s", "dev_overhead_s", "dev_ratio",
                           "20m_container_wall_s"?: S, "20m_ratio"?}
  },

  "constraints": {"stdout_bytes_max", "threads_max", "threads_probe", "readonly_container_ok",
                  "clean_image_build_ok", "clean_image_build_detail", "binary_bytes", "image_bytes": {"<arch>"},
                  "repo": {"tracked_bytes", "tracked_files", "data_files", "largest": [{"path", "bytes"}]}},

  "baseline": null | {"kind": "submitted|submit-ready", "version", "sha", "wall_s": S,
                      "ab_wall_s"?: S, "ab_candidate_wall_s"?: S},
  "calibration": {"ratio_scorer_over_local", "points", "estimated_scorer_20m_s"},

  "gates": {"A" | "B" | "C": {"status": "pass|fail|incomplete",
                              "checks": [{"name", "status": "pass|fail|not_run", "detail"}],
                              "warnings"?: [...]}},       // C also has baseline, gain, pooled_sd_s
  "verdict": {"verdict": "REJECT|HOLD|SUBMIT-READY", "final": bool, "reasons": [...], "warnings": [...]},
  "notes": [...], "errors": [{"stage", "error", "trace"}]
}
```

**RUN** (one execution, `lib/measure.run_once`):
`{returncode, wall_s, ncpu, stdout_bytes, stderr_bytes, phases: [{key, label, at_s, dur_s}], time_real_s, user_s,
sys_s, cpu_util, max_rss_bytes, peak_footprint_bytes, page_reclaims, page_faults, vcsw, ivcsw, instructions, cycles,
block_in, block_out, canonical_hash?, rows?, files_sha?, stderr_tail?}`.

- `wall_s` is measured by the runner around the process (includes spawn and exit); `time_real_s` is `/usr/bin/time`'s.
- `cpu_util` = (user + sys) / (wall × NCPU).
- `phases`: parsed from stderr marks `[  1.234s] name (detail)`. The key drops the parenthesised detail and numbers
  (`lookups (3.6M linked ids)` → `lookups`); a repeated key gets ` #2`, ` #3`. New or renamed phases become new keys.
- `canonical_hash`: sha256 over both tables after sorting all rows by all columns (layout- and order-insensitive).
  `files_sha` hashes the raw output files (byte identity, informational).

**Verdict:** `REJECT` if any Gate A or B check fails; otherwise `HOLD` if Gate C fails or anything is `not_run`
(then `final: false`, i.e. provisional, e.g. the quick profile); otherwise `SUBMIT-READY`.
