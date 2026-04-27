# Worker instruction template

The task-specific instruction sent via renga-peers `send_message` (`to_id="worker-{task_id}"`).
Permissions, reporting destinations, SUSPEND handling, and knowledge recording are consolidated in worker-claude-template.md (via CLAUDE.md), so they are not repeated here.

## Template

```
Please carry out the following task. Detailed code of conduct is described in CLAUDE.md.

## Task
{Concretely describe the task's goal and the expected deliverable}

## Project preparation
Important: your working directory is the absolute path described in CLAUDE.md.
First, run `pwd` and confirm it matches the working directory in CLAUDE.md.
All file creation is restricted to inside that directory. Moving to `..` and reproducing the claude-org structure is prohibited.
{Choose one of the following based on the directory pattern}

### Pattern A (project directory, first time):
{Choose one of the following}
- For an existing local project: run `git clone {local path}` inside the current directory.
- For a remote repository: run `git clone {URL}` inside the current directory.
- For a new project: run `git init` in the current directory (the path output by `pwd`) and create files directly. Do not create directories that mimic the claude-org structure (.claude/, .state/, etc.).

### Pattern A (project directory, reuse):
This directory was used by a previous task. Existing files and git history remain.
No clone is needed. {Note any handoff items}

### Pattern B (worktree):
This directory is prepared as a git worktree, checked out on branch `{branch_name}`.
No clone is needed. Start working directly.

### Pattern C (ephemeral):
{Choose one of the following}
- For an existing repository: run `git clone {URL}` inside the current directory and work inside the cloned directory
- For an existing local project: run `git clone {local path}` inside the current directory
- For a new project: run `git init` in the current directory (the path output by `pwd`) and create files directly. Do not create directories that mimic the claude-org structure (.claude/, .state/, etc.)

## Branch strategy
{Specify the branch name, or work directly on main, etc.}

## How to work
Work directly in auto mode. Do not use Plan mode.

## Constraints
{Note any language, framework, test requirements, etc.}

## Verification depth: {full | minimal}
**Do not delete this line**; always send it. The Lead fills in exactly one of the two values.
The default is `full`. Choose `minimal` only for trivial fixes; the Lead is the one filling it in.

- **full** (new feature implementation / fix / refactor / adding tests / hook / skill / settings edits, etc., anything that changes code or behavior)
  - **Required regardless of whether codex is available**: run the repository's normal verification (existing test suite / lint / type-check, etc.) to green and report in the normal completion format (deliverable description, remaining work, PR draft / retro record)
  - **Additional gate (optional)**: after commit completes, if the `codex` CLI is available, run Codex self-review via `codex exec --skip-git-repo-check`
    - Detection commands: `command -v codex` (Bash/zsh) / `Get-Command codex -ErrorAction SilentlyContinue` (PowerShell)
    - In environments where codex is not installed, skip the self-review and proceed to the completion report on the normal verification alone (the round discipline below does not apply)
  - **The following applies only when codex was run**:
    - Stack a fix commit before the completion report for Blocker / Major
    - **If the same finding category (e.g. loose-match precision / type narrowing, etc.) cannot be eliminated in 3 rounds, treat it as a design issue**. Send the completion report immediately and ask the Lead for a scope-reduction decision (to prevent infinite loops)
    - Minor / Nit are left in place by default. Document them as known limitations in README / Issue / PR body
    - Do not use the `codex:rescue` skill (there are cases of >18-minute hangs; direct `codex exec` is more stable)
  - Example review instruction: `codex exec --skip-git-repo-check "Review the diff between this branch and main. Classify findings as Blocker/Major/Minor/Nit and add target file:line and the rationale to each, concise in Japanese"`

- **minimal** (trivial fixes: CI output formatting / typo / comment edits / matching to existing test format, etc., where the instruction limits changes to a few lines in 1 file)
  - Apply the requested fix → `git add` → `git commit` straight through
  - Operational checks beyond Codex self-review / additional test runs / diff inspection are **strictly forbidden**
  - The completion report is a single line sent to the Lead (`secretary`):
    - `done: {short commit SHA} {changed file name}` (e.g. `done: be8f497 tests/test-block-pretooluse-hooks.sh`)
    - SHA is from `git rev-parse --short HEAD`; file name is one if a single file, space-separated if multiple
    - Other information (deliverable description, PR draft, remaining points, etc.) is unnecessary. push / PR creation are done on the Lead side
  - Retro record (`knowledge/raw/`) is **not needed** for minimal (trivial fixes are presumed to have no reusable lessons). If you make a non-obvious discovery, you may create one as in `full`

**Choosing the value is the Lead's responsibility.** The Worker follows the value (`full` or `minimal`) as written in the instruction; do not switch on your own. If this line itself was not sent at dispatch time, or the value is unclear, the Worker should confirm with the Lead (do not silently fall back to `full`).
```

## Consistency grep target list for cross-cutting operational changes

When delegating a **cross-cutting change** (one that does not stay in a single file but spans multiple roles / skills / settings / docs) — such as operational mode, common settings, naming conventions — explicitly state the grep scope for consistency check in the "Constraints" or "Task" section of the Worker instruction. Without scope, the Worker fixes only the files in front of them and misses the same-name references on the other-role / docs side (often happens with renames / mode changes).

### Examples judged as "cross-cutting"

- **Operational mode change**: switching the default of Plan / auto / `bypassPermissions` etc.
- **Wholesale change of permissions / hook settings**: cross-cutting rewrites to allow / deny / hooks of `.claude/settings*.json`
- **Renaming communication channels / MCP server names**: renaming peer names of renga-peers / MCP server names / role identifiers (e.g. `foreman` → `dispatcher`)
- **Adding / removing common flags / env vars**: environment variables or CLI flags read by all roles or multiple skills

Conversely, behavior changes confined to a single skill or role (e.g. format adjustment within `org-retro`) are not cross-cutting, so this section is unneeded.

### Recommended grep target directories

If judged cross-cutting, **enumerate at least the following as the grep scope** in the Worker instruction. Trim those that don't exist depending on the project layout:

- `.claude/` — in addition to skills (`skills/`), include `settings.json` / `settings.local.json`. Permissions / hook / env changes often remain in the settings themselves; scanning only `.claude/skills/` misses the canonical settings
- `registry/` — projects.md / org-config.md / worker-directory.md
- `knowledge/curated/` — accumulated operational knowledge (patterns written under old names tend to remain)
- `dashboard/` — JSON generation scripts and templates
- `.dispatcher/` — Dispatcher role's runtime / prompt
- `.curator/` — Curator role's runtime / prompt
- `.hooks/` — PreToolUse / PostToolUse hook scripts themselves (references to hook file names / role identifiers tend to remain)
- `docs/` — public documentation
- `tools/` — checkers / helper scripts (`check_role_configs.py`, etc.)
- `tests/` — hook / runner / checker tests (missing fixture names from rename / mode changes can break CI)

Example Worker instruction:

```
## Constraints
- grep for any remaining references to old name `foo` in the following directories, and replace all with the new name `bar` if found:
  - .claude/                (also include settings.json / settings.local.json)
  - registry/
  - knowledge/curated/
  - dashboard/
  - .dispatcher/
  - .curator/
  - .hooks/
  - docs/
  - tools/
  - tests/
- Example grep command (Bash / Git Bash / WSL): `grep -rn "foo" .claude/ registry/ knowledge/curated/ dashboard/ .dispatcher/ .curator/ .hooks/ docs/ tools/ tests/`
- Example grep command (PowerShell): `Select-String -Path .claude\,registry\,knowledge\curated\,dashboard\,.dispatcher\,.curator\,.hooks\,docs\,tools\,tests\ -Pattern "foo" -Recurse`
```

If the old / new names are not yet decided at delegation time, run the Worker in two steps: "detect the target patterns and list them → confirm with the Lead → replace".

## Notes on use

- Make the task description concrete; ambiguous instructions raise the Worker's judgment cost
- Always state constraints explicitly when there are any
