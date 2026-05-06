# Organization Config

> **Sync note**: `CLAUDE.md` has no variable expansion mechanism, so the `permission_mode` values under `.claude/skills/**` and `docs/contracts/role-contract.md` are hard-coded as the literal `auto` (fixed after the regression in session #15 where Secretary incorrectly assigned `acceptEdits`). Changing the value in this file alone does not propagate to the skill/docs side. If you change `default_permission_mode`, manually update the following as well (`tools/gen_delegate_payload.py` is the only file that reads this config at runtime, so it follows automatically. Use `grep -rn '"auto"' .claude/skills docs/contracts` to check for misses):
>
> - `.claude/skills/org-start/SKILL.md`
> - `.claude/skills/org-delegate/SKILL.md`
> - `.claude/skills/org-delegate/references/pane-layout.md`
> - `docs/contracts/role-contract.md`

## Permission Mode
default_permission_mode: auto

Options:
- bypassPermissions: full अनुमति, no confirmation (default)
- auto: classifier-based safety checks (Team/Enterprise/API plans only)
- default: confirm each time
- acceptEdits: auto-approve file edits only
- dontAsk: explicit approval only

### Role-Specific Scope

`default_permission_mode` applies to Curator / Worker. Other roles are handled as follows:

- **Secretary**: out of scope. Keep the default Claude Code behavior with no `--permission-mode` specified (show a confirmation prompt before tool execution). Secretary is the human-facing role, so it should avoid auto-approving operations that require human judgment. See Issue #10 for details.
- **Dispatcher**: always uses `bypassPermissions` regardless of `default_permission_mode`. See the "ディスパッチャー" section in `.claude/skills/org-start/SKILL.md` for the rationale.

## Workers Directory
workers_dir: ../workers

Location of the worker-only directory. Relative path from the `claude-org` repository.
Keeping it outside the repository prevents the parent repository's git context from interfering when a worker creates a new project.
