---
name: org-start
description: >
  Start up the org. Load the previous state and brief, then launch the dispatcher pane.
  Run this once right after starting Claude Code. Also triggered by "start", "boot", "begin", etc.
  The curator is not launched (it has moved to on-demand launch by the dispatcher
  when the threshold check at worker close fires).
effort: low
allowed-tools:
  - Read
  - Bash(bash tools/journal_append.sh:*)
  - Bash(py -3 tools/journal_append.py:*)
  - Bash(python -m tools.state_db.importer:*)
  - Bash(py -3 dashboard/org_state_converter.py:*)
  - Bash(python3 dashboard/org_state_converter.py:*)
  - Bash(py -3 tools/check_runtime_version.py:*)
  - Bash(python3 tools/check_runtime_version.py:*)
  - mcp__renga-peers__*
---

# org-start: starting the org

The first skill to run after Claude Code launches. Performs previous-state restoration and dispatcher startup.

> **The curator is not launched (on-demand model)**: the resident curator (spawn +
> `/loop 30m /org-curate`) is retired. The curator is launched temporarily only when the
> dispatcher detects, at worker pane close, that `tools/check_curate_threshold.py` exceeded
> a threshold ([`.dispatcher/references/pane-close.md`](../../../.dispatcher/references/pane-close.md) Step 5).
> org-start explicitly clears `curator_pane_id` / `curator_peer_id` via `StateWriter.CLEAR`
> (Block D-5). **Curator absence (null) is the normal state.**
> An auxiliary trigger for the threshold-check starvation case where no worker close happens
> for a while (an org-start backstop) is backlogged as
> [Issue #502](https://github.com/suisya-systems/claude-org-ja/issues/502).

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

> **Issue #410 / Stage B**: As soon as Step 0 (all four sub-steps: set_summary / MCP connectivity / identity verification / workers_dir verification) is complete, fire the `spawn_claude_pane` for the dispatcher, and in parallel with waiting for Claude to boot (~30-60s), run Block B (DB read of previous state) / Block C (dashboard server startup). The goal is to compress wall-clock time from ~3 minutes (when run serially) down to ~35s.
>
> **Execution model**: the Secretary fires the following three blocks (A/B/C) and finally joins at block D. Block A is I/O bound (renga MCP responses take a few hundred ms; after that we are just waiting on Claude's boot, which is a separate process), so wall-clock fully overlaps with B/C.

### Block A: spawn the dispatcher pane (fire only; do not wait for boot to finish)

Pane layout follows org-delegate/references/pane-layout.md (renga edition). The curator is not spawned here (on-demand model; see the note at the top of this file).

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
2. **Block here only on the spawn result** (do not wait for Claude's boot to complete). If the spawn failed with `[<code>] <msg>`, jump to "### Failure modes" at the end of this file. If the spawn succeeded (pane_id obtained), proceed in parallel with Blocks B / C.

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
     After briefing finishes, wait at Block D's join for the dispatcher to be ready, then run org-resume Phase 4 (worker re-dispatch) based on human approval.
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

### Block C2: claude-org-runtime version drift detection (Issue #472)

In parallel with Block A's spawn firing. Compare the installed version of `claude-org-runtime` to the latest on PyPI, and if there is drift, attach a one-line warning to the Step 4 startup-complete report. No auto-upgrade; notification only. **Do not hard-code version numbers in either this file or the script — use only values dynamically obtained via importlib.metadata and the PyPI JSON API** (to avoid the description going stale every time runtime releases).

1. Run the drift check:
   ```bash
   py -3 tools/check_runtime_version.py   # Windows
   python3 tools/check_runtime_version.py # Mac/Linux
   ```
2. Output branches:
   - stdout is empty (exit 0): one of installed == latest, not installed, offline, PyPI response parse failure, pin parse failure, no release within the pin range. **Do not emit a warning line in the Step 4 report** (silent).
   - stdout contains one line of `[runtime drift] ...`: drift detected. **Verbatim, transcribe that one line as a warning at the end of the Step 4 startup-complete report**.

> Design notes:
> - latest acquisition hits the PyPI JSON API (`https://pypi.org/pypi/claude-org-runtime/json`) via urllib.request (timeout 3s). `pip index versions` is experimental and emits a warning on stderr, so it is not adopted.
> - **pin window**: dynamically read the `claude-org-runtime` dependency constraint from ja's `pyproject.toml` via regex, and from the PyPI releases, only the latest satisfying that constraint is used as `latest` for comparison. This means that even if a higher major / higher minor is released to PyPI, an upgrade outside the window is not encouraged (uses `packaging.SpecifierSet`). On environments where `packaging` is not installed, silent skip.
> - yanked releases are excluded from candidates (so that versions pip would not normally pick are not displayed as `latest`).
> - Both "drift = older" and "drift = preview pulled in (installed > latest, release-channel skew)" are notified with the same one line. No auto-upgrade; the response is left to the user's judgment.
> - The warning command embeds the pin constraint read from `pyproject.toml` verbatim, so even if the user pastes the warning command as is, it will not upgrade outside the window.
> - Script body: [`tools/check_runtime_version.py`](../../../tools/check_runtime_version.py).

> **Sidebar: attention watcher startup guidance (optional, explicit start recommended)**
>
> You can run a separate resident watcher that actively notifies via OS notifications + sound + terminal bell for things like awaiting approval / awaiting decision / CI failure / silent stop / PR merged. **`/org-start` does not start it automatically** (OS notification backends are highly environment-dependent, and unsolicited sound is easily annoying. Design [`docs/design/attention-notification.md`](../../../docs/design/attention-notification.md) §11 Q1).
>
> For users who want to enable it, alongside the Step 4 startup-complete report, suggest running [`/org-attention-start`](../org-attention-start/SKILL.md). The skill handles the following in one shot:
>
> - If `.state/attention.json` is not in place, auto-copy it from `tools/templates/attention.example.json`.
> - Vertical-split the right side of the dispatcher pane and start `claude-org-runtime attention watch ...` resident.
> - Record the pane_id in the `.state/attention_pane.json` sidecar (referenced from [`/org-attention-stop`](../org-attention-stop/SKILL.md) for stopping).
>
> For a one-shot smoke test, use `claude-org-runtime attention scan --state-dir .state --config .state/attention.json --dry-run --json` (omit `--config` and you get the runtime-neutral English default, so always pass it when validating the ja template path). For per-OS backend behavior, troubleshooting, and bare-CLI startup from a separate terminal, see [`docs/operations/attention-watch.md`](../../../docs/operations/attention-watch.md).

### Block D: dispatcher join (Enter / list_peers poll / greeting / DB write / snapshot)

After Block A's spawn succeeds, Claude is booting in the dispatcher pane.

1. **Send Enter** — accept the "Load development channel? (Y/n)" prompt on Claude Code's first launch:
   ```
   mcp__renga-peers__send_keys(target="dispatcher", enter=true)
   ```
   - Enter is written to the PTY as CR (0x0D).
   - Without approval, the `server:renga-peers` channel is not enabled and `send_message` channel pushes do not arrive.
   - Depending on boot speed, sending Enter before the prompt is displayed may become a no-op. If the next list_peers poll does not confirm peer registration, resend Enter.
2. **Poll list_peers and confirm the dispatcher's peer registration**:
   ```
   mcp__renga-peers__list_peers
   # Poll until name="dispatcher" appears in the result
   ```
   - If it does not appear, (a) resend Enter, (b) if it is fatal such as `[pane_not_found]`, jump to the "Failure modes" section.
3. **Send the greeting message**:
   - dispatcher:
     "You are the dispatcher. Receive DELEGATE messages from the Lead, and on its behalf launch worker panes, send instructions, and record state. When you receive a CLOSE_PANE message, close that pane."
   - There is no greeting to the curator (it is not resident; the instruction message at on-demand launch is sent by the dispatcher).
4. **Wait for Block B's DB initialization to complete** — the join point for parallel execution. If in Block B-1 `.state/state.db` was absent and `importer --rebuild` ran, `StateWriter.update_session()` will fail until schema construction is complete, so Block B must finish before Block D-5's DB write. If Block B is incomplete (waiting on SUSPENDED briefing), wait for briefing to finish -> confirm DB schema health -> then proceed here.
5. **Record identities by batching DB transactions into one** (via `StateWriter.transaction()`; do not edit markdown directly. The post-commit hook regenerates `.state/org-state.md`). Write the dispatcher's identity, and **always explicitly clear the curator's identity with `StateWriter.CLEAR`** (with the on-demand model there is no resident curator. If stale `curator_pane_id` / `curator_peer_id` carried over from an old-scheme SUSPENDED state remain, the dashboard and balanced-split target selection misjudge based on the premise that a live curator exists. `StateWriter.update_session()` is contracted to interpret `None` as "unspecified = preserve", so explicit clear is mandatory):
   ```bash
   python -c "
   from pathlib import Path
   from tools.state_db import connect
   from tools.state_db.writer import StateWriter
   conn = connect('.state/state.db')
   with StateWriter(conn, claude_org_root=Path('.')).transaction() as w:
       w.update_session(
           dispatcher_pane_id='<d_pane>', dispatcher_peer_id='<d_peer>',
           curator_pane_id=StateWriter.CLEAR, curator_peer_id=StateWriter.CLEAR,
       )
   "
   ```
   Null curator fields are the **normal state**; suspend / handover / resume / dashboard all operate on that premise.
6. Regenerate the JSON snapshot just once (for the dashboard; separate path from the state-db cutover):
   `py -3 dashboard/org_state_converter.py`.

### Appendix: details of spawn_claude_pane arguments

Meanings and pitfalls of the spawn arguments:

- `target`: the pane to split. dispatcher uses `target="focused"` (splits the Lead pane).
- `direction`: `"horizontal"` = top/bottom split (existing = top / new = bottom); `"vertical"` = left/right split (existing = left / new = right).
- `role`: a label that lets `mcp__renga-peers__list_panes` identify the role.
- `name`: a stable name referenced by later `send_message(to_id="dispatcher", ...)` etc. **renga-peers interprets all-numeric names as ids, so always include letters in the name**.
- `cwd`: resolved relative to the caller pane's (= Lead's) cwd. The old approach of embedding `cd X && claude ...` in `command` is forbidden (the auto-upgrade does not fire and channel push is lost — a known pitfall).
- `permission_mode` / `model`: renga composes and runs `claude --permission-mode {mode} --model {model} --dangerously-load-development-channels server:renga-peers`.
- Return value: the text `"Spawned pane id=N."`. Errors are in the form `[<code>] <msg>` (e.g., `[split_refused]` / `[pane_not_found]` / `[cwd_invalid]`). For the code list and branches, see `.claude/skills/org-delegate/references/renga-error-codes.md`.
- `.dispatcher/CLAUDE.md` / `.curator/CLAUDE.md` hold the per-role instructions (separate from Secretary's CLAUDE.md).

### Failure modes

Classify at Block A's spawn stage:

- **dispatcher spawn failure (`[split_refused]` / `[cwd_invalid]` / other `[<code>]`)** — **Report the failure to the user; after fixing the cause, re-run /org-start**.
- **Spawn succeeds, but no peer registration during boot** — the Block D-2 poll times out. Resend Enter -> re-poll. After 3 retries, it is fatal: without the dispatcher, org-delegate / SECRETARY_RELAY do not function, so discard the pane with `close_pane`, **clear both dispatcher / curator identities with `StateWriter.CLEAR`, report to the user**, and prompt for /org-start re-execution.
- **Enter-timing skew** — if you send Enter before the "Load development channel?" prompt is displayed, it becomes a no-op. The Block D-2 peer-registration poll is ground truth. If the peer is not registered, return to Block D-1 and resend.

Curator spawn / boot failure modes do not exist in org-start (it does not spawn one). For failure handling at on-demand launch, see [`.dispatcher/references/pane-close.md`](../../../.dispatcher/references/pane-close.md) Steps 5-3 / 5-4.

### Wall-clock impact of Stage A / Stage B

| stage | change | wall-clock |
|---|---|---|
| before | state restore -> dashboard start -> dispatcher start (spawn+Enter+poll+greet+DB+snapshot) -> curator start (same) in serial | ~180s |
| after Stage A | dispatcher / curator startup batched into one parallel block; both spawn / Enter / poll / greet / DB write / snapshot bundled together | ~90s |
| after Stage A+B | on top of the above, fire Block A's spawn right after Step 0 completes, overlapping Claude's boot wait with Block B (state restore) / Block C (dashboard startup) | ~35s |
| after curator on-demand | only the dispatcher is launched (curator's spawn / Enter / poll / greet are gone) | further reduced |

## Step 4: report ready

Report concisely to the human. Only the dispatcher is launched (the curator is on-demand).

**Handling Block C2's runtime drift output**: if Block C2's `tools/check_runtime_version.py` stdout emitted a single `[runtime drift] ...` line, then for any of the templates below **transcribe that one line verbatim at the end, separated by one blank line**. If stdout was empty, do not attach the warning line (installed == latest / not installed / offline / parse failure / no release within the pin range are all silent).

**With previous state**:
```
Org started.
Previous state: {summary}
Dispatcher is running (the curator will be launched automatically and temporarily once enough learnings accumulate).
What would you like to do?
```

**First launch**:
```
Org started.
Dispatcher is running (the curator will be launched automatically and temporarily once enough learnings accumulate).
No projects are registered yet. What would you like to do?
```

**Example of attached warning on drift detection** (transcribed at the end of any template above; `{installed}` / `{latest_in_window}` / `{pin}` are determined at runtime by the script from PyPI and `pyproject.toml`, and must not be hard-coded into this file):
```
...
What would you like to do?

[runtime drift] claude-org-runtime: installed={installed} latest={latest_in_window} -- update with `python -m pip install --upgrade 'claude-org-runtime{pin}'`
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

### Curator (on-demand launch only — org-start does not spawn it)

Spawned by the dispatcher when a threshold fires at worker close ([`.dispatcher/references/pane-close.md`](../../../.dispatcher/references/pane-close.md) Step 5-3):

- `cwd="../.curator"` (the caller is the dispatcher; relative resolution against cwd=`.dispatcher/`)
- `permission_mode=auto`
- `model="opus"`

### Worker (used in org-delegate's Step 3)

**`model="opus"` is required (sonnet forbidden).**
Rationale: the worker's default permission_mode is `auto` (classifier-based). This safety classifier only operates stably on Opus. With sonnet, the classifier misjudges frequently, the approval flow breaks down, and work stalls. Only the dispatcher is fixed at `bypassPermissions` and thus bypasses the classifier, so sonnet operation is fine there (dispatcher is on sonnet for cost optimization; this does not apply to workers).

Typical:
- `cwd="{workers_dir}/{task_id}"` (absolute path recommended)
- `permission_mode=auto`
- `model="opus"`
