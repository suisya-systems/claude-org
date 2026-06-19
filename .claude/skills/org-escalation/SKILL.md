---
name: org-escalation
description: >
  When a worker sends a peer message such as "judgment escalation",
  "approval request", "OK to continue?", "scope-expansion proposal",
  "unexpected", "runbook deviation", or "block / blocker", the Lead
  does NOT pre-approve and instead escalates to the human.
  Triggers: receipt of a judgment-escalation / scope-expansion /
  blocker message from a worker.
  Normal progress / completion reports are handled by org-delegate
  Step 5 (1) / (2a). This skill owns the canonical "do not approve
  on your own; update the registers" flow.
effort: medium
allowed-tools:
  - Read
  - Edit
  - Bash(bash tools/journal_append.sh:*)
  - Bash(python tools/pending_decisions.py:*)
  - Bash(py -3 tools/pending_decisions.py:*)
  - mcp__renga-peers__send_message
---

# org-escalation: judgment-escalation / scope-expansion / blocker escalation

When the Lead receives a peer message containing "approval request", "judgment escalation", "OK to continue?", "scope expansion", "proposal", "unexpected", "runbook deviation", "block", "blocker", or similar, the Lead **does not pre-approve** and escalates to the human. The Lead is a relay role, not a judgment layer.

> **Transport — both backends (default `broker` / opt-in `renga`)**: the peer-message and pane operations in this file (and across the skills) are written as `mcp__org-broker__*`. With **`ORG_TRANSPORT` unset = default `broker`**, follow them as-is. With `ORG_TRANSPORT=renga` (opt-in, revertible), the MCP server name becomes `renga-peers`, and the **fully qualified names are mechanically substituted `mcp__org-broker__*` → `mcp__renga-peers__*`** (argument shape and semantics are identical, so the operational logic does not change). The three transport-dependent differences are:
>
> - **Receive model (default = push-primary = `claude/channel` / pull fallback)**: the default broker is designed as **push-primary** (runtime push-first 0.1.24+; design SoT is transport-lab `docs/design/broker-native-roles.md` §9). A **channel sidecar** (`server:org-broker-channel`) co-located with each pane claims the broker queue at ~1s intervals and pushes via `notifications/claude/channel`, injecting the body into an idle session (creating the "respond as soon as it arrives" trigger). Worker ack (`to_id="worker-{task_id}"`), retro-gate ack (`to_id="dispatcher"`), and the dispatcher handover route's `send_message` / `check_messages` / `send_keys` / `inspect_pane` all work under the same tool names (`mcp__org-broker__*`). **Pull is the fallback layer**: when the sidecar is absent or unhealthy (heartbeat timeout flips to `delivery_mode=PULL`), for channel-incapable panes (codex pull-peer), or when claude.ai login is missing, each role actively `check_messages` on its own cadence (per-role cadence: worker = turn boundary / bounded `/loop` after completion; dispatcher = `/loop 3m`; secretary = at turn start; the existing "when you see a nudge, `check_messages`" prose is **not retracted** and should be read as this fallback cadence). With `ORG_TRANSPORT=renga` (opt-in), worker reports and dispatcher responses are pushed in-band as `<channel source="renga-peers" …>` (renga's in-band push and broker push-primary share the same immediate-response trigger). Contract-wise, push-primary is **ratified** on Surface 8 + push-primary amendment (2026-06-15, S3; pull is retained as fallback; renga is unchanged).
> - **Spawn ritual (default = folder-trust approval + dev-channel sidecar approval, 2 steps)**: when spawning a child pane, the default broker injects `--mcp-config <broker>` and mechanically approves Claude Code's **folder-trust prompt** with `send_keys(enter=true)`, **and in addition**, loads the channel sidecar via `--dangerously-load-development-channels server:org-broker-channel` for push-primary and mechanically approves the dev-channel approval prompt (spawn-flow 3-3b) with `send_keys(enter=true)` (folder-trust + dev-channel = 2-step approval; details in [`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md) 3-2 / 3-3b, design in broker-native-roles.md §9.5). With `ORG_TRANSPORT=renga` (opt-in), it injects `--dangerously-load-development-channels server:renga-peers` and approves the "Load development channel?" prompt with Enter — 1 step. **Note: the attention watcher is a transport-independent CLI pane and is exempt from both the folder-trust and dev-channel 2-step approvals** (do not pull it into the spawn-ritual inversion).
> - **Error branching (default = broker extended codes included)**: in addition to the shared codes (`pane_not_found` / `last_pane` / `invalid-params`, Surface 6), the default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` / `[unknown_tool]` (unknown codes escalate via the default branch). With `ORG_TRANSPORT=renga`, broker-specific codes never occur — only shared codes + renga-specific codes.
>
> The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14) + the tail "Ratified amendment (2026-06-15): push-primary delivery" (S3; **broker push-primary is the default contract**, pull is retained as structural fallback). Design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary) / `docs/design/ja-migration-plan.md` §5 and §8. **The opt-in `renga` is not deleted and is maintained as a permanently-available fallback** (the revert safety net). Broker actual-run (dogfood) is in scope for Epic #6 Issue G and is **not** the default operational route in this file (**Two-frame note on "default" (Refs #604)**: "default `broker`" here refers to the **code-default** frame — `tools/transport.py: DEFAULT_TRANSPORT` has been flipped to `broker` in runtime 0.1.28 (Epic #586), and the ja generator / `transport.resolve()` render against this code frame, so the generated surface displays it this way. There is a separate **operational-default** frame in which the operational default route is `renga`, because broker actual-run dogfood is not yet activated through Epic #6 Issue G. The two frames refer to different objects (code constant vs. operational route) and do not contradict each other. The overview is in root [`CLAUDE.md`](../../../CLAUDE.md), section "Transport — both backends".)

> **Why state preservation matters**: so that a Lead restart or handoff
> does not lose pending decisions, write to all 3 layers (Progress Log /
> events / pending-decisions register) at the same time. Missing any
> of them causes the Dispatcher's SECRETARY_RELAY_GAP_SUSPECTED detector
> ([`../../../.dispatcher/references/worker-monitoring.md` Step 5.1](../../../.dispatcher/references/worker-monitoring.md#step-5-1)) to either misfire or miss real gaps.

> **ack template SoT**: the 3 required elements, example messages, and
> anti-patterns for the judgment-escalation ack live in
> [`.claude/skills/org-delegate/references/ack-template.md`](../org-delegate/references/ack-template.md). This skill does not duplicate them; it links and delegates.

## Canonical flow

1. **Send the ack to the worker first** (before state preservation or relaying to the user). Refer to the "judgment-escalation ack" section of [`.claude/skills/org-delegate/references/ack-template.md`](../org-delegate/references/ack-template.md) (this skill does not duplicate it).
   - **The Lead does not pre-approve.** The reply to the worker is only "received; I will check with the human."
   - Do not approve on the basis of self-interpretation such as "the user picked option X so this is implicitly included" or "this falls within the overall intent" (see CLAUDE.md `feedback_relay_user_decisions_to_workers`).
   - ack ≠ user approval: the ack is a receipt confirmation that releases the worker's dead-lock; it grants no push / PR authority.

2. **Persist state** (3 layers simultaneously, none may be skipped):
   - Append to the Progress Log of `.state/workers/worker-{task_id}.md` with "received judgment escalation" and the key points.
   - Append to the DB events table:
     ```bash
     bash tools/journal_append.sh worker_escalation worker=worker-{task_id} task={task_id} reason="<summary>"
     ```
   - **Append to the pending-decisions register** (Issue #297):
     ```bash
     python tools/pending_decisions.py append --task-id {task_id} --message "<body summary>"
     ```
     If a pending entry for the same task_id already exists this is idempotent (no-op). The register is the primary lookup source for the Dispatcher's SECRETARY_RELAY_GAP_SUSPECTED detector ([`../../../.dispatcher/references/worker-monitoring.md` Step 5.1](../../../.dispatcher/references/worker-monitoring.md#step-5-1)).

3. **Relay to the human**: organize the content and the options and present them. **At the moment you present the options (the ask moment)**, immediately before updating the register to `escalated` via `resolve --kind to_user`, emit an awaiting_user signal to the attention watcher (Issue #28, ask-time gate):
   ```bash
   bash tools/journal_append.sh notify_sent kind=awaiting_user task_id={task_id} gate=escalation_to_user note="<short summary of the options presented>"
   python tools/pending_decisions.py resolve --task-id {task_id} --kind to_user
   ```
   The classifier picks it up as `secretary_awaiting_user` (default severity `urgent`) and beeps the instant a decision is requested. In interactive use the user replies within tens of seconds to a few minutes, so pending_decision aging (15 min) effectively never fires, which makes this ask-time emit the primary route for the urgent notification. The Step 4.5 emit (`escalation_reply_forward`) remains a separate forward-time emit (Step 3 = ask time / 4.5 = forward time). This emit only appends a single journal line and does not touch the register or pending_decisions state.

4. **The moment a reply arrives from the user** — **before** forwarding it to the worker — record `user_replied_at` in the register (Issue #301):
   ```bash
   python tools/pending_decisions.py mark-user-replied --task-id {task_id}
   ```
   No-op if no escalated entry exists; idempotent if already set. This lets [`../../../.dispatcher/references/worker-monitoring.md` Step 5.1 (a-2)](../../../.dispatcher/references/worker-monitoring.md#step-5-1) deterministically detect "user has replied but Lead forgot to relay".

4.5. **Emit the awaiting_user notification (Issue #28)**: on the `mark-user-replied` → `resolve --kind to_worker` boundary, emit one line telling the attention watcher about the user-driven action on the Secretary side between "the user reply has landed at the Secretary" and "the Secretary forwards it to the worker":
   ```bash
   bash tools/journal_append.sh notify_sent kind=awaiting_user task_id={task_id} gate=escalation_reply_forward note="<short summary of the decision>"
   ```
   The classifier in the parallel runtime PR picks it up as `secretary_awaiting_user` (default severity `urgent`). See the "Notify when the Secretary is waiting on a user judgment" section in CLAUDE.md. This emit leaves no side effects regardless of whether an escalated entry exists (a single journal-line append only; it does not touch the register or pending_decisions).

5. **Relay the human's decision to the worker** (`send_message` with `to_id="worker-{task_id}"`). Right after sending, update the register to `resolved`:
   ```bash
   python tools/pending_decisions.py resolve --task-id {task_id} --kind to_worker
   ```

## Triple-redundancy policy

- The 3 layers (Progress Log / journal events / pending-decisions register) are **maintained independently as overlapping insurance.**
- Missing either the register `append` or `resolve` causes the Dispatcher to fire SECRETARY_RELAY_GAP_SUSPECTED erroneously (alert fires after a relay was actually done) or to miss it (cannot detect a forgotten relay).
- Blocker reports are also handled by this skill. When a blocker overlaps with a judgment escalation, this flow takes priority.

## Out of scope (not handled here)

- Progress reports (Progress Log append + ack only; no user report or approval gate) → `.claude/skills/org-delegate/SKILL.md` Step 5 (1).
- Completion reports (REVIEW transition + user report + approval gate) → `.claude/skills/org-delegate/SKILL.md` Step 5 (2a).
- Post-approval push / PR creation / review loop / post-merge close → `.claude/skills/org-pull-request/SKILL.md`.
- Worker monitoring & intervention triage (deep-dive detection / Esc cancel / tight fix-instructions) → `.claude/skills/org-delegate/SKILL.md` "Worker monitoring & intervention triage".
