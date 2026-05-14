---
name: org-resume
description: >
  Resume a suspended org. Use when `.state/org-state.md` exists with Status: SUSPENDED,
  or when the user says "resume", "pick up from where we left off", or "where did we stop last time?".
  Also handles the automatic startup briefing.
effort: low
allowed-tools:
  - Read
  - Bash(git status)
  - Bash(git log:*)
  - Bash(py -3 tools/state_migrate.py)
  - Bash(python3 tools/state_migrate.py)
  - Bash(py -3 tools/journal_append.py:*)
  - Bash(bash tools/journal_append.sh:*)
  - Bash(python -m tools.state_db.importer:*)
---

# org-resume: resuming the org

Load the state of a suspended org, brief the human, and resume.

> **state DB premise (Issue #267 / M4)**: `.state/state.db` is the sole SoT.
> The read path is DB-only (markdown fallback was removed in M4); the write path
> for structured sections goes through `StateWriter.transaction()` (the post-commit
> hook regenerates `.state/org-state.md` from the DB; direct markdown editing is
> forbidden — drift_check will detect it). Free-form learnings / Pending Lead etc.
> are stored under `notes/`. `.state/journal.jsonl` was retired in M4.
> If the DB is missing, build it with `python -m tools.state_db.importer --db .state/state.db --rebuild --no-strict`.

## Phase 1: load state and brief

0. **Run the state schema migration** (Set C §4.4 contract). Bring the JSON state under `.state/` up to the latest schema before reading:

   ```bash
   py -3 tools/state_migrate.py    # Windows
   python3 tools/state_migrate.py   # Mac/Linux
   ```

   Continue on exit 0. On exit 1 (unsupported version remaining) / exit 2 (migration loop anomaly), report to the human and stop.
1. **Fetch previous state from the DB** (Phase 1 uses the lightweight briefing API, Issue #412):
   - `.state/state.db` exists -> query the DB:
     ```bash
     python -c "from tools.state_db import connect; from tools.state_db.queries import get_resume_briefing_light; import json; \
       conn = connect('.state/state.db'); \
       print(json.dumps(get_resume_briefing_light(conn), ensure_ascii=False, indent=2, default=str))"
     ```
     Build briefing material from `active_runs` / `reserved_runs` / `recent_events` / `last_suspend_summary`.
     `session` contains a compressed view of Status / Current Objective / suspended_at / resumed_at / resume_summary (raw `resume_instructions` body and raw event `payload_json` are not included).
     `active_inventory_dirs` is the worker_dir set derived from `runs.status` (state-semantics-contract I7 — it is not `worker_dirs.lifecycle='active'`).
     If needed (very rare cases), `get_resume_briefing` can retrieve the raw payload / full resume_instructions, but do not use it in startup Phase 1.
   - DB missing -> prompt the human to rebuild:
     "state.db not found. Run: `python -m tools.state_db.importer --db .state/state.db --root . --rebuild`".
2. Present a concise summary to the human:
   - Overall objective (briefing's `session.objective`).
   - State of each work item (done / in progress / on hold / blocked; briefing's `active_runs` / `reserved_runs`).
   - Suspend timestamp (briefing's `last_suspend_summary.occurred_at`; reason / counts are in the same dict).
3. Check free-form material under `notes/` (learnings / Pending Lead / session summary).

## Phase 2: reconcile with reality

Use the DB's active_runs as the SoT for reconciliation; treat markdown as a display aid.

1. Starting from the active_runs fetched from the DB (or the markdown Worker Directory Registry), verify each run's `worker_dir`.
2. Also reference each worker state file under `.state/workers/` (legacy path).
3. In each worker's working directory, check:
   - Whether the directory exists.
   - `git status` — uncommitted changes?
   - `git log --oneline -5` — does the last commit match the run's `commit_short` / state file?
   - Does the branch match the run's `branch` / what is recorded in the state file?
4. Check for unsorted files under `knowledge/raw/`.
5. Report any discrepancies to the human (e.g., "The DB says the OAuth run is in_use, but the directory does not exist").

## Phase 3: propose a resume plan

Branch the proposal by state:

- **COMPLETED**: just report results.
- **IN_PROGRESS (suspended)**: "There are uncommitted changes. Shall I dispatch a worker to continue?"
- **PENDING**: check blocker state and judge whether it is now actionable.
- **BLOCKED**: check whether the blocker has been resolved.

**Important: wait for the human's confirmation before acting. Do not dispatch workers on your own.**

## Phase 4: rebuild the org

For the work the human approved:

1. Dispatch workers with the `/org-delegate` skill.
2. Pass the contents of the previous worker state file (`.state/workers/worker-{id}.md`) to the new worker as context.
3. **Write Status / Resumed to the DB** (via `StateWriter.transaction()`. The post-commit hook updates the Status line of `.state/org-state.md` to `ACTIVE`. Even if regen fails, the DB is already committed, and only a stderr warning is emitted):

   ```bash
   python -c "
   from datetime import datetime, timezone
   from pathlib import Path
   from tools.state_db import connect
   from tools.state_db.writer import StateWriter
   ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%fZ')
   conn = connect('.state/state.db')
   with StateWriter(conn, claude_org_root=Path('.')).transaction() as w:
       w.update_session(status='ACTIVE', resumed_at=ts, updated_at=ts)
   "
   ```
4. Regenerate the JSON snapshot (for the dashboard; separate path from the state-db cutover):

   ```bash
   py -3 dashboard/org_state_converter.py    # Windows
   python3 dashboard/org_state_converter.py   # Mac/Linux
   ```

5. Launching the dispatcher / curator panes is owned by /org-start, so do not do it here.
6. Append the resume event to the DB (`tools/journal_append.py` routes DB-only in M4; `ts` is added automatically):
   ```bash
   py -3 tools/journal_append.py resume \
       --json '{"resumed_items": ["blog-redesign", "data-analysis"]}'
   ```
   For event-name and payload-key conventions, see [`docs/journal-events.md`](../../../docs/journal-events.md).
