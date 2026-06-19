# Ack template — Lead → worker peer message

Acknowledgement template that the Lead sends in response to a peer message from a worker. SKILL.md Step 5's "Canonical event flow" requires it as **step 1**.

> **Transport layer both systems (`ORG_TRANSPORT`: default `renga` / opt-in `broker`)**: the `mcp__renga-peers__send_message` in the examples below is **default `renga`** (`ORG_TRANSPORT` unset). Under `ORG_TRANSPORT=broker` (opt-in, revertible), the fully qualified name gets machine-substituted from **`mcp__renga-peers__send_message` → `mcp__org-broker__send_message`** (argument shape, address specification, and ack text are identical). The worker's report-receipt is not an in-band push but a **pane-local nudge + `check_messages` pull**, so the Lead's order becomes "see the nudge → pull the body via `mcp__org-broker__check_messages` → ack" (the ack-mandatory / dead-lock prevention nature is invariant across systems). See [`docs/contracts/backend-interface-contract.md`](../../../../docs/contracts/backend-interface-contract.md) Surface 8 (awaiting ratification) and the broker section of [`.claude/skills/org-delegate/references/renga-error-codes.md`](renga-error-codes.md) for details. The default-renga example texts are unchanged (broker is additive).

## Why ack is mandatory

- worker-claude-template instructs workers to end completion / progress reports with "Holding the pane. Awaiting next instructions."
- If the Lead does not send an ack, the worker has no way to know whether the message reached the Lead or what to do next, and idles in a dead-lock.
- This was actually observed as a failure mode in session #13 — the Lead mistook "I reported to the user" for "I replied to the worker".
- ack ≠ user approval. The ack is a receipt confirmation that releases the dead-lock; it grants no push / PR authority.

## Minimum content of an ack (3 required elements)

1. **Receipt confirmation**: "received", "acknowledged", "got it", etc.
2. **Next step**: PR creation pending user approval / awaiting CI / additional review needed / awaiting human judgment, etc.
3. **Pane state**: hold / scheduled to close.

## Example messages by category

### Progress-report ack

```
mcp__renga-peers__send_message(
  to_id="worker-{task_id}",
  message="Progress received. OK to continue. Once complete, report back with the same to_id=\"secretary\". Hold the pane."
)
```

### Completion-report ack (PR not yet created)

```
mcp__renga-peers__send_message(
  to_id="worker-{task_id}",
  message="Completion report received. I'll now report to the user, get approval, and the Lead will perform the push / PR creation. Hold the pane and stand by. If CI fails or review feedback arrives, I'll send the next instruction in the same pane."
)
```

(If a full completion report omits the "human-comprehension summary", do not define a special ack for it; treat it as ordinary review feedback and ask the same pane to supply it. See [`.claude/skills/org-delegate/SKILL.md`](../SKILL.md) Step 5 (2a) / [`.claude/skills/org-pull-request/SKILL.md`](../../org-pull-request/SKILL.md) 2c for the procedure.)

### Codex self-review round-completion ack

```
mcp__renga-peers__send_message(
  to_id="worker-{task_id}",
  message="Codex round received. If there are Blocker / Major issues, fix them in a follow-up commit and proceed to the next round. Up to a 3-round cap is OK. If only Minor / Nit remain, switch to the final completion report. Hold the pane."
)
```

### Judgment-escalation ack

```
mcp__renga-peers__send_message(
  to_id="worker-{task_id}",
  message="Judgment-escalation received. The Lead does not pre-approve; I'll confirm with the user. Hold the pane and wait for the response (do not auto-continue)."
)
```

For judgment escalations, also follow SKILL.md Step 5 subsection 0: append to the Progress Log, append a `worker_escalation` journal entry, and `pending_decisions append` in parallel. The ack is an independent feedback channel back to the worker.

### Block-report ack

The same wording as the judgment-escalation ack is fine. Depending on the nature of the block, also include the next plan explicitly: "this task is paused; we may reassign it to another worker", "the pane will be closed", etc.

## Anti-patterns

- ❌ Skipping the ack and only doing run.status update + user report → worker dead-lock.
- ❌ Writing "OK, pushing now" in the ack and pushing before user approval → violates the user-approval gate (SKILL.md Step 5 (2a→2b) gate).
- ❌ Using a post-user-approval "proceeding now" notice in place of an ack → during the lag between completion report and user approval, the worker idles and waits. The ack must be sent immediately upon receipt.
