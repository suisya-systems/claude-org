---
name: org-suspend
description: >
  Suspend the organization, saving all state to disk. Use when told "suspend",
  "save and exit", "I want to close", "let's stop for now", or "we're done for today".
---

# org-suspend: Suspend the organization

Collect all Worker state, save it to disk, and stop all panes.

Pane operations go through the `mcp__renga-peers__*` MCP tools (renga 0.18.0+ is required). pane_exited
and equivalent lifecycle events are long-polled via `mcp__renga-peers__poll_events`, screen scraping
is done with `mcp__renga-peers__inspect_pane`, and raw key input via `mcp__renga-peers__send_keys`.

## Phase 1: Collect Worker state

1. Enumerate live peers with `mcp__renga-peers__list_peers`.
2. Send the following to all peers except yourself and the Curator via `mcp__renga-peers__send_message`:
   ```
   SUSPEND: please report your current state.
   1. What you have completed so far
   2. Files you changed (committed / uncommitted)
   3. What you were going to do next
   4. Blockers or unresolved issues
   ```
3. Wait 30 seconds for replies via `mcp__renga-peers__check_messages` (poll every 5 seconds).
4. Record the reports from Workers that responded.

## Phase 2: Scrape unresponsive Workers

For Workers that did not respond:

1. Read the Worker's state file under `.state/workers/` and obtain the Pane Name and Directory.
2. Read the latest console output via screen content scrape:
   ```
   mcp__renga-peers__inspect_pane(target="worker-{task_id}", format="text")
   ```
   If the screen content alone is insufficient, supplement with the git information in Step 3.
3. In the Worker's working directory, run:
   - `git status`
   - `git diff --stat`
   - `git log --oneline -5`
4. Estimate the Worker's state from this information.

## Phase 3: Write state

1. Copy the existing `org-state.md` to `org-state.prev.md` (backup).
2. Update `org-state.md`:
   - Change Status to `SUSPENDED`
   - Update Updated to the current time
   - Update each Work Item's state from the collected information
   - Note any caveats for resume in Resume Instructions
3. Regenerate the JSON snapshot:

   ```bash
   py -3 dashboard/org_state_converter.py    # Windows
   python3 dashboard/org_state_converter.py   # Mac/Linux
   ```

4. Update each Worker's `.state/workers/worker-{id}.md`:
   - Add/update a Current State at Suspend section
   - Append the suspend-time state to Progress Log
5. Append a suspend event to `journal.jsonl`:
   ```json
   {"ts":"<ISO timestamp>","event":"suspend","reason":"user_requested","active_workers":["worker-xxx"],"pending_items":["blog-redesign"]}
   ```

## Phase 3.5: Stop the dashboard server

```bash
kill $(cat .state/dashboard.pid 2>/dev/null) 2>/dev/null || true
```

## Phase 4: Stop all panes

The order matters. Stop in the order: Workers → Dispatcher → Curator.

1. Enumerate live peers with `mcp__renga-peers__list_peers`.
2. **Stop Workers first**: instruct all Worker peers to terminate via `mcp__renga-peers__send_message`:
   "SHUTDOWN: please end your work."
3. **Confirm Worker panes have closed** — perform with a 2-pass structure:

   **Pass 1 (observe polite shutdown, up to 10 seconds)**:

   Long-poll `pane_exited` via `mcp__renga-peers__poll_events`. Use the `types=["pane_exited"]` filter to exclude other types, and loop within the deadline; break once all targets have closed:
   ```
   pending_workers = {set of all Worker names}
   cursor = None                           # omit since on first call
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
   # exit when deadline reached or pending_workers is empty
   ```
   - With `since` omitted on the first call, the semantics are "events from now on" (no replay of past pane_exited).
   - The `types=["pane_exited"]` filter advances the cursor across all types, so there is no duplicate scan.
   - When a non-matching event arrives the long-poll early-returns (`events:[]` + advanced cursor), so the loop continues until the deadline on empty responses.
   - Workers that did not close within 10 seconds advance to Pass 2.

   **Pass 2 (fallback for stragglers + reconfirm, up to 5 seconds)**:
   - For each Worker that did not close in Pass 1:
     ```
     mcp__renga-peers__close_pane(target="worker-{task_id}")
     ```
     to explicitly destroy the pane. On success, the text `"Closed pane id=N."` is returned. `[pane_not_found]` / `[pane_vanished]` are treated as already-closed and skipped (see `references/renga-error-codes.md`). `[last_pane]` does not normally occur at the Worker stop stage (because the Lead/Dispatcher/Curator are still alive).
   - Then run the same `poll_events` loop again with `timeout_ms=5000` / a 5-second deadline to consume the `pane_exited` events triggered by close_pane.
   - Workers that are still not closed after Pass 2 are checked for liveness with `mcp__renga-peers__list_panes`; if any remain, log to journal and report to the human (forced termination is currently unsupported).

4. **Stop the Dispatcher**: instruct the Dispatcher to terminate via `mcp__renga-peers__send_message`:
   "SHUTDOWN: please end your work."
5. **Stop the Curator**: instruct the Curator to terminate via `mcp__renga-peers__send_message`:
   "SHUTDOWN: please end your work."
6. Confirm Dispatcher / Curator with the same 2-pass structure as in (3) (put `pending = {"dispatcher", "curator"}` into the set, and wait for `pane_exited` with `role == "dispatcher"` or `role == "curator"`):
   - Pass 1: an equivalent `poll_events(types=["pane_exited"], timeout_ms=10000)` loop
   - Pass 2: send `mcp__renga-peers__close_pane(target="dispatcher")` / `mcp__renga-peers__close_pane(target="curator")` to any remaining panes, and reconfirm via the `poll_events` loop (timeout_ms=5000)

**Handling the last pane (Lead)**: once the Dispatcher and Curator are closed, the only pane remaining in the tab is the Lead pane.
If the Lead tries to close itself with `mcp__renga-peers__close_pane(target="secretary")`, `[last_pane]` (the only pane in the only tab) is returned, so **the Lead exits naturally on its own with `exit`** (the human closes the terminal, or returns to the shell with `/exit`).
org-suspend takes no responsibility for closing the Lead pane.

7. Report to the human:
   ```
   The organization has been suspended.
   - Saved: {N} work items
   - State file: .state/org-state.md
   You can resume with /org-start.
   ```
