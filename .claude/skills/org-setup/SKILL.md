---
name: org-setup
description: |
  Skill that installs / updates the Claude Code permission settings and
  environment variables required by every role in the organization
  (Lead / Dispatcher / Curator / Worker) in one shot.
  Triggered by phrases like "configure", "update permissions", "set up",
  "permissions config", "org-setup".
---

# org-setup: install organization permissions in one shot

Place the permissions allow entries and environment variables required by each
role in the organization into the settings files at the correct scope.

## Where settings live and at what scope

Claude Code reads settings from **`.claude/` under the launch directory**.
When launched from a subdirectory, settings in the parent directory are **not** loaded.
For that reason each role needs its own independent settings file.

| Scope | File path | Target |
|---|---|---|
| User-wide | `~/.claude/settings.json` | All projects, all roles |
| Lead | `<repo>/.claude/settings.local.json` | Lead launched at the repository root |
| Dispatcher | `<repo>/.dispatcher/.claude/settings.local.json` | Dispatcher launched in `.dispatcher/` |
| Curator | `<repo>/.curator/.claude/settings.local.json` | Curator launched in `.curator/` |
| Worker | Worker directory's `.claude/settings.local.json` | Created dynamically by org-delegate |

## Required settings per role

The JSON definitions for every role live in **references/permissions.md**. The procedure below references it.

## Procedure

### Step 1: Read the current settings

Read the following 4 files (treat as empty object if absent):

1. `~/.claude/settings.json`
2. `<repo>/.claude/settings.local.json`
3. `<repo>/.dispatcher/.claude/settings.local.json`
4. `<repo>/.curator/.claude/settings.local.json`

### Step 2: Identify the diff

For each file, compare against "Required settings per role" above and identify the missing entries.

### Step 3: Merge and write

Add the missing entries. **Never delete** existing settings.
`permissions.allow` is an array, so preserve existing entries while appending new ones.
`env` is an object, so preserve existing keys while adding new ones.

### Step 4: Report the result

When changes were made:
```
Settings updated:
- ~/.claude/settings.json: added renga, renga-peers permissions
- .dispatcher/.claude/settings.local.json: added permission for the claude launch command
- (no change: .curator/.claude/settings.local.json)
```

When nothing changed:
```
All settings are up to date. No changes.
```

### Step 5: Resolve drift (`--prune` mode)

The normal Steps 1–3 are **additive-only** (only add what is missing; never delete what exists).
Overly broad allows or stale entries that have accumulated in the past therefore stick around forever, so a prune mode is provided that **completely rewrites** `settings.local.json` using `permissions.md` as the source of truth.

Run it via `tools/org_setup_prune.py`:

```bash
# Diff preview (no writes)
python tools/org_setup_prune.py --role secretary --dry-run
python tools/org_setup_prune.py --all --dry-run

# Execute (auto-generates a timestamped .bak, then rewrites)
python tools/org_setup_prune.py --role secretary
python tools/org_setup_prune.py --all
```

Target roles: `secretary` / `dispatcher` / `curator`.
(`user_common` is excluded because `~/.claude/settings.json` coexists with other plugins.
Workers are excluded because org-delegate generates them dynamically.)

#### Protecting user extensions: `settings.local.override.json`

Because prune wholesale-rewrites using the role template in `permissions.md`,
any allow / env / hook you added personally would be wiped out.
To avoid that, place a `settings.local.override.json` in the **same directory**
as each settings file; prune deep-merges it in.

Example: to permanently allow `Bash(my-private-tool:*)` for the Lead, write the
following to `.claude/settings.local.override.json` (the prune tool only reads
this file; it never rewrites it):

```json
{
  "permissions": {
    "allow": ["Bash(my-private-tool:*)"]
  }
}
```

Merge rules:
- `permissions.allow` / `permissions.deny`: union, preserving base order
- `env`: per-key merge (override wins)
- `hooks.PreToolUse[]` etc.: dedupe by equality, then append
- Other scalars: override wins

It is `.gitignore`d (because it is personal). `.gitignore:23-25` already ignores
`.claude/settings.local.override.json` and `.claude/settings.local.json.bak.*`.
`.curator/.claude/` and `.dispatcher/.claude/` are entirely ignored, so they are
covered automatically. For settings to share with the team, add them to
`permissions.md` and update the schema (`tools/role_configs_schema.json`) at the
same time.

`tools/check_role_configs.py` reads the same override file and excludes its
allows from closed-world validation (`_load_override_allow`). So personal
allows added via override do not show up as `unknown allow entry` under CI /
`--include-local`. However `forbidden_allow_exact` (wide allows like `Bash(git *)`)
and `disallow_allow_regex` (e.g. legacy `mcp__claude-peers__*`, now `renga-peers`) still ERROR
even when they appear in override. The safety contract cannot be bypassed via override.

#### Resolving `{claude_org_path}` for the dispatcher

The dispatcher template contains a `{claude_org_path}` placeholder.
The prune tool resolves it in the following order of precedence:

1. The `--claude-org-path <abs>` argument
2. `env.CLAUDE_ORG_PATH` in the existing `settings.local.json`
3. `<abs>` from `bash "<abs>/.hooks/..."` inside an existing hook command

If none can be obtained (fresh install, etc.), pass `--claude-org-path` explicitly:

```bash
python tools/org_setup_prune.py --role dispatcher --claude-org-path "C:/Users/me/work/claude-org"
```

#### Backups

Before rewriting, a `settings.local.json.bak.YYYYMMDD-HHMMSS` is created in the same directory.
On failure, `mv` this `.bak` back to restore the previous state.
Suppress with `--no-backup` if not needed.

## Notes

- `settings.local.json` is assumed to be in `.gitignore` (because it is personal config)
- Take care not to clobber existing settings (plugins etc.) in user-level `~/.claude/settings.json`
- Worker settings are not placed by this skill (org-delegate handles them)
- The canonical reference for prune behavior is the docstring in `tools/org_setup_prune.py` and the tests in `tools/test_org_setup_prune.py`
