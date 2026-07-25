---
name: org-retro
description: >
  Retrospective on the delegation process. When a worker delegation
  finishes, look back at how the delegation itself went and record
  process-improvement learnings. Also decide whether the completed
  task's pattern should be promoted to a work-skill.
  Technical retrospectives on the actual work are done by the worker
  automatically and are not handled here.
effort: medium
allowed-tools:
  - Read
  - Write
  - Edit
  - mcp__renga-peers__send_message
---

# org-retro: delegation-process retrospective

After a delegation to a worker finishes, look back at the delegation process itself and improve it.
Also decide whether the completed task's working pattern is reusable as a work-skill.

> **Transport — both backends (default `broker` / opt-in `renga`)**: the peer-message and pane operations in this file (and across the skills) are written as `mcp__org-broker__*`. With **`ORG_TRANSPORT` unset = default `broker`**, follow them as-is. With `ORG_TRANSPORT=renga` (opt-in, revertible), the MCP server name becomes `renga-peers`, and the **fully qualified names are mechanically substituted `mcp__org-broker__*` → `mcp__renga-peers__*`** (argument shape and semantics are identical, so the operational logic does not change). The three transport-dependent differences are:
>
> - **Receive model (default = push-primary = `claude/channel` / pull fallback)**: the default broker is designed as **push-primary** (runtime push-first 0.1.24+; design SoT is transport-lab `docs/design/broker-native-roles.md` §9). A **channel sidecar** (`server:org-broker-channel`) co-located with each pane claims the broker queue at ~1s intervals and pushes via `notifications/claude/channel`, injecting the body into an idle session (creating the "respond as soon as it arrives" trigger). Worker ack (`to_id="worker-{task_id}"`), retro-gate ack (`to_id="dispatcher"`), and the dispatcher handover route's `send_message` / `check_messages` / `send_keys` / `inspect_pane` all work under the same tool names (`mcp__org-broker__*`). **Pull is the fallback layer**: when the sidecar is absent or unhealthy (heartbeat timeout flips to `delivery_mode=PULL`), for channel-incapable panes (codex pull-peer), or when claude.ai login is missing, each role actively `check_messages` on its own cadence (per-role cadence: worker = turn boundary / bounded `/loop` after completion; dispatcher = `/loop 3m`; secretary = at turn start; the existing "when you see a nudge, `check_messages`" prose is **not retracted** and should be read as this fallback cadence). With `ORG_TRANSPORT=renga` (opt-in), worker reports and dispatcher responses are pushed in-band as `<channel source="renga-peers" …>` (renga's in-band push and broker push-primary share the same immediate-response trigger). Contract-wise, push-primary is **ratified** on Surface 8 + push-primary amendment (2026-06-15, S3; pull is retained as fallback; renga is unchanged).
> - **Spawn ritual (default = folder-trust approval + dev-channel sidecar approval, 2 steps)**: when spawning a child pane, the default broker injects `--mcp-config <broker>` and mechanically approves Claude Code's **folder-trust prompt** with `send_keys(enter=true)`, **and in addition**, loads the channel sidecar via `--dangerously-load-development-channels server:org-broker-channel` for push-primary and mechanically approves the dev-channel approval prompt (spawn-flow 3-3b) with `send_keys(enter=true)` (folder-trust + dev-channel = 2-step approval; details in [`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md) 3-2 / 3-3b, design in broker-native-roles.md §9.5). With `ORG_TRANSPORT=renga` (opt-in), it injects `--dangerously-load-development-channels server:renga-peers` and approves the "Load development channel?" prompt with Enter — 1 step. **Note: the attention watcher is a transport-independent CLI pane and is exempt from both the folder-trust and dev-channel 2-step approvals** (do not pull it into the spawn-ritual inversion).
> - **Error branching (default = broker extended codes included)**: in addition to the shared codes (`pane_not_found` / `last_pane` / `invalid-params`, Surface 6), the default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` / `[unknown_tool]` (unknown codes escalate via the default branch). With `ORG_TRANSPORT=renga`, broker-specific codes never occur — only shared codes + renga-specific codes.
>
> The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14) + the tail "Ratified amendment (2026-06-15): push-primary delivery" (S3; **broker push-primary is the default contract**, pull is retained as structural fallback). Design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary) / `docs/design/ja-migration-plan.md` §5 and §8. **The opt-in `renga` is not deleted and is maintained as a permanently-available fallback** (the revert safety net). Broker actual-run (dogfood) is in scope for Epic #6 Issue G and is **not** the default operational route in this file (**Two-frame note on "default" (Refs #604)**: "default `broker`" here refers to the **code-default** frame — `tools/transport.py: DEFAULT_TRANSPORT` has been flipped to `broker` in runtime 0.1.28 (Epic #586), and the ja generator / `transport.resolve()` render against this code frame, so the generated surface displays it this way. There is a separate **operational-default** frame in which the operational default route is `renga`, because broker actual-run dogfood is not yet activated through Epic #6 Issue G. The two frames refer to different objects (code constant vs. operational route) and do not contradict each other. The overview is in root [`CLAUDE.md`](../../../CLAUDE.md), section "Transport — both backends".)

**Note**: technical learnings about the actual work (gotchas, API quirks, etc.) are recorded automatically by the worker into `knowledge/raw/` per CLAUDE.md instructions. They are not handled here.

> **Transport layer both systems (`ORG_TRANSPORT`: default `renga` / opt-in `broker`)**: this skill's `mcp__renga-peers__*` calls (report `send_message`) are written for **default `renga`** and can be followed as-is when `ORG_TRANSPORT` is unset (default behavior unchanged). Under `ORG_TRANSPORT=broker` (opt-in, revertible), the fully qualified names get machine-substituted to **`mcp__renga-peers__*` → `mcp__org-broker__*`**, and receive is also **push-primary** under broker (the channel sidecar `server:org-broker-channel` injects into idle via `notifications/claude/channel`; runtime push-first 0.1.24+, transport-lab `docs/design/broker-native-roles.md` §9). **On push failure the fallback** is an active `check_messages` (a nudge can be a trigger, but it does not wake an idle session, so an active poll is the canonical path — §9.6). Errors gain the broker-specific codes (see the broker section in [`.claude/skills/org-delegate/references/renga-error-codes.md`](../org-delegate/references/renga-error-codes.md)). The design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary redesign) / `docs/design/ja-migration-plan.md` §5.2(ii); the contract is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (ratified 2026-06-14; the push-primary additive amendment S3 is ratified 2026-06-15, with existing ratified text unchanged). The default-renga procedure is unchanged (broker is additive).

## Step 1: retrospective on the delegation process

Sort out the following:
- **Was the task split right?** Was the granularity too coarse / too fine?
- **Were the instructions clear?** Did the worker proceed without confusion? Were there many questions?
- **Was the project chosen correctly?** Did the worker work in the right directory?
- **Was the parallelism right?** Were there too many / too few workers?
- **Was the completion report sufficient?** Did it give enough material to brief the human?

## Step 2: decide what learnings to keep

Use these criteria to decide whether to record:

**Record if**:
- A pattern likely to recur in delegations of the same kind.
- An insight that improves the instruction template.
- A project-specific constraint that will likely affect the next delegation.
- A point where the worker's retrospective recording was insufficient or excessive — an improvement angle.

**Do not record if**:
- A one-off problem specific to this task.
- Already recorded by the worker as a technical learning.

## Step 3: record

If there is a learning, create a file at:

- Path: `knowledge/raw/{YYYY-MM-DD}-delegation-{topic}.md`
- `{topic}` is English kebab-case (e.g., `delegation-task-granularity`, `delegation-frontend-instructions`).
- Prefix with `delegation-` to distinguish from the worker's technical learnings.

### File format

See "Recording format" in `.claude/skills/org-curate/references/knowledge-standards.md`.

## Step 4: work-skill promotion judgment

Call `skill-eligibility-check` against the completed task's working pattern to decide whether to promote it to a work-skill.

The decision criteria themselves live in `.claude/skills/skill-eligibility-check/references/signals.md` and are referenced by both org-retro and org-curate (so the criteria do not drift).

### Step 4.1: call skill-eligibility-check

Construct and pass the following input:

```yaml
context: post_retro
pattern_name: <inferred skill name, kebab-case>
summary: <1–2 sentences on what is reusable>
task_ids: [<this task_id>]
raw_files: <array of paths under knowledge/raw/ that the worker recorded>
steps_outline:
  - <main step 1>
  - <main step 2>
  - ...
trigger_description: <situation in which this pattern applies>
decision_criteria: <decision criteria or thresholds>
output_format: <artifact structure>
```

The skill scores 5 signals and returns `decision`:
- `skill_recommend` (≥ 3 points)
- `candidate_queue` (2 points)
- `curated_only` (≤ 1 point)

For `skill_recommend`, the skill itself appends to `knowledge/skill-candidates.local.md` (the machine-local file holding the real entries, Issue #755; the public file keeps the format definition only).

### Step 4.2: branch on decision

#### decision == skill_recommend

1. Propose to the human:
   ```
   [work-skill proposal] This task's working pattern looks reusable as a work-skill.
   - Proposed skill name: {proposed_skill_name}
   - Reason: {matched_signals} (total {score}/5)
   - Summary: {what is reusable}

   Record it?
   ```
2. If the human approves:
   - **The Lead does NOT directly create / edit the skill file.** Per the ratification of Set E §2.4 (Q7), skill-promotion goes through `org-delegate` as a delegated task to a worker.
   - The Lead launches `org-delegate` and produces a worker task with role `claude-org-self-edit`. The instructions must include:
     - The target skill name `{skill-name}` and write target `.claude/skills/{skill-name}/SKILL.md`.
     - Template reference: `.claude/skills/org-retro/references/work-skill-template.md`.
     - The source (worker artifacts / raw learning files) and the policy of substituting task-specific values for placeholders.
     - That this is a skill-promotion delegation (one of the carve-outs of the Set A worker write-surface).
   - The Dispatcher / Lead does **not** write directly to `.claude/skills/{skill-name}/` or `knowledge/skill-candidates.local.md` (the file holding the real entries, Issue #755). Per Set E §1.4 / §2.4, the status transition on the `.local.md` entry (move to `approved`, fill `decision date`) is also the same delegated worker's responsibility; include it in the instructions.
3. If the human rejects:
   - Record the reason in `knowledge/raw/` for future use in similar judgments.
   - Updating the `knowledge/skill-candidates.local.md` entry (status → `rejected`, append the rejection reason) also goes through worker delegation (`org-delegate`); the Lead / Dispatcher does not edit it directly (per Set E §1.4 owner definition).
4. If the human picks "merge into an existing skill" (terminal status `merged-into-{existing-skill}`):
   - Identify the merge target and delegate to a skill-promotion worker via `org-delegate`: edit `.claude/skills/{existing-skill}/SKILL.md` to incorporate, and update the `knowledge/skill-candidates.local.md` entry's status to `merged-into-{existing-skill}` (fill the `merge target` field with the existing skill name).
   - Do not create a new skill file. The Lead / Dispatcher does not edit directly.
5. If the human picks "shelve it for now" (status `deferred`, Issue #753):
   - Updating the `knowledge/skill-candidates.local.md` entry's status from `pending` to `deferred` goes through worker delegation (`org-delegate`); the Lead / Dispatcher does not edit it directly (per Set E §1.4 owner definition).
   - `deferred` is not terminal, but it is **excluded from the threshold count and from re-asking**. Do not move the candidate back to `pending` afterwards, and do not dredge it up again in a batch ask or via `/skill-audit` (this is the countermeasure for shelved candidates needlessly spawning the curator on every worker close). Only when the human explicitly wants to reconsider later should a separate entry be raised under a new date.

#### decision == candidate_queue

Stays a candidate. The next time the same pattern reappears in raw, the raw_reappearance signal will fire, so do not promote yet. Recording the technical learning in `knowledge/raw/` proceeds normally (skip if the worker already recorded it).

#### decision == curated_only

Recording the technical learning in `knowledge/raw/` is enough (skip if the worker already recorded it).
No report required.

## Step 5: report

Briefly report to the human:
- If a learning was recorded: "Recorded a learning about the delegation process — {topic}".
- If proposing a work-skill: present the `skill_recommend` format from Step 4.2.
- For `candidate_queue` / `curated_only`: no report (move on silently).
