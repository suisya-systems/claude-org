---
name: dispatcher-resume
description: >
  Read the handover file written by /dispatcher-handover and bring the
  Dispatcher back in a fresh session. Use it on the very first turn after
  /clear. Atomically update `dispatcher_pane_id` / `dispatcher_peer_id` in
  state.db, and resume the `/loop 3m` worker monitoring loop.
  Use when the Secretary instructs "resume the Dispatcher" / "resume" /
  "pick up from the handover". This is not /org-start (the Worker /
  Secretary / Curator are assumed to still be alive).
effort: low
allowed-tools:
  - Read
  - Bash(py -3 ../tools/journal_append.py:*)
  - Bash(bash ../tools/journal_append.sh:*)
  - Bash(python3 -c:*)
  - Bash(py -3 -c:*)
  - Bash(ls:*)
  - Bash(mv:*)
  - mcp__renga-peers__set_summary
  - mcp__renga-peers__list_panes
  - mcp__renga-peers__set_pane_identity
  - mcp__renga-peers__list_peers
  - mcp__renga-peers__check_messages
  - mcp__renga-peers__send_message
---

> **Transport — both backends (default `broker` / opt-in `renga`)**: the peer-message and pane operations in this file are written as `mcp__org-broker__*`. With `ORG_TRANSPORT` unset, follow them as-is. With `ORG_TRANSPORT=renga` (opt-in), the fully qualified names are mechanically substituted `mcp__org-broker__*` → `mcp__renga-peers__*` (argument shape and semantics are identical). The transport-dependent differences are:
>
> - **Spawn ritual**: in addition to the default broker's mechanical approval of Claude Code's **folder-trust prompt** (via `--mcp-config <broker>` injection) with `send_keys(enter=true)`, for push-primary the channel sidecar is loaded with `--dangerously-load-development-channels server:org-broker-channel` and the dev-channel approval prompt is mechanically approved with `send_keys(enter=true)` (2-step approval). With `ORG_TRANSPORT=renga`, only the 1-step `--dangerously-load-development-channels server:renga-peers` "Load development channel?" Enter approval applies.
> - **Error branching**: in addition to the shared codes (`pane_not_found` / `last_pane` / `invalid-params`), the default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` (unknown codes escalate via the default branch). With `ORG_TRANSPORT=renga`, broker-specific codes never occur.
>
> `new_tab` / `focus_pane` are **not** in the broker surface (intentionally excluded). The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 + push-primary amendment (**broker push-primary is the default contract**, pull is retained as fallback). **The opt-in `renga` is not deleted and is maintained as a permanently-available revert safety net**. Broker actual-run (dogfood) is in scope for Epic #6 Issue G and is not the default operational route in this file (**Two-frame note (Refs #604)**: "default `broker`" here refers to the **code-default** (`tools/transport.py: DEFAULT_TRANSPORT`; the generated surface renders against this). The **operational-default** is `renga` because broker dogfood is not yet activated through Epic #6 Issue G; the two refer to different objects and do not contradict. Overview in root [`CLAUDE.md`](../../../CLAUDE.md).)

# dispatcher-resume: bring the Dispatcher back

Read `.state/dispatcher-handover.md` written by `/dispatcher-handover` and
restore the Dispatcher's minimum self-awareness (its standing as an org
member, in-flight dispatches, workers under monitoring), then resume the
`/loop 3m` worker monitoring loop.

> **Preconditions**:
> - The Worker / Secretary / Curator panes are still alive from the previous
>   session. Do not spawn new ones (this is not `/org-start`).
> - Your own pane (name=`dispatcher`) is alive too. You are right after the
>   Secretary issued `/clear` → `/dispatcher-resume` via `send_keys`. The
>   `pane_id` / `peer_id` should not have changed, but you must observe them
>   and **atomically update state.db**.
> - The state DB (`.state/state.db`) is used as-is.
> - The internal state files that bridge the monitoring gap
>   (`.state/dispatcher-event-cursor.txt` /
>   `.state/dispatcher/worker-idle-state.json` /
>   `.state/dispatcher/curate-inflight.json` (when present) /
>   `.state/pending_decisions.json`) survive from the previous session.
>   Do not re-create or re-initialize (continue from existing values).
> - If the handover file does not exist or is too old, point at `/org-start`
>   and stop.

## Before Step 0: residual loop reservation / stale re-fire guard (cut off duplicate startup early)

`/dispatcher-resume` is a **one-shot that consumes the handover exactly once**
(Step 7 renames `.state/dispatcher-handover.md` to `.consumed.md`). But if the
`/loop 3m` reservation started in Step 5 — due to a past bug or a manual
operation — holds `/dispatcher-resume` itself as its iteration target, this
skill re-fires on every monitoring cycle. Cut off such **stale re-fire /
duplicate startup** before entering Step 0 (background on the permanent fix:
[`knowledge/raw/2026-06-19-dispatcher-resume-loop-recursion.md`](../../../knowledge/raw/2026-06-19-dispatcher-resume-loop-recursion.md)).

1. Judge the live / consumed handover state on an **existence basis** (do not
   depend on a timestamp comparison against `now`. Aligns with the rule in
   `.dispatcher/CLAUDE.md` that the cold-start vs resume branch only looks at
   the live `.md`):
   ```bash
   python3 -c "
   import os
   md = '../.state/dispatcher-handover.md'
   cm = '../.state/dispatcher-handover.consumed.md'
   if os.path.exists(md):
       print('resume')            # canonical resume: live handover present
   elif os.path.exists(cm):
       print('already_consumed')  # already consumed: suspect residual loop / duplicate startup
   else:
       print('no_handover')       # no handover ever: real cold-start candidate
   "
   ```
2. **`already_consumed` (no live `.md`, `.consumed.md` present)**: a resume
   invocation with no live handover but `.consumed.md` still there. This is
   either "(i) re-fire / duplicate startup from a residual loop reservation
   left by a successful prior resume (org is healthy, monitoring loop is
   running)" or "(ii) an erroneous invocation in a situation that actually
   requires cold-start (org is down)". **Falling through to no-op based on
   existence alone permanently hides the cold-start guidance in (ii)**, so
   branch by observing whether the monitoring targets are actually live:
   - Use `mcp__renga-peers__list_panes` / `mcp__renga-peers__list_peers` to
     check **whether monitoring targets are live**: at least one active
     worker pane (`role == "worker"`) exists, or
     `.state/dispatcher/curate-inflight.json` exists (= a state in which the
     monitoring loop ought to be running).
   - **(i) monitoring targets are live = stale re-fire / duplicate startup**:
     the org is healthy and cold-start is not required. **Do not send**
     `DISPATCHER_RESUME_FAILED` (do not emit a spurious `/org-start`
     guidance), and exit early without proceeding past Step 1. **Do not
     leave the residual reservation dangling**: if there is a sign that the
     monitoring `/loop` is holding `/dispatcher-resume` as its iteration
     target, explicitly re-arm the loop with the Step 5 monitoring-only
     directive (the `/loop 3m ...` form that obeys INVARIANT(loop-prompt))
     to overwrite the reservation (no duplicate startup = converge to a
     single loop). If a monitoring directive is already running, this cycle
     is a **no-op heartbeat** (emit nothing). Either branch must not leave
     the reservation held by the skill itself. Record the fact of the
     re-fire to the journal:
     ```bash
     bash ../tools/journal_append.sh anomaly_observed \
         source=dispatcher_resume worker=dispatcher kind=stale_loop_refire confidence=n/a \
         note=handover_already_consumed
     ```
   - **(ii) no monitoring targets = erroneous invocation that actually needs
     cold-start**: not a stale re-fire. Do not fall over to no-op; **fall
     through to Step 1's "no handover file" branch and emit
     `DISPATCHER_RESUME_FAILED` → cold-start guidance** (do not hide the
     cold-start guidance).
3. **`resume` (live `.md` present)**: proceed to Step 0 as usual.
4. **`no_handover` (neither live `.md` nor `.consumed.md`)**: proceed to
   Step 0 → Step 1 as usual, and fall through to Step 1's "no handover file"
   branch, dropping into `DISPATCHER_RESUME_FAILED` → cold-start guidance.

## Step 0: confirm your identity

1. Use `mcp__renga-peers__set_summary` to set "Dispatcher: monitoring (resumed)".
2. Use `mcp__renga-peers__list_panes` to check the focused pane's name/role:
   - Expected: `name == "dispatcher"` and `role == "dispatcher"`
   - If mismatched, repair with
     `mcp__renga-peers__set_pane_identity(target="focused", name="dispatcher", role="dispatcher")`
3. Get your own `pane_id` from `list_panes` (the id where `focused: true`).
4. Get the `peer_id` for `name == "dispatcher"` from
   `mcp__renga-peers__list_peers`.

## Step 1: read the handover file

The Dispatcher's cwd is `.dispatcher/`, so resolve repo-root paths one
level up.

1. Check that `.state/dispatcher-handover.md` exists:
   ```bash
   ls -la ../.state/dispatcher-handover.md 2>&1
   ```
   - Missing → notify the Secretary and stop:
     ```
     DISPATCHER_RESUME_FAILED: handover file not found.
     Cold-start the Dispatcher with /org-start.
     ```
2. Look at frontmatter `created_at` to judge freshness:
   - Within 24h → adopt as-is
   - 24h < … ≤ 7d → warn the Secretary ("handover is stale; continuing anyway")
   - More than 7d → do not adopt; recommend switching to `/org-start` and stop
3. Read the body via Read. Treat its contents as "fact" for your next-session
   self (Step 3 reconciles against state.db).

## Step 2: atomically update Dispatcher identity in state.db

Write the `pane_id` / `peer_id` observed in Step 0 through
`StateWriter.transaction()` **in a single transaction** (the post-commit
hook will regenerate `.state/org-state.md`). This is the substance of the
acceptance requirement that "state.db identity is updated atomically".

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.path.abspath('..'))
from pathlib import Path
from tools.state_db import connect
from tools.state_db.writer import StateWriter
conn = connect('../.state/state.db')
with StateWriter(conn, claude_org_root=Path('..')).transaction() as w:
    w.update_session(
        dispatcher_pane_id='<observed_pane_id>',
        dispatcher_peer_id='<observed_peer_id>',
    )
"
```

- Write `dispatcher_pane_id` / `dispatcher_peer_id` as **strings** (the
  schema is TEXT and existing `/org-start` writes strings; keep types aligned)
- Inside `transaction()`, even if one half fails the DB will not be left in
  a half-written state
- If the observed values differ from the handover frontmatter, treat the
  current observation (`list_panes` / `list_peers`) as ground truth and
  prefer it. Include the diff in the message you send to the Secretary.

## Step 3: re-fetch the current state from state.db and reconcile with the handover

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.path.abspath('..'))
from tools.state_db import connect
from tools.state_db.queries import get_org_state_summary
import json
conn = connect('../.state/state.db')
print(json.dumps(get_org_state_summary(conn), ensure_ascii=False, indent=2, default=str))
"
```

Items to check:
- Whether `active_runs[]` lines up with the handover's "Workers under monitoring" section
- Whether the worker directories in `active_worker_dirs[]` exist

If a worker is `active` in state.db but not in the handover, or is in the
handover but missing from state.db / `list_panes`, **report to the
Secretary** for a decision (do not respawn or change status on your own).

## Step 4: pane liveness check

Call `mcp__renga-peers__list_peers` again and confirm that the worker
names recorded in the handover still exist. If any are gone, notify the
Secretary with `WORKER_PANE_EXITED: worker-{task_id} (missing at resume
time)`. Reconciliation is the Secretary's responsibility.

## Step 5: resume the monitoring loop

Evaluate the following **in this order**:

1. **Inflight regeneration (do this first)**: if Step 4's `list_peers` /
   `list_panes` shows a live pane with `name == "curator"` but
   `.state/dispatcher/curate-inflight.json` is absent (e.g., the previous
   session was cut off right after spawn, before the inflight write), do
   not leave the curator untracked: **regenerate** the inflight record with
   `started_at = now` / `reasons: []` / `extended: false` /
   `last_inspect_hash: null` / `last_inspect_ts: null`. All subsequent
   judgments use this post-regeneration state (= this case always satisfies
   the resume condition in 2).
2. **`/loop 3m` resume condition**: if the handover's
   `active_worker_count > 0`, the active worker dirs in state.db are
   non-empty, **or `curate-inflight.json` exists** (including one
   regenerated in 1; completion monitoring of an on-demand curate is part
   of the handover — `.dispatcher/references/worker-monitoring.md`
   Step 5.3), resume worker monitoring with `/loop 3m` by passing the
   monitoring-only directive below (**do not omit the prompt**):

<!--
INVARIANT(loop-prompt): Do not pass this skill itself (`/dispatcher-resume`)
or any other slash command as the prompt argument to `/loop`. Starting
`/loop` with the prompt omitted from within the skill's execution turn lets
the active slash command be captured as the iteration target, causing this
skill to self-recurse every 3 minutes (the 2026-06-19 incident; details in
knowledge/raw/2026-06-19-dispatcher-resume-loop-recursion.md). Always pass
the monitoring-only natural-language directive explicitly.
tests/test_dispatcher_resume_loop_invariant.py pins this invariant.
-->

```
/loop 3m Run exactly one cycle of "monitoring loop 1 cycle" from references/worker-monitoring.md (relative to the Dispatcher cwd .dispatcher/) — poll_events → check_messages → list_panes → inspect_pane → stall / relay-gap / pane_output evaluation. Only notify the Secretary on cycles where anomaly / stall / relay-gap / pane_exited is detected; if nothing is detected, emit nothing (do not write a per-cycle status summary or any natural-language status description). Keep cadence at 3 minutes or longer; do not shorten. Do not include slash commands or this skill itself as iteration targets.
```

- On the first cycle of the monitoring loop, `mcp__renga-peers__poll_events`
  resumes from the previous cursor (the moment the previous session ended)
  in `.state/dispatcher-event-cursor.txt`. This preserves the semantics that
  "any `pane_exited` that arrived while the pane was closed is still
  guaranteed to be picked up at the next poll" (renga 0.5.7+ cursor spec).
- On the first cycle, `mcp__renga-peers__check_messages` drains any
  worker → dispatcher peer messages queued during the previous session.
- `.state/dispatcher/worker-idle-state.json` retains the previous session's
  `idle_streak_cycles`, so stall-detection continuity is preserved as well.

Only if there is nothing to monitor (active worker dirs is 0,
`active_runs` is 0, no `curate-inflight.json`, and — since this comes
after evaluating 1 — no curator pane in `list_panes` either), do not start
`/loop`; notify the Secretary that you are idle and wait:

```
DISPATCHER_RESUMED_IDLE: resume complete with no monitoring targets. Awaiting DELEGATE.
```

## Step 6: brief the Secretary

Combine the handover + current state.db and report concisely to the
Secretary:

```
DISPATCHER_RESUMED: Dispatcher resume complete.
- pane=<observed_pane_id> / peer=<observed_peer_id> (state.db updated)
- workers under monitoring: <task_id list>
- pending decisions: <count>
- diff vs. handover: <one line if any, else "none">
- monitoring loop: /loop 3m resumed (or idle)
```

## Step 7: switch the handover file to consumed state

Once resume succeeds, **rename** `.state/dispatcher-handover.md` to
`.state/dispatcher-handover.consumed.md`. This:

- Prevents the auto-branch in `.dispatcher/CLAUDE.md` at startup
  (resume if a handover file is present within the last 7 days) from
  mistakenly branching to resume on the next `/org-start` cold-start after
  the resume has been consumed once
- Keeps the most recent one for reference in `.consumed.md` form (when the
  next `/dispatcher-handover` writes a new `.md`, the prior one is rotated
  to `.prev.md` backup or overwritten)

```bash
mv ../.state/dispatcher-handover.md ../.state/dispatcher-handover.consumed.md
```

- If `.consumed.md` already exists, overwrite is fine (keep only the most
  recent one)
- `.state/dispatcher-handover.prev.md` is the backup written by the previous
  `/dispatcher-handover`. Even if it has been read, do not delete it.

## Event recording

The Dispatcher cwd is `.dispatcher/`, so call one level up:

```bash
bash ../tools/journal_append.sh dispatcher_resumed \
    pane_id=<observed_pane_id> peer_id=<observed_peer_id> \
    active_workers=<count> note=resumed_from_handover
```

## What you must not do

- Spawn a new Dispatcher / Curator (they are already alive)
- Send SUSPEND / SHUTDOWN to Workers on your own
- Initialize / delete `.state/dispatcher-event-cursor.txt` /
  `worker-idle-state.json` / `curate-inflight.json` /
  `pending_decisions.json` (monitoring continuity from the previous
  session breaks)
- When the handover content disagrees with the current state.db, take it
  upon yourself to favor one side (always report to the Secretary for a
  decision)
- Split the atomic update across multiple writes (it must always complete
  within a single `StateWriter.transaction()` block)
- Start Step 5's `/loop 3m` with the prompt omitted, or pass
  `/dispatcher-resume` (this skill itself) or any other slash command as
  `/loop`'s iteration target (the skill will self-recurse every 3 minutes;
  always pass the monitoring-only directive explicitly. See Step 5's
  INVARIANT(loop-prompt))
