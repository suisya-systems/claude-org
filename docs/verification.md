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
  || echo "OK: no cd&&claude synthesis"

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
- Tools missing → `renga mcp install --force` to refresh a stale registration

This script does not require a live renga session (it is a static probe that retrieves tools/list via `renga mcp-peer` stdio).

---

## 1. Basic Startup Test

**Purpose**: Start ClaudeCode in the cloned repo and confirm that `CLAUDE.md` and skills are loaded correctly.

**Steps**:
1. `git clone` this repository to any location
2. In the clone, run `renga --layout ops` (the secretary pane launches)
3. Confirm that `mcp__renga-peers__list_panes` is reachable from the secretary's Claude Code (MCP availability check in Step 0)
4. Run `/org-start` in the secretary's Claude Code

**Expected results**:
- Because `.state/org-state.md` does not exist, the run is judged to be a first-time startup
- `mcp__renga-peers__spawn_claude_pane` opens the dispatcher pane below the secretary (no curator pane opens — it is on-demand now)
- Right after the Dispatcher starts, the "development channel confirmation prompt" is passed by injecting Enter via `mcp__renga-peers__send_keys(target=<pane>, enter=true)` (per `org-start` SKILL Block D-1)
- `curator_pane_id` / `curator_peer_id` in state.db are null via `StateWriter.CLEAR` (null is the normal state)
- A "First-time startup. What would you like to do?" message is reported

**Failure patterns and remedies**:
- `CLAUDE.md` is not loaded → check `.claude/` directory placement
- Skills are not recognized → check the frontmatter format of `.claude/skills/*/SKILL.md`
- `/org-start` does not fire → check for skill-name conflicts or description issues
- `mcp__renga-peers__list_panes` errors → rerun `renga mcp install --force`, verify registration with `claude mcp list`
- `send_keys(enter=true)` fails to inject Enter → check whether the Dispatcher pane is stuck on the "Load development channel?" prompt; press Enter manually

---

## 2. org-delegate Test (Worker dispatch)

**Purpose**: Confirm that a worker is dispatched correctly, completes the work, and reports back.

**Prerequisites**: Launched with `renga --layout ops` and `renga-peers` MCP enabled (Connected confirmed via `claude mcp list`). Test 1 has run `/org-start`.

**Steps**:
1. Ask the secretary Claude for a task (e.g., "Add a new article to the blog")
2. For a new project, confirmations about its common name / path / description appear; answer them
3. Confirm that the secretary dispatches a worker with `/org-delegate`

**Expected results**:
- The project is automatically registered in `registry/projects.md`
- The secretary sends a DELEGATE message to the dispatcher and immediately returns to dialogue with the user
- The dispatcher uses `mcp__renga-peers__spawn_claude_pane` to spawn a worker pane in the same tab (`name="worker-{task_id}"`; balanced split strategy follows `pane-layout.md`)
- The dispatcher confirms launch completion with `mcp__renga-peers__poll_events(types=["pane_started"])`
- Right after the worker starts, the "development channel confirmation prompt" is passed by `mcp__renga-peers__send_keys(target="worker-{task_id}", enter=true)` (per `org-delegate` SKILL Step 3-2)
- The dispatcher sends work instructions to the worker via `mcp__renga-peers__send_message`
- The dispatcher creates `.state/workers/worker-{id}.md`
- `.state/org-state.md` is created/updated
- Events are recorded in `.state/journal.jsonl`
- After the worker completes, the report arrives via `renga-peers` **to the secretary** (not the dispatcher)
- The secretary conveys the result to the human in business language (avoiding technical jargon)
- The secretary asks the dispatcher to close the pane (the dispatcher disposes it with `mcp__renga-peers__close_pane(target="worker-{task_id}")`)

**Verification commands**:
```bash
cat .state/org-state.md
cat .state/journal.jsonl
ls .state/workers/
cat registry/projects.md
```

Pane state is confirmed via the MCP tool:
```
mcp__renga-peers__list_panes    # Current pane list
```

**Failure patterns and remedies**:
- Pane does not open → check the current pane state with `mcp__renga-peers__list_panes`, branch on `[split_refused]` / `[pane_not_found]` in tool results per `references/renga-error-codes.md`
- Cannot communicate over renga-peers → check whether `renga-peers` is Connected via `claude mcp list`, confirm peer IDs (`worker-{task_id}` / `dispatcher` / `curator` / `secretary`) via `list_peers`
- State files are not created → review the org-delegate skill steps
- Worker does not understand the instructions → improve `instruction-template.md`
- Project name resolution does not work → revisit org-delegate Step 0

### 2.1 Balanced split scale verification (4-way / 8-way)

**Purpose**: Confirm in practice that the rect-based balanced split in org-delegate Step 3 generates the expected tree for both 4-way and 8-way parallelism without triggering `[split_refused]`.

**Prerequisites**: Test 2 passes. Terminal width `W ≥ 160 cols` (check with `tput cols`). Have the "Balanced split strategy for workers" section of `pane-layout.md` open at hand.

**Steps**:
1. Run `tput cols` and record W. If under 160, mark as not verifiable and skip or widen the terminal.
2. Ask the secretary for 8 mutually independent tasks (dummies are fine, e.g., lightweight tasks like `echo-1` through `echo-8`). For each k from 1 to 8, confirm:
   - a. The dispatcher's `mcp__renga-peers__spawn_claude_pane` result text does not include `[split_refused]`
   - b. The `target` / `direction` chosen by the Step 3-1b algorithm can be reproduced rect-based from the `list_panes` snapshot just before
   - c. Save the `mcp__renga-peers__list_panes` immediately after launch to **a separate log file (e.g., `.state/verification/balanced-split-{timestamp}.log`)**, or record the `name` / `id` of `role == "worker"` on the spot and reconcile against the `worker_spawned` events in `.state/journal.jsonl`
3. At each k, fetch the pane layout with `list_panes` and confirm by hand that the Step 3-1b algorithm (identify curator → role filter (all 4 roles candidate) → dispatcher-curator adjacency check → direction decision → `new_w / new_h` calculation → MIN_PANE constraint → SECRETARY safeguard (`new_w >= 140` and `new_h >= 30`) → **(role priority desc, metric desc, id asc) sort** *where role priority = secretary 4 > curator 3 > worker 2 > dispatcher 1*) is reproducible against the snapshot. As stated under "Balanced split strategy for workers" in `pane-layout.md`, since this is a rect-based dynamic layout, fixed grid shapes like 2×2 or 2×4 are NOT a success criterion.
4. Try a 9th dummy task and confirm that the dispatcher sends `SPLIT_CAPACITY_EXCEEDED` to the secretary via `renga-peers`. **Only the 9th worker's dispatch is aborted; the dispatcher's monitoring loop keeps running** (`spawn_claude_pane` is not issued, and the dispatcher does not exit, etc.).

> **Note**: Verification logs like `.state/verification/balanced-split-{timestamp}.log` are temporary files and not subject to commit. `.state/*` is already excluded by the existing `.gitignore`.

**Expected results**:
- Zero `[split_refused]` for k=1..8
- Layout at each k matches the Step 3-1b decision (fixed grid shapes not required; rect dynamic placement should just work)
- Candidates do not become empty within the bounds of the MIN_PANE constraint (`new_w ≥ 20` / `new_h ≥ 5`)
- Explicit escalation at k=9 (no silent failure)

**Verification commands**:
```bash
tput cols                                # Record terminal width
cat .state/journal.jsonl | grep worker_spawned
```

Pane state via MCP:
```
mcp__renga-peers__list_panes             # Snapshot at each k
```

**Failure patterns and remedies**:
- `[split_refused]` at k=4 → check the `tput cols` value. If W < 160, balanced split's requirement is unmet. Widen the terminal and retry
- `[split_refused]` already at k=3 → check whether a file-tree / preview is sitting right below the dispatcher (those subtract 20–40 cols from `W_f` while displayed)
- Layout diverges from expectation → an unclosed worker from a previous task forgot `close_pane`. Check via `list_panes` that the role=worker active count starts at 0
- Silent behavior at k=9 → the Step 3-1c (`SPLIT_CAPACITY_EXCEEDED` escalate) branch did not fire. Check that the Step 3-1b decision logic correctly returns "candidates empty"

---

## 3. org-suspend Test (Suspend)

**Purpose**: Confirm the org state is correctly persisted and all panes are halted.

**Prerequisites**: From Test 2, a worker is running (or has just completed).

**Steps**:
1. Tell the secretary Claude "Suspend"
2. Confirm that `/org-suspend` triggers

**Expected results**:
- SUSPEND messages are sent to workers via `mcp__renga-peers__send_message`
- Workers report their state back via `renga-peers`. For unresponsive workers, read screen contents with `mcp__renga-peers__inspect_pane(target="worker-{task_id}", format="text")` and infer state by combining with git status
- `.state/org-state.md` Status becomes `SUSPENDED`
- A backup is created at `.state/org-state.prev.md`
- A SHUTDOWN message is sent to all peers via `mcp__renga-peers__send_message`
- `mcp__renga-peers__poll_events(types=["pane_exited"], timeout_ms=10000)` waits for `pane_exited` events; `role == "worker"` ones are drained in bulk
- Remaining workers are closed via a fallback `mcp__renga-peers__close_pane(target="worker-{task_id}")`
- All worker panes close first, then the dispatcher, and the curator last
- The secretary reports suspend completion

**Verification commands**:
```bash
cat .state/org-state.md | head -5  # Confirm Status: SUSPENDED
cat .state/journal.jsonl | tail -1  # Confirm the suspend event
```

**Failure patterns and remedies**:
- Worker does not respond to SUSPEND → inspect screen contents with `inspect_pane` and check whether the Phase 2 scrape works
- Pane does not close → check `close_pane(target="X")` result text. `[pane_not_found]` / `[pane_vanished]` are treated as skipped
- `[last_pane]` appears → let the last secretary pane terminate naturally via self exit (org-suspend does not close it)
- State file incomplete → revisit org-suspend steps

---

## 4. org-resume Test (Resume)

**Purpose**: Confirm that after suspending and relaunching, the previous state is restored correctly.

**Prerequisites**: Suspended in Test 3.

**Steps**:
1. **Completely close** the secretary Claude's terminal
2. Relaunch in the clone with `renga --layout ops`
3. Run `/org-start`

**Expected results**:
- Block A of `/org-start` fires `spawn_claude_pane` for the dispatcher immediately after Step 0 (since the parallelization in Issue #410; does not wait for boot completion, lets Block B / C proceed in parallel; the curator is not spawned — it is on-demand now)
- Block B queries `.state/state.db` and confirms Status: SUSPENDED
- `/org-resume` Phase 1–3 (briefing / git state reconciliation / resume plan proposal) proceeds in the background while Claudes are still booting
- After the resume plan is presented, **Phase 4 worker re-dispatch waits for human approval** (does not dispatch on its own)
- Before approval, the dispatcher pane has already appeared on `mcp__renga-peers__list_panes` (pre-fired in Block A → peer registration converges in Block D; the absence of a curator pane is normal)

**Checkpoints**:
- The briefing content matches `.state/org-state.md`
- git state reconciliation is accurate
- The dispatcher pane is running (confirm with `mcp__renga-peers__list_panes`; no curator pane existing is normal)

**Failure patterns and remedies**:
- `/org-start` does not read state → revisit org-start skill Block B (loading previous state from DB)
- State is inaccurate → revisit `org-state.md` format or org-suspend's writes
- The dispatcher does not start → check org-start Block A (spawn_claude_pane) / Block D (send & peer registration)

---

## 5. Sudden Termination Test (Crash recovery)

**Purpose**: Confirm how much can be restored when the terminal is closed without running org-suspend.

**Steps**:
1. From Test 2 (worker running), close the terminal **without suspending**
2. Relaunch with `renga --layout ops`
3. Run `/org-start`

**Expected results**:
- `/org-start` detects `.state/org-state.md` and finds Status still ACTIVE
- It determines the previous session ended abruptly and checks the git state of each worker directory
- Events after the snapshot are filled in from `.state/journal.jsonl`
- The current situation is reported

**Acceptable degradation**:
- Detailed self-reported progress from workers is lost
- Information after the last entry in journal.jsonl is lost
- Uncommitted git work may have unclear state
- If the Dispatcher's `poll_events` cursor (`.state/dispatcher-event-cursor.txt`) is lost, the last ~5 seconds of events may be missed, but recoverable via `list_panes` reconciliation

**Failure patterns and remedies**:
- `org-state.md` too stale → increase periodic snapshot frequency (strengthen progress tracking in org-delegate)
- `journal.jsonl` missing → check the journaling implementation

---

## 6. org-retro Test (Retrospective)

**Purpose**: Confirm that learnings are correctly recorded after task completion.

**Steps**:
1. A worker completes some task
2. Confirm the secretary runs `/org-retro`

**Expected results**:
- If there are reusable insights, `knowledge/raw/YYYY-MM-DD-{topic}.md` is created
- The format follows "fact → judgment → rationale → applicable context"
- If judged unnecessary, nothing is created (correct judgment)

**Verification commands**:
```bash
ls knowledge/raw/
cat knowledge/raw/*.md  # Check format
```

---

## 7. org-curate Test (Knowledge curation + self-growth loop)

**Purpose**: Confirm that the curator organizes knowledge and can propose improvements.

**Prerequisites**: `knowledge/raw/` contains 5+ unorganized files.

**Steps**:
1. Create 5+ dummy knowledge files in `knowledge/raw/` for testing
2. Run `py -3 tools/check_curate_threshold.py` and confirm exit 10 with `raw_threshold` set in `reasons`
3. Run `/org-curate` manually (or close a worker and wait for the dispatcher-driven on-demand launch)

**Expected results**:
- Raw files are classified by theme
- Theme files are created in `knowledge/curated/{theme}.md`
- The processed raw files are moved to `knowledge/raw/archive/` and get `<!-- curated -->` prepended at the top
- If there are improvement proposals, the secretary is notified via `renga-peers`
- Finally, `CURATE_DONE` is sent via direct send to the dispatcher (when a dispatcher is running)

**Verification commands**:
```bash
# POSIX (bash)
python3 tools/check_curate_threshold.py; echo "exit=$?"
# Windows (PowerShell — $? is a boolean, so use $LASTEXITCODE)
py -3 tools/check_curate_threshold.py; echo "exit=$LASTEXITCODE"
ls knowledge/curated/
cat knowledge/curated/*.md
head -1 knowledge/raw/archive/*.md  # Check <!-- curated --> marker
```

**Self-growth check**:
- Improvement proposals are concrete
- Proposals are not auto-executed without human approval

---

## 8. Dispatcher / On-Demand Curator Test

**Purpose**: Confirm that the dispatcher starts correctly, and that the curator is launched on demand when the threshold check fires at worker close.

**Steps**:
1. Run `/org-start` and confirm the dispatcher pane launches (the curator is not launched)
2. Confirm the dispatcher receives a role instruction via `mcp__renga-peers__send_message`
3. With fewer files than the threshold in `knowledge/raw/`, close a worker and confirm the curator is **not** launched (`check_curate_threshold.py` exit 0)
4. Increase past the threshold, close a worker, and confirm: curator pane launches temporarily → runs `/org-curate` once → pane is closed after `CURATE_DONE` is received

**Expected results**:
- After `/org-start`, the dispatcher opens below the secretary (confirm with `mcp__renga-peers__list_panes`; there is no curator pane)
- The dispatcher waits for DELEGATE messages
- The threshold check runs only at worker close (`.dispatcher/references/pane-close.md` Step 5)
- Below threshold, the curator is not launched; at/above threshold, it launches temporarily → closes after completion

**Failure patterns and remedies**:
- Panes open but no instructions arrive → adjust the renga-peers peer-discovery timing (retry `list_peers`, extend the pane_started event wait)
- Dispatcher does not react to DELEGATE → review the initial message content sent to the dispatcher
- The curator is not launched → run `py -3 tools/check_curate_threshold.py` manually and inspect the exit code / reasons
- The curator pane lingers → check whether `.state/dispatcher/curate-inflight.json` exists and whether the monitoring loop's Step 5.3 (CURATE_* receipt / 20-min timeout management) is running, and that the CURATE_* direct send arrived

---

## 9. org-dashboard Test (Dashboard)

**Purpose**: Confirm that the dashboard live server launches and browser display works correctly.

**Prerequisites**: Test 2 worker dispatch and project registration are complete.

**Steps**:
1. Tell the secretary "Show me the dashboard"
2. Confirm `/org-dashboard` fires

**Expected results**:
- `dashboard/server.py` launches and serves at `http://localhost:8099`
- The browser opens `http://localhost:8099`
- Project list, work status, activity, and knowledge are displayed
- `/api/state` response matches actual state

**Failure patterns and remedies**:
- Server does not start → check `dashboard/server.py` error output
- Browser shows no data → confirm `http://localhost:8099` responds via `curl`
- Data is not updated → check SSE connection state (`/api/events`)

---

## 10. E2E Test (Full cycle)

**Purpose**: Confirm the full cycle of start → work → suspend → resume → knowledge curation.

**Steps**:
1. Launch ClaudeCode in the clone (`renga --layout ops`)
2. Run `/org-start` (initial startup)
3. Request 3 tasks (ones that trigger worker dispatch)
4. Confirm a retrospective is recorded after each task
5. Say "Show me the dashboard" and verify the overall view
6. Suspend with `/org-suspend`
7. Close the terminal completely
8. Relaunch → `/org-start` → previous state is reported
9. Approve resume → workers are re-dispatched
10. When `knowledge/raw/` reaches the threshold, confirm curation runs
11. git commit → push the curated knowledge

**Success criteria**:
- All steps complete without human intervention (other than instructions and approvals)
- No state loss
- Knowledge is accumulated and organized
- Dashboard provides an overall view

---

## 10.1. sandbox.denyRead / denyWrite Live Verification (Phase 2a, Issue #79)

**Purpose**: Confirm that `sandbox.filesystem.denyRead` / `denyWrite` in `.claude/settings.json` works as expected in Windows + Git Bash, and that secret files such as `.env` cannot be read via Claude Code's Bash tool.

**Prerequisites**:
- This repository is cloned and Claude Code can launch
- A dummy `.env` (e.g., `FAKE_TOKEN=dummy-not-a-real-secret`) is prepared directly under the verification target repo (covered by `.gitignore` so not committed)
- A known bug [anthropics/claude-code#32226](https://github.com/anthropics/claude-code/issues/32226) reports cases where denyRead does not work as expected, so **always confirm behavior in practice**
- **Pre-apply personal sandbox reinforcement (Issue #429 Task B/C + Issue #433)**: For Step 3 (`~/.ssh/id_rsa` read) and Step 4 (`~/.claude/settings.json` write), both go through deny entries that have **been moved to the personal `~/.claude/settings.json`**. Before verification, run `python tools/org_setup_prune.py --user-common-sandbox` once and confirm the entries have been merged into the personal `~/.claude/settings.json`'s `sandbox.filesystem.denyRead` / `denyWrite`, then perform Steps 1–4. Without running it, the shared settings side has no entry and nothing is denied, producing a false "fail" verdict

**Steps**:
1. Ask the secretary Claude to run `cat .env` (via Bash tool)
2. Ask for a command that reads `.env` such as `grep -r FAKE_TOKEN .`
3. Ask for a command that reads `~/.ssh/id_rsa` (if it exists)
4. Ask for a command that attempts to write `~/.claude/settings.json` (e.g., `echo x >> ~/.claude/settings.json`)

**Expected results**:
- Steps 1–2: denied (equivalent to `Permission denied`) in the Bash subprocess via the shared `.claude/settings.json`'s `sandbox.filesystem.denyRead` (`.env` / `**/credentials*` etc.)
- Step 3: denied in the Bash subprocess by the personal `~/.claude/settings.json`'s `sandbox.filesystem.denyRead` (`~/.ssh` etc., already merged per the prerequisite above). In environments where it is not merged, Claude Code's built-in credential protection layer may catch it, but here we verify Layer 3 (sandbox) individually
- Step 4: write fails by the personal `~/.claude/settings.json`'s `sandbox.filesystem.denyWrite` (`~/.claude/settings.json`, already merged per the prerequisite, Issue #433)

**Failure patterns and remedies**:
- `.env` contents become readable → possibly a Claude Code bug. Record the version and `claude --version`, check the status of Issue #32226. As a stopgap, add `Read(./.env)` to `permissions.deny` (close Claude Code's Read-tool route)
- Glob `**/credentials*` does not work on Windows → possible forward/backward slash differences. Adjust the glob to `./credentials*` etc. and retry
- The sandbox itself does not fire → Claude Code's `sandbox.enabled` default may be OFF. Check the current default in the official docs

**Note**: `sandbox.enabled` is **explicitly set to `true` in the current shared [`.claude/settings.json`](../.claude/settings.json)** (since the initial v0.1.0 commit). In an older version of this section it was left implicit, but the shared settings later explicitly set it to `true`. In environments affected by known bug #32226, consider temporarily falling back to `false` as a judgment lever; keep in mind that the current default policy is explicit `true`.

### Measured results (2026-04-25, Windows 11 + Git Bash, Claude Code Desktop)

| # | Operation | Result |
|---|---|---|
| 1 | `cat .env` | Readable (sandbox did not fire) |
| 2 | `grep -r FAKE_TOKEN .` | Readable (sandbox did not fire) |
| 3 | `cat ~/.ssh/id_rsa` | denied (※ by Claude Code's built-in credential protection layer, NOT by sandbox) |

Even with `sandbox.enabled: true` explicitly set, #1 #2 pass through. Confirmed in the official docs that Windows native sandbox enforcement is "planned" (not yet implemented): https://docs.claude.com/en/docs/claude-code/iam#sandbox. This setting only takes effect on **macOS (Seatbelt) / Linux / WSL2 (bubblewrap)**.

### WSL2 measured results (2026-04-25)

| Operation | Result |
|---|---|
| `cat .env` (on PR branch checkout) | Readable (sandbox disabled) |
| `grep -r FAKE_TOKEN .` | Readable |
| Warning at `claude` startup | `⚠ Sandbox disabled: bubblewrap (bwrap) not installed, socat not installed` |

**Cause**: Claude Code's sandbox requires **`bubblewrap` and `socat`** as runtime dependencies on Linux / WSL2, but Ubuntu / Debian-based WSL images do not include them by default.

**Remedy**: To actually activate the sandbox in WSL, do the following:

```bash
sudo apt install -y bubblewrap socat
claude  # Confirm the warning disappears
```

After this, re-confirm via the next section's verification steps that `cat .env` etc. are denied.

**Detection procedure**: The sandbox state can be checked right after `claude --version` / by running `/sandbox` (Claude Code displays a warning). In CI environments or Docker containers where the sandbox is expected, explicitly add `apt install bubblewrap socat` to the Dockerfile / workflow.

### WSL2 verification procedure (not yet performed, human task)

1. Clone this repo inside WSL2 or share a Windows-side worktree via `\\wsl$\...`
2. On the WSL side, launch `claude` (the wsl version of Claude Code or installed via `npm install -g`)
3. **Apply personal sandbox reinforcement** (required for Issue #429 Task B/C + Issue #433): run `python tools/org_setup_prune.py --user-common-sandbox` once and merge entries into the personal `~/.claude/settings.json`'s `sandbox.filesystem.denyRead` / `denyWrite`
4. **Back up the personal `~/.claude/settings.json`** (to avoid corruption if deny does not fire): `cp ~/.claude/settings.json ~/.claude/settings.json.preflight-backup`
5. Request each of the following and confirm deny:
   - "Run `cat .env`" → equivalent to Permission denied via the shared settings' sandbox denyRead
   - "Run `grep -r FAKE_TOKEN .`" → same
   - `echo x >> ~/.claude/settings.json` → write fails by the personal settings' denyWrite (the exact-match denyWrite added in Issue #433). **If deny does not fire**, `x` will be appended to the end of the file; restore with `cp ~/.claude/settings.json.preflight-backup ~/.claude/settings.json`
6. Record measured results in this section's table (add an OS row)

If deny does not fire on WSL, then one of: (a) the Claude Code version does not support sandbox, (b) settings syntax interpretation differs, (c) a different symptom of #32226, (d) `--user-common-sandbox` merge has not taken effect. Record the version, Issue #32226 status, and the `sandbox.filesystem.denyWrite` content in `~/.claude/settings.json`.

### Phase 2a portability fix ([Issue #83](https://github.com/suisya-systems/systems/claude-org-ja/issues/83))

To address the issue where, when `bubblewrap` is not installed on WSL2 etc., sandbox init silently no-ops and the denyRead/denyWrite of `~/.aws/**` / `~/.ssh/**` are disabled, **home dotfiles (`~/.aws` / `~/.ssh`) are placed out of sandbox scope** and protected via `permissions.deny`'s `Read(~/.ssh/*)` / `Read(~/.aws/*)`. For portability, home dotfiles are out of sandbox scope. The sandbox-side `denyRead` / `denyWrite` is focused on repo-local `.env` / credential files.

#### Addendum: Withdrawal of the Phase 2a premise (Issue #429 Task A investigation conclusion)

**Premise withdrawn**: The above premise — "protect via `permissions.deny`'s `Read(...)`" — **diverges from the documented behavior of current Claude Code**. Migration to `permissions.deny` does not hold as a portability fix.

**Evidence (Claude Code official docs)**: <https://code.claude.com/docs/en/settings>, `sandbox.filesystem.denyRead` description:

> Paths where sandboxed commands cannot read. Arrays are merged across all settings scopes. **Also merged with paths from `Read(...)` deny permission rules.**

That is, when you write `Read(~/.aws/*)` in `permissions.deny`, Claude Code adds the same path to the sandbox's effective denyRead set even without explicitly writing it in `sandbox.filesystem.denyRead`. **The merge behavior is the same whether you write it in shared settings or personal settings**, and migrating to `permissions.deny` cannot avoid sandbox bootstrap failures (e.g., environments where `~/.aws` is a symlink to `/mnt/c/...` on WSL2 + bwrap and `bwrap: Can't create file at /home/<user>/.aws/config` is emitted).

**Practical portability fix (choose one)**:

1. **In the affected environment, move/remove the symlink and recreate the real directory with `mkdir -p`**. A single `mkdir -p` does not replace an existing symlink with a real directory, so explicit replacement like `rm <link> && mkdir -p <dir>` is required.
2. **In that environment, exclude `Read(~/.aws/*)` / `Read(~/.ssh/*)` from both shared and personal settings**. A workaround to avoid bwrap bootstrap failure. **However, this choice intentionally weakens Claude-side credential read protection, with the following residual risks**: (a) Claude Code runs with the same user privileges, so OS-level file permissions do not stop the Claude process itself; (b) claude-org-runtime's WSL Layer 3 suppression (§10.2 Phase 3 case E) drops escaping Layer 3 entries **at emit time**, it does not strengthen deny; (c) `--user-common-sandbox` also skips the same candidates. What remains is Claude Code's built-in credential protection layer (for specific paths like `~/.ssh/id_*`) and Layer 4 hook / role contract only; there is no guarantee that `cat ~/.aws/credentials` is fully stopped. In symlink-escape environments, choice 1 (real directory) is preferable; choice 2 is positioned as a compromise when that is operationally impossible.

claude-org-ja itself removed `Read(~/.ssh/*)` / `Read(~/.aws/*)` / `~/.config/gh/hosts.yml` from the shared `.claude/settings.json` in Issue #429 Task C (the same PR as this addendum) (= adopting choice 2 above). To deny actually existing (= non-symlink) sensitive directories per personal environment, run `python tools/org_setup_prune.py --user-common-sandbox` once (introduced in Issue #429 Task B); directory-level deny is merged into `~/.claude/settings.json`'s `sandbox.filesystem.denyRead` (symlink-escape candidates are auto-skipped). See the "Personal common sandbox denyRead / denyWrite reinforcement (`--user-common-sandbox`)" section of [`.claude/skills/org-setup/references/permissions.md`](../.claude/skills/org-setup/references/permissions.md) for details.

**Optional upstream enhancement request**: The portability issue is structurally resolved if Claude Code adds an improvement like "when merging `Read(...)` / `Edit(...)` `permissions.deny` into `sandbox.filesystem.denyRead`, exclude paths whose realpath escapes `sandbox_read_roots`". Out of scope for this task.

The full investigation log is in [the comment on Issue #429](https://github.com/suisya-systems/claude-org-ja/issues/429#issuecomment-4419741705).

#### Addendum 2: denyWrite merge semantics confirmation and migration (Issue #433)

**Premise check**: Claude Code's official docs at <https://code.claude.com/docs/en/settings>, `sandbox.filesystem.denyWrite` description (as of 2026-05):

> Paths where sandboxed commands cannot write. Arrays are merged across all settings scopes. **Also merged with paths from `Edit(...)` deny permission rules.**

So denyWrite, symmetric with denyRead, (a) merges arrays across multiple settings scopes (user / shared / project), and (b) adds Layer 2 (`permissions.deny`'s `Edit(...)`) paths to the effective set. Note: "only `Edit(...)`, not `Write(...)` is mentioned" — `Write(...)` is also a new-file write tool, but it is not explicitly listed in the official docs (live verification of `Write(...)` → `denyWrite` merge is out of scope for this PR; for now interpret per docs as only `Edit(...)` auto-mirroring to Layer 3).

**Migration decision**: In Issue #429 Task C and Issue #433, **denyWrite of `~/.claude/settings.json` was also migrated from the shared `.claude/settings.json` to the personal `~/.claude/settings.json` side** (symmetric with Task C's denyRead migration, extending the Task B `--user-common-sandbox` flag to handle both denyRead and denyWrite under a single flag). Reasons:

1. **Per-person opt-out possibility**: If you put `denyWrite: ["~/.claude/settings.json"]` in shared settings, deny applies to the home paths of every user who pulls the repo. Moving to personal settings lets each operator revoke it by editing their own `~/.claude/settings.json`, making it easier to align role contracts with personal operation.
2. **Storage location matches intent**: The intent "protect the personal `~/.claude/settings.json` from sandbox subprocess writes" physically matches the location where the deny itself is written (personal `~/.claude/settings.json`). In shared settings, "who is protecting whose home dir" tends to be opaque.
3. **Maintaining defense-in-depth**: Per the official docs' merge rules, Layer 2 (`permissions.deny Edit(~/.claude/settings.json)`) and Layer 3 (`sandbox.filesystem.denyWrite`) converge in the effective set. Even with Layer 3 moved to the personal side, Layer 2 can still be declared on the shared settings side if needed, so defense-in-depth is reconstructible idempotently.

**Decision about preventive deny (= merge even when file does not exist)**: `~/.claude/settings.json` is created by a fresh-install Claude Code at first startup. If you run `--user-common-sandbox` **before `~/.claude/settings.json` is created** and skip the entry, there is a time window between the first Claude Code launch and the next `--user-common-sandbox` run during which bwrap subprocess writes pass through. To avoid this, denyWrite candidates are **merged unconditionally without existence checks** (asymmetric with denyRead, which is directory-scoped and risks bwrap bootstrap failures, so existence-checked).

**Residual verification (live, not yet performed)**: The current table in §10.1 has only 2 rows — Windows native (sandbox not implemented, `cat .env` etc. pass through) and WSL2 (`bubblewrap` not installed, sandbox disabled). Live denyWrite confirmation on macOS / Linux / WSL2 after installing bubblewrap is **not yet performed** at this PR's time. Confirming the Issue #433 happy path (`echo x >> ~/.claude/settings.json` being denied by the personal `~/.claude/settings.json`'s `denyWrite` after applying `--user-common-sandbox`) remains as a human task at Step 4 of §10.1; record the result by appending to the table in this section. Deny non-firing on Windows native is already recorded in §10.1; no additional verification is needed in this addendum (because the sandbox itself is not implemented there).

**Implementation**: `tools/org_setup_prune.py`'s `merge_user_common_sandbox_denywrite` / `USER_COMMON_SANDBOX_DENYWRITE_CANDIDATES`, and `tools/test_org_setup_prune.py`'s `MergeUserCommonSandboxDenywriteTests` and the denyWrite-related cases in `UserCommonSandboxEndToEndTests`.

---

## 10.2. Phase 3 sandbox case E live verification (WSL Layer 3 suppression, runtime 0.1.4+)

**Purpose**: Confirm that the WSL Layer 3 suppression introduced in runtime 0.1.4 fires as expected. Specifically, that when the worker_dir's realpath escapes the sandbox read roots (typical: WSL's `/home/user/...` resolves to `/mnt/c/...`), the corresponding `sandbox.filesystem.denyRead` / `denyWrite` entries are automatically dropped from the rendered `settings.local.json`.

**Prerequisites**: `claude-org-runtime>=0.1.4` is installed (via `pyproject.toml` / `requirements.txt`).

**Steps**:

1. Prepare a fresh worker dir in a WSL environment and run:
   ```bash
   claude-org-runtime settings show \
       --explain --json \
       --role default \
       --worker-dir <worker_dir> \
       --claude-org-path <ja root>
   ```
2. Confirm in the output JSON that `wsl_detected` is `true` and `sandbox_read_roots` contains `<worker_dir>` + `additionalDirectories`.
3. Confirm that the `suppressions` array contains at least one entry with the following fields:
   - `layer == 'sandbox.filesystem.denyRead'` or `'sandbox.filesystem.denyWrite'`
   - `reason == 'realpath escapes sandbox read roots'`
   - `realpath`, `sandbox_read_roots`

   On WSL, typically Layer 3 entries like `~/.aws/*` and `~/.ssh/*` are suppressed by realpath escape.
4. Separately generate the rendered `settings.local.json` and confirm that the entries in `suppressions` are absent from `sandbox.filesystem.denyRead` / `denyWrite`. Note that after Issue #429 Task C, this repo's shared `.claude/settings.json` **does not even contain** `Read(~/.aws/*)` / `Read(~/.ssh/*)` (see §10.1 Addendum, Phase 2a's Layer 2 mirror premise has been withdrawn). Layer 2 fallback is evaluated only via worker_role templates (`tools/org_extension_schema.json`'s `worker_roles.*`) or the personal `~/.claude/settings.json`. The runtime-side contract "Layer 2 is never suppressed" itself stands, and `permissions.deny` emitted by worker_role remains independent of §1.3 case E.
5. In a non-WSL Linux environment (GitHub Actions `ubuntu-latest` etc.), run `settings show --explain` similarly and confirm `wsl_detected=false` / `suppressions=[]` / Layer 3 entries remain in the rendered settings.

**Expected results and judgment**:
- On WSL, Layer 3 is adaptively dropped, and worker_role's Layer 2 mirror (on the emit side) is always kept.
- Outside WSL, Layer 3 remains as is.
- worker_role's `permissions.deny` is intact (note that the shared `.claude/settings.json` no longer has `Read(~/.aws/*)` etc. after §10.1 Addendum).

**Failure isolation**:
- (a) `wsl_detected` is `false` but `/mnt/c` appears in realpath → bug in the `/proc/version` / `osrelease` detection logic (runtime issue).
- (b) `suppressions` is empty but entries are missing from rendered settings → `render_role` and `show` sources diverge.
- (c) Layer 2 entries that worker_role should emit are missing → runtime regression, escalate to the runtime side immediately (the removal from the shared `.claude/settings.json` side is intentional per Issue #429 Task C; do not confuse the two).

**Relationship to §Phase 2a portability fix (§10.1)**: §10.1 Addendum (Issue #429 Task A investigation conclusion) confirmed that "`permissions.deny Read(...)` is merged on the Claude Code side into `sandbox.filesystem.denyRead` (regardless of shared / personal settings)", which led to withdrawing the Phase 2a premise that "migration to permissions.deny is a portability fix". Per the new policy, `Read(~/.ssh/*)` / `Read(~/.aws/*)` are removed from the shared `.claude/settings.json`, and per-personal-environment directory-level deny is reinforced into the personal `~/.claude/settings.json` via `python tools/org_setup_prune.py --user-common-sandbox` (symlink-escape auto-skip). Phase 3 case E (the WSL Layer 3 suppression on the runtime side) remains valid as worker_role's generator behavior, and §10.2 here stands independently as runtime suppression verification for WSL environments.

**Reference**:
- runtime 0.1.4 release notes: https://github.com/suisya-systems/claude-org-runtime/releases/tag/v0.1.4
- claude-org-runtime#10 (Phase 3 case E MVP)

---

## 11. MCP Connectivity Test (Environment check)

**Purpose**: Confirm that the `renga-peers` MCP server is connected to Claude Code, all 14 tools are registered on the tool surface, and verify sample-call responses for side-effect-free tools. The actual behavior of side-effectful tools (`send_keys` / `spawn_pane` / `spawn_claude_pane` / `close_pane` / `focus_pane` / `new_tab` / `set_pane_identity`) is covered by the Test 1–10 E2E flows, so this test only does registration confirmation.

**Steps**:

### 11-a. Registration check (14 tools)
1. Confirm that `claude mcp list` shows `renga-peers` as Connected
2. Confirm that `renga --version` is 0.18.0 or higher
3. Confirm that the following 14 tools appear on the Claude Code tool surface (matching the tool names returned by the MCP server's tools/list):
   - Side-effect-free / light side-effects: `list_panes` / `list_peers` / `set_summary` / `check_messages` / `send_message` / `poll_events` / `inspect_pane`
   - Heavy side-effects (pane / PTY operations): `spawn_pane` / `spawn_claude_pane` / `close_pane` / `focus_pane` / `new_tab` / `send_keys` / `set_pane_identity`

### 11-b. Response check for side-effect-free tools (7 tools)
Call each of the following 7 tools in turn and confirm a response is returned without error:

| Tool | Example call | Expected response |
|---|---|---|
| `list_panes` | no args | Current pane list as text |
| `list_peers` | no args | Peer list in the same tab, or `(no peers — …)` |
| `set_summary` | `summary="test"` | `Summary accepted (v1 stub: …)` |
| `check_messages` | no args | `No queued messages.` |
| `send_message` | `to_id=<self pane id or name>, message="ping"` | `Delivered to <target>.` or `(message dropped — …)` |
| `poll_events` | `timeout_ms=0` (non-blocking drain) | JSON of `{next_since, events}` |
| `inspect_pane` | `target="focused", lines=5, format="text"` | Last 5 lines of the screen + `structuredContent` |

### 11-c. Defer side-effectful tools to E2E
`spawn_pane` / `spawn_claude_pane` / `close_pane` / `focus_pane` / `new_tab` / `set_pane_identity` are confirmed in Tests 1 / 2 / 3 / 4. `send_keys` is confirmed in Test 1 (Enter injection for the development channel prompt).

**Expected results**:
- 11-a: `claude mcp list` output contains `renga-peers: … ✓ Connected`, and all 14 tools are registered in the Claude Code tool list
- 11-b: All 7 tools respond without error; on error, text in the format `[<code>] <msg>` is returned (e.g., `[shutting_down]` from `list_panes` when renga is not running)
- 11-c: Side-effectful tools are not run in this test; coverage is delegated to E2E

**Failure patterns and remedies**:
- `renga-peers` does not appear in `claude mcp list` → rerun `renga mcp install --force`
- `list_panes` errors → check `renga --version` for 0.14.0+; if older, `npm install -g @suisya-systems/renga@0.14.0`
- `poll_events` does not return JSON → mismatch in `mcp_peer/mod.rs` implementation; check renga version

---

## 11.1. attention watcher verification (scan --dry-run)

**Purpose**: Confirm that `claude-org-runtime attention scan` extracts attention events from `.state/state.db` and `.state/pending_decisions.json`, and that the ja-default Japanese templates ([`tools/templates/attention.example.json`](../tools/templates/attention.example.json)) load as the runtime config. Since `watch` is a long-running command that is hard to run in CI, the proper verification is to take a one-shot extraction in JSON via `scan --dry-run --json` and inspect the shape and severity classification. See [`docs/operations/attention-watch.md`](operations/attention-watch.md) for details.

**Prerequisites**:
- `claude-org-runtime` is installed (`pip install -e .` so the `claude-org-runtime` CLI is on `PATH`)
- `/org-start` has been run at this repo root, or `.state/state.db` is initialized via `python -m tools.state_db.importer --db .state/state.db --rebuild --no-strict`

**Steps**:

1. Place the ja-default config under `.state/` (since `.state/` is gitignored, copy from the tracked example; on a fresh clone the directory does not exist yet, so combine with `mkdir -p .state`):
   ```bash
   mkdir -p .state
   cp tools/templates/attention.example.json .state/attention.json
   ```
2. Run a dry-run scan with JSON output:
   ```bash
   claude-org-runtime attention scan --state-dir .state --config .state/attention.json --dry-run --json
   ```
3. Check the output JSON. Each element of the `events` array should have:
   - `key`: a stable ID for dedup (`event:<events.id>` or `pending:<task_id>:<kind>`)
   - `kind`: one of the runtime 0.1.x classification kinds (`approval_blocked` / `relay_gap_suspected` / `silent_worker_output` / `ci_failed` / `pending_decision` / `user_reply_not_forwarded` / `pane_silent` / `pane_crashed` / `worker_stalled` / `worker_not_reported` / `worker_error` / `worker_completed` / `pr_merged` / `secretary_awaiting_user`)
   - `severity`: `urgent` or `normal`
   - `title` / `body`: strings with the ja config template applied (Japanese)
   - Optionally `task_id` / `worker` / `created_at`

**Expected results**:

- Exit code 0 with JSON returned. If `.state/state.db` has a corresponding `notify_sent kind=approval_blocked` event, it appears as `kind: "approval_blocked"`, `severity: "urgent"`
- If `ci_completed` has `status` of `failed` / `canceled` / `incomplete`, it appears as `kind: "ci_failed"`, `severity: "urgent"`
- `worker_completed` / `pr_merged` are `severity: "normal"`; the other classifications above are `urgent` in the ja default
- If a pending decision exceeds `pending_decision_min` (default 15 min), it appears as `kind: "pending_decision"`, `severity: "urgent"`
- A `notify_sent kind=awaiting_user` (the 4 gates where the Secretary stops while awaiting the user's decision) appears as `kind: "secretary_awaiting_user"`, `severity: "urgent"`
- `title` / `body` are Japanese strings from the ja default, with placeholders like `{worker}` / `{task_id}` / `{pr}` / `{status}` resolved
- Because `--dry-run` is specified, no desktop notification subprocess is invoked (nothing appears in macOS notification center, no `notify-send` on Linux)
- Removing `--config .state/attention.json` and rerunning yields the neutral English defaults from runtime in title / body (corroborating that the ja override is effective)

**Failure patterns and remedies**:

- `command not found: claude-org-runtime` → `pip install -e .` not run. Run `pip install -e .` at the project root (the runtime is installed via the dependency in `pyproject.toml`)
- `.state/state.db: no such file` → initialize via `python -m tools.state_db.importer --db .state/state.db --rebuild --no-strict`
- `events` array is empty → `.state/state.db` has no classified events (a normal case immediately after clean init). Inject something like `tools/journal_append.sh notify_sent kind=approval_blocked task=test-1 worker=worker-test-1` manually and rescan
- `title` / `body` still contain placeholders like `{worker}` → the template in `tools/templates/attention.example.json` may have added a placeholder unsupported by runtime. The allowlist is 6 types: `{task_id} {worker} {kind} {status} {pr} {summary}` ([`docs/design/attention-notification.md`](design/attention-notification.md) §6)
- `title` / `body` are still in English → `.state/attention.json` is not being read. Pass `--config` with an absolute path or confirm the file exists at `.state/attention.json`
- "fallback to terminal bell" appears in human-readable output without `--json` → backend has crashed. With `--dry-run`, the notification subprocess itself is not invoked, so this fallback log is not expected. If it appears, check the runtime version

**Note**: Live `watch` verification is not yet included in this repo's automated verification. `tests/fixtures/attention/*` and integration tests will be added in a separate Issue (#445). This section minimally guarantees that the path through which ja templates resolve in runtime is intact, via `scan --dry-run`.

---

<a id="security-matrix"></a>

## 12. Attack Vector × Defense Layer Matrix

Based on this repo's own `.claude/settings.json` (for secretary/curator, `auto` mode) and `.githooks/pre-commit`, a table of major attack vectors and how each layer handles them. The worker role templates ([`tools/org_extension_schema.json`](../tools/org_extension_schema.json)'s `worker_roles.{default,claude-org-self-edit}` is the SoT; `.claude/skills/org-setup/references/permissions.md` is a reference doc for the same SoT) also deploy `check-worker-boundary.sh` / `block-org-structure.sh` / `block-git-push.sh` plus `block-no-verify.sh` / `block-dangerous-git.sh`. `permissions.deny`, in addition to the `git push` family and `rm -r` / `rm -rf`, rejects `git fetch` / `git pull` / `git remote add|set-url|remove` / `git submodule` / `git lfs` / `git gc` / `git filter-branch` / `git filter-repo` / `git replace` / `git update-ref` / `git config --global|--local|--worktree` / `git reflog expire|delete` / `git worktree*` including their `-C` variants. Direct blocking of `--no-verify` / `git reset --hard` / `git branch -D` family is active on the secretary / curator and also on the worker side (dispatcher is managed separately via its own hook set under `.dispatcher/`).

Legend: ✅ block / ⚠️ partial or conditional / — out of scope / ➖ not deployed.

| Attack vector | `permissions.deny` | PreToolUse hook | sandbox | pre-commit |
|---|---|---|---|---|
| `git commit --no-verify` direct (secretary/curator) | ✅ | ✅ (`block-no-verify.sh`) | — | — |
| `eval "git commit --no-verify"` / `bash -c "..."` | — | ✅ Phase 2a [#79](https://github.com/suisya-systems/claude-org-ja/issues/79): explicit parsing via `unwrap_eval_and_bashc` | — | — |
| `VAR=$(printf -- '--no-verify'); git commit $VAR` | — | ✅ assignment collection + `flatten_substitutions` | — | — |
| `git push --force` / `git reset --hard` / `git branch -D` (secretary/curator) | ✅ | ✅ (`block-dangerous-git.sh`) | — | — |
| `cat .env` / credential read (via Bash) | — | — | ⚠️ macOS (Seatbelt) / Linux / WSL2 (`bubblewrap`+`socat`) only. **Windows native is unimplemented on the Claude Code side and passes through** ([§10.1](#101-sandboxdenyread--denywrite-live-verification-phase-2a-issue-79)) | — |
| `cat ~/.ssh/<key>` / `cat ~/.aws/credentials` (Bash subprocess read of home dotfiles) | — (removed from shared settings in Issue #429 Task C) | — | ⚠️ Running `python tools/org_setup_prune.py --user-common-sandbox` once on the personal `~/.claude/settings.json` merges directory-level deny into `sandbox.filesystem.denyRead` (symlink-escape auto-skipped; Issue #429 Task B). **Protection only for Bash subprocess (sandboxed commands)**: `sandbox.filesystem.denyRead` stops sandbox-routed syscalls but not the Read tool itself | — |
| `echo x >> ~/.claude/settings.json` (Bash subprocess overwrite of personal Claude settings) | — (removed from shared settings' `denyWrite` and moved to personal settings in Issue #433) | — | ⚠️ Running `python tools/org_setup_prune.py --user-common-sandbox` once on the personal `~/.claude/settings.json` merges `~/.claude/settings.json` into `sandbox.filesystem.denyWrite` (preventive deny, applied even before the file exists; Issue #433). **Protection only for Bash subprocess (sandboxed commands)**: `Edit(...)` via the Read tool is suppressed by another layer (`permissions.deny`) | — |
| Home dotfile read via `Read tool` (`Read(~/.ssh/<key>)` etc.) | — (removed from shared settings in Issue #429 Task C) | — | — (`sandbox.filesystem.denyRead` does not reverse-merge into the Read tool. Claude Code official docs only specify one-way `Read(...)` deny → `denyRead` merge) | — |
| Secret leakage into staged diff | — | — | — | ✅ ([.githooks/pre-commit](../.githooks/pre-commit)) |
| Bypass via shell function (`f(){ git commit --no-verify; }; f`) | — | ➖ static analysis of function definitions is not supported | — | — |

### Residual risk

- **Routing via shell function definitions**: Forbidden commands hidden in a function body cannot be detected by the PreToolUse hook's static analysis (the shell-layer static analysis explored in Phase 2c was abandoned for false-positive rate and maintenance cost reasons). The sandbox's `denyWrite` also does not stop repo side-effects like `git commit`. Defense-in-depth for home dotfiles was **migrated from the shared `.claude/settings.json` to the personal `~/.claude/settings.json`** by [Issue #429](https://github.com/suisya-systems/claude-org-ja/issues/429) Task B/C (denyRead candidates) and [Issue #433](https://github.com/suisya-systems/claude-org-ja/issues/433) (`denyWrite` of `~/.claude/settings.json`). Running `python tools/org_setup_prune.py --user-common-sandbox` once simultaneously merges, per personal environment, directory-level `sandbox.filesystem.denyRead` (symlink-escape auto-skipped) and file-level `sandbox.filesystem.denyWrite` (preventive, applied even before the file exists). **This reinforcement only stops reads / writes via sandboxed Bash subprocess; it does not stop `Read(~/.aws/<file>)` via Read tool or `Edit(~/.claude/settings.json)` via Edit tool** (Claude Code official docs only define one-way merge: `Read(...)` deny → `denyRead`, `Edit(...)` deny → `denyWrite`). The Read / Edit tool route remains a residual risk, mitigated by Claude Code's built-in credential protection layer and the `permissions.deny` emitted by the worker_role schema (`tools/org_extension_schema.json`'s `worker_roles.*`). On WSL2 + DriveFS environments where `~/.aws` is a symlink to `/mnt/c/...`, the denyRead side is auto-skipped, structurally avoiding bwrap bootstrap failures (denyWrite is a single-file literal and is unaffected by symlink-escape). Note that on WSL, `claude-org-runtime` suppresses Layer 3 `denyRead` / `denyWrite` entries whose realpath escapes the sandbox visible range at emit time, listing the suppressed entries in a `$comment` field in the output. This vector is currently underwritten by role-contract self-discipline plus the user-level sandbox deny described above.
- **Absence of Windows native sandbox**: Per the table above, `cat .env` etc. pass through on Windows native. As a worker execution environment, macOS / Linux / WSL2 is recommended; on Windows native, complement with other channels (OS-side file permissions, GitHub Secret Scanning, etc.).

For details and the phased-rollout decision, see [Issue #79](https://github.com/suisya-systems/claude-org-ja/issues/79) and [§10.1–§10.2](#101-sandboxdenyread--denywrite-live-verification-phase-2a-issue-79).

---

## Recording Test Results

Record the result of each test in this format:

```markdown
## Test {N}: {test name}
- Date/time: YYYY-MM-DD HH:MM
- Result: PASS / FAIL / PARTIAL
- Issues: {describe if any}
- Remedy: {what was fixed}
- Retest: needed / not needed
```

Save under the `docs/test-results/` directory.
