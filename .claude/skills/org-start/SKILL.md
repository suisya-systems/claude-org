---
name: org-start
description: >
  Start up the org. Load the previous state and brief, then launch the dispatcher and curator panes.
  Run this once right after starting Claude Code. Also triggered by "start", "boot", "begin", etc.
effort: low
allowed-tools:
  - Read
  - Bash(bash tools/journal_append.sh:*)
  - Bash(py -3 tools/journal_append.py:*)
  - Bash(python -m tools.state_db.importer:*)
  - Bash(py -3 dashboard/org_state_converter.py:*)
  - Bash(python3 dashboard/org_state_converter.py:*)
  - mcp__renga-peers__*
---

# org-start: starting the org

The first skill to run after Claude Code launches. Performs previous-state restoration, dispatcher startup, and curator startup.

> **Premise**: this Claude is running inside the Lead pane started via `renga --layout ops`.
> The `RENGA_SOCKET` / `RENGA_PANE_ID` environment variables are inherited, so the 14 `mcp__renga-peers__*` MCP
> tools (`spawn_pane` / `spawn_claude_pane` / `close_pane` / `focus_pane` /
> `list_panes` / `new_tab` / `send_message` / `list_peers` / `set_summary` /
> `check_messages` / `inspect_pane` / `poll_events` / `send_keys` /
> `set_pane_identity`) fully cover pane operations / peer messaging / screen scraping / lifecycle
> event subscription / raw key input within the same tab (**renga 0.18.0+ required**).
>
> **state DB premise (Issue #267 / M4)**: `.state/state.db` is the sole SoT.
> The read path is DB-only (markdown fallback was removed in M4); the write path
> for structured sections (Status / Dispatcher / Curator / Worker Directory Registry /
> Active Work Items / Resume Instructions) goes through `StateWriter.transaction()`
> (the post-commit hook regenerates `.state/org-state.md` from the DB; direct
> markdown editing is forbidden — drift_check will detect it). Free-form notes
> (learnings / Pending Lead etc.) live under `notes/`. `.state/journal.jsonl`
> was retired in M4.
> If the DB is missing, build it with `python -m tools.state_db.importer --db .state/state.db --rebuild --no-strict`.

## Step 0: initialization

1. Set your own summary via `mcp__renga-peers__set_summary`: "Secretary: Lead".
   - Required so that worker / dispatcher / curator can discover the Lead via `mcp__renga-peers__list_peers`.
2. Verify `renga-peers` MCP connectivity: call `mcp__renga-peers__list_panes`.
   - If a response comes back without error, MCP is enabled. From here on, proceed on the premise that renga-peers MCP tools are usable.
   - If an error returns / the tool is not registered, ask the user to run `renga mcp install` and
     pause execution of the Skill (have them retry after MCP is installed). See the README's
     "Installation" section for details.
3. **Verify and auto-recover the secretary pane identity**:
   - From the result of `mcp__renga-peers__list_panes`, identify the pane with `focused=true` (= yourself).
   - Expected: `name == "secretary"` and `role == "secretary"`.
   - **If mismatched** — started via a route other than `renga --layout ops` / attached to an existing session that was launched from the old ops.toml, etc.:
     1. Call `mcp__renga-peers__set_pane_identity(target="focused", name="secretary", role="secretary")` to auto-repair.
     2. On success, log a warning in the events table and continue (`bash tools/journal_append.sh secretary_identity_restored note=auto_recovered`).
     3. Failure branches:
        - `name_in_use` error: another existing pane is occupying `secretary`. Report the situation to the user and present the options "continue current session by making all workers send to `to_id="{numeric_pane_id}"`" / "persistent fix: `/org-suspend` -> exit -> relaunch with `renga --layout ops`".
        - `name_invalid` / other: report the cause to the user.
   - **If matched**: continue as is.
4. Read `workers_dir` from `registry/org-config.md` and verify the worker directories exist.
   If any exist, report the list to the user (absolutely do not delete).
   **Forbidden**: worker directories may contain past deliverables or reusable projects, so
   they must not be deleted at org-start. Follow org-delegate's directory-retention policy.

## Steps 1-3: parallel startup phase

> **Issue #410 / Stage B**: As soon as Step 0 (all four sub-steps: set_summary / MCP connectivity / identity verification / workers_dir verification) is complete, fire the `spawn_claude_pane` for dispatcher / curator, and in parallel with waiting for Claude to boot (~30-60s), run Block B (DB read of previous state) / Block C (dashboard server startup). The goal is to compress wall-clock time from ~3 minutes (when run serially) down to ~35s.
>
> **Execution model**: the Secretary fires the following three blocks (A/B/C) and finally joins at block D. Block A is I/O bound (renga MCP responses take a few hundred ms; after that we are just waiting on Claude's boot, which is a separate process), so wall-clock fully overlaps with B/C.

### Block A: spawn dispatcher / curator panes (fire only; do not wait for boot to finish)

Pane layout follows org-delegate/references/pane-layout.md (renga edition). The spawn itself completes with a few-hundred-ms MCP response, so it is sufficient to fire them sequentially (no need for parallel firing; curator needs to resolve dispatcher's name with target="dispatcher").

1. `spawn_claude_pane` for dispatcher:
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
   Capture the dispatcher's `pane_id` from the returned `"Spawned pane id=N."`. For the meaning of arguments and pitfalls, see "### Appendix: details of spawn_claude_pane arguments" at the end of this file.
2. Immediately after that returns, `spawn_claude_pane` for curator:
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
   target="dispatcher" resolves the stable name established in (1). Capture the curator's `pane_id` too.
3. **Block here only on the spawn result** (do not wait for Claude's boot to complete). If both spawns failed with `[<code>] <msg>`, jump to "### Failure modes" at the end of this file. If both spawns succeeded (pane_id obtained), proceed in parallel with Blocks B / C.

### Block B: check previous state

The read path is **DB only** (Issue #267 / M4). Run in parallel with Block A's spawn firing (Block A only asks for pane creation via MCP, and Claude's boot is a separate process, so there is no CPU / I/O contention).

1. Check whether `.state/state.db` exists.
   - Exists -> query the DB:
     ```bash
     python -c "from tools.state_db import connect; from tools.state_db.queries import get_org_state_summary; import json; \
       conn = connect('.state/state.db'); \
       print(json.dumps(get_org_state_summary(conn), ensure_ascii=False, indent=2, default=str))"
     ```
     Use `active_runs` / `recent_events` / `run_status_counts` / `session.status` / `session.objective` to understand the previous state.
   - Does not exist -> treat as first launch. Prompt the Secretary to run the importer:
     `python -m tools.state_db.importer --db .state/state.db --root . --rebuild --no-strict`.
2. Check session.status:
   - If `SUSPENDED`, run /org-resume Phases 1-3 (briefing / reconciliation / resume plan).
     Block A's spawn has already been fired, so Claude boots in the background while you brief.
     After briefing finishes, wait at Block D's join for dispatcher / curator to be ready, then run org-resume Phase 4 (worker re-dispatch) based on human approval.
   - If `ACTIVE`, the previous session may have terminated abruptly.
     Check the git state of each worker directory and report the current situation.

### Block C: start the dashboard server

In parallel with Block A's spawn firing. The dashboard server is a separate process (Python HTTP server) and is independent of Claude panes.

1. Check whether the dashboard server is running:
   ```bash
   cat .state/dashboard.pid 2>/dev/null && kill -0 $(cat .state/dashboard.pid) 2>/dev/null && echo "running" || echo "stopped"
   ```
2. If stopped, start it:
   ```bash
   python3 dashboard/server.py &   # Mac/Linux
   py -3 dashboard/server.py &     # Windows
   ```
3. Inform the user:
   "Dashboard started -> http://localhost:8099".

> **Sidebar: attention watcher startup guidance (optional, explicit start recommended)**
>
> You can run a separate resident watcher that actively notifies via OS notifications + sound + terminal bell for things like awaiting approval / awaiting decision / CI failure / silent stop / PR merged. **`/org-start` does not start it automatically** (OS notification backends are highly environment-dependent, and unsolicited sound is easily annoying. Design [`docs/design/attention-notification.md`](../../../docs/design/attention-notification.md) §11 Q1).
>
> For users who want to enable it, alongside the Step 4 startup-complete report, present them with running [`/org-attention-start`](../org-attention-start/SKILL.md). The skill handles the following in one shot:
>
> - If `.state/attention.json` is not in place, auto-copy it from `tools/templates/attention.example.json`.
> - Vertical-split the right side of the dispatcher pane and start `claude-org-runtime attention watch ...` resident.
> - Record the pane_id in the `.state/attention_pane.json` sidecar (referenced from [`/org-attention-stop`](../org-attention-stop/SKILL.md) for stopping).
>
> For a one-shot smoke test, use `claude-org-runtime attention scan --state-dir .state --config .state/attention.json --dry-run --json` (omit `--config` and you get the runtime-neutral English default, so always pass it when validating the ja template path). For per-OS backend behavior, troubleshooting, and bare-CLI startup from a separate terminal, see [`docs/operations/attention-watch.md`](../../../docs/operations/attention-watch.md).

### Block D: join both panes (Enter / list_peers poll / greeting / DB write / snapshot)

After both Block A spawns succeed, Claude is booting in parallel on both panes. **Wait for boot completion just once, then fire Enter / list_peers poll / greeting / DB write together for both panes** to realize the Stage A wall-clock reduction (180s -> 90s).

1. **Send Enter to both panes** — accept the "Load development channel? (Y/n)" prompt on Claude Code's first launch. Issue them in parallel (renga MCP is serial, but with few-hundred-ms responses it feels simultaneous):
   ```
   mcp__renga-peers__send_keys(target="dispatcher", enter=true)
   mcp__renga-peers__send_keys(target="curator", enter=true)
   ```
   - Enter is written to the PTY as CR (0x0D).
   - Without approval, the `server:renga-peers` channel is not enabled and `send_message` channel pushes do not arrive.
   - Because Claude boots at slightly different speeds, sending Enter before the prompt is displayed may become a no-op. If the next list_peers poll does not confirm peer registration, resend Enter.
2. **Poll list_peers and confirm both dispatcher / curator peer registrations in one go** — since both panes boot in parallel, you do not need separate polls per role; a single poll loop can wait for both registrations simultaneously:
   ```
   mcp__renga-peers__list_peers
   # Poll until both name="dispatcher" / "curator" appear in the result
   ```
   - If both do not appear, (a) resend Enter to the pane that did not receive it, (b) if it is fatal such as `[pane_not_found]`, jump to the "Failure modes" section.
3. **Send greeting messages to both in parallel**:
   - dispatcher:
     "You are the dispatcher. Receive DELEGATE messages from the Lead, and on its behalf launch worker panes, send instructions, and record state. When you receive a CLOSE_PANE message, close that pane."
   - curator:
     "You are the curator. Please run /loop 30m /org-curate. You will perform knowledge curation every 30 minutes."
4. **Wait for Block B's DB initialization to complete** — the join point for parallel execution. If in Block B-1 `.state/state.db` was absent and `importer --rebuild` ran, `StateWriter.update_session()` will fail until schema construction is complete, so Block B must finish before Block D-5's DB write. If Block B is incomplete (waiting on SUSPENDED briefing), wait for briefing to finish -> confirm DB schema health -> then proceed here.
5. **Record identities by batching DB transactions into one** (via `StateWriter.transaction()`; do not edit markdown directly. The post-commit hook regenerates `.state/org-state.md`). **If both roles succeeded, write all four**. **If one role failed at D-2 / D-3 (boot impossible, already `close_pane`'d, etc.), write only the successful role; for the failed role, explicitly clear the stale `*_pane_id` / `*_peer_id` carried over from the previous SUSPENDED with `StateWriter.CLEAR`** (`StateWriter.update_session()` is contracted to interpret `None` as "unspecified = preserve", so explicit clear is mandatory):
   ```bash
   python -c "
   from pathlib import Path
   from tools.state_db import connect
   from tools.state_db.writer import StateWriter
   conn = connect('.state/state.db')
   with StateWriter(conn, claude_org_root=Path('.')).transaction() as w:
       # Example for the both-success case (for a failed role, pass StateWriter.CLEAR instead of a value)
       w.update_session(
           dispatcher_pane_id='<d_pane>', dispatcher_peer_id='<d_peer>',
           curator_pane_id='<c_pane>', curator_peer_id='<c_peer>',
       )
   "
   ```
6. Regenerate the JSON snapshot just once (for the dashboard; separate path from the state-db cutover. Since both identities can be reflected together, there is no need to call it twice):
   `py -3 dashboard/org_state_converter.py`.

### Appendix: details of spawn_claude_pane arguments

Meanings and pitfalls of the arguments shared by both spawns:

- `target`: the pane to split. dispatcher uses `target="focused"` (splits the Lead pane). curator uses `target="dispatcher"` (resolves the stable name established at Block A-1 and takes the right half of the dispatcher pane).
- `direction`: `"horizontal"` = top/bottom split (existing = top / new = bottom); `"vertical"` = left/right split (existing = left / new = right).
- `role`: a label that lets `mcp__renga-peers__list_panes` identify the role.
- `name`: a stable name referenced by later `send_message(to_id="dispatcher", ...)` / `close_pane(target="curator")` etc. **renga-peers interprets all-numeric names as ids, so always include letters in the name**.
- `cwd`: resolved relative to the caller pane's (= Lead's) cwd. The old approach of embedding `cd X && claude ...` in `command` is forbidden (the auto-upgrade does not fire and channel push is lost — a known pitfall).
- `permission_mode` / `model`: renga composes and runs `claude --permission-mode {mode} --model {model} --dangerously-load-development-channels server:renga-peers`.
- Return value: the text `"Spawned pane id=N."`. Errors are in the form `[<code>] <msg>` (e.g., `[split_refused]` / `[pane_not_found]` / `[cwd_invalid]`). For the code list and branches, see `.claude/skills/org-delegate/references/renga-error-codes.md`.
- `.dispatcher/CLAUDE.md` / `.curator/CLAUDE.md` hold the per-role instructions (separate from Secretary's CLAUDE.md).

### Failure modes

Parallel firing introduces failure patterns that differ from the old serial execution. Classify at Block A's spawn stage:

- **dispatcher spawn failure (`[split_refused]` / `[cwd_invalid]` / other `[<code>]`)** — curator spawn will fail to resolve the name in `target="dispatcher"` and fail in succession with `[pane_not_found]`. **Report both failures to the user; after fixing the cause, re-run /org-start**. The half-done state (curator alone running) cannot occur.
- **curator spawn failure / dispatcher spawn success** — keep dispatcher and report to the user. The core of org functionality (worker dispatch / state writes) is maintained by dispatcher alone, so **present the user with the options "dispatcher is up; respawn curator, or temporarily continue without curator"**. Drive Blocks B / C / D dispatcher-related steps to completion independent of curator failure. **The DB write should write only the dispatcher portion; explicitly clear the curator portion with `StateWriter.CLEAR`** (if stale `curator_pane_id` / `curator_peer_id` from the previous SUSPENDED remain, the dashboard and balanced-split target selection misjudge based on the premise that a live curator exists. `StateWriter.update_session()` is contracted to interpret `None` as "unspecified = preserve", so explicit clear is mandatory):
  ```python
  from tools.state_db.writer import StateWriter
  ...
  with StateWriter(conn, claude_org_root=Path('.')).transaction() as w:
      w.update_session(
          dispatcher_pane_id='<d_pane>', dispatcher_peer_id='<d_peer>',
          curator_pane_id=StateWriter.CLEAR, curator_peer_id=StateWriter.CLEAR,
      )
  ```
- **Both spawns succeed, but one fails to register as a peer during boot** — the Block D-2 poll times out on one side. Resend Enter to that pane -> re-poll. After 3 retries, discard the pane with `close_pane` and branch as follows:
  - **Curator-only peer registration failure**: allow the same temporary continuation as "curator spawn failure / dispatcher spawn success" above (dispatcher alone maintains the core org functionality). Block D-5's DB write writes only dispatcher; curator gets `StateWriter.CLEAR`.
  - **Dispatcher-only peer registration failure**: temporary continuation not allowed (fatal). Without dispatcher, org-delegate / SECRETARY_RELAY do not function, and keeping curator alone is useless, so also `close_pane` the curator, **clear both identities with `StateWriter.CLEAR`, report to the user**, and prompt for /org-start re-execution.
  - **Both time out**: `close_pane` both panes, `StateWriter.CLEAR` both identities, report to the user + re-execute.
- **Enter-timing skew** — if you send Enter before the "Load development channel?" prompt is displayed, it becomes a no-op. Block D-1 sends both in parallel so one side may be too early, but the Block D-2 peer-registration poll is ground truth. If a peer is not registered, return to Block D-1 and resend.

### Wall-clock impact of Stage A / Stage B

| stage | change | wall-clock |
|---|---|---|
| before | state restore -> dashboard start -> dispatcher start (spawn+Enter+poll+greet+DB+snapshot) -> curator start (same) in serial | ~180s |
| after Stage A | dispatcher / curator startup batched into one parallel block; both spawn / Enter / poll / greet / DB write / snapshot bundled together | ~90s |
| after Stage A+B | on top of the above, fire Block A's spawn right after Step 0 completes, overlapping Claude's boot wait with Block B (state restore) / Block C (dashboard startup) | ~35s |

## Step 4: report ready

Report concisely to the human. Depending on what was written in Block D-5's DB write, accurately enumerate the started roles (so as not to falsely report "curator started" when curator failed):

**With previous state (both roles succeeded)**:
```
Org started.
Previous state: {summary}
Dispatcher and curator are running.
What would you like to do?
```

**First launch (both roles succeeded)**:
```
Org started.
Dispatcher and curator are running.
No projects are registered yet. What would you like to do?
```

**curator spawn / boot failure, dispatcher only running**:
```
Org started (partial).
Dispatcher is running, but curator startup failed (reason: {[<code>] / peer-registration timeout etc.}).
Choose between respawning curator to recover, or temporarily continuing without curator.
(Without curator, worker dispatch / state writes still work, but automatic knowledge curation (/loop 30m /org-curate) is disabled.)
```

## Appendix: Claude Code startup commands (per role)

Per-role parameters for `spawn_claude_pane` used in Block A / org-delegate Step 3.
On renga 0.18.0+, `mcp__renga-peers__spawn_claude_pane` accepts per-role structured fields (`cwd` / `permission_mode` / `model` / `args[]`) and auto-appends `--dangerously-load-development-channels server:renga-peers`. The old pattern of piping `cd X && claude ...` into `spawn_pane` is **forbidden** (it reintroduces the pitfall where renga's bare-`claude` auto-upgrade does not fire and channel push is lost).

Common arguments:
- `permission_mode`: literal `auto` written directly (except for dispatcher). CLAUDE.md has no variable-expansion mechanism, so values from `registry/org-config.md` cannot be substituted at runtime. If you change the value, see the sync-warning section at the top of `registry/org-config.md`.
- `cwd`: relative path to each role's dedicated directory (resolved relative to the caller pane's cwd).

> **Note**: The Secretary is launched via `renga --layout ops` and runs without `--permission-mode` specified (as the human-judgment Lead). See the "Per-role scope of application" section in `registry/org-config.md`.

### Dispatcher

- `cwd=".dispatcher"`
- `permission_mode="bypassPermissions"` (fixed; not affected by `default_permission_mode`)
- `model="sonnet"`

Rationale: when launching workers, the dispatcher issues `mcp__renga-peers__spawn_claude_pane`. The safety classifier of auto mode judges this "child agent launch" as "Create Unsafe Agents" and blocks it, so worker dispatch does not succeed under auto.

### Curator

- `cwd=".curator"`
- `permission_mode=auto`
- `model="opus"`

### Worker (used in org-delegate's Step 3)

**`model="opus"` is required (sonnet forbidden).**
Rationale: the worker's default permission_mode is `auto` (classifier-based). This safety classifier only operates stably on Opus. With sonnet, the classifier misjudges frequently, the approval flow breaks down, and work stalls. Only the dispatcher is fixed at `bypassPermissions` and thus bypasses the classifier, so sonnet operation is fine there (dispatcher is on sonnet for cost optimization; this does not apply to workers).

Typical:
- `cwd="{workers_dir}/{task_id}"` (absolute path recommended)
- `permission_mode=auto`
- `model="opus"`
