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
