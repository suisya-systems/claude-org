---
name: org-setup
description: |
  Place and update the Claude Code permission settings and environment
  variables required by every role in the org (Lead / Dispatcher /
  Curator / Worker), in one go.
  Triggers: "set up", "update permissions", "do the setup",
  "permissions config", "org-setup", etc.
effort: low
allowed-tools:
  - Read
  - Edit
  - Write
  - Bash(python tools/org_setup_prune.py:*)
  - Bash(py -3 tools/org_setup_prune.py:*)
  - Bash(python tools/check_role_configs.py:*)
  - Bash(py -3 tools/check_role_configs.py:*)
---

# org-setup: place all the org's permission settings

Place the per-role `permissions.allow` entries and environment variables that each role of the org needs into the right settings file at the right scope.

> **Transport layer both systems (`ORG_TRANSPORT`: default `renga` / opt-in `broker`)**: the messaging MCP allows that this skill places are **default `renga`** (`ORG_TRANSPORT` unset) at the `mcp__renga-peers__*` tier. **`references/permissions.md` stays unchanged as a renga anchor (byte-comparison target)**, and broker substitution happens on the generation/verification tool side rather than in the prose: `tools/org_setup_prune.py` (per-role allow / `--user-common-allowlist`) and `tools/check_role_configs.py` project the `mcp__renga-peers__*` block to the broker messaging tier (`mcp__org-broker__*`) when `ORG_TRANSPORT=broker` (driven by the runtime `transport_allowlist` descriptor, Epic #6 E). **Default-renga is identity** (generated artifacts are byte-equivalent / file no-op), so this skill's procedure and report text can be used as-is. The design SoT is transport-lab `docs/design/ja-migration-plan.md` §5.3; the contract is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (awaiting ratification).

## Settings files and their scopes

Claude Code reads settings from `**.claude/`** under the directory it was started in.
If started in a subdirectory, the parent's settings are **not** loaded.
Each role therefore needs its own settings file.

| Scope | File path | Applies to |
|---|---|---|
| User-wide | `~/.claude/settings.json` | Every project, every role |
| Lead | `<repo>/.claude/settings.local.json` | Lead pane started at the repo root |
| Dispatcher | `<repo>/.dispatcher/.claude/settings.local.json` | Dispatcher pane started in `.dispatcher/` |
| Curator | `<repo>/.curator/.claude/settings.local.json` | Curator pane started in `.curator/` |
| Worker | `<worker_dir>/.claude/settings.local.json` | Created dynamically by org-delegate |

## Per-role required settings

The full JSON definitions for every role live in **references/permissions.md**. The procedure below references that file.

## Procedure

### Step 1: read current settings

Read these 4 files (treat as `{}` if absent):

1. `~/.claude/settings.json`
2. `<repo>/.claude/settings.local.json`
3. `<repo>/.dispatcher/.claude/settings.local.json`
4. `<repo>/.curator/.claude/settings.local.json`

### Step 2: identify diffs

For each file, compare against the "Per-role required settings" above and identify the missing entries.

### Step 3: merge and write

Add the missing entries. **Never delete** existing settings.
`permissions.allow` is an array — append new entries while preserving existing ones.
`env` is an object — add new keys while preserving existing ones.

### Step 4: report results

When changes were made:
```
Settings updated:
- ~/.claude/settings.json: added renga, renga-peers permissions
- .dispatcher/.claude/settings.local.json: added claude launch-command permission
- (no change: .curator/.claude/settings.local.json)
```

When no changes were needed:
```
All settings are up to date. No changes.
```

### Step 5: drift sweep (`--prune` mode)

The regular Step 1–3 path is **additive-only** (only adds missing entries; never removes existing ones).
Old, over-broad allow entries accumulated in the past stick around forever, so a prune mode is provided that **fully rewrites** `settings.local.json` from `permissions.md` as the SoT.

Run it with `tools/org_setup_prune.py`:

```bash
# Diff preview (no rewrite)
python tools/org_setup_prune.py --role secretary --dry-run
python tools/org_setup_prune.py --all --dry-run

# Run (auto-creates a timestamped .bak, then rewrites)
python tools/org_setup_prune.py --role secretary
python tools/org_setup_prune.py --all
```

Targets: `secretary` / `dispatcher` / `curator`.
(`user_common` lives in `~/.claude/settings.json` alongside other plugins, so it is excluded.
Workers are created dynamically by org-delegate, so they are excluded.)

#### User-extension protection: `settings.local.override.json`

Because prune fully rewrites from the role template in `permissions.md`, any allow / env / hook the user added personally would be wiped. To prevent this, place a file named `settings.local.override.json` in the **same directory** as the corresponding settings file; the prune tool deep-merges it during rewrite.

Example: to permanently allow `Bash(my-private-tool:*)` for the Lead, write the following in `.claude/settings.local.override.json` (the prune tool only reads this file; it never rewrites it):

```json
{
  "permissions": {
    "allow": ["Bash(my-private-tool:*)"]
  }
}
```

Merge rules:
- `permissions.allow` / `permissions.deny`: union, preserving the base order.
- `env`: per-key merge (override wins).
- `hooks.PreToolUse[]` and similar: append after equality-based dedup.
- Other scalars: override wins.

The override file is `.gitignore`d (since it is personal). `.gitignore:23-25` already ignores `.claude/settings.local.override.json` and `.claude/settings.local.json.bak.*`. `.curator/.claude/` and `.dispatcher/.claude/` are ignored as a whole, so anything underneath them is automatically covered. Settings you want to share with the team should be added to `permissions.md` (and to `tools/org_extension_schema.json` at the same time).

`tools/check_role_configs.py` reads the same override file and excludes its allow entries from closed-world validation (`_load_override_allow`). So entries you add via override do not appear as `unknown allow entry` in CI / `--include-local`.
However, `forbidden_allow_exact` (wide-allow such as `Bash(git *)`) and `disallow_allow_regex` (the legacy `mcp__claude-peers__*`, current `renga-peers`, etc.) are still ERROR even when present in override — safety contracts cannot be bypassed via override.

#### Resolving `{claude_org_path}` for the Dispatcher

The Dispatcher template contains a `{claude_org_path}` placeholder. The prune tool resolves it in this priority order:

1. The `--claude-org-path <abs>` argument.
2. `env.CLAUDE_ORG_PATH` in the existing `settings.local.json`.
3. The `<abs>` extracted from `bash "<abs>/.hooks/..."` in an existing hook command.

If none of these are available (e.g., a fresh install), pass `--claude-org-path` explicitly:

```bash
python tools/org_setup_prune.py --role dispatcher --claude-org-path "C:/Users/me/work/claude-org"
```

#### Backups

Before rewriting, the tool creates `settings.local.json.bak.YYYYMMDD-HHMMSS` in the same directory. On failure you can `mv` the `.bak` back to recover. Suppress backup with `--no-backup` if not needed.

## Caveats

- `settings.local.json` is assumed to be `.gitignore`d (it is personal).
- Be careful editing the user-level `~/.claude/settings.json` so that you do not break existing settings (plugins, etc.).
- This skill does not place worker settings (org-delegate handles those).
- The canonical reference for the prune behavior is the docstring of `tools/org_setup_prune.py` and the tests in `tools/test_org_setup_prune.py`.
