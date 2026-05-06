---
name: org-resume
description: >
  Resume a suspended org. Use when `.state/org-state.md` exists with
  Status: SUSPENDED and the user says "resume", "continue from where we left off",
  "where did we get to last time?". Also covers the auto-briefing on startup.
---

# org-resume: resume the org

Load the suspended org's state, brief the human, and resume.

> **state DB premise (Issue #267 / M4)**: `.state/state.db` is the sole SoT.
> The read path is DB only (markdown fallback was removed in M4); the structured
> sections' write path goes through `StateWriter.transaction()` (a post-commit
> hook auto-regenerates `.state/org-state.md` from the DB; direct markdown edits
> are forbidden — drift_check detects them). Free-form learnings / Pending Lead
> items go under `notes/`. `.state/journal.jsonl` was retired in M4. If the DB
> is missing, build it with
> `python -m tools.state_db.importer --db .state/state.db --rebuild --no-strict`.

## Phase 1: Load state and brief

0. **Run the state-schema migration** (Set C §4.4 contract). Bring the JSON state under `.state/` to the latest schema before reading:

   ```bash
   py -3 tools/state_migrate.py    # Windows
   python3 tools/state_migrate.py   # Mac/Linux
   ```

   exit 0 → continue. exit 1 (unsupported version remains) / exit 2 (migration loop anomaly) → report to the human and stop.
1. **Pull the previous state from the DB**:
   - `.state/state.db` exists → query the DB:
     ```bash
     python -c "from tools.state_db import connect; from tools.state_db.queries import get_resume_briefing; import json; \
       conn = connect('.state/state.db'); \
       print(json.dumps(get_resume_briefing(conn), ensure_ascii=False, indent=2, default=str))"
     ```
     Use `active_runs` / `recent_events` / `last_suspend_at` to compose the briefing material. Status / Current Objective / Resume Instructions are also stored on `org_sessions`.
   - DB is missing → ask the human to rebuild it:
     "state.db not found. Run: `python -m tools.state_db.importer --db .state/state.db --root . --rebuild`".
2. Present a concise summary to the human:
   - Overall objective (DB `objective`).
   - Status of each work item (done / in progress / pending / blocked, from DB active_runs).
   - Suspend timestamp (DB `last_suspend_at`).
3. Check the free-form notes under `notes/` (learnings / Pending Lead / session summaries).

## Phase 2: Cross-check against reality

Treat the DB's active_runs as the SoT and use markdown only as a display aid.

1. Starting from the active_runs returned by the DB (or the markdown Worker Directory Registry), verify the `worker_dir` of each run.
2. Also reference each worker's state file under `.state/workers/` (legacy path).
3. In each worker's working directory, verify:
   - The directory exists.
   - `git status` — any uncommitted changes?
   - `git log --oneline -5` — does the last commit match the run's `commit_short` / state-file record?
   - The branch matches the run's `branch` / state-file description.
4. Check `knowledge/raw/` for any unsorted files.
5. If you find a discrepancy, report it to the human (e.g., "the DB lists OAuth run as in_use, but the directory does not exist").

## Phase 3: Propose a resumption plan

Branch the proposal on the state:

- **COMPLETED**: just report the result.
- **IN_PROGRESS (suspended)**: "Uncommitted changes are present. Should I dispatch a worker to continue?"
- **PENDING**: confirm the blocker's status and judge whether it is now executable.
- **BLOCKED**: confirm whether the blocker has been resolved.

**Important: wait for the human's approval before acting. Do not dispatch a worker on your own.**

## Phase 4: Reconstruct the org

For each work item the human approves:

1. Dispatch a worker with the `/org-delegate` skill.
2. Pass the contents of the previous worker's state file (`.state/workers/worker-{id}.md`) to the new worker as context.
3. **Write Status / Resumed to the DB** (via `StateWriter.transaction()`. The post-commit hook updates the Status line of `.state/org-state.md` to `ACTIVE`. If regen fails the DB write is still committed; only a stderr warning is emitted):

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
4. Regenerate the JSON snapshot (for the dashboard; this is a separate path from the state-db cutover):

   ```bash
   py -3 dashboard/org_state_converter.py    # Windows
   python3 dashboard/org_state_converter.py   # Mac/Linux
   ```

5. Starting the Dispatcher and Curator panes is /org-start's job, not org-resume's.
6. Append a resume event to the DB (`tools/journal_append.py` is M4 DB-only routing; `ts` is auto-populated):
   ```bash
   py -3 tools/journal_append.py resume \
       --json '{"resumed_items": ["blog-redesign", "data-analysis"]}'
   ```
   Refer to [`docs/journal-events.md`](../../../docs/journal-events.md) for the event-name / payload-key convention.
