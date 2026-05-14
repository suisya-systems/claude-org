# Linux / WSL2 sandbox verification runbook

> **Scope**: A procedural guide for verifying on real hardware that
> claude-org-ja's Layer 2 / 3 / 4 defenses **fire as designed** for each
> role × pattern combination, on Linux native and WSL2 environments.
>
> **Position of this document**: This is not the source of truth for the
> design — it is the **operational / release-time verification
> checklist**. For *what* is being prevented and *why*, refer to the SoTs
> below. This runbook addresses only "how to confirm."
>
> - Structure of Layer 2 / 3 / 4 and the prescriptive surface per
>   role × pattern:
>   [`docs/contracts/role-pattern-sandbox-contract.md`](../contracts/role-pattern-sandbox-contract.md)
> - bwrap launcher protocol surface (case A bootstrap fallback /
>   `failIfUnavailable` / `sandbox_deny_skipped` event):
>   [`docs/contracts/sandbox-launcher-contract.md`](../contracts/sandbox-launcher-contract.md)
> - History of the existing handcraft profile + Pre-Phase 0 spike:
>   [`docs/sandbox-probe/notes/sandbox-probe-runbook.md`](../sandbox-probe/notes/sandbox-probe-runbook.md)
>
> **Refs**: claude-org-ja#380. Phase 2 hook attach: claude-org-ja#420.
> Phase 3 case A implementation follow-up: claude-org-ja#392.

---

## 0. Verification scope and prerequisites

| Item | Value |
|---|---|
| Target OS | Linux x86_64 / WSL2 (Ubuntu 22.04 or later assumed) |
| Target Claude Code | Build with sandbox feature support (a build whose `claude --version` reads `sandbox.filesystem.*`) |
| Target runtime | `claude-org-runtime` ≥0.1.9, <0.2 (pinned in [`requirements.txt`](../../requirements.txt)) |
| Target schema | [`tools/org_extension_schema.json`](../../tools/org_extension_schema.json) Phase 1 PR4 or later, which has `worker_roles[*].sandbox_by_pattern` |
| Target hooks | [`.hooks/`](../../.hooks/) Phase 2 hook attach (PR #420) or later |
| **Out of scope** | macOS (no sandbox-exec / `bwrap`), Windows native PowerShell, nested sandboxes inside Codespaces / DevContainer, launcher-side implementation of case A bootstrap fallback (managed separately under #392) |

In environments where `bubblewrap` (`bwrap`) is missing or fails to
start, Layer 3 fall-opens (§5). There are cases in which it is
acceptable to verify only Layer 2 / Layer 4, but **if you are running
full verification that includes Layer 3, the prerequisite installs in §1
are mandatory**. Because seeing "all rows passed" while in a fall-open
state merely means sandbox is disabled, always confirm the `/sandbox`
status first via §2.

---

## 1. Prerequisite installs / environment checks

### 1.1 Required command availability check

```bash
command -v bwrap   # /usr/bin/bwrap
command -v socat   # /usr/bin/socat
command -v jq      # /usr/bin/jq
command -v claude  # ~/.local/bin/claude etc.
```

If `bwrap` / `socat` are not installed (Ubuntu / Debian):

```bash
sudo apt-get update
sudo apt-get install -y bubblewrap socat jq
```

On WSL2, if `bwrap` fails to start with `Operation not permitted`,
verify that user namespaces are enabled:

```bash
sysctl kernel.unprivileged_userns_clone   # expected: 1
unshare --user --pid echo ok              # "ok" → user namespaces OK
```

### 1.2 Version check

```bash
bwrap --version   # bubblewrap 0.5.x to 0.10.x is the contract scope
claude --version

# Check the claude-org-runtime version by invoking the CLI directly.
# `pip show` may peek at a different site-packages than the CLI the
# operator actually invokes, so it can return a stale value and
# mislead about the effective version used by `settings generate`
# (round 3 review).
# Prefer venv → CLI on PATH → fall back to pip show only if neither
# is reachable.
.venv/bin/claude-org-runtime --version 2>/dev/null \
  || claude-org-runtime --version 2>/dev/null \
  || pip show claude-org-runtime | grep -E '^(Name|Version)'

jq --version
```

If `claude-org-runtime` does not satisfy `>=0.1.9`, the emit logic that
consumes `worker_roles[*].sandbox_by_pattern` is old, and **Layer 3
sandbox blocks are highly likely not to be written to
`.claude/settings.local.json`**. In that case, update with
`pip install -U 'claude-org-runtime>=0.1.9,<0.2'` (consistent with
[`requirements.txt`](../../requirements.txt)) and re-run the
verification. If you treat verification as complete with the old
version still in place, the Layer 3 rows in §4 / §5 / §6 are merely
observing "a silent fall-open caused by sandbox not being emitted."

### 1.3 Automated check

```bash
bash tests/sandbox/test_role_pattern_smoke.sh
```

[`tests/sandbox/test_role_pattern_smoke.sh`](../../tests/sandbox/test_role_pattern_smoke.sh)
batches together the scriptable assertions from this runbook. Coverage
and granularity:

| Runbook §  | Automation | Content |
|---|---|---|
| §1.1 jq    | hard fail | If absent the smoke cannot continue (hooks depend on jq) |
| §1.1 bwrap | soft skip | Absence is detected and reported as `# SKIP` (Layer 3 fall-open warning) |
| §1.1 socat | soft skip | Same as above |
| §1.1 claude | soft skip | Absence detected; E2E spawn (§3) is done manually from this runbook |
| §1.2 claude-org-runtime version | soft skip | Confirms `>=0.1.9,<0.2` via `claude-org-runtime --version` (venv priority → PATH). Falls back to `pip show` only if the CLI is unreachable (output is labeled with the source). `# SKIP` if it does not meet the bound |
| §3 schema consistency | hard | Asserts presence of `worker_roles.default.sandbox_by_pattern` / Layer 2 mirror / Phase 2 hook attach |
| §4 hook smoke (incl. §6.1 / §6.2) | hard | Directly invokes `.hooks/*` with PreToolUse JSON and confirms exit 0 / 2 |
| §2 `/sandbox` display, §3 spawn E2E, §4 commit smoke, §5 syscall-level deny | manual | Requires actually starting Claude Code / a bwrap subprocess, executed manually from this runbook |

The soft-skip rows tolerate the current CI environment
([`.github/workflows/tests.yml`](../../.github/workflows/tests.yml))
installing only `jq`. Operationally this means the convention is "the
operator must check §1.1 / §1.2 on real hardware before running full
Layer 3 verification." Do not treat a smoke result that includes SKIP
rows as a pass and fill in §7 (verification-complete judgment) of this
runbook — SKIP is an instruction to fill in manually.

---

## 2. `/sandbox` status check

After starting Claude Code, run `/sandbox` in each role's pane and
confirm:

| Display item | Expected value |
|---|---|
| Sandbox status | `Enabled` (if Disabled, `bwrap` is missing per §1.1 / Layer 3 fail-open) |
| Sandbox profile / `additionalDirectories` | Matches the prescribed surface in §3 / §4 of [`docs/contracts/role-pattern-sandbox-contract.md`](../contracts/role-pattern-sandbox-contract.md) for each role × pattern |
| `denyRead` | The credential set per §3.1.1 / §4.1.1 of the same contract (accounting for the WSL adaptation suppression exception in §5.1) |
| case-A `suppressed_entries` | Normally empty. If anything appears, case A is outside expectations per §5.2 — read alongside the `sandbox_deny_skipped` event in `.state/state.db` |
| case-E `suppressed_entries` | On WSL it is normal for `~/.aws/**` / `~/.ssh/**` etc. to be suppressed. `$comment` displays `platform=wsl, layer-3 entries suppressed: [...]` (see [`docs/contracts/sandbox-launcher-contract.md`](../contracts/sandbox-launcher-contract.md) §3.4) |
| `failIfUnavailable` | Per the table in each role's §4.2. dispatcher's **prescribed value is `true`**, but the current schema emits `false` — a known gap (same §4.2 "Prescribed (not yet implemented)") |

If `/sandbox` returns `Disabled`, **stop verification there**, resolve
the `bwrap` install / startup blocker per §1.1, then re-run. An
observation that "Layer 3 deny is working" while in a fall-open state
is meaningless.

---

## 3. Secretary → Dispatcher → Worker spawn E2E checklist

Run the following checks in order immediately after `/org-start`. Each
row's check command is intended to be run in the operator's shell.

### 3.1 Secretary pane

```bash
# 1. cwd is under claude_org_path
pwd     # project root, e.g. /home/<user>/work/org/claude-org-ja

# 2. .claude/settings.local.json has been generated from the secretary template
jq '.permissions.allow | length, .permissions.deny | length' \
   .claude/settings.local.json
# Both allow / deny non-empty (empty → claude-org-runtime settings generate not yet run)

# 3. Whether the sandbox block is emitted (Phase 1 PR3 = roles.secretary.sandbox)
jq 'has("sandbox")' .claude/settings.local.json
# Expected true. If false, may indicate claude-org-runtime <0.1.9 (see §1.2)
```

Run `/sandbox` in the secretary pane and confirm the display per the
§2 table.

### 3.2 Dispatcher pane

The dispatcher starts with `<claude_org_path>/.dispatcher/` as cwd and
`permission_mode=bypassPermissions`.

```bash
realpath .dispatcher
# /home/<user>/work/org/claude-org-ja/.dispatcher

jq '.permissions.allow, .hooks.PreToolUse[].hooks[].command' \
   .dispatcher/.claude/settings.local.json
# permissions.allow has only Bash(claude :*) and Bash(sleep:*)
# hooks: block-dispatcher-out-of-scope.sh / block-git-push.sh /
# block-dangerous-git.sh / block-no-verify.sh / block-workers-delete.sh
```

Run `/sandbox` in the dispatcher pane:

- Expected: sandbox enabled, with `additionalDirectories` being the
  dispatcher-related subtree under `<claude_org_path>` (Phase 1 PR3
  emits the `roles.dispatcher.sandbox` body).
- Known gap: `failIfUnavailable=false` (prescribed `true`, §4.2). In a
  bwrap-missing environment, fall-open combined with bypassPermissions
  disables both Layer 2 and Layer 3. **Do not put the dispatcher pane
  into operational use in this state** — always confirm the bwrap
  install per §1.1.

### 3.3 Worker pane (verified via dispatcher → spawn)

The actual spawn is done by the dispatcher via
`mcp__renga-peers__spawn_claude_pane`. The operator confirms the
following in the worker pane after spawn:

```bash
# 1. cwd is worker_dir
pwd     # Pattern A: <workers_dir>/<project>/
        # Pattern B (default): <workers_dir>/<project>/.worktrees/<task>/
        # Pattern B (live_repo_worktree): <claude_org_path>/.worktrees/<task>/
        # Pattern C: <workers_dir>/<task>/

# 2. CLAUDE.md (Pattern A/B/C) or CLAUDE.local.md (B-live_repo_worktree
#    / C-gitignored_repo_root) is placed as the brief
ls -la CLAUDE.md CLAUDE.local.md 2>&1 | grep -v 'No such'

# 3. .claude/settings.local.json has been generated from the worker template
jq '.permissions.allow | length, .permissions.deny | length' \
   .claude/settings.local.json
# Non-empty

# 4. Phase 2 hook attach check (PR #420 or later)
jq '.hooks.PreToolUse[] | select(.matcher=="Bash") | .hooks[].command' \
   .claude/settings.local.json
# Expected: 4 entries (Bash matcher): block-git-push.sh /
# block-dangerous-git.sh / block-no-verify.sh /
# block-org-structure.sh
# Before Phase 2, block-dangerous-git.sh / block-no-verify.sh were
# not included and relied on inheritance via repo-shared

# 5. sandbox block emit (Phase 1 PR4 = worker_roles.default.sandbox_by_pattern)
jq '.sandbox' .claude/settings.local.json
# Expected: filesystem.additionalDirectories has worker_dir; for
# Pattern B, additionally {base_clone}/.git/worktrees/{task_id} /
# objects / refs/heads/{branch_ref} / packed-refs and
# {claude_org_path}/knowledge/raw line up alongside it.
# null → may indicate claude-org-runtime <0.1.9 (§1.2)
```

Run `/sandbox` in the worker pane and confirm per the §2 table.

---

## 4. Pattern B worktree worker commit verification (Phase 2 hook attach + pin v0.1.9)

Pattern B (`<workers_dir>/<project>/.worktrees/<task>/`) involves
sharing of git worktree metadata, so always verify that a commit
succeeds.

### 4.1 Worktree git metadata consistency

```bash
# .git is a file (worktree pointer), not a directory
[[ -f .git ]] && echo "ok: .git is a file"
cat .git
# Expected: "gitdir: <workers_dir>/<project>/.git/worktrees/<task>"

# Both the shared object store and worktree-private metadata are readable
git rev-parse --git-dir   # <workers_dir>/<project>/.git/worktrees/<task>
git rev-parse --git-common-dir  # <workers_dir>/<project>/.git
```

### 4.2 Commit goes through

```bash
# Modify any file under an allowed path
echo "smoke" >> README.md   # or any file under worker_dir
git add README.md
git commit -m "smoke(test): worktree commit verification"

# Expected: success. The pre-commit hooks (block-no-verify /
# block-dangerous-git) see git commit via the Bash matcher PreToolUse
# hook, but since --no-verify is not included it passes.
```

If `worker_roles.default.sandbox_by_pattern.B`'s
`additionalDirectories` does not include `<base_clone>/.git/worktrees/<task>`,
`objects`, `refs/heads/<branch>`, and `packed-refs` per the table in
§4.2.1 of [`docs/contracts/role-pattern-sandbox-contract.md`](../contracts/role-pattern-sandbox-contract.md),
git will return `EACCES` on packed-refs rewrites and object additions.
**"Commit goes through" is the most practical smoke for Pattern B
sandbox schema consistency.**

### 4.3 Cross-worktree isolation (negative)

Confirm that writes to `<base_clone>/.git/worktrees/<other_task>/` are
rejected (preventing destruction of a sibling worktree's HEAD / index).
This confirms that Layer 3's `additionalDirectories` mounts only the
`<task_id>`-specific paths.

```bash
# Attempt to write to another worktree's HEAD (expected: failure)
echo malicious > "$(git rev-parse --git-common-dir)/worktrees/other_task/HEAD" \
  || echo "ok: cross-worktree write blocked"
```

If there is no sibling worktree in the actual environment, this row can
be skipped. Confirming Layer 3 isolation in isolation can also be
substituted by the "write to an unauthorized path" row in §6.1.

---

## 5. Current state of fail-open / fail-closed semantics

§3 (case A bootstrap fallback) and §4.1 (`failIfUnavailable` re-semantics)
of [`docs/contracts/sandbox-launcher-contract.md`](../contracts/sandbox-launcher-contract.md)
are **prescribed**. This section describes the procedure to confirm
**current behavior**.

### 5.1 case E (runtime-side symlink-escape suppression)

On WSL2, when `~/.aws` is a symlink to `/mnt/c/Users/<user>/.aws`,
`claude-org-runtime`'s `render_role_with_metadata()` detects the escape
via `realpath` and suppresses the matching entry from Layer 3 `denyRead`
([`docs/contracts/role-pattern-sandbox-contract.md`](../contracts/role-pattern-sandbox-contract.md)
§1.3).

```bash
# On WSL, check $comment in the worker .claude/settings.local.json
jq '.["$comment"], .sandbox.filesystem.denyRead' \
   .claude/settings.local.json
# Expected (WSL): $comment has "platform=wsl, layer-3 entries suppressed: [...]"
# Expected (Linux native): no $comment or "platform=linux, ...", and
# ~/.aws/** / ~/.ssh/** remain in denyRead
```

Entries on which case E fires are covered by the Layer 2
`permissions.deny` side (`Read(~/.aws/*)` etc.) in
`worker_roles.default.permissions.deny`. **case E itself is behavior as
designed**, and the suppression appearing is not in itself anomalous.

### 5.2 case A (launcher-side bwrap bootstrap fallback) — **not implemented**

If bwrap returns a transient failure at startup with
`Can't create file at <path>` / `Can't mount tmpfs on <path>`, in the
prescribed behavior the launcher drops the relevant entry and retries
once ([`docs/contracts/sandbox-launcher-contract.md`](../contracts/sandbox-launcher-contract.md)
§3.2).

**Current state**:

- The launcher lives on the Claude Code core (upstream) side and is
  not in this repo
  ([`docs/contracts/sandbox-launcher-contract.md`](../contracts/sandbox-launcher-contract.md)
  §1.1 / §6.1).
- Whether the case A retry algorithm is implemented in upstream Claude
  Code core cannot be verified from this repo. **This runbook does not
  perform this check**.
- The case A implementation and `sandbox_deny_skipped` event emission
  (case_a side) is being followed up in claude-org-ja#392.
- Until then:
  - If bwrap returns a transient mount failure, **bwrap itself fails
    to start**, and either Claude Code falls over, or, when
    `failIfUnavailable=false`, it **silently fall-opens**.
  - A silent fall-open can be observed in `/sandbox` as `Disabled` or
    a partial state, but is not recorded as an event row, so retro /
    curator cannot detect it.

### 5.3 Current behavior of `failIfUnavailable`

`tools/org_extension_schema.json` emits **`failIfUnavailable=false`
for all roles** (table in §4.2 of
[`docs/contracts/sandbox-launcher-contract.md`](../contracts/sandbox-launcher-contract.md)).

| Environment | bwrap status | Expected (prescribed §4.1) | Actual (today) |
|---|---|---|---|
| Linux native | `bwrap` present + starts normally | sandbox enabled, Layer 3 enforced | Same |
| Linux native | `bwrap` missing | Per the §4.2 table per role (dispatcher is fail-closed) | **All roles fall-open** (uniformly emits `failIfUnavailable=false`) |
| WSL2 | `bwrap` present + with case E suppression | sandbox enabled, case E entries substituted by Layer 2 | Same |
| WSL2 | `bwrap` startup failure (case A trigger) | The launcher retries to partial_success or fall-open | Retry not implemented. Falls over or fall-opens |

**Operational implication**: The dispatcher pane starts with
`bypassPermissions`, so Layer 2 is disabled. Operating the dispatcher
in a bwrap-missing environment yields **Layer 2 disabled + Layer 3
fall-open + Layer 4 hooks only**, and credential reads pass straight
through over Bash. Treat installing bwrap as a **de facto prerequisite**
for starting the dispatcher (see
[`docs/contracts/role-pattern-sandbox-contract.md`](../contracts/role-pattern-sandbox-contract.md)
§3.2.4 Bash-redirect carve-out).

### 5.4 Observation procedure

```bash
# 1. Check the current state with /sandbox (§2)
# 2. If fall-open is suspected, attempt credential reads in the worker dir
cat ~/.aws/credentials  # only if present
cat ~/.ssh/id_*         # only if present
# Expected (sandbox enabled): Permission denied / No such file (denyRead effect)
# Observed (fall-open):       contents readable → halt operations and install bwrap

# 3. sandbox_deny_skipped event check in .state/state.db (after future case A impl)
sqlite3 .state/state.db \
  "SELECT occurred_at, payload_json FROM events
   WHERE kind='sandbox_deny_skipped' ORDER BY occurred_at DESC LIMIT 10;"
# Currently only the case_e (runtime-side) event is expected. The
# case_a side does not appear until #392 is complete.
```

---

## 6. Security boundary checks (acceptance criteria)

Below, rows that are automated by
[`tests/sandbox/test_role_pattern_smoke.sh`](../../tests/sandbox/test_role_pattern_smoke.sh)
and rows that must be confirmed manually are listed separately.

### 6.1 Worker write to a disallowed path is **denied** (Layer 4)

| Path | Command (run in worker pane) | Expected |
|---|---|---|
| Edit / Write tool | (Inside Claude Code, pass `file_path: "/tmp/evil.sh"` to the `Write` tool) | hook `check-worker-boundary.sh` denies with `exit 2`. stderr contains "outside allowed path" |
| Bash redirect | `echo x > /tmp/evil.sh` | **Not detectable at Layer 4** (see [`docs/contracts/role-pattern-sandbox-contract.md`](../contracts/role-pattern-sandbox-contract.md) §4.1.2: "Bash-mediated writes outside `<worker_dir>/` are NOT caught"). Expected to be rejected by bwrap as a write outside Layer 3 `additionalDirectories` |
| Bash org-structure | `mkdir -p .claude/settings` (an org-structure dir inside worker dir) | hook `block-org-structure.sh` (Bash matcher) denies |

Automated portion: `tests/sandbox/test_role_pattern_smoke.sh` confirms
via direct hook invocation of `check-worker-boundary.sh` /
`block-org-structure.sh` (via the `Edit | Write` matcher path). The
Layer 3 check for Bash redirect requires a running worker pane and is
therefore manual.

### 6.2 Worker write to `knowledge/raw/YYYY-MM-DD-*.md` is **allowed**

```bash
# Via the Edit / Write tool in the worker pane:
# file_path: "<claude_org_path>/knowledge/raw/2026-05-11-test.md"
# Expected: passes the hook. Operationally, only workers with
# validation-depth full write to this path.
```

Automation: the smoke test passes a correctly-formatted kebab-case
filename to `check-worker-boundary.sh` and confirms exit 0. It also
confirms that a kebab-case violation (e.g.
`2026-05-11-Test_File.md`) yields exit 2 (allowed-path 3 in
[`.hooks/check-worker-boundary.sh`](../../.hooks/check-worker-boundary.sh)).

### 6.3 `.env` / credentials `denyRead` is effective

```bash
# In the worker pane:
echo SECRET=x > .env   # place a dummy in worker_dir
cat .env               # Expected (Layer 3 enabled): Permission denied
```

| Layer | Expected |
|---|---|
| Layer 2 (`Read` tool) | Reads via the Claude Code `Read` tool are denied by `Read(.env)` in `worker_roles.default.permissions.deny` |
| Layer 3 (via Bash) | `bwrap`'s `denyRead` mount denies the `cat` syscall as well. When symlink escape occurs on WSL, case E suppression applies → Layer 2 fallback only |

Automation: the smoke test asserts that the schema's
`worker_roles.default.permissions.deny` contains the credential
entries, and that corresponding entries line up under
`sandbox_by_pattern.A/B/C.filesystem.denyRead`. Confirming deny at the
actual syscall level requires a worker pane and is manual.

### 6.4 Dispatcher write boundary (Layer 4 only)

The dispatcher runs with `bypassPermissions`, so Layer 2 is absent.
Only `block-dispatcher-out-of-scope.sh` (Edit/Write/NotebookEdit
matcher) enforces the write boundary
([`docs/contracts/role-pattern-sandbox-contract.md`](../contracts/role-pattern-sandbox-contract.md)
§3.2.3).

```bash
# In the dispatcher pane, via the Edit / Write tool:
# file_path: "<claude_org_path>/tools/evil.py"
# Expected: hook denies with exit 2
```

Automation: the smoke test invokes
`block-dispatcher-out-of-scope.sh` directly.

---

## 7. Verification-complete judgment

A single Linux/WSL2 sandbox verification is complete when all of the
following are filled in:

1. §1.1 / §1.2 (prerequisite commands + versions) → smoke test passes
2. §2 (`/sandbox` status) → secretary / dispatcher / worker panes all
   show `Enabled` + `additionalDirectories` / `denyRead` match the
   contract
3. §3 (E2E spawn checklist) → all rows confirmed
4. §4 (Pattern B commit) → smoke commit succeeds + cross-worktree
   isolation
5. §5.4 (fall-open observation) → credential reads are **denied**
6. §6 (acceptance criteria) → automated rows pass the smoke test;
   manual rows confirmed in worker pane

If anything unexpected (behavior diverging from expectations) is
observed, record it in one of the following ways:

- Gap on the contract side: update the contract docs (not this runbook)
- Bug on the runtime side: open a claude-org-runtime issue / PR
  separately
- Launcher side (Claude Code core): consolidate into the #392 follow-up
- Missing description in this runbook: update this runbook (PR it)

---

## 8. Related issues / references

- claude-org-ja#380 (parent Issue for this runbook + smoke test)
- claude-org-ja#420 (Phase 2 worker git guardrails — hook attach +
  Layer 2 deny family)
- claude-org-ja#414 (Phase 3 prerequisite — sandbox launcher contract)
- claude-org-ja#392 (Phase 3 case A implementation / launcher-side
  follow-up)
- claude-org-ja#378 (Phase 1 schema sandbox surface — `sandbox_by_pattern`)
- claude-org-ja#376 (Phase 0 parent epic)

External:

- bubblewrap(1) man page (`man bwrap` / Debian package `bubblewrap`,
  0.5.x–0.10.x scope)
- Claude Code sandbox feature (built-in, upstream)
