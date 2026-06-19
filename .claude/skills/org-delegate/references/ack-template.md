# Ack template — Lead → worker peer message

Acknowledgement template that the Lead sends in response to a peer message from a worker. SKILL.md Step 5's "Canonical event flow" requires it as **step 1**.
> **Transport (dual-rail) - default `broker` / opt-in `renga`**: This file (and each skill) writes its peer-message / pane operations as `mcp__org-broker__*`, so with **`ORG_TRANSPORT` unset = default `broker`** you can follow the prose as-is. Under `ORG_TRANSPORT=renga` (opt-in, revertible) the MCP server name becomes `renga-peers`, and the **fully-qualified names mechanically rewrite from `mcp__org-broker__*` to `mcp__renga-peers__*`** (the argument shape and semantics are identical, so the operation logic does not change). Only the following three points differ between the rails:
>
> - **Receive model (default = push-primary = `claude/channel` / pull fallback)**: Default broker is designed as **push-primary** (runtime push-first 0.1.24+, design SoT in transport-lab `docs/design/broker-native-roles.md` §9): each pane's co-resident **channel sidecar** (`server:org-broker-channel`) claims the broker queue at ~1s intervals and pushes by injecting bodies into idle sessions via `notifications/claude/channel` (a "receive then immediately respond" moment arises). Worker acks (`to_id="worker-{task_id}"`), retro-gate acks (`to_id="dispatcher"`), and the dispatcher-handover path all use the same tool names (`mcp__org-broker__*`) for `send_message` / `check_messages` / `send_keys` / `inspect_pane`. **Pull is the fallback layer**: when the sidecar is absent / unhealthy (heartbeat timeout flips `delivery_mode=PULL`) / on channel-unsupported panes (codex pull-peer) / when claude.ai login is missing, each role actively `check_messages` at its own cadence (per-role cadence: worker = turn boundary / bounded `/loop` after completion; dispatcher = `/loop 3m`; secretary = top-of-turn). The existing "if a nudge arrives, then `check_messages`" prose is **not retracted** and should be read as this fallback cadence. Under `ORG_TRANSPORT=renga` (opt-in), worker reports and dispatcher responses are pushed in-band as `<channel source="renga-peers" ...>` (renga's in-band push and broker push-primary share the same immediate-response moment). On contract surface, push-primary is **ratified** under Surface 8 + push-primary amendment (2026-06-15, S3; pull retained as fallback; renga unchanged).
> - **Spawn ritual (default = folder-trust approval + dev-channel sidecar approval, two-step)**: When spawning child panes, default broker injects `--mcp-config <broker>` and machine-approves Claude Code's **folder-trust prompt** via `send_keys(enter=true)`, **and in addition** loads the channel sidecar via `--dangerously-load-development-channels server:org-broker-channel` for push-primary and machine-approves the dev-channel approval prompt (spawn-flow 3-3b) via `send_keys(enter=true)` (the two-step approval = folder-trust + dev-channel; see [`.dispatcher/references/spawn-flow.md`](../../../../.dispatcher/references/spawn-flow.md) 3-2 / 3-3b; design in broker-native-roles.md §9.5). Under `ORG_TRANSPORT=renga` (opt-in), it injects `--dangerously-load-development-channels server:renga-peers` and Enter-approves "Load development channel?" - a single step. **Note: the attention watcher is a transport-neutral CLI pane and is exempt from both folder-trust and dev-channel two-step approval** (do not drag it into the spawn-ritual flip).
> - **Error branches (default = broker extended codes included)**: Default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` / `[unknown_tool]` in addition to shared codes (`pane_not_found` / `last_pane` / `invalid-params`, Surface 6) (unknown codes are escalated via the default branch). Under `ORG_TRANSPORT=renga`, the broker-specific codes do not occur; only shared codes + renga-specific codes apply.
>
> The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../../docs/contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14) + the trailing "Ratified amendment (2026-06-15): push-primary delivery" (S3; **broker push-primary is the contract default**, pull retained as structural fallback). Design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary) / `docs/design/ja-migration-plan.md` §5, §8. **Opt-in `renga` is not removed; it is retained as an always-available fallback** (the revert safety net). Running broker is the default operational path.


> **Transport layer both systems (`ORG_TRANSPORT`: default `renga` / opt-in `broker`)**: the `mcp__renga-peers__send_message` in the examples below is **default `renga`** (`ORG_TRANSPORT` unset). Under `ORG_TRANSPORT=broker` (opt-in, revertible), the fully qualified name gets machine-substituted from **`mcp__renga-peers__send_message` → `mcp__org-broker__send_message`** (argument shape, address specification, and ack text are identical). The worker's report receive is also **push-primary** under broker (the per-pane channel sidecar `server:org-broker-channel` injects the body into idle via `notifications/claude/channel`; runtime push-first 0.1.24+, transport-lab `docs/design/broker-native-roles.md` §9), and the Lead's "arrival → immediate ack" order matches renga. **On push failure the fallback** is the Lead actively `mcp__org-broker__check_messages` at the start of each turn, and immediately ack on arrival (a nudge can be a trigger, but it does not wake an idle session, so an active poll is the canonical path — §9.6). The ack-mandatory / dead-lock prevention nature is invariant across systems and across layers. See [`docs/contracts/backend-interface-contract.md`](../../../../docs/contracts/backend-interface-contract.md) Surface 8 (ratified 2026-06-14; the push-primary additive amendment S3 is ratified 2026-06-15, with existing ratified text unchanged) and the broker section of [`.claude/skills/org-delegate/references/renga-error-codes.md`](renga-error-codes.md) for details. The default-renga example texts are unchanged (broker is additive).

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
mcp__org-broker__send_message(
  to_id="worker-{task_id}",
  message="Progress received. OK to continue. Once complete, report back with the same to_id=\"secretary\". Hold the pane."
)
```

### Completion-report ack (PR not yet created)

```
mcp__org-broker__send_message(
  to_id="worker-{task_id}",
  message="Completion report received. I'll now report to the user, get approval, and the Lead will perform the push / PR creation. Hold the pane and stand by. If CI fails or review feedback arrives, I'll send the next instruction in the same pane."
)
```

### Codex self-review round-completion ack

```
mcp__org-broker__send_message(
  to_id="worker-{task_id}",
  message="Codex round received. If there are Blocker / Major issues, fix them in a follow-up commit and proceed to the next round. Up to a 3-round cap is OK. If only Minor / Nit remain, switch to the final completion report. Hold the pane."
)
```

### Judgment-escalation ack

```
mcp__org-broker__send_message(
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
