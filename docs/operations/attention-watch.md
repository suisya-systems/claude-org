# attention-watch operations guide

`claude-org-runtime attention scan` / `attention watch` is a watcher that monitors `.state/state.db` and `.state/pending_decisions.json` and notifies — via desktop notification + sound + terminal bell fallback — states that require a human response (waiting for approval / waiting for a judgment / CI failed / silent stop, etc.). This document covers operational procedures on the Layer 4 (`claude-org-ja`) side. For the design premises, classification rules, and dedup spec, see [`docs/design/attention-notification.md`](../design/attention-notification.md).

## 1. Role, inputs, outputs

- **Inputs**:
  - The `events` table in `.state/state.db` (`notify_sent` / `ci_completed` / `worker_completed` / `pr_merged`, etc.)
  - `.state/pending_decisions.json` (the register of human-judgment escalations)
  - optional config: `.state/attention.json` (use `tools/templates/attention.example.json` as a template)
- **Outputs**:
  - desktop notification (OS-specific backends — see §3)
  - sound (one of `urgent-only` / `all` / `off` — see §4)
  - terminal bell fallback (`\a`)
  - structured stdout log
  - dedup state: `.state/attention_notified.json` (managed automatically by the runtime)

## 2. Enable / disable

### 2.1 Recommended: start / stop via skills

From inside the renga tab (the Secretary session), the recommended path is the **two skills** that handle config auto-placement, splitting the dispatcher pane, and pane_id recording in one shot:

| Operation | Skill | Side effects |
|---|---|---|
| Start | [`/org-attention-start`](../../.claude/skills/org-attention-start/SKILL.md) | If `.state/attention.json` is missing, auto-copy from `tools/templates/attention.example.json` → vertical-split the right side of the dispatcher pane → start `claude-org-runtime attention watch ...` resident → record the pane_id in the `.state/attention_pane.json` sidecar |
| Stop | [`/org-attention-stop`](../../.claude/skills/org-attention-stop/SKILL.md) | Read the sidecar, discard the pane via `mcp__renga-peers__close_pane` → delete the sidecar |

It does not auto-start from `/org-start` (OS notification backends are strongly environment-dependent, and unsolicited sound is easily annoying. Design [`docs/design/attention-notification.md`](../design/attention-notification.md) §11 Q1). After `/org-start` completes, either fire `/org-attention-start` explicitly, or place it manually only when needed (§2.2).

The sidecar (`.state/attention_pane.json`) follows the same "auxiliary-process tracking" pattern as `.state/dashboard.pid` / `.state/attention_notified.json`, and `.state/state.db` schema is not extended (to avoid ripple effects on importer / writer / snapshotter / converter / drift_check). Since `.state/` is gitignored, the sidecar is not committed either.

### 2.2 Manual placement (outside renga / starting from a separate terminal)

`tools/templates/attention.example.json` is a tracked example containing the ja default template set. If you want to run it resident from a separate terminal without using the renga tab, or to hand-edit the template before placement, do the following:

```bash
mkdir -p .state
cp tools/templates/attention.example.json .state/attention.json
```

To change OS-notification or sound behavior, edit `.state/attention.json` (override template strings, switch `sound`, adjust `cooldown_sec`, etc.). The template placeholder allowlist is the 6 placeholders `{task_id}` / `{worker}` / `{kind}` / `{status}` / `{pr}` / `{summary}`; unknown placeholders are either left as literals or filled by the runtime's fallback template (see design §6).

### 2.3 One-shot verification (`scan`)

Before keeping `watch` resident, confirm that attention events are extracted from the current `.state/` as expected:

```bash
claude-org-runtime attention scan --state-dir .state --config .state/attention.json --dry-run --json
```

Always pass `--config .state/attention.json` (without it, the runtime-neutral English defaults appear in title/body, and you cannot tell whether the ja templates are actually taking effect). `--dry-run` does not invoke OS-notification subprocesses, so it is safe in CI environments or during quiet hours. The output is in the form `{ "events": [{ "key": ..., "kind": ..., "severity": ..., "title": ..., "body": ...}, ...] }` (for details, see [the attention scan verification block in `docs/verification.md`](../verification.md)).

### 2.4 Resident mode (`watch`) — manual start

For the raw CLI when you want to start the watcher directly from outside the renga tab (separate terminal / background):

```bash
claude-org-runtime attention watch --state-dir .state --config .state/attention.json
```

In normal operation, use `/org-attention-start` from §2.1 (the skill handles pane_id recording / sidecar management / double-start checks). Stopping is Ctrl-C (the dedup state is written via atomic replace, so even a forced kill can be recovered on next startup — see §5).

### 2.5 Disabling

When started from inside the renga tab, use [`/org-attention-stop`](../../.claude/skills/org-attention-stop/SKILL.md) to clean up the sidecar and the pane in one shot. A manually started watcher can just be terminated with Ctrl-C. There is no need to delete the config file (`.state/attention.json`). To temporarily suppress notifications, set `"desktop": false` / `"sound": "off"` in `.state/attention.json`, or demote individual-kind severities from `"urgent"` to `"normal"` (the value of `notify.<kind>` only accepts `"urgent"` / `"normal"`; there is no per-kind `off`. To stop completely, use the global `desktop: false`).

## 3. OS-specific notification backend behavior

The runtime invokes OS-standard commands via subprocess (with timeouts) without adding dependencies. Unusable backends fall back to stdout + terminal bell, and the watcher itself does not crash. **The current runtime (0.1.x) does not have an audio-file playback path; when `sound` is effective, it rings the terminal bell (`\a`) immediately after the OS notification** (on Windows / WSL only, it uses `[console]::beep` for a simple beep). Sound-playback commands such as `afplay` / `paplay` / `canberra-gtk-play` are not currently used and are only described as future enhancements.

| OS / environment | desktop backend | sound backend | notes |
|---|---|---|---|
| macOS | `osascript -e 'display notification ...'` | terminal bell `\a` | macOS shows desktop notifications by default. When `sound` is effective, a bell rings right after the notification |
| Linux | `notify-send <title> <body>` | terminal bell `\a` | `notify-send` is from the `libnotify-bin` package. Works on GNOME / KDE. If DBus is absent, `notify-send` silently fails, but the watcher does not crash and falls back to stdout |
| Windows native | PowerShell `Write-Host` (in reality produces no visible UI) | PowerShell `[console]::beep` (urgent only) | **Currently has no visible notification surface.** Only the urgent-severity beep is audible; nothing reaches the Windows notification center. Conversion to a real toast via BurntToast / WinRT is split out as a separate follow-up Issue on the runtime side (not addressed in PR #27) |
| WSL (with `wsl-notify-send.exe`, **recommended**) | `wsl-notify-send.exe --category <title> <body>` produces a real toast in the Windows notification center | PowerShell `[console]::beep` (urgent only, separate subprocess) | If `wsl-notify-send.exe` is on `$PATH` inside WSL, the runtime selects this path automatically. See §3.1 for install steps. On a successful toast, the terminal bell is suppressed to avoid a double beep |
| WSL (only `powershell.exe`, fallback) | PowerShell `Write-Host` (no visible UI) | PowerShell `[console]::beep` (urgent only) | A legacy path used when `wsl-notify-send.exe` is not installed and only `powershell.exe` is on PATH. **No visible UI; only the urgent beep is audible**. To reach the Windows notification center, follow the install steps in §3.1 |
| fallback (none of the above / containers, etc.) | structured stdout log | terminal bell `\a` | The watcher does not crash |

During `--dry-run`, no OS subprocess is invoked in any environment — stdout only.

WSL backend selection follows a 3-step priority `wsl-notify-send.exe` → `powershell.exe` → stdout, switching automatically based on PATH presence. The design intentionally does not provide a way to name the backend explicitly in the runtime config — behavior is determined by tuning the environment (i.e., installing or not installing `wsl-notify-send.exe`).

### 3.1 Installing wsl-notify-send.exe (WSL recommended)

To get real toasts in the Windows notification center from WSL, install [`stuartleeks/wsl-notify-send`](https://github.com/stuartleeks/wsl-notify-send). The runtime selects automatically based on whether the exe is on WSL's `$PATH`, so no config changes (such as `.state/attention.json`) are needed.

```bash
mkdir -p ~/.local/bin
curl -L -o ~/.local/bin/wsl-notify-send.exe \
  https://github.com/stuartleeks/wsl-notify-send/releases/latest/download/wsl-notify-send.exe
chmod +x ~/.local/bin/wsl-notify-send.exe
wsl-notify-send.exe 'test'
```

- If `~/.local/bin` is not on `$PATH`, add it in `.bashrc` / `.zshrc` (`export PATH="$HOME/.local/bin:$PATH"`).
- If the verification step `wsl-notify-send.exe 'test'` shows 'test' in the Windows notification center, the install succeeded.
- Upstream (`stuartleeks/wsl-notify-send`) is MIT-licensed and written in Go. The last release is from 2021; it is stable but upstream is dormant (no plans for new features).
- After installing, re-running `claude-org-runtime attention scan --state-dir .state --config .state/attention.json --dry-run --json` does not change the JSON output (dry-run does not invoke OS subprocesses). To verify an actual toast, drop `--dry-run` and trigger a single urgent-severity event.

#### How title/body are rendered

The `wsl-notify-send.exe --category <title> <body>` call maps to the Windows toast as follows:

- The notification's **title line** (top) ← the runtime template `title` passed via `--category`
- The notification's **body** (bottom) ← the runtime template `body` passed as a positional argument

`--category` is originally intended as a "notification category" flag, but upstream `wsl-notify-send` renders it as the title string, so claude-org-runtime puts the title on `--category` (design judgment from the PR #27 worker, following upstream `main.go` documentation). The `templates.<kind>.title` / `body` values in `.state/attention.json` can be read directly as the toast's 2-line display.

### 3.2 Why no toast on Windows native / WSL fallback? — history

Before Issue #25 / PR #27, both WSL and Windows native were described as "produces a toast via PowerShell `Write-Host`," but the implementation just wrote `Write-Host` to the subprocess's captured stdout and discarded it — nothing reached the Windows notification center (only the urgent `[console]::beep` was an audible signal).

- PR #27 ([suisya-systems/claude-org-runtime#27](https://github.com/suisya-systems/claude-org-runtime/pull/27)) split the WSL backend into the 3-step `wsl-notify-send.exe → powershell.exe → stdout`, with the top-priority `wsl-notify-send.exe` path now producing real toasts.
- The Windows native backend carries the same defect and is not fixed by PR #27. Work to produce real toasts via BurntToast / WinRT is split out as a separate Issue on the runtime side.
- Impact on existing users: WSL users who have not installed `wsl-notify-send.exe` remain on the same legacy path as before PR #27 (Write-Host + beep). There is no breaking change; only users who follow `§3.1`'s install steps automatically receive real toasts.

## 4. Key config keys (operational view)

For the detailed schema, see [`docs/design/attention-notification.md`](../design/attention-notification.md) §5 / §6; the SoT is the runtime config schema. Here we list only the keys frequently touched in ja operations.

| Key | Default | Role |
|---|---|---|
| `desktop` | `true` | Whether to fire desktop notifications. `false` keeps stdout + bell only |
| `sound` | `"urgent-only"` | `"off"` / `"urgent-only"` / `"all"`. urgent-only makes sound only for urgent-severity events |
| `cooldown_sec` | `300` | Minimum interval (seconds) for re-notifying the same dedup key |
| `poll_interval_sec` | `10` | Polling period of `watch` |
| `pending_decision_min` | `15` | Elapsed minutes after which a `pending_decisions.json` pending becomes urgent (the entry of the 4-step ladder — see §4.1) |
| `pending_decision_max` | `1440` | Upper bound (minutes) of the urgent period. Pendings past this drop to normal (24h) |
| `pending_decision_drop` | `10080` | End of normal notifications (minutes). Pendings past this are suppressed from notification and remain only in `--json` output (7d) |
| `user_replied_min` | `15` | Elapsed minutes after which "user replied but worker not yet forwarded" becomes urgent |
| `max_title_chars` / `max_body_chars` | `80` / `240` | Truncation upper bounds of template output (part of secret-safe formatting) |
| `notify.<kind>` | see §4.1 | Per-event-kind severity (only the values `urgent` / `normal`; `off` is not allowed. To stop completely, use the global `desktop: false`) |
| `templates.<kind>.{title,body}` | ja default text | Placeholder allowlist: `{task_id} {worker} {kind} {status} {pr} {summary}` |

### 4.1 Default severity classification

The default severities for each kind in the `notify` map of `tools/templates/attention.example.json` are listed below. **urgent roughly corresponds to "action-required moments where only the user can recover," and normal to "anomaly / precursor signals that may self-recover"** (for the taxonomy rationale, see [`docs/design/attention-notification.md`](../design/attention-notification.md) §12).

| event kind | Default severity | Category | Notes |
|---|---|---|---|
| `approval_blocked` | urgent | action-required | The worker is fully stopped on tool approval, etc. Cannot be unblocked except via the user |
| `ci_failed` | urgent | action-required | CI failure. The user is needed to decide on re-push / fix |
| `pending_decision` | urgent | action-required | Worker asks for a judgment. The Secretary is responsible for escalating to the human (see CLAUDE.md) |
| `user_reply_not_forwarded` | urgent | action-required | The user already replied but it has not reached the worker. A Secretary operational gap |
| `pane_crashed` | urgent | action-required | A pane terminated unexpectedly. The user is needed to decide on restart |
| `relay_gap_suspected` | normal | anomaly / precursor | Dispatcher-monitoring precursor detection. Often self-recovers, and was the primary cause of urgent muting, so demoted |
| `silent_worker_output` | normal | anomaly / precursor | Pane has output but no peer message arrived. Same as above |
| `pane_silent` | normal | anomaly / precursor | Pane is unresponsive. May self-recover on the dispatcher side |
| `worker_stalled` | normal | anomaly / precursor | Heuristic estimate of worker progress stagnation. Short term may self-recover |
| `worker_not_reported` | normal | anomaly / precursor | No report has arrived from the worker. Short term may just be a delay |
| `worker_error` | normal | anomaly / precursor | Error report from the worker. May recover inside the worker |
| `worker_completed` | normal | progress | Completion. No immediate action required, but waiting for review |
| `pr_merged` | normal | progress | Merged. A trigger for post-merge cleanup |

**※ Local overrides**: in `.state/attention.json` you can override per-kind severity. The ja distribution's template defaults and the user's individual `.state/attention.json` overlay are separate layers (templates are tracked; the overlay is gitignored). For example, a user who wants to "see it immediately" for `worker_completed` can raise it to urgent in their `.state/attention.json`, while the template default (normal) is maintained independently.

### 4.2 4-step TTL ladder for pending_decisions

The three thresholds `pending_decision_min` / `pending_decision_max` / `pending_decision_drop` create a **4-step notification decay** based on the elapsed time since a judgment escalation was registered. This is designed to avoid the failure pattern where "ringing urgent forever on unresolved judgments" causes the watcher itself to be muted (noise → uniformly ignored) — see the rationale in [`docs/design/attention-notification.md`](../design/attention-notification.md) §12.

| Elapsed time | Stage | Behavior |
|---|---|---|
| `< pending_decision_min` (default less than 15 min) | grace | No attention event fired. A grace window on the assumption that the Secretary can relay to a human within a short time |
| `pending_decision_min ≤ t < pending_decision_max` (default 15 min — 24h) | urgent | desktop notification + urgent sound + terminal bell. First-response window |
| `pending_decision_max ≤ t < pending_decision_drop` (default 24h — 7d) | normal / visual-only | The desktop notification fires but no urgent sound. A visual remnant marking long-unresolved cases |
| `≥ pending_decision_drop` (default 7d or more) | suppressed | Both desktop and sound are suppressed. Only the `attention scan --json` output retains it, viewable via audit / dashboard paths |

**Runtime-side consistency conditions**: configs that do not satisfy `pending_decision_min < pending_decision_max < pending_decision_drop` cause the runtime's `attention/config.py` to return a validation error at load time (`user_replied_min < pending_decision_max` is also checked).

**Tuning advice**:

- **Tighten the urgent window in noisier workflows**: lower `pending_decision_max` (e.g., 24h → 4h). Demotes urgent → normal earlier, distinguishing the high-urgency newer pendings
- **Keep a longer audit trail**: raise `pending_decision_drop` (e.g., 7d → 30d). Extends the grace before full suppression, making long-running backlogs auditable via `attention scan --json`
- **Judgment escalations are frequent and the 15-minute grace feels short**: lengthen `pending_decision_min` (e.g., 15 → 60). For operations that want headroom for the Secretary's relay and want to suppress urgent over-firing
- Aligning `pending_decision_drop = pending_decision_max` removes the normal/visual stage, so excess immediately becomes suppressed. For short-lifecycle teams that do not need a "while-demoting" display

## 5. Troubleshooting

### 5.1 Desktop notification does not appear

1. Confirm that attention events appear on stdout with `--dry-run`:
   ```bash
   claude-org-runtime attention scan --state-dir .state --config .state/attention.json --dry-run --json
   ```
   If no event appears, the cause is upstream of the classifier (event injection into `.state/state.db` or the state of `.state/pending_decisions.json`). Trace `tools/journal_append.sh` / `tools/pending_decisions.py` paths instead of the watcher side.
2. If events appear but only OS notifications are absent, the backend was judged unavailable, or a backend without a visible UI was selected:
   - **macOS**: confirm that the notification-center settings allow notifications to your terminal / iTerm
   - **Linux**: run `which notify-send`; if missing, install via `sudo apt install libnotify-bin` or similar
   - **WSL**: verify install with `which wsl-notify-send.exe`. If not installed, it falls back to PowerShell `Write-Host` and nothing reaches the Windows notification center (only the urgent beep is audible). Install `~/.local/bin/wsl-notify-send.exe` via the steps in §3.1
   - **Windows native**: currently no visible notification surface implemented (see the §3 table). Only the urgent beep is audible. Real toast is planned in a separate follow-up Issue
3. If stdout contains a log similar to "fallback to terminal bell," the backend has explicitly fallen back. Check the items above.

### 5.2 Sound does not ring

- Check `sound` in `.state/attention.json` (not `"off"`? if `"urgent-only"`, is the target event classified as `urgent`?)
- The current runtime does not invoke sound-playback commands (`afplay` / `paplay`, etc.); when `sound` is effective, it rings the terminal bell `\a`. Check whether your terminal config has suppressed the bell (iTerm / Windows Terminal / GNOME Terminal each have visual bell / silent bell options)
- On Windows / WSL, `powershell.exe -NoProfile -Command "[console]::beep(...)"` runs as a separate subprocess (the beep goes through the same PowerShell even when the WSL `wsl-notify-send.exe` path is chosen). Check host-side sound settings (system volume / stereo-mixer muting)
- On the WSL real-toast path (§3.1), when the toast succeeds, the terminal bell is suppressed (to avoid double-beep with the PowerShell beep). If toasts appear but beeps do not, check in order: `sound` setting / whether the event severity is classified as urgent / system volume

### 5.3 The same event keeps ringing / does not ring

The dedup state is managed by the runtime in `.state/attention_notified.json`.

- **The same event keeps ringing despite cooldown** → `.state/attention_notified.json` may be broken JSON. The runtime emits a warning and regenerates when corruption is detected, but to force a reset, delete it manually:
  ```bash
  rm .state/attention_notified.json
  ```
  It will be regenerated on the next scan / watch (atomic replace).
- **An event you want to hear does not ring** → it may be suppressed inside cooldown. Temporarily shorten `cooldown_sec`, or manually remove the key from `.state/attention_notified.json` and rescan.

### 5.4 Notification body is unexpected / garbled

- Placeholders appear as literals → if you wrote anything outside the design §6 allowlist (`{task_id} {worker} {kind} {status} {pr} {summary}`) into the template, the runtime keeps it as a literal or uses the fallback template. Rewrite within the allowlist
- Body is cut off → being truncated at `max_title_chars` / `max_body_chars`. This is part of secret-safe formatting, so it is preferable to shorten the summary rather than lengthen the body
- Japanese characters become `?` / garbled → on Linux, `notify-send` can corrupt them when locale is `C`. Export `LANG=ja_JP.UTF-8` or similar before starting `watch`

## 6. Related

- Design: [`docs/design/attention-notification.md`](../design/attention-notification.md)
- Verification procedure: the `attention scan --dry-run` verification block in [`docs/verification.md`](../verification.md)
- Startup guidance from `/org-start`: [`.claude/skills/org-start/SKILL.md`](../../.claude/skills/org-start/SKILL.md)
- External sinks (Slack / Discord / ntfy) are out of the initial scope (design §9, future opt-in)
