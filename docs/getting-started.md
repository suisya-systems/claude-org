# Getting Started

A guide to using claude-org.

---

## Setup

### Prerequisites

Whether you use the one-liner or the manual steps, you need to install the following tools in advance. The installers (`scripts/install.sh` / `scripts/install.ps1`) fail closed when checking for the five required commands `git` / `claude` / `renga` / `gh` / `jq`; Python produces only a warning, and Node.js is checked only on Linux / macOS (none of these are auto-installed). To cover the use cases in the table below, all seven tools are required.

| Tool | Minimum version | Purpose | Install link |
|---|---|---|---|
| **`git`** | Any stable 2.x release | Repository checkout (`git clone`), commits, Worker working-directory management | [git-scm.com/downloads](https://git-scm.com/downloads) |
| **GitHub CLI (`gh`)** | Any stable 2.x release | Pull request creation, Issue operations, CI monitoring (`gh pr checks --watch`) | [cli.github.com](https://cli.github.com/) |
| **Node.js** | v18+ | Runtime for installing `renga` via npm | [nodejs.org](https://nodejs.org/) |
| **Python** | 3.10+ | Running `pip install -e .` for `core-harness` / `claude-org-runtime` (aligned with `requires-python` in `pyproject.toml`) | [python.org/downloads](https://www.python.org/downloads/) |
| **`jq`** | 1.6+ | Formatting and extracting `.state/` JSON / `gh api` output (used in hooks and tools) | [jqlang.org/download](https://jqlang.org/download/) |
| **Claude Code CLI (`claude`)** | Latest stable release | Main executable for each role pane. Initial login is also done when launching `claude` | [claude.ai/code](https://claude.ai/code) |
| **`renga`** | 0.18.0+ | The Layer 3 terminal multiplexer + `renga-peers` MCP server (`npm install -g @suisya-systems/renga@0.18.0`) | [github.com/suisya-systems/renga](https://github.com/suisya-systems/renga) |

In addition, the following Claude Code configuration is required:

- **renga-peers MCP** — inter-instance communication and pane operations within the same tab (register with `renga mcp install`)
- **GitHub CLI authentication** — `gh auth status` must report "Logged in"

### Installation

If the required tools (`git` / `claude` / `renga` / `gh` / `jq`) are installed, you can run a one-liner to clone the repo and run `renga mcp install` in one shot.

**macOS / Linux (bash)**:

```bash
curl -fsSL https://raw.githubusercontent.com/suisya-systems/claude-org/main/scripts/install.sh | bash
cd claude-org
bash scripts/install-hooks.sh
python tools/org_setup_prune.py --user-common-sandbox   # Required once after pulling main (Issue #429 Task B/C + Issue #433 denyWrite)
renga --layout ops
```

**Windows (PowerShell 7+)**:

```powershell
iwr -useb https://raw.githubusercontent.com/suisya-systems/claude-org/main/scripts/install.ps1 | iex
cd claude-org
bash scripts/install-hooks.sh                            # Run on Git Bash / WSL
py -3 tools/org_setup_prune.py --user-common-sandbox     # Required once after pulling main (Issue #429 Task B/C + Issue #433 denyWrite)
renga --layout ops
```

The scripts check whether the prerequisite commands are installed. If any are missing, they exit after showing setup instructions (they do not install anything automatically).

If you want to change the clone directory name, run the script directly instead of using the one-liner and pass flags to it (flags cannot be forwarded through pipe execution):

```bash
# bash: save the script, then run it
curl -fsSLo /tmp/install.sh https://raw.githubusercontent.com/suisya-systems/claude-org/main/scripts/install.sh
bash /tmp/install.sh --dir my-claude-org

# PowerShell: download it first, then run it
iwr -useb https://raw.githubusercontent.com/suisya-systems/claude-org/main/scripts/install.ps1 -OutFile $env:TEMP\install.ps1
pwsh -NoProfile -File $env:TEMP\install.ps1 -Dir my-claude-org
```

For available flags, see `bash install.sh --help` / `pwsh install.ps1 -Help`.

If you do not use the one-liner, run the following manually:

```bash
git clone https://github.com/suisya-systems/claude-org.git
cd claude-org
renga mcp install                                            # First time only. Registers renga-peers MCP at user scope
bash scripts/install-hooks.sh                                # Enables the pre-commit secret scanner
python tools/org_setup_prune.py --user-common-sandbox        # Required once after pulling main (Issue #429 Task B/C + Issue #433 denyWrite)
renga --layout ops
```

Based on the definition in `renga-layouts/ops.toml`, the Lead (`Secretary`) pane starts up.
Once Claude Code in the Lead pane has started, **run the following in order**:

1. `/org-setup` — places role-specific `settings.local.json` files (Lead, Dispatcher, Curator, Worker) and required hooks. **Required on first run only**. If you skip this, you will get a large number of permission prompts for renga-peers MCP / git / gh.
2. `/org-start` — starts the organization. The Dispatcher is spawned in the same tab (the Curator is launched on demand and temporarily once learnings accumulate).

`/org-setup` is **additive-only** (it only adds missing pieces and does not remove existing ones). If you want to return drifted settings to the baseline, manually replace `settings.local.json` using the role-specific sample JSON in [`.claude/skills/org-setup/references/permissions.md`](../.claude/skills/org-setup/references/permissions.md).

> **⚠️ Required once after pulling main (Issue #429 Task B / C + Issue #433)**: Because personal-path entries have been removed from the shared `.claude/settings.json` (denyRead entries such as `Read(~/.ssh/*)` / `Read(~/.aws/*)`, and denyWrite entries such as `~/.claude/settings.json`), **run `python tools/org_setup_prune.py --user-common-sandbox` once** on first setup / after pulling main (a single flag covers both denyRead and denyWrite). If you skip this, your personal-environment sandbox defenses will be temporarily weakened (see [README §Reinforcing the personal sandbox](../README.md) and [`.claude/skills/org-setup/references/permissions.md`](../.claude/skills/org-setup/references/permissions.md)). Note that `~/.config/gh` is excluded from the candidate list because gh CLI is required for the Lead's normal workflow; if a past revision left it in your personal `settings.json`, it will be pruned automatically on the next run.
>
> ```bash
> # Preview the diff
> python tools/org_setup_prune.py --user-common-sandbox --dry-run
>
> # Apply (idempotent — re-running is a no-op)
> python tools/org_setup_prune.py --user-common-sandbox
> ```

### Compatibility Preflight (Optional, Recommended)

Before running `/org-start`, you can verify that your renga version and MCP tool surface meet claude-org's requirements:

```bash
py -3 tools/check_renga_compat.py            # Windows
python3 tools/check_renga_compat.py          # macOS / Linux
```

- renga version (requires 0.18.0 or later)
- `renga-peers` MCP registration (`Connected` in `claude mcp list`)
- whether the required 14 tools appear in tools/list

If you want machine-readable JSON, use `--json`. Scripts that want to handle failures via exit code should use this:

```bash
py -3 tools/check_renga_compat.py --json
```

This script does not require a live renga session (static checks + MCP stdio probe only), so you can run it either before or after `renga --layout ops`.

---

## Basic Usage

### Start It Up

After the initial clone, follow the "Installation" section above and run `/org-setup` → `/org-start` once in that order (`/org-setup` prevents a flood of permission prompts).

From the second time onward, just open the Lead pane with `renga --layout ops` and run `/org-start` in Claude Code.
If there is saved state from the previous session, it will be reported, and the Dispatcher (task assignment) will start automatically. The Curator (knowledge organization) is not resident; it is launched automatically and temporarily once learnings accumulate.

```
You:  /org-start
Lead: The organization has started.
      Previous state: blog article update is complete, e-commerce site fixes are in progress.
      Dispatcher has started (the Curator will be launched automatically and temporarily once enough learnings accumulate).
      What would you like to do?
```

### Tell It What You Want to Do

Just say what you want to do.
You do not need to use technical terms. The Lead Claude will understand the request and assign the work to the appropriate Workers.
For consultations or questions, the Lead answers directly.

```
You:  I want to add a new article to the blog
Lead: The blog, got it. Please tell me the article title and content.
```

The Lead identifies "the blog" from the registered projects and proceeds appropriately.
If it cannot tell which project you mean, it will ask.

```
Lead: Which project is it?
      ・Blog (company blog site)
      ・E-commerce Site (online store)
      ・Admin Panel (internal admin tool)
```

### Request Multiple Tasks at Once

```
You:  Update the blog article, and also fix the product page on the e-commerce site
Lead: I will handle these two tasks in parallel.
      ・Blog: article update
      ・E-commerce Site: product page fix
      I have assigned an owner to each. I will report back when they are done.
```

Separate Workers handle the tasks in parallel behind the scenes. Once they finish, you get a combined report.

### Check the Work Results

The Lead reports results without technical jargon.

```
Lead: The blog article update is complete.
      ・Added the new article "New Products for Spring 2026"
      ・The changes have already been submitted. They are now waiting for review
```

### Pause

```
You:  That's it for today
Lead: The organization has been suspended. The state has been saved.
```

You can safely close the terminal.

### Resume

Next time, start `renga --layout ops` in this repository directory and enter Claude Code in the Lead pane. It will automatically report the previous state.

```
Lead: Previous state (suspended at 4/5 18:30):
      ・Blog article update: complete
      ・E-commerce site product page: in progress (60%)
      ・Add tests: not started yet
      Continue?
You:  Please continue with the e-commerce site work
Lead: Understood. I will resume the e-commerce site work.
```

---

## Troubleshooting

### A Large Number of Permission Prompts Appear at Startup

**Symptoms**: A permission dialog appears every time `mcp__renga-peers__*`, `git`, or `gh` tools are called in the Lead, Dispatcher, or Worker roles.

**Diagnosis**: First, check the state of `settings.local.json` for the affected role.

```bash
python tools/check_role_configs.py --include-local
```

If you are running it inside a specific role's worktree, use it together with `--role <secretary|dispatcher|curator|worker>`. The output lists missing / unknown allow entries by role, as well as missing required hooks.

**Fix**:

- **`settings.local.json` does not exist / many required allow entries and hooks are missing**: Run `/org-setup` in Claude Code in the Lead pane (it is additive-only, so it will not break existing settings). Afterward, run `check_role_configs.py` again to confirm the missing entries are gone.
- **The missing entries are local and limited (only 1-2 specific allow entries are missing)**: Add the relevant entries in the order schema → `permissions.md` → actual `settings.local.json` (same procedure as the drift resolution flow in the next section).

### `tools/check_role_configs.py` Reports Drift Between schema/permissions/settings

**Symptoms**: CI or your local `python tools/check_role_configs.py --include-local` reports `unknown allow entry`, `permissions.md mismatch`, or `missing required hook`.

**Diagnosis**: Determine whether the source of the drift is on the schema side, the `permissions.md` side, or the actual `settings.local.json` side.

```bash
python tools/check_role_configs.py --include-local        # Validate all roles at once
python tools/check_role_configs.py --role <role>          # Validate the affected role individually in its worktree
git diff tools/org_extension_schema.json                  # Check recent edits to the org-extension schema on this side
git diff .claude/skills/org-setup/references/permissions.md
```

The canonical framework schema is bundled by the `claude-org-runtime` package (via `core_harness.schema.load_framework_schema()`), and `tools/org_extension_schema.json` is the source of truth for org-extension entries specific to this side. **When adding or changing rules, always apply them in the order schema → `permissions.md` → actual `settings.local.json`**. If you do it in reverse, CI will detect drift.

**Fix** — depending on where the drift came from:

- **An allow entry not registered in the schema has been introduced into `permissions.md` or actual settings**: If the entry is needed, add it to the schema first, then propagate it to `permissions.md` / `settings.local.json`. If it is not needed, remove it.
- **The sample JSON in `permissions.md` has diverged from the schema**: Treat the schema as correct and rewrite the `permissions.md` side to match it.
- **Drift remains in `settings.local.json` even after rerunning `/org-setup`**: Because it is additive-only, it will not remove anything automatically. Restore the affected role's `settings.local.json` to baseline by **replacing it entirely** with the role-specific sample JSON in `.claude/skills/org-setup/references/permissions.md` (**last resort**). The `{worker_dir}` / `{claude_org_path}` placeholders in the Worker sample must be manually resolved to absolute paths in the real environment when replacing them. If you had added local custom overrides, note them down in advance.

### JSON Parse Error / Load Failure in the schema

**Symptoms**: `check_role_configs.py` or `/org-setup` fails immediately while loading the schema (JSON syntax error, etc.).

**Diagnosis**:

```bash
git status tools/org_extension_schema.json
git diff tools/org_extension_schema.json
python -c "import json; json.load(open('tools/org_extension_schema.json'))"
```

**Fix**: If a recent edit broke it, revert it with `git restore tools/org_extension_schema.json`, or temporarily save the uncommitted changes with `git stash push tools/org_extension_schema.json` and try again. After fixing the schema syntax, always run `python tools/check_role_configs.py --include-local` before committing.

---

## View the Big Picture in the Dashboard

If you say "Show me the dashboard," you can view the organization's overall state in the browser.

```
You:  Show me the dashboard
Lead: (starts the live server and opens http://localhost:8099 in the browser)
```

The dashboard shows the following:

- **Project list** — registered projects and common task examples
- **Work status** — currently in progress, completed, and on-hold work items
- **Recent activity** — a timeline of what happened and when
- **Accumulated knowledge** — what kinds of knowledge have been collected by theme

The dashboard updates automatically via SSE. You do not need to reload the browser; the latest state is reflected in real time.

---

## Skill List

| Command | Purpose | When to use it |
|---|---|---|
| `/org-start` | Start the organization | **Run once immediately after Claude Code starts** |
| `/org-delegate` | Assign work | Triggered automatically when work is requested (the Lead is the command center, Workers do the actual work) |
| `/org-suspend` | Suspend work | Triggered automatically when you say "done" or "pause" |
| `/org-resume` | Resume work | Automatically called from org-start if work was suspended previously |
| `/org-retro` | Record learnings | After work is completed (often triggered automatically) |
| `/org-curate` | Organize knowledge | Runs automatically and temporarily once learnings accumulate. Can also be run manually |
| `/org-dashboard` | Show the dashboard | Triggered when you say "Show me the dashboard" |

In general, you do not need to consciously call skills yourself.
The Lead Claude uses the right skills based on the situation.

---

## Directory Structure

```
claude-org/
  CLAUDE.md              <- Behavior guidelines for the Lead Claude
  .claude/skills/        <- The organization's skills (tracked by git)
  .state/                <- Session state (not tracked by git)
  dashboard/             <- Dashboard (HTML/CSS/JS/server.py are tracked by git)
  knowledge/
    raw/                 <- Raw learnings (not tracked by git)
    curated/             <- Organized knowledge (tracked by git)
  registry/
    projects.md          <- Project list (registered automatically)
  docs/                  <- Documentation
```

### Things You May Want to Touch
- `knowledge/curated/` — review the organized knowledge (generated automatically)

### Things You Do Not Need to Touch
- `registry/projects.md` — registered automatically when work is requested
- `dashboard/` — the dashboard's design and data. Managed automatically
- `.claude/skills/` — skill definitions. Improvement suggestions are generated automatically as the organization grows
- `.state/` — session state. Managed automatically
- `CLAUDE.md` — you can change it if you want, but keep it thin

---

## Accumulating Knowledge and Growing

The more you use the organization, the smarter it gets.

1. Each time work is completed, the learning is recorded
2. At a natural break point (when a worker finishes), it is automatically organized (when 5 or more items have accumulated)
3. Organized knowledge is saved by theme
4. If improvements to skills or processes are needed, suggestions are made
5. Once approved, the improvements are applied, and from the next run onward the entire organization operates in the improved state

---

## Tips

- **It is okay if the terminal closes suddenly**: state is saved periodically. It will be restored the next time you start it. Still, formally suspending it by saying "That's it for today" leaves a more accurate state.
- **If it feels like there is too much work**: just say "Do them one at a time." The Lead prioritizes human instructions.
- **If the learning is off target**: say "That learning is unnecessary" and it will not be recorded. You can also reject improvement suggestions.
- **Project registration is automatic**: when you request work for a new project, it is automatically registered after confirming the name and location.
- **You can view the dashboard anytime**: say "Show me the dashboard" or "Show me the big picture" and it will open in the browser.
