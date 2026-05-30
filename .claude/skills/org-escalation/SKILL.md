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
