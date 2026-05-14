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

3. **Relay to the human**: organize the content and the options and present them. Right after presenting, update the register to `escalated`:
   ```bash
   python tools/pending_decisions.py resolve --task-id {task_id} --kind to_user
   ```

4. **The moment a reply arrives from the user** — **before** forwarding it to the worker — record `user_replied_at` in the register (Issue #301):
   ```bash
   python tools/pending_decisions.py mark-user-replied --task-id {task_id}
   ```
   No-op if no escalated entry exists; idempotent if already set. This lets [`../../../.dispatcher/references/worker-monitoring.md` Step 5.1 (a-2)](../../../.dispatcher/references/worker-monitoring.md#step-5-1) deterministically detect "user has replied but Lead forgot to relay".

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
