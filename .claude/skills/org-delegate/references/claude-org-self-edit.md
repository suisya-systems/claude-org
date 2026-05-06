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

In the schema, the `claude-org-self-edit` role is already defined with the `block-org-structure.sh` hook **excluded** (for both the `Edit|Write` and `Bash` matchers). Other hooks such as `check-worker-boundary.sh` and `block-git-push.sh` remain in place as usual. Do not manually re-edit the generated JSON afterward (drift CI fails. If you add a new role, the PR must add it to both the **ja-side `tools/org_extension_schema.json` (the org-extension canonical source used by the drift validator `tools/check_role_configs.py`) and the merged role schema bundled in `claude-org-runtime` (the canonical source used by the generator `claude-org-runtime settings generate`)**: adding it only on the ja side means the generator does not know the new role and generation fails; adding it only on the runtime side means drift CI fails. If you change the framework-side schema shape itself (the allowed shape definition for `worker_roles`), that is handled only in `claude-org-runtime`. The current unsynchronized state between the two is tracked as a follow-up in `docs/internal/phase4-completion-2026-05-02.md:71-77`).

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

## Rationale

See the "Workers that edit `claude-org` itself pre-adjust settings inside the worktree" section in `knowledge/curated/delegation.md`.
---
