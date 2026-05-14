# sandbox-probe runbook (Issue #376 Pre-Phase 0)

## 0. Purpose and scope

- Goal: as the Pre-Phase 0 spike for Issue #376, fix a procedure that can reproduce **B1-1 (dispatcher × bypassPermissions × sandbox)** and **B2-1 (worker × repo-shared settings inheritance)** on real machines.
- Even after this document is complete, **real-machine execution is outside this spike's scope**. Execution is done by the probe-worker (a harness equivalent to this worker) in the next iteration.
- Verification depth is minimal. fmt/lint are not run (the handcraft profile JSON is only syntax-checked via `jq empty`).

## 1. Prerequisites

| prerequisite | verification command | expected value |
|---|---|---|
| Linux or WSL2 | `uname -a` | Linux x86_64 / WSL2 |
| `bubblewrap` installed | `command -v bwrap` | `/usr/bin/bwrap` etc. |
| `socat` installed | `command -v socat` | `/usr/bin/socat` etc. |
| `jq` installed | `command -v jq` | `/usr/bin/jq` etc. |
| Claude Code runnable | `claude --version` | sandbox-supporting version (cf. docs/verification.md:430-441) |
| `claude-org-runtime` installed | `claude-org-runtime --version` | 0.1.2 or later (as of this spike) |

In environments without bubblewrap/socat, sandbox falls back to **silent no-op** via `sandbox.failIfUnavailable: false`. In that case, the B1-1 / B2-1 measurements are meaningless, so install `bwrap` first.

## 2. Preparing the probe worker (B2-1)

### 2.1 Stand up one Pattern A worker dir

Either dispatch a directory of the same form as this worker (sandbox-probe) via the dispatcher, or manually carve out `/home/$USER/work/org/workers/sandbox-probe-iter1/`. Reusing this spike worker (`<workers-root>/sandbox-probe`) is also acceptable.

### 2.2 Generate settings.local.json

```bash
cd /home/$USER/work/org/claude-org-ja
.venv/bin/claude-org-runtime settings generate \
  --role default \
  --worker-dir /home/$USER/work/org/workers/sandbox-probe-iter1 \
  --claude-org-path /home/$USER/work/org/claude-org-ja \
  --out /home/$USER/work/org/workers/sandbox-probe-iter1/.claude/settings.local.json
```

### 2.3 Observation point A: emitted JSON has no `sandbox` block

```bash
jq 'has("sandbox")' /home/$USER/work/org/workers/sandbox-probe-iter1/.claude/settings.local.json
# expected: false (no sandbox field in the bundled schema at this spike's time)
```

### 2.4 Observation point B: emitted hooks have no `block-dangerous-git.sh` / `block-no-verify.sh`

```bash
jq '.hooks.PreToolUse[].hooks[].command' /home/$USER/work/org/workers/sandbox-probe-iter1/.claude/settings.local.json
# expected:
#   "bash \"$CLAUDE_ORG_PATH/.hooks/check-worker-boundary.sh\""
#   "bash \"$CLAUDE_ORG_PATH/.hooks/block-org-structure.sh\""
#   "bash \"$CLAUDE_ORG_PATH/.hooks/block-git-push.sh\""
#   "bash \"$CLAUDE_ORG_PATH/.hooks/block-org-structure.sh\""
# block-dangerous-git.sh / block-no-verify.sh are **not included**
```

### 2.5 Observation point C: the repo-shared settings are not inherited by the worker

```bash
# The sandbox / dangerous-git of the claude-org-ja repo live in repo-shared
jq '.sandbox, .hooks' /home/$USER/work/org/claude-org-ja/.claude/settings.json

# The worker's cwd is worker_dir, outside the repo-shared tree
realpath /home/$USER/work/org/workers/sandbox-probe-iter1
# /home/.../workers/sandbox-probe-iter1 (not a subpath of claude-org-ja)
```

→ **B2-1 confirmation**: the worker does not inherit `block-dangerous-git.sh` / `block-no-verify.sh`, and does not inherit `sandbox.filesystem.*` either.

### 2.6 Action verification: 5 rows measured by the probe (`probes/checklist.md` 2.x)

Start the worker in Claude Code and try the following in auto mode in order.

| # | command | observation |
|---|---|---|
| 2.1 | `git reset --hard HEAD` (at worker dir) | denied by hook/perms / passes through |
| 2.2 | `git commit --allow-empty --no-verify -m probe` | same as above |
| 2.3 | `cat ./.env` (pre-created with `echo SECRET=x > .env`) | confirm it passes through (no sandbox inheritance) |
| 2.4 | `git branch -D probe-tmp` (pre-created with `git branch probe-tmp`) | confirm it passes through |
| 2.5 | `/sandbox` slash command | sandbox status display (Disabled / Enabled / fail-open) |

## 3. Preparing the probe dispatcher (B1-1)

### 3.1 Launch the dispatcher pane (the pane usually started by the renga layout)

The dispatcher is assumed to be started in `bypassPermissions` mode. renga layout: `dispatcher.json` etc. This runbook alone does not start renga; checking with `mcp__renga-peers__list_peers` for the presence of an already-running dispatcher pane is sufficient.

### 3.2 Verify dispatcher's cwd and settings.local.json

```bash
# dispatcher's cwd
realpath /home/$USER/work/org/claude-org-ja/.dispatcher
# expected: /home/.../.dispatcher (directly under claude-org-ja)

# dispatcher's settings.local.json
jq '.permissions, .hooks, .sandbox' /home/$USER/work/org/claude-org-ja/.dispatcher/.claude/settings.local.json
# expected: permissions allow has only Bash(claude :*) and Bash(sleep:*); hooks contain block-dispatcher-out-of-scope.sh + block-git-push.sh + block-dangerous-git.sh + block-workers-delete.sh + block-no-verify.sh; sandbox is absent (not emitted because the schema lacks it)
```

### 3.3 The dispatcher's cwd is under claude_org_path, so it **inherits** repo-shared `.claude/settings.json`

- The `hooks` (block-no-verify, block-dangerous-git) and `sandbox` from `claude_org_path/.claude/settings.json:60-91` are **likely** effective on the dispatcher (Claude Code inheritance rule: cwd is `.dispatcher/` but settings.json are searched in the parent direction; precedence is cwd > parent > home). Confirm by real-machine `/sandbox`.
- However, the dispatcher operates under **bypassPermissions**, so `permissions.deny` is disabled. **Whether sandbox remains as a separate layer is the core of this probe**.

### 3.4 Action verification: 5 rows measured by the probe (`probes/checklist.md` 1.x)

Send probe commands to the dispatcher pane via `mcp__renga-peers__send_message`, or prompt interactively.

| # | command (executed at dispatcher) | observation |
|---|---|---|
| 1.1 | `cat ~/.config/gh/hosts.yml` | denied by sandbox denyRead / passes through |
| 1.2 | `cat ./.env` (dummy .env pre-placed at dispatcher cwd) | same as above |
| 1.3 | `cat ./creds.pem` (dummy placed) | same as above |
| 1.4 | `echo x >> ~/.claude/settings.json.sandbox-test` | denied by sandbox denyWrite |
| 1.5 | `/sandbox` slash command | sandbox status |

### 3.5 Observation point: case classification of results

| result | interpretation | Phase 1 schema impact |
|---|---|---|
| 1.1–1.4 all denied | bypassPermissions only disables permissions.allow/deny; sandbox fires as a separate layer | design with a sandbox column on dispatcher too |
| 1.1–1.4 mixed deny / allow | sandbox firing conditions are more fine-grained (cwd vs absolute path, etc.) | recheck the grammar of each deny pattern; unify in Phase 1 |
| 1.1–1.4 all allowed | bypassPermissions disables sandbox too | dispatcher defense is hook-only; no sandbox column in Phase 1 schema |
| `/sandbox` shows Disabled | bubblewrap absent in environment, fail-open silent | **probe result invalid**; install bubblewrap and re-run |

## 4. Profile switching verification (Pattern A worker)

### 4.1 Apply baseline

The official copy of the profile is in the claude-org-ja repo (`docs/sandbox-probe/profiles/profile-baseline.json`). In environments without the original spike worker (`/home/$USER/work/org/workers/sandbox-probe/`), copy from here.

```bash
cp /home/$USER/work/org/claude-org-ja/docs/sandbox-probe/profiles/profile-baseline.json \
   /home/$USER/work/org/workers/sandbox-probe-iter1/.claude/settings.local.json

# placeholder substitution
sed -i "s|{worker_dir}|/home/$USER/work/org/workers/sandbox-probe-iter1|g; s|{claude_org_path}|/home/$USER/work/org/claude-org-ja|g" \
       /home/$USER/work/org/workers/sandbox-probe-iter1/.claude/settings.local.json

jq empty /home/$USER/work/org/workers/sandbox-probe-iter1/.claude/settings.local.json
```

Restart Claude Code and re-run checklist 2.x / 5.x / 7.x. Under baseline:
- `git reset --hard HEAD` → expected **deny by hook** (block-dangerous-git.sh)
- `git commit --no-verify` → expected **deny by perms or hook**
- `cat .env` (worker cwd) → expected **deny by sandbox**
- `cat ~/.config/gh/hosts.yml` → expected **deny by sandbox**

### 4.2 Apply tightened

```bash
cp /home/$USER/work/org/claude-org-ja/docs/sandbox-probe/profiles/profile-tightened.json \
   /home/$USER/work/org/workers/sandbox-probe-iter1/.claude/settings.local.json

sed -i "s|{worker_dir}|/home/$USER/work/org/workers/sandbox-probe-iter1|g; s|{claude_org_path}|/home/$USER/work/org/claude-org-ja|g" \
       /home/$USER/work/org/workers/sandbox-probe-iter1/.claude/settings.local.json
```

Restart Claude Code, and additionally (`$SCRATCH_BASE_REPO` follows the safety prerequisite at the top of `probes/checklist.md` and points to a disposable scratch clone; e.g. `/tmp/sandbox-probe-scratch`):
- `git -C $SCRATCH_BASE_REPO reset --hard HEAD` → expected **deny by perms**
- `git worktree remove --force ../<other>` → expected **deny by perms**
- `cat ~/.aws/credentials` (dummy) → expected **deny by sandbox** (since this is via Bash, `permissions.deny`'s `Read(~/.aws/*)` is for the Read tool and is ineffective. If you try to read `~/.aws/credentials` via the `Read tool`, perms also denies it, but that is measured as a separate row.)

## 5. Verification completion criteria

The iteration is complete once all of the following are satisfied:

1. The **observed result** column of `probes/checklist.md` is filled for all rows (un-tested may remain with a reason).
2. The **conclusion** column of `probes/checklist.md` says "allow / deny by X".
3. The diff between baseline and tightened is classified as either "as expected" or "unexpected".
4. If there are surprises, add them as next-iteration checklist rows.

## 6. Anticipated risks and mitigations

- **`git reset --hard` etc. pass through by accident, destroying worker dir data**: keep the worker dir dedicated to the probe, do not mix with real repos. Use `git stash` to set aside necessary changes before running.
- **Dispatcher accidentally fires `git push --force`**: the dispatcher has permissions.deny disabled. **Do not run push-family commands on the dispatcher in this runbook**. Push verification is done only on the worker.
- **bubblewrap fails to start and sandbox silently falls back**: always check status with `/sandbox` first. If Disabled, stop the procedure and install bubblewrap.
- **The `additionalDirectories` path contains the username so cannot be carried to other environments**: commit the profile JSON in placeholder form, and only substitute with `sed` at application time. This spike's handcraft profiles already do so.

## 7. Related resources

- audit-issue-376-2026-05-09.md (B0/B1/B2/B3 details, `<workers-root>/claude-org-ja/tmp/audit-issue-376-2026-05-09.md`)
- claude-org-ja `docs/verification.md:386-457` (sandbox real-machine verification procedure, bubblewrap/socat prerequisites)
- claude-org-ja `tools/org_extension_schema.json` (worker_roles and forbidden_allow_exact)
- claude-org-ja `.claude/settings.json` (current state of repo-shared defense)
- claude-org-ja `.hooks/block-dangerous-git.sh` etc. (hook implementations)
- this worker's `probes/checklist.md`, `probes/categories.md`, `profiles/*.json`
