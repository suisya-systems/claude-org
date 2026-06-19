---
name: secretary-resume
description: >
  Load the handover file written by /secretary-handover and resume the
  Secretary in a fresh session. Use it on the very first turn after /clear.
  Trigger phrases: "resume the Secretary", "resume", "pick up from the handover".
  This is not /org-start (Dispatcher / Curator are assumed to still be alive).
effort: low
allowed-tools:
  - Read
  - Bash(py -3 tools/journal_append.py:*)
  - mcp__org-broker__set_summary
  - mcp__org-broker__list_panes
  - mcp__org-broker__set_pane_identity
  - mcp__org-broker__list_peers
  - mcp__org-broker__check_messages
---

# secretary-resume: bring the Secretary back

Load `.state/secretary-handover.md` (written by `/secretary-handover`) and
restore the minimum Secretary awareness — your stance as an org member,
recent exchanges with the human, and in-flight work.

> **Transport (dual-rail) - default `broker` / opt-in `renga`**: This file (and each skill) writes its peer-message / pane operations as `mcp__org-broker__*`, so with **`ORG_TRANSPORT` unset = default `broker`** you can follow the prose as-is. Under `ORG_TRANSPORT=renga` (opt-in, revertible) the MCP server name becomes `renga-peers`, and the **fully-qualified names mechanically rewrite from `mcp__org-broker__*` to `mcp__renga-peers__*`** (the argument shape and semantics are identical, so the operation logic does not change). Only the following three points differ between the rails:
>
> - **Receive model (default = push-primary = `claude/channel` / pull fallback)**: Default broker is designed as **push-primary** (runtime push-first 0.1.24+, design SoT in transport-lab `docs/design/broker-native-roles.md` §9): each pane's co-resident **channel sidecar** (`server:org-broker-channel`) claims the broker queue at ~1s intervals and pushes by injecting bodies into idle sessions via `notifications/claude/channel` (a "receive then immediately respond" moment arises). Worker acks (`to_id="worker-{task_id}"`), retro-gate acks (`to_id="dispatcher"`), and the dispatcher-handover path all use the same tool names (`mcp__org-broker__*`) for `send_message` / `check_messages` / `send_keys` / `inspect_pane`. **Pull is the fallback layer**: when the sidecar is absent / unhealthy (heartbeat timeout flips `delivery_mode=PULL`) / on channel-unsupported panes (codex pull-peer) / when claude.ai login is missing, each role actively `check_messages` at its own cadence (per-role cadence: worker = turn boundary / bounded `/loop` after completion; dispatcher = `/loop 3m`; secretary = top-of-turn). The existing "if a nudge arrives, then `check_messages`" prose is **not retracted** and should be read as this fallback cadence. Under `ORG_TRANSPORT=renga` (opt-in), worker reports and dispatcher responses are pushed in-band as `<channel source="renga-peers" ...>` (renga's in-band push and broker push-primary share the same immediate-response moment). On contract surface, push-primary is **ratified** under Surface 8 + push-primary amendment (2026-06-15, S3; pull retained as fallback; renga unchanged).
> - **Spawn ritual (default = folder-trust approval + dev-channel sidecar approval, two-step)**: When spawning child panes, default broker injects `--mcp-config <broker>` and machine-approves Claude Code's **folder-trust prompt** via `send_keys(enter=true)`, **and in addition** loads the channel sidecar via `--dangerously-load-development-channels server:org-broker-channel` for push-primary and machine-approves the dev-channel approval prompt (spawn-flow 3-3b) via `send_keys(enter=true)` (the two-step approval = folder-trust + dev-channel; see [`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md) 3-2 / 3-3b; design in broker-native-roles.md §9.5). Under `ORG_TRANSPORT=renga` (opt-in), it injects `--dangerously-load-development-channels server:renga-peers` and Enter-approves "Load development channel?" - a single step. **Note: the attention watcher is a transport-neutral CLI pane and is exempt from both folder-trust and dev-channel two-step approval** (do not drag it into the spawn-ritual flip).
> - **Error branches (default = broker extended codes included)**: Default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` / `[unknown_tool]` in addition to shared codes (`pane_not_found` / `last_pane` / `invalid-params`, Surface 6) (unknown codes are escalated via the default branch). Under `ORG_TRANSPORT=renga`, the broker-specific codes do not occur; only shared codes + renga-specific codes apply.
>
> The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14) + the trailing "Ratified amendment (2026-06-15): push-primary delivery" (S3; **broker push-primary is the contract default**, pull retained as structural fallback). Design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary) / `docs/design/ja-migration-plan.md` §5, §8. **Opt-in `renga` is not removed; it is retained as an always-available fallback** (the revert safety net). Running broker is the default operational path.

> **Preconditions**:
> - Dispatcher / Worker panes are still alive from the previous
>   session. Do not spawn new ones (this is not /org-start).
> - The Curator is not resident (on-demand model). Null `curator_pane_id` /
>   `curator_peer_id`, and the curator not appearing in the pane list, are
>   the **normal state**.
> - The state DB (`.state/state.db`) is reused as-is. No need to re-record
>   pane identities.
> - If the handover file does not exist or is too stale, guide the user
>   to use /org-start or /org-resume instead.

## Step 0: confirm your own identity

1. Set the summary to "Secretary: front desk (resumed)" via
   `mcp__org-broker__set_summary`.
2. Check the focused pane's name/role with `mcp__org-broker__list_panes`:
   - Expected: `name == "secretary"` and `role == "secretary"`.
   - On mismatch, fix with
     `mcp__org-broker__set_pane_identity(target="focused", name="secretary", role="secretary")`.

## Step 1: load the handover file

1. Check that `.state/secretary-handover.md` exists:
   ```bash
   ls -la .state/secretary-handover.md 2>&1
   ```
   - Does not exist → guide the user and stop:
     "No handover file. Please run /org-start to bring the org up, or
     /org-resume to pick up from a suspended state."
2. Check freshness via the frontmatter `created_at`:
   - Within 24 hours → use as-is.
   - 24 hours to 7 days → warn the user ("the handover is stale, continue?").
   - More than 7 days → do not adopt; recommend switching to `/org-start`.
3. Read the file body. **Treat what is written as "fact" for next-session you**
   (Step 3 will reconcile with state.db).

## Step 2: re-fetch current state from state.db

```bash
python -c "
from tools.state_db import connect
from tools.state_db.queries import get_org_state_summary
import json
conn = connect('.state/state.db')
print(json.dumps(get_org_state_summary(conn), ensure_ascii=False, indent=2, default=str))
"
```

Verify:
- `session.status` matches the handover frontmatter.
- `dispatcher_pane_id` matches what the handover recorded.
- `curator_pane_id` / `curator_peer_id` are null (**null is normal**. If
  values remain, they may be stale values from the old scheme — report to
  the human).
- `active_runs[]` is consistent with the handover's "In-flight work" section.

## Step 3: confirm panes are alive

```
mcp__org-broker__list_peers
```

- The Dispatcher name should be visible.
- The curator is **normally not visible, and that is normal** (on-demand
  model). If it is visible, an on-demand curate is running; leave it alone
  (the dispatcher will close it).
- Workers listed in the handover should still exist (see below if missing).

**If anything diverges, report it to the human** (e.g., "the handover says
worker X is in progress, but the current pane list does not show it"). Do not
re-spawn on your own.

## Step 4: brief the human

Synthesize the handover and the current state.db view, and report concisely
in this shape:

```
The Secretary is resumed.

[Session]
- Objective: <session.objective>
- Status: <session.status>

[Panes]
- dispatcher (pane=N, peer=M)
- curator: not resident (launched on demand)
- workers: <task_id list>

[Recent agreements / decisions]
- ...

[Pending Decisions]
- ... ("none" if empty)

[Next action]
- ...

Please advise.
```

## Step 5: keep the handover file around

- Do not delete it (kept for reference in case of next-time trouble).
- `.state/secretary-handover.prev.md` is the previous one. Do not remove
  it even after loading the current one.

## Event record

```bash
py -3 tools/journal_append.py secretary_resumed \
    --json '{"handover_age_hours": <number>}' 2>/dev/null \
    || echo "(journal_append unavailable; skipping)"
```

## Things not to do

- Do not spawn a new Dispatcher / Curator (they are already alive).
- Do not send SUSPEND / SHUTDOWN to workers on your own.
- When the handover content disagrees with state.db, do not silently align
  one to the other — always report to the human and ask for a judgment.
