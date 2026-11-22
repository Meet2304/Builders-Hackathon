# Live dashboard sync

**Artifact (one stable URL, never create another):** https://claude.ai/artifact/WtswJrVasZtzDdyXH1Ci82
(also in `ARTIFACT_URL`). It is a claude.ai "Data" dashboard owned by the main claude.ai account
(the one this project's threads normally run on).

**Account caveat.** An artifact can only be written by an account that can edit it. While the threads ran on the
`claude_andrew` account for a while, that account got its own copy,
https://claude.ai/artifact/BeFsRwhCxaqqo3KRDhdWM5. It is frozen and stale: don't sync to it, and never make a
third. If a sync fails with "no such artifact ... or no access", the thread is on an account that can't edit
the main dashboard. Skip that sync and say so in the log. The next sync from the main account brings everything
up to date, because a sync always writes the full current state. To make every account work, the user can share
the main dashboard with edit access to the other account from its Share menu.

The page (`files/index.html` in the store, source `page.html` here) never changes on a sync.
A sync is only data writes, with the `ArtifactData` tool, to the collection `data/board/rows`.
Each row has a `kind`: `headline`, `version` (one per eval version), `phase`, `thread`, `log`, `insights`, `git`.

## Steps (Orchestrator, after each loop iteration)

Run them from the repo checkout whose `evals/` and `LOG.md` are current (normally the main checkout).
`D` = `<checkout>/docs/orchestration/dashboard`.
Until `dashboard/live` is merged, run step 2 from the dashboard worktree but read the main checkout:
`python3 docs/orchestration/dashboard/export.py --root "<main checkout>" --plan docs/orchestration/dashboard/existing > docs/orchestration/dashboard/existing/plan.json`.

1. **Read the store's current rows and versions.**
   First run `rm -rf $D/existing`. Then call:
   ```
   ArtifactData action=list url=https://claude.ai/artifact/WtswJrVasZtzDdyXH1Ci82
     collection=data/board/rows query={"limit":1000} out_dir=$D/existing
   ```
   The result text has one line per document: `- "git"  1164 bytes  version 2  "..."`.
   **Save that whole result text** with the Write tool to `$D/existing/listing.txt`.
   The JSON files carry no version, and every write to an existing row needs `if_version`.
2. **Export and plan:** `make dashboard-snapshot > $D/existing/plan.json`.
   Results that Eval has committed on `eval/framework` but not yet merged to main: add
   `--evals-ref eval/framework` (run `export.py` directly). A result there that is newer by `finished` wins.
   The 20M median is the interleaved A/B median when the eval ran one; otherwise it is the timed block's
   median. `median_20m_basis` says which.
   This writes `snapshot.json` and `snapshot/<id>.json`, and prints
   `{"url", "batches": [[write, ...], ...]}`. Each write is a `set` (with `file_path` and `if_version`) for a new or changed row, or a `delete` for a row no longer exported.
   Unchanged rows are skipped. `headline` is always written, and written last.
   `listing.txt` is renamed to `listing.used`, so a stale listing can't be reused. If the plan stops with
   "no version for N stored docs", step 1's listing text is missing. Redo step 1.
3. **Write:** for each batch in `plan.json`, call
   `ArtifactData action=batch url=<url> writes=<that batch, verbatim>`.
   Each batch is atomic. If one fails with a version conflict, redo from step 1.
   Don't add `force` and don't write without `if_version`.
4. Never call `Artifact publish` with a `type_url` (that makes a new dashboard), and never publish `file_path` to this URL.
   Readers who have the page open get the new rows live.

## Changing the page itself (rare)

Edit `page.html` here. Then `ArtifactData get collection=files doc_id=index.html` to get its version (someone may
have edited it in the page's pencil since; merge their change). Then
`ArtifactData set collection=files doc_id=index.html file_path=<json {"text": <page.html>}> if_version=<v>`.
Before changing it, read the type's `artifact-type/reference/one-writer.md` (`Artifact read url=... path=...`).

## Files

- `export.py`: stdlib exporter and sync planner (`--plan DIR`, `--listing FILE`).
- `page.html`: the dashboard page, as stored in `files/index.html`.
- `ARTIFACT_URL`: the URL above.
- `snapshot.json`, `snapshot/`, `existing/`: generated, gitignored.
