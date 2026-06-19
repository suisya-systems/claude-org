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
  - mcp__renga-peers__set_summary
  - mcp__renga-peers__list_panes
  - mcp__renga-peers__set_pane_identity
  - mcp__renga-peers__list_peers
  - mcp__renga-peers__check_messages
---

# secretary-resume: bring the Secretary back

Load `.state/secretary-handover.md` (written by `/secretary-handover`) and
restore the minimum Secretary awareness — your stance as an org member,
recent exchanges with the human, and in-flight work.

> **Transport — both backends (default `broker` / opt-in `renga`)**: the peer-message and pane operations in this file are written as `mcp__org-broker__*`. With `ORG_TRANSPORT` unset, follow them as-is. With `ORG_TRANSPORT=renga` (opt-in), the fully qualified names are mechanically substituted `mcp__org-broker__*` → `mcp__renga-peers__*` (argument shape and semantics are identical). The transport-dependent differences are:
>
> - **Spawn ritual**: in addition to the default broker's mechanical approval of Claude Code's **folder-trust prompt** (via `--mcp-config <broker>` injection) with `send_keys(enter=true)`, for push-primary the channel sidecar is loaded with `--dangerously-load-development-channels server:org-broker-channel` and the dev-channel approval prompt is mechanically approved with `send_keys(enter=true)` (2-step approval). With `ORG_TRANSPORT=renga`, only the 1-step `--dangerously-load-development-channels server:renga-peers` "Load development channel?" Enter approval applies.
> - **Error branching**: in addition to the shared codes (`pane_not_found` / `last_pane` / `invalid-params`), the default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` (unknown codes escalate via the default branch). With `ORG_TRANSPORT=renga`, broker-specific codes never occur.
>
> `new_tab` / `focus_pane` are **not** in the broker surface (intentionally excluded). The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 + push-primary amendment (**broker push-primary is the default contract**, pull is retained as fallback). **The opt-in `renga` is not deleted and is maintained as a permanently-available revert safety net**. Broker actual-run (dogfood) is in scope for Epic #6 Issue G and is not the default operational route in this file (**Two-frame note (Refs #604)**: "default `broker`" here refers to the **code-default** (`tools/transport.py: DEFAULT_TRANSPORT`; the generated surface renders against this). The **operational-default** is `renga` because broker dogfood is not yet activated through Epic #6 Issue G; the two refer to different objects and do not contradict. Overview in root [`CLAUDE.md`](../../../CLAUDE.md).)

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

> **Transport layer (transport) both systems — default `renga` / opt-in `broker`**: this skill's `mcp__renga-peers__*` calls are written for **default `renga`** (`ORG_TRANSPORT` unset) and can be followed as-is (default behavior unchanged). Under `ORG_TRANSPORT=broker` (opt-in, revertible) the MCP server name becomes `org-broker`, and tools' **fully qualified names get machine-substituted from `mcp__renga-peers__*` → `mcp__org-broker__*`** (argument shape and semantics are identical). Only the transport-dependent points are noted in broker form:
>
> - **Receive model (push → pull)**: under renga, worker / dispatcher peer messages are pushed in-band. Under broker only a pane-local nudge fires, and the body must be pulled via `check_messages` (broker: `mcp__org-broker__check_messages`) (when the Lead receives messages after resume, it just changes to "see the nudge → `check_messages`").
> - **Spawn rite (dev-channel approval → folder-trust approval)**: resume does not spawn, so approvals are unused; but on broker, the spawn-time approval (on the org-start / org-delegate side) shifts from dev-channel to the Claude Code **folder-trust prompt**.
> - **Error branching (broker additional codes)**: on top of renga codes, broker may return `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` (unknown codes hit the default branch). See the broker section in [`.claude/skills/org-delegate/references/renga-error-codes.md`](../org-delegate/references/renga-error-codes.md).
>
> `new_tab` / `focus_pane` are **absent** from the broker surface (intentional exclusion). The canonical contract is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (proposed, awaiting ratification); the design SoT is transport-lab `docs/design/ja-migration-plan.md` §5.2(ii). Broker real-run (dogfood) is scoped to Epic #6 Issue G and is not this skill's default path.

## Step 0: confirm your own identity

1. Set the summary to "Secretary: front desk (resumed)" via
   `mcp__renga-peers__set_summary`.
2. Check the focused pane's name/role with `mcp__renga-peers__list_panes`:
   - Expected: `name == "secretary"` and `role == "secretary"`.
   - On mismatch, fix with
     `mcp__renga-peers__set_pane_identity(target="focused", name="secretary", role="secretary")`.

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
mcp__renga-peers__list_peers
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
