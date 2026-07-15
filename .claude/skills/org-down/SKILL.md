---
name: org-down
description: >
  Suspend the org and fully stop it, down to and including the broker daemon.
  Use when told "stop it completely", "bring it down including the daemon", "org down it", "shut everything down".
  An integrated shutdown that runs suspend (state save + stopping ja-managed processes / panes) to completion
  and then calls `claude-org-runtime org down`. For a plain "suspend" / "done for today", use /org-suspend,
  which leaves the daemon running.
effort: low
allowed-tools:
  - Read
  - Bash(bash tools/journal_append.sh:*)
  - Bash(py -3 tools/journal_append.py:*)
  - Bash(python -m tools.state_db.importer:*)
  - Bash(python3 tools/secretary_queue_watcher.py:*)
  - Bash(py -3 tools/secretary_queue_watcher.py:*)
  - Bash(python3 tools/stop_dashboard.py:*)
  - Bash(py -3 tools/stop_dashboard.py:*)
  - Bash(echo:*)
  - Bash(rm -f .state/attention_pane.json)
  - Bash(del .state\attention_pane.json)
  - Bash(claude-org-runtime org down:*)
  - Bash(py -3 -m claude_org_runtime.cli org down:*)
  - mcp__org-broker__check_messages
  - mcp__org-broker__close_pane
  - mcp__org-broker__inspect_pane
  - mcp__org-broker__list_panes
  - mcp__org-broker__list_peers
  - mcp__org-broker__poll_events
  - mcp__org-broker__send_keys
  - mcp__org-broker__send_message
  - mcp__org-broker__set_summary
---

# org-down: full shutdown of the org (down to the broker daemon)

`/org-down` is an integrated-shutdown skill that **runs `/org-suspend` to completion first** and then calls
`claude-org-runtime org down` to fully stop the org, down to and including the broker daemon.

> **Responsibility boundary (most important)**: **only this skill** calls `claude-org-runtime org down` (stop
> the broker daemon). [`/org-suspend`](../org-suspend/SKILL.md) stops at "state save + stopping the ja-managed
> auxiliary processes (dashboard / secretary_queue_watcher / attention watcher) and panes" and leaves the
> daemon running (a pause on the premise of resuming with `/org-start`). /org-down proceeds to the daemon stop
> **only when it can confirm suspend succeeded**. The order is enforced because bringing the daemon down while
> unsaved state remains would lose the recovery path (draining via `check_messages`, etc.) along with it.
>
> The runtime-side pre-flight detection (a feature that warns about live workers / undrained queues before
> `org down`) is owned by
> [runtime#142](https://github.com/suisya-systems/claude-org-runtime/issues/142) and this skill does not touch
> it. This skill only **calls** the runtime's `org down`.

> **Transport premise**: `claude-org-runtime org down` is the command that brings down the broker daemon, and
> it is meaningful only on the broker transport (`ORG_TRANSPORT` unset = code default broker, or explicit
> broker). On the renga fallback (`ORG_TRANSPORT=renga` starting with `renga --layout ops`) there is no notion
> of a daemon, so skip Step 3 and note "no daemon stop is needed on renga". The judgment is made at the Step 3
> transport check.

## Step 1: run /org-suspend to completion

Run all phases of [`/org-suspend`](../org-suspend/SKILL.md) in order (Phase 1 state collection → Phase 2
no-response scrape → Phase 3 state write → **Phase 3.6 stop secretary_queue_watcher** → **Phase 3.7 stop
attention watcher** (before pane teardown) → Phase 4 stop all panes).

**However, replace Phase 3.5's dashboard blind kill with this skill's Step 2 stale-pid-safe stop** (in the
full shutdown just before org down, an unverified kill of a pid-recycled stale `dashboard.pid` would hit an
unrelated process. Mis-kill prevention). Run the other phases as-is.

**Confirming suspend succeeded (gate)** — proceed to Step 2 / Step 3 only when the following hold:

- `session.status` in `.state/state.db` is `SUSPENDED` (Phase 3's DB write took effect).
- The worker / dispatcher panes have been stopped by Phase 4's 2-pass (they no longer appear in
  `list_panes`. The last secretary pane may remain — the secretary cannot close itself).

**If suspend aborts / fails** (the DB does not become SUSPENDED / pane stop does not complete / a worker does
not return a SUSPEND response and its state remains unknown, etc.), **do not proceed to org down — STOP**.
Report the situation to the human and note "the daemon was not brought down because state could not be fully
saved. Re-run /org-down after resolving the cause, or use /org-suspend to pause for now."

## Step 2: stop the dashboard (stale-pid-safe)

`dashboard.pid` holds only a bare pid, so an unverified kill of a recycled pid would hit an unrelated process.
**Match not only that the pid is alive but that its cmdline is `dashboard/server.py`** before killing, and if
the match fails, do not kill — delete the stale pid file.

> **sandbox note**: host process inspection / kill cannot be observed inside Claude Code's Bash sandbox
> (process-namespace isolation). Run this Step on the host with `dangerouslyDisableSandbox: true` (the same
> reason as the dashboard startup in org-start Block C).

The identity-matching logic is inside a helper (`tools/stop_dashboard.py`), so on POSIX you just call one
line. The helper SIGTERMs only when, in addition to the pid being alive, it can match that the live argv
(Linux/WSL via `/proc`, macOS/BSD via a `ps` fallback) contains `dashboard/server.py`; if the match fails, it
does not kill and deletes the pid file as stale.

**Mac / Linux / WSL**:
```bash
python3 tools/stop_dashboard.py   # on Windows, use py -3 ... for the console python
```
Transcribe the one output line (`[stop-dashboard] dashboard (pid=N) stopped` / `... gone (stale) ...` /
`... not running ...`) into the Step 4 report as-is (to tell the human correctly whether it was actually
stopped or was stale). exit 0 is the normal case. exit 2 (identity unconfirmed) is a signal that appears only
in environments with neither `/proc` nor `ps` (Windows native); in that case use the PowerShell procedure
below.

**Windows native (PowerShell)** — identity-check via `Get-CimInstance Win32_Process`'s CommandLine before
`Stop-Process`:
```powershell
$pf = ".state\dashboard.pid"
if (Test-Path $pf) {
  $dpid = [int]((Get-Content $pf -Raw).Trim())
  $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$dpid" -ErrorAction SilentlyContinue
  if ($proc -and ($proc.CommandLine -match 'dashboard[\\/]server\.py')) {
    Stop-Process -Id $dpid -Force
    Write-Output "dashboard (pid=$dpid) stopped"
  } else {
    Write-Output "dashboard pid stale or not running; removing stale pidfile (no kill)"
  }
  Remove-Item $pf -ErrorAction SilentlyContinue
}
```

## Step 3: stop the broker daemon (org down)

Run this **only when the Step 1 suspend gate is satisfied**.

1. **Check the transport**:
   ```bash
   echo "${ORG_TRANSPORT:-broker}"
   ```
   - `renga`: there is no notion of a daemon, so **skip this Step**. In Step 4, note "no daemon stop is needed
     because of the renga fallback".
   - `broker` (including unset): continue.

2. Stop the broker daemon (this call also terminates the current broker session's tmux, including the
   secretary pane. **Always run it last**):
   ```bash
   claude-org-runtime org down          # Mac / Linux / WSL
   py -3 -m claude_org_runtime.cli org down   # on Windows when the console script is not on PATH
   ```
   - On a normal exit the broker daemon stops; restart afterward with `claude-org-runtime org up` →
     `/org-start`.
   - On failure (non-zero exit / error output), report it to the human as-is. State save (Step 1) is already
     complete, so even if the daemon remains, it does not impede a `/org-start` resume.

> **Note**: after `org down` runs, the broker daemon and the secretary pane go down, so prepare the rest of
> this skill (the Step 4 report) **before** `org down` and make `org down` the last operation. Alternatively,
> if you report only after receiving `org down`'s stdout/exit, emit it concisely in one line so the human can
> read it before the terminal closes.

## Step 4: report

**When the daemon was stopped too on broker** (present it right before running `org down`. Transcribe the
dashboard line from Step 2's stdout and write `stopped` or `stale` (was not running to begin with) exactly as
it is — do not assert "stopped" without confirmation):
```
Fully stopping the org.
- State save: complete (.state/state.db = SUSPENDED)
- dashboard: {Step 2's output (stopped / stale)}
- Stopped: secretary_queue_watcher / attention watcher / all worker & dispatcher panes
- About to stop the broker daemon (claude-org-runtime org down).
To resume, run `claude-org-runtime org up` → `/org-start`.
```

**When the daemon stop was skipped on the renga fallback**:
```
Suspended the org (no broker daemon stop is needed because of the renga fallback).
- State save: complete (.state/state.db = SUSPENDED)
- Stopped: dashboard / attention watcher / all worker & dispatcher panes
  (secretary_queue_watcher is broker-only, so N/A on renga)
To resume, run `renga --layout ops` → `/org-start`.
```

**When the suspend gate could not be satisfied and it STOPped** (already branched in Step 1): do not run org
down; report the unsaved cause and the recovery procedure (re-run or /org-suspend) to the human.
