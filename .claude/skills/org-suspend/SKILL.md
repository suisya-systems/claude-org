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
  - mcp__renga-peers__*
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

Pane operations go through the `mcp__renga-peers__*` MCP tools (renga 0.18.0+ assumed). Lifecycle events equivalent to pane_exited are long-polled via `mcp__renga-peers__poll_events`; screen scraping via `mcp__renga-peers__inspect_pane`; raw key input via `mcp__renga-peers__send_keys`.

## Phase 1: collect worker state

1. List the active peers with `mcp__renga-peers__list_peers`.
2. Send the following to every peer except yourself and the Curator via `mcp__renga-peers__send_message`:
   ```
   SUSPEND: report your current state.
   1. What you have completed so far.
   2. Files you changed (committed / uncommitted).
   3. What you were about to do next.
   4. Blockers or unresolved issues.
   ```
3. Wait up to 30 seconds for responses, polling `mcp__renga-peers__check_messages` every 5 seconds.
4. Record the responses from the workers that replied.

## Phase 2: scrape unresponsive workers

For workers that did not reply:

1. Read the worker's state file under `.state/workers/` to get the Pane Name and Directory.
2. Read the latest console output via screen scrape:
   ```
   mcp__renga-peers__inspect_pane(target="worker-{task_id}", format="text")
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

1. List the active peers with `mcp__renga-peers__list_peers`.
2. **Stop the workers first**: send a shutdown instruction to every worker peer with `mcp__renga-peers__send_message`:
   "SHUTDOWN: please end your work."
3. **Confirm worker panes are closed** — use a 2-pass structure:

   **Pass 1 (observe polite shutdown, up to 10 seconds)**:

   Long-poll `pane_exited` with `mcp__renga-peers__poll_events`. Filter with `types=["pane_exited"]` to exclude other types, loop until the deadline, and break when every target has closed:
   ```
   pending_workers = {set of all worker names}
   cursor = None                           # omit `since` on the first call
   deadline = now + 10 seconds
   while pending_workers not empty and now < deadline:
       remaining_ms = (deadline - now) milliseconds
       result = mcp__renga-peers__poll_events(
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
     mcp__renga-peers__close_pane(target="worker-{task_id}")
     ```
     to explicitly destroy the pane. On success the response text is `"Closed pane id=N."`. `[pane_not_found]` / `[pane_vanished]` are treated as already closed and skipped (see `references/renga-error-codes.md`). `[last_pane]` does not normally occur during the worker-shutdown phase (Lead / Dispatcher / Curator are still alive).
   - After that, run the same `poll_events` loop with `timeout_ms=5000` / a 5-second deadline to absorb the `pane_exited` events triggered by close_pane.
   - Workers still not closed after Pass 2 are checked with `mcp__renga-peers__list_panes`; if they are still present, log to the journal and report to the human (forced kill is currently not supported).

4. **Stop the Dispatcher**: send a shutdown instruction to the Dispatcher via `mcp__renga-peers__send_message`:
   "SHUTDOWN: please end your work."
5. **Stop the Curator (only if present)**: the curator is not resident, so this step is
   normally a no-op. Only when a pane with `name == "curator"` exists in
   `mcp__renga-peers__list_panes` (the case where an on-demand curate was running when
   suspend overlapped it), send a shutdown instruction via `send_message`:
   "SHUTDOWN: please end your work." (curate uses a move-then-mark design, so stopping
   mid-cycle leaves no destructive intermediate state)
6. Confirm the Dispatcher (and, only if it existed, the Curator) with the same 2-pass structure as (3) (`pending = {"dispatcher"}`; if a curator existed, also add `"curator"` to the set; wait for `pane_exited` events whose `role == "dispatcher"` or `role == "curator"`):
   - Pass 1: a `poll_events(types=["pane_exited"], timeout_ms=10000)`-equivalent loop.
   - Pass 2: send `mcp__renga-peers__close_pane(target="dispatcher")` (and `close_pane(target="curator")` if a curator remains) to remaining panes, then re-confirm with a `poll_events` loop (timeout_ms=5000).

**Handling the last pane (Lead)**: once the Dispatcher (and the Curator, if one existed) has closed, the only pane left in the tab is the Lead's. If the Lead tries to close itself with `mcp__renga-peers__close_pane(target="secretary")`, `[last_pane]` (sole pane in the only tab) is returned, so the **Lead exits naturally on its own** (the human closes the terminal, or `/exit`s back to a shell). org-suspend is not responsible for closing the Lead pane.

7. Report to the human:
   ```
   The org has been suspended.
   - Saved: {N} work items
   - State file: .state/org-state.md
   Resume with /org-start.
   ```
