# baseline observations (Issue #376 Pre-Phase 0, Iteration 1)

Organizes the facts that can be determined from static analysis of the codebase alone, without running a real-machine probe. Items awaiting measurement are tracked in `probes/checklist.md`.

## 1. Confirmed facts (100% confirmed by static analysis)

### 1.1 The worker does not inherit the repo-shared `.claude/settings.json`

- Evidence:
  - The bundled `role_configs_schema.json` of `claude-org-runtime` (v0.1.2) does **not contain** a `sandbox` field (grep against `/home/.../site-packages/claude_org_runtime/settings/role_configs_schema.json` returned nothing).
  - The `worker_roles.default.hooks.PreToolUse` in `tools/org_extension_schema.json` does **not include** `block-dangerous-git.sh` / `block-no-verify.sh` (`org_extension_schema.json:302-330`).
  - The real settings of this worker (`<workers-root>/sandbox-probe/.claude/settings.local.json`) follow the schema and lack the two hooks above, with no `sandbox` block.
  - The worker cwd (`/home/.../workers/<project>/`) is outside the tree of `claude-org-ja/.claude/settings.json`, so Claude Code's cwd-based settings lookup logic cannot reach `claude_org_path/.claude/settings.json`.
- Consequences:
  - `git reset --hard`, `git branch -D`, `git commit --no-verify` are **not stopped by schema or hook** for the worker.
  - sandbox denyRead for `.env` / `**/credentials*` / `**/*.pem` is **not in effect** for the worker.
  - audit B2-1 is **confirmable from the codebase alone, without real-machine verification**.

### 1.2 The dispatcher's cwd is `claude_org_path/.dispatcher/`, in a path that inherits repo-shared

- Evidence:
  - `tools/org_extension_schema.json:166` sets the dispatcher's `settings_paths` to `[".dispatcher/.claude/settings.local.json"]`, meaning cwd is under `claude_org_path/.dispatcher/`.
  - Claude Code merges settings.json from cwd → parent → home. The parent of `.dispatcher/` is `claude_org_path/`, which contains the repo-shared `.claude/settings.json`.
- Consequences:
  - The dispatcher's **hook layer** (block-no-verify, block-dangerous-git) is enabled via repo-shared (also explicit in `worker_roles.dispatcher.required_hooks`).
  - Whether the dispatcher's **sandbox layer** is enabled via the same path is unconfirmed (the core of B1-1).
  - The dispatcher's **permissions.allow/deny layer** is disabled by `bypassPermissions` mode (explicit in the description at `org_extension_schema.json:163-165`).

### 1.3 Schema-side forbidden_allow_exact closes off the network family from the worker

- Evidence: `forbidden_allow_exact` at `tools/org_extension_schema.json:11-13` includes `Bash(gh:*)` etc. (premise from audit §1, §5).
- Consequences: `gh api` / `curl` / `cargo fetch` from the worker are blocked by **permissions.allow absent**. The current `claude-org-ja/.claude/settings.json` has **no** `sandbox.network` block (filesystem only).
- This is consistent with the decision to make Phase 4 (network policy) non-goal for this epic.

### 1.4 The worker schema's deny is only `git push *` / `rm -rf *` / `rm -r *`

- Evidence: `tools/org_extension_schema.json:242-247` (and `worker_roles.default.permissions.deny`).
- Consequences: For this worker too, `git reset --hard`, `git branch -D`, `git commit --no-verify`, `git -C <other> ...` are all absent from schema deny, so at the Claude Code perms layer they **pass through**.

### 1.5 worker hook binding and repo-shared hook binding are separate

- worker (`worker_roles.default.hooks`):
  - Edit|Write: `check-worker-boundary.sh`, `block-org-structure.sh`
  - Bash: `block-git-push.sh`, `block-org-structure.sh`
- repo-shared (`claude-org-ja/.claude/settings.json:60-74`):
  - Bash: `block-no-verify.sh`, `block-dangerous-git.sh`
- Common point: both reference `.hooks/` via `${CLAUDE_PROJECT_DIR}` or `{claude_org_path}`. To bind a repo-shared hook from the worker, **just write the command path as `{claude_org_path}/.hooks/...`; the file itself need not be ported**. This is the design rationale of `profiles/profile-baseline.json`.

## 2. Strong estimates (from static analysis + audit + official docs)

### 2.1 sandbox likely does not fire on dispatcher (B1-1 expectation)

- Evidence (indirect):
  - Official Claude Code docs describe `bypassPermissions` as "skip the permission system and execute tools immediately". sandbox is an OS-level bubblewrap fork, so the **layers should be separated**, but `bypassPermissions` may internally skip sandbox seccomp/bwrap as well.
  - audit B1-1 says "real-machine confirmation spike is needed", and there is no document-based confirmation at this point.
- Conclusion: **measurement is mandatory**. Main thrust of this spike.

### 2.2 The worker is likely to be able to **read** `~/.ssh/*` / `~/.aws/*`

- Evidence:
  - No `Read(~/.ssh/*)` / `Read(~/.aws/*)` in worker schema deny (`org_extension_schema.json:242-247`).
  - The worker does not inherit the repo-shared `.claude/settings.json:55-56` `Read(~/.ssh/*)` / `Read(~/.aws/*)` denies (same root as 1.1).
  - Claude Code's built-in credential protection (`docs/verification.md:418`) is observed to deny `cat ~/.ssh/<ssh-key>`, but this is **claude-builtin** and sandbox/perms-independent.
- Conclusion: 7.2 (`cat ~/.ssh/<ssh-key>`) is likely denied by claude-builtin. Meanwhile, 7.3 (`cat ~/.config/gh/hosts.yml`) is estimated to be outside claude-builtin's protection target → high chance **readable**.

### 2.3 `git -C <base_repo> reset --hard` bypasses schema deny

- Evidence: schema deny patterns are string-prefix forms like `Bash(git push *)`. `Bash(git -C ... reset --hard)` does not match.
- Conclusion: Phase 2 (Issue #379) needs to add `Bash(git -C * reset --hard*)` to worker schema deny + add `block-dangerous-git.sh` to worker hooks, providing double defense (design rationale of `profile-tightened.json`).

### 2.4 With `additionalDirectories` unspecified, the worker cwd itself is writable

- Evidence: Claude Code's sandbox defaults to making cwd writable (official sandbox overview).
- Conclusion: writes from the worker pass as long as they are inside cwd. Explicitly setting `additionalDirectories: [worker_dir]` does not change behavior, but making it explicit makes the diff during Pattern B/C migration visible (intent of `profile-tightened.json`).

## 3. Unresolved open items (to be filled by the real-machine probe iteration)

| item | impact target | required probe |
|---|---|---|
| Whether sandbox fires on dispatcher | Issue #378 schema design (sandbox column of the dispatcher row) | checklist 1.1–1.5 |
| Worker read of `~/.ssh/*` (presence/absence of claude-builtin) | whether to add Read() to Phase 2 schema deny | checklist 7.2, 7.6 |
| Catch range of `git -C <other>` form by hook | whether to extend the `block-dangerous-git.sh` regex | checklist 5.8, 5.9 |
| Behavior when `additionalDirectories` is extended to base_repo for Pattern B | design of `{base_repo}` placeholder in Issue #378 schema | (Pattern B-dedicated profile needed; out of scope for this iteration) |
| Whether startup fails when `failIfUnavailable` is `true` (fail-closed) | Phase 3 environment-specific matrix | (separate iteration, measured per CI / dev environment) |

## 4. Tangential notes

- **The cwd of this worker (sandbox-probe) is not a git repo** (Pattern A, send_plan.json's `base_repo: null`). In this iteration, we use a structure of **`git init` then commit** without a remote. Push is via the secretary.
- **Knowledge curation contract carve-out** (`docs/contracts/knowledge-curation-contract.md:116-128`) is, as the audit pointed out, a task-derived carve-out with dynamic hook judgment. Not handled in this spike.
- **Pattern C (gitignored repo root) family** (audit B0-4) is out of scope for this iteration. Priority for the next iteration is low (fixing the Pattern A minimum baseline first is preferable).
