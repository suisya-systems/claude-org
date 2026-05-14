---
name: org-delegate
description: >
  Dispatch Worker Claude instances and delegate work to them. The Lead acts as the
  command node, and hands off hands-on execution to Workers by default.
  Trigger this when a user request requires file edits, implementation, research,
  or other execution work.
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

# org-delegate: Worker Dispatch

Delegate work to Worker Claude instances. The Lead only decomposes the task and generates the dispatch payload, then hands pane launch and instruction delivery to the Dispatcher. This minimizes the Lead's lock time.

> **Scope of this SKILL**: Only the initial dispatch phase: task identification → dispatch payload generation → handing off `DELEGATE` to the Dispatcher → greeting after Worker launch → ack on progress/completion reports and transition to REVIEW. The following are split into other skills / references:
> - **Worker launch, instruction delivery, and state recording procedure** → [`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md) (Dispatcher-only)
> - **Push / PR / CI watch / review-fix loop / post-merge close after user approval** → [`.claude/skills/org-pull-request/SKILL.md`](../org-pull-request/SKILL.md)
> - **Worker requests for judgment, scope expansion, and blocker escalation** → [`.claude/skills/org-escalation/SKILL.md`](../org-escalation/SKILL.md)
> - **Minimum three ack elements and message-type-specific examples** → [`.claude/skills/org-delegate/references/ack-template.md`](references/ack-template.md) (single SoT)

> **state-db cutover (M4, Issue #267 / #284)**: Structured section writes must go **through `StateWriter.transaction()`**. The post-commit hook automatically regenerates `.state/org-state.md` / `.state/org-state.json` from the DB, and `update_run_status('<task_id>', 'completed')` automatically moves `.state/workers/worker-<task_id>.md` to `.state/workers/archive/`. Direct markdown edits are detected by `drift_check`. For events, the DB `events` table is the SoT (`tools/journal_append.sh` / `.py` already route to the DB). If the DB is missing, build it with `python -m tools.state_db.importer --db .state/state.db --rebuild --no-strict`.

## Lead and Dispatcher Responsibilities

| Stage | Owner |
|---|---|
| Project name resolution | **Lead** |
| work-skill search | **Lead** |
| Task decomposition / dispatch payload generation | **Lead** (`gen_delegate_payload.py`) |
| `DELEGATE` send | **Lead** (the Lead is released here) |
| Pane launch, peer wait, instruction delivery, state recording | **Dispatcher** ([`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md)) |
| Dispatch completion report to the Lead | **Dispatcher** |
| Receive progress / completion / escalation reports from Workers | **Lead** |
| Pane close on Worker completion | **Dispatcher** (`CLOSE_PANE` requested by the Lead) |

## Pre-delegation Checklist (run by the Lead)

Before task decomposition, check the request from the following angles. Ask the user to clarify when applicable.

| Check item | Situation to confirm | Example |
|---|---|---|
| **Ambiguous terms / abbreviations** | A tool name, service name, or abbreviation may have multiple meanings | `gog` → Google OAuth? `gog` CLI? |
| **OS-specific prerequisites** | The output differs by OS and default assumptions must be explicit | Mac=`zsh`, Windows=`py -3`, path separators |

- If there is ambiguous terminology: ask the user, "Does `○○` mean `△△`?" before proceeding.
- For OS-specific tasks: include OS-specific prerequisites in the Worker instructions when generating the payload.

## Step 0: Project Name Resolution (run by the Lead)

Identify the project from the user request:

1. Read `registry/projects.md`
2. Identify the matching project from keywords in the request (match against alias, project name, and description)
3. If identified, use that path
4. If not identified, show the list of registered project aliases and let the user choose
5. For a new project:
   - Confirm the path with the user
   - Infer the alias, description, and common work examples, then append them to `registry/projects.md` after user confirmation

## Step 0.5: work-skill Search (run by the Lead)

Before task decomposition, search for existing related work-skills. Include matched work-skills in Worker instructions as reference material.

1. Enumerate all `SKILL.md` files under `.claude/skills/`
2. Match each `SKILL.md` frontmatter (`type` / `description` / `triggers`) against the task. Exclude the `org-` prefix because those are org-operation skills
3. Include relevant candidates when applicable. Exact match is not required; if multiple match, include all in relevance order

**If matched:**
- Notify the human: `Found a related work-skill: {skill-name} — I will include it as reference material`
- Pass the work-skill `SKILL.md` path to the `gen_delegate_payload.py` call via the `--knowledge` flag. The Stage 2 brief renderer embeds that path into `CLAUDE.md` / `CLAUDE.local.md` as `[references].knowledge`. For multiple matches, repeat as `--knowledge <path1> --knowledge <path2>`
- Explicitly note the presence of the reference skill in the Worker instructions (`instruction-template`)

Do not copy a work-skill procedure verbatim. Present it as reference material and let the Worker decide.

## Step 0.6: Pre-fetch for release-class tasks (run by the Lead)

Tasks that cut a `release/*` branch assume the Worker branches from the **latest `main` of the target project**. Since the Phase 2 Worker git guardrails, the Worker-side `.claude/settings.json` `permissions.deny` list includes `Bash(git fetch)` / `Bash(git pull)` / `Bash(git remote update)`. Dispatching a Worker while local `origin/main` is stale therefore fires a "git fetch deny" BLOCKER within 5 minutes of start, causing a 10+ minute round-trip with the Lead (claude-org-runtime v0.1.10 incident).

For this reason, **only for release-class tasks**, the Lead performs the fetch on the Worker's behalf before `gen_delegate_payload.py preview` / `apply`:

```bash
# Local root of the target project (the repo where the release will be cut)
cd <target project root>

# Pick up the latest origin/main and ff-update local main
git fetch origin
git pull --ff-only origin main
```

### Applicability

Trigger only when one of the following applies:

- The task description / commit-prefix / planned branch contains a release-promotion term such as `release`, `release/`, `vX.Y.Z`
- The target files include release-promotion work such as a `CHANGELOG.md` promotion or a `version` bump in `__about__.__version__` / `pyproject.toml`
- The `task_id` contains `release` (example: `runtime-0-1-10-release`)

Do not run this for ordinary feature / fix / docs tasks. Worker permissions deny is an intentional design choice that "the Worker does not pull mainline history and completes work inside the sandbox"; only releases are the exception that requires "branching from the latest main".

### Background

For the detailed background (the measured 5-minute Worker BLOCKER → 10-minute extra round-trip, comparison of four response options, and the permissions-side root cause), see the section "On release-branch creation, the Lead performs `git fetch` on the Worker's behalf" in [`knowledge/curated/release-process.md`](../../../knowledge/curated/release-process.md).

## Step 0.7 / 1 / 1.5 / 2: Generate the Dispatch Payload with One Command (Issue #283)

Step 0.7 (pre-check for `.gitignore`) / Step 1 (Pattern decision) / Step 1.5 (Worker directory preparation + role decision + settings generation) / Step 2 (`DELEGATE` body assembly) are handled **in one pass by `tools/gen_delegate_payload.py`**. The Lead is only responsible for task identification (Step 0), work-skill search (Step 0.5), target file extraction, and depth selection.

### Standard flow (recommended)

```bash
# 1. preview: fully non-destructive. Only check the DELEGATE body and the list of files to be created
python tools/gen_delegate_payload.py preview \
    --task-id <task-id> --project-slug <slug> \
    --target <path>... --description "<desc>" \
    --verification-depth full

# 1.5. Step 1.7 gate: evaluate Codex design-review trigger conditions against the preview output.
#      Only when applicable, run a design review with `codex exec` and pass the summary to apply
#      via --impl-guidance or --knowledge (see Step 1.7 below).

# 2. apply: reserve state.db with runs.status='queued' + place CLAUDE.md/CLAUDE.local.md
#    + run claude-org-runtime settings generate + output send_plan.json
python tools/gen_delegate_payload.py apply \
    --task-id <task-id> --project-slug <slug> \
    --target <path>... --description "<desc>" \
    --verification-depth full

# 3. Copy the send_plan.json emitted by apply into the MCP call
#    cat <worker_dir>/send_plan.json
#    → mcp__renga-peers__send_message(to_id="dispatcher", message=<message>)
```

`apply` performs **T1 reservation only** (`runs.status='queued'`). Activation into Active Work Items is Dispatcher T2 ([`docs/contracts/delegation-lifecycle-contract.md`](../../../docs/contracts/delegation-lifecycle-contract.md)), so this skill does not touch it. On failure, leave the queued entry in place and ask the Lead for judgment.

### Common flags

- `--mode edit|audit` (default `edit`): explicitly use `--mode audit` for **read-only** audit tasks on `claude-org`
- `--branch <name>`: override `planned_branch`. Default is `feat/<task-id>` (`fix/<task-id>` when the description contains `fix` / `bug` / `修正`)
- `--commit-prefix "<prefix>"`: if omitted, infer from the head of `project_slug` (example: `claude-org` → `feat(claude):`)
- `--closes-issue N` / `--refs-issues N1 N2`: embed `Closes #N` / `Refs #N1 #N2` into the brief
- `--impl-target <path>` / `--impl-guidance "<text>"` / `--knowledge <path>`: optional `[implementation]` / `[references]` sections
- `--skip-settings`: skip `claude-org-runtime settings generate` (for environments where the CLI is not installed)
- `--from-toml <path>`: use an existing `worker_brief.toml` as input. CLI flags override the TOML

### Pattern / role / branch decision details

See [`.claude/skills/org-delegate/references/delegate-flow-details.md`](references/delegate-flow-details.md) for the decision logic (`Pattern A` vs `B` vs `C` / gitignored submodes / role table / `planned_branch` / required lines in the `DELEGATE` body). For the self-edit task special case (Issue #289, `pattern_variant='live_repo_worktree'`), see §3 of [`.claude/skills/org-delegate/references/claude-org-self-edit.md`](references/claude-org-self-edit.md).

### Target file extraction

The Lead extracts "target files" from the task description: paths explicitly named in the request text, Issue body, or user message. Do not determine them mechanically. For tasks where target files cannot be identified, such as pure research or new file creation with undecided paths, `--target` is not required.

### When the standard path returns unexpected output

If the standard path (`gen_delegate_payload.py apply`) returns unexpected output such as a wrong Pattern decision, resolver error, or brief inconsistency, the Lead must **not manually reproduce the same work**. File an Issue for the resolver bug and pause delegation for that task until the resolver is fixed. Manual fallback is out of scope for this skill. In environments without the CLI, only the `--skip-settings` flag is allowed. A museum copy of the historical handwritten path exists at `docs/legacy/hand-typed-delegate-path.md`, but it must not be referenced in standard operations.

## Step 1.7: Codex Design-Review Trigger (run by the Lead, Issue #337)

Looking at the `preview` output (`description` / number of `--target` entries / referenced documents), if **at least one** of the following applies, run a Codex design review **before** `apply`. This gate is based on Curator session #18 retrospective (Issue #283 / session #12), where "an up-front Codex design review caught 2 Blocker + 5 Major findings in a single round."

| Trigger | How to evaluate |
|---|---|
| Estimated effort ≥ 3h | Lead's judgment from the task description (user input / preview scale) |
| Introduces a new module / new tool | The description contains "new", "new tool", "newly introduced", etc., or the planned files in preview are all new paths |
| File changes ≥ 3 | Number of `--target` entries + edit targets enumerated in the preview brief |
| References a contract document under `docs/contracts/` | The description / brief / `--knowledge` references something under `docs/contracts/` |

**Procedure:**

```bash
codex exec --skip-git-repo-check "Design review for <task-id>.\
  Task: <description>.\
  Target files: <target paths>.\
  Related contracts / references: <docs paths>.\
  Classify pre-implementation findings as Blocker / Major / Minor / Nit, and for each finding include the target file:line and the rationale, in concise English."
```

Do not use the `codex:rescue` skill (forbidden by `CLAUDE.local.md`). Use `codex exec` directly only.

**Embedding the review summary:**

- Save the summary at `tmp/codex-review-{task-id}.md`
- When calling `apply`, pass **`--impl-guidance "<summary body>"`**. This expands the summary body into `[implementation].guidance` in the brief, so the Worker can read it directly
- As a supplement, add `--knowledge tmp/codex-review-{task-id}.md` so the brief's `[references].knowledge` enumerates the path and the Worker can refer to the full text on demand (`gen_worker_brief.py` only enumerates paths and does not embed bodies). Reliably delivering the body to the Worker is the responsibility of `--impl-guidance`
- If a Blocker / Major is reported, escalate to the user and confirm whether the approach should change before proceeding to apply

**Helper script:** marked optional in the Issue #337 acceptance and not implemented in this PR. The Lead evaluates the table above manually.

## Step 1.8: Dogfood Follow-up Issue Protocol (Lead + org-pull-request, Issue #338)

For PRs that introduce a new tool / runtime / workflow, create a "dogfood follow-up" issue paired with the implementation PR, and explicitly earmark the next delegation that actually uses the new tool as a **dogfood pass**. This protocol is based on the Curator session #18 retrospective, where "PR #288 surfaced 4 categories of defects only on first real use" (also reproduced in session #11).

### Applicability

Triggered when the task is one of the following:

- Adds a new CLI tool / script (`tools/*.py`, `tools/*.sh`, `tools/*.ps1`, etc.)
- Introduces a new runtime / new workflow / new protocol
- A breaking redesign of an existing tool

### Lead (org-delegate) responsibilities

The dogfood protocol spans **two delegations**: (A) the **implementation delegation** that introduces the new tool, and (B) the **dogfood pass delegation** that actually uses that tool afterward. The Lead reads/writes `registry/dogfood_pending.md` in both.

**(A) When opening the implementation delegation (same timing as Step 1.7 evaluation):**

1. Determine that applicability is satisfied, and in parallel with preview, mark the task as a "dogfood target task"
2. Append one new row to `registry/dogfood_pending.md` with `status=pending`, empty `dogfood_issue` / `dogfood_run_task_id`, and empty `impl_pr` (the PR number is filled in later). At this point the implementation PR itself does not yet exist
3. The implementation Worker brief does not need to mention dogfood (neither the issue number nor the PR number is finalized at this point). The implementation Worker just builds the tool as usual

**(B) When opening the dogfood pass delegation:**

4. Whenever opening a new delegation, check rows in `registry/dogfood_pending.md` whose `status=open` (= the paired follow-up issue is created and a dogfood pass has not yet been run)
5. If the new task being opened actually uses the tool / surface in question, earmark that task as the dogfood pass:
   - Add `--impl-guidance "Dogfood pass for paired follow-up issue #<N>. Report any defects to that issue using the format in references/dogfood-issue-template.md. Refs #<N>, do not Closes."` to the `apply` call
   - Additionally pass `--knowledge .claude/skills/org-delegate/references/dogfood-issue-template.md` so the defect-reporting format is included in the brief
6. Update the relevant row: fill in `dogfood_run_task_id=<new task_id>`, leave `status` at `open` (it transitions to `consumed` upon receipt of the dogfood Worker's completion report — see §register state transitions)

### org-pull-request responsibilities (cross-ref)

At PR creation / merge time, the org-pull-request side does the following (detailed steps live there; Issue #338 only records the protocol in this SKILL):

1. Right after creating the implementation PR: find the row in `registry/dogfood_pending.md` with `status=pending`, fill in `impl_pr=#<NNN>`, and create the paired follow-up issue with `gh issue create --body-file <rendered template>` (template: [`references/dogfood-issue-template.md`](references/dogfood-issue-template.md))
2. Fill the created issue number into `dogfood_issue=#<MMM>` on that row, and transition `status` from `pending → open`
3. Append `Paired dogfood issue: #<MMM>` to the bottom of the implementation PR body
4. When the paired issue is closed, transition `status` from `consumed → closed` on that row

### `dogfood_pending` register format

`registry/dogfood_pending.md` is **not append-only but a partial-update register**: appending rows is via append, and per-column updates (`impl_pr` / `dogfood_issue` / `dogfood_run_task_id` / `status`) are allowed. Logical deletion and row reordering are forbidden.

```
| task_id | tool / surface | impl_pr | dogfood_issue | dogfood_run_task_id | status |
|---------|----------------|---------|---------------|---------------------|--------|
| issue-XXX-new-tool | tools/foo.py | #YYY | #ZZZ | issue-MMM-bar | open |
```

### register state transitions

```
[Append row] (org-delegate Step 1.8 §A.2)
  status = pending      ← issue not created yet / impl_pr also empty
       │
       │ Implementation PR created + paired issue created (org-pull-request §1-2)
       ▼
  status = open         ← paired issue created / dogfood pass not yet run
       │
       │ Earmarked by a follow-up delegation (org-delegate Step 1.8 §B.5-6)
       │ Fill in dogfood_run_task_id. status stays open
       │
       │ Dogfood pass Worker completion report received → defects already aggregated on the paired issue
       ▼
  status = consumed     ← defect monitoring period
       │
       │ Paired issue closed (org-pull-request §4)
       ▼
  status = closed       ← terminal
```

Each transition is a **single-column delta on a single row**. Updating multiple columns at once is allowed within the same row (e.g., `pending → open` updates `impl_pr` + `dogfood_issue` + `status` together).

### `consumed → closed` observation timing (Lead's register-hygiene responsibility)

A paired follow-up issue may be closed outside the implementation PR's lifecycle (manual close / split into individual fix issues / cleanup after a long idle period), so detection cannot be guaranteed by org-pull-request triggers (PR creation / review / post-merge close) alone. The Lead runs the following hygiene check at **every moment it writes to `registry/dogfood_pending.md`** (= opening the implementation delegation / earmarking the dogfood pass / receiving the dogfood-pass completion report / state inspection):

```bash
# For each row with status=consumed, transition to closed if the paired dogfood_issue is closed
gh issue view <dogfood_issue> --json state -q .state
  # → if "CLOSED", rewrite status from consumed to closed
```

In addition, the `/org-resume` startup briefing also scans rows with `status=consumed` once each and closes them (resume-time hygiene). This way, even if `consumed` rows linger in the register, they are reliably collected by the next register operation.

## Step 3 / 4: Worker Launch, Instruction Delivery, State Recording (run by the Dispatcher)

For the detailed procedure (`3-1 balanced split` / `3-1c SPLIT_CAPACITY_EXCEEDED escalate` / `3-2 spawn` / `3-3 pane_started` / `3-3b channel approve` / `3-4 list_peers` / `3-5 instruction send` / `3-6 sequential launch` / Step 4 state recording / Worker Directory Registry), use **[`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md)** as the primary reference. The Lead does not touch this.

When dispatch completes, the Dispatcher returns `DELEGATE_COMPLETE` to the Lead.

## Step 5: Progress Management (run by the Lead)

### On `DELEGATE_COMPLETE`

After receiving the dispatch completion report from the Dispatcher, send a greeting message to each Worker:
```
mcp__renga-peers__send_message(
  to_id="worker-{task_id}",
  message="窓口です。{task_id} の作業をお願いしています。完了・進捗・ブロック、全ての報告は `to_id=\"secretary\"` で renga-peers 送信してください。"
)
```

### On message receipt from a Worker

**Canonical event flow** (do not skip intermediate stages):

```
worker → Secretary peer message
  1. ack to worker (全 message 共通で必須。dead-lock 防止)
  2. update Progress Log + DB (run.status / events / pending-decisions register)
  3. report to user           (完了 / escalation / blocker のみ。進捗報告は不要)
  4. wait for user approval before push/PR
  5. CI watch / next instruction → [`.claude/skills/org-pull-request/SKILL.md`](../org-pull-request/SKILL.md)
```

- For minimum ack content and examples by message type, see [`.claude/skills/org-delegate/references/ack-template.md`](references/ack-template.md). **`ack` != user approval**: only issue `git push`, `gh pr create`, and `tools/pr-watch.*` after explicit user OK
- The order `2 → 3` follows the rule: make internal state consistent first, then report to the user

#### 0. Requests for judgment, scope expansion, blockers (identify first, highest priority)

→ Trigger [`.claude/skills/org-escalation/SKILL.md`](../org-escalation/SKILL.md). The Lead does not give first-line approval.

#### 1. Progress reports

- Return an ack to the worker (see the "progress report ack" section of [`.claude/skills/org-delegate/references/ack-template.md`](references/ack-template.md), before appending to the Progress Log). **Do not report progress updates to the user, and do not wait for approval**
- Append to the Progress Log in `.state/workers/worker-{task_id}.md`
- Append the event to the DB `events` table (`bash tools/journal_append.sh ...`)

#### 2a. Completion reports

- Return an ack to the worker (see the "completion report ack" section of [`.claude/skills/org-delegate/references/ack-template.md`](references/ack-template.md))
- **Transition the run to REVIEW through the DB** (direct markdown edits are forbidden):
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
- Append the event to the DB `events` table (`bash tools/journal_append.sh ...`)
- **Register update on dogfood-pass completion (Issue #338)**: if the completed task is earmarked in the `dogfood_run_task_id` column of `registry/dogfood_pending.md`, transition `status` on that row from `open → consumed`. Defects are assumed to already be aggregated on the paired follow-up issue (`dogfood_issue` column) per the format pre-specified in the dogfood-pass Worker's brief. The full protocol's SoT is Step 1.8 of this SKILL
- **Emit the awaiting_user notification (Issue #28)**: just before reporting to the human and stopping to wait for approval, tell the attention watcher that the Secretary is about to stop waiting on a user judgment:
  ```bash
  bash tools/journal_append.sh notify_sent kind=awaiting_user task_id=<task_id> gate=worker_completed note="<short context such as PR/Issue>"
  ```
  The classifier in the parallel runtime PR picks this single line up as `secretary_awaiting_user` (default severity `urgent`), so the user gets a beep even when not at the screen. See the "Notify when the Secretary is waiting on a user judgment" section in CLAUDE.md.
- Report the result to the human and **stop, waiting for approval without closing the pane**. Issuing push/PR without approval violates protocol for both the Worker and the user

#### 2b / 2c. After user approval, review comments, post-merge close

→ Trigger [`.claude/skills/org-pull-request/SKILL.md`](../org-pull-request/SKILL.md).

### Worker monitoring and intervention decisions (run by the Lead)

After dispatch, periodically check whether the Worker has fallen into a deep-dive or over-verification loop. **Intervention triggers** (if any one applies, inspect the state with `mcp__renga-peers__inspect_pane`):

- More than 30 minutes elapsed on the same task, and the Worker has entered the same phase (implementation / review / verification) for the third time or later
- Quiet for more than 1 hour with no progress report (not waiting for input, and no progress log either)
- If using codex: Codex self-review has entered round 4 or later

**Intervention procedure**: inspect the screen with `inspect_pane` → if it is judged to be a deep dive, interrupt with `send_keys(target="worker-{task_id}", keys=["Escape"])` → send a tight corrective instruction with `send_message` (example: `Switch verification depth to minimal. No Codex review, no additional tests. Reply with one line only: done: {commit SHA} {filename}`).

The Lead is blocked by the auto-mode classifier from making a commit directly in the Worker's worktree on the Worker's behalf (out-of-scope action). Intervention must be done strictly by resending instructions.
