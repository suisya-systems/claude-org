# Special handling when editing claude-org itself

> **Premise (Pattern decision)**: when the target file is gitignored (e.g. internal memos under `docs/internal/`, `notes/`, `tmp/`), the "Pre-check: is the target file git-tracked?" in SKILL.md Step 1 forces **Pattern C**. The special handling in this document (hook exclusion, `CLAUDE.local.md`) applies under both Pattern B and Pattern C, but in Pattern C no worktree is created — instead, set WORKER_DIR to the existing repository root that has access to the target file. The procedure below mainly assumes Pattern B (editing tracked files).

When dispatching a Worker that edits the claude-org repository's skills / docs / settings, the normal worktree preparation alone causes the following accidents:

- The `block-org-structure.sh` hook rejects Edit / Write to `.claude/skills/` and similar (a confirmation prompt fires due to exit code 2 even in `bypassPermissions` mode)
- The root `CLAUDE.md` is the Secretary (Lead) directive, so a Worker reading it would mistakenly conclude "you are the Lead"

Therefore, for claude-org self-edit tasks, **the following 3 items are added to the normal procedure during Step 1.5 Worker directory preparation**.

## 1. Exclude the `block-org-structure.sh` hook from the worktree's settings.local.json

When placing `.claude/settings.local.json` directly under the worktree, **exclude** the `block-org-structure.sh` entry from `hooks.PreToolUse`. You must exclude it under both the `Edit|Write` matcher and the `Bash` matcher.

Other hooks (e.g. `block-git-push.sh`, `block-workers-delete.sh`, `check-worker-boundary.sh`, etc.) may remain as usual. The exclusion target is strictly the claude-org structure-blocking hook only.

## 2. Write Worker instructions to `CLAUDE.local.md`, not `CLAUDE.md`

The root `CLAUDE.md` is the Secretary directive, so do not overwrite it with the Worker's CLAUDE.md (other roles would break).
Write the Worker instruction to `CLAUDE.local.md` directly under the worktree (untracked by git).

Claude Code reads both `CLAUDE.md` and `CLAUDE.local.md` in the same directory, so the Worker can see both.

### Re-reading the normal procedure (important)

For claude-org self-edit tasks, wherever SKILL.md Step 1.5, `worker-claude-template.md`, or `instruction-template.md` says "generate / place / verify CLAUDE.md", **read it as `CLAUDE.local.md`**:

- "Generate CLAUDE.md (substitute template variables)" in Step 1.5 common procedure → make the generation target `CLAUDE.local.md`. You may reuse the body of `worker-claude-template.md` as the template
- "Verify the generated CLAUDE.md contains the 'Working directory (most important constraint)' section" in Step 1.5 common procedure (after placement) → verify against the generated `CLAUDE.local.md`
- "Detailed code of conduct is described in CLAUDE.md" / "absolute path described in CLAUDE.md" in `instruction-template.md` → rewrite those passages to refer to `CLAUDE.local.md` before sending to the Worker
- The reference work-skill section is also added to `CLAUDE.local.md`

Do not overwrite the root `CLAUDE.md` (Secretary directive) under any circumstances.

## 3. Make "ignore the root CLAUDE.md" explicit at the top of `CLAUDE.local.md`

Always write the following intent at the top of `CLAUDE.local.md`:

> This Worker operates in a worktree of the claude-org repository itself. Ignore the Secretary directive in `./CLAUDE.md` (the root CLAUDE.md). You are not the Lead — you are a Worker.

Without this notice, the Worker reads the root CLAUDE.md first and starts behaving as the Secretary (e.g. prompting `/org-start`).

## Rationale

See the section "When dispatching a Worker that edits claude-org itself, adjust the in-worktree settings up front" in `knowledge/curated/delegation.md`.
