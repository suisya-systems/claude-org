# Organization Config

## Permission Mode
default_permission_mode: auto

Options:
- bypassPermissions: allow everything, no confirmation (default)
- auto: classifier-based safety check (Team / Enterprise / API plans only)
- default: confirm each time
- acceptEdits: auto-allow file edits only
- dontAsk: explicit allow only

### Per-role applicability

`default_permission_mode` applies to the Curator and Workers. Other roles are handled as follows:

- **Secretary**: out of scope. Keeps the Claude Code default behavior (confirmation prompts on tool execution) with no `--permission-mode` specified. The Secretary is the human-facing window, so we avoid auto-approving operations that require human judgment. See Issue #10 for details.
- **Dispatcher**: regardless of the `default_permission_mode` value, fixed at `bypassPermissions`. For the rationale, see the "Dispatcher" section of `.claude/skills/org-start/SKILL.md`.

## Workers Directory
workers_dir: ../workers

Where the per-Worker dedicated directories live, as a path relative to the
claude-org repository. Placing them outside the repo prevents the parent
repo's git context from interfering when a Worker creates a new project.
