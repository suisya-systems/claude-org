# Attention notification design

> Status: **design only**. This document defines the implementation direction and Issue split. The actual implementation is done in separate Issues / PRs on the `claude-org-runtime` side and the `claude-org-ja` side.
> Scope: an attention layer that uses desktop notifications / sound to alert the moment an AI worker needs a human response.
> Conclusion: the implementation body goes in **Layer 2 = `claude-org-runtime`**. `claude-org-ja` owns the Japanese default settings, onboarding paths, and documentation. `core-harness` and `renga` are not touched in the initial implementation.

---

## 1. Background

`claude-org-ja` already has mechanisms to detect and record worker approval waits, judgment waits, CI failures, silent deadlocks, and so on.

- The dispatcher uses `inspect_pane` / `check_messages` / `poll_events` to detect `APPROVAL_BLOCKED`, `ERROR_DETECTED`, `relay_gap_suspected`, `pane_output_without_peer_msg`, and similar conditions.
- The Secretary records worker escalations in `.state/pending_decisions.json`.
- `tools/pr_watch.py` records CI results as `ci_completed` events and also best-effort notifies the renga peer.
- `state.db` is the post-M4 SoT, holding events / runs / worker_dirs / sessions.

However, current notifications are mostly limited to renga-peers channel messages and rendering inside the Secretary pane. When the human is not looking at the terminal, the following genuinely important states are easy to miss.

- A worker stalled waiting for tool approval.
- A worker asked for a judgment but the human did not notice.
- The human already replied but the Secretary has not relayed it to the worker.
- CI failed.
- A worker completed and is waiting for review.
- The pane has output but no peer message has been sent.

The value here is stronger as an attention notification that "calls the human back" than as a dashboard the human has to "go look at." Therefore the main feature is designed not as a dashboard but as a **watcher that alerts the moments a human response is required, via OS notification / sound / fallback bell**.

---

## 2. Goal

Add `claude-org-runtime attention watch` that monitors `.state/state.db` and `.state/pending_decisions.json` and notifies via desktop notification / sound / terminal bell whenever a human response is needed.

Expected command shapes:

```bash
claude-org-runtime attention scan --state-dir .state --dry-run
claude-org-runtime attention watch --state-dir .state
claude-org-runtime attention watch --state-dir .state --config .state/attention.json
```

`scan` evaluates once and exits. `watch` keeps monitoring by polling.

---

## 3. Layer decision

### 3.1 Why this lives in Layer 2 `claude-org-runtime`

The substance of attention notification is not the OS notification itself but **how to interpret claude-org's execution state**.

The runtime is already responsible for:

- the dispatcher CLI,
- worker settings generation,
- bundling the role schema,
- deterministic operations close to worker startup and state recording,
- operational logic carved out of Layer 4.

The inputs the attention watcher reads are close to the runtime's responsibilities.

- `.state/state.db`
- `.state/pending_decisions.json`
- `notify_sent`
- `ci_completed`
- `worker_completed`
- `pr_merged`
- `relay_gap_suspected`
- `pane_output_without_peer_msg`

These are not `core-harness` safety primitives; they are claude-org runtime semantics. So the implementation body belongs in `claude-org-runtime`.

### 3.2 What remains in Layer 4 `claude-org-ja`

`claude-org-ja`, as the consumer / reference distribution, holds:

- Japanese notification templates,
- default config,
- README / getting-started / verification onboarding paths,
- documentation that guides starting the attention watcher from `/org-start`,
- ja-specific troubleshooting.

### 3.3 Why this does not go into `core-harness`

`core-harness` is the low-level safety / audit foundation of the Claude Code harness: permission schema, validator, hook framework, dangerous git/no-verify block, audit primitives, and so on.

Desktop notification / sound / operator attention is closer to UX / runtime operation, not core safety primitives. Putting it here would stretch `core-harness`'s responsibility too far.

We only consider a constrained Layer 1 extraction in the future if multiple harnesses end up needing a shared `AttentionEvent` envelope or dedup/cooldown primitive.

### 3.4 Why this does not go into `renga`

`renga` is a terminal multiplexer + MCP server — a Layer 3 component that provides pane control / peer messaging / screen inspection / event polling.

The attention watcher's input is not renga's live event stream; the persisted `state.db` / `pending_decisions.json` from claude-org is enough. OS notification is not the responsibility of a backend terminal multiplexer.

If a TUI-integrated notification primitive like `renga notify` is needed in the future, that becomes a separate Issue.

---

## 4. Non-goals

- Do not implement OS notifications inside renga itself.
- Do not have the Secretary / Dispatcher prompts directly issue OS notifications.
- Do not make a dashboard the primary UI.
- Do not require external notifications (Slack / Discord / ntfy / Pushover, etc.) in the initial scope.
- Do not notify on every progress event.
- Do not include secrets, diffs, full commands, or long logs in notification bodies.
- Do not stretch `core-harness`'s responsibility into UX / OS integration.

---

## 5. Runtime Issue: attention scan/watch CLI

### Issue title

`claude-org-runtime`: add attention scan/watch CLI for human-required events

### Implementation target

Add the following to `claude-org-runtime`.

```text
claude_org_runtime/attention/
  __init__.py
  cli.py
  config.py
  classifier.py
  readers.py
  dedup.py
  notify.py
  platform.py
```

CLI:

```bash
claude-org-runtime attention scan --state-dir .state --dry-run
claude-org-runtime attention watch --state-dir .state --config .state/attention.json
```

### Inputs

- `.state/state.db`
- `.state/pending_decisions.json`
- optional config JSON (`.state/attention.json`)

### Outputs

- desktop notification
- urgent sound
- terminal bell fallback
- stdout log
- dedup state file (`.state/attention_notified.json`)

### Attention event model

Internally the runtime converts inputs into the following normalized event.

```python
@dataclass(frozen=True)
class AttentionEvent:
    key: str
    kind: str
    severity: Literal["urgent", "normal"]
    title: str
    body: str
    source: str
    task_id: str | None = None
    worker: str | None = None
    created_at: str | None = None
```

`key` is a stable ID used for dedup.

- From a DB event: `event:<events.id>`
- From a pending decision: `pending:<task_id>:<kind>`

### Classification rules

| Input | Condition | Attention kind | Severity |
|---|---|---|---|
| `events` | `event='notify_sent'` and `kind='approval_blocked'` | `approval_blocked` | urgent |
| `events` | `event='notify_sent'` and `kind='relay_gap_suspected'` | `relay_gap_suspected` | urgent |
| `events` | `event='notify_sent'` and `kind='pane_output_without_peer_msg'` | `silent_worker_output` | urgent |
| `events` | `event='ci_completed'` and `status in ('failed','canceled','incomplete')` | `ci_failed` | urgent |
| `events` | `event='worker_completed'` | `worker_completed` | normal |
| `events` | `event='pr_merged'` | `pr_merged` | normal |
| `pending_decisions.json` | pending older than threshold | `pending_decision` | urgent |
| `pending_decisions.json` | user replied but not forwarded older than threshold | `user_reply_not_forwarded` | urgent |

Not notified:

- progress-only events
- `heartbeat`
- raw `anomaly_observed` without a notification path
- duplicate `notify_sent`
- normal worker reports

### Notification backend

Implement without additional dependencies. Subprocess invocations carry a timeout.

| Environment | Desktop | Sound |
|---|---|---|
| macOS | `osascript display notification` | `afplay` if configured, otherwise bell |
| Linux | `notify-send` | `paplay` / `canberra-gtk-play` / bell |
| Windows native | PowerShell `Write-Host` (a defect remained at implementation time: no visible UI. Conversion to real toasts is tracked as a separate follow-up Issue) | PowerShell `[console]::beep` |
| WSL (with `wsl-notify-send.exe`, recommended) | `wsl-notify-send.exe --category <title> <body>` produces a real toast in the Windows notification center | A separate PowerShell `[console]::beep` subprocess (terminal bell is suppressed when the toast succeeds) |
| WSL (only `powershell.exe`, fallback) | PowerShell `Write-Host` (no visible UI, the legacy path uncovered by Issue #25) | PowerShell `[console]::beep` |
| fallback | stdout | terminal bell `\a` |

If no desktop notification backend is available, `watch` still does not crash. It falls back to stdout + bell.

**Implementation reality note (design ↔ implementation drift)**: the initial design described the WSL backend in a single line as "PowerShell via the Windows host," but at implementation time Issue #25 revealed that the `Write-Host` path does not reach the Windows notification center. `claude-org-runtime` PR #27 ([suisya-systems/claude-org-runtime#27](https://github.com/suisya-systems/claude-org-runtime/pull/27)) split it into a 3-step priority chain `wsl-notify-send.exe` → `powershell.exe` → stdout. The Windows native backend carries the same defect and is not fixed by PR #27 (tracked in a separate follow-up Issue). For the operational onboarding path and install instructions, see [`docs/operations/attention-watch.md`](../operations/attention-watch.md) §3.1.

### Config

The runtime owns the config schema and defaults.

```json
{
  "desktop": true,
  "sound": "urgent-only",
  "cooldown_sec": 300,
  "poll_interval_sec": 10,
  "pending_decision_min": 15,
  "user_replied_min": 15,
  "max_title_chars": 80,
  "max_body_chars": 240,
  "notify": {
    "approval_blocked": "urgent",
    "relay_gap_suspected": "urgent",
    "silent_worker_output": "urgent",
    "ci_failed": "urgent",
    "pending_decision": "urgent",
    "user_reply_not_forwarded": "urgent",
    "worker_completed": "normal",
    "pr_merged": "normal"
  }
}
```

Possible values for `sound`:

- `"off"`
- `"urgent-only"`
- `"all"`

### Dedup / cooldown

The runtime manages `.state/attention_notified.json`.

```json
{
  "events": {
    "event:123": "2026-05-12T10:00:00Z"
  },
  "pending": {
    "pending:issue-123:user_reply_not_forwarded": "2026-05-12T10:00:00Z"
  }
}
```

Requirements:

- The same DB event id is notified only once.
- Cooldown applies to pending decisions by `(task_id, kind)`.
- Broken JSON emits a warning and is regenerated.
- Writes to the dedup state are an atomic replace.

### Secret-safe formatting

Notification bodies are short and secret-safe.

- Do not include the full command.
- Do not include diffs / logs / stack traces.
- Do not emit arbitrary fields of `payload_json` directly into the body.
- Keep contents at task id / worker id / PR number / status level.
- Truncate the body at `max_body_chars`.

### Runtime acceptance criteria

- `claude-org-runtime attention scan --state-dir <fixture> --dry-run` emits attention events from a fake state.
- `notify_sent kind=approval_blocked` is classified as urgent.
- `ci_completed status=failed` is classified as urgent.
- `worker_completed` is classified as normal.
- Progress-only events are ignored.
- Stale pending decisions are classified as urgent.
- User replied but not forwarded is classified as urgent.
- Event id dedup works.
- Pending decision cooldown works.
- When no desktop backend is available, it falls back to stdout + bell.
- macOS / Linux / Windows / WSL backend selection is unit tested.
- `--dry-run` does not invoke OS notification subprocesses.
- Recovery from a broken `.state/attention_notified.json` works.

---

## 6. Runtime Issue: locale/template override

### Issue title

`claude-org-runtime`: support attention notification templates and locale overrides

### Background

The runtime owns the implementation body, but we do not want to hard-code notification text to `claude-org-ja`, the Japanese distribution. The runtime carries neutral default titles/bodies, and Layer 4 needs to override them via a locale config.

### Implementation direction

Add `templates` to the runtime config.

```json
{
  "templates": {
    "approval_blocked": {
      "title": "Worker approval required",
      "body": "{worker} is waiting for approval."
    },
    "ci_failed": {
      "title": "CI failed",
      "body": "PR #{pr} finished with {status}."
    }
  }
}
```

Template placeholders are allowlisted.

Allowed placeholders:

- `{task_id}`
- `{worker}`
- `{kind}`
- `{status}`
- `{pr}`
- `{summary}`

Unknown placeholders are either left as literals (not raised as errors) or trigger a warning + fallback template. The fallback template is recommended for the initial implementation.

### Acceptance criteria

- Template overrides in the config are reflected in title/body.
- The watcher does not crash on unknown placeholders.
- Template-derived bodies are also truncated at `max_title_chars` / `max_body_chars`.
- The ja-side config can supply Japanese text.

---

## 7. ja Issue: default config and documentation

### Issue title

`claude-org-ja`: add attention watcher config, docs, and README positioning

### Implementation target

Add / update the following on the `claude-org-ja` side.

```text
.state/attention.example.json
docs/operations/attention-watch.md
docs/verification.md
README.md
.claude/skills/org-start/SKILL.md
```

Because `.state/` is gitignored, the example should live at a tracked path. Candidates:

```text
tools/templates/attention.example.json
```

or:

```text
docs/operations/attention.example.json
```

Following the existing template placement, `tools/templates/attention.example.json` is recommended.

### README positioning

Do not pitch the README's value proposition solely on "AI organization operation." Lean into the following pains.

- Be able to come back the moment a Claude worker is waiting on a human.
- Do not miss approval / judgment / CI failure / silent stop.
- No need to keep watching multiple workers all the time.

That said, do not remove the existing 4-layer architecture or Secretary/Dispatcher/Curator/Worker description. Move the front-door pitch toward attention / ops and place the organizational structure as a mechanism in a later section.

### org-start guidance

Add startup guidance for the attention watcher to the `/org-start` procedure.

Example:

```bash
claude-org-runtime attention watch --state-dir .state --config .state/attention.json
```

That said, do not make auto-start mandatory in the first iteration. OS notifications are environment-dependent, so the user should be able to enable them explicitly.

### ja default template

The ja config ships with short Japanese text.

Example:

```json
{
  "templates": {
    "approval_blocked": {
      "title": "ワーカーが承認待ちです",
      "body": "{worker} が承認待ちで停止しています。"
    },
    "ci_failed": {
      "title": "CI が失敗しました",
      "body": "PR #{pr} の CI が {status} で完了しました。"
    },
    "pending_decision": {
      "title": "判断待ちがあります",
      "body": "{task_id} が人間の判断を待っています。"
    },
    "user_reply_not_forwarded": {
      "title": "返答の転送待ちです",
      "body": "{task_id} でユーザー返答が worker に未転送です。"
    }
  }
}
```

### ja acceptance criteria

- The README documents the value of the attention watcher and a startup example.
- `docs/operations/attention-watch.md` covers OS-specific fallback and troubleshooting.
- `docs/verification.md` covers the `scan --dry-run` verification procedure.
- `tools/templates/attention.example.json` carries the ja default config.
- The `/org-start` docs include watcher startup guidance.

---

## 8. ja Issue: integration verification fixtures

### Issue title

`claude-org-ja`: add fixtures for attention watcher integration verification

### Background

Unit tests on the runtime side alone make it hard to notice when ja's event vocabulary drifts from the real `.state` shape. We also place semantic fixtures on the `claude-org-ja` side and verify integration with the runtime CLI.

### Implementation target

```text
tests/fixtures/attention/
  state.db
  pending_decisions.json
  expected_scan.json
tests/test_attention_runtime_integration.py
```

Whether the `state.db` fixture is held as a binary or generated from schema inside the test is decided at implementation time. The test-generation approach has higher maintainability.

### Acceptance criteria

- The fixture's `notify_sent approval_blocked` produces the expected urgent event.
- The fixture's `ci_completed failed` produces the expected urgent event.
- The fixture's stale `pending_decisions.json` produces the expected urgent event.
- The output of `claude-org-runtime attention scan --dry-run --json` matches a golden file.

---

## 9. Future Issue: optional external notification sinks

### Issue title

`claude-org-runtime`: optional external attention sinks for Slack/Discord/ntfy

### Background

The initial implementation is confined to local notification. External notification carries secret / privacy / network configuration concerns, so it is not made mandatory.

### Direction

Add external sinks as optional only after local notification has stabilized.

Candidates:

- Slack webhook
- Discord webhook
- ntfy.sh
- Gotify
- Pushover

External sinks are always opt-in. Their notification bodies are even shorter than local notifications, and they share the secret-safe formatting.

---

## 10. Overall acceptance criteria

- The runtime ships `claude-org-runtime attention scan/watch`.
- `claude-org-runtime attention scan --state-dir .state --dry-run` can be run from the ja repo.
- approval blocked / relay gap / silent worker output / CI failed / pending decision become urgent notifications.
- worker completed / pr merged become normal notifications.
- Progress-style events are not notified.
- Even in environments where OS notifications are unavailable, it falls back to stdout + terminal bell.
- With urgent-only sound, only urgent events make a sound.
- Dedup / cooldown prevent the same event from sounding repeatedly.
- Notification bodies are secret-safe and short.
- The ja side has Japanese config and operational procedures.
- core-harness / renga are not modified.

---

## 11. Open questions

1. Should `watch` auto-start from `/org-start`, or remain an explicit start?
   - Explicit start is recommended for the first iteration. OS notifications are environment-dependent, and sound going off without consent is easily unpleasant.
2. Should `worker_completed` be included in normal desktop notifications?
   - Included in the initial defaults. But sound does not fire.
3. The default for `pending_decision_min`.
   - Match the existing dispatcher monitoring's 15 minutes.
4. How to tolerate `notify_sent` event payload schema drift?
   - The runtime classifier tolerates missing fields and reconstructs from at least `event` / `kind` / `payload_json`.
5. Behavior on first launch when `state.db` does not exist.
   - No-op, not a warning. `scan` / `watch` do not crash.

---

## 12. Severity taxonomy and TTL ladder

> **Implementation reality note (design ↔ implementation drift, Part B)**: the Config example in §5 preserves the design snapshot from the initial version of this document. The real runtime defaults were updated by Issue #26 / `claude-org-runtime` PR #29 ([suisya-systems/claude-org-runtime#29](https://github.com/suisya-systems/claude-org-runtime/pull/29)): (a) the severity of 6 anomaly kinds was demoted from `urgent` to `normal`, and (b) two new TTL keys `pending_decision_max` / `pending_decision_drop` were added. This section is the SoT describing the rationale and taxonomy for that update. For the Layer 4 ja distribution's reflected defaults, see [`tools/templates/attention.example.json`](../../tools/templates/attention.example.json); for the operations-perspective table and tuning advice, see [`docs/operations/attention-watch.md`](../operations/attention-watch.md) §4.1 / §4.2.

### 12.1 Anomaly / precursor vs action-required dichotomy

attention events split into two by **"whether recovery is possible via a path other than the user."** This is also the basis for revisiting the severity defaults in Issue #26 Part B.

- **action-required moments (urgent default)** — events where the user is the only recovery path. The runtime / dispatcher / Secretary can only detect and notify; releasing the state requires human intervention.
  - `approval_blocked`: tool approval / sensitive op approval — cannot proceed without the user's reply
  - `ci_failed`: CI failure — the decision to re-push / fix is up to the user
  - `pending_decision`: a worker asks for a judgment — the Secretary is a relay, and the human is the judgment layer (CLAUDE.md § "judgment escalations go to the human")
  - `user_reply_not_forwarded`: the user replied but the worker has not received it — visibility into a Secretary operational gap
  - `pane_crashed`: a pane terminated unexpectedly — the decision to restart is up to the user

- **anomaly / precursor signals (normal default)** — best-effort detections, events that may self-recover on the worker / dispatcher / runtime side. To avoid urgent muting (where the alarm rings every day and ends up being uniformly ignored), all 6 of these were demoted to normal in Part B.
  - `relay_gap_suspected`: dispatcher's SECRETARY_RELAY_GAP_SUSPECTED precursor detection. Often transient on the Secretary side in the short term
  - `silent_worker_output`: pane has output but no peer message has arrived — may be flushed on the worker side
  - `pane_silent`: pane is unresponsive, including silence during tool execution. Not necessarily a full stall
  - `worker_stalled`: heuristic estimate that worker progress has stagnated — may self-recover
  - `worker_not_reported`: no report has arrived from the worker — may just be a delay in the short term
  - `worker_error`: an error report from the worker — may be retried / recovered internally

`worker_completed` / `pr_merged` are treated as **progress events**: normal default, but taxonomically a third independent category (no immediate action required, yet a trigger for review / cleanup).

### 12.2 4-step TTL ladder for pending_decisions

If a judgment escalation stays "urgent forever once urgent," in operations where unresolved items pile up, the watcher itself ends up muted (noise → uniformly ignored), a failure mode. To avoid this, runtime PR #29 introduced a ladder that decays the elapsed time of a pending decision through 4 stages.

| Elapsed time | Stage | Behavior |
|---|---|---|
| `t < pending_decision_min` | grace | No event fired. A grace window on the assumption that the Secretary can relay to a human within a short time |
| `pending_decision_min ≤ t < pending_decision_max` | urgent | desktop notification + urgent sound + terminal bell |
| `pending_decision_max ≤ t < pending_decision_drop` | normal / visual-only | The desktop notification fires but no urgent sound. A visual remnant marking long-unresolved items |
| `t ≥ pending_decision_drop` | suppressed | Both desktop and sound are suppressed; only `attention scan --json` output retains it |

The design aim is **"the decay curve preserves the signal while suppressing dead state":**

- The **first 24 hours (default)** of a new pending is the urgent window — guaranteed audiovisual notice.
- After 24h, it does not disappear from the dashboard / `--json` output but remains as normal/visual. A state in which **the fact that the long-term backlog is non-zero** stays visible.
- Past 7 days, the dead state is suppressed from notification surfaces and only accessible via audit/dashboard paths. This prevents noise from growing linearly.

Consistency conditions (validated in the runtime `attention/config.py`):

- `pending_decision_min < pending_decision_max < pending_decision_drop`
- `user_replied_min < pending_decision_max`

These are returned as validation errors at load time, so typos in Layer 4 / user overlays are caught early.
