---
name: org-pull-request
description: >
  After the user approves a worker's completion report, the Lead handles push / PR creation / CI monitoring /
  review-feedback loop / final close after PR merge. Triggers:
  (1) immediately after a worker submits a completion report and the user gives explicit approval such as "OK" or "go ahead",
  (2) when review feedback / CI failure arrives on the GitHub PR and you need to send fix instructions back to the worker,
  (3) when the PR is merged and the final close conditions are met.
  The initial "delegate work to a worker" step is handled by org-delegate, not by this skill.
effort: medium
allowed-tools:
  - Read
  - Bash(git push:*)
  - Bash(git -C * worktree remove:*)
  - Bash(git worktree remove:*)
  - Bash(gh pr create:*)
  - Bash(gh pr view:*)
  - Bash(gh pr checks:*)
  - Bash(gh issue create:*)
  - Bash(gh issue edit:*)
  - Bash(bash tools/journal_append.sh:*)
  - Bash(py -3 tools/journal_append.py:*)
  - Bash(python tools/set_run_pr_open.py:*)
  - Bash(py -3 tools/set_run_pr_open.py:*)
  - Bash(python tools/run_complete_on_merge.py:*)
  - Bash(py -3 tools/run_complete_on_merge.py:*)
  - Bash(bash tools/pr-watch.sh:*)
  - Bash(pwsh tools/pr-watch.ps1:*)
  - Bash(powershell tools/pr-watch.ps1:*)
  - mcp__renga-peers__send_message
  - mcp__renga-peers__check_messages
---

# org-pull-request: PR creation, review, and post-merge close

Covers worker completion report -> user approval -> push / PR creation / CI monitoring / review-feedback loop / final close after PR merge. **Lead only.** The precondition for invoking this skill is that the worker has submitted a completion report and the user has given explicit approval. The pre-approval phase (ack issuance, transition to REVIEW, reporting to the user) is covered by `.claude/skills/org-delegate/SKILL.md` Step 5 (2a).

> **T5 contract**: The canonical spec for the `awaiting_review -> complete` transition handled by this skill is
> [`docs/contracts/delegation-lifecycle-contract.md`](../../../docs/contracts/delegation-lifecycle-contract.md) §2 T5 / T6 / §1.5 close-condition.
> That contract is the SoT that pins close-condition / pane discipline / no-respawn.
> This SKILL owns the procedure; the contract owns the invariants.

> **ack != user approval**: By the time this skill is invoked, ack has already been issued (`.claude/skills/org-delegate/SKILL.md` Step 5 step 1 / [`.claude/skills/org-delegate/references/ack-template.md`](../org-delegate/references/ack-template.md)). push / `gh pr create` / `tools/pr-watch.*` are issued only after user approval.

## 2b-i. PR creation phase (run immediately)

Triggered immediately after the user gives **explicit approval** such as "OK", "looks good", "no issues", or "go ahead":

- The Lead performs push / PR creation as needed (the worker does not have `git push` / PR-creation permissions). The language convention for PR bodies follows `feedback_pr_issue_english` (PRs / Issues in English).
- **As soon as the PR number is confirmed, immediately back-fill `runs.pr_url` / `runs.branch` with `tools/set_run_pr_open.py`** (Issue #323):
  ```bash
  python tools/set_run_pr_open.py --task-id <task_id> --pr <PR>
  ```
  This calls `gh pr view <PR> --json url,headRefName` once and overwrites `runs.pr_url` and `runs.branch` via `StateWriter.set_run_pr`. Re-invocation is idempotent (overwrites with the same values, no events appended). Without this, the later `tools/run_complete_on_merge.py` cannot look up `runs.pr_url`, fails with `no_run` (exit 3), and the `-MergeWatch` auto-completion breaks.
- Append events to the DB events table (push / PR open etc., `bash tools/journal_append.sh ...`).
- Once the PR number is confirmed, monitor CI with `tools/pr-watch.ps1 <PR>` (Windows) / `tools/pr-watch.sh <PR>` (POSIX). On completion `ci_completed` is automatically recorded in events. pr-watch **returns** once CI completes (so it does not synchronously block, allowing you to proceed to review-feedback loop 2c or manual close 2b-ii).
- **In renga environments, pr-watch sends a peer message to the Secretary at the moment of CI completion / merge detection / 24h timeout** (Issue #326). The Lead does not poll the events table; it advances to the next step on arrival of `<channel source="renga-peers"> CI_COMPLETED: PR #<n> ...` (and `PR_MERGED: PR #<n>` / `PR_MERGE_WATCH_TIMEOUT: PR #<n>` / `PR_MERGED_NO_RUN: PR #<n>`). `CI_COMPLETED` received -> ask the user for merge approval -> user approval -> `PR_MERGED` received -> go to 2b-ii post-merge cleanup. `PR_MERGED_NO_RUN` is a failure case where merge was observed but no corresponding run row was found (the `no_run` terminal state of `tools/run_complete_on_merge.py`); do not proceed to post-merge cleanup — handle by human judgment. In plain shells / CI without `RENGA_SOCKET` set, peer-send is a silent noop and falls back to polling the events table as before.
- **Right before "CI_COMPLETED received -> ask user for merge approval", emit an awaiting_user notification (Issue #28)**: this tells the attention watcher that the user is stopped while awaiting merge approval:
  ```bash
  bash tools/journal_append.sh notify_sent kind=awaiting_user task_id=<task_id> gate=ci_green_merge_gate note="PR #<PR> CI green, awaiting merge approval"
  ```
  The classifier in the parallel runtime PR picks this up as `secretary_awaiting_user` (default severity `urgent`). See the "notify when the secretary is waiting on a user decision" section of CLAUDE.md. Failure cases such as `PR_MERGE_WATCH_TIMEOUT` are out of scope (those go to human judgment via a different path, not awaiting_user).
- **Only when you want to wait for merge**, pass `-MergeWatch` (PowerShell) / `--merge-watch` (POSIX). After CI passes, it polls `gh pr view --json mergedAt` for 24h and calls `tools/run_complete_on_merge.py` on the first observed merge (Issue #317). During merge-watch the pr-watch process stays alive; on merge observation it appends a `pr_merged` event to events and then returns.
- run.status **stays at REVIEW** (so that GitHub PR review feedback can be handled in the same pane; the transition to COMPLETED happens in 2b-ii via `update_run_status('<task_id>', 'completed')`). Do not edit markdown directly.
- **Do not close the pane yet**: do not send `CLOSE_PANE` immediately after PR creation. worktree removal and Worker Directory Registry updates are deferred until 2b-ii.
- If PR review feedback arrives, follow flow 2c and send a `send_message` follow-up instruction to the same worker so they push fix commits in the same pane (avoid respawning a new worker — you would pay the cost of rebuilding Issue / diff / judgment boundaries).
- **For dogfood-target PRs (Issue #338)**: in `registry/dogfood_pending.md`, find the row for the relevant task_id with `status=pending`, then (a) fill in `impl_pr=#<PR>`, (b) create the paired follow-up issue with `gh issue create --title "dogfood follow-up: <surface>" --body-file <rendered template>` (template: [`.claude/skills/org-delegate/references/dogfood-issue-template.md`](../org-delegate/references/dogfood-issue-template.md)), (c) fill in the resulting issue number as `dogfood_issue=#<MMM>` and transition `status` from `pending -> open`, (d) append `Paired dogfood issue: #<MMM>` to the end of the PR body. The SoT for the full protocol is [`.claude/skills/org-delegate/SKILL.md`](../org-delegate/SKILL.md) Step 1.8.

### Warning: cwd when launching pr-watch

`tools/pr-watch.sh` / `tools/pr-watch.ps1` / `tools/pr_watch.py` open `state.db` via a relative path, so if the cwd at launch is not the ja root, writing the CI-completion event will crash and peer notifications (`CI_COMPLETED` / `PR_MERGED` etc.) will not fire. If you just `cd .worktrees/...` beforehand, always launch as `cd <ja-root> && nohup bash tools/pr-watch.sh <PR> ...`. A root fix (cwd-independence) is in progress in Issue #398.

### Warning: when launching via the Claude Code Bash tool

When the Lead launches `tools/pr-watch.sh` / `tools/pr-watch.ps1` from inside Claude Code, always submit with the Bash tool's `run_in_background: true`. With `nohup ... &` + `disown` alone, the Claude Code bash sub-shell is short-lived and pr-watch gets killed along with it as soon as the call returns, so neither the CI-completion event nor the peer notification fires (the process disappears quietly and only an empty log file is left behind, which is hard to notice). This trap is especially easy to fall into in fresh sessions right after `/clear` / [`/secretary-resume`](../secretary-resume/SKILL.md). With `run_in_background: true`, you get an automatic completion notification (with exit code), so the CI-completion detection path is covered there as well.

## 2c. Review feedback / CI failure feedback loop

If a human provides feedback / fix instructions, or if CI fails and the user says "have them fix it":

- Send additional instructions to the worker via renga-peers (`to_id="worker-{task_id}"`).
- If the additional instructions are a trivial fix (CI output formatting / typo / comment fix etc.), explicitly state **verification depth `minimal`** and tell them to reply with only a single line `done: {short commit SHA} {changed file names}` (the format follows [`.claude/skills/org-delegate/references/instruction-template.md`](../org-delegate/references/instruction-template.md) / [`.claude/skills/org-delegate/references/worker-claude-template.md`](../org-delegate/references/worker-claude-template.md)).
- **Move the run back to IN_PROGRESS via the DB** (`run.status='in_use'`, do not edit markdown directly. The post-commit hook regenerates `.state/org-state.md`):
  ```bash
  python -c "
  from pathlib import Path
  from tools.state_db import connect
  from tools.state_db.writer import StateWriter
  conn = connect('.state/state.db')
  with StateWriter(conn, claude_org_root=Path('.')).transaction() as w:
      w.update_run_status('<task_id>', 'in_use')
  "
  ```
- Append events to the DB events table (`bash tools/journal_append.sh ...`) (`tools/journal_append.py` is already routed to the DB).
- The JSON snapshot is automatically regenerated by the StateWriter post-commit hook (Issue #284).
- (The pane is alive, so the worker simply continues working.)
- **Do not respawn a new worker** (T6 contract): Issue / diff / judgment boundaries would be lost. Only when the worker becomes unresponsive does the Lead make that call.

Once a new completion report arrives from the worker, proceed again through `.claude/skills/org-delegate/SKILL.md` Step 5 (2a) -> user approval -> 2b-i of this skill.

## 2b-ii. Final close phase (run once the close conditions are met)

Close conditions (same as contract §1.5; at least one must be satisfied):
- The PR has been merged (confirmed by `gh pr view {n} --json mergedAt` etc., or the Lead receives a merge notification, or notified via the `pr_merged` event of `pr-watch --merge-watch`).
- The user explicitly says "you can close it", "close it", "merged", etc.
- 24-48 hours of long idle with no review activity (left to the Lead's operational discretion; not automated).

Actions to perform:

- DB-update the relevant run to **COMPLETED** (use the `update_run_status('<task_id>', 'completed')` block described below). Do not edit markdown directly.
- Final-update the worker's state file (append the last Progress Log entry, etc.).
- **The worker state file (`.state/workers/worker-{task_id}.md`) is automatically moved to `.state/workers/archive/` by StateWriter's post-commit on `update_run_status('<task_id>', 'completed')`** (Issue #284. `archive/` is lazily created if absent; re-invocation is idempotent. The dashboard does not treat files in this directory as live workers (Issue #264). They are not deleted, in case the journal / retro needs to reference history.)
- Append events to the DB events table (`bash tools/journal_append.sh ...`).
- Ask the dispatcher to close the pane:
  `CLOSE_PANE: please close pane {pane_id}.`
- **Post-processing per directory pattern** (do at the same time):
  - Pattern A (project directory): keep the directory (reused for the next task).
  - Pattern B (worktree): run `git -C {workers_dir}/{project_slug}/ worktree remove .worktrees/{task_id}`. Keep the branch (do not delete the branch even after merge, for PR history).
    - **For self-edit (`pattern_variant='live_repo_worktree'`)**: the worktree base is `{claude_org_path}`, so run `git -C {claude_org_path} worktree remove .worktrees/{task_id}` (Issue #289). Keep the branch likewise.
  - Pattern C (ephemeral, `pattern_variant='ephemeral'`): keep the directory (consider manual deletion only if capacity becomes an issue).
  - **Special cleanup for Pattern C (`gitignored_repo_root`, claude-org self-edit) (Issue #478)**: `worker_dir` is the claude-org-ja repo root itself, so neither worktree remove nor dir removal applies, and `{claude_org_root}/CLAUDE.local.md` (the Worker-instruction brief) lingers. If it remains, on the next `/org-start` the Lead loads a contradictory "Lead and Worker" role identity. **At close, call `cleanup_pattern_c_local_md()` from `tools/run_complete_on_merge.py` to delete the brief** (bundled into the StateWriter block below). Detection is `runs.pattern == 'C'` AND `worker_dirs.abs_path == claude_org_root`, and it is a no-op for ephemeral C / Patterns A and B. One `pattern_c_cleanup` row (payload: `task` / `removed_path` / `mode`) is appended to `events`. Idempotent (`mode=skip` when the file is absent). When a PR-driven close calls `tools/run_complete_on_merge.py --pr <PR>`, the same cleanup runs automatically at merge-record time, but gitignored tasks rarely produce a PR, so the explicit call from the StateWriter block below is the primary route. `.claude/settings.local.json` is out of scope (a separate Issue) because it needs worker-origin vs. Lead-origin discrimination.
- **When closing a dogfood-target PR's paired issue (Issue #338)**: because the implementation PR's merge and the paired follow-up issue's close can have independent lifecycles, this skill does not guarantee "do `consumed -> closed` on implementation-PR merge". The terminal transition `consumed -> closed` is the Lead's register-hygiene responsibility and is collected via [`.claude/skills/org-delegate/SKILL.md`](../org-delegate/SKILL.md) Step 1.8 §"consumed -> closed observation timing" (on register write + at `/org-resume` startup, check paired-issue state with `gh issue view`). If this skill happens to observe the relevant row at PR-merge time, it may invoke the hygiene step opportunistically.
- **For PR-driven closes, call `tools/run_complete_on_merge.py`** (Issue #317. The merge-watch loop of `pr-watch --merge-watch` invokes it automatically, so manual execution is normally unnecessary; call it explicitly only when merge-watch was skipped or when the merge was observed manually):
  ```bash
  python tools/run_complete_on_merge.py --pr <PR>
  ```
  This calls `gh pr view <PR> --json url,state,mergedAt,mergeCommit,headRefName` once and, if the PR is merged, updates `pr_state='merged'` / `commit_short` / `pr_url` / `completed_at` via `StateWriter.transaction()` and appends a single `pr_merged` event (payload: `task` / `pattern` / `auto_completed`). Re-invocation is idempotent (does not write a duplicate event). task_id is auto-resolved from `runs.pr_url` / `runs.branch` (restricted to active runs); if resolution fails, pass `--task-id` explicitly.
  - **The helper does not touch runs.status**: dispatcher-side pane close / worker_closed / worker-state final update are required (delegation-lifecycle-contract §T5). The helper only records the merge fact; the status flip and worker_dir removal are done by the Lead via the StateWriter below.
  - **CLI exit codes**: `merged` / `already` / `not_yet` are exit 0; `no_run` (no matching row in runs) is exit 3 and counted as failure. Check the exit code when running manually.
- **Pattern B / C registry-entry deletion and final close are done by a separate StateWriter call** (do not edit markdown directly. run_complete_on_merge has already written `pr_state='merged'` and `completed_at`, so here we only do the status flip and worker_dir removal):
  ```bash
  python -c "
  from pathlib import Path
  from tools.state_db import connect
  from tools.state_db.writer import StateWriter
  from tools.run_complete_on_merge import cleanup_pattern_c_local_md
  conn = connect('.state/state.db')
  with StateWriter(conn).transaction() as w:
      w.update_run_status('<task_id>', 'completed')  # post-commit hook archives worker-{task}.md
      w.remove_worker_dir('<abs>')  # Pattern B / C only
  # Issue #478: delete the CLAUDE.local.md of a Pattern C gitignored_repo_root run
  # (actual deletion only when runs.pattern=='C' AND worker_dir==root; no-op otherwise)
  cleanup_pattern_c_local_md(conn, task_id='<task_id>', claude_org_root=Path('.').resolve())
  "
  ```
  The legacy hand-rolled completion script is preserved at `docs/legacy/pr-merge-completion-manual.md`. The standard route is `tools/run_complete_on_merge.py` above; reaching for the museum copy is allowed only after opening an issue and getting user judgment (same pattern as PR #315).
  - Pattern A: lifecycle stays `active`; with run.status='completed' the snapshotter renders it as available-equivalent.
  - Pattern B / C: the physical dir is handled separately (worktree remove / dir retention). For registry-entry deletion, add `w.remove_worker_dir('<abs>')` inside the with block above.
- The JSON snapshot is automatically regenerated by the StateWriter post-commit hook (Issue #284).
