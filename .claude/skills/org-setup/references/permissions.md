# Required settings per role

> **Source of truth**: this document is a human-facing explanation; the
> machine-readable canonical version is
> [`tools/role_configs_schema.json`](../../../../tools/role_configs_schema.json).
> If the JSON blocks in this file drift from the schema, CI
> (`tools/check_role_configs.py`) fails. When adding rules or changing
> wording, update the schema first, then the docs.

The per-role definitions of permissions allow entries and environment variables that org-setup references.

## User-wide (`~/.claude/settings.json`)

Settings every role needs. Putting them at the user level applies them to every subdirectory.

```json
{
  "permissions": {
    "allow": [
      "Bash(renga --version)",
      "Bash(renga --help)",
      "Bash(renga --layout:*)",
      "Bash(renga mcp install:*)",
      "Bash(renga mcp uninstall:*)",
      "Bash(renga mcp status:*)",
      "Bash(renga mcp --help)",
      "mcp__renga-peers__set_summary",
      "mcp__renga-peers__list_peers",
      "mcp__renga-peers__send_message",
      "mcp__renga-peers__check_messages",
      "mcp__renga-peers__list_panes",
      "mcp__renga-peers__spawn_pane",
      "mcp__renga-peers__close_pane",
      "mcp__renga-peers__focus_pane",
      "mcp__renga-peers__new_tab",
      "mcp__renga-peers__inspect_pane",
      "mcp__renga-peers__poll_events",
      "mcp__renga-peers__send_keys",
      "mcp__renga-peers__spawn_claude_pane",
      "mcp__renga-peers__set_pane_identity"
    ]
  },
  "env": {
    "CLAUDE_CODE_NO_FLICKER": "1"
  }
}
```

**Bash permission policy**: the legacy `Bash(renga:*)` glob has been removed (since renga 0.14.0+ pane operations, peer messaging, event subscription, scraping, and raw key sending are all available via MCP). The remaining `Bash(renga …)` entries are **operational commands only**:

- `renga --version` / `renga --help`: environment check
- Equivalent of `renga --layout ops` (`--layout:*`): initial layout launch (see `renga-layouts/ops.toml`)
- `renga mcp install` / `uninstall` / `status` / `--help`: MCP server registration management (bootstrap to make `mcp__renga-peers__*` usable)

Pane operations (`renga split` / `close` / `list` / `send` / `events` / `inspect` / `new-tab` etc.) go through MCP tools (`mcp__renga-peers__*`). Do not include the corresponding Bash permissions.

**Note**: the 14 `renga-peers` MCP tools become usable only after running `renga mcp install` once to register the MCP server at user scope. See the README "Installation" section for the registration procedure.

## Lead (`<repo>/.claude/settings.local.json`)

Lead-specific settings. Common entries live at the user level, so write only what only the Lead needs here.

**Narrow policy**: avoid wide allows that grant entire feature sets like `gh:*`; instead, **narrow per subcommand** like `gh issue:*` / `gh pr:*`. For git, also narrow with the colon form `Bash(git add:*)` etc., not `Bash(git *)` (the space-form wildcard).

```json
{
  "permissions": {
    "allow": [
      "mcp__renga-peers__set_summary",
      "mcp__renga-peers__list_peers",
      "mcp__renga-peers__send_message",
      "mcp__renga-peers__check_messages",
      "mcp__renga-peers__list_panes",
      "mcp__renga-peers__spawn_pane",
      "mcp__renga-peers__spawn_claude_pane",
      "mcp__renga-peers__close_pane",
      "mcp__renga-peers__inspect_pane",
      "mcp__renga-peers__poll_events",
      "mcp__renga-peers__send_keys",
      "mcp__renga-peers__set_pane_identity",

      "Bash(git add:*)",
      "Bash(git commit:*)",
      "Bash(git status:*)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(git branch:*)",
      "Bash(git checkout:*)",
      "Bash(git switch:*)",
      "Bash(git push:*)",
      "Bash(git worktree:*)",
      "Bash(git fetch:*)",
      "Bash(git pull:*)",
      "Bash(git stash:*)",
      "Bash(git -C ../workers/claude-org status)",
      "Bash(git -C ../workers/claude-org remote -v)",

      "Bash(gh issue:*)",
      "Bash(gh pr:*)",
      "Bash(gh label:*)",
      "Bash(gh api:*)",
      "Bash(gh gist:*)",
      "Bash(gh run:*)",
      "Bash(gh auth status)",
      "Bash(gh auth login:*)",

      "Bash(python:*)",
      "Bash(python3:*)",
      "Bash(py -3 dashboard/:*)",
      "Bash(py -3 tools/:*)",
      "Bash(py dashboard/:*)",

      "Bash(renga --version)",
      "Bash(renga --help)",
      "Bash(renga --layout:*)",
      "Bash(renga mcp install:*)",
      "Bash(renga mcp uninstall:*)",
      "Bash(renga mcp status:*)",
      "Bash(renga mcp --help)",

      "Bash(sleep:*)",
      "Bash(codex exec:*)",
      "Bash(curl -s -o /dev/null -w \"%{http_code}\" http://localhost:8099/:*)",
      "Bash(curl -s http://localhost:8099/ -o /dev/null -w \"%{http_code}\\\\n\")",
      "PowerShell(Out-File *)"
    ],
    "deny": [
      "Write(*/workers/*/.claude/settings.local.json)",
      "Edit(*/workers/*/.claude/settings.local.json)",
      "Write(*/workers/*/.worktrees/*/.claude/settings.local.json)",
      "Edit(*/workers/*/.worktrees/*/.claude/settings.local.json)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash .hooks/block-workers-delete.sh"
          }
        ]
      }
    ]
  }
}
```

**Duplication of mcp__renga-peers__\***: these duplicate the user-wide settings.json, but the Lead always uses the renga-peers MCP immediately on launch, so we explicitly list them at Lead scope as well to pin the source of truth (so the Lead still works even if user settings drift).

**`permissions.deny` (added in Issue #99 Phase 2)**: forbids the Lead from editing Worker settings files (`workers/<project>/.claude/settings.local.json` and the worktree path `workers/<project>/.worktrees/<task>/.claude/settings.local.json`) **directly via Claude's `Write` / `Edit` tools**. The Lead launches in normal mode (not `bypassPermissions`), so this `permissions.deny` always works via static pattern match.

This deny is limited to gates on Claude's file-editing tools (Write/Edit). The Lead still allows `Bash(python:*)` / `Bash(python3:*)` / `PowerShell(Out-File *)`, so writing `cat > settings.local.json` from Bash/PowerShell is technically still possible. The deny is meant to close off the **main mis-grant path** — the Lead opening the `Edit` tool by hand to rewrite settings — and does not fully cut off everything other than `tools/generate_worker_settings.py`. Full generator-only enforcement (including the Bash side) is Phase 3 work (alongside drift CI scope expansion and escape-hatch design).

**Duplicate renga bootstrap**: duplicates user-wide settings for the same reason — the Lead uses these immediately for initial layout launch and pane control, so we list them explicitly.

**Ordering**: (1) MCP tools, (2) git, (3) gh, (4) python/dashboard, (5) renga bootstrap, (6) other (sleep / codex / curl / PowerShell). Preserve this order when adding new entries.

**About hooks**: `block-workers-delete.sh` blocks recursive deletion of the workers directory (`rm -r` / `rm -rf` / `rm --recursive`). It allows `rm` of individual files. The `renga` command is excluded (to prevent false positives during Worker launch).

**What must not be written**:
- Wide allows (`Bash(git *)`, `Bash(git push *)`, `Bash(git fetch *)`, `Bash(git branch *)`, `Bash(git pull *)`, `Bash(gh:*)`, `Bash(gh *)`)
- Legacy `mcp__claude-peers__*` (migrated to renga-peers in 2025)
- Legacy Bash allows for `renga list/split/send/events/close/inspect *` (replaced by MCP in renga 0.14.0+)
- Past one-shot commands (commands containing a specific PR number / branch name / PID, like `gh pr create --repo ... --head feat/xxx ...`)
- User-specific absolute paths (such as `Read(//c/Users/<you>/Documents/work/**)`)

If these accumulate, you have drift. Periodically prune by reconciling against `permissions.md`.

**Pruning (drift resolution) is automated via the `--prune` mode**: when entries from "What must not be written" above accumulate in `settings.local.json`, you can wholesale-rewrite using the per-role samples in this document as the SOT via `tools/org_setup_prune.py`.

```bash
python tools/org_setup_prune.py --role secretary --dry-run   # diff preview
python tools/org_setup_prune.py --role secretary             # execute (auto-generates .bak)
python tools/org_setup_prune.py --all                        # secretary / dispatcher / curator together
```

**Protecting user extensions**: to keep personally added allow / env / hook entries, place a `settings.local.override.json` in the **same directory** as each settings file. Prune deep-merges it in, and the tool never rewrites the override file. See Step 5 of `.claude/skills/org-setup/SKILL.md` for details.

## Dispatcher (`<repo>/.dispatcher/.claude/settings.local.json`)

The Dispatcher launches claude in Worker panes and inspects pane contents.

**Important**: due to a Sonnet constraint, the Dispatcher launches with `permission_mode=bypassPermissions`, so **both `permissions.allow` and `permissions.deny` are bypassed** (Claude Code official behavior). The effective write boundary and git restrictions can **only be enforced by PreToolUse hooks**. The `hooks.PreToolUse` block below is the Dispatcher's only barrier; do not delete or disable it.

```json
{
  "permissions": {
    "allow": [
      "Bash(claude :*)",
      "Bash(sleep:*)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"{claude_org_path}/.hooks/block-dispatcher-out-of-scope.sh\""
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"{claude_org_path}/.hooks/block-git-push.sh\""
          },
          {
            "type": "command",
            "command": "bash \"{claude_org_path}/.hooks/block-dangerous-git.sh\""
          },
          {
            "type": "command",
            "command": "bash \"{claude_org_path}/.hooks/block-workers-delete.sh\""
          },
          {
            "type": "command",
            "command": "bash \"{claude_org_path}/.hooks/block-no-verify.sh\""
          }
        ]
      }
    ]
  },
  "env": {
    "CLAUDE_ORG_PATH": "{claude_org_path}"
  }
}
```

**Note**: replace `{claude_org_path}` with a resolved absolute path when generating `settings.local.json`. Paths inside hook commands are quoted to handle spaces.

**Hook responsibilities**:
- `block-dispatcher-out-of-scope.sh`: limits the Dispatcher's Edit/Write target paths to `.dispatcher/`, `.state/`, and `knowledge/raw/YYYY-MM-DD-{topic}.md`. Forces delegation to a Worker for application code (`tools/`, `dashboard/`, `tests/`, `.claude/skills/`, `docs/`, `registry/`, etc.)
- `block-git-push.sh`: forbids the Dispatcher from pushing directly (push goes through the Lead)
- `block-dangerous-git.sh`: blocks `git push --force` / `git reset --hard` / `git branch -D`
- `block-workers-delete.sh`: blocks recursive deletion of the workers directory (protects Worker deliverables)
- `block-no-verify.sh`: blocks `--no-verify`-style validation bypass

## Curator (`<repo>/.curator/.claude/settings.local.json`)

The Curator does only knowledge curation. No additional Bash permissions are needed.

```json
{
  "permissions": {
    "allow": []
  }
}
```

## Worker (dynamically generated)

Worker settings are created dynamically in Step 1.5 of org-delegate.

> **Phase 2 onward (Issue #99)**: Worker `settings.local.json` is generated by `tools/generate_worker_settings.py` from the `worker_roles[<role>]` section of `tools/role_configs_schema.json` (3 roles: `default` / `claude-org-self-edit` / `doc-audit`). The JSON shown in this section is reference only; hand-editing is forbidden (drift CI fails). If a new permission pattern is needed, open a PR to add a role to the schema.

```json
{
  "permissions": {
    "allow": [
      "Bash(git add:*)",
      "Bash(git commit:*)",
      "Bash(git status:*)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(git branch:*)",
      "Bash(git checkout:*)",
      "Bash(git switch:*)",
      "Bash(git worktree:*)",
      "Bash(git stash:*)",
      "Bash(sleep:*)"
    ],
    "deny": [
      "Bash(git push *)",
      "Bash(git push)",
      "Bash(rm -rf *)",
      "Bash(rm -r *)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"{claude_org_path}/.hooks/check-worker-boundary.sh\""
          },
          {
            "type": "command",
            "command": "bash \"{claude_org_path}/.hooks/block-org-structure.sh\""
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"{claude_org_path}/.hooks/block-git-push.sh\""
          },
          {
            "type": "command",
            "command": "bash \"{claude_org_path}/.hooks/block-org-structure.sh\""
          }
        ]
      }
    ]
  },
  "env": {
    "WORKER_DIR": "{worker_dir}",
    "CLAUDE_ORG_PATH": "{claude_org_path}"
  }
}
```

**Note**: replace `{claude_org_path}` and `{worker_dir}` with resolved absolute paths when generating `settings.local.json`. Paths inside hook commands are quoted to handle spaces.

**Roles of `deny` and hooks**: Workers launch in normal mode (not `bypassPermissions`), so `permissions.deny` always works via static pattern match. It does not depend on external commands (jq, bash), making it highly reliable. Hooks meanwhile handle dynamic checks like Worker directory boundary checks. Combining the two yields defense in depth. Because `deny` cannot cover embedded commands like `echo foo && git push`, the `block-git-push.sh` hook is kept as a secondary defense. Note that for roles launched with `bypassPermissions` (the Dispatcher), `permissions.deny` is bypassed; only hooks act as a barrier there (see the "Important" note above).
