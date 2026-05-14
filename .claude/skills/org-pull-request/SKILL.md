---
name: org-pull-request
description: >
  After user approval of a Worker completion report, the Lead handles push / PR creation / CI monitoring / the review feedback loop /
  and final close-out after PR merge. Trigger conditions:
  (1) immediately after receiving a completion report from a Worker and the user gives explicit approval such as "OK" or "Proceed",
  (2) when review feedback or a CI failure arrives on a GitHub PR and the Lead sends a follow-up fix request back to the Worker,
  (3) when the PR is merged and the final close-out condition is satisfied.
  The initial action of simply "asking a Worker to do work" belongs to org-delegate, not this skill.
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

# org-pull-request: PR Creation, Review, and Post-Merge Close-Out

Handles the flow from Worker completion report → user approval → push / PR creation / CI monitoring / review feedback loop / final close-out after PR merge. **Lead-only**. This skill assumes the state is already "Worker has reported completion and the user has given explicit approval." For the pre-approval phase (issuing ack, transition to REVIEW, user report), see `.claude/skills/org-delegate/SKILL.md` Step 5 (2a).

> **T5 contract**: The canonical spec for the `awaiting_review → complete` transition handled by this skill is
> [`docs/contracts/delegation-lifecycle-contract.md`](../../../docs/contracts/delegation-lifecycle-contract.md) §2 T5 / T6 / §1.5 close-condition.
> That contract is the SoT that pins close-condition / pane discipline / the no-respawn rule.
> This SKILL covers procedure; the contract covers invariants.

> **ack ≠ user approval**: By the time this skill is triggered, ack has already been issued (`.claude/skills/org-delegate/SKILL.md` Step 5 step 1 / [`.claude/skills/org-delegate/references/ack-template.md`](../org-delegate/references/ack-template.md)). Only issue push / `gh pr create` / `tools/pr-watch.*` after user approval.

## 2b-i. PR Creation Phase (Execute Immediately)

Trigger this immediately after the user gives **explicit approval** such as "OK", "Reviewed", "No issue", or "Proceed":

- The Lead pushes and creates the PR as needed (the Worker does not have permission for `git push` or PR creation). Follow `feedback_pr_issue_english` for PR body language rules (PRs / Issues are in English)
- **As soon as the PR number is known, immediately back-fill `runs.pr_url` / `runs.branch` with `tools/set_run_pr_open.py`** (Issue #323):
  ```bash
  python tools/set_run_pr_open.py --task-id <task_id> --pr <PR>
  ```
  This fetches `gh pr view <PR> --json url,headRefName` once and overwrites `runs.pr_url` and `runs.branch` via `StateWriter.set_run_pr`. Re-invocation is idempotent (same-value overwrite, no event append). Without this, downstream `tools/run_complete_on_merge.py` cannot resolve `runs.pr_url`, exits with `no_run` (exit 3), and `-MergeWatch` auto-completion fails
- Append an event to the DB `events` table (push / PR open, etc., via `bash tools/journal_append.sh ...`)
- Once the PR number is known, monitor CI with `tools/pr-watch.ps1 <PR>` (Windows) / `tools/pr-watch.sh <PR>` (POSIX). On completion, `ci_completed` is automatically recorded in `events`. When CI completes, pr-watch **returns** (it does not hold the session synchronously, so the flow can proceed to review feedback loop 2c or manual close 2b-ii)
- **In a renga environment, pr-watch sends a peer message to Lead when CI completes / merge is detected / 24h timeout hits** (Issue #326). The Lead does not poll the `events` table. Instead, proceed when `<channel source="renga-peers"> CI_COMPLETED: PR #<n> ...` arrives (and likewise `PR_MERGED: PR #<n>` / `PR_MERGE_WATCH_TIMEOUT: PR #<n>` / `PR_MERGED_NO_RUN: PR #<n>`). On `CI_COMPLETED` → ask the user for merge approval → user approves → on `PR_MERGED`, proceed to 2b-ii post-merge cleanup. `PR_MERGED_NO_RUN` is a failure path where merge was observed but no matching run row was found (`tools/run_complete_on_merge.py` ended with `no_run`); do not proceed to post-merge cleanup, handle with human judgment. In plain shell / CI with `RENGA_SOCKET` unset, peer-send is a silent noop and the flow falls back to polling the `events` table as before
- **Emit the awaiting_user notification just before asking the user for merge approval after CI_COMPLETED (Issue #28)**: tell the attention watcher that the user is stopped waiting on a merge approval:
  ```bash
  bash tools/journal_append.sh notify_sent kind=awaiting_user task_id=<task_id> gate=ci_green_merge_gate note="PR #<PR> CI green, awaiting merge approval"
  ```
  The classifier in the parallel runtime PR picks it up as `secretary_awaiting_user` (default severity `urgent`). See the "Notify when the Secretary is waiting on a user judgment" section in CLAUDE.md. Failure paths such as `PR_MERGE_WATCH_TIMEOUT` are out of scope (they go through a separate human-judgment path, not awaiting_user).
- Add `-MergeWatch` (PowerShell) / `--merge-watch` (POSIX) **only when you want to wait for merge**. After CI passes, it polls `gh pr view --json mergedAt` for 24h and calls `tools/run_complete_on_merge.py` on first merge detection (Issue #317). During merge-watch, the pr-watch process stays alive and returns only after appending a `pr_merged` event to `events`
- Keep `run.status` **at REVIEW** (so the same pane can handle GitHub-side PR review feedback if it arrives. Transition to COMPLETED happens in 2b-ii by calling `update_run_status('<task_id>', 'completed')`). Do not edit markdown directly
- **Do not close the pane yet**: do not send `CLOSE_PANE` immediately after PR creation. Delay worktree removal and Worker Directory Registry updates until 2b-ii
- If PR review feedback arrives, follow flow 2c and send follow-up instructions to the same Worker with `send_message`, then have it stack fix commits in the same pane (avoid dispatching a new Worker; that would pay the cost of reconstructing the Issue / diff / decision boundary)
- **For a dogfood-target PR (Issue #338)**: in `registry/dogfood_pending.md`, find the `status=pending` row for this `task_id` and (a) fill in `impl_pr=#<PR>`, (b) create the paired follow-up issue with `gh issue create --title "dogfood follow-up: <surface>" --body-file <rendered template>` (template: [`.claude/skills/org-delegate/references/dogfood-issue-template.md`](../org-delegate/references/dogfood-issue-template.md)), (c) fill the created issue number into `dogfood_issue=#<MMM>` and transition `status` from `pending → open`, (d) append `Paired dogfood issue: #<MMM>` to the bottom of the PR body. The full protocol's SoT is [`.claude/skills/org-delegate/SKILL.md`](../org-delegate/SKILL.md) Step 1.8

## 2c. Review Feedback / CI Failure Feedback Loop

When a human gives feedback or fix instructions, or when CI fails and the user says "have them fix it":

- Send additional instructions to the Worker over renga-peers (`to_id="worker-{task_id}"`)
- If the added instruction is a trivial fix (CI output formatting / typo / comment edit, etc.), explicitly set verification depth to `minimal` and instruct the Worker to return completion in a single line as `done: {short commit SHA} {changed filename}` (format follows [`.claude/skills/org-delegate/references/instruction-template.md`](../org-delegate/references/instruction-template.md) / [`.claude/skills/org-delegate/references/worker-claude-template.md`](../org-delegate/references/worker-claude-template.md))
- **Return the run to IN_PROGRESS via DB** (`run.status='in_use'`, direct markdown edits are forbidden. The post-commit hook regenerates `.state/org-state.md`):
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
- Append an event to the DB `events` table (`bash tools/journal_append.sh ...`) (`tools/journal_append.py` already routes to DB)
- The JSON snapshot is automatically regenerated by the StateWriter post-commit hook (Issue #284)
- (Because the pane is still alive, the Worker continues in place)
- **Do not respawn a new Worker** (T6 contract): that would lose the Issue / diff / decision boundary. Only the Lead decides otherwise if the Worker becomes non-responsive

When a new completion report comes back from the Worker, go again in this order: `.claude/skills/org-delegate/SKILL.md` Step 5 (2a) → user approval → this skill 2b-i.

## 2b-ii. Final Close-Out Phase (Execute When a Close Condition Is Met)

Close condition (same as contract §1.5; satisfy at least one):
- The PR is merged (confirm with `gh pr view {n} --json mergedAt`, etc., or the Lead receives a merge notice, or `pr-watch --merge-watch` reports a `pr_merged` event)
- The user explicitly says "you can close it", "close it", "already merged", etc.
- Long idle with no review activity for 24-48 hours (Lead operational judgment as needed; do not automate)

Actions:

- Update the target run to **COMPLETED** in the DB (done via the `update_run_status('<task_id>', 'completed')` block below). Do not edit markdown directly
- Final-update the Worker state file (append the last Progress Log, etc.)
- **The Worker state file (`.state/workers/worker-{task_id}.md`) is automatically moved into `.state/workers/archive/` by StateWriter in the post-commit hook of `update_run_status('<task_id>', 'completed')`** (Issue #284. `archive/` is created lazily if absent; re-invocation is idempotent. The dashboard does not treat files in this directory as live Workers (Issue #264). Do not delete them; journal / retro may need the history)
- Append an event to the DB `events` table (`bash tools/journal_append.sh ...`)
- Ask the Dispatcher to close the pane:
  `CLOSE_PANE: Please close pane {pane_id}.`
- **Run cleanup based on directory pattern** (at the same time):
  - Pattern A (project directory): keep the directory (reuse it for the next task)
  - Pattern B (worktree): run `git -C {workers_dir}/{project_slug}/ worktree remove .worktrees/{task_id}`. Keep the branch (do not delete it even after merge; preserve PR history)
    - **For self-edit (`pattern_variant='live_repo_worktree'`)**: because the worktree base is `{claude_org_path}`, run `git -C {claude_org_path} worktree remove .worktrees/{task_id}` (Issue #289). Keep the branch here as well
  - Pattern C (ephemeral): keep the directory (consider manual deletion only if disk usage becomes a problem)
- **On paired-issue close for a dogfood-target PR (Issue #338)**: because the implementation PR merge and the paired follow-up issue close can have independent lifecycles, this skill does not guarantee the `consumed → closed` transition simply because the implementation PR was merged. The terminal `consumed → closed` transition is the Lead's register-hygiene responsibility, collected via [`.claude/skills/org-delegate/SKILL.md`](../org-delegate/SKILL.md) Step 1.8 §`consumed → closed` observation timing (verify the paired-issue state with `gh issue view` at register-write time + at `/org-resume` startup). If this skill happens to observe the relevant row at PR-merge time, opportunistically run the hygiene step
- **For PR-based close-out, call `tools/run_complete_on_merge.py`** (Issue #317. Normally no manual invocation is needed because the merge-watch loop in `pr-watch --merge-watch` starts automatically, but call it explicitly if merge-watch was skipped or merge was observed manually):
  ```bash
  python tools/run_complete_on_merge.py --pr <PR>
  ```
  This fetches `gh pr view <PR> --json url,state,mergedAt,mergeCommit,headRefName` once. If the PR is merged, it updates `pr_state='merged'` / `commit_short` / `pr_url` / `completed_at` through `StateWriter.transaction()` and appends one `pr_merged` event (payload: `task` / `pattern` / `auto_completed`). Re-invocation is idempotent (no duplicate event). `task_id` is resolved automatically from `runs.pr_url` / `runs.branch` (active runs only); if resolution fails, specify `--task-id`
  - **The helper does not touch `runs.status`**: Dispatcher-side pane close / worker_closed / final Worker-state update are still required (delegation-lifecycle-contract §T5). The helper records only the merge fact; the Lead performs the status flip and Worker-dir removal with the StateWriter block below
  - **CLI exit codes**: `merged` / `already` / `not_yet` exit 0; `no_run` (no matching row in `runs`) exits 3 and is treated as failure. Check the exit code in manual operation
- **For Pattern B / C, remove the registry entry and perform final close separately via StateWriter** (direct markdown edits forbidden. Since `run_complete_on_merge` already wrote `pr_state='merged'` and `completed_at`, only perform the status flip and Worker-dir removal here):
  ```bash
  python -c "
  from tools.state_db import connect
  from tools.state_db.writer import StateWriter
  conn = connect('.state/state.db')
  with StateWriter(conn).transaction() as w:
      w.update_run_status('<task_id>', 'completed')  # post-commit hook が worker-{task}.md を archive
      w.remove_worker_dir('<abs>')  # パターン B / C のみ
  "
  ```
  The legacy hand-rolled completion script is stored in `docs/legacy/pr-merge-completion-manual.md`. The standard path is the `tools/run_complete_on_merge.py` above. Reach for the museum copy only after filing an Issue and asking for user judgment (same pattern as PR #315)
  - Pattern A: keep `lifecycle='active'`, with `run.status='completed'` so the snapshotter renders it equivalent to available
  - Pattern B / C: handle the physical dir separately (worktree remove / keep dir). For registry entry removal, add `w.remove_worker_dir('<abs>')` inside the `with` block above
- The JSON snapshot is automatically regenerated by the StateWriter post-commit hook (Issue #284)
---
