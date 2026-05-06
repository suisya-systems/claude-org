---
name: org-start
description: >
  Start the organization. Load the previous state and brief it,
  then start the Dispatcher and Curator panes. Run once immediately after starting ClaudeCode.
  Also triggers on phrases like "start", "boot", or "begin".
---

# org-start: Start the Organization

The first skill to run after starting ClaudeCode. Restores the previous state, starts the Dispatcher, and starts the Curator.

> **Prerequisite**: This Claude is running inside the Lead pane started with `renga --layout ops`.
> Because the `RENGA_SOCKET` / `RENGA_PANE_ID` environment variables are inherited, the 14
> `mcp__renga-peers__*` MCP tools (`spawn_pane` / `spawn_claude_pane` / `close_pane` / `focus_pane` /
> `list_panes` / `new_tab` / `send_message` / `list_peers` / `set_summary` /
> `check_messages` / `inspect_pane` / `poll_events` / `send_keys` /
> `set_pane_identity`) cover pane operations, peer messaging, screen scraping, lifecycle
> event subscription, and raw key input within the same tab (**requires renga 0.18.0+**).
>
> **State DB prerequisite (Issue #267 / M4)**: `.state/state.db` is the only SoT.
> The read path is DB only (markdown fallback was removed in M4), and the write path for
> structured sections (Status / Dispatcher / Curator / Worker Directory Registry /
> Active Work Items / Resume Instructions) goes through
> `StateWriter.transaction()` (the post-commit hook automatically regenerates
> `.state/org-state.md` from the DB; direct markdown edits are forbidden and
> detected by drift_check). Free-form notes (findings / Pending Lead / etc.)
> are stored under `notes/`. `.state/journal.jsonl` was removed in M4.
> If the DB does not exist, build it with `python -m tools.state_db.importer --db .state/state.db --rebuild --no-strict`.

## Step 0: Initialization

1. Set your summary with `mcp__renga-peers__set_summary`: `Secretary: Lead`
   - Required so Workers / Dispatcher / Curator can discover the Lead via `mcp__renga-peers__list_peers`
2. Verify connectivity to the `renga-peers` MCP: call `mcp__renga-peers__list_panes`.
   - If it returns without error, the MCP is active. Continue assuming the renga-peers MCP tools are available
   - If it returns an error or the tool is not registered, tell the user to run `renga mcp install`
     and pause this skill (have them retry after MCP setup). See the `Installation` section in
     `README.md` for details
3. **Validate and auto-recover the secretary pane identity**:
   - From the `mcp__renga-peers__list_panes` result, identify the pane with `focused=true` (= yourself)
   - Expected: `name == "secretary"` and `role == "secretary"`
   - **If it does not match**: started outside `renga --layout ops`, or attached to an existing session started with an old `ops.toml`, etc.
     1. Call `mcp__renga-peers__set_pane_identity(target="focused", name="secretary", role="secretary")` to auto-repair
     2. If it succeeds, leave a warning log in the events table and continue (`bash tools/journal_append.sh secretary_identity_restored note=auto_recovered`)
     3. Failure branches:
        - `name_in_use` error: another existing pane already owns `secretary`. Report the situation to the user and offer these options: "If continuing this session, have all Workers send to `to_id="{numeric_pane_id}"`" or "For a permanent fix, run `/org-suspend` -> exit -> restart with `renga --layout ops`"
        - `name_invalid` / other: report the cause to the user
   - **If it matches**: continue as-is
4. Read `registry/org-config.md`, get `workers_dir`, and verify whether the worker directory exists.
   If any directories exist, report the list to the user (never delete them).
   **Forbidden**: worker directories may contain prior work products or reusable projects,
   so do not delete them during org-start. Follow the directory retention policy in org-delegate.

## Step 1: Check the Previous State

The read path is **DB only** (Issue #267 / M4).

1. Check whether `.state/state.db` exists
   - If it exists, query the DB:
     ```bash
     python -c "from tools.state_db import connect; from tools.state_db.queries import get_org_state_summary; import json; \
       conn = connect('.state/state.db'); \
       print(json.dumps(get_org_state_summary(conn), ensure_ascii=False, indent=2, default=str))"
     ```
     Use `active_runs` / `recent_events` / `run_status_counts` / `session.status` / `session.objective` to understand the previous state
   - If it does not exist, treat this as the first startup. Prompt the Lead to run the importer:
     `python -m tools.state_db.importer --db .state/state.db --root . --rebuild --no-strict`
2. Check `session.status`:
   - If `SUSPENDED`, run Phases 1-3 of /org-resume (briefing, reconciliation, resume plan).
     Then continue to Step 2 and later, start the Dispatcher and Curator, and after that run Phase 4 of org-resume (re-dispatch Workers) based on human approval
   - If `ACTIVE`, the previous session may have terminated unexpectedly.
     Check the git state of each worker directory and report the current situation

## ClaudeCode Launch Commands by Role

In renga 0.18.0+, `mcp__renga-peers__spawn_claude_pane` accepts role-specific structured fields (`cwd` / `permission_mode` / `model` / `args[]`) and automatically appends `--dangerously-load-development-channels server:renga-peers`. The old pattern of passing `cd X && claude ...` through `spawn_pane` is **forbidden** because it reintroduces the pitfall where renga's bare-`claude` auto-upgrade does not fire and channel push stops working.

Common arguments:
- `permission_mode`: write the literal `auto` directly (except for the Dispatcher). `CLAUDE.md` has no variable expansion mechanism, so values from `registry/org-config.md` cannot be substituted at runtime. If you need to change it, see the sync note section at the top of `registry/org-config.md`
- `cwd`: relative path to the directory dedicated to that role (resolved relative to the caller pane's cwd)

> **Note**: The Lead is started by `renga --layout ops` and runs without `--permission-mode` set (because it is the human-judgment desk). See the `Role-specific scope` section in `registry/org-config.md`.

### Dispatcher

- `cwd=".dispatcher"`
- `permission_mode="bypassPermissions"` (fixed; not affected by `default_permission_mode`)
- `model="sonnet"`

Reason: the Dispatcher issues `mcp__renga-peers__spawn_claude_pane` when starting Workers. The auto-mode safety classifier classifies this "child agent startup" as "Create Unsafe Agents" and blocks it, so Worker dispatch does not work under auto.

### Curator

- `cwd=".curator"`
- `permission_mode=auto`
- `model="opus"`

### Worker (used in org-delegate Step 3)

**`model="opus"` is required (`sonnet` is forbidden).**
Reason: the default Worker `permission_mode` is `auto` (classifier-based). This safety classifier only behaves reliably on Opus. With sonnet it misclassifies too often, the approval flow breaks, and work stalls. Only the Dispatcher is fixed to `bypassPermissions`, so it does not go through the classifier and is safe to run on sonnet (the Dispatcher uses sonnet for cost optimization; do not apply that to Workers).

Normal:
- `cwd="{workers_dir}/{task_id}"` (absolute path recommended)
- `permission_mode=auto`
- `model="opus"`

## Step 1.5: Start the Dashboard Server

1. Check whether the dashboard server is running:
   ```bash
   cat .state/dashboard.pid 2>/dev/null && kill -0 $(cat .state/dashboard.pid) 2>/dev/null && echo "running" || echo "stopped"
   ```
2. If it is stopped, start it:
   ```bash
   python3 dashboard/server.py &   # Mac/Linux
   py -3 dashboard/server.py &     # Windows
   ```
3. Tell the user:
   "Started the dashboard -> http://localhost:8099"

## Step 2: Start the Dispatcher Pane

Follow the pane layout in `org-delegate/references/pane-layout.md` (renga version).

1. Use `mcp__renga-peers__spawn_claude_pane` to split the Lead pane horizontally and start the Dispatcher Claude in the lower half:
   ```
   mcp__renga-peers__spawn_claude_pane(
     target="focused",
     direction="horizontal",
     role="dispatcher",
     name="dispatcher",
     cwd=".dispatcher",
     permission_mode="bypassPermissions",
     model="sonnet"
   )
   ```
   - `target="focused"`: split the currently focused Lead pane (optional; defaults to focused if omitted)
   - `direction="horizontal"` = top/bottom split (Lead=top / Dispatcher=bottom)
   - `role="dispatcher"`: attach a label so `mcp__renga-peers__list_panes` can identify the role
   - `name="dispatcher"`: stable name used by later calls such as `mcp__renga-peers__send_message(to_id="dispatcher", ...)` and `close_pane(target="dispatcher")`. **renga-peers interprets all-digit names as ids, so always use a name that contains letters**
   - `cwd=".dispatcher"`: resolved to `.dispatcher/` relative to the caller pane (= Lead). The old pattern of embedding `cd X && claude ...` in `command` is forbidden because auto-upgrade does not fire and channel push is lost
   - `permission_mode="bypassPermissions"` / `model="sonnet"`: renga synthesizes and runs `claude --permission-mode bypassPermissions --model sonnet --dangerously-load-development-channels server:renga-peers`
   - `.dispatcher/CLAUDE.md` contains Dispatcher role instructions (separate from the Lead's `CLAUDE.md`)
   - Return value: text like `"Spawned pane id=N."`. For later pane operations, refer to it as `name="dispatcher"`
   - Errors are returned as text in `[<code>] <msg>` format (for example `[split_refused]` / `[pane_not_found]` / `[cwd_invalid]`). For the code list and handling, see `.claude/skills/org-delegate/references/renga-error-codes.md`
2. On first Claude Code startup, the confirmation prompt `Load development channel? (Y/n)` appears. Approve it by sending Enter with `mcp__renga-peers__send_keys`:
   ```
   mcp__renga-peers__send_keys(target="dispatcher", enter=true)
   ```
   - Enter is written to the PTY as CR (`0x0D`)
   - Without approval, the `server:renga-peers` channel is not enabled, `send_message` channel push does not arrive, and the `list_peers` wait in Step 3 times out
3. Wait for the new peer to appear in `mcp__renga-peers__list_peers`
4. Send the following to the Dispatcher with `mcp__renga-peers__send_message`:
   "You are the Dispatcher. Receive DELEGATE messages from the Lead, then handle Worker pane startup, instruction delivery, and state recording. If you receive a CLOSE_PANE message, close the pane."
5. **Record the Dispatcher identity through the DB** (via `StateWriter.transaction()`; direct markdown edits are forbidden. The post-commit hook regenerates it):
   ```bash
   python -c "
   from pathlib import Path
   from tools.state_db import connect
   from tools.state_db.writer import StateWriter
   conn = connect('.state/state.db')
   with StateWriter(conn, claude_org_root=Path('.')).transaction() as w:
       w.update_session(dispatcher_pane_id='<pane_id>', dispatcher_peer_id='<peer_id>')
   "
   ```
6. Regenerate the JSON snapshot (for the dashboard; separate path from the state-db cutover):
   `py -3 dashboard/org_state_converter.py`

## Step 3: Start the Curator Pane

1. Use `mcp__renga-peers__spawn_claude_pane` to start the Curator in the right half of the Dispatcher pane:
   ```
   mcp__renga-peers__spawn_claude_pane(
     target="dispatcher",
     direction="vertical",
     role="curator",
     name="curator",
     cwd=".curator",
     permission_mode="auto",
     model="opus"
   )
   ```
   - `target="dispatcher"`: use the Dispatcher pane named in Step 2 as the split target
   - `direction="vertical"` = left/right split (Dispatcher=left / Curator=right)
   - `name="curator"`: stable name (must contain letters; all-digit names are forbidden)
   - `cwd=".curator"`: resolves to `.curator/` relative to the caller pane (= Lead)
   - `.curator/CLAUDE.md` contains Curator role instructions
   - Errors use the same `[<code>] <msg>` format as Step 2
2. As in Step 2, approve the `Load development channel?` prompt by sending Enter:
   ```
   mcp__renga-peers__send_keys(target="curator", enter=true)
   ```
3. Wait for the new peer to appear in `mcp__renga-peers__list_peers`
4. Send the following to the Curator with `mcp__renga-peers__send_message`:
   "You are the Curator. Run /loop 30m /org-curate. Organize findings every 30 minutes."
5. **Record the Curator identity through the DB** (via `StateWriter.transaction()`; direct edits are forbidden. The post-commit hook regenerates it):
   ```bash
   python -c "
   from pathlib import Path
   from tools.state_db import connect
   from tools.state_db.writer import StateWriter
   conn = connect('.state/state.db')
   with StateWriter(conn, claude_org_root=Path('.')).transaction() as w:
       w.update_session(curator_pane_id='<pane_id>', curator_peer_id='<peer_id>')
   "
   ```
6. Regenerate the JSON snapshot (for the dashboard; separate path from the state-db cutover):
   `py -3 dashboard/org_state_converter.py`

## Step 4: Report Ready State

Report concisely to the human:

**If there is a previous state**:
```
組織を起動しました。
前回の状態: {サマリー}
ディスパッチャーとキュレーターを起動しました。
何をしますか？
```

**If this is the first startup**:
```
組織を起動しました。
ディスパッチャーとキュレーターを起動しました。
プロジェクトはまだ登録されていません。何をしましょうか？
```
