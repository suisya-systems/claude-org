---
name: org-delegate
description: >
  Dispatch Worker Claude instances and delegate work to them. The Lead acts as the
  command node, and hands off hands-on execution to Workers by default.
  Trigger this when a user request requires file edits, implementation, research,
  or other execution work.
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

## Step 0.7 / 1 / 1.5 / 2: Generate the Dispatch Payload with One Command (Issue #283)

Step 0.7 (pre-check for `.gitignore`) / Step 1 (Pattern decision) / Step 1.5 (Worker directory preparation + role decision + settings generation) / Step 2 (`DELEGATE` body assembly) are handled **in one pass by `tools/gen_delegate_payload.py`**. The Lead is only responsible for task identification (Step 0), work-skill search (Step 0.5), target file extraction, and depth selection.

### Standard flow (recommended)

```bash
# 1. preview: fully non-destructive. Only check the DELEGATE body and the list of files to be created
python tools/gen_delegate_payload.py preview \
    --task-id <task-id> --project-slug <slug> \
    --target <path>... --description "<desc>" \
    --verification-depth full

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
