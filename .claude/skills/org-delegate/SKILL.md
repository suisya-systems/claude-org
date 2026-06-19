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

> **Transport layer (transport) both systems — default `renga` / opt-in `broker`**: this skill's `mcp__renga-peers__*` calls are written for **default `renga`** (`ORG_TRANSPORT` unset) and can be followed as-is (default behavior unchanged). Under `ORG_TRANSPORT=broker` (opt-in, revertible) the MCP server name becomes `org-broker`, and tools' **fully qualified names get machine-substituted from `mcp__renga-peers__*` → `mcp__org-broker__*`** (argument shape and semantics are identical, so the procedure logic is unchanged). Only the transport-dependent points are noted in broker form:
>
> - **Receive model (push → pull)**: under renga, progress / completion / judgment requests from workers are pushed in-band as `<channel source="renga-peers" …>`. Under broker, **only a pane-local nudge fires**, and the body must be pulled via `check_messages` (broker: `mcp__org-broker__check_messages`) — broker delivers to all peers via pull = `receive_mode` constant `"poll"`. The Step-5 line "when a message arrives from the worker" becomes "when you see a nudge, `check_messages`", but the rest (the ack `send_message` etc.) keeps the same shape.
> - **Spawn rite (dev-channel approval → folder-trust approval)**: worker spawn is dispatcher-exclusive ([`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md)), but under broker the `--dangerously-load-development-channels` injection is replaced with `--mcp-config <broker>`, and the approval prompt shifts to the Claude Code **folder-trust prompt** (machine-approval via `send_keys(enter=true)` keeps the same shape). The `send_keys` pre-approval for root `.claude/**` self-edits (Step 5 below) also uses `mcp__org-broker__send_keys` under broker in the same procedure.
> - **Error branching (broker additional codes)**: on top of the renga codes, broker may return `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` (unknown codes hit the default branch to escalate). See the broker section in [`.claude/skills/org-delegate/references/renga-error-codes.md`](references/renga-error-codes.md).
>
> `new_tab` / `focus_pane` are **absent** from the broker surface (intentional exclusion; this flow does not use them anyway). The canonical contract is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, proposed/awaiting ratification); the design SoT is transport-lab `docs/design/ja-migration-plan.md` §5.2(ii). Broker real-run (dogfood) is scoped to Epic #6 Issue G and is not this skill's default path.

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

## Lane selection decision (executed by the Lead, Refs #515)

Before entering the pre-delegation checklist, first decide **which lane to run this task on**. Task routing is a two-lane system: the principle (CLAUDE.md "Delegate all implementation work to Workers") is preserved, while a lightweight lane limited to very small tasks is held as an exception (for background and the empirical evidence, treat the "Task routing two-lane system" section in CLAUDE.md as the SoT).

| Lane | Trigger conditions | Processing path |
|---|---|---|
| **Lightweight lane** (subagent direct handling) | **All** of the following: estimated effort S or less / single-file class / no expected need to escalate a judgment / does not span a day | The Lead calls the `Agent` tool (`isolation="worktree"`, **`run_in_background=true` required**) **in its own session** and handles the task directly. **Do not proceed to the rest of this SKILL (org-delegate)** (this section is routing decision only; because subagent launch happens in the Lead body's context, `Agent` does not need to be in this skill's `allowed-tools`). |
| **Heavyweight lane** (Worker dispatch) | Even one lightweight condition is not met, or any of the following applies | Run this SKILL from Step 0 and dispatch a worker via the Dispatcher. |

**Cases that must always go to the heavyweight lane (overrides even when some lightweight conditions are met):**
- There is a judgment boundary / escalation is expected
- Spans a day / does not complete on the spot
- Requires resident monitoring (long-running progress tracking or intervention judgment)

When in doubt, fall back to the heavyweight lane (the lightweight lane is for "clearly very small" cases only).

**Mandatory conditions when the lightweight lane is chosen (non-omittable):**
- Launch the `Agent` tool with `run_in_background=true`. **Synchronous execution is forbidden** (it would block the Lead's human contact and the immediacy of worker acks).
- Within the subagent, run a Codex review in-loop and fix until Blocker/Major is zero (a gate equivalent to verification depth full).
- Maintain the existing human gates for push / PR / merge (the subagent must not push / `gh pr create` / merge automatically).

This section is responsible for the routing decision only. If you choose the lightweight lane, do not proceed to the pre-delegation checklist through Step 5; switch to `Agent` direct handling in the Lead body's context. Only when the heavyweight lane is chosen, continue below.

**Heavyweight-lane brief reinforcement (ultracode):** Within the heavyweight lane, for tasks that are **M class or higher / contain design judgment / change multiple files**, you may state "ultracode use permitted" explicitly in the Worker brief (recommended). Pass it as brief text via `--impl-guidance "<text>"` of `gen_delegate_payload.py` (example: `--impl-guidance "This task involves multiple files and design judgment, so the use of ultracode is permitted."`). A dedicated flag in `gen_delegate_payload.py` (flag-ification) is out of scope; brief-text level is sufficient. Do not state ultracode for lightweight-lane or single-file small tasks.

## Pre-delegation checklist (executed by the Lead)

Before entering task decomposition, check the request from the following angles. If any apply, ask the user back.

| Check item | Situations to confirm | Example |
|---|---|---|
| **Ambiguous terms / abbreviations** | When a tool name, service name, or abbreviation could mean multiple things | "gog" → Google OAuth? gog CLI? |
| **OS-specific preconditions** | When producing OS-specific deliverables, default settings must be made explicit | Mac=zsh, Windows=py -3, path separator |

- When there is an ambiguous term: ask the user "Do you mean XX by YY?" before proceeding
- For OS-specific tasks: include OS-specific preconditions in the Worker instructions when generating the payload
  - **Windows worker + CLI / stdout-producing tool implementation**: include in the brief via `--impl-guidance` etc. the two reminders that (1) strings emitted to the CLI (argparse `help=` / `print()`) must use ASCII `-` and avoid em-dash and other characters that cp932 cannot encode, and (2) `--help` must be smoke-tested once in a real terminal (these are also permanently noted in the Windows section of the rendered brief, but at CLI-tool delegation time the Lead must explicitly hold this in mind). Background: a pattern in which the cp932 console cannot encode em-dash (U+2014) and crashes `--help` has fired twice (ja#537 / runtime#63). pytest captures via `redirect_stdout` in UTF-8 and passes, so the failure only manifests in a real terminal.

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

Before `gen_delegate_payload.py apply`, update the target project's local main with `git fetch origin` + `git pull --ff-only origin main` **only when** one of the following 4 conditions applies:

- The task description / commit-prefix / planned branch contains release-promotion words such as `release`, `release/`, `vX.Y.Z`
- The target files include `CHANGELOG.md` promotion / `__about__.__version__` / `pyproject.toml` `version` bumps, etc.
- The task_id contains `release` (e.g., `runtime-0-1-10-release`)

For detailed conditions, the execution command, and the rationale behind the worker permissions deny (fetch miss → worker BLOCKER within 5 minutes → 10-minute-plus loss background), refer to [`references/release-pre-fetch.md`](references/release-pre-fetch.md) as the primary source. **The 4 conditions retained in this body must not be omitted, because missing the trigger leads directly to a worker BLOCKER.**

> **Distinction from Pattern B (Issue #480)**: For Pattern B, apply itself runs `git fetch origin` and branches off `origin/HEAD` when creating the worktree, so the freshness of the worktree's starting point does not depend on this Step 0.6. What Step 0.6 guarantees is the **freshness of local main** for Pattern A (where the worker cuts `release/*` from local main); the two address different targets. For details, see the "Relation to Issue #480" section of [`.claude/skills/org-delegate/references/release-pre-fetch.md`](references/release-pre-fetch.md).

## Step 0.7 / 1 / 1.5 / 2: Generate the dispatch payload in 1 command (Issue #283)

Step 0.7 (gitignore pre-check) / Step 1 (Pattern determination) / Step 1.5 (Worker directory preparation + role decision + settings generation) / Step 2 (DELEGATE body assembly) are **all handled by `tools/gen_delegate_payload.py`**. The Lead's responsibility is only task identification (Step 0), work-skill search (Step 0.5), target-file extraction, and depth judgment.

### Pre-dispatch verification checks (auxiliary to Step 0.7 — Secretary runs them by hand)

The following 2 items are **not** verified by `gen_delegate_payload.py`; the Secretary confirms them by hand before `preview`. **If they cannot be satisfied, the dispatch is not viable and you must not proceed to `apply`** (resolve the cause on the Secretary side or escalate to the user, then restart from Step 0):

1. **Committed-base existence check**: for `--target`, **file existence is always verified**. **Line existence is verified only for delegations whose input carries line-numbered review findings or patches**. A delegation whose edit base is uncommitted live-tree state is not viable (the worker's worktree / clone is cut from the committed base and cannot see the target) — commit first and re-delegate.
2. **Contracts grep for org-behavior changes**: for delegations that change org behavior (cadence / lifecycle / responsibility boundaries), grep `docs/contracts/` with behavior keywords (loop / cadence / curator / close, etc.) and follow the cited sources of every contract that hits (`.dispatcher/CLAUDE.md`, `.dispatcher/references/worker-monitoring.md`, etc.). **Do not place hits into `--target`** (it contaminates the edit scope); carry them in the brief via `--knowledge` / `--impl-guidance`.

For the determination criteria, command examples, and the grep keyword list, see [`.claude/skills/org-delegate/references/delegate-flow-details.md`](references/delegate-flow-details.md) §1.5 as the primary source.

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

### Heavy-lane brief enhancement (ultracode)

For heavy-lane tasks at **M-class or above / involving design judgment / spanning multiple files**, you may permit the Worker to use ultracode (multi-agent workflow) (recommended). The Lead states the permission in the brief via `gen_delegate_payload.py`'s `--impl-guidance "<text>"` (example: `--impl-guidance "This task involves multiple files and design judgment, so ultracode use is permitted. Use ultracode for implementation and pre-Codex self-review convergence; the final Codex gate is maintained as before"`). This text is rendered into the "Implementation guidance" section of the worker brief (default `CLAUDE.md`; for claude-org self-edit tasks, `CLAUDE.local.md`), and **the Dispatcher reads it there to decide whether arming is needed** ([`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md) 3-5a).

**However, the brief text is a "permission declaration", not an "opt-in arming" (Issue #554).** ultracode is armed only when an `ultracode` token appears in a **user turn input** of the worker session. Live runs have confirmed that even if the keyword appears in the brief file (the worker behavioral rules file — default `CLAUDE.md`, `CLAUDE.local.md` for self-edit tasks — loaded as context), in `send_message` bodies, or in the body delivered via `check_messages`, no arming occurs. **The arming trigger is for the Dispatcher to issue the kickoff as a user turn via `send_keys` on the in-use transport, with a standalone `ultracode` token in that body** (SoT: [`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md) 3-5a). In other words, **the Lead's brief permission is a necessary condition; the Dispatcher's send_keys kickoff is the arming condition**.

Adding a dedicated flag to `gen_delegate_payload.py` is out of scope (the division of labor — permission via the `--impl-guidance` brief text, arming via the Dispatcher's send_keys — is sufficient). **Positioning**: ultracode is the **front stage** used for implementation and pre-Codex self-review convergence, not a replacement for the final Codex gate (independent review by a separate model, Blocker / Major zero). Do not permit ultracode for light-lane tasks or small single-file tasks.

## Step 1.7: Codex design review trigger (executed by the Lead, Issue #337)

Decide whether to perform a Codex design review before `apply`. Run it only when one of the following applies:

- Estimated effort ≥ 3h
- Introduction of a new module / new tool
- File changes ≥ 3
- Reference to contract documents under `docs/contracts/`

For the detailed trigger-determination table, the `codex exec` command, and the procedure for incorporating the review summary via `--impl-guidance` / `--knowledge`, refer to [`references/codex-design-review.md`](references/codex-design-review.md) as the primary source.

## Step 1.8: dogfood follow-up issue protocol (Lead + org-pull-request coordination, Issue #338)

A task that introduces a new CLI tool / new runtime / new workflow / new protocol, or that redesigns an existing tool with a breaking change, is a **dogfood target**. Paired with the implementation delegation, create a follow-up issue and earmark the subsequent real-use delegation as a dogfood pass.

For the dogfood-target determination, the Lead's responsibilities — (A) appending to `registry/dogfood_pending.md` at implementation filing and (B) the dogfood pass earmark procedure — the org-pull-request coordination, the register format, and the hygiene check (consumed → closed), refer to [`references/dogfood-protocol.md`](references/dogfood-protocol.md) as the primary source.

State transitions: `pending → open → consumed → closed`.

## Step 3 / 4: Worker spawn / instruction send / state recording (executed by the Dispatcher)

For the detailed procedure (3-1 balanced split / 3-1c SPLIT_CAPACITY_EXCEEDED escalate / 3-2 spawn / 3-3 pane_started / 3-3b channel approve / 3-4 list_peers / 3-5 instruction send / 3-6 sequential spawn / Step 4 state recording / Worker Directory Registry), reference **[`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md)** as the primary source. The Lead does not touch it.

The Dispatcher returns `DELEGATE_COMPLETE` to the Lead upon dispatch completion.

## Step 5: Progress management (executed by the Lead)

### ⚠️ cwd caution: state.db touching tools

`tools/journal_append.sh` / `tools/journal_append.py` / `tools/set_run_pr_open.py` / `python -c "... StateWriter ..."` and the like — any tool that opens `state.db` via a relative path — assume ja-root-relative. If you launch them from a worker / worktree cwd, they will fail silently or crash with `no such table: runs` / `no such table: events`, and the downstream post-commit hook and snapshot regeneration will not run either. Always `cd <ja-root>` before executing. Issue #398 is tracking a root fix.

### Lead → Worker messaging rules (Issue #475: 1 worker = 1 task = 1 scope)

Every message the Lead sends to an existing Worker follows the "1 worker = 1 task = 1 scope" principle. For the canonical 3 rules, refer to CLAUDE.md "Role Boundaries > Boundary for follow-up requests to a Worker" as the SoT:

1. **Keep follow-up requests within the original task's scope**: only send on supplementary or corrective instructions within the range laid out in the brief. Do not feed an out-of-scope, separate concern into the same Worker; re-run this SKILL from Step 0 and dispatch a different Worker via the Dispatcher.
2. **Route Worker scope expansion proposals through escalation**: the Lead does not pre-approve them and triggers [`.claude/skills/org-escalation/SKILL.md`](../org-escalation/SKILL.md) (`/org-escalation`).
3. **The Lead does not do the Worker's work**: do not reach into a Lead-side worktree for file edits, commits, tests, etc.; return the work to the Worker as a follow-up request, or dispatch a different Worker.

Violation case: 2026-05-21, mixing a separate concern into the voice-v2-independent pane (an out-of-scope task was sent on to the same Worker, collapsing into one Worker a separate concern that should have had its own Worker). The guard / CI implementation for this section is a separate Issue.

### On DELEGATE_COMPLETE receipt

When you receive a dispatch-complete report from the Dispatcher, send a greeting message to each Worker:
```
mcp__renga-peers__send_message(
  to_id="worker-{task_id}",
  message="This is the Lead. You are assigned to {task_id}. Send all reports — completion, progress, and blockers — to `to_id=\"secretary\"` over renga-peers."
)
```

**Pre-approval via send_keys for `.claude/` edit tasks (root `.claude/**` self-edits only)**: when the delegation scope includes claude-org root `.claude/**` (excluding `.dispatcher/` / `.curator/`, and the worker-dir generated `.claude/settings.local.json`), the Secretary **follows up** the greeting above by typing an approval message into the worker pane via `mcp__renga-peers__send_keys` (enumerating the target files, the task_id, and explicit "user approval via the Lead" wording). The worker confirms the approval input exists before editing; if absent, it must not edit and must request the approval input from the Secretary (a fixed handshake that prevents deadlock / empty-press accidents). For the scope boundary, background (the 2-layer guard), approval-text template, and the mandatory wording for the worker brief, see [`.claude/skills/org-delegate/references/claude-org-self-edit.md`](references/claude-org-self-edit.md) §5 as the primary source.

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

- Return ack to the worker (see the "completion report ack" section of [`.claude/skills/org-delegate/references/ack-template.md`](references/ack-template.md); immediately on receipt, before any other state update, to prevent dead-lock)
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
- **Use the human-comprehension summary as the basis of the approval presentation and persist it (verification depth `full` only)**: A full-mode completion report includes a worker-written "human-comprehension summary" — (1) the N most important changes, (2) files / hunks that require review, (3) design decisions and rationale (schema SoT is [`.claude/skills/org-delegate/references/worker-claude-template.md`](references/worker-claude-template.md)). The Lead does not read the code itself; instead it uses this summary as the basis of the approval presentation to the user (rephrasing into business language as needed). Append the received summary to the Progress Log of `.state/workers/worker-{task_id}.md` verbatim under a `Human Understanding Summary:` heading followed directly by a fenced code block (this is the source that is re-presented at merge approval; if there are multiple full completion reports, the latest block is canonical). The PR description may also include a summary. **If a full completion report omits the summary, treat it as ordinary review feedback and ask the worker in the same pane to supply it** (handled via the review-feedback procedure in [`.claude/skills/org-pull-request/SKILL.md`](../org-pull-request/SKILL.md) 2c). This is a procedural-layer extension of the completion report format and does not change the contract (T4 `worker_completed`) transition condition. The 1-line `done:` report in minimal mode does not carry a summary
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
