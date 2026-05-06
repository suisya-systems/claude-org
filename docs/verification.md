# Verification Procedures

Verification steps for each feature. If an issue is found, fix the skill or `CLAUDE.md` and retest.

**Prerequisites**: renga 0.18.0+ (`npm install -g @suisya-systems/renga@0.18.0`, then `renga mcp install --force` to register the `renga-peers` MCP server in user scope). Assumes support for structured `cwd` (0.16.0), `set_pane_identity` (0.17.0), and `spawn_claude_pane` (0.18.0).

---

## 0. Regression Check (Preventing startup template regressions)

**Purpose**: Detect whether the `cd X && claude ...` auto-upgrade bypass pattern removed in Issue #58 has been reintroduced into templates / skills / docs.

**Steps**:
```bash
# (1) Places where `cd X && claude` is composed into the command argument of spawn_pane / spawn_claude_pane
#     (Forbidden: renga's bare-claude auto-upgrade will not trigger, and channel push will not arrive)
grep -rEn 'command="cd [^"]*&&[[:space:]]*claude' --include="*.md" --include="*.toml" . \
  && { echo "FAIL: cd&&claude composition still remains"; exit 1; } \
  || echo "OK: no cd&&claude composition"

# (2) `claude --dangerously-load-development-channels` is handwritten in command lines in ops.toml / layout TOML
#     (Unnecessary because of bare-claude auto-upgrade in renga 0.16.0+ / automatic addition by spawn_claude_pane)
grep -En '^[[:space:]]*command[[:space:]]*=.*dangerously-load-development-channels' renga-layouts/*.toml \
  && { echo "FAIL: dangerously flag is handwritten in layout"; exit 1; } \
  || echo "OK: no explicit flag in layout TOML"
```

**Expected results**:
- (1) returns 0 matches (explanatory mentions in prose should not match because the quoting / notation is different)
- (2) returns 0 matches in `renga-layouts/*.toml`

**If it fails**:
- If there is a match, rewrite it using the structured fields of `spawn_claude_pane` (`cwd` / `permission_mode` / `model`). For details, see the "ClaudeCode startup commands (by role)" section in `.claude/skills/org-start/SKILL.md` and `.claude/skills/org-delegate/references/pane-layout.md`

## 0. Compatibility Preflight

**Purpose**: Before running `/org-start`, verify that the renga version and MCP tool surface satisfy claude-org requirements (Issue #61).

**Steps**:
```bash
py -3 tools/check_renga_compat.py            # Windows
python3 tools/check_renga_compat.py          # macOS / Linux
py -3 tools/check_renga_compat.py --json     # Machine-readable output
```

**Expected result**: Exits with `Result: OK` and exit code 0. It passes if the renga version, `renga-peers` MCP registration, and all 14 required tools are present.

**Failure patterns**:
- renga version too old → `npm update -g @suisya-systems/renga`
- MCP not registered → `renga mcp install`
- Missing tools → refresh stale registration with `renga mcp install --force`

This script does not require a live renga session (it performs a static probe by fetching tools/list through `renga mcp-peer` stdio).

---

## 1. Basic Startup Test

**Purpose**: Start ClaudeCode in a cloned repository and verify that `CLAUDE.md` and the skills are loaded correctly.

**Steps**:
1. `git clone` this repository anywhere
2. Run `renga --layout ops` in the clone destination (the Lead pane should start)
3. In Claude Code in the Lead pane, confirm that `mcp__renga-peers__list_panes` is reachable (MCP validity check from Step 0)
4. In Claude Code in the Lead pane, run `/org-start`

**Expected results**:
- Since `.state/org-state.md` does not exist, it is recognized as the first startup
- `mcp__renga-peers__spawn_claude_pane` opens the Dispatcher pane below the Lead, and then opens the Curator pane to its right
- The "development channel confirmation prompt" shown immediately after Dispatcher / Curator startup is passed by injecting Enter with `mcp__renga-peers__send_keys(target=<pane>, enter=true)` (the procedure in `org-start` SKILL Step 2 / Step 3)
- The Curator is instructed via `mcp__renga-peers__send_message` to run `/loop 30m /org-curate`
- It reports: "This is the first startup. What would you like to do?"

**Failure patterns and fixes**:
- `CLAUDE.md` is not loaded → verify `.claude/` directory placement
- Skills are not recognized → verify the frontmatter format of `.claude/skills/*/SKILL.md`
- `/org-start` does not trigger → check for skill name conflicts or the description
- `mcp__renga-peers__list_panes` returns an error → rerun `renga mcp install --force`, then confirm registration with `claude mcp list`
- `send_keys(enter=true)` fails to inject Enter → check whether the Dispatcher / Curator pane is stuck at the "Load development channel?" prompt, then press Enter manually

---

## 2. org-delegate Test (Dispatching Workers)

**Purpose**: Verify that Workers are dispatched correctly, complete their work, and report results.

**Prerequisites**: Started with `renga --layout ops`, `renga-peers` MCP is enabled (`Connected` confirmed in `claude mcp list`), and `/org-start` has already been run in Test 1.

**Steps**:
1. Ask the Lead Claude to do a task (for example: "Add a new blog post")
2. For a new project, answer the prompts for alias, path, and description
3. Confirm that the Lead dispatches a Worker with `/org-delegate`

**Expected results**:
- The project is automatically registered in `registry/projects.md`
- The Lead sends a DELEGATE message to the Dispatcher and immediately returns to the conversation with the user
- The Dispatcher spawns a Worker pane in the same tab with `mcp__renga-peers__spawn_claude_pane` (`name="worker-{task_id}"`; the balanced split strategy follows `pane-layout.md`)
- The Dispatcher confirms startup completion with `mcp__renga-peers__poll_events(types=["pane_started"])`
- The "development channel confirmation prompt" shown immediately after Worker startup is passed by injecting Enter with `mcp__renga-peers__send_keys(target="worker-{task_id}", enter=true)` (`org-delegate` SKILL Step 3-2)
- The Dispatcher sends work instructions to the Worker via `mcp__renga-peers__send_message`
- The Dispatcher creates `.state/workers/worker-{id}.md`
- `.state/org-state.md` is created/updated
- Events are recorded in `.state/journal.jsonl`
- After the Worker finishes, the report arrives via `renga-peers` to the **Lead** (not the Dispatcher)
- The Lead communicates the result to the human in business language (avoiding technical jargon)
- The Lead asks the Dispatcher to close the pane (the Dispatcher destroys it with `mcp__renga-peers__close_pane(target="worker-{task_id}")`)

**Verification commands**:
```bash
cat .state/org-state.md
cat .state/journal.jsonl
ls .state/workers/
cat registry/projects.md
```

To inspect pane state, use the MCP tool:
```
mcp__renga-peers__list_panes    # Current pane list
```

**Failure patterns and fixes**:
- A pane does not open → check the current pane state with `mcp__renga-peers__list_panes`, then branch on `[split_refused]` / `[pane_not_found]` from the tool result using `references/renga-error-codes.md`
- Cannot communicate over `renga-peers` → check with `claude mcp list` that `renga-peers` is Connected, and use `list_peers` to confirm peer IDs (`worker-{task_id}` / `dispatcher` / `curator` / `secretary`)
- State files are not created → review the org-delegate skill procedure
- The Worker does not understand the instructions → improve the wording in `instruction-template.md`
- Project name resolution does not work → review org-delegate Step 0

### 2.1 Balanced Split Scale Verification (4 parallel / 8 parallel)

**Purpose**: On a real system, verify that the rect-based balanced split in org-delegate Step 3 produces the expected tree for both 4-way and 8-way parallelism without triggering `[split_refused]`.

**Prerequisites**: Test 2 passes. Terminal width `W ≥ 160 cols` (check with `tput cols`). Keep the "Balanced split strategy for Workers" section of `pane-layout.md` open for reference.

**Steps**:
1. Run `tput cols` and record W. If it is below 160, skip as not verifiable or widen the terminal.
2. Ask the Lead for 8 mutually independent tasks in sequence (dummy tasks are fine, for example lightweight tasks such as `echo-1` through `echo-8`). For each k=1 through 8, confirm all of the following:
   - a. The result text of the Dispatcher's `mcp__renga-peers__spawn_claude_pane` call does not contain `[split_refused]`
   - b. The `target` / `direction` selected by the Step 3-1b algorithm can be reproduced from the immediately preceding `list_panes` snapshot on a rect basis
   - c. Save the `mcp__renga-peers__list_panes` output immediately after startup to a **separate log file (for example `.state/verification/balanced-split-{timestamp}.log`)**, or record the `name` / `id` where `role == "worker"` on the spot, and cross-check afterward against the `worker_spawned` event in `.state/journal.jsonl`
3. At each point k is reached, fetch the pane layout with `list_panes` and confirm that the Step 3-1b algorithm can be reproduced by hand against the snapshot (identify curator → role filter (all 4 roles are candidates) → dispatcher-curator adjacency check → direction decision → `new_w / new_h` calculation → `MIN_PANE` constraint → SECRETARY safeguard (`new_w >= 140` and `new_h >= 30`) → **sort by (role priority desc, metric desc, id asc)** where role priority is secretary 4 > curator 3 > worker 2 > dispatcher 1). As stated in "Balanced split strategy for Workers" in `pane-layout.md`, do not use fixed grid shapes such as 2×2 or 2×4 as the success criterion because the layout is rect-based and dynamic.
4. Try a 9th dummy task and confirm that the Dispatcher sends `SPLIT_CAPACITY_EXCEEDED` to the Lead through `renga-peers`. **Dispatch must be aborted only for that 9th Worker, while the Dispatcher's own monitoring loop continues running** (`spawn_claude_pane` is not issued, and the Dispatcher does not exit because of `exit` or similar).

> **Note**: Verification logs such as `.state/verification/balanced-split-{timestamp}.log` are temporary files and should not be committed. `.state/*` is already excluded by the existing `.gitignore`.

**Expected results**:
- Zero occurrences of `[split_refused]` for k=1 through 8
- For each k, the layout matches the Step 3-1b decision result (fixed grid shapes are not required; the rect-based dynamic layout must work correctly)
- The candidate set does not become empty as long as the `MIN_PANE` constraints (`new_w ≥ 20` / `new_h ≥ 5`) are satisfied
- Explicit escalation at k=9 (no silent failure)

**Verification commands**:
```bash
tput cols                                # Record terminal width
cat .state/journal.jsonl | grep worker_spawned
```

For pane state, use MCP:
```
mcp__renga-peers__list_panes             # Snapshot at each k
```

**Failure patterns and fixes**:
- `[split_refused]` at k=4 → check the value from `tput cols`. If W < 160, the balanced split requirement is not met. Retry after widening the terminal
- `[split_refused]` already at k=3 → check whether a file tree / preview is still open directly under the Dispatcher (if visible, they reduce `W_f` by 20 to 40 cols)
- Layout deviates from expectations → a Worker from a previous task was not closed. Confirm with `list_panes` that the count of active panes with `role=worker` starts from 0
- Silent behavior at k=9 → the Step 3-1c (`SPLIT_CAPACITY_EXCEEDED` escalation) branch is not firing. Confirm that the Step 3-1b decision logic correctly returns "no candidates"

---

## 3. org-suspend Test (Suspend)

**Purpose**: Verify that the organization state is saved correctly and all panes stop.

**Prerequisites**: From Test 2, a Worker is running or has just finished.

**Steps**:
1. Tell the Lead Claude: "Suspend"
2. Confirm that `/org-suspend` triggers

**Expected results**:
- A SUSPEND message is sent to the Worker via `mcp__renga-peers__send_message`
- The Worker reports its state via `renga-peers`. For unresponsive Workers, read the screen contents with `mcp__renga-peers__inspect_pane(target="worker-{task_id}", format="text")` and estimate the state in combination with git status
- The Status in `.state/org-state.md` becomes `SUSPENDED`
- A backup is created at `.state/org-state.prev.md`
- SHUTDOWN is sent to all peers with `mcp__renga-peers__send_message`
- Wait for `pane_exited` with `mcp__renga-peers__poll_events(types=["pane_exited"], timeout_ms=10000)` and process all `role == "worker"` exits together
- Remaining Workers are fallback-closed with `mcp__renga-peers__close_pane(target="worker-{task_id}")`
- All Worker panes are closed first, then the Dispatcher, and finally the Curator
- The Lead reports that suspension is complete

**Verification commands**:
```bash
cat .state/org-state.md | head -5  # Confirm Status: SUSPENDED
cat .state/journal.jsonl | tail -1  # Confirm suspend event
```

**Failure patterns and fixes**:
- A Worker does not respond to SUSPEND → inspect the screen content with `inspect_pane` and confirm that the Phase 2 scrape works
- A pane does not close → check the result text of `close_pane(target="X")`. Treat `[pane_not_found]` / `[pane_vanished]` as skip
- `[last_pane]` appears → let the final Lead pane exit naturally by self-exit (org-suspend does not close it)
- State file is incomplete → review the org-suspend procedure

---

## 4. org-resume Test (Resume)

**Purpose**: Verify that after suspension and restart, the previous state is restored correctly.

**Prerequisites**: Suspended in Test 3.

**Steps**:
1. **Completely close** the Lead Claude terminal
2. Start again in the clone destination with `renga --layout ops`
3. Run `/org-start`

**Expected results**:
- `/org-start` detects `.state/org-state.md` and confirms `Status: SUSPENDED`
- Following the `/org-resume` procedure, it displays a summary of the previous state
- It reports the reconciliation results against git state in each working directory
- It proposes a resume plan
- It waits for human approval (it does not dispatch Workers on its own)
- The Dispatcher and Curator panes are restarted via `mcp__renga-peers__spawn_claude_pane`

**Verification points**:
- Whether the briefing matches `.state/org-state.md`
- Whether git state reconciliation is accurate
- Whether the Dispatcher and Curator panes are running (check with `mcp__renga-peers__list_panes`)

**Failure patterns and fixes**:
- `/org-start` does not read the state → review Step 1 of the org-start skill
- State is inaccurate → review the format of `org-state.md` or the write path in org-suspend
- The Curator does not start → check `send_message` / `spawn_claude_pane` in org-start Step 3

---

## 5. Sudden Termination Test (Crash Recovery)

**Purpose**: Verify how much can be restored if the terminal is closed without running org-suspend.

**Steps**:
1. In the Test 2 state (Worker running), close the terminal **without suspending**
2. Start again with `renga --layout ops`
3. Run `/org-start`

**Expected results**:
- `/org-start` detects `.state/org-state.md` and confirms that the Status is still ACTIVE
- It determines that the previous session ended unexpectedly and checks git state in each Worker directory
- It supplements events since the last snapshot from `.state/journal.jsonl`
- It reports the current state

**Acceptable degradation**:
- Detailed progress information reported by Workers themselves is lost
- Information after the last entry in `journal.jsonl` is lost
- Work not committed to git may have ambiguous status
- If the Dispatcher's `poll_events` cursor (`.state/dispatcher-event-cursor.txt`) is lost, events from the previous 5 seconds may be missed, but recovery is possible by reconciling with `list_panes`

**Failure patterns and fixes**:
- `org-state.md` is too stale → increase periodic snapshot frequency (strengthen progress management in org-delegate)
- `journal.jsonl` does not exist → check the journaling implementation

---

## 6. org-retro Test (Retrospective)

**Purpose**: Verify that lessons learned are recorded correctly after task completion.

**Steps**:
1. Have a Worker complete some task
2. Confirm that the Lead runs `/org-retro`

**Expected results**:
- If there is reusable knowledge, `knowledge/raw/YYYY-MM-DD-{topic}.md` is created
- The format follows "fact → judgment → evidence → application context"
- If it is judged unnecessary to record, nothing is created (which is the correct decision)

**Verification commands**:
```bash
ls knowledge/raw/
cat knowledge/raw/*.md  # Check format
```

---

## 7. org-curate Test (Knowledge Curation + Self-Improvement Loop)

**Purpose**: Verify that the Curator can organize knowledge and make improvement proposals.

**Prerequisites**: There are at least 5 uncurated files in `knowledge/raw/`.

**Steps**:
1. Create 5 or more dummy knowledge files in `knowledge/raw/` for testing
2. Run `/org-curate` manually (or wait for the Curator's `/loop`)

**Expected results**:
- Raw files are classified by theme
- Themed files are created in `knowledge/curated/{theme}.md`
- `<!-- curated -->` is appended to the beginning of processed raw files
- If there is an improvement proposal, the Lead is notified via `renga-peers`

**Verification commands**:
```bash
ls knowledge/curated/
cat knowledge/curated/*.md
head -1 knowledge/raw/*.md  # Confirm <!-- curated --> marker
```

**Self-improvement checks**:
- Whether the content of the improvement proposal is concrete
- Whether the proposal is not executed without human approval

---

## 8. Dispatcher / Curator Pane Test

**Purpose**: Verify that the Dispatcher and Curator start correctly in dedicated panes and function properly.

**Steps**:
1. Run `/org-start` and confirm that the Dispatcher and Curator panes are launched
2. Confirm that the Dispatcher receives role instructions via `mcp__renga-peers__send_message`
3. Confirm that the Curator runs `/loop 30m /org-curate` via `mcp__renga-peers__send_message`
4. Place fewer than the threshold number of files in `knowledge/raw/` and confirm that the Curator skips
5. Increase the count above the threshold and confirm that it runs in the next `/loop` cycle

**Expected results**:
- After `/org-start`, the Dispatcher and Curator open side by side below the Lead (`mcp__renga-peers__list_panes` for confirmation)
- The Dispatcher enters a state of waiting for DELEGATE messages
- The Curator starts `/loop`
- org-curate triggers every 30 minutes
- It skips below the threshold and runs at or above the threshold

**Failure patterns and fixes**:
- Panes open but do not receive instructions → adjust `renga-peers` peer detection timing (retry `list_peers`, extend waiting for `pane_started` events)
- The Dispatcher does not react to DELEGATE → review the contents of the initial message to the Dispatcher
- `/loop` does not run → review the message contents sent to the Curator

---

## 9. org-dashboard Test (Dashboard)

**Purpose**: Verify that the dashboard live server starts correctly and renders in the browser.

**Prerequisites**: Worker dispatch and project registration are complete in Test 2.

**Steps**:
1. Tell the Lead: "Show me the dashboard"
2. Confirm that `/org-dashboard` triggers

**Expected results**:
- `dashboard/server.py` starts and the server comes up at `http://localhost:8099`
- `http://localhost:8099` opens in the browser
- The project list, work status, activity, and knowledge are displayed
- The response from `/api/state` matches the actual state

**Failure patterns and fixes**:
- Server does not start → check error output from `dashboard/server.py`
- Data does not appear in the browser → verify with `curl` that `http://localhost:8099` is responding
- Data does not update → check the SSE connection state (`/api/events`)

---

## 10. E2E Test (Full Cycle)

**Purpose**: Verify that the entire cycle of startup → work → suspend → resume → knowledge curation functions correctly.

**Steps**:
1. Start ClaudeCode in the clone destination (`renga --layout ops`)
2. Run `/org-start` (first startup)
3. Request 3 tasks (ones that cause Worker dispatch)
4. Confirm that a retrospective is recorded after each task is completed
5. Review the overall picture with "Show me the dashboard"
6. Suspend with `/org-suspend`
7. Completely close the terminal
8. Start again → `/org-start` → confirm that the previous state is reported
9. Approve resumption → confirm that Workers are dispatched again
10. When `knowledge/raw/` reaches the threshold, confirm that curation runs
11. Confirm that curated knowledge can be `git commit`ed and pushed

**Success criteria**:
- All steps complete without human intervention other than instructions and approval
- No state is lost
- Knowledge is accumulated and organized
- The overall picture can be reviewed in the dashboard

---

## 10.1. sandbox.denyRead / denyWrite Real-Environment Verification (Phase 2a, Issue #79)

**Purpose**: Verify that `sandbox.filesystem.denyRead` / `denyWrite` in `.claude/settings.json` behaves as expected in a Windows + Git Bash environment, and that secret files such as `.env` cannot be read through Claude Code's Bash tool.

**Prerequisites**:
- This repository is cloned and Claude Code can be started
- A dummy `.env` is prepared at the root of the repository under test (for example `FAKE_TOKEN=dummy-not-a-real-secret`; it is not committed because it is covered by `.gitignore`)
- A known bug, [anthropics/claude-code#32226](https://github.com/anthropics/claude-code/issues/32226), has reports of cases where denyRead does not work as expected, so **the behavior must always be verified on a real machine**

**Steps**:
1. Ask the Lead Claude to run `cat .env` (through the Bash tool)
2. Ask it to run a command that reads `.env`, such as `grep -r FAKE_TOKEN .`
3. Ask it to run a command that tries to read `~/.ssh/id_rsa` (if it exists)
4. Ask it to run a command that tries to write to `~/.claude/settings.json` (for example `echo x >> ~/.claude/settings.json`)

**Expected results**:
- Steps 1-3: denied in the Bash subprocess by the sandbox (an error equivalent to `Permission denied`). Even if Claude Code receives the result, the content is empty or an error
- Step 4: write fails due to denyWrite

**Failure patterns and fixes**:
- The contents of `.env` can be read → possible bug on the Claude Code side. Record the version and `claude --version`, and check the status of Issue #32226. As a temporary workaround, add `Read(./.env)` to `permissions.deny` (to block the Claude Code Read tool path)
- Glob such as `**/credentials*` does not work on Windows → possible forward/backward slash difference. Adjust the glob pattern to `./credentials*` or similar and retry
- The sandbox itself is not activating → possible default OFF for `sandbox.enabled` in Claude Code. Check the current default in the official docs

**Note**: `sandbox.enabled` is not explicitly set in this PR (it relies on the Claude Code default). To limit the impact surface of known bug #32226, this is being introduced in phases, and explicit `true` should be considered separately in environments where denyRead is ineffective under the default behavior.

### Measured Results (2026-04-25, Windows 11 + Git Bash, Claude Code Desktop)

| # | Operation | Result |
|---|---|---|
| 1 | `cat .env` | Read succeeded (sandbox did not activate) |
| 2 | `grep -r FAKE_TOKEN .` | Read succeeded (sandbox did not activate) |
| 3 | `cat ~/.ssh/id_rsa` | denied (but by Claude Code's built-in credential protection layer, not the sandbox) |

Even with `sandbox.enabled: true` explicitly set, #1 and #2 still passed through. The official documentation confirms that Windows native sandbox enforcement is still "planned" (not implemented) (https://docs.claude.com/en/docs/claude-code/iam#sandbox). This setting is effective only on **macOS (Seatbelt) / Linux / WSL2 (bubblewrap)**.

### WSL2 Measured Results (2026-04-25)

| Operation | Result |
|---|---|
| `cat .env` (on the checked-out PR branch) | Read succeeded (sandbox disabled) |
| `grep -r FAKE_TOKEN .` | Read succeeded |
| Warning at `claude` startup | `⚠ Sandbox disabled: bubblewrap (bwrap) not installed, socat not installed` |

**Cause**: Claude Code's sandbox on Linux / WSL2 requires **`bubblewrap` and `socat`** as runtime dependencies, but Ubuntu / Debian-based WSL images do not include them by default.

**Fix**: In WSL environments where you want the sandbox to actually activate, do the following:

```bash
sudo apt install -y bubblewrap socat
claude  # Confirm that the warning disappears
```

After installing them, rerun the verification steps in the next section and confirm that `cat .env` and similar commands are denied.

**Detection method**: You can check sandbox status immediately after `claude --version` or by running `/sandbox` (Claude Code shows a warning). If you expect sandboxing in CI environments or Docker containers, explicitly add `apt install bubblewrap socat` to the Dockerfile / workflow.

### Verification Steps in WSL2 (Not yet performed, human task)

1. Clone this repository inside WSL2, or share the Windows-side worktree through `\\wsl$\...`
2. Start `claude` on the WSL side (Claude Code for WSL, or installed via `npm install -g`)
3. Ask it to do the following and confirm denial in each case:
   - `Run cat .env` → denied by sandbox denyRead with an error equivalent to Permission denied
   - `Run grep -r FAKE_TOKEN .` → same
   - `echo x >> ~/.claude/settings.json.sandbox-test` → write failure due to denyWrite
4. Append the measured results to the table in this section (add a new OS row)

If WSL still does not deny, one of the following is likely true: (a) the Claude Code version does not support sandboxing, (b) there is a difference in settings syntax interpretation, or (c) it is another manifestation of #32226. Record the version and the status of Issue #32226.

### Phase 2a portability fix ([Issue #83](https://github.com/suisya-systems/claude-org/issues/83))

As a mitigation for the issue where sandbox initialization silently falls back to a no-op when `bubblewrap` is not installed on WSL2 and similar environments, disabling `denyRead`/`denyWrite` for `~/.aws/**` / `~/.ssh/**`, **home dotfiles (`~/.aws` / `~/.ssh`) are treated as outside the sandbox scope** and protected with `permissions.deny` using `Read(~/.ssh/*)` / `Read(~/.aws/*)`. For portability, home dotfiles are out of sandbox scope. On the sandbox side, `denyRead` / `denyWrite` should focus on repository-local `.env` and credential files.

---

## 11. MCP Connectivity Test (Environment Verification)

**Purpose**: Verify that the `renga-peers` MCP server is connected to Claude Code, that all 14 tools are registered in the tool surface, and that tools callable without side effects respond correctly in sample invocations. Actual runtime verification of high-side-effect tools (`send_keys` / `spawn_pane` / `spawn_claude_pane` / `close_pane` / `focus_pane` / `new_tab` / `set_pane_identity`) is covered by the E2E flow in Tests 1-10, so this test is limited to registration checks for those tools.

**Steps**:

### 11-a. Registration Check (14 tools)
1. Confirm that `claude mcp list` shows `renga-peers` as Connected
2. Confirm that `renga --version` is 0.18.0 or later
3. Confirm that the following 14 tools appear in Claude Code's tool surface (matching the tool names returned by tools/list from the MCP server):
   - No side effects / light side effects: `list_panes` / `list_peers` / `set_summary` / `check_messages` / `send_message` / `poll_events` / `inspect_pane`
   - High side effects (pane / PTY operations): `spawn_pane` / `spawn_claude_pane` / `close_pane` / `focus_pane` / `new_tab` / `send_keys` / `set_pane_identity`

### 11-b. Response Check for No-Side-Effect Tools (7 tools)
Call the following 7 tools in sequence and verify that each returns a response without error:

| Tool | Example call | Expected response |
|---|---|---|
| `list_panes` | no arguments | Current pane list text |
| `list_peers` | no arguments | Peer list in the same tab, or `(no peers — …)` |
| `set_summary` | `summary="test"` | `Summary accepted (v1 stub: …)` |
| `check_messages` | no arguments | `No queued messages.` |
| `send_message` | `to_id=<self pane id or name>, message="ping"` | `Delivered to <target>.` or `(message dropped — …)` |
| `poll_events` | `timeout_ms=0` (non-blocking drain) | JSON with `{next_since, events}` |
| `inspect_pane` | `target="focused", lines=5, format="text"` | Last 5 screen lines + `structuredContent` |

### 11-c. Delegate High-Side-Effect Tools to E2E Tests
`spawn_pane` / `spawn_claude_pane` / `close_pane` / `focus_pane` / `new_tab` / `set_pane_identity` are verified in actual operation within Tests 1 / 2 / 3 / 4. `send_keys` is verified in Test 1 (Enter injection for development channel confirmation).

**Expected results**:
- 11-a: The output of `claude mcp list` includes `renga-peers: … ✓ Connected`, and all 14 tools are registered in Claude Code's tool list
- 11-b: All 7 tools respond without error; on error, text in the format `[<code>] <msg>` is returned (for example, if renga is not running, `list_panes` may return `[shutting_down]` or similar)
- 11-c: High-side-effect tools are not executed in this test and are left to E2E coverage

**Failure patterns and fixes**:
- `renga-peers` does not appear in `claude mcp list` → rerun `renga mcp install --force`
- `list_panes` returns an error → verify with `renga --version` that it is 0.14.0 or later; if older, run `npm install -g @suisya-systems/renga@0.14.0`
- `poll_events` does not return JSON → implementation mismatch in `mcp_peer/mod.rs`; verify renga version

---

## Recording Test Results

Record the results of each test in the following format:

```markdown
## Test {N}: {test name}
- Date/Time: YYYY-MM-DD HH:MM
- Result: PASS / FAIL / PARTIAL
- Issues: {describe if any}
- Action taken: {fix details}
- Retest: Required / Not required
```

Save them in the `docs/test-results/` directory.
