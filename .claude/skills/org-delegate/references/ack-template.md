# Ack template — Lead → worker peer message

Acknowledgement template that the Lead sends in response to a peer message from a worker. SKILL.md Step 5's "Canonical event flow" requires it as **step 1**.

> **Transport — both backends (default `broker` / opt-in `renga`)**: the peer-message and pane operations in this file (and across the skills) are written as `mcp__org-broker__*`. With **`ORG_TRANSPORT` unset = default `broker`**, follow them as-is. With `ORG_TRANSPORT=renga` (opt-in, revertible), the MCP server name becomes `renga-peers`, and the **fully qualified names are mechanically substituted `mcp__org-broker__*` → `mcp__renga-peers__*`** (argument shape and semantics are identical, so the operational logic does not change). The three transport-dependent differences are:
>
> - **Receive model (default = push-primary = `claude/channel` / pull fallback)**: the default broker is designed as **push-primary** (runtime push-first 0.1.24+; design SoT is transport-lab `docs/design/broker-native-roles.md` §9). A **channel sidecar** (`server:org-broker-channel`) co-located with each pane claims the broker queue at ~1s intervals and pushes via `notifications/claude/channel`, injecting the body into an idle session (creating the "respond as soon as it arrives" trigger). Worker ack (`to_id="worker-{task_id}"`), retro-gate ack (`to_id="dispatcher"`), and the dispatcher handover route's `send_message` / `check_messages` / `send_keys` / `inspect_pane` all work under the same tool names (`mcp__org-broker__*`). **Pull is the fallback layer**: when the sidecar is absent or unhealthy (heartbeat timeout flips to `delivery_mode=PULL`), for channel-incapable panes (codex pull-peer), or when claude.ai login is missing, each role actively `check_messages` on its own cadence (per-role cadence: worker = turn boundary / bounded `/loop` after completion; dispatcher = `/loop 3m`; secretary = at turn start; the existing "when you see a nudge, `check_messages`" prose is **not retracted** and should be read as this fallback cadence). With `ORG_TRANSPORT=renga` (opt-in), worker reports and dispatcher responses are pushed in-band as `<channel source="renga-peers" …>` (renga's in-band push and broker push-primary share the same immediate-response trigger). Contract-wise, push-primary is **ratified** on Surface 8 + push-primary amendment (2026-06-15, S3; pull is retained as fallback; renga is unchanged).
> - **Spawn ritual (default = folder-trust approval + dev-channel sidecar approval, 2 steps)**: when spawning a child pane, the default broker injects `--mcp-config <broker>` and mechanically approves Claude Code's **folder-trust prompt** with `send_keys(enter=true)`, **and in addition**, loads the channel sidecar via `--dangerously-load-development-channels server:org-broker-channel` for push-primary and mechanically approves the dev-channel approval prompt (spawn-flow 3-3b) with `send_keys(enter=true)` (folder-trust + dev-channel = 2-step approval; details in [`.dispatcher/references/spawn-flow.md`](../../../../.dispatcher/references/spawn-flow.md) 3-2 / 3-3b, design in broker-native-roles.md §9.5). With `ORG_TRANSPORT=renga` (opt-in), it injects `--dangerously-load-development-channels server:renga-peers` and approves the "Load development channel?" prompt with Enter — 1 step. **Note: the attention watcher is a transport-independent CLI pane and is exempt from both the folder-trust and dev-channel 2-step approvals** (do not pull it into the spawn-ritual inversion).
> - **Error branching (default = broker extended codes included)**: in addition to the shared codes (`pane_not_found` / `last_pane` / `invalid-params`, Surface 6), the default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` / `[unknown_tool]` (unknown codes escalate via the default branch). With `ORG_TRANSPORT=renga`, broker-specific codes never occur — only shared codes + renga-specific codes.
>
> The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../../docs/contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14) + the tail "Ratified amendment (2026-06-15): push-primary delivery" (S3; **broker push-primary is the default contract**, pull is retained as structural fallback). Design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary) / `docs/design/ja-migration-plan.md` §5 and §8. **The opt-in `renga` is not deleted and is maintained as a permanently-available fallback** (the revert safety net). Broker actual-run (dogfood) is in scope for Epic #6 Issue G and is **not** the default operational route in this file (**Two-frame note on "default" (Refs #604)**: "default `broker`" here refers to the **code-default** frame — `tools/transport.py: DEFAULT_TRANSPORT` has been flipped to `broker` in runtime 0.1.28 (Epic #586), and the ja generator / `transport.resolve()` render against this code frame, so the generated surface displays it this way. There is a separate **operational-default** frame in which the operational default route is `renga`, because broker actual-run dogfood is not yet activated through Epic #6 Issue G. The two frames refer to different objects (code constant vs. operational route) and do not contradict each other. The overview is in root [`CLAUDE.md`](../../../../CLAUDE.md), section "Transport — both backends".)

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
