# Comparing v5 inside and outside gVisor

Run from the repository root on the shared arm64 Docker Desktop host. The probe creates a private named volume, copies the seed into it, and mounts it read-only for both modes. Both launch the same ELF with eight Rayon workers, an eight-CPU quota, 22 GiB memory with swap disabled, and tmpfs output. The outer container is privileged so a nested runsc can create its sandbox. Only trusted local images and datasets belong in this probe.

Install the pinned official arm64 gVisor bundle in a temporary directory. Keep the sidecars next to runsc.

```sh
mkdir -p /tmp/builders-gvisor-20261116
(
  cd /tmp/builders-gvisor-20261116 || exit 1
  url=https://storage.googleapis.com/gvisor/releases/release/20261116/aarch64
  curl -fSLO "$url/gvisor.tar.zstd" &&
  curl -fSLO "$url/gvisor.tar.zstd.sha512" &&
  shasum -a 512 -c gvisor.tar.zstd.sha512 &&
  tar -xf gvisor.tar.zstd
)
python3 evals/explore/runsc/probe.py \
  --image sessions-eval:5b7bcc239556-arm64-faults \
  --gvisor /tmp/builders-gvisor-20261116 --data data/seed-42 --pairs 3
```

Each stdout line is JSON. GNU time inside the chosen environment reports binary lifetime (10 ms resolution), user/system CPU and child minor/major faults. The outer shell reports elapsed time from just before the command until it returns, including sandbox startup and teardown for runsc. Docker CLI latency, dataset staging and image creation are excluded. The probe reverses the order on alternate pairs. The first pair can include cache conditioning. The Mac benchmark lock covers all launches, and cleanup removes the private volume. Rootless runsc ignores nested cgroups because Docker enforces the quota in the outer container.

A successful run checks the process exit status. Use the repository's exact table comparison separately for candidate correctness.

For phase fault counters and input policy experiments, apply `v5-input-probe.patch` on top of `5b7bcc2` in a disposable Linux build, and copy its executable into the timing image. The patch emits cumulative `getrusage(RUSAGE_SELF)` counters before each phase mark. All instrumented modes open files through the same parallel iterator. Set `--env CRIT_INPUT=populate` to request file-backed MAP_POPULATE, `--env CRIT_INPUT=read` to read each file into a private anonymous buffer, or `--env CRIT_INPUT=read-huge` to additionally request MADV_HUGEPAGE before that read. Keep the backing bytes alive through output because fallback string keys borrow them. These are diagnostic builds. The read modes retain one buffer per file.

The one-command wrapper accepts either a local Linux/arm64 ELF or an existing arm64 timing image. It verifies and caches the pinned official gVisor bundle on first use. Supply `GVISOR_DIR` to use an existing bundle. Set `RUNSC_PAIRS=1` for a smoke check, or `RUNSC_JSONL=/path/to/results.jsonl` to retain each sample and phase log.

```sh
evals/explore/runsc/run.sh ./sessions-linux-arm64 data/seed-42
evals/explore/runsc/run.sh sessions-eval:5b7bcc239556-arm64-faults data/seed-42
```
