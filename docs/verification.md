# Verification

Procedures for confirming each feature works. When a problem is found, fix the
skill or CLAUDE.md and retest.

**Prerequisites**: renga 0.18.0+ (after `npm install -g @suisya-systems/renga@0.18.0`,
register the `renga-peers` MCP server at user scope with `renga mcp install --force`).
Assumes structured `cwd` (0.16.0) / `set_pane_identity` (0.17.0) / `spawn_claude_pane` (0.18.0)
are all available.

---

## 0. Regression check (preventing regressions in launch templates)

**Goal**: detect whether the `cd X && claude ...` auto-upgrade-bypass pattern
removed in Issue #58 has been reintroduced into templates / skills / docs.

**Procedure**:
```bash
# (1) Spots that synthesize `cd X && claude` into the command argument of
#     spawn_pane / spawn_claude_pane
#     (forbidden: renga's bare-claude auto-upgrade does not fire and channel push does not arrive)
grep -rEn 'command="cd [^"]*&&[[:space:]]*claude' --include="*.md" --include="*.toml" . \
  && { echo "FAIL: cd&&claude synthesis remains"; exit 1; } \
  || echo "OK: no cd&&claude synthesis"

# (2) Hand-written `claude --dangerously-load-development-channels` on the
#     command line of ops.toml / layout TOML
#     (unnecessary thanks to renga 0.16.0+ bare-claude auto-upgrade / spawn_claude_pane auto-injection)
grep -En '^[[:space:]]*command[[:space:]]*=.*dangerously-load-development-channels' renga-layouts/*.toml \
  && { echo "FAIL: dangerously flag hand-written in layout"; exit 1; } \
  || echo "OK: no explicit flag in layout TOML"
```

**Expected result**:
- (1) returns 0 hits (descriptive mentions in prose use different quoting / notation and do not match)
- (2) returns 0 hits in `renga-layouts/*.toml`

**Recovery on failure**:
- Rewrite hits to use the structured fields of `spawn_claude_pane` (`cwd` /
  `permission_mode` / `model`). For details, see the "ClaudeCode launch
  command (per role)" section of `.claude/skills/org-start/SKILL.md` and
  `.claude/skills/org-delegate/references/pane-layout.md`.

## 0. Compatibility preflight

**Goal**: confirm that, before running `/org-start`, the renga version and MCP
tool surface meet claude-org's requirements (Issue #61).

**Procedure**:
```bash
py -3 tools/check_renga_compat.py            # Windows
python3 tools/check_renga_compat.py          # macOS / Linux
py -3 tools/check_renga_compat.py --json     # Machine-readable output
```

**Expected result**: exits with `Result: OK` and exit code 0. Pass criteria:
renga version, `renga-peers` MCP registration, and all 14 required tools are
present.

**Failure patterns**:
- renga version too old → `npm update -g @suisya-systems/renga`
- MCP not registered → `renga mcp install`
- Tools missing → `renga mcp install --force` to refresh stale registrations

This script does not require a live renga session (it is a static probe that
fetches tools/list via `renga mcp-peer` stdio).

---

## 1. Basic launch test

**Goal**: launch ClaudeCode at the clone destination and confirm CLAUDE.md
and skills are loaded correctly.

**Procedure**:
1. `git clone` this repository into any location
2. Run `renga --layout ops` at the clone destination (a Lead pane comes up)
3. Confirm `mcp__renga-peers__list_panes` is reachable from the Lead's Claude
   Code (Step 0 MCP-availability check)
4. Run `/org-start` in the Lead's Claude Code

**Expected result**:
- `.state/org-state.md` does not exist, so it is judged as a first-time launch
- `mcp__renga-peers__spawn_pane` opens the Dispatcher pane below the Lead, and
  the Curator pane to its right
- The "load development channel?" prompt that appears immediately after
  Dispatcher / Curator launch is bypassed by injecting Enter via
  `mcp__renga-peers__send_keys(target=<pane>, enter=true)` (per the
  `org-start` SKILL Step 2 / Step 3 procedure)
- The Curator is instructed via `mcp__renga-peers__send_message` to run
  `/loop 30m /org-curate`
- Reports "First launch. What shall we do?"

**Failure patterns and recovery**:
- CLAUDE.md is not loaded → check the layout of the `.claude/` directory
- Skills are not recognized → check the frontmatter format of
  `.claude/skills/*/SKILL.md`
- `/org-start` does not fire → check for skill-name conflicts or the description
- `mcp__renga-peers__list_panes` errors → re-run `renga mcp install --force`,
  verify with `claude mcp list`
- `send_keys(enter=true)` fails to inject Enter → verify the Dispatcher /
  Curator pane is stuck on the "Load development channel?" prompt; press
  Enter manually

---

## 2. org-delegate test (worker dispatch)

**Goal**: confirm a worker is correctly dispatched, completes its task, and
reports the result.

**Prerequisites**: launched with `renga --layout ops`, `renga-peers` MCP is
active (verify Connected with `claude mcp list`). Test 1 has run `/org-start`.

**Procedure**:
1. Ask the Lead Claude for a task (e.g. "add a new article to the blog")
2. For a new project, the Lead asks for nickname / path / description; answer
3. Confirm the Lead dispatches a worker via `/org-delegate`

**Expected result**:
- The project is auto-registered in `registry/projects.md`
- The Lead sends a DELEGATE message to the Dispatcher and immediately returns
  to the user dialogue
- The Dispatcher derives a worker pane in the same tab via
  `mcp__renga-peers__spawn_pane` (`name="worker-{task_id}"`; the balanced split
  strategy follows `pane-layout.md`)
- The Dispatcher confirms launch completion via
  `mcp__renga-peers__poll_events(types=["pane_started"])`
- The "load development channel?" prompt right after worker launch is bypassed
  by `mcp__renga-peers__send_keys(target="worker-{task_id}", enter=true)`
  (per `org-delegate` SKILL Step 3-2)
- The Dispatcher sends the task instruction to the worker via
  `mcp__renga-peers__send_message`
- The Dispatcher creates `.state/workers/worker-{id}.md`
- `.state/org-state.md` is created/updated
- Events are recorded in `.state/journal.jsonl`
- After the worker finishes, the report arrives **at the Lead** via
  `renga-peers` (not the Dispatcher)
- The Lead conveys the result to the human in business language (avoiding
  technical jargon)
- The Lead asks the Dispatcher to close the pane (the Dispatcher disposes of
  it via `mcp__renga-peers__close_pane(target="worker-{task_id}")`)

**Verification commands**:
```bash
cat .state/org-state.md
cat .state/journal.jsonl
ls .state/workers/
cat registry/projects.md
```

Pane state is checked via the MCP tool:
```
mcp__renga-peers__list_panes    # Current pane list
```

**Failure patterns and recovery**:
- Pane does not open → check current pane state with
  `mcp__renga-peers__list_panes`; branch on `[split_refused]` /
  `[pane_not_found]` in the tool result via `references/renga-error-codes.md`
- Cannot communicate via renga-peers → confirm `renga-peers` is Connected with
  `claude mcp list`, check peer IDs (`worker-{task_id}` / `dispatcher` /
  `curator` / `secretary`) with `list_peers`
- State file not created → revisit the org-delegate skill steps
- Worker does not understand the instruction → improve the wording in
  instruction-template.md
- Project name resolution does not work → revisit org-delegate Step 0

### 2.1 Balanced-split scale verification (4-way / 8-way)

**Goal**: confirm in real hardware that the rect-based balanced split in
org-delegate Step 3 produces the expected tree without `[split_refused]` for
both 4-way and 8-way concurrency.

**Prerequisites**: Test 2 passing. Terminal width `W ≥ 160 cols` (verify with
`tput cols`). Have the "Worker balanced split strategy" section of
`pane-layout.md` open at hand.

**Procedure**:
1. Run `tput cols` and record W. If under 160, mark unverifiable and skip, or
   widen the terminal.
2. Ask the Lead 8 mutually independent tasks in sequence (dummies are fine,
   e.g. lightweight tasks like `echo-1` ... `echo-8`). Confirm each k = 1..8
   satisfies:
   - a. The text result of the Dispatcher's `mcp__renga-peers__spawn_pane`
        call does not contain `[split_refused]`
   - b. The `target` / `direction` selected by the Step 3-1b algorithm can be
        reproduced rect-wise from the immediately preceding `list_panes`
        snapshot
   - c. Save `mcp__renga-peers__list_panes` taken just after launch to a
        **separate log file (e.g. `.state/verification/balanced-split-{timestamp}.log`)**,
        or record the `name` / `id` of `role == "worker"` on the spot, and
        cross-check after the fact against the `worker_spawned` events in
        `.state/journal.jsonl`
3. At each k, fetch the pane layout with `list_panes` and confirm that the
   Step 3-1b algorithm (curator identification → role filter →
   dispatcher-curator adjacency check → direction decision → `new_w / new_h`
   calculation → MIN_PANE constraint → SECRETARY safety clause → metric sort)
   can be hand-reproduced against the snapshot. As stated in the "Worker
   balanced split strategy" section of `pane-layout.md`, this is rect-based
   dynamic placement, so fixed grid shapes such as 2×2 or 2×4 are not used as
   success criteria.
4. Try a 9th dummy task and confirm the Dispatcher sends
   `SPLIT_CAPACITY_EXCEEDED` to the Lead via `renga-peers`. **Only the 9th
   worker dispatch is canceled; the Dispatcher's monitoring loop itself
   continues to run** (no `spawn_pane` is issued and the Dispatcher does not
   fall over via `exit` etc.).

> **Note**: verification logs such as
> `.state/verification/balanced-split-{timestamp}.log` are temporary and not
> committed. `.state/*` is already excluded by the existing `.gitignore`.

**Expected result**:
- Zero `[split_refused]` for k=1..8
- Each k's layout matches the Step 3-1b decision (no fixed grid shape required;
  the rect dynamic placement works correctly)
- Within the MIN_PANE constraint (`new_w ≥ 20` / `new_h ≥ 5`), the candidate
  set does not become empty
- At k=9, an explicit escalate (no silent failure)

**Verification commands**:
```bash
tput cols                                # Record terminal width
cat .state/journal.jsonl | grep worker_spawned
```

Pane state via MCP:
```
mcp__renga-peers__list_panes             # Snapshot at each k
```

**Failure patterns and recovery**:
- `[split_refused]` at k=4 → check the value of `tput cols`. If W < 160 the
  balanced-split prerequisite is not met. Retry after widening the terminal
- Already `[split_refused]` at k=3 → check whether file-tree / preview is
  squatting directly under the Dispatcher (these eat 20-40 cols of `W_f` while
  visible)
- Layout differs from expected → forgot `close_pane` for a leftover worker
  from a previous task. Verify role=worker active starts from 0 in `list_panes`
- k=9 silently succeeds → the Step 3-1c (`SPLIT_CAPACITY_EXCEEDED` escalate)
  branch did not fire. Confirm the Step 3-1b decision logic correctly returns
  "candidate empty"

---

## 3. org-suspend test (suspend)

**Goal**: confirm the org's state is correctly saved and all panes stop.

**Prerequisites**: a worker is running (or has just finished) from Test 2.

**Procedure**:
1. Tell the Lead Claude "suspend"
2. Confirm `/org-suspend` fires

**Expected result**:
- A SUSPEND message is sent to the worker via `mcp__renga-peers__send_message`
- The worker reports state via `renga-peers`. For unresponsive workers, use
  `mcp__renga-peers__inspect_pane(target="worker-{task_id}", format="text")`
  to read the screen contents and infer state combined with the git status
- `.state/org-state.md` Status becomes `SUSPENDED`
- A backup is created in `.state/org-state.prev.md`
- A SHUTDOWN is sent to all peers via `mcp__renga-peers__send_message`
- Wait for pane_exited via
  `mcp__renga-peers__poll_events(types=["pane_exited"], timeout_ms=10000)` and
  drain `role == "worker"` in bulk
- Stragglers are fall-back closed via
  `mcp__renga-peers__close_pane(target="worker-{task_id}")`
- All worker panes close first, then the Dispatcher, then the Curator
- The Lead reports completion of the suspend

**Verification commands**:
```bash
cat .state/org-state.md | head -5  # Confirm Status: SUSPENDED
cat .state/journal.jsonl | tail -1  # Confirm the suspend event
```

**Failure patterns and recovery**:
- Worker does not respond to SUSPEND → check screen contents with
  `inspect_pane`, verify the Phase 2 scrape works
- Pane does not close → check the result text of `close_pane(target="X")`.
  Treat `[pane_not_found]` / `[pane_vanished]` as skip
- `[last_pane]` appears → let the final Lead pane exit naturally via self-exit
  (org-suspend does not close it)
- State file incomplete → revisit the org-suspend procedure

---

## 4. org-resume test (resume)

**Goal**: confirm that on relaunch after suspend, the previous state is
correctly restored.

**Prerequisites**: suspended in Test 3.

**Procedure**:
1. **Completely close** the Lead Claude's terminal
2. Re-launch with `renga --layout ops` at the clone destination
3. Run `/org-start`

**Expected result**:
- `/org-start` detects `.state/org-state.md` and confirms Status: SUSPENDED
- Following the `/org-resume` procedure, a summary of the previous state is shown
- A reconciliation report against each working directory's git state is shown
- A resume plan is proposed
- Waits for human approval (does not dispatch workers on its own)
- Dispatcher and Curator panes are relaunched via
  `mcp__renga-peers__spawn_pane`

**Verification points**:
- Briefing contents match `.state/org-state.md`
- Git-state reconciliation is accurate
- Dispatcher and Curator panes are running (verify with
  `mcp__renga-peers__list_panes`)

**Failure patterns and recovery**:
- `/org-start` does not read state → revisit Step 1 of the org-start skill
- State is inaccurate → revisit org-state.md format or the org-suspend write
- Curator does not start → verify `send_message` / `spawn_pane` in org-start Step 3

---

## 5. Sudden-exit test (crash recovery)

**Goal**: confirm how much can be restored when the terminal is closed
without running org-suspend.

**Procedure**:
1. From the Test 2 state (worker running), close the terminal **without
   suspending**
2. Re-launch with `renga --layout ops`
3. Run `/org-start`

**Expected result**:
- `/org-start` detects `.state/org-state.md` and confirms Status remains ACTIVE
- Concludes the previous session ended abruptly and inspects each worker
  directory's git state
- Backfills events after the snapshot from `.state/journal.jsonl`
- Reports the current state

**Acceptable degradation**:
- Detailed self-reported worker progress is lost
- Information after the last entry in journal.jsonl is lost
- Work that was not git-committed may end up in an unclear state
- If the Dispatcher's `poll_events` cursor (`.state/dispatcher-event-cursor.txt`)
  is lost, up to ~5 seconds of past events may be missed, but recoverable via
  `list_panes` reconciliation

**Failure patterns and recovery**:
- org-state.md is too stale → increase periodic snapshot frequency (strengthen
  org-delegate progress tracking)
- journal.jsonl is missing → check the journaling implementation

---

## 6. org-retro test (retrospective)

**Goal**: confirm that after a task completes, learnings are correctly recorded.

**Procedure**:
1. A worker completes some task
2. Confirm the Lead runs `/org-retro`

**Expected result**:
- If reusable knowledge exists,
  `knowledge/raw/YYYY-MM-DD-{topic}.md` is created
- Format follows "fact → decision → rationale → applicable situation"
- If recording is judged unnecessary, nothing is created (a correct judgment)

**Verification commands**:
```bash
ls knowledge/raw/
cat knowledge/raw/*.md  # Format check
```

---

## 7. org-curate test (knowledge curation + self-improvement loop)

**Goal**: confirm the Curator organizes knowledge and can make improvement
proposals.

**Prerequisites**: 5 or more unprocessed files exist in `knowledge/raw/`.

**Procedure**:
1. For testing, create 5+ dummy knowledge files in `knowledge/raw/`
2. Run `/org-curate` manually (or wait for the Curator's /loop)

**Expected result**:
- Raw files are categorized by theme
- Per-theme files are created at `knowledge/curated/{theme}.md`
- A `<!-- curated -->` marker is prepended at the top of processed raw files
- If improvement proposals exist, the Lead is notified via `renga-peers`

**Verification commands**:
```bash
ls knowledge/curated/
cat knowledge/curated/*.md
head -1 knowledge/raw/*.md  # Check <!-- curated --> marker
```

**Self-improvement check**:
- Improvement proposals are concrete
- Proposals are not executed without human approval

---

## 8. Dispatcher / Curator pane test

**Goal**: confirm the Dispatcher and Curator launch correctly in their
dedicated panes and function.

**Procedure**:
1. Run `/org-start` and confirm the Dispatcher and Curator panes launch
2. Confirm the Dispatcher receives role instructions via
   `mcp__renga-peers__send_message`
3. Confirm the Curator runs `/loop 30m /org-curate` via
   `mcp__renga-peers__send_message`
4. Place fewer than the threshold in `knowledge/raw/` and confirm the Curator
   skips
5. Increase to at or above the threshold and confirm it runs in the next
   /loop cycle

**Expected result**:
- After `/org-start` runs, the Dispatcher and Curator open side by side below
  the Lead (verify with `mcp__renga-peers__list_panes`)
- The Dispatcher enters a state of waiting for DELEGATE messages
- The Curator starts `/loop`
- org-curate fires every 30 minutes
- Skips below threshold; runs at or above threshold

**Failure patterns and recovery**:
- Pane opens but does not receive instructions → adjust `renga-peers` peer
  detection timing (retry `list_peers`, extend the wait for `pane_started`)
- Dispatcher does not respond to DELEGATE → revisit the initial message to the
  Dispatcher
- /loop does not run → revisit the message content to the Curator

---

## 9. org-dashboard test (dashboard)

**Goal**: confirm the dashboard live-server launch and browser display work
correctly.

**Prerequisites**: worker dispatch and project registration completed in Test 2.

**Procedure**:
1. Tell the Lead "show the dashboard"
2. Confirm `/org-dashboard` fires

**Expected result**:
- `dashboard/server.py` starts and serves at `http://localhost:8099`
- A browser opens `http://localhost:8099`
- Project list, work status, activity, and knowledge are displayed
- The `/api/state` response matches actual state

**Failure patterns and recovery**:
- Server does not start → check error output of `dashboard/server.py`
- Data is not displayed in the browser → verify `http://localhost:8099`
  responds with `curl`
- Data does not refresh → check the SSE connection state (`/api/events`)

---

## 10. E2E test (full cycle)

**Goal**: confirm the full cycle of launch → work → suspend → resume →
knowledge curation works.

**Procedure**:
1. Launch ClaudeCode at the clone destination (`renga --layout ops`)
2. Run `/org-start` (first launch)
3. Request 3 tasks (ones that trigger worker dispatch)
4. Confirm a retrospective is recorded after each task completes
5. With "show the dashboard," confirm the overall picture
6. Suspend with `/org-suspend`
7. Completely close the terminal
8. Re-launch → `/org-start` → previous state is reported
9. Approve the resume → workers are redispatched
10. Confirm curation runs once `knowledge/raw/` reaches the threshold
11. git commit → push curated knowledge

**Success criteria**:
- All steps complete without human intervention (apart from instructions and approvals)
- No state loss
- Knowledge accumulates and is organized
- The full picture is visible on the dashboard

---

## 10.1. sandbox.denyRead / denyWrite real-hardware verification (Phase 2a, Issue #79)

**Goal**: confirm that `sandbox.filesystem.denyRead` / `denyWrite` in
`.claude/settings.json` work as expected on Windows + Git Bash, and that
secret-information files such as `.env` cannot be read via Claude Code's Bash
tool.

**Prerequisites**:
- This repository cloned, and Claude Code can launch
- A dummy `.env` (e.g. `FAKE_TOKEN=dummy-not-a-real-secret`) is placed at the
  root of the verification target repository (`.gitignore`'d so not committed)
- Known bug [anthropics/claude-code#32226](https://github.com/anthropics/claude-code/issues/32226)
  reports cases where denyRead does not work as expected, so **be sure to
  verify on real hardware**

**Procedure**:
1. Ask the Lead Claude to run `cat .env` (via the Bash tool)
2. Ask for a command that reads `.env`, e.g. `grep -r FAKE_TOKEN .`
3. Ask for a command attempting to read `~/.ssh/id_rsa` (if it exists)
4. Ask for a command attempting to write to `~/.claude/settings.json`
   (e.g. `echo x >> ~/.claude/settings.json`)

**Expected result**:
- Steps 1-3: denied by sandbox in the Bash subprocess (an error equivalent to
  `Permission denied`). Even if Claude Code receives a result, the contents
  are empty / an error
- Step 4: write fails due to denyWrite

**Failure patterns and recovery**:
- `.env` contents are readable → possibly a Claude Code bug. Record the
  version with `claude --version` and check the status of Issue #32226. As a
  stopgap, add `Read(./.env)` to `permissions.deny` (closes the Read-tool path
  in Claude Code)
- Glob (`**/credentials*`) does not work on Windows → may be forward/backward
  slash differences. Adjust glob patterns to e.g. `./credentials*` and retry
- The sandbox itself does not fire → Claude Code's `sandbox.enabled` may default
  to OFF. Check the official docs for the current default

**Note**: this PR does not explicitly set `sandbox.enabled` (leaving it to
Claude Code's default). To limit the blast radius of known bug #32226, this
is a staged rollout; in environments where denyRead is ineffective by default,
explicitly setting it to true should be considered separately.

### Measured results (2026-04-25, Windows 11 + Git Bash, Claude Code Desktop)

| # | Operation | Result |
|---|---|---|
| 1 | `cat .env` | Read (sandbox did not fire) |
| 2 | `grep -r FAKE_TOKEN .` | Read (sandbox did not fire) |
| 3 | `cat ~/.ssh/id_rsa` | Denied (* not by the sandbox but by Claude Code's built-in credential protection layer) |

Even with explicit `sandbox.enabled: true`, #1 and #2 still pass through. The
official documentation confirms native sandbox enforcement on Windows is in
the "planned" state (not yet implemented)
(https://docs.claude.com/en/docs/claude-code/iam#sandbox).
This setting works only on **macOS (Seatbelt) / Linux / WSL2 (bubblewrap)**.

### WSL2 measured results (2026-04-25)

| Operation | Result |
|---|---|
| `cat .env` (on PR branch checkout) | Read (sandbox disabled) |
| `grep -r FAKE_TOKEN .` | Read |
| Warning at `claude` launch | `⚠ Sandbox disabled: bubblewrap (bwrap) not installed, socat not installed` |

**Cause**: Claude Code's sandbox requires **`bubblewrap` and `socat`** as
runtime dependencies on Linux / WSL2, but they are not included by default in
Ubuntu / Debian-family WSL images.

**Recovery**: in WSL environments where you actually want the sandbox to fire,
do the following:

```bash
sudo apt install -y bubblewrap socat
claude  # Confirm the warning disappears
```

After installing this, re-run the verification procedure in the next section
to confirm `cat .env` etc. are denied.

**Detection procedure**: the sandbox state can be checked right after
`claude --version` / by running `/sandbox` (Claude Code shows the warning).
In CI environments or Docker containers where you expect the sandbox, make
`apt install bubblewrap socat` explicit in the Dockerfile / workflow.

### WSL2 verification procedure (not yet performed, human task)

1. Clone this repository inside WSL2, or share the Windows-side worktree via
   `\\wsl$\...`
2. Launch `claude` inside WSL (use Claude Code for WSL or install via
   `npm install -g`)
3. Ask for the following and verify each is denied:
   - "Run `cat .env`" → Permission denied equivalent via sandbox denyRead
   - "Run `grep -r FAKE_TOKEN .`" → ditto
   - `echo x >> ~/.claude/settings.json.sandbox-test` → write fails via denyWrite
4. Append the measured results to the table in this section (add an OS row)

If WSL does not deny, then either (a) Claude Code's version does not support
sandbox, (b) a config-syntax interpretation difference, or (c) another symptom
of #32226. Record the version and the status of Issue #32226.

### Phase 2a portability fix ([Issue #83](https://github.com/suisya-systems/claude-org-ja/issues/83))

To work around the issue where, on WSL2 without `bubblewrap`, sandbox init silently no-op falls back and disables `~/.aws/**` / `~/.ssh/**` denyRead/denyWrite, **home dotfiles (`~/.aws` / `~/.ssh`) are moved out of sandbox scope** and defended instead via `permissions.deny` `Read(~/.ssh/*)` / `Read(~/.aws/*)`. For portability, home dotfiles are out of sandbox scope. The sandbox's `denyRead` / `denyWrite` are concentrated on repo-local `.env` / credential files.

The `permissions.deny` Read defense covers the Read tool path only; Bash-mediated reads and the Dispatcher (`bypassPermissions` mode) are not covered. This trade-off was discussed and accepted in Issue #83 as portability-first.

---

## 11. MCP connectivity test (environment check)

**Goal**: confirm the `renga-peers` MCP server is connected to Claude Code,
that all 14 tools are registered as the tool surface, and that — for
side-effect-free tools — sample calls return responses correctly. The
real-behavior check for tools with large side effects (`send_keys` /
`spawn_pane` / `spawn_claude_pane` / `close_pane` / `focus_pane` / `new_tab`
/ `set_pane_identity`) is covered by the Test 1-10 E2E flow, so this test
limits itself to registration verification only.

**Procedure**:

### 11-a. Registration check (14 tools)
1. Confirm `claude mcp list` shows `renga-peers` as Connected
2. Confirm `renga --version` is 0.18.0 or higher
3. Confirm the following 14 tools appear on Claude Code's tool surface
   (matches the tool names returned by the MCP server's tools/list):
   - No / light side effects: `list_panes` / `list_peers` / `set_summary` /
     `check_messages` / `send_message` / `poll_events` / `inspect_pane`
   - Large side effects (pane / PTY operations): `spawn_pane` /
     `spawn_claude_pane` / `close_pane` / `focus_pane` / `new_tab` /
     `send_keys` / `set_pane_identity`

### 11-b. Response check for side-effect-free tools (7 tools)
Call the following 7 tools in sequence and confirm they respond without errors:

| Tool | Sample call | Expected response |
|---|---|---|
| `list_panes` | No args | Current pane list text |
| `list_peers` | No args | Same-tab peer list or `(no peers — …)` |
| `set_summary` | `summary="test"` | `Summary accepted (v1 stub: …)` |
| `check_messages` | No args | `No queued messages.` |
| `send_message` | `to_id=<own pane id or name>, message="ping"` | `Delivered to <target>.` or `(message dropped — …)` |
| `poll_events` | `timeout_ms=0` (non-blocking drain) | JSON of `{next_since, events}` |
| `inspect_pane` | `target="focused", lines=5, format="text"` | Last 5 screen lines + `structuredContent` |

### 11-c. Side-effect-large tools delegated to E2E tests
`spawn_pane` / `spawn_claude_pane` / `close_pane` / `focus_pane` / `new_tab` /
`set_pane_identity` are exercised in Tests 1 / 2 / 3 / 4. `send_keys` is
exercised in Test 1 (Enter injection on the development-channel prompt).

**Expected result**:
- 11-a: `claude mcp list` output contains `renga-peers: … ✓ Connected` and
  all 14 tools are registered in Claude Code's tool list
- 11-b: all 7 tools respond without error; on error a `[<code>] <msg>` text
  is returned (e.g. `list_panes` returns `[shutting_down]` if renga is not
  running)
- 11-c: side-effect-large tools are not run in this test; coverage is left to
  E2E

**Failure patterns and recovery**:
- `renga-peers` does not appear in `claude mcp list` → re-run
  `renga mcp install --force`
- `list_panes` errors → check `renga --version` is 0.14.0+; if older
  `npm install -g @suisya-systems/renga@0.14.0`
- `poll_events` does not return JSON → implementation mismatch in
  `mcp_peer/mod.rs`; check the renga version

---

## Recording test results

Record each test result in the following format:

```markdown
## Test {N}: {test name}
- Date: YYYY-MM-DD HH:MM
- Result: PASS / FAIL / PARTIAL
- Issues: {if any}
- Recovery: {fix details}
- Retest: required / not required
```

Save under the `docs/test-results/` directory.
