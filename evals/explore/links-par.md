# Parallel Links & Lookups Phase: In-Place Lock-Free DSU (`explore/links-par`)

Prototype `explore/links-par` at `8528a07` based on v8 release candidate `2bfb034`.

## Hypothesis and Changes

In v8 / v5, the links phase used a two-stage approach:
1. Parse all chunk lines into `Vec<Vec<(u64, u64)>>`.
2. Construct a temporary `Components` hash table (size `(3 * edges).next_power_of_two()`, requiring 96 MB for 60M).
3. Concurrently intern and union into `Components`.
4. Scan all slots of `Components` into chunked `records: Vec<(u64, u64)>`.
5. Allocate a second table `LinkTable` (up to 64 MB), zeroed single-threaded via `map(...).collect()`.
6. Concurrently insert all records into `LinkTable`.

Under Linux and gVisor, allocating and zeroing 160 MB across multiple tables, plus 40 MB of intermediate `Vec`s, triggered tens of thousands of page faults (which trap into gVisor's Sentry kernel), dominating the lookups phase (up to 93 ms).

### The In-Place Streamed Design

1. **Direct Streamed SIMD Parsing (Zero Intermediate Allocation):**
   - As each link line is decoded by the SIMD register parser in `columns::links_for_each`, `(a, b)` is directly interned and unioned into `LinkTable`.
   - Completely eliminates `pairs: Vec<Vec<(u64, u64)>>` and intermediate heap reallocations.

2. **In-Place Lock-Free Union-Find in `LinkTable`:**
   - `LinkTable` itself serves as the union-find structure.
   - `slot[0]` stores the 64-bit user ID key.
   - `slot[1]` stores the 1-based parent slot index during union-find (0 = uninitialized / self-root).
   - `intern`: lock-free open-addressing with CAS on `slot[0]` using the exact multiplicative hash of `LinkTable`.
   - `root`: path-halving compression with atomic `compare_exchange_weak`.
   - `union`: merges the root with the strictly larger byte-wise ID to the root with the strictly smaller byte-wise ID (`ids.cmp`), guaranteeing acyclicity and lock-free progress.

3. **Two-Pass In-Place Resolution:**
   - Pass 1: Parallel path compression so all nodes point directly to their component root.
   - Pass 2: Overwrite `slot[1]` with `person = table.slots[root][0]` (the minimum byte-wise ID key) and count distinct linked IDs in parallel.
   - Unlinked users hit `slot[0] == 0` during events/clicks and return themselves; linked roots return `slot[1] == key`; remapped users return `slot[1] == person`.

4. **Presized Zeroed Table with No Rehash:**
   - `LinkTable::new_with_cap(cap, hmask)` allocates zeroed memory via `std::alloc::alloc_zeroed`, avoiding single-threaded user-space zeroing loops.
   - Sized conservatively via `(in_bytes / 9).next_power_of_two()`, guaranteeing 32%–48% load factor across all datasets without rehashing.

## Numbers and Measurements

Binaries:
- Baseline (`2bfb034`): `c3efdbbb44f5a9f0c0b96b5b13d11c7a8a020bc8980ebd8a2ee2c5230636c066`
- New (`8528a07`): `b467ce5854f118f9221792cc10349fe391c9455a26a6420b7ecf7afabacc3ebb`

### Lookups Phase Performance (Native, nice 19, median of 3 runs)

| Dataset | Metric | Baseline (`2bfb034`) | New (`8528a07`) | Delta |
|---|---|---|---|---|
| **dev (1M)** NCPU=8 | Lookups Wall | 5 ms | 2 ms | **-60.0%** |
| | Lookups Instructions | 0.043 G | 0.033 G | **-23.3%** |
| **seed-42 (20M)** NCPU=8 | Lookups Wall | 34 ms | 28 ms | **-17.6%** |
| | Lookups CPU | 245 ms | 212 ms | **-13.5%** |
| | Lookups Instructions | 0.605 G | 0.548 G | **-9.4% (-57M instr)** |
| **seed-42 (20M)** NCPU=1 | Lookups Wall | 124 ms | 111 ms | **-10.5%** |
| | Lookups CPU | 125 ms | 111 ms | **-11.2%** |
| | Lookups Instructions | 0.564 G | 0.527 G | **-6.6% (-37M instr)** |
| **seed-43 (60M)** NCPU=8 | Lookups Wall | 96–131 ms | 77 ms | **-19.8% to -41.2%** |
| | Lookups CPU | 690–703 ms | 597 ms | **-13.5% to -15.1%** |
| | Lookups Instructions | 1.84–2.04 G | 1.67 G | **-9.2% to -18.1% (-170M to -370M instr)** |
| **seed-43 (60M)** NCPU=1 | Lookups Wall | 440 ms | 389 ms | **-11.6%** |
| | Lookups Instructions | 1.85 G | 1.63 G | **-11.9%** |

### Memory Footprint & Allocations
- Eliminated ~100 MB of duplicate table allocations and temporary `Vec<Vec<(u64, u64)>>` buffers.
- Zero allocations during streaming link parse.
- Zero secondary table construction passes.

## Verification & Gates
- **Fixtures:** 36/36 passed (`make fixtures-local`).
- **Dev MATCH:** Verified bit-for-bit identical MATCH against `data/dev-answer` under `NO_FAST=0, 1, 2, 3`.
- **Seed-42 Oracle:** Verified bit-for-bit identical MATCH against `data/expected/seed-42`.
- **Fuzz Suite:** All 25 `links`-focused seeds passed differential checks against the Python oracle (both default and `NO_FAST=1, 2, 3`).
- **Compiler:** Built cleanly with 0 warnings.
