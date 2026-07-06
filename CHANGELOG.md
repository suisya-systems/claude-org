# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-06

First stable release of **claude-org-ja**, the Japanese edition of the Claude Code
multi-role AI organization harness. This release consolidates the 426 commits made
since the initial `v0.1.0` tag into a production-ready harness: a role-based
organization (Lead / Dispatcher / Curator / Worker) driven over a pluggable peer
transport, with resident monitoring, human-gated escalation, next-work triage, and
an attention-notification pipeline. Highlights below are grouped by theme rather
than listed commit-by-commit.

### Added

- **Broker transport layer (opt-in, rollback-safe).** Introduced a second peer
  transport (`org-broker`) alongside `renga`. `renga` remains the default transport
  when `ORG_TRANSPORT` is unset (default behavior unchanged); setting
  `ORG_TRANSPORT=broker` opts in to the broker and is reversible at any time. Added
  broker authentication and delivery (Surface 8 of the backend-interface contract,
  ratified after the Epic #6 dogfood), a push-first receive model with pane-local
  nudges + `check_messages`, folder-trust spawn approval, and broker-specific error
  branches. Includes the broker dogfood operations runbook, a `renga`-decoupling
  design (Plan B: terminal adapter), and a conversational transport-switch UX that
  keeps the raw `ORG_TRANSPORT` toggle hidden behind the Secretary and `org-start`.
- **Work-discovery triage.** New deterministic scan tool (`tools/work_discovery_scan.py`)
  and `/work-discovery` skill that surface "next-work candidates (N + 1 recommendation)"
  to the human. Adds a repo-calibrated effort-learning framework with a correlation
  gate, cross-repository dependency resolution (`owner/repo#N`), and post-merge
  proactive next-dispatch so the Lead offers candidates automatically after a merge.
- **Attention notification pipeline.** Added the `/org-attention-start` and
  `/org-attention-stop` skills to run a resident watcher that raises active OS
  notifications (sound/beep) for awaiting-approval, awaiting-decision, and CI-failure
  states. Instrumented `awaiting_user` emission at the four Secretary gates
  (worker-completed, CI-green merge gate, escalation-to-user ask-time, and
  escalation-reply-forward) and added a resident watcher for stalled Secretary-bound
  broker messages (`org-start` Block C3).
- **Dispatcher self-repair view.** A read-only control-plane view over broker/tmux
  that keeps active workers, the polling cursor, and pending escalations continuously
  visible, plus a dispatcher-view operations guide.
- **Dispatcher handover / resume protocol.** New `/dispatcher-handover` and
  `/dispatcher-resume` skills that persist monitoring state to a handover file and
  bring the Dispatcher back in a fresh session without closing its pane, minimizing
  the monitoring gap when its context grows long.
- **Two-lane task routing.** Codified a lightweight subagent lane (very small,
  single-file, no-escalation tasks handled directly by the Lead via a background
  worktree subagent with an in-loop Codex gate) as an exception to the
  delegate-everything rule, with the heavyweight Worker lane as the default fallback.
- **On-demand Curator.** Replaced the resident `/loop 30m` Curator with a
  threshold-triggered spawn at worker close (`tools/check_curate_threshold.py`),
  reducing idle overhead.
- **Team-adoption metrics CLI.** Added `tools/org_metrics_report.py` for reporting
  delegation throughput and outcomes to teams evaluating the harness.
- **Operator skills.** Added `/org-attach` (generate read-only tmux attach commands
  for org panes), `/pr-watch-pane` (run PR CI monitoring in a dedicated broker tmux
  pane, outside the sandbox and independent of the Lead session lifetime),
  `/org-conveyor` (human-scope-approved self-driving belt that always stops at each
  merge gate), and `/org-escalation` (canonical escalate-to-human flow).
- **State-drift detection.** Added detection for stale queued runs and DB/worker-file
  drift, plus lifecycle tests locking the canonical state-semantics contract.
- **Auto-mirror CI pipeline.** Added the workflow that mirrors runtime and translation
  changes from the Japanese upstream into this repository (warn-only P1 → enforcing P2),
  including the `JA_REPO` wiring needed to fetch upstream PR files.
- **English documentation set.** Translated the full public-facing documentation
  from the Japanese source of truth: README, getting-started, verification, the
  `docs/contracts/**` backend-interface contract, `docs/sandbox-probe/**`, and the
  `.claude/skills/**` skill prose, along with the attention-notification and
  broker-dogfood design/operations docs.

### Changed

- **Lead role carve-out (Issue #320).** Split the Lead's operational responsibilities
  into dedicated skills — `/org-delegate` (delegation), `/org-escalation` (human
  escalation + pending-decisions register), and `/org-pull-request` (push / PR / CI
  / merge close-out) — while keeping the single Lead role.
- **Startup entrypoint and README.** Rebuilt the README as a concise public-facing
  landing page and made `claude-org-runtime org up` the primary documented way to
  bring the org up, with `renga` presented as an alternative launcher for a
  full-screen multi-pane view. (This is the launcher entrypoint only; it does not
  change the peer-transport default, which remains `renga` — see Added.)
- **Codex self-review switched to the review surface.** Moved the self-review source
  of truth from long inline prompts to `codex exec review` (method A), giving roughly
  2× throughput on small/medium diffs at safe-side parity; pinned the canonical
  `codex exec` invocation in the instruction template.
- **Worker brief hardening.** Baked in a default Codex round cap (3) with an
  over-limit reporting rule, a `PYTHONPATH=src` / no-editable-install convention for
  src-layout projects, a Windows CLI ASCII-output check, unified Windows Python launch
  commands, and a mandatory human-comprehension summary in `full` completion reports.
- **Installers made lighter.** Demoted `renga` (and `node`/`npm`) from required to
  optional in the installers, added Git Bash for Windows detection, and added a
  `py -3` fallback to the PowerShell installer's Python detection.
- **Foreground subagent launches blocked.** Added a `PreToolUse` hook that uniformly
  blocks synchronous (foreground) Agent launches to preserve the Lead's responsiveness.
- **Runtime pins.** Advanced the `claude-org-runtime` pin to `>=0.1.36,<0.2` (via a
  series of paired schema/fixture updates), and kept `tools/org_extension_schema.json`
  and worker settings generation in sync with the runtime schema.
- **Markdown conventions.** Standardized documentation link notation with a validation
  script, and moved skill prose to a source/generator (`SKILL.md.in`) model with a
  pre-commit drift guard.
- **Guard scoping.** Scoped the block-org-structure guard to the claude-org repo so
  workers may write to a target repo's `.claude/` directory.

### Fixed

- **Dispatcher monitoring accuracy.** Permanently fixed the `dispatcher-resume`
  `/loop 3m` self-recursion, suppressed stall-detection false positives (normalized
  full-visible-line hashing + capped new-spinner suppression), resolved idle
  misclassification via the decision-register gate, and expanded ERROR detection to
  cover 529/transient codes and spinner age.
- **Retro-gate acknowledgement.** Fixed ack-guard edge cases around polite negations
  and question-terminated phrasing, and added "merged"/"completed" to the default ack
  patterns.
- **Broker delivery correctness.** Made `peer_notify` transport-neutral so Secretary
  notifications arrive under the broker, wired `ORG_BROKER_STATE_DIR` into the broker
  send path, and structurally blocked live broker sends during tests via a
  package-level hermetic-env guard.
- **PR watch reliability.** Made `pr-watch.sh`/`.ps1` self re-exec to absorb
  cwd/argument/stdin mix-ups, converted merge-watch to a head-poll loop that
  re-observes new CI, and separated a checks-fetch failure into an `indeterminate`
  state so a real red no longer degrades into a stalled/incomplete watch.
- **Worker layout & close-phase cleanup.** Unified Pattern A/B/C worker-directory
  handling with atomic apply and a repo-clone fallback, fetched `origin` before
  Pattern B worktree creation so it branches off the latest `main`, made Pattern C
  `CLAUDE.local.md` cleanup order-independent, and stopped self-edit boilerplate from
  leaking into normal worker briefs.
- **Work-discovery robustness.** Fixed a `cp932` `UnicodeDecodeError` → `NoneType`
  cascade in the scan, made stdout strings ASCII-safe, and joined
  `closingIssuesReferences` by `(repo, number)` to exclude cross-repo closings from
  effort samples.
- **Metrics tooling.** Gave `org_metrics_report` an actionable exit-2 on a bad DB and
  stabilized its JSON type/key-set output.
- **Curator robustness.** Fixed the curate-threshold code-fence mismatch and hardened
  the `org-curate` marker assignment against `mv -i` alias and zsh history-expansion
  pitfalls.
- **Environment resolution.** Added a repo `.venv` fallback to `segment-split.sh`
  core-harness resolution, permanently resolving fail-closed Bash on panes that do not
  inherit the venv.

[1.0.0]: https://github.com/suisya-systems/claude-org/releases/tag/v1.0.0
