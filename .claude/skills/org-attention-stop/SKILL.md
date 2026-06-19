---
name: org-attention-stop
description: >
  Stop the attention watcher pane started by `/org-attention-start`. It reads the pane_id recorded
  in `.state/attention_pane.json`, closes the pane via `close_pane` (pane destroy), and deletes
  the sidecar.
  Triggered by "stop attention", "halt notification monitoring", "shut down the watcher", etc.
effort: low
allowed-tools:
  - Read
  - Bash(rm:*)
  - Bash(del:*)
  - Bash(bash tools/journal_append.sh:*)
  - Bash(py -3 tools/journal_append.py:*)
  - mcp__org-broker__check_messages
  - mcp__org-broker__close_pane
  - mcp__org-broker__inspect_pane
  - mcp__org-broker__list_panes
  - mcp__org-broker__list_peers
  - mcp__org-broker__poll_events
  - mcp__org-broker__send_keys
  - mcp__org-broker__send_message
  - mcp__org-broker__set_pane_identity
  - mcp__org-broker__set_summary
  - mcp__org-broker__spawn_claude_pane
  - mcp__org-broker__spawn_pane
---

# org-attention-stop: stop the attention watcher

Close the watcher pane started by [`/org-attention-start`](../org-attention-start/SKILL.md) and
clear the sidecar (`.state/attention_pane.json`).

> **Transport (dual-rail) - default `broker` / opt-in `renga`**: This file (and each skill) writes its peer-message / pane operations as `mcp__org-broker__*`, so with **`ORG_TRANSPORT` unset = default `broker`** you can follow the prose as-is. Under `ORG_TRANSPORT=renga` (opt-in, revertible) the MCP server name becomes `renga-peers`, and the **fully-qualified names mechanically rewrite from `mcp__org-broker__*` to `mcp__renga-peers__*`** (the argument shape and semantics are identical, so the operation logic does not change). Only the following three points differ between the rails:
>
> - **Receive model (default = push-primary = `claude/channel` / pull fallback)**: Default broker is designed as **push-primary** (runtime push-first 0.1.24+, design SoT in transport-lab `docs/design/broker-native-roles.md` §9): each pane's co-resident **channel sidecar** (`server:org-broker-channel`) claims the broker queue at ~1s intervals and pushes by injecting bodies into idle sessions via `notifications/claude/channel` (a "receive then immediately respond" moment arises). Worker acks (`to_id="worker-{task_id}"`), retro-gate acks (`to_id="dispatcher"`), and the dispatcher-handover path all use the same tool names (`mcp__org-broker__*`) for `send_message` / `check_messages` / `send_keys` / `inspect_pane`. **Pull is the fallback layer**: when the sidecar is absent / unhealthy (heartbeat timeout flips `delivery_mode=PULL`) / on channel-unsupported panes (codex pull-peer) / when claude.ai login is missing, each role actively `check_messages` at its own cadence (per-role cadence: worker = turn boundary / bounded `/loop` after completion; dispatcher = `/loop 3m`; secretary = top-of-turn). The existing "if a nudge arrives, then `check_messages`" prose is **not retracted** and should be read as this fallback cadence. Under `ORG_TRANSPORT=renga` (opt-in), worker reports and dispatcher responses are pushed in-band as `<channel source="renga-peers" ...>` (renga's in-band push and broker push-primary share the same immediate-response moment). On contract surface, push-primary is **ratified** under Surface 8 + push-primary amendment (2026-06-15, S3; pull retained as fallback; renga unchanged).
> - **Spawn ritual (default = folder-trust approval + dev-channel sidecar approval, two-step)**: When spawning child panes, default broker injects `--mcp-config <broker>` and machine-approves Claude Code's **folder-trust prompt** via `send_keys(enter=true)`, **and in addition** loads the channel sidecar via `--dangerously-load-development-channels server:org-broker-channel` for push-primary and machine-approves the dev-channel approval prompt (spawn-flow 3-3b) via `send_keys(enter=true)` (the two-step approval = folder-trust + dev-channel; see [`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md) 3-2 / 3-3b; design in broker-native-roles.md §9.5). Under `ORG_TRANSPORT=renga` (opt-in), it injects `--dangerously-load-development-channels server:renga-peers` and Enter-approves "Load development channel?" - a single step. **Note: the attention watcher is a transport-neutral CLI pane and is exempt from both folder-trust and dev-channel two-step approval** (do not drag it into the spawn-ritual flip).
> - **Error branches (default = broker extended codes included)**: Default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` / `[unknown_tool]` in addition to shared codes (`pane_not_found` / `last_pane` / `invalid-params`, Surface 6) (unknown codes are escalated via the default branch). Under `ORG_TRANSPORT=renga`, the broker-specific codes do not occur; only shared codes + renga-specific codes apply.
>
> The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14) + the trailing "Ratified amendment (2026-06-15): push-primary delivery" (S3; **broker push-primary is the contract default**, pull retained as structural fallback). Design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary) / `docs/design/ja-migration-plan.md` §5, §8. **Opt-in `renga` is not removed; it is retained as an always-available fallback** (the revert safety net). Running broker is the default operational path.

## Step 1: check sidecar and live-pane state

1. Call `mcp__org-broker__list_panes`. If a live pane with `name="attention"` or
   `role="attention"` exists, record its pane_id (**check both name and role**: an orphaned pane
   from a manual start may have only the role without a name).
2. If `.state/attention_pane.json` can be opened with `Read`, read `pane_id` from it. If it does
   not exist, skip.
3. Branch:
   - **sidecar present** → go to 2-a.
   - **sidecar absent + orphan pane detected** → go to 2-b.
   - **sidecar absent + no orphan pane** → report "the attention watcher is already stopped" and
     exit.

## Step 2: close the pane

### 2-a: close using the recorded pane_id

```
mcp__org-broker__close_pane(target="<sidecar pane_id>")
```

- On success: text `"Closed pane id=N."` returns.
- `[pane_not_found]` / `[pane_vanished]`: already closed. The sidecar is stale. Proceed to Step 3.
- `[last_pane]`: the attention pane was the tab's only remaining pane (does not normally happen —
  dispatcher / secretary should still be alive). Report the situation to the user and abort
  (defer to manual handling).

If the "attention pane visible in list_panes" obtained in Step 1 does not match the sidecar's
pane_id, **close using the sidecar's id first**, then re-fetch `list_panes`. If something
remains, proceed to 2-b (extra cleanup for drift / orphans).

### 2-b: cleaning up an orphan pane (no sidecar / drift)

Close using the **pane_id (the numeric id, not the name)** obtained from `list_panes` in Step 1:

```
mcp__org-broker__close_pane(target="<numeric pane_id from list_panes>")
```

Do not use a name target like `target="attention"`: it would not hit an orphan pane that has only
the role and no name. Treat `[pane_not_found]` / `[pane_vanished]` as skip.

## Step 3: delete the sidecar

```bash
rm -f .state/attention_pane.json
```

Windows native: `del .state\attention_pane.json` (already-deleted is harmless — suppress with
`2>nul` etc.).

Append a single journal event line:

```bash
bash tools/journal_append.sh attention_watch_stopped pane_id=<N>
```

On Windows native: `py -3 tools/journal_append.py attention_watch_stopped pane_id=<N>`.

## Step 4: report

```
Stopped the attention watcher (pane id={N}).
Run /org-attention-start to start it again.
```

If there was no sidecar and no orphan pane:

```
The attention watcher is already stopped.
```
