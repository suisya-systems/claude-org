---
name: dispatcher-handover
description: >
  To avoid continuing the Dispatcher session while its context stays bloated,
  write the monitoring state (active workers / latest polling cursor /
  pending escalations) to a handover file, then — on the Secretary's
  instruction — prepare a fresh Dispatcher session via /clear →
  /dispatcher-resume.
  Use when a DISPATCHER_HANDOVER peer message arrives from the Secretary,
  or when the Dispatcher itself judges that context has grown long.
effort: low
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash(py -3 ../tools/journal_append.py:*)
  - Bash(bash ../tools/journal_append.sh:*)
  - Bash(python3 -c:*)
  - Bash(py -3 -c:*)
  - Bash(ls:*)
  - Bash(cp:*)
  - mcp__renga-peers__send_message
---

# dispatcher-handover: hand off the Dispatcher

Without dragging the Dispatcher session on, produce a handover file that
carries the current monitoring state and the Dispatcher's standing as an
org member into the next session. After writing, notify the Secretary
to "once you ack, send_keys `/clear` → `/dispatcher-resume`".

> **Transport — both backends (default `broker` / opt-in `renga`)**: the peer-message and pane operations in this file (and across the skills) are written as `mcp__org-broker__*`. With **`ORG_TRANSPORT` unset = default `broker`**, follow them as-is. With `ORG_TRANSPORT=renga` (opt-in, revertible), the MCP server name becomes `renga-peers`, and the **fully qualified names are mechanically substituted `mcp__org-broker__*` → `mcp__renga-peers__*`** (argument shape and semantics are identical, so the operational logic does not change). The three transport-dependent differences are:
>
> - **Receive model (default = push-primary = `claude/channel` / pull fallback)**: the default broker is designed as **push-primary** (runtime push-first 0.1.24+; design SoT is transport-lab `docs/design/broker-native-roles.md` §9). A **channel sidecar** (`server:org-broker-channel`) co-located with each pane claims the broker queue at ~1s intervals and pushes via `notifications/claude/channel`, injecting the body into an idle session (creating the "respond as soon as it arrives" trigger). Worker ack (`to_id="worker-{task_id}"`), retro-gate ack (`to_id="dispatcher"`), and the dispatcher handover route's `send_message` / `check_messages` / `send_keys` / `inspect_pane` all work under the same tool names (`mcp__org-broker__*`). **Pull is the fallback layer**: when the sidecar is absent or unhealthy (heartbeat timeout flips to `delivery_mode=PULL`), for channel-incapable panes (codex pull-peer), or when claude.ai login is missing, each role actively `check_messages` on its own cadence (per-role cadence: worker = turn boundary / bounded `/loop` after completion; dispatcher = `/loop 3m`; secretary = at turn start; the existing "when you see a nudge, `check_messages`" prose is **not retracted** and should be read as this fallback cadence). With `ORG_TRANSPORT=renga` (opt-in), worker reports and dispatcher responses are pushed in-band as `<channel source="renga-peers" …>` (renga's in-band push and broker push-primary share the same immediate-response trigger). Contract-wise, push-primary is **ratified** on Surface 8 + push-primary amendment (2026-06-15, S3; pull is retained as fallback; renga is unchanged).
> - **Spawn ritual (default = folder-trust approval + dev-channel sidecar approval, 2 steps)**: when spawning a child pane, the default broker injects `--mcp-config <broker>` and mechanically approves Claude Code's **folder-trust prompt** with `send_keys(enter=true)`, **and in addition**, loads the channel sidecar via `--dangerously-load-development-channels server:org-broker-channel` for push-primary and mechanically approves the dev-channel approval prompt (spawn-flow 3-3b) with `send_keys(enter=true)` (folder-trust + dev-channel = 2-step approval; details in [`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md) 3-2 / 3-3b, design in broker-native-roles.md §9.5). With `ORG_TRANSPORT=renga` (opt-in), it injects `--dangerously-load-development-channels server:renga-peers` and approves the "Load development channel?" prompt with Enter — 1 step. **Note: the attention watcher is a transport-independent CLI pane and is exempt from both the folder-trust and dev-channel 2-step approvals** (do not pull it into the spawn-ritual inversion).
> - **Error branching (default = broker extended codes included)**: in addition to the shared codes (`pane_not_found` / `last_pane` / `invalid-params`, Surface 6), the default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` / `[unknown_tool]` (unknown codes escalate via the default branch). With `ORG_TRANSPORT=renga`, broker-specific codes never occur — only shared codes + renga-specific codes.
>
> The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14) + the tail "Ratified amendment (2026-06-15): push-primary delivery" (S3; **broker push-primary is the default contract**, pull is retained as structural fallback). Design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary) / `docs/design/ja-migration-plan.md` §5 and §8. **The opt-in `renga` is not deleted and is maintained as a permanently-available fallback** (the revert safety net). Broker actual-run (dogfood) is in scope for Epic #6 Issue G and is **not** the default operational route in this file (**Two-frame note on "default" (Refs #604)**: "default `broker`" here refers to the **code-default** frame — `tools/transport.py: DEFAULT_TRANSPORT` has been flipped to `broker` in runtime 0.1.28 (Epic #586), and the ja generator / `transport.resolve()` render against this code frame, so the generated surface displays it this way. There is a separate **operational-default** frame in which the operational default route is `renga`, because broker actual-run dogfood is not yet activated through Epic #6 Issue G. The two frames refer to different objects (code constant vs. operational route) and do not contradict each other. The overview is in root [`CLAUDE.md`](../../../CLAUDE.md), section "Transport — both backends".)

> **Key preconditions**:
> - This skill is run by the **Dispatcher itself** (cwd `.dispatcher/`).
>   It is not invoked directly from the Secretary.
> - Keep the Worker / Secretary / Curator panes alive. `/clear` only resets
>   the Dispatcher Claude's context, so as long as state.db and the handover
>   file allow recovery, monitoring stays uninterrupted.
> - Keep the Dispatcher pane (name=`dispatcher`) alive too. Closing the pane
>   itself changes `pane_id` / `peer_id` and forces the `/loop 3m` hook to
>   be re-registered. The Secretary takes the canonical path of merely
>   sending `/clear` and `/dispatcher-resume` keystrokes via
>   `mcp__renga-peers__send_keys(target="dispatcher", ...)` so that the pane
>   is preserved.
> - The state DB (`.state/state.db`) is the single SoT. Pane / peer identity
>   is written into the handover as a reference value, but on resume the
>   ground truth is the live observation from `list_panes` / `list_peers`.
> - To avoid creating a gap in the monitoring loop, the following files must
>   **never be deleted or edited**:
>   - `.state/dispatcher-event-cursor.txt` (next cycle's `poll_events` cursor)
>   - `.state/dispatcher/worker-idle-state.json` (idle streak for stall detection)
>   - `.state/dispatcher/curate-inflight.json` (start record of an on-demand curate; only if present)
>   - `.state/pending_decisions.json` (pending-decisions register)
>   - `.state/workers/worker-*.md` (per-worker run state)
>   The handover file is restricted to the **additional** context above
>   (no human-conversation temperature, but in-flight dispatch context and
>   recent anomaly observations).

## Step 1: collect what to hand over

Before writing, extract the following from the Dispatcher's (your) context:

1. **Recent dispatch context**
   - DELEGATE received → spawn success/failure, and task IDs that have moved
     onto the escalation path
2. **Workers under monitoring**
   - Pane names whose `Status` in `.state/workers/worker-*.md` is `active`,
     plus the latest Progress Log excerpt
3. **Recent anomaly observations summary**
   - Out of the past cycle's `journal_append`'d `anomaly_observed` /
     `notify_sent`, the ones still unresolved
4. **Undelivered / failed sends**
   - Things escalated to the Secretary as `[pane_not_found]` /
     `[split_refused]` etc., or awaiting retry
5. **Next actions (Dispatcher's view)**
   - Workers to re-confirm next cycle, judgments waiting to be relayed

## Step 2: pull structured info from state.db

Embed it in the handover as reference. Write to a sandbox-writable
`$TMPDIR` (falling back to `/tmp` if unset):

```bash
python3 -c "
from tools.state_db import connect
from tools.state_db.queries import get_org_state_summary
import json, os
conn = connect('.state/state.db')
out_path = os.path.join(os.environ.get('TMPDIR', '/tmp'), 'dispatcher-handover-state.json')
with open(out_path, 'w') as f:
    json.dump(get_org_state_summary(conn), f, ensure_ascii=False, indent=2, default=str)
print(out_path)
"
```

From this, extract:
- `session.dispatcher_pane_id` / `session.dispatcher_peer_id` (current identity)
- `active_runs[]` (in-flight tasks)
- `active_worker_dirs[]` (live worker directories)
- The most recent `recent_events` — top ~5 of `worker_spawned` /
  `worker_reported` / `worker_escalation`

The Dispatcher's cwd is `.dispatcher/`, so resolve relative paths one
level up:

```bash
# When run from .dispatcher/
python3 -c "
import sys, os
sys.path.insert(0, os.path.abspath('..'))
from tools.state_db import connect
from tools.state_db.queries import get_org_state_summary
import json
conn = connect('../.state/state.db')
out_path = os.path.join(os.environ.get('TMPDIR', '/tmp'), 'dispatcher-handover-state.json')
with open(out_path, 'w') as f:
    json.dump(get_org_state_summary(conn), f, ensure_ascii=False, indent=2, default=str)
print(out_path)
"
```

## Step 3: write the handover file

Destination: `.state/dispatcher-handover.md` (rooted at the repo root;
from the Dispatcher cwd `.dispatcher/`, that is
`../.state/dispatcher-handover.md`).

If a previous file exists, back it up to `.prev.md` before overwriting:

```bash
[ -f ../.state/dispatcher-handover.md ] && \
  cp ../.state/dispatcher-handover.md ../.state/dispatcher-handover.prev.md
```

Format (YAML frontmatter + markdown):

```markdown
---
created_at: <UTC ISO8601>
dispatcher_pane: <pane_id> / peer=<peer_id>
active_worker_count: <int>
event_cursor_present: <true | false>
idle_state_present: <true | false>
pending_decisions_count: <int>
---

# Dispatcher Handover

## Workers under monitoring
- worker-<task_id> (<worker_dir>): Status=<active|...>, one-line Progress Log excerpt
- ...

## Recent anomaly / notify_sent summary
- worker-<task_id>: kind=<approval_blocked|stall_suspected|relay_gap_suspected> ...
(If none, write "none" explicitly.)

## Undelivered / failed sends
- ...
(If none, write "none".)

## Next actions (Dispatcher's view)
- Re-confirm next cycle: worker-<task_id> due to <reason>
- ...

## Files to bridge the monitoring gap (read-only; this skill must not touch)
- `.state/dispatcher-event-cursor.txt`: next `poll_events` cursor (use as-is on resume)
- `.state/dispatcher/worker-idle-state.json`: idle streak for stall detection
- `.state/dispatcher/curate-inflight.json`: start record of an on-demand curate (only if present; after resume, Step 5.3 timeout management continues from its `started_at`)
- `.state/pending_decisions.json`: pending-decisions register
- `.state/workers/worker-*.md`: per-worker run state

## Reference: state.db snapshot
(Briefly transcribe session / active_runs / recent_events captured in Step 2.)
```

**Writing notes**:
- Write as "a memo to your next self", not as "past logs".
- Never write secrets / tokens / passwords.
- Assume the Secretary / human may also read this file.

## Step 4: record the event

The Dispatcher cwd is `.dispatcher/`, so call one level up:

```bash
bash ../tools/journal_append.sh dispatcher_handover \
    active_workers=<int> pending_decisions=<int> \
    note=context_compaction
```

## Step 5: notify the Secretary

Via `mcp__renga-peers__send_message(to_id="secretary", message=...)`,
convey the following:

```
DISPATCHER_HANDOVER_READY: written to ../.state/dispatcher-handover.md.
Once you ack, please use mcp__renga-peers__send_keys(target="dispatcher")
to issue /clear and then /dispatcher-resume in order.
Do not close the pane (preserving pane_id keeps the monitoring gap minimal).
active workers: <count>, pending decisions: <count>.
```

The Secretary receives this message and — without escalating to the
human (a routine handover is not a decision request) — uses `send_keys`
to issue `/clear` and `/dispatcher-resume`. Once the Secretary's ack
returns, this skill is complete; do nothing further (the assumption is
that `/clear` will reset your context).

**What the Dispatcher must NOT do**:
- Issue `/clear` itself (it is the recipient of an external `send_keys`)
- Send SHUTDOWN to Workers or the Curator (keep panes alive)
- Edit / delete `.state/dispatcher-event-cursor.txt` /
  `worker-idle-state.json` / `curate-inflight.json` / `pending_decisions.json`
  (resume continuity breaks)
- Stop `/loop 3m` itself (the design resumes it after resume; the current
  cycle continues)
