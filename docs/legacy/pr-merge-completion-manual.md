> **This document is historical reference material.** Do not consult it for Lead / worker / dispatcher standard operations. The standard path is the merge-watch loop via `tools/pr-watch.ps1 -PR <PR>` (Windows) / `tools/pr-watch.sh --pr <PR>` (POSIX), or `python tools/run_complete_on_merge.py --pr <PR>` (Issue #317). If `tools/run_complete_on_merge.py` behaves unexpectedly, do not reproduce it manually; file an Issue and pause the affected close until the bug on the resolver / helper side is fixed. Any decision to do manual work as an exception is left to the user's explicit judgment. If Lead reaches this document on its own, that is a protocol violation.

# Legacy hand-rolled PR-merge completion (museum copy)

This file preserves the pre-Issue-317 manual completion snippet for archaeological reference. It was extracted from `.claude/skills/org-delegate/SKILL.md` Step 5 2b-ii (same externalization pattern as PR #315).

## Why this is no longer in the active skill

Documenting a hand-rolled `python -c` block inside the active skill acted like an "easy button": when the secretary observed a PR merge, they would copy the snippet and run it ad hoc, which had several historical failure modes:

- **Forgotten `pr_state='merged'`** — the legacy snippet only called `update_run_status('<task_id>', 'completed')`. `runs.pr_state` remained `'open'`, so dashboards / queries filtering on `pr_state` showed inconsistent state. `tools/run_complete_on_merge.py` writes `pr_state='merged'`, `commit_short`, `pr_url`, and `completed_at` from the `gh pr view` payload in one transaction.
- **Missing `pr_merged` event** — the snippet did not append an event row, so the journal had no record of *why* the run transitioned to completed. The helper appends a single `pr_merged` event with PR / repo / merge_commit / merged_at in the payload, and is idempotent (a second invocation does not double-write).
- **Manual `mergedAt` confirmation** — the secretary had to run `gh pr view --json mergedAt` themselves and decide whether the PR was actually merged. The merge-watch loop in `tools/pr_watch.py` handles this end to end.
- **No completed_at** — the snippet did not pass `completed_at`, so `runs.completed_at` remained NULL and downstream "time-to-merge" queries lost data. The helper threads the PR's `mergedAt` directly into `update_run_status(..., completed_at=...)`.

Today, if `tools/run_complete_on_merge.py` errors or writes a wrong row, the canonical response is to **file an Issue against the helper and pause the affected close until the underlying bug is fixed**. Whether to invoke any manual workaround at all is a user judgment call. Lead must not self-grant the exception.

## Legacy procedure (verbatim, do not use)

```bash
python -c "
from pathlib import Path
from tools.state_db import connect
from tools.state_db.writer import StateWriter
conn = connect('.state/state.db')
with StateWriter(conn, claude_org_root=Path('.')).transaction() as w:
    w.update_run_status('<task_id>', 'completed')
    # パターン B / C のエントリ削除はここで w.remove_worker_dir('<abs>') を追加
"
```

Operationally, this meant:

- Lead confirms the merge with `gh pr view <PR> --json mergedAt` or similar
- Run the inline Python above after replacing `<task_id>`
- If needed, separately run `bash tools/journal_append.sh pr_merged ...` to leave an event row (in practice this was often forgotten)
- In pattern B, also add `w.remove_worker_dir('<abs>')` in the same script

The legacy block did **not** set `pr_url` / `pr_state` / `commit_short` / `completed_at`, did **not** append a `pr_merged` event, and did **not** verify `mergedAt` against `gh pr view`; all four are now handled in one transaction by `tools/run_complete_on_merge.py`.
---
