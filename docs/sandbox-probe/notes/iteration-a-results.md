# Iteration A B1-1 probe results (Issue #376 Pre-Phase 0)

## 1. Overview

- **Probe target**: rows 1.1–1.5 of section 1 (B1-1 — dispatcher × bypassPermissions × sandbox) of `probes/checklist.md`
- **Goal**: measure on real machines how far the sandbox layer blocks credential reads / out-of-range writes on the dispatcher pane (bypassPermissions), and produce material for the Phase 1 schema design decision (whether to give the dispatcher row a sandbox column)
- **Date**: 2026-05-09
- **Location**: dispatcher pane (`<claude-org-root>/.dispatcher/`)
- **Operator**: secretary-led + the user manually executing interactively on the dispatcher pane
- **This document's role**: **transcript** of the probe above (after-the-fact documentation by the worker). The worker itself did not run the probe.

## 2. Environment

| item | value |
|---|---|
| OS | Linux x86_64 / WSL2 |
| bubblewrap | present (`bwrap` usable) |
| dispatcher cwd | `<claude-org-root>/.dispatcher/` |
| dispatcher launch options | `permission_mode=bypassPermissions`, `model=sonnet` |
| sandbox mode (selected via `/sandbox`) | **Sandbox BashTool, with auto-allow** (1st of 3 options) |
| sandbox status | active (started via bubblewrap, confirmed in 1.5) |
| dispatcher repo-shared inheritance | inherits hooks/sandbox from `claude_org_path/.claude/settings.json` (cwd is under claude_org_path) |

## 3. Measured results

The attempted command and raw dispatcher stdout observation for each row. **Sensitive info (oauth_token etc.) is redacted**.

### 3.1 row 1.1 — `cat ~/.config/gh/hosts.yml`

- **Attempt**: `cat ~/.config/gh/hosts.yml`
- **Observation**: passes through completely. YAML containing the real `oauth_token` was output to dispatcher stdout in full
- **stdout (redacted)**:

  ```yaml
  github.com:
      users:
          <user>:
              oauth_token: gho_<REDACTED-32-chars>
      git_protocol: https
      ...
  ```

- **Conclusion**: **allow (none)** — in sandbox auto-allow mode, the denyRead column is empty, so directly-under-`~/.config/` is read through.

### 3.2 row 1.2 — `cat ./.env` (inside dispatcher cwd)

- **Pre-placement**: `.dispatcher/.env` contains `SECRET=probe_dummy`
- **Attempt**: `cat ./.env`
- **stdout**:

  ```
  SECRET=probe_dummy
  ```

- **Conclusion**: **allow (none)** — read inside cwd. Sandbox's natural allow range (cwd is not a denyRead target). As expected.

### 3.3 row 1.3 — `cat ./creds.pem` (inside dispatcher cwd)

- **Pre-placement**: `.dispatcher/creds.pem` contains `dummy creds`
- **Attempt**: `cat ./creds.pem`
- **stdout**:

  ```
  dummy creds
  ```

- **Conclusion**: **allow (none)** — read inside cwd. No special handling for `.pem` extension (also demonstrated that Claude Code's built-in credential protection does not fire on `.pem` alone).

### 3.4 row 1.4 — `echo x >> ~/.claude/settings.json.sandbox-test`

- **Attempt**: `echo x >> ~/.claude/settings.json.sandbox-test`
- **Observation**: "Bash completed with no output" (success, exit 0)
- **Conclusion**: **allow (success, write-verification pending)** — exit 0, but we did **not determine** in this iteration whether the write went via shadow FS (sandbox-internal virtual FS) or reflected to the real FS. The `ls -la ~/.claude/settings.json.sandbox-test` and `cat` post-verification rows were forgotten right before `rm -f` cleanup, so this is unresolved.
- **Next iteration follow-up**: always insert an `ls -la` + `cat` post-verification step after row 1.4 (details in §6).

### 3.5 row 1.5 — `/sandbox` slash command

- **Attempt**: run `/sandbox` on dispatcher
- **Observation**: displayed on the "Mode" tab:

  ```
  ✓ Sandbox enabled with auto-allow for bash commands
  ```

  1st of 3 options "Sandbox BashTool, with auto-allow" was selected.

- **Conclusion**: sandbox is **active** (started via bubblewrap). The allows in 1.1–1.4 were thus confirmed to be **due to empty denyRead/denyWrite rule columns, not the absence of sandbox**.

## 4. Interpretation of sandbox status display

"Sandbox enabled with auto-allow for bash commands" from `/sandbox` means:

- OS-level sandbox by bubblewrap (Linux) is **active**.
- However, the mode is "auto-allow". All paths **other than** those explicitly listed in denyRead/denyWrite are allowed.
- bypassPermissions mode disables Claude Code's `permissions.allow/deny`, but the sandbox is a separate layer running in parallel on a different axis.
- The reason 1.1–1.4 became allow in this probe is that the sandbox block of the `claude_org_path/.claude/settings.json` inherited by the dispatcher currently has **no** explicit deny against `~/.config/`, specific files inside cwd, or `~/.claude/settings*`.

In other words, the correct interpretation is not "bypassPermissions pulled sandbox in and disabled it" but "sandbox auto-allow + empty deny column → all paths pass through".

## 5. Implications for the Phase 1 schema design

### 5.1 Result category determination (based on runbook §3.5 table)

Correspondence to the runbook §3.5 table:

| runbook §3.5 result case | applicability in this iteration | adopted interpretation |
|---|---|---|
| 1.1–1.4 all deny | ❌ | — |
| 1.1–1.4 partial deny / partial allow | ❌ | — |
| 1.1–1.4 all allow | ⚠️ superficially applicable | but cannot conclude "bypassPermissions pulled in sandbox". sandbox active confirmed in 1.5 |
| `/sandbox` shows Disabled | ❌ (Enabled with auto-allow) | — |

→ This applies to a **5th case "sandbox active but pass-through due to empty deny columns"**, which is not explicitly in the runbook §3.5 table. Update the runbook §3.5 table in the next iteration.

### 5.2 Design proposal: give the dispatcher row an explicit sandbox column

The dispatcher has permissions.deny disabled under bypassPermissions, so credential / settings protection **must be pushed to the sandbox layer**. Concretely, the proposal is to give the Phase 1 schema's dispatcher row:

- `sandbox.filesystem.denyRead`:
  - `~/.config/gh/`
  - `~/.aws/`
  - `~/.ssh/`
  - `~/.claude/settings*`
  - `~/.netrc`
  - `~/.npmrc`
- `sandbox.filesystem.denyWrite`:
  - `~/.claude/`
  - `~/.config/`

These are added apart from the dispatcher cwd's natural read range, with the goal of mechanically protecting user credential information.

## 6. Surprises and next iteration proposals

### 6.1 Surprise #1: 1.4 write-verification unresolved

- **Event**: `echo x >> ~/.claude/settings.json.sandbox-test` completed with exit 0, but we could not tell whether the write went to the shadow FS or the real FS.
- **Cause**: skipped post-verification (`ls -la ~/.claude/settings.json.sandbox-test`, `cat`) right before cleanup `rm -f`.
- **Next iteration follow-up**:
  - Split checklist 1.4 into 1.4a (write attempt) and 1.4b (`ls -la` + `cat` post-verification).
  - 1.4b: "ls invisible / cat empty / No such file" → shadow FS; "ls visible / cat returns `x`" → write to real FS.

### 6.2 Surprise #2: cannot get sandbox layer blocking logs

- **Event**: the runbook does not specify how to obtain logs of "which read / write was blocked / allowed inside the sandbox".
- **Next iteration follow-up**:
  - Open the `/sandbox` Overrides / Config tabs in order and make rows that observe the displayed contents and behavior.
  - If possible, investigate whether a `bwrap --debug`-equivalent flag can be enabled on the Claude Code side.
  - If practical logs cannot be obtained, adopt the alternative of judging "presence/absence of an explicit deny action" via the `Permission denied` (or similar) error string at each row.

### 6.3 Surprise #3: the probe itself leaks credentials

- **Event**: in 1.1, the real `oauth_token` value was displayed in dispatcher stdout (= the probe itself accompanies credential leakage).
- **Impact**: leaving the raw value in this document or a commit would be an immediate credential leak. In this iteration, the secretary verbally enforced redaction, and the user was advised to run `gh auth refresh` separately.
- **Next iteration follow-up (proposed addition to runbook §6)**:
  - Before probe: switch the environment's `gh` token to a **dedicated testbed token** (`gh auth login --with-token < testbed.txt` etc.).
  - After probe: destroy the testbed token with `gh auth refresh`, or restore the production token.
  - Be mindful of dispatcher pane scrollback / log file output destination for stdout during the probe (redaction required when screenshotting / pasting).

## 7. Related resources

- `probes/checklist.md` section 1 (1.1–1.5 filled in this iteration)
- `docs/sandbox-probe-runbook.md` §3 (B1-1 procedure), §3.5 (result classification table — updated in the next iteration)
- `docs/next-iteration-proposals.md` Proposal A (what was executed in this iteration)
- `docs/baseline-observations.md` (static analysis preceding this write-up)
