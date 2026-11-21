# Shopping Sessions: Rust pipeline.
# The scorers build this natively on linux/amd64 (Intel Xeon, Cascade Lake+, AVX-512),
# with network for up to 10 min. No FROM pins a platform, so it also builds natively
# on Apple silicon for fast local loops (make build-native).

FROM rust:1-slim-bookworm AS build
ARG TARGETARCH
# Scorer default. Local amd64 emulation has no AVX-512: `make build` passes X86_CPU=x86-64-v2.
ARG X86_CPU=cascadelake
ENV TARGETARCH=$TARGETARCH X86_CPU=$X86_CPU
WORKDIR /src
COPY docker/cargo-build.sh /usr/local/bin/cargo-build.sh

# 1) Dependency cache: build deps against a stub main so edits to src/ don't rebuild arrow/parquet.
COPY Cargo.toml Cargo.lock ./
RUN mkdir src && echo 'fn main() {}' > src/main.rs \
 && cargo-build.sh --deps-only \
 && rm -rf src

# 2) The real build. touch: COPY keeps host mtimes, which can look older than the stub build.
COPY src ./src
RUN touch src/main.rs && cargo-build.sh

FROM debian:bookworm-slim
# The scorer runs the container as uid 1000; give that uid a name and a home.
RUN useradd --uid 1000 --no-create-home --home-dir /scratch app
COPY --from=build /sessions /app/sessions
# Runtime: root fs read-only, uid 1000, no network, /data read-only,
# only /output and /scratch writable (+ 64 MB /tmp). Log to stderr only.
CMD ["/app/sessions"]
