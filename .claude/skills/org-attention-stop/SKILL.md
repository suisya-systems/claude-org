---
name: org-attention-stop
description: >
  Stop the attention watcher pane started by `/org-attention-start`. It identity-checks the pane_id
  recorded in `.state/attention_pane.json` against the name/role from `list_panes`, and destroys the
  pane via `close_pane` (pane destroy) only when it still points at the attention watcher (if the
  pane_id has already been reassigned to another pane, it does not close it and deletes it as a stale sidecar).
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

## Step 1: reconcile live panes and the sidecar (fix identity before closing)

> **Why identity verification is needed (Issue #468)**: renga 0.18+ / broker **recycle** pane ids
> across lifecycles. When a watcher crashes, its pane_id can be reassigned to another pane (a freshly
> spawned worker, etc.). If you then `close_pane` the pane_id left in the sidecar
> (`.state/attention_pane.json`) **without verification, you kill an unrelated pane**. So this skill
> makes **only panes whose identity `list_panes` confirms by name/role the close targets**, and never
> uses the sidecar's pane_id as the direct basis for a close.

1. Call `mcp__org-broker__list_panes` and collect **all** live panes with `name="attention"` **or**
   `role="attention"` (all of them if there are several). Call this the "**confirmed attention pane
   set**" and record each pane's **numeric pane_id** (**check both name and role**: an orphaned pane
   from a manual start may have only the role without a name).
2. If `.state/attention_pane.json` can be opened with `Read`, read `pane_id` from it (= the **sidecar
   pane_id**). If it does not exist, treat it as "no sidecar".
3. Classify the sidecar pane_id's identity against the `list_panes` result (**do not trust the name
   recorded in the sidecar; judge by the name/role that `list_panes` returns now**):
   - **verified**: the sidecar pane_id is in the "confirmed attention pane set" → that pane is still
     the real watcher. It is a close target.
   - **recycled**: the sidecar pane_id exists in `list_panes`, but that pane's name/role is **not**
     attention → the pane_id has been reassigned to an unrelated pane (a worker, etc.). **Never close it.**
   - **gone**: the sidecar pane_id is not in `list_panes` → the watcher is already gone.
   - **no sidecar**: skip the classification above (only consider cleaning up orphan panes).

   If the classification is ambiguous (the `list_panes` name/role is empty / unclear), you may reinforce
   it by inspecting the content with `mcp__org-broker__inspect_pane(target="<sidecar pane_id>")`, but the
   **primary identity source is the name/role that `list_panes` returns**.

## Step 2: decide and execute the close targets

**The only panes you may close are those in the "confirmed attention pane set"** (only panes whose
identity was verified). The sidecar pane_id becomes a close target **only when verified (= when that id
is in the confirmed set)**. A recycled / gone sidecar pane_id is not a close target.

Close each pane in the confirmed attention pane set in turn, by the **numeric pane_id obtained from
`list_panes`**:

```
mcp__org-broker__close_pane(target="<numeric pane_id from the confirmed set>")
```

- On success: text `"Closed pane id=N."` returns.
- `[pane_not_found]` / `[pane_vanished]`: it vanished just now; treat as skip and move on.
- `[last_pane]`: the attention pane was the tab's only remaining pane (does not normally happen —
  dispatcher / secretary should still be alive). Report the situation to the user and abort
  (defer to manual handling).

**Do not use a name target** like `target="attention"` (it would not hit an orphan pane that has only
the role and no name). Always specify the numeric pane_id.

Behavior by classification:

- **verified**: the sidecar pane_id is in the confirmed set, so it is closed together by the close
  above. If the set contains other attention panes (drift / double-start orphans), close those too,
  likewise by numeric pane_id.
- **recycled / gone**: **do not close** the sidecar pane_id. However, if the confirmed set contains an
  orphan watcher (with an id different from the sidecar's), close it by numeric pane_id. The watcher the
  sidecar pointed at is already gone → in Step 4, report "the watcher was already gone (the sidecar is
  stale)".
- **no sidecar**: if the confirmed set contains an orphan attention pane, close it by numeric pane_id.
  If the set is empty, do nothing to close (report "already stopped" in Step 4).

## Step 3: delete the sidecar

If the sidecar existed, **always delete it regardless of classification** (delete it both after a
verified close and when it was classified stale as recycled / gone):

```bash
rm -f .state/attention_pane.json
```

Windows native: `del .state\attention_pane.json` (already-deleted is harmless — suppress with
`2>nul` etc.).

Append a single journal event line. Record `attention_watch_stopped` **only when there is a pane that
was actually closed** (if you performed no close because of recycled / gone, omit `<N>` and add
`reason=stale_sidecar` so an unrelated pane is not falsely recorded as stopped):

```bash
# when you closed a confirmed attention pane (verified / orphan cleanup)
bash tools/journal_append.sh attention_watch_stopped pane_id=<N>

# when the sidecar was recycled / gone and you performed no close
bash tools/journal_append.sh attention_watch_stopped reason=stale_sidecar
```

On Windows native: `py -3 tools/journal_append.py attention_watch_stopped ...`.

## Step 4: report

**For verified (stopped the recorded watcher) / orphan cleanup**:

```
Stopped the attention watcher (pane id={N}).
Run /org-attention-start to start it again.
```

**For recycled / gone (the sidecar was stale and the watcher itself was already gone)** — report
explicitly that you did not close an unrelated pane:

```
The attention watcher was already gone (the sidecar is stale).
The recorded pane id={sidecar pane_id} had already been reassigned to another pane / already vanished,
so to avoid closing an unrelated pane no close was performed; only the stale sidecar was deleted.
Run /org-attention-start to start it again.
```

(If in the recycled case you also cleaned up an orphan watcher with a different id, add one line above:
"also cleaned up orphan attention pane id={M}".)

**If there was no sidecar and no orphan pane**:

```
The attention watcher is already stopped.
```
