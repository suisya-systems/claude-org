---
name: org-suspend
description: >
  Suspend the org and persist all state to disk. Use when the user says
  "suspend", "save and exit", "I want to close", "let's stop for now",
  "done for today".
effort: low
allowed-tools:
  - Read
  - Bash(bash tools/journal_append.sh:*)
  - Bash(py -3 tools/journal_append.py:*)
  - Bash(python -m tools.state_db.importer:*)
  - mcp__org-broker__*
---

# org-suspend: suspend the org

Collect every worker's state, persist it to disk, and stop every pane.

> **Transport — both backends (default `broker` / opt-in `renga`)**: the peer-message and pane operations in this file are written as `mcp__org-broker__*`. With `ORG_TRANSPORT` unset, follow them as-is. With `ORG_TRANSPORT=renga` (opt-in), the fully qualified names are mechanically substituted `mcp__org-broker__*` → `mcp__renga-peers__*` (argument shape and semantics are identical). The transport-dependent differences are:
>
> - **Spawn ritual**: in addition to the default broker's mechanical approval of Claude Code's **folder-trust prompt** (via `--mcp-config <broker>` injection) with `send_keys(enter=true)`, for push-primary the channel sidecar is loaded with `--dangerously-load-development-channels server:org-broker-channel` and the dev-channel approval prompt is mechanically approved with `send_keys(enter=true)` (2-step approval). With `ORG_TRANSPORT=renga`, only the 1-step `--dangerously-load-development-channels server:renga-peers` "Load development channel?" Enter approval applies.
> - **Error branching**: in addition to the shared codes (`pane_not_found` / `last_pane` / `invalid-params`), the default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` (unknown codes escalate via the default branch). With `ORG_TRANSPORT=renga`, broker-specific codes never occur.
>
> `new_tab` / `focus_pane` are **not** in the broker surface (intentionally excluded). The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 + push-primary amendment (**broker push-primary is the default contract**, pull is retained as fallback). **The opt-in `renga` is not deleted and is maintained as a permanently-available revert safety net**. Broker actual-run (dogfood) is in scope for Epic #6 Issue G and is not the default operational route in this file (**Two-frame note (Refs #604)**: "default `broker`" here refers to the **code-default** (`tools/transport.py: DEFAULT_TRANSPORT`; the generated surface renders against this). The **operational-default** is `renga` because broker dogfood is not yet activated through Epic #6 Issue G; the two refer to different objects and do not contradict. Overview in root [`CLAUDE.md`](../../../CLAUDE.md).)

> **Curator absence is the normal state (on-demand model)**: the curator is not resident.
> Null `curator_pane_id` / `curator_peer_id` in state.db is normal, and the curator not
> appearing in `list_panes` / `list_peers` is not an anomaly. A curator pane exists only in
> the transient case where "an on-demand curate triggered by a worker close was still running
> when suspend overlapped it"; only then is it included in Phase 4's shutdown targets.

Pane operations go through the `mcp__org-broker__*` MCP tools. Lifecycle events equivalent to pane_exited are long-polled via `mcp__org-broker__poll_events`; screen scraping via `mcp__org-broker__inspect_pane`; raw key input via `mcp__org-broker__send_keys`.

> **Transport (dual-rail) - default `broker` / opt-in `renga`**: This file (and each skill) writes its peer-message / pane operations as `mcp__org-broker__*`, so with **`ORG_TRANSPORT` unset = default `broker`** you can follow the prose as-is. Under `ORG_TRANSPORT=renga` (opt-in, revertible) the MCP server name becomes `renga-peers`, and the **fully-qualified names mechanically rewrite from `mcp__org-broker__*` to `mcp__renga-peers__*`** (the argument shape and semantics are identical, so the operation logic does not change). Only the following three points differ between the rails:
>
> - **Receive model (default = push-primary = `claude/channel` / pull fallback)**: Default broker is designed as **push-primary** (runtime push-first 0.1.24+, design SoT in transport-lab `docs/design/broker-native-roles.md` §9): each pane's co-resident **channel sidecar** (`server:org-broker-channel`) claims the broker queue at ~1s intervals and pushes by injecting bodies into idle sessions via `notifications/claude/channel` (a "receive then immediately respond" moment arises). Worker acks (`to_id="worker-{task_id}"`), retro-gate acks (`to_id="dispatcher"`), and the dispatcher-handover path all use the same tool names (`mcp__org-broker__*`) for `send_message` / `check_messages` / `send_keys` / `inspect_pane`. **Pull is the fallback layer**: when the sidecar is absent / unhealthy (heartbeat timeout flips `delivery_mode=PULL`) / on channel-unsupported panes (codex pull-peer) / when claude.ai login is missing, each role actively `check_messages` at its own cadence (per-role cadence: worker = turn boundary / bounded `/loop` after completion; dispatcher = `/loop 3m`; secretary = top-of-turn). The existing "if a nudge arrives, then `check_messages`" prose is **not retracted** and should be read as this fallback cadence. Under `ORG_TRANSPORT=renga` (opt-in), worker reports and dispatcher responses are pushed in-band as `<channel source="renga-peers" ...>` (renga's in-band push and broker push-primary share the same immediate-response moment). On contract surface, push-primary is **ratified** under Surface 8 + push-primary amendment (2026-06-15, S3; pull retained as fallback; renga unchanged).
> - **Spawn ritual (default = folder-trust approval + dev-channel sidecar approval, two-step)**: When spawning child panes, default broker injects `--mcp-config <broker>` and machine-approves Claude Code's **folder-trust prompt** via `send_keys(enter=true)`, **and in addition** loads the channel sidecar via `--dangerously-load-development-channels server:org-broker-channel` for push-primary and machine-approves the dev-channel approval prompt (spawn-flow 3-3b) via `send_keys(enter=true)` (the two-step approval = folder-trust + dev-channel; see [`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md) 3-2 / 3-3b; design in broker-native-roles.md §9.5). Under `ORG_TRANSPORT=renga` (opt-in), it injects `--dangerously-load-development-channels server:renga-peers` and Enter-approves "Load development channel?" - a single step. **Note: the attention watcher is a transport-neutral CLI pane and is exempt from both folder-trust and dev-channel two-step approval** (do not drag it into the spawn-ritual flip).
> - **Error branches (default = broker extended codes included)**: Default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` / `[unknown_tool]` in addition to shared codes (`pane_not_found` / `last_pane` / `invalid-params`, Surface 6) (unknown codes are escalated via the default branch). Under `ORG_TRANSPORT=renga`, the broker-specific codes do not occur; only shared codes + renga-specific codes apply.
>
> The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14) + the trailing "Ratified amendment (2026-06-15): push-primary delivery" (S3; **broker push-primary is the contract default**, pull retained as structural fallback). Design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary) / `docs/design/ja-migration-plan.md` §5, §8. **Opt-in `renga` is not removed; it is retained as an always-available fallback** (the revert safety net). Running broker is the default operational path.

> **Transport layer (transport) both systems — default `renga` / opt-in `broker`**: this skill's `mcp__renga-peers__*` calls are written for **default `renga`** (`ORG_TRANSPORT` unset) and can be followed as-is (default behavior unchanged). Under `ORG_TRANSPORT=broker` (opt-in, revertible) the MCP server name becomes `org-broker`, and tools' **fully qualified names get machine-substituted from `mcp__renga-peers__*` → `mcp__org-broker__*`** (argument shape and semantics are identical). Only the transport-dependent points are noted in broker form:
>
> - **Receive model (push-primary = `claude/channel` / pull fallback)**: under renga, worker responses to SUSPEND/SHUTDOWN are pushed in-band. Broker has been **redesigned to push-primary** (runtime push-first 0.1.24+, transport-lab `docs/design/broker-native-roles.md` §9): the per-pane channel sidecar (`server:org-broker-channel`) injects worker responses into the idle session via `notifications/claude/channel`. **Pull is the fallback layer**: when the sidecar is absent / unhealthy, the Phase 1 response wait actively polls via `check_messages` (broker: `mcp__org-broker__check_messages`) (a nudge can be a trigger, but it does not wake an idle session, so an active poll is the canonical path — §9.6). `poll_events` (lifecycle) / `close_pane` / `list_panes` also follow the same logic under broker but the tool name becomes `mcp__org-broker__*`.
> - **Spawn rite (folder-trust approval + dev-channel sidecar approval re-introduced)**: suspend is the pane-closing side, so spawn approvals are unused; but on broker, the spawn-time flow (on the org-start / org-delegate side) machine-approves the `--mcp-config <broker>` **folder-trust prompt** **in addition to** the channel sidecar's `--dangerously-load-development-channels server:org-broker-channel` dev-channel approval (the re-introduced spawn-flow 3-3b) for push-primary (additive over ratified §5/§8.5; design broker-native-roles.md §9.5).
> - **Error branching (broker additional codes)**: on top of renga codes (`[pane_not_found]` / `[pane_vanished]` / `[last_pane]` etc.), broker may return `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` (unknown codes hit the default branch). See the broker section in [`.claude/skills/org-delegate/references/renga-error-codes.md`](../org-delegate/references/renga-error-codes.md).
>
> `new_tab` / `focus_pane` are **absent** from the broker surface (intentional exclusion). The canonical contract is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (ratified 2026-06-14; the push-primary additive amendment S3 is ratified 2026-06-15, with existing ratified text unchanged); the design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary redesign) / `docs/design/ja-migration-plan.md` §5.2(ii). Broker real-run (dogfood) is scoped to Epic #6 Issue G and is not this skill's default path.

## Phase 1: collect worker state

1. List the active peers with `mcp__org-broker__list_peers`.
2. Send the following to every peer except yourself and the Curator via `mcp__org-broker__send_message`:
   ```
   SUSPEND: report your current state.
   1. What you have completed so far.
   2. Files you changed (committed / uncommitted).
   3. What you were about to do next.
   4. Blockers or unresolved issues.
   ```
3. Wait up to 30 seconds for responses, polling `mcp__org-broker__check_messages` every 5 seconds.
4. Record the responses from the workers that replied.

## Phase 2: scrape unresponsive workers

For workers that did not reply:

1. Read the worker's state file under `.state/workers/` to get the Pane Name and Directory.
2. Read the latest console output via screen scrape:
   ```
   mcp__org-broker__inspect_pane(target="worker-{task_id}", format="text")
   ```
   If the screen alone is insufficient, supplement with the git information in Step 3.
3. In the worker's working directory, run:
   - `git status`
   - `git diff --stat`
   - `git log --oneline -5`
4. Infer the worker's state from this information.

## Phase 3: persist state

> **state-db cutover (M4, Issue #267)**: `.state/state.db` is the sole SoT.
> Structured sections (Status / Updated / Suspended / Dispatcher / Curator /
> Worker Directory Registry / Active Work Items / Resume Instructions) **must
> be written via StateWriter**. The `transaction()` post-commit hook auto-
> regenerates `.state/org-state.md` from the DB (direct markdown edits are
> forbidden — drift_check detects them). Free-form session notes / Pending
> Lead / learnings live under `notes/` (see `notes/README.md`).
> `.state/journal.jsonl` was retired in M4 (the events table is the SoT).
> If the DB is stale, rebuild it with
> `python -m tools.state_db.importer --db .state/state.db --rebuild --no-strict`.

1. Copy the existing `org-state.md` to `org-state.prev.md` (backup).
2. **Write Status / Suspended to the DB** (via `StateWriter.transaction()`. The post-commit hook auto-regenerates `.state/org-state.md`; if regen fails, the DB write still committed and only a stderr warning is emitted):

   ```bash
   python -c "
   from datetime import datetime, timezone
   from pathlib import Path
   from tools.state_db import connect
   from tools.state_db.writer import StateWriter
   ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%fZ')
   conn = connect('.state/state.db')
   with StateWriter(conn, claude_org_root=Path('.')).transaction() as w:
       w.update_session(status='SUSPENDED', suspended_at=ts, updated_at=ts)
   "
   ```

   - bash / zsh / PowerShell all pass newlines inside `"..."` through, so the multi-line form works cross-shell. Windows CMD has no heredoc, so use the single-line fallback `py -3 -c "ts=...; conn=...; w=...; w.begin(); w.update_session(...); w.commit()"` (in which case the `transaction()` rollback / regen auto-swallow is lost; add explicit try/except).
   - The same command flips the Status line of `.state/org-state.md` to `SUSPENDED` (regenerated from the DB).
   - Free-form "supplementary notes for Resume Instructions", "Pending Lead", "learnings", etc. **go under `notes/`** (see `notes/README.md`). Direct markdown edits are detected by drift_check. `update_session(resume_instructions=...)` writes to the DB as a structured section.
3. To update the state of each Work Item, call `upsert_run(task_id=..., status=...)` inside the `transaction()`.
4. Update each worker's `.state/workers/worker-{id}.md`:
   - Add / update the "Current State at Suspend" section.
   - Append the suspend-time state to the Progress Log.
5. Append a suspend event to the DB (`tools/journal_append.py` is M4 DB-only routing; `ts` is auto-populated):
   ```bash
   py -3 tools/journal_append.py suspend \
       reason=user_requested \
       --json '{"active_workers": ["worker-xxx"], "pending_items": ["blog-redesign"]}'
   ```
   Refer to [`docs/journal-events.md`](../../../docs/journal-events.md) for the event-name / payload-key convention.

## Phase 3.5: stop the dashboard server

```bash
kill $(cat .state/dashboard.pid 2>/dev/null) 2>/dev/null || true
```

## Phase 4: stop all panes

The order matters. Stop in the order Worker → Dispatcher → Curator.

1. List the active peers with `mcp__org-broker__list_peers`.
2. **Stop the workers first**: send a shutdown instruction to every worker peer with `mcp__org-broker__send_message`:
   "SHUTDOWN: please end your work."
3. **Confirm worker panes are closed** — use a 2-pass structure:

   **Pass 1 (observe polite shutdown, up to 10 seconds)**:

   Long-poll `pane_exited` with `mcp__org-broker__poll_events`. Filter with `types=["pane_exited"]` to exclude other types, loop until the deadline, and break when every target has closed:
   ```
   pending_workers = {set of all worker names}
   cursor = None                           # omit `since` on the first call
   deadline = now + 10 seconds
   while pending_workers not empty and now < deadline:
       remaining_ms = (deadline - now) milliseconds
       result = mcp__org-broker__poll_events(
           since=cursor,
           timeout_ms=min(remaining_ms, 10000),
           types=["pane_exited"]
       )
       cursor = result.next_since
       for ev in result.events:
           if ev.role == "worker" and ev.name in pending_workers:
               pending_workers.remove(ev.name)
   # exit when deadline hits or pending_workers is empty
   ```
   - Omitting `since` on the first call gives "events from now on" semantics (does not replay past pane_exited).
   - The `types=["pane_exited"]` filter advances the cursor across all types, so there is no duplicate scan.
   - When a non-matching event arrives, long-poll early-returns (`events:[]` + advanced cursor); on empty responses, keep looping until the deadline.
   - Workers that did not close within 10 seconds go to Pass 2.

   **Pass 2 (fallback for residual workers + reconfirmation, up to 5 seconds)**:
   - For each worker still open after Pass 1:
     ```
     mcp__org-broker__close_pane(target="worker-{task_id}")
     ```
     to explicitly destroy the pane. On success the response text is `"Closed pane id=N."`. `[pane_not_found]` / `[pane_vanished]` are treated as already closed and skipped (see `references/renga-error-codes.md`). `[last_pane]` does not normally occur during the worker-shutdown phase (Lead / Dispatcher / Curator are still alive).
   - After that, run the same `poll_events` loop with `timeout_ms=5000` / a 5-second deadline to absorb the `pane_exited` events triggered by close_pane.
   - Workers still not closed after Pass 2 are checked with `mcp__org-broker__list_panes`; if they are still present, log to the journal and report to the human (forced kill is currently not supported).

4. **Stop the Dispatcher**: send a shutdown instruction to the Dispatcher via `mcp__org-broker__send_message`:
   "SHUTDOWN: please end your work."
5. **Stop the Curator (only if present)**: the curator is not resident, so this step is
   normally a no-op. Only when a pane with `name == "curator"` exists in
   `mcp__org-broker__list_panes` (the case where an on-demand curate was running when
   suspend overlapped it), send a shutdown instruction via `send_message`:
   "SHUTDOWN: please end your work." (curate uses a move-then-mark design, so stopping
   mid-cycle leaves no destructive intermediate state)
6. Confirm the Dispatcher (and, only if it existed, the Curator) with the same 2-pass structure as (3) (`pending = {"dispatcher"}`; if a curator existed, also add `"curator"` to the set; wait for `pane_exited` events whose `role == "dispatcher"` or `role == "curator"`):
   - Pass 1: a `poll_events(types=["pane_exited"], timeout_ms=10000)`-equivalent loop.
   - Pass 2: send `mcp__org-broker__close_pane(target="dispatcher")` (and `close_pane(target="curator")` if a curator remains) to remaining panes, then re-confirm with a `poll_events` loop (timeout_ms=5000).

**Handling the last pane (Lead)**: once the Dispatcher (and the Curator, if one existed) has closed, the only pane left in the tab is the Lead's. If the Lead tries to close itself with `mcp__org-broker__close_pane(target="secretary")`, `[last_pane]` (sole pane in the only tab) is returned, so the **Lead exits naturally on its own** (the human closes the terminal, or `/exit`s back to a shell). org-suspend is not responsible for closing the Lead pane.

7. Report to the human:
   ```
   The org has been suspended.
   - Saved: {N} work items
   - State file: .state/org-state.md
   Resume with /org-start.
   ```
