# Special handling when editing claude-org itself

> **Premise (Pattern decision)**: when the target file is gitignored (e.g. internal memos under `docs/internal/`, `notes/`, `tmp/`), the "Pre-check: is the target file git-tracked?" in SKILL.md Step 1 forces **Pattern C**. The special handling in this document (hook exclusion, `CLAUDE.local.md`) applies under both Pattern B and Pattern C, but in Pattern C no worktree is created — instead, set WORKER_DIR to the existing repository root that has access to the target file. The procedure below mainly assumes Pattern B (editing tracked files).

When dispatching a Worker that edits the claude-org repository's skills / docs / settings, the normal worktree preparation alone causes the following accidents:

- The `block-org-structure.sh` hook rejects Edit / Write to `.claude/skills/` and similar (a confirmation prompt fires due to exit code 2 even in `bypassPermissions` mode)
- The root `CLAUDE.md` is the Lead directive, so a Worker reading it would mistakenly conclude "you are the Lead"

Therefore, for claude-org self-edit tasks, **the following 3 items are added to the normal procedure during Step 1.5 Worker directory preparation**.

## 1. Generate settings.local.json with the `claude-org-self-edit` role

From Phase 2 (Issue #99) onward, a Worker's `.claude/settings.local.json` is generated **schema-driven** by `tools/generate_worker_settings.py` (hand-editing is forbidden by the Lead-side `permissions.deny`). For claude-org self-edit tasks, specify `--role claude-org-self-edit`:

```bash
python tools/generate_worker_settings.py \
  --role claude-org-self-edit \
  --worker-dir {worker_dir} \
  --claude-org-path {claude_org_path} \
  --out {worker_dir}/.claude/settings.local.json
```

The `claude-org-self-edit` role is defined in the schema with the `block-org-structure.sh` hook **already excluded** (under both the `Edit|Write` and `Bash` matchers). Other hooks such as `check-worker-boundary.sh` / `block-git-push.sh` remain as usual. Do not hand-edit the generated JSON (drift CI fails; if a new pattern is needed, open a PR to add a role to `worker_roles` in `tools/role_configs_schema.json`).

## 2. Write Worker instructions to `CLAUDE.local.md`, not `CLAUDE.md`

The root `CLAUDE.md` is the Lead's directive, so do not overwrite it with the Worker's CLAUDE.md (other roles would break).
Write the Worker instruction to `CLAUDE.local.md` directly under the worktree (untracked by git).

Claude Code reads both `CLAUDE.md` and `CLAUDE.local.md` in the same directory, so the Worker can see both.

### Re-reading the normal procedure (important)

For claude-org self-edit tasks, wherever SKILL.md Step 1.5, `worker-claude-template.md`, or `instruction-template.md` says "generate / place / verify CLAUDE.md", **read it as `CLAUDE.local.md`**:

- "Generate CLAUDE.md (substitute template variables)" in Step 1.5 common procedure → make the generation target `CLAUDE.local.md`. You may reuse the body of `worker-claude-template.md` as the template
- "Verify the generated CLAUDE.md contains the 'Working directory (most important constraint)' section" in Step 1.5 common procedure (after placement) → verify against the generated `CLAUDE.local.md`
- "Detailed code of conduct is described in CLAUDE.md" / "absolute path described in CLAUDE.md" in `instruction-template.md` → rewrite those passages to refer to `CLAUDE.local.md` before sending to the Worker
- The reference work-skill section is also added to `CLAUDE.local.md`

Do not overwrite the root `CLAUDE.md` (the Lead's directive) under any circumstances.

## 3. Make "ignore the root CLAUDE.md" explicit at the top of `CLAUDE.local.md`

Always write the following intent at the top of `CLAUDE.local.md`:

> This Worker operates in a worktree of the claude-org repository itself. Ignore the Lead directive in `./CLAUDE.md` (the root CLAUDE.md). You are not the Lead — you are a Worker.

Without this notice, the Worker reads the root CLAUDE.md first and starts behaving as the Lead (e.g. prompting `/org-start`).

## Rationale

See the section "When dispatching a Worker that edits claude-org itself, adjust the in-worktree settings up front" in `knowledge/curated/delegation.md`.
