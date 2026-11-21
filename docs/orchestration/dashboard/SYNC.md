# Live dashboard sync

**Artifact (one stable URL, never create another):** https://claude.ai/artifact/BeFsRwhCxaqqo3KRDhdWM5
(also in `ARTIFACT_URL`). It is a claude.ai "Data" dashboard owned by the `claude_andrew` account.
The earlier artifact `WtswJrVasZtzDdyXH1Ci82` belonged to the old account. It can't be reached from this one, so don't use it.

The page (`files/index.html` in the store, source `page.html` here) never changes on a sync.
A sync is only data writes, with the `ArtifactData` tool, to the collection `data/board/rows`.
Each row has a `kind`: `headline`, `version` (one per eval version), `phase`, `thread`, `log`, `insights`, `git`.

## Steps (Orchestrator, after each loop iteration)

Run them from the repo checkout whose `evals/` and `LOG.md` are current (normally the main checkout).
`D` = `<checkout>/docs/orchestration/dashboard`.

1. **Read the store's current rows and versions.**
   First run `rm -rf $D/existing`. Then call:
   ```
   ArtifactData action=list url=https://claude.ai/artifact/BeFsRwhCxaqqo3KRDhdWM5
     collection=data/board/rows query={"limit":1000} out_dir=$D/existing
   ```
   The result text has one line per document: `- "git"  1164 bytes  version 2  "..."`.
   **Save that whole result text** with the Write tool to `$D/existing/listing.txt`.
   The JSON files carry no version, and every write to an existing row needs `if_version`.
2. **Export and plan:** `make dashboard-snapshot > $D/existing/plan.json`.
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
