---
name: org-start
description: >
  Start the organization. Load prior state, brief, and bring up the Dispatcher
  and Curator panes. Run this once immediately after launching ClaudeCode.
  Also triggered by "start it", "boot", "begin", etc.
---

# org-start: Starting the organization

The first skill to run after ClaudeCode launches. It restores prior state, brings up the Dispatcher, and brings up the Curator.

> **Prerequisite**: This Claude runs inside a Lead pane that was started via `renga --layout ops`.
> The `RENGA_SOCKET` / `RENGA_PANE_ID` environment variables are inherited, so the 14 `mcp__renga-peers__*` MCP
> tools (`spawn_pane` / `spawn_claude_pane` / `close_pane` / `focus_pane` /
> `list_panes` / `new_tab` / `send_message` / `list_peers` / `set_summary` /
> `check_messages` / `inspect_pane` / `poll_events` / `send_keys` /
> `set_pane_identity`) cover everything: pane operations within the same tab, peer messaging, screen scraping, lifecycle
> event subscription, even raw key input (**requires renga 0.18.0+**).

## Step 0: Initialization

1. Set your own summary via `mcp__renga-peers__set_summary`: "Lead"
   - Required so that Workers / Dispatcher / Curator can find the Lead via `mcp__renga-peers__list_peers`
2. Verify `renga-peers` MCP connectivity by calling `mcp__renga-peers__list_panes`.
   - If a response comes back without error, MCP is enabled. From here on, assume the renga-peers MCP tools are usable.
   - If an error is returned / the tool is unregistered, prompt the user to run `renga mcp install`
     and pause this Skill (have them retry once MCP is set up). See the README's
     "Installation" section for details.
3. **Validate the secretary pane identity and auto-recover if needed**:
   - From the result of `mcp__renga-peers__list_panes`, identify the pane with `focused=true` (= yourself)
   - Expected: `name == "secretary"` and `role == "secretary"`
   - **If they do not match** — started via a path other than `renga --layout ops`, or attached to an existing session created with an old ops.toml, etc.:
     1. Call `mcp__renga-peers__set_pane_identity(target="focused", name="secretary", role="secretary")` to auto-repair
     2. On success, leave a warning log (`{"event":"secretary_identity_restored"}` in `journal.jsonl`) and continue
     3. Failure branches:
        - `name_in_use` error: another existing pane occupies `secretary`. Report the situation to the user and offer the choice between "if continuing the current session, have all Workers send with `to_id="{numeric_pane_id}"`" or "for a permanent fix, `/org-suspend` → exit → restart with `renga --layout ops`".
        - `name_invalid` / other: report the cause to the user
   - **If they match**: continue as-is
4. Read `workers_dir` from `registry/org-config.md` and confirm that the worker directories exist.
   If any directories exist, report the list to the user (never delete them).
   **Prohibited**: worker directories may contain past deliverables or reusable projects, so
   they must not be deleted at org-start time. Follow the directory retention policy in org-delegate.

## Step 1: Check prior state

1. Check whether `.state/org-state.md` exists
2. If it exists:
   - Read the file and check Status
   - If Status is `SUSPENDED`, run Phases 1–3 (briefing / reconciliation / resume plan) of /org-resume.
     Then proceed to Step 2 onward, bring up the Dispatcher and Curator, and finally execute Phase 4 (re-dispatch Workers) of /org-resume based on human approval
   - If Status is `ACTIVE`, the prior session may have terminated abruptly.
     Check the git status of each worker directory and report the current state
3. If it does not exist:
   - Treat this as the first launch

## ClaudeCode launch commands (per role)

In renga 0.18.0+, `mcp__renga-peers__spawn_claude_pane` accepts role-specific structured fields (`cwd` / `permission_mode` / `model` / `args[]`) and automatically appends `--dangerously-load-development-channels server:renga-peers`. The old pattern of feeding `cd X && claude ...` into `spawn_pane` is **prohibited** (it reintroduces the trap where renga's bare-`claude` auto-upgrade does not fire and channel push fails to arrive).

Common arguments:
- `permission_mode`: use the value of `default_permission_mode` from registry/org-config.md (except for the Dispatcher)
- `cwd`: relative path to each role's dedicated directory (resolved against the caller pane's cwd)

> **Note**: the Secretary is started via `renga --layout ops` and runs without `--permission-mode` specified (it is the human-judgment window). See the "Per-role applicability" section in `registry/org-config.md`.

### Dispatcher

- `cwd=".dispatcher"`
- `permission_mode="bypassPermissions"` (fixed; not affected by `default_permission_mode`)
- `model="sonnet"`

Reason: when launching Workers, the Dispatcher issues `mcp__renga-peers__spawn_claude_pane`. The auto-mode safety classifier flags this "child agent launch" as "Create Unsafe Agents" and blocks it, so Worker dispatch does not work in auto mode.

### Curator

- `cwd=".curator"`
- `permission_mode={default_permission_mode}`
- `model="opus"`

### Worker (used in org-delegate Step 3)

**`model="opus"` is required (sonnet prohibited).**
Reason: the Worker's default permission_mode is `auto` (classifier-based). This safety classifier only operates reliably on Opus. With sonnet the classifier misclassifies frequently, the approval flow breaks down, and work stalls. Only the Dispatcher is fixed at `bypassPermissions`, so it bypasses the classifier and runs fine on sonnet (the Dispatcher uses sonnet as a cost optimization; do not extend that to Workers).

Normal:
- `cwd="{workers_dir}/{task_id}"` (absolute path recommended)
- `permission_mode={default_permission_mode}`
- `model="opus"`

## Step 1.5: Start the dashboard server

1. Check whether the dashboard server is running:
   ```bash
   cat .state/dashboard.pid 2>/dev/null && kill -0 $(cat .state/dashboard.pid) 2>/dev/null && echo "running" || echo "stopped"
   ```
2. If stopped, start it:
   ```bash
   python3 dashboard/server.py &   # Mac/Linux
   py -3 dashboard/server.py &     # Windows
   ```
3. Tell the user:
   "Dashboard started → http://localhost:8099"

## Step 2: Spawn the Dispatcher pane

Pane layout follows org-delegate/references/pane-layout.md (renga edition).

1. Use `mcp__renga-peers__spawn_claude_pane` to split the Lead pane horizontally and launch the Dispatcher Claude in the bottom half:
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
   - `target="focused"`: split the currently focused Lead pane (optional; defaults to focused)
   - `direction="horizontal"` = top/bottom split (Lead = top / Dispatcher = bottom)
   - `role="dispatcher"`: label so that `mcp__renga-peers__list_panes` can identify the role
   - `name="dispatcher"`: stable name used for later `mcp__renga-peers__send_message(to_id="dispatcher", ...)` and `close_pane(target="dispatcher")`. **renga-peers interprets all-digit names as ids, so always use a name that contains letters.**
   - `cwd=".dispatcher"`: resolved to `.dispatcher/` relative to the caller pane (= Lead) cwd. The old method of embedding `cd X && claude ...` in `command` is prohibited (auto-upgrade does not fire and channel push is lost).
   - `permission_mode="bypassPermissions"` / `model="sonnet"`: renga composes and runs `claude --permission-mode bypassPermissions --model sonnet --dangerously-load-development-channels server:renga-peers`
   - `.dispatcher/CLAUDE.md` contains the role instructions for the Dispatcher (separate from the Lead's CLAUDE.md)
   - Return value: text of the form `"Spawned pane id=N."`. Subsequent pane operations should reference it as `name="dispatcher"`.
   - Errors are returned as text in `[<code>] <msg>` form (e.g. `[split_refused]` / `[pane_not_found]` / `[cwd_invalid]`). See `.claude/skills/org-delegate/references/renga-error-codes.md` for the code list and branches.
2. On the first launch of Claude Code, a "Load development channel? (Y/n)" prompt appears. Approve it via the shared helper, which polls the screen until the prompt is actually rendered before sending Enter (a blind `send_keys(enter=true)` here races zsh and silently leaves the pane hung — see suisya-systems/claude-org#23):

   ```
   approve_dev_channel_prompt(target="dispatcher")
   ```

   The full procedure, marker strings, and timeout-escalation behavior live in `.claude/skills/org-delegate/references/approve-dev-channel.md` (path is from the repo root; the helper is shared across this skill and `org-delegate`). The helper is idempotent — safe to call even if the prompt has already cleared. On timeout it sends a `DEV_CHANNEL_TIMEOUT` message to `secretary` (a send-to-self when the Lead is the caller — surfaces in the Lead's own inbox), and the Lead pauses `/org-start` for human direction. Without approval the `server:renga-peers` channel is not enabled, so `send_message` push from later steps would never arrive and the `list_peers` wait in Step 3 would time out.
3. Wait for the new peer to appear via `mcp__renga-peers__list_peers`
4. Send the following to the Dispatcher via `mcp__renga-peers__send_message`:
   "You are the Dispatcher. Receive DELEGATE messages from the Lead and, on its behalf, launch Worker panes, send instructions, and record state. When you receive a CLOSE_PANE message, close the pane."
5. Record the Dispatcher's peer ID and renga pane name (`dispatcher`) (in the Dispatcher section of org-state.md)
6. Regenerate the JSON snapshot:
   `py -3 dashboard/org_state_converter.py`

## Step 3: Spawn the Curator pane

1. Use `mcp__renga-peers__spawn_claude_pane` to launch the Curator on the right half of the Dispatcher pane:
   ```
   mcp__renga-peers__spawn_claude_pane(
     target="dispatcher",
     direction="vertical",
     role="curator",
     name="curator",
     cwd=".curator",
     permission_mode="{default_permission_mode}",
     model="opus"
   )
   ```
   - `target="dispatcher"`: target the Dispatcher pane named in Step 2 for splitting
   - `direction="vertical"` = left/right split (Dispatcher = left / Curator = right)
   - `name="curator"`: stable name (must contain letters; all-digit names are forbidden)
   - `cwd=".curator"`: resolved to `.curator/` from the caller pane (= Lead) cwd
   - `.curator/CLAUDE.md` contains the role instructions for the Curator
   - Errors use the same `[<code>] <msg>` form as Step 2
2. As in Step 2, approve the "Load development channel?" prompt via the shared helper (polls until the prompt renders, then sends Enter; idempotent and timeout-safe):

   ```
   approve_dev_channel_prompt(target="curator")
   ```

   See `.claude/skills/org-delegate/references/approve-dev-channel.md` for the procedure and timeout-escalation behavior.
3. Wait for the new peer to appear via `mcp__renga-peers__list_peers`
4. Send the following to the Curator via `mcp__renga-peers__send_message`:
   "You are the Curator. Run /loop 30m /org-curate. Knowledge curation runs every 30 minutes."
5. Record the Curator's peer ID and renga pane name (`curator`) (in the Curator section of org-state.md)
6. Regenerate the JSON snapshot:
   `py -3 dashboard/org_state_converter.py`

## Step 4: Report readiness

Report concisely to the human:

**When prior state exists**:
```
Organization started.
Prior state: {summary}
Dispatcher and Curator are up.
What would you like to do?
```

**On first launch**:
```
Organization started.
Dispatcher and Curator are up.
No projects are registered yet. What shall we do?
```
