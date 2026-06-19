---
name: org-attention-stop
description: >
  Stop the attention watcher pane started by `/org-attention-start`. It reads the pane_id recorded
  in `.state/attention_pane.json`, closes the pane via `mcp__renga-peers__close_pane`, and deletes
  the sidecar.
  Triggered by "stop attention", "halt notification monitoring", "shut down the watcher", etc.
effort: low
allowed-tools:
  - Read
  - Bash(rm:*)
  - Bash(del:*)
  - Bash(bash tools/journal_append.sh:*)
  - Bash(py -3 tools/journal_append.py:*)
  - mcp__renga-peers__*
---

# org-attention-stop: stop the attention watcher

Close the watcher pane started by [`/org-attention-start`](../org-attention-start/SKILL.md) and
clear the sidecar (`.state/attention_pane.json`).

> **Transport — both backends (default `broker` / opt-in `renga`)**: the peer-message and pane operations in this file (and across the skills) are written as `mcp__org-broker__*`. With **`ORG_TRANSPORT` unset = default `broker`**, follow them as-is. With `ORG_TRANSPORT=renga` (opt-in, revertible), the MCP server name becomes `renga-peers`, and the **fully qualified names are mechanically substituted `mcp__org-broker__*` → `mcp__renga-peers__*`** (argument shape and semantics are identical, so the operational logic does not change). The three transport-dependent differences are:
>
> - **Receive model (default = push-primary = `claude/channel` / pull fallback)**: the default broker is designed as **push-primary** (runtime push-first 0.1.24+; design SoT is transport-lab `docs/design/broker-native-roles.md` §9). A **channel sidecar** (`server:org-broker-channel`) co-located with each pane claims the broker queue at ~1s intervals and pushes via `notifications/claude/channel`, injecting the body into an idle session (creating the "respond as soon as it arrives" trigger). Worker ack (`to_id="worker-{task_id}"`), retro-gate ack (`to_id="dispatcher"`), and the dispatcher handover route's `send_message` / `check_messages` / `send_keys` / `inspect_pane` all work under the same tool names (`mcp__org-broker__*`). **Pull is the fallback layer**: when the sidecar is absent or unhealthy (heartbeat timeout flips to `delivery_mode=PULL`), for channel-incapable panes (codex pull-peer), or when claude.ai login is missing, each role actively `check_messages` on its own cadence (per-role cadence: worker = turn boundary / bounded `/loop` after completion; dispatcher = `/loop 3m`; secretary = at turn start; the existing "when you see a nudge, `check_messages`" prose is **not retracted** and should be read as this fallback cadence). With `ORG_TRANSPORT=renga` (opt-in), worker reports and dispatcher responses are pushed in-band as `<channel source="renga-peers" …>` (renga's in-band push and broker push-primary share the same immediate-response trigger). Contract-wise, push-primary is **ratified** on Surface 8 + push-primary amendment (2026-06-15, S3; pull is retained as fallback; renga is unchanged).
> - **Spawn ritual (default = folder-trust approval + dev-channel sidecar approval, 2 steps)**: when spawning a child pane, the default broker injects `--mcp-config <broker>` and mechanically approves Claude Code's **folder-trust prompt** with `send_keys(enter=true)`, **and in addition**, loads the channel sidecar via `--dangerously-load-development-channels server:org-broker-channel` for push-primary and mechanically approves the dev-channel approval prompt (spawn-flow 3-3b) with `send_keys(enter=true)` (folder-trust + dev-channel = 2-step approval; details in [`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md) 3-2 / 3-3b, design in broker-native-roles.md §9.5). With `ORG_TRANSPORT=renga` (opt-in), it injects `--dangerously-load-development-channels server:renga-peers` and approves the "Load development channel?" prompt with Enter — 1 step. **Note: the attention watcher is a transport-independent CLI pane and is exempt from both the folder-trust and dev-channel 2-step approvals** (do not pull it into the spawn-ritual inversion).
> - **Error branching (default = broker extended codes included)**: in addition to the shared codes (`pane_not_found` / `last_pane` / `invalid-params`, Surface 6), the default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` / `[unknown_tool]` (unknown codes escalate via the default branch). With `ORG_TRANSPORT=renga`, broker-specific codes never occur — only shared codes + renga-specific codes.
>
> The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14) + the tail "Ratified amendment (2026-06-15): push-primary delivery" (S3; **broker push-primary is the default contract**, pull is retained as structural fallback). Design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary) / `docs/design/ja-migration-plan.md` §5 and §8. **The opt-in `renga` is not deleted and is maintained as a permanently-available fallback** (the revert safety net). Broker actual-run (dogfood) is in scope for Epic #6 Issue G and is **not** the default operational route in this file (**Two-frame note on "default" (Refs #604)**: "default `broker`" here refers to the **code-default** frame — `tools/transport.py: DEFAULT_TRANSPORT` has been flipped to `broker` in runtime 0.1.28 (Epic #586), and the ja generator / `transport.resolve()` render against this code frame, so the generated surface displays it this way. There is a separate **operational-default** frame in which the operational default route is `renga`, because broker actual-run dogfood is not yet activated through Epic #6 Issue G. The two frames refer to different objects (code constant vs. operational route) and do not contradict each other. The overview is in root [`CLAUDE.md`](../../../CLAUDE.md), section "Transport — both backends".)

## Step 1: check sidecar and live-pane state

1. Call `mcp__renga-peers__list_panes`. If a live pane with `name="attention"` or
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
mcp__renga-peers__close_pane(target="<sidecar pane_id>")
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
mcp__renga-peers__close_pane(target="<numeric pane_id from list_panes>")
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
