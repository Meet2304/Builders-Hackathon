IMAGE    ?= shopping-sessions:latest
CPUS     ?= 8
MEM      ?= 24g
# The scorer's platform. `make build-native` / PLATFORM=linux/arm64 runs natively on Apple silicon.
PLATFORM ?= linux/amd64
FIXTURES ?= fixtures
DEV      ?= data/dev
ANSWER   ?= data/dev-answer
OUT      ?= out
PY       ?= .venv/bin/python
GEN      ?= tools/generator/target/release/generate
BIN      ?= target/release/sessions
REF      ?= $(PY) reference/reference.py
# For `make gen` / `make diff-seed`: extra datasets for differential testing
SEED     ?= 2
EVENTS   ?= 200000
CLICKS   ?= 50000
export IMAGE CPUS MEM PLATFORM

.PHONY: help setup release fixtures-local run-dev-local check-dev \
        build build-native fixtures fixtures-native run-dev run-dev-native \
        generator dev gen ref-fixtures ref-dev diff-seed clean

help:            ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

setup:           ## One-time: Python venv for test scripts, generator, dev set
	uv venv -q --python 3.12 .venv && uv pip install -q --python $(PY) -r requirements-dev.txt
	$(MAKE) generator dev

# ---- Fast native loop (no Docker) -------------------------------------------
release:         ## cargo build --release (native)
	cargo build --release

fixtures-local: release  ## Run the native binary on all 36 fixtures
	$(PY) scripts/run_fixtures.py $(FIXTURES) -- $(BIN)

run-dev-local: release   ## Run the native binary on the dev set, timed
	rm -rf $(OUT) && mkdir -p $(OUT) /tmp/sessions-scratch
	time env DATA_DIR=$(DEV) OUTPUT_DIR=$(OUT) SCRATCH_DIR=/tmp/sessions-scratch NCPU=$(CPUS) $(BIN)

check-dev:       ## Exact diff of $(OUT) against the published dev answer
	$(PY) scripts/compare.py $(OUT) $(ANSWER)

# ---- Docker, the way the scorer runs it -------------------------------------
# Local amd64 emulation lacks AVX-512, so local builds use a generic x86 target.
# The scorer builds with the Dockerfile default (cascadelake). `make build X86_CPU=cascadelake` to override.
X86_CPU ?= x86-64-v2
build:           ## Build the image for linux/amd64 (emulated on Apple silicon: slow)
	docker buildx build --platform $(PLATFORM) --build-arg X86_CPU=$(X86_CPU) --load -t $(IMAGE) .

build-native:    ## Build the image natively for arm64 (fast local loop on a Mac)
	$(MAKE) build PLATFORM=linux/arm64

fixtures: build  ## Run the image on all 36 fixtures with scorer flags
	$(PY) scripts/run_fixtures.py $(FIXTURES) -- scripts/docker_run.sh

fixtures-native: ## Same, arm64 image
	$(MAKE) fixtures PLATFORM=linux/arm64

run-dev: build   ## Run the image on the dev set with scorer flags, timed
	rm -rf $(OUT) && time scripts/docker_run.sh $(DEV) $(OUT)

run-dev-native:  ## Same, arm64 image
	$(MAKE) run-dev PLATFORM=linux/arm64

# ---- Data -------------------------------------------------------------------
generator:       ## Build the organizers' dataset generator
	cd tools/generator && cargo build --release

dev:             ## The public 1M-event dev set (seed 1) -> data/dev
	$(GEN) --seed 1 --events 1000000 --clicks 250000 --output $(DEV)

gen:             ## Another dataset: make gen SEED=7 EVENTS=200000 CLICKS=50000
	$(GEN) --seed $(SEED) --events $(EVENTS) --clicks $(CLICKS) --output data/seed-$(SEED)

# ---- Reference implementation (correctness oracle) --------------------------
ref-fixtures:    ## Run the Python reference on all fixtures
	$(PY) scripts/run_fixtures.py $(FIXTURES) -- $(REF)

ref-dev:         ## Run the Python reference on the dev set and check it
	rm -rf out-ref && mkdir -p out-ref && DATA_DIR=$(DEV) OUTPUT_DIR=out-ref $(REF)
	$(PY) scripts/compare.py out-ref $(ANSWER)

diff-seed: release  ## Differential test: Rust vs reference on data/seed-$(SEED)
	@test -d data/seed-$(SEED) || $(MAKE) gen
	rm -rf out-a out-b && mkdir -p out-a out-b /tmp/sessions-scratch
	DATA_DIR=data/seed-$(SEED) OUTPUT_DIR=out-a SCRATCH_DIR=/tmp/sessions-scratch $(BIN)
	DATA_DIR=data/seed-$(SEED) OUTPUT_DIR=out-b $(REF)
	$(PY) scripts/compare.py out-a out-b

clean:           ## Remove build outputs and run outputs (keeps data/)
	cargo clean; rm -rf $(OUT) out-a out-b out-ref

.PHONY: dashboard dashboard-watch dashboard-snapshot

dashboard:       ## Generate the progress dashboard
	@if test -x .venv/bin/python; then .venv/bin/python docs/orchestration/dashboard/build.py; \
	else python3 docs/orchestration/dashboard/build.py; fi

dashboard-snapshot: ## Export the live-dashboard snapshot and print the sync batch (see docs/orchestration/dashboard/SYNC.md)
	@python3 docs/orchestration/dashboard/export.py --plan docs/orchestration/dashboard/existing

dashboard-watch: ## Regenerate the progress dashboard every 30 seconds
	@while :; do $(MAKE) --no-print-directory dashboard || exit $$?; sleep 30; done

# ---- Evaluation framework (evals/, owned by the Eval thread) -----------------
VERSION ?=
REV     ?= HEAD
PROFILE ?= quick
.PHONY: eval eval-compare eval-cache-ref eval-selftest eval-calibrate
eval:            ## Evaluate a candidate: make eval VERSION=v2 REV=method/v2 PROFILE=quick|full
	@test -n "$(VERSION)" || (echo "VERSION=... is required" && exit 2)
	$(PY) evals/run.py --version $(VERSION) --rev $(REV) --profile $(PROFILE)

eval-compare:    ## Per-metric deltas with significance: make eval-compare A=v1 B=v2
	$(PY) evals/compare.py $(A) $(B)

eval-cache-ref:  ## One-time: cache the reference's output for every oracle dataset (20M: ~4 min, 17 GB)
	$(PY) evals/cache_reference.py

eval-selftest:   ## Mutation self-test: how many reference mutants do fixtures and fuzz kill
	$(PY) evals/fuzz/selftest.py

eval-calibrate:  ## Recompute the local-to-scorer fit from evals/calibration.json points
	$(PY) evals/calibrate.py
