# Special Cases for Tasks That Edit `claude-org` Itself

> **Precondition (Pattern selection)**: If the target file is gitignored (for example, internal notes under `docs/internal/`, `notes/`, or `tmp/`), **Pattern C is forced** by SKILL.md **Step 0.7 "Pre-check whether the target file is gitignored"** (the directory-pattern checks in Step 1 are never reached). The special handling in this document (hook exclusion and `CLAUDE.local.md`) applies to both Pattern B and Pattern C, but Pattern C does not create a worktree, so `WORKER_DIR` must point at the existing repository root that can access the target file. The procedure below primarily assumes Pattern B (editing tracked files).

When dispatching a Worker to edit skills, docs, or configuration in the `claude-org` repository, leaving the normal worktree setup unchanged causes the following failures:

- The `block-org-structure.sh` hook rejects `Edit` / `Write` under `.claude/skills/` and similar paths (`bypassPermissions` still triggers a confirmation prompt because it exits with code 2)
- The root `CLAUDE.md` contains instructions for the Lead, so the Worker reads it and misidentifies itself as "you are the Lead"

Because of this, for `claude-org` self-edit tasks, **add the following three items to the normal Step 1.5 Worker-directory setup**.

## 1. Generate `settings.local.json` with the `claude-org-self-edit` role

Generate the Worker `.claude/settings.local.json` with `claude-org-runtime settings generate` in a **schema-driven** way (manual edits are blocked by the Lead's `permissions.deny`). For `claude-org` self-edit tasks, pass `--role claude-org-self-edit`:

```bash
claude-org-runtime settings generate \
  --role claude-org-self-edit \
  --worker-dir {worker_dir} \
  --claude-org-path {claude_org_path} \
  --out {worker_dir}/.claude/settings.local.json
```

In the schema, the `claude-org-self-edit` role is already defined with the `block-org-structure.sh` hook **excluded** (for both the `Edit|Write` and `Bash` matchers). Other hooks such as `check-worker-boundary.sh` and `block-git-push.sh` remain in place as usual. Do not manually re-edit the generated JSON afterward (drift CI fails. If you add a new role, the PR must add it to both the **ja-side `tools/org_extension_schema.json` (the org-extension canonical source used by the drift validator `tools/check_role_configs.py`) and the merged role schema bundled in `claude-org-runtime` (the canonical source used by the generator `claude-org-runtime settings generate`)**: adding it only on the ja side means the generator does not know the new role and generation fails; adding it only on the runtime side means drift CI fails. If you change the framework-side schema shape itself (the allowed shape definition for `worker_roles`), that is handled only in `claude-org-runtime`. The current unsynchronized state between the two is tracked as a follow-up in `docs/internal/` (ja-only)).

## 2. Write Worker instructions in `CLAUDE.local.md`, not `CLAUDE.md`

The root `CLAUDE.md` contains Lead instructions, so do not overwrite it with a Worker `CLAUDE.md` (that breaks other roles).
Write Worker instructions in `CLAUDE.local.md` directly under `{worker_dir}` (not tracked by git). For Pattern B (tracked-file edits), `{worker_dir}` is the worktree root. For forced Pattern C (gitignored submode), `{worker_dir}` points at the existing repository root that can access the target file.

> **Same-repo exclusion for forced Pattern C**: `CLAUDE.local.md` and `.claude/settings.local.json` use fixed filenames, so do **not** run two or more forced-Pattern-C Workers against the same repository root at the same time (they overwrite the earlier Worker's instructions and permissions). Serialize them on the Lead side. SKILL.md Step 0.7 "Pattern C forced (gitignored submode)" previously mentioned only conflicts with A/B, but C/C is also mutually exclusive in the same way (already added to the "Conflicts with parallel work" item in that section).

Claude Code loads both `CLAUDE.md` and `CLAUDE.local.md` from the same directory, so the Worker sees both.

### Reinterpretation of the normal procedure (important)

For `claude-org` self-edit tasks, reinterpret every instruction in SKILL.md Step 1.5 and in `worker-claude-template.md` / `instruction-template.md` that says to generate / place / verify `CLAUDE.md` as **`CLAUDE.local.md`** instead:

- In the common Step 1.5 procedure, "Generate `CLAUDE.md` (substitute template variables)" becomes generating `CLAUDE.local.md`. You may reuse the body of `worker-claude-template.md` as the template unchanged
- In the common Step 1.5 procedure after placement, "Verify that the generated `CLAUDE.md` contains the 'Working directory (most important constraint)' section" becomes verifying the generated `CLAUDE.local.md`
- In `instruction-template.md`, rewrite "Detailed behavioral rules are documented in `CLAUDE.md`" and "the absolute path documented in `CLAUDE.md`" to `CLAUDE.local.md` before sending them to the Worker
- Any reference work-skill section must also be added to `CLAUDE.local.md`

Never overwrite the root `CLAUDE.md` (Lead instructions) under any circumstances.

### Lead-side cleanup obligation on Worker completion (Issue #478)

`CLAUDE.local.md` is **not done once generated — the obligation extends to the Lead reclaiming it on Worker completion**. The reclaim path differs by pattern:

- **Pattern B (`live_repo_worktree`)**: the brief sits directly under the worktree (`{claude_org_path}/.worktrees/{task_id}/CLAUDE.local.md`), so the close-time `git -C {claude_org_path} worktree remove .worktrees/{task_id}` reclaims it together with the whole directory. No per-file deletion needed.
- **Pattern C (`gitignored_repo_root`)**: `worker_dir` is the claude-org repo root itself, so neither worktree remove nor dir removal applies. Unless `{claude_org_root}/CLAUDE.local.md` is **deleted individually it lingers**, and on the next `/org-start` the Lead loads a contradictory role identity ("Lead and Worker" — the brief's opening line "You are not the Lead. You are the Worker.") into context. Being gitignored, CI never flags it and it stratifies (Issue #478 occurrence example: `lt-lapras-392778-01`).

The per-file deletion for Pattern C is built into the close phase as a responsibility in [`.claude/skills/org-pull-request/SKILL.md`](../../org-pull-request/SKILL.md) 2b-ii. The mechanism is [`tools/run_complete_on_merge.py`](../../../../tools/run_complete_on_merge.py) `cleanup_pattern_c_local_md(conn, task_id=..., claude_org_root=..., worker_dir_abs=...)`:

- Detection: `runs.pattern == 'C'` AND `worker_dir == claude_org_root` (no schema change needed; ephemeral C automatically falls through as a no-op because `worker_dir != root`). `worker_dir` is resolved by preferring the `runs.worker_dir_id` -> `worker_dirs` join, and falls back to the `worker_dir_abs` argument only when the join is NULL (i.e. `remove_worker_dir()` already ran), so a live row is not overridden by a stray argument.
- Action: delete `{claude_org_root}/CLAUDE.local.md` via `Path.unlink(missing_ok=True)` and append one `pattern_c_cleanup` row to `events` (payload: `task` / `removed_path` / `mode`). Idempotent (`mode=skip` when the file is absent; never stops on error).
- **Order-independent (Issue #486)**: the close-phase StateWriter block DELETEs the `worker_dirs` row via `remove_worker_dir()` (`runs.worker_dir_id` is `ON DELETE SET NULL`). If cleanup is called after the row deletion, the join resolves to `abs_path=NULL` and becomes a no-op, so the caller passes the deleted `abs_path` explicitly via `worker_dir_abs=` to keep detection working whether it is called before or after the row deletion.
- When the PR-merge close path calls `tools/run_complete_on_merge.py --pr <PR>`, the same cleanup runs automatically at merge-record time (this path does not call `remove_worker_dir()`, so the live join suffices and no `worker_dir_abs` fallback is needed). But gitignored tasks rarely produce a PR, so the explicit call from the close-phase StateWriter block is the primary path.

> **scope**: this Issue's scope is `CLAUDE.local.md` only. Auto-deleting `.claude/settings.local.json` requires a worker-origin vs. Lead-origin discrimination design (the Lead itself uses it, e.g. for renga-peers MCP allows), so it is a separate Issue.

## 3. For Pattern B, place the worktree base in the **Lead's live repo** (`live_repo_worktree` variant)

When a `claude-org` self-edit task uses Pattern B (worktree), place the worktree base in **the `.worktrees/` under the Lead's own live repo**, not the normal `{workers_dir}/{project_slug}/.worktrees/{task_id}/` pattern:

```
{claude_org_path}/.worktrees/{task_id}/
```

This is the de facto convention used by every `claude-org` self-edit Worker throughout sessions #11-#12 (PR #276, #279, #280, #282, #288, #291, #294, #293, #295, #296), and it was formally documented in Issue #289.

Reasons:

- Because the Lead and Worker share a **single `.git/`**, there is no need for the two-stage clone sync between the Lead-side clone and the workers-side clone
- The Lead's repo itself serves as the canonical local clone, with no extra indirection
- `git worktree list` always shows live Worker branches, so the Lead does not need to `cd` to inspect state

How to choose between normal Pattern B (not self-edit) and this exception:

| Condition | worktree base | `pattern_variant` |
|---|---|---|
| Pattern B + `role == claude-org-self-edit` | `{claude_org_path}/.worktrees/{task_id}/` | `live_repo_worktree` |
| Pattern B + `role == default` (normal project) | `{workers_dir}/{project_slug}/.worktrees/{task_id}/` | `null` |

`tools/resolve_worker_layout.py` automatically selects `pattern_variant='live_repo_worktree'` and sets `worker_dir` to the live-repo path above when **Pattern B + self-edit role** is used (Issue #289). Explicitly setting `pattern_variant='live_repo_worktree'` in the TOML `[worker]` block produces the same result.

## 4. Explicitly say at the top of `CLAUDE.local.md` to ignore the root `CLAUDE.md`

At the beginning of `CLAUDE.local.md`, always include text to this effect:

> This Worker operates in `{worker_dir}` of the `claude-org` repository itself (for Pattern B, directly under the worktree; for forced Pattern C, directly under the repo root). Ignore the Lead instructions in `./CLAUDE.md` (the root `CLAUDE.md`). You are not the Lead. You are the Worker.

Without this explicit note, the Worker reads the root `CLAUDE.md` first and starts acting as the Lead (for example, prompting execution of `/org-start`).

## 5. send_keys pre-approval handshake for root `.claude/**` edit tasks

### Scope boundary

This section applies **only to `claude-org` root `.claude/**` (self-edit)**:

- **In scope**: any delegation that includes an Edit / Write to `.claude/**` directly under the claude-org repo root (**at any depth, all of it**). Not just `.claude/settings.json` and `.claude/skills/**/SKILL.md` (including the `.in` source) themselves directly under the root, but the brief-norm prose under `.claude/skills/**/references/**` is equally in scope. In particular, the high-impact templates that shape every worker's brief norms — [`.claude/skills/org-delegate/references/worker-claude-template.md`](worker-claude-template.md) / [`.claude/skills/org-delegate/references/instruction-template.md`](instruction-template.md) / [`.claude/skills/org-delegate/references/ack-template.md`](ack-template.md) / this file itself ([`.claude/skills/org-delegate/references/claude-org-self-edit.md`](claude-org-self-edit.md)) — must always be included in the handshake scope (these are illustrative; the load-bearing boundary is the whole of root `.claude/**` including `references/**`, and files not listed here are in scope too). This closes the anti-laundering hole where a worker rewrites its own brief norms without approval; in the past, editing a brief template under `references/` succeeded ungated because the handshake did not fire (incident #612). **Editing the definition of this section (the scope boundary) itself is also handshake-required**, forbidding a worker from self-narrowing the gate definition (e.g. dropping `references/**` from scope).
- **Out of scope**: `.dispatcher/` / `.curator/` (runtime directories of other roles, not `.claude/`), and the worker-dir artifact `.claude/settings.local.json` (an artifact placed by `claude-org-runtime settings generate`; the worker itself never edits it).

> **Canonical definition (single SoT)**: the canonical definition of the handshake-required paths is this section (the scope boundary), as the single SoT. The send_keys pre-approval description in [`.claude/skills/org-delegate/SKILL.md`](../SKILL.md) is a back-reference to this section (`see §5 as the primary source`) and does not independently redefine the boundary of target paths.

### Background (two-layer guard)

Writes under `.claude/` are normally guarded in two layers: the `block-org-structure.sh` hook lets only Edit / Write through, while the auto-mode classifier blocks "`.claude/` edits without user approval". **However, for a self-edit worker (`claude-org-self-edit` role) this hook guard does not exist**: `block-org-structure.sh` is dropped in the role definition, the remaining `check-worker-boundary.sh` uniformly allows everything inside WORKER_DIR (the Pattern B live-repo worktree, including `references/**`), and the generated `settings.local.json` carries no allow / deny / ask at all for Edit / Write to `.claude/**`. Therefore, for a self-edit worker **this handshake (the send_keys approval that clears the classifier) is the sole gate on `.claude/**` edits**, and the precision of the scope boundary above is exactly the gate's coverage (missing `references/**` was the direct cause that let ungated edits through). The classifier's approval **passes only via terminal input by send_keys (arriving in the worker's conversation as a user message)**. A peer message (`send_message`) does not become user input and so does not function as approval.

> **Transport layer both systems (`ORG_TRANSPORT`: default `renga` / opt-in `broker`)**: the `send_keys`-based handshake that approves the auto-mode classifier for `.claude/**` edits is **default `renga`** (`ORG_TRANSPORT` unset) and uses `mcp__renga-peers__send_keys`. Under `ORG_TRANSPORT=broker` (opt-in, revertible), it gets machine-substituted to **`mcp__renga-peers__send_keys` → `mcp__org-broker__send_keys`** (raw key input = approval-text input to the terminal; the nature and argument shape are identical, so the logic of the approval text arriving as a user message and clearing the classifier is invariant across systems). Note that the spawn-time initial approval prompt itself becomes, under broker, the **two-stage** Claude Code **folder-trust prompt + the channel sidecar's dev-channel approval ("Load development channel?", spawn-flow 3-3b re-introduced)** (renga has only dev-channel; this is additive, not a replacement, due to push-primary adoption; design transport-lab `docs/design/broker-native-roles.md` §9.5), but that is a separate layer from the pre-approval for `.claude/` edits in this section (the spawn-rite difference, on the pane-layout / spawn-flow side). See [`docs/contracts/backend-interface-contract.md`](../../../../docs/contracts/backend-interface-contract.md) Surface 8 (ratified 2026-06-14; the push-primary additive amendment S3 is ratified 2026-06-15, with existing ratified text unchanged) and the broker section of [`.claude/skills/org-delegate/references/renga-error-codes.md`](renga-error-codes.md) for details. The default-renga procedure is unchanged (broker is additive). (**Note on the two default frames (Refs #604)**: here "default `renga`" means the **operational default** (running broker in dogfood is inactive until Epic #6 Issue G). Separately, as the **code default**, `tools/transport.py: DEFAULT_TRANSPORT` has already flipped to `broker` in runtime 0.1.28 (Epic #586), and the ja generator / `transport.resolve()` render in this code frame, so the generated surface shows "default `broker`" — the two frames refer to different things (operational path vs. code constant) and do not conflict. The overview is in the root `CLAUDE.md` "Transport layer both systems" section.)

### Handshake (fixed procedure)

To prevent deadlock (a worker waiting forever for an approval that never arrives) and empty Enter presses (a send with no approval text), fix the procedure as follows:

1. **Lead**: when you receive `DELEGATE_COMPLETE` from the dispatcher, **following** the greeting send in SKILL.md Step 5, input the approval text into the worker pane via send_keys ahead of time:
   ```
   mcp__renga-peers__send_keys(
     target="worker-{task_id}",
     text="Approved: I approve editing {enumeration of target files} in this task ({task_id}). This is user approval via the Lead.",
     enter=true
   )
   ```
   The three required elements of the approval text: **enumeration of the target files** / **task_id** / **explicit mention of "user approval via the Lead"**.
2. **worker brief**: a brief (`CLAUDE.local.md` / instruction message) for a delegation that includes root `.claude/**` (at any depth, including the brief-norm prose under `.claude/skills/**/references/**`) must always state the following intent:
   > This task includes `.claude/` edits. **Before editing, confirm that the approval input (target-file enumeration + task_id + "user approval via the Lead") exists in the conversation as a user message.** If it does not exist, do not begin editing; request the approval input from the Lead via `send_message(to_id="secretary")` and wait.
3. **worker**: begin editing only after the above confirmation. If you need a `.claude/` edit to a file not enumerated in the approval text, treat it as scope expansion and escalate via [`.claude/skills/org-escalation/SKILL.md`](../../org-escalation/SKILL.md).

## Rationale

See the "Workers that edit `claude-org` itself pre-adjust settings inside the worktree" section in `knowledge/curated/delegation.md`.
