---
name: org-resume
description: >
  Resume a suspended organization. Use when .state/org-state.md exists with Status: SUSPENDED,
  or when told "resume", "continue from where we left off", or "what did we do last time?".
  Also handles automatic briefing on startup.
---

# org-resume: Resume the organization

Read the state of a suspended organization, brief the human, and resume.

## Phase 1: Load state and brief

1. Read `.state/org-state.md`.
2. Present a concise summary to the human:
   - The overall goal
   - The state of each work item (completed / in progress / pending / blocked)
   - The time of suspension
3. If `.state/journal.jsonl` exists, check entries since the `Updated` timestamp in org-state.md,
   and add any events that happened after the snapshot.

## Phase 2: Reconcile with reality

For each work item, check the actual filesystem state:

1. Read each Worker state file under `.state/workers/`.
2. In each Worker's working directory, check:
   - Whether the directory exists
   - `git status` — whether there are uncommitted changes
   - `git log --oneline -5` — whether the last commit matches the state file
   - Whether the branch matches what is described in the state file
3. Check whether there are un-curated files in `knowledge/raw/`.
4. If there are discrepancies, report them to the human (e.g. "The state file says OAuth is 60% complete, but the actual file does not exist.").

## Phase 3: Propose a resume plan

Branch the proposal by state:

- **COMPLETED**: just report the result
- **IN_PROGRESS (suspended)**: "There are uncommitted changes. Shall I dispatch a Worker to continue?"
- **PENDING**: check the blocker state and judge whether it is actionable
- **BLOCKED**: check whether the blocker has been resolved

**Important: wait for the human's confirmation before acting. Do not dispatch Workers on your own.**

## Phase 4: Rebuild the organization

For work the human has approved:

1. Dispatch a Worker via the `/org-delegate` skill.
2. Pass the contents of the previous Worker state file (`.state/workers/worker-{id}.md`) as context to the new Worker.
3. Update Status in `org-state.md` to `ACTIVE`.
4. Regenerate the JSON snapshot:

   ```bash
   py -3 dashboard/org_state_converter.py    # Windows
   python3 dashboard/org_state_converter.py   # Mac/Linux
   ```

5. Starting the Dispatcher and Curator panes is /org-start's responsibility, so do not do it here.
6. Append a resume event to `journal.jsonl`:
   ```json
   {"ts":"<ISO timestamp>","event":"resume","resumed_items":["blog-redesign","data-analysis"]}
   ```
