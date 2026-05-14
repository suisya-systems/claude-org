---
name: org-delegate
description: >
  Dispatch a Worker Claude to delegate work. The Lead is the command tower;
  hands-on execution is, in principle, left to Workers.
  Fires when a user request involves actual hands-on work such as
  file edits, implementation, or investigation.
effort: medium
allowed-tools:
  - Read
  - Edit
  - Write
  - Bash(python tools/gen_delegate_payload.py:*)
  - Bash(py -3 tools/gen_delegate_payload.py:*)
  - Bash(bash tools/journal_append.sh:*)
  - Bash(py -3 tools/journal_append.py:*)
  - Bash(python -m tools.state_db.importer:*)
  - Bash(git fetch:*)
  - Bash(git log:*)
  - Bash(gh issue create:*)
  - mcp__renga-peers__send_message
  - mcp__renga-peers__inspect_pane
  - mcp__renga-peers__list_peers
  - mcp__renga-peers__list_panes
---

# org-delegate: Worker dispatch

Delegate work to a Worker Claude. The Lead performs only task decomposition and dispatch-payload generation; pane spawning and instruction delivery are delegated to the Dispatcher. This minimizes the time the Lead is locked.

> **Scope of this SKILL**: Only the "initial leg" of dispatch (task identification → dispatch-payload generation → handoff of DELEGATE to the Dispatcher → greeting after the Worker is started → ack and REVIEW transition when progress / completion reports come in). The following are separated into other skills / references:
> - **Worker spawning, instruction sending, and state recording procedures** → [`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md) (Dispatcher-exclusive)
> - **Post-user-approval push / PR / CI watch / review-comment loop / post-merge close** → [`.claude/skills/org-pull-request/SKILL.md`](../org-pull-request/SKILL.md)
> - **Escalation of judgment requests / scope expansion / blockers from Workers** → [`.claude/skills/org-escalation/SKILL.md`](../org-escalation/SKILL.md)
> - **Minimum 3 elements of an ack message and per-kind example texts** → [`.claude/skills/org-delegate/references/ack-template.md`](references/ack-template.md) (single SoT)

> **state-db cutover (M4, Issue #267 / #284)**: All writes to structured sections **must go through `StateWriter.transaction()`**. A post-commit hook auto-regenerates `.state/org-state.md` / `.state/org-state.json` from the DB, and calling `update_run_status('<task_id>', 'completed')` automatically moves `.state/workers/worker-<task_id>.md` to `.state/workers/archive/`. Direct markdown edits are detected by drift_check. The SoT for events is the DB `events` table (`tools/journal_append.sh` / `.py` already route to the DB). When the DB is missing, build it with `python -m tools.state_db.importer --db .state/state.db --rebuild --no-strict`.

## Lead / Dispatcher division of roles

| Step | Owner |
|---|---|
| Project name resolution | **Lead** |
| work-skill search | **Lead** |
| Task decomposition / dispatch-payload generation | **Lead** (`gen_delegate_payload.py`) |
| DELEGATE send | **Lead** (the Lead is released at this point) |
| Pane spawn / peer wait / instruction send / state recording | **Dispatcher** ([`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md)) |
| Dispatch-complete report back to the Lead | **Dispatcher** |
| Receiving progress / completion / escalation reports from Workers | **Lead** |
| Pane close on Worker completion | **Dispatcher** (on `CLOSE_PANE` request from the Lead) |

## Pre-delegation checklist (executed by the Lead)

Before entering task decomposition, check the request from the following angles. If any apply, ask the user back.

| Check item | Situations to confirm | Example |
|---|---|---|
| **Ambiguous terms / abbreviations** | When a tool name, service name, or abbreviation could mean multiple things | "gog" → Google OAuth? gog CLI? |
| **OS-specific preconditions** | When producing OS-specific deliverables, default settings must be made explicit | Mac=zsh, Windows=py -3, path separator |

- When there is an ambiguous term: ask the user "Do you mean XX by YY?" before proceeding
- For OS-specific tasks: include OS-specific preconditions in the Worker instructions when generating the payload

### Initial-step checklist for incorporation / sync tasks

For incorporation / sync tasks that bring a source (review results / another branch / state of another repository) into a destination, **when the source commit is more than N commits ahead of the destination's current state, consider selective merge (cherry-pick / apply only the necessary hunks) as the initial move**. A byte-identical cp risks mechanically overwriting Codex iterative review fixes.

| Angle | Check | Action |
|---|---|---|
| Divergence between source and destination | Verify both directions with `git log <source>..<destination>` / `git log <destination>..<source>` | If both directions have diverged, prohibit cp and adopt selective merge |
| Additional fixes on the destination side | Whether Codex review fixes / Blocker fixes are stacked on the destination branch | If they are, do not mechanically overwrite with cp (cherry-pick or hunk-level apply) |

Background: There have been past incidents where cp mechanically reverted destination-side fixes (a destination-side credential-exposure Blocker fix nearly got reverted). Require the Worker brief to specify "no cp as the initial step / state the incorporation strategy explicitly".

## Step 0: Project name resolution (executed by the Lead)

Identify the project from the user's request:

1. Read `registry/projects.md`
2. Identify the matching project from keywords in the request (match against alias / project name / description)
3. If identified, use that path
4. If not identifiable, present the list of registered project aliases and let the user choose
5. For a new project:
   - Confirm the path with the user
   - Estimate alias / description / typical work examples, confirm with the user, then append to `registry/projects.md`

## Step 0.5: work-skill search (executed by the Lead)

Before task decomposition, search for any related existing work-skills. Matched work-skills are included as reference information in the Worker instructions.

1. Enumerate all SKILL.md files under `.claude/skills/`
2. Compare each SKILL.md's frontmatter (`type` / `description` / `triggers`) against the task content. The `org-` prefix denotes org-operation skills and is excluded from the search
3. Include any relevant candidates (exact match not required; for multiple matches, include all in relevance order)

**When matches are found:**
- Notify the human: "Found a related work-skill: `{skill-name}` — including as reference information"
- Pass the work-skill's SKILL.md path to `gen_delegate_payload.py` via the `--knowledge` flag. The Stage 2 brief renderer embeds that path into CLAUDE.md / CLAUDE.local.md as `[references].knowledge`. For multiple matches, repeat: `--knowledge <path1> --knowledge <path2>`
- Also note the presence of the reference skill in the Worker instructions (instruction-template)

Do not copy the work-skill's procedure verbatim. Present it as reference information and let the Worker decide.

## Step 0.6: Pre-fetch for release-class tasks (executed by the Lead)

Tasks that cut a `release/*` branch assume the worker branches from **the target project's latest `main`**. Since Phase 2 worker git guardrails, the worker-side `.claude/settings.json` `permissions.deny` includes `Bash(git fetch)` / `Bash(git pull)` / `Bash(git remote update)`. If you dispatch a worker while local `origin/main` is stale, a "git fetch deny" BLOCKER fires within 5 minutes of work, costing over 10 minutes of Lead round-trip (claude-org-runtime v0.1.10 case).

For this reason, **only for release-class tasks**, the Lead performs the fetch on its side before `gen_delegate_payload.py preview` / `apply`:

```bash
# Local root of the target project (the repository where the release is cut)
cd <target project root>

# Pull in the latest origin/main and fast-forward local main
git fetch origin
git pull --ff-only origin main
```

### Trigger conditions

Fire only when one of the following applies:

- The task description / commit-prefix / planned branch contains words signaling a release promotion such as `release`, `release/`, `vX.Y.Z`
- The target files include release-promotion work such as promoting `CHANGELOG.md`, bumping `__about__.__version__` / `pyproject.toml`'s `version`
- The task_id contains `release` (e.g., `runtime-0-1-10-release`)

Do not execute for ordinary feature / fix / docs tasks. The worker permissions deny is an intentional design that "the worker does not pull in mainline history and self-contains within its sandbox"; only release is the exception flow that requires "branching from the latest main".

### Background

For the detailed history (measured 5-minute-in BLOCKER → 10-minute additional loss for workers, comparison of 4 response options, permissions-side root cause), refer to the "When creating a release branch, the Lead performs `git fetch` on its side" section of [`knowledge/curated/release-process.md`](../../../knowledge/curated/release-process.md).

## Step 0.7 / 1 / 1.5 / 2: Generate the dispatch payload in 1 command (Issue #283)

Step 0.7 (gitignore pre-check) / Step 1 (Pattern determination) / Step 1.5 (Worker directory preparation + role decision + settings generation) / Step 2 (DELEGATE body assembly) are **all handled by `tools/gen_delegate_payload.py`**. The Lead's responsibility is only task identification (Step 0), work-skill search (Step 0.5), target-file extraction, and depth judgment.

### Standard flow (recommended)

```bash
# 1. preview: completely non-destructive. Only confirms the DELEGATE body and the list of files to be created
python tools/gen_delegate_payload.py preview \
    --task-id <task-id> --project-slug <slug> \
    --target <path>... --description "<desc>" \
    --verification-depth full

# 1.5. Step 1.7 gate: evaluate the Codex design review trigger conditions on the preview output
#      Only when applicable, run a design review with codex exec and pass the summary
#      to apply via --impl-guidance or --knowledge (see Step 1.7 below)

# 2. apply: reserve in state.db with runs.status='queued' + place CLAUDE.md/CLAUDE.local.md
#    + run claude-org-runtime settings generate + emit send_plan.json
python tools/gen_delegate_payload.py apply \
    --task-id <task-id> --project-slug <slug> \
    --target <path>... --description "<desc>" \
    --verification-depth full

# 3. Copy-paste the send_plan.json from the apply output into the MCP call
#    cat <worker_dir>/send_plan.json
#    → mcp__renga-peers__send_message(to_id="dispatcher", message=<message>)
```

`apply` performs **only T1 reservation** (`runs.status='queued'`). Activation into Active Work Items is the Dispatcher's T2 ([`docs/contracts/delegation-lifecycle-contract.md`](../../../docs/contracts/delegation-lifecycle-contract.md)), so this skill does not touch it. On failure, leave the queue as is and escalate to the Secretary for judgment.

### Frequently used flags

- `--mode edit|audit` (default `edit`): For **read-only** audit tasks on claude-org, explicitly specify `--mode audit`
- `--branch <name>`: Override planned_branch. Default is `feat/<task-id>` (becomes `fix/<task-id>` if the description contains "fix" / "bug" / "修正")
- `--commit-prefix "<prefix>"`: When omitted, inferred from the head of project_slug (e.g., `claude-org-ja` → `feat(claude):`)
- `--closes-issue N` / `--refs-issues N1 N2`: Embeds "Closes #N" / "Refs #N1 #N2" into the brief
- `--impl-target <path>` / `--impl-guidance "<text>"` / `--knowledge <path>`: optional `[implementation]` / `[references]` sections
- `--skip-settings`: Skip `claude-org-runtime settings generate` (for environments without the CLI)
- `--from-toml <path>`: Take an existing `worker_brief.toml` as input. CLI flags override the TOML

### Details on Pattern / role / branch determination

For the determination logic (Pattern A vs B vs C / gitignored sub-mode / role table / planned_branch / required lines in the DELEGATE body), see [`.claude/skills/org-delegate/references/delegate-flow-details.md`](references/delegate-flow-details.md). For the special case of self-edit tasks (Issue #289, `pattern_variant='live_repo_worktree'`), see [`.claude/skills/org-delegate/references/claude-org-self-edit.md`](references/claude-org-self-edit.md) §3.

### Target-file extraction

"Target files" are extracted by the Lead from the task description (paths explicitly stated in the request text, Issue body, or user utterances; no mechanical determination). For tasks whose target files cannot be identified (pure investigation, new-creation tasks with no fixed target path, etc.), `--target` need not be passed.

### When the standard route returns unexpected output

When the standard route (`gen_delegate_payload.py apply`) returns unexpected output (Pattern misjudgment / resolver error / brief inconsistency, etc.), the Secretary **must not manually reproduce the same work**. File an Issue as a resolver bug, and pause delegation of that task until the resolver is fixed. Manual fallback is out of scope for this skill. In environments without the CLI, limit yourself to the `--skip-settings` flag. A museum copy of the historic hand-typed route exists at `docs/legacy/hand-typed-delegate-path.md`, but it is prohibited from reference in standard operations.

## Step 1.7: Codex design review trigger (executed by the Lead, Issue #337)

Looking at the `preview` output's `description` / `--target` count / referenced documents, if **at least one** of the following applies, run a Codex design review before `apply`. This gate is based on the track record from the Curator session #18 retrospective (Issue #283 / session #12) where "a pre-Codex design review caught 2 Blockers + 5 Majors in one round".

| Trigger | Determination method |
|---|---|
| Estimated effort ≥ 3h | Lead judges from the task description (user input / scale sense of preview) |
| Introduction of a new module / new tool | Description contains "新規" / "new tool" / "新ツール" / "新規導入" etc., or the files to be created in the preview are all on new paths |
| File changes ≥ 3 | Count of `--target` + edit targets listed in the preview brief |
| Reference to contract documents under `docs/contracts/` | Description / brief / `--knowledge` references `docs/contracts/` |

**Execution procedure:**

```bash
codex exec --skip-git-repo-check "Design review for <task-id>.\
  Task description: <description>.\
  Target files: <target paths>.\
  Related contracts / references: <docs paths>.\
  Classify pre-design findings as Blocker / Major / Minor / Nit. For each finding, cite the target file:line and the rationale. Be concise."
```

Do not use the `codex:rescue` skill (prohibited per CLAUDE.local.md). Only direct `codex exec` invocation.

**Incorporating the review summary:**

- Save the summary to `tmp/codex-review-{task-id}.md`
- When calling `apply`, pass **`--impl-guidance "<summary body>"`**. This expands the summary body into the brief's `[implementation].guidance` so the Worker can read it directly
- As a supplement, adding `--knowledge tmp/codex-review-{task-id}.md` lists the path under the brief's `[references].knowledge`, letting the Worker refer to the full text as needed (`gen_worker_brief.py` only lists the path, it does not embed the body). The responsibility for reliably delivering the body to the Worker lies on the `--impl-guidance` side
- If a Blocker / Major is flagged, escalate to the user to confirm direction-change possibility before proceeding to apply

**helper script:** Optional per the Issue #337 acceptance, not implemented in this PR. The Secretary judges the above table manually.

## Step 1.8: dogfood follow-up issue protocol (Lead + org-pull-request coordination, Issue #338)

For PRs that introduce a new tool / runtime / workflow, create a "dogfood follow-up" issue paired with the implementation PR, and explicitly earmark the next delegation that actually uses that new tool as a **dogfood pass**. This protocol is based on the phenomenon in the Curator session #18 retrospective where "PR #288 only surfaced 4 categories of defects on first real use" (also reproduced in session #11).

### Trigger conditions

Fires when the task is one of the following:

- Adding a new CLI tool / script (`tools/*.py`, `tools/*.sh`, `tools/*.ps1`, etc.)
- Introducing a new runtime / new workflow / new protocol
- Re-design of an existing tool that involves a breaking change

### The Lead's (org-delegate) responsibilities

The dogfood protocol spans **2 delegations**: (A) the **implementation delegation** that introduces the new tool, and (B) the subsequent **dogfood pass delegation** that actually uses that tool. The Lead reads and writes `registry/dogfood_pending.md` in both.

**(A) When filing the implementation delegation (same timing as Step 1.7 evaluation):**

1. Determine that the trigger conditions apply and, in parallel with preview, mark it as a "dogfood-target task"
2. Append 1 new row to `registry/dogfood_pending.md` with `status=pending` / `dogfood_issue` / `dogfood_run_task_id` empty / `impl_pr` empty (PR number filled in later). At this point the implementation PR itself does not yet exist
3. The brief for the implementation worker need not mention dogfood (neither issue number nor PR number is fixed at this point). The implementation worker simply builds the tool as usual

**(B) When filing the dogfood pass delegation:**

4. Whenever filing a new delegation, check `registry/dogfood_pending.md`'s `status=open` rows (= paired follow-up issue created / dogfood pass not yet performed) each time
5. If the new task to be filed actually uses the target in the `tool / surface` column, earmark that task as a dogfood pass:
   - Add `--impl-guidance "Dogfood pass for paired follow-up issue #<N>. Report any defects to that issue using the format in references/dogfood-issue-template.md. Refs #<N>, do not Closes."` to the `apply` call
   - Additionally pass `--knowledge .claude/skills/org-delegate/references/dogfood-issue-template.md` to include the defect-reporting format in the brief
6. Update the relevant row: fill `dogfood_run_task_id=<new task_id>`, and leave `status` as `open` (transitions to `consumed` upon receipt of the completion report from the dogfood worker; see §Register state transitions)

### org-pull-request's responsibilities (cross-ref)

Done at the time of implementation PR creation / merge (detailed procedure is maintained separately on the org-pull-request side; Issue #338's scope is to record the protocol in this SKILL):

1. Immediately after implementation PR creation: find the matching `status=pending` row in `registry/dogfood_pending.md`, fill in `impl_pr=#<NNN>`, and create the paired follow-up issue via `gh issue create --body-file <rendered template>` (template: [`references/dogfood-issue-template.md`](references/dogfood-issue-template.md))
2. Fill the created issue number into the row's `dogfood_issue=#<MMM>`, and transition `status` from `pending → open`
3. Append `Paired dogfood issue: #<MMM>` to the bottom of the implementation PR body
4. When the paired issue is closed, transition the row's `status` from `consumed → closed`

### dogfood_pending register format

`registry/dogfood_pending.md` is **a partial-update register, not append-only**: row additions are append; updates to each column (`impl_pr` / `dogfood_issue` / `dogfood_run_task_id` / `status`) are allowed. Logical deletion and row reordering are prohibited.

```
| task_id | tool / surface | impl_pr | dogfood_issue | dogfood_run_task_id | status |
|---------|----------------|---------|---------------|---------------------|--------|
| issue-XXX-new-tool | tools/foo.py | #YYY | #ZZZ | issue-MMM-bar | open |
```

### Register state transitions

```
[Row added] (org-delegate Step 1.8 §A.2)
  status = pending      ← issue not created / impl_pr also empty
       │
       │ Implementation PR created + paired issue created (org-pull-request §1-2)
       ▼
  status = open         ← paired issue created / dogfood pass not yet performed
       │
       │ Earmarked by a subsequent delegation (org-delegate Step 1.8 §B.5-6)
       │ Fill dogfood_run_task_id. status stays open
       │
       │ Dogfood pass worker completion report received → defects aggregated into paired issue
       ▼
  status = consumed     ← defect monitoring period
       │
       │ Paired issue closed (org-pull-request §4)
       ▼
  status = closed       ← terminal
```

Each transition is a **single-column diff rewrite** on a single row of the table. Rewriting multiple columns simultaneously (e.g., pending → open is a batched update of `impl_pr`, `dogfood_issue`, and `status`) is allowed as long as it stays on the same row.

### consumed → closed observation timing (Lead's register hygiene responsibility)

Because the paired follow-up issue can be closed outside the implementation PR's lifecycle (manual close / split into individual fix issues / cleanup after long idle), relying only on `org-pull-request`'s trigger events (PR creation / review / post-merge close) will cause detection gaps. The Lead performs the following hygiene check at **every opportunity it writes to `registry/dogfood_pending.md`** (= implementation delegation filing / dogfood pass earmarking / dogfood pass completion receipt / status check):

```bash
# For status=consumed rows, transition to closed if the paired dogfood_issue is closed
gh issue view <dogfood_issue> --json state -q .state
  # → if "CLOSED", rewrite status from consumed to closed
```

In addition, the briefing at `/org-resume` startup also scans `status=consumed` rows once each and closes them (resume-time hygiene). This ensures that even if consumed lingers in the register, it is always reaped by the next register operation.

## Step 3 / 4: Worker spawn / instruction send / state recording (executed by the Dispatcher)

For the detailed procedure (3-1 balanced split / 3-1c SPLIT_CAPACITY_EXCEEDED escalate / 3-2 spawn / 3-3 pane_started / 3-3b channel approve / 3-4 list_peers / 3-5 instruction send / 3-6 sequential spawn / Step 4 state recording / Worker Directory Registry), reference **[`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md)** as the primary source. The Lead does not touch it.

The Dispatcher returns `DELEGATE_COMPLETE` to the Lead upon dispatch completion.

## Step 5: Progress management (executed by the Lead)

### ⚠️ cwd caution: state.db touching tools

`tools/journal_append.sh` / `tools/journal_append.py` / `tools/set_run_pr_open.py` / `python -c "... StateWriter ..."` and the like — any tool that opens `state.db` via a relative path — assume ja-root-relative. If you launch them from a worker / worktree cwd, they will fail silently or crash with `no such table: runs` / `no such table: events`, and the downstream post-commit hook and snapshot regeneration will not run either. Always `cd <ja-root>` before executing. Issue #398 is tracking a root fix.

### On DELEGATE_COMPLETE receipt

When you receive a dispatch-complete report from the Dispatcher, send a greeting message to each Worker:
```
mcp__renga-peers__send_message(
  to_id="worker-{task_id}",
  message="This is the Lead. You are assigned to {task_id}. Send all reports — completion, progress, and blockers — to `to_id=\"secretary\"` over renga-peers."
)
```

### On message receipt from a Worker

**Canonical event flow** (intermediate steps must not be skipped):

```
worker → Secretary peer message
  1. ack to worker (required for all messages; deadlock prevention)
  2. update Progress Log + DB (run.status / events / pending-decisions register)
  3. report to user           (only for completion / escalation / blocker; progress reports not needed)
  4. wait for user approval before push/PR
  5. CI watch / next instruction → [`.claude/skills/org-pull-request/SKILL.md`](../org-pull-request/SKILL.md)
```

- For the minimum ack contents and per-kind example texts, see [`.claude/skills/org-delegate/references/ack-template.md`](references/ack-template.md). **ack ≠ user approval**: `git push` / `gh pr create` / `tools/pr-watch.*` are issued only after the user's explicit OK
- The 2 → 3 ordering follows the principle "reconcile internal state first, then report to the user"

#### 0. Judgment request / scope expansion / blocker (identify with top priority)

→ Trigger [`.claude/skills/org-escalation/SKILL.md`](../org-escalation/SKILL.md). The Secretary does not pre-approve.

#### 1. Progress report

- Return ack to the worker (see the "progress report ack" section of [`.claude/skills/org-delegate/references/ack-template.md`](references/ack-template.md); before the Progress Log append). **Do not escalate progress reports to the user or wait for approval**
- Append to the Progress Log of `.state/workers/worker-{task_id}.md`
- Append an event to the DB events table (`bash tools/journal_append.sh ...`)

#### 2a. Completion report

- Return ack to the worker (see the "completion report ack" section of [`.claude/skills/org-delegate/references/ack-template.md`](references/ack-template.md))
- **Transition the run to REVIEW via the DB** (direct markdown edits prohibited):
  ```bash
  python -c "
  from pathlib import Path
  from tools.state_db import connect
  from tools.state_db.writer import StateWriter
  conn = connect('.state/state.db')
  with StateWriter(conn, claude_org_root=Path('.')).transaction() as w:
      w.update_run_status('<task_id>', 'review')
  "
  ```
- Append an event to the DB events table (`bash tools/journal_append.sh ...`)
- **Register update on dogfood pass completion (Issue #338)**: If the completed task was earmarked in the `dogfood_run_task_id` column of `registry/dogfood_pending.md`, transition that row's `status` from `open → consumed`. Defects are assumed to already be aggregated in the paired follow-up issue (the `dogfood_issue` column) — the format is specified in the dogfood pass worker's brief. The full protocol's SoT is Step 1.8 of this SKILL
- **Emit awaiting_user notification (Issue #28)**: Just before reporting to the human → entering an approval-wait stop, inform the attention watcher that "the Secretary is stopping while awaiting the user's judgment":
  ```bash
  bash tools/journal_append.sh notify_sent kind=awaiting_user task_id=<task_id> gate=worker_completed note="<short context such as PR/Issue>"
  ```
  The classifier of the parallel runtime PR picks this single line up as `secretary_awaiting_user` (default severity `urgent`) and beeps even when the user is not in front of the screen. See the CLAUDE.md section "Notify when the secretary is waiting for the user's judgment"
- Report the result to the human and **stop awaiting approval without closing the pane**. Issuing push/PR without approval is a protocol violation toward both the worker and the user

#### 2b / 2c. After user approval / review comments / post-merge close

→ Trigger [`.claude/skills/org-pull-request/SKILL.md`](../org-pull-request/SKILL.md).

### Worker monitoring and intervention judgment (executed by the Lead)

After dispatch, periodically check that the Worker has not entered a deep-dive or excessive-verification loop. **Intervention triggers** (if any one or more applies, check the situation with `mcp__renga-peers__inspect_pane`):

- More than 30 minutes elapsed on the same task, and entering the same phase (implementation / review / verification) for the 3rd time or later
- Silent for more than 1 hour with no progress report (not waiting for input either, and no progress log being emitted)
- (When using codex) Codex self-review is on its 4th or later round

**Intervention procedure**: Check the screen with `inspect_pane` → if judged to be deep-diving, interrupt with `send_keys(target="worker-{task_id}", keys=["Escape"])` → send a tight correction instruction via `send_message` (e.g., "Switch verification depth to minimal. Codex review and additional tests prohibited. Return only the single line `done: {commit SHA} {filename}`").

The Lead substituting in a commit on its own at the Worker's worktree is blocked by the auto-mode classifier (scope deviation). Intervention should be done strictly by "re-sending instructions".
