# Getting Started

A usage guide for claude-org.

---

## Setup

### Prerequisites

The following must all be installed and configured. See [README.md](../README.md#quickstart) for details.

- **Claude Code** — the AI agent itself
- **renga** — terminal multiplexer (used to manage the org's panes)
- **renga-peers MCP** — same-tab inter-instance communication and pane control (registered with `renga mcp install`)
- **GitHub CLI (`gh`)** — authenticated (verify with `gh auth status`)

### Install

If the dependencies (`git` / `claude` / `renga` / `gh`) are present, a one-liner clones the repo and runs `renga mcp install`.

**macOS / Linux (bash)**:

```bash
curl -fsSL https://raw.githubusercontent.com/suisya-systems/claude-org/main/scripts/install.sh | bash
cd claude-org
bash scripts/install-hooks.sh
renga --layout ops
```

**Windows (PowerShell 7+)**:

```powershell
iwr -useb https://raw.githubusercontent.com/suisya-systems/claude-org/main/scripts/install.ps1 | iex
cd claude-org
bash scripts/install-hooks.sh   # run inside Git Bash / WSL
renga --layout ops
```

The script checks whether each prerequisite is present and, if any is missing, prints installation guidance and exits (it does not auto-install).

To clone into a non-default directory name, don't use the one-liner — download the script and pass a flag (a piped invocation cannot forward flags):

```bash
# bash: save the script first, then run it
curl -fsSLo /tmp/install.sh https://raw.githubusercontent.com/suisya-systems/claude-org/main/scripts/install.sh
bash /tmp/install.sh --dir my-claude-org

# PowerShell: download then run
iwr -useb https://raw.githubusercontent.com/suisya-systems/claude-org/main/scripts/install.ps1 -OutFile $env:TEMP\install.ps1
pwsh -NoProfile -File $env:TEMP\install.ps1 -Dir my-claude-org
```

For all flags see `bash install.sh --help` / `pwsh install.ps1 -Help`.

If you skip the one-liner, run the steps manually:

```bash
git clone https://github.com/suisya-systems/claude-org.git
cd claude-org
renga mcp install              # first time only — registers the renga-peers MCP at user scope
renga --layout ops
```

A Lead pane comes up per the definition in `renga-layouts/ops.toml`.
Once the Lead's Claude Code is up, **run the following in order**:

1. `/org-setup` — places per-role `settings.local.json` (Lead, Dispatcher, Curator, Worker) and the required hooks. **Required on the first run.** Without it, `renga-peers` MCP / git / gh produce a flood of permission prompts.
2. `/org-start` — boots the organization. The Dispatcher and the Curator are spawned in the same tab.

`/org-setup` is **additive-only** (it adds what's missing without removing what exists). To return drift back to the baseline, replace `settings.local.json` by hand using the per-role sample JSON in [`.claude/skills/org-setup/references/permissions.md`](../.claude/skills/org-setup/references/permissions.md).

### Compatibility preflight (optional, recommended)

Before running `/org-start`, you can verify that the renga version and MCP tool surface meet claude-org's requirements:

```bash
py -3 tools/check_renga_compat.py            # Windows
python3 tools/check_renga_compat.py          # macOS / Linux
```

This checks:

- The renga version (≥ 0.18.0)
- That the `renga-peers` MCP is registered (`claude mcp list` reports Connected)
- That all 14 required tools appear in `tools/list`

For machine-readable JSON, pass `--json`. Use that variant in scripts that want to react to the exit code:

```bash
py -3 tools/check_renga_compat.py --json
```

The script does not require a live renga session (static checks plus an MCP stdio probe), so it is safe to run before or after `renga --layout ops`.

---

## Day-to-day usage

### Booting

After the first clone, follow the "Install" section above and run `/org-setup` then `/org-start`, in that order, exactly once (skipping `/org-setup` will produce a flood of permission prompts).

From the second session onward, just open the Lead pane with `renga --layout ops` and run `/org-start` in Claude Code.
If a previous state exists, it is reported, and the Dispatcher (work assignment) and Curator (knowledge curation) are spawned automatically.

```
You:    /org-start
Lead:   The organization is up.
        Previous state: blog-post update completed; storefront fix is in progress.
        The Dispatcher and the Curator have been started.
        What would you like to do?
```

### Stating what you want done

Just say what you want, in plain language.
You don't need technical vocabulary; the Lead understands the request and dispatches a suitable Worker.
For questions and discussion, the Lead answers directly.

```
You:    I want to add a new post to the blog
Lead:   Got it — the blog. What's the title and content?
```

The Lead resolves "the blog" against the registered projects and proceeds appropriately.
If the project is ambiguous, the Lead asks back with a list:

```
Lead:   Which project do you mean?
        - blog (company blog site)
        - storefront (e-commerce site)
        - admin console (internal admin tool)
```

### Asking for several things at once

```
You:    Update the blog post, and also fix the product page on the storefront
Lead:   I'll run the two in parallel:
        - blog: post update
        - storefront: product-page fix
        Each has been assigned. I'll report back as they complete.
```

Behind the scenes, separate Workers run in parallel; reports come back as they finish.

### Reading the result

The Lead reports without technical jargon.

```
Lead:   The blog post update is complete.
        - Added a new post titled "Spring 2026 New Arrivals"
        - The change has been submitted; it's awaiting review
```

### Suspending

```
You:    We're done for today
Lead:   The organization has been suspended. State has been saved.
```

You can safely close the terminal at this point.

### Resuming

Next time you start `renga --layout ops` in this repository's directory and enter the Lead's Claude Code, the previous state is reported automatically.

```
Lead:   Previous state (suspended at 4/5 18:30):
        - Blog post update: complete
        - Storefront product page: in progress (60%)
        - Test addition: not started
        Continue?
You:    Please continue the storefront work
Lead:   Understood. Resuming the storefront task.
```

---

## Troubleshooting

### A flood of permission prompts at boot

**Symptoms**: any of the Lead, Dispatcher, or Worker raises a permission dialog every time it calls `mcp__renga-peers__*` / `git` / `gh` tools.

**Diagnosis**: first, inspect the state of that role's `settings.local.json`:

```bash
# Windows: prefer `py -3`; on POSIX use `python3` (`python` is a fallback when neither launcher is available)
py -3 tools/check_role_configs.py --include-local
```

To inspect inside a specific role's worktree, also pass `--role <secretary|dispatcher|curator|worker>` (`secretary` is the implementation identifier for the Lead role; the CLI literal is kept as-is). The output enumerates per-role missing/unknown allow entries and missing required hooks.

**Fix**:

- **No `settings.local.json`, or many required allows and hooks are missing**: run `/org-setup` from the Lead's Claude Code (additive-only — existing settings are not destroyed). After it runs, re-run `check_role_configs.py` to confirm the missing entries are gone.
- **Only a couple of allows are missing locally**: add them in the order schema → `permissions.md` → actual `settings.local.json` (the same flow as the next section's drift fix).

### `tools/check_role_configs.py` reports drift between schema, permissions, and settings

**Symptoms**: CI or local `py -3 tools/check_role_configs.py --include-local` (POSIX: `python3 tools/check_role_configs.py --include-local`) reports `unknown allow entry` / `permissions.md mismatch` / `missing required hook`.

**Diagnosis**: identify which side the drift is on — schema, `permissions.md`, or actual `settings.local.json`.

```bash
# Windows: prefer `py -3`; on POSIX use `python3`
py -3 tools/check_role_configs.py --include-local        # validate all roles at once
py -3 tools/check_role_configs.py --role <role>          # individual validation in that role's worktree
git diff tools/role_configs_schema.json                   # recent edits on the schema side
git diff .claude/skills/org-setup/references/permissions.md
```

`tools/role_configs_schema.json` is the canonical source. **Add or modify rules in the order schema → `permissions.md` → actual `settings.local.json`**, always. Reverse order will trip CI's drift detector.

**Fix** — by where the drift is:

- **An allow entry not registered in the schema is present in `permissions.md` or actual settings**: if it's needed, add it to the schema first, then propagate to `permissions.md` and `settings.local.json`. If it isn't, delete it.
- **The sample JSON in `permissions.md` has diverged from the schema**: treat the schema as canonical and rewrite the `permissions.md` side to match.
- **`/org-setup` re-run does not eliminate drift in `settings.local.json`**: additive-only mode can't remove anything automatically. As a **last resort**, replace the role's `settings.local.json` wholesale with the per-role sample JSON in `.claude/skills/org-setup/references/permissions.md` to return to baseline. The `{worker_dir}` / `{claude_org_path}` placeholders in the worker sample must be hand-resolved to absolute paths in your environment. Make sure to record any local overrides before doing this. After updating, re-run `py -3 tools/check_role_configs.py --include-local` (POSIX: `python3 tools/check_role_configs.py --include-local`) to confirm the drift is gone.

### Schema JSON parse error / read failure

**Symptoms**: `check_role_configs.py` or `/org-setup` fails immediately when reading the schema (JSON syntax error, etc.).

**Diagnosis**:

```bash
git status tools/role_configs_schema.json
git diff tools/role_configs_schema.json
# Windows: prefer `py -3`; on POSIX use `python3`
py -3 -c "import json; json.load(open('tools/role_configs_schema.json'))"
```

**Fix**: if a recent edit broke the file, restore it with `git restore tools/role_configs_schema.json`, or temporarily set the change aside with `git stash push tools/role_configs_schema.json` and try again. After fixing the schema syntax, always run `py -3 tools/check_role_configs.py --include-local` (POSIX: `python3 tools/check_role_configs.py --include-local`) cleanly before committing.

---

## See the whole picture in the dashboard

Say "show me the dashboard" and the browser opens with a high-level view.

```
You:    Show me the dashboard
Lead:   (starts the live server and opens http://localhost:8099 in the browser)
```

The dashboard shows:

- **Project list** — registered projects with example tasks
- **Work status** — work items in progress, completed, or pending
- **Recent activity** — a timeline of what happened when
- **Accumulated knowledge** — what kinds of knowledge have been gathered, by topic

The dashboard auto-updates over SSE, so the latest state is reflected in real time without reloading the browser.

---

## Skill index

| Command | Purpose | When to use |
|---|---|---|
| `/org-start` | Boot the organization | **Run once, right after Claude Code starts** |
| `/org-delegate` | Assign work | Fires automatically when a request comes in (the Lead is a coordinator; real work goes to a Worker) |
| `/org-suspend` | Suspend work | Auto-fires on "we're done", "suspend", etc. |
| `/org-resume` | Resume work | Auto-called from `/org-start` when a previous suspend exists |
| `/org-retro` | Capture learnings | After work completes (mostly auto) |
| `/org-curate` | Curate knowledge | Auto-runs; manual is fine too |
| `/org-dashboard` | Show the dashboard | Fires on "show me the dashboard" |

You generally don't need to be aware of these — the Lead picks the right skill based on context.

---

## Directory layout

```
claude-org/
  CLAUDE.md              <- Lead's behavior guide
  .claude/skills/        <- Skill set (tracked)
  .state/                <- Session state (untracked)
  dashboard/             <- Dashboard (HTML/CSS/JS/server.py are tracked)
  knowledge/
    raw/                 <- Raw notes (untracked)
    curated/             <- Curated knowledge (tracked)
  registry/
    projects.md          <- Project list (auto-registered)
  docs/                  <- Documentation
```

### Things you might touch
- `knowledge/curated/` — review the curated knowledge (auto-generated)

### Things you don't need to touch
- `registry/projects.md` — auto-registered when work is requested
- `dashboard/` — dashboard design and data; auto-managed
- `.claude/skills/` — skill definitions; improved via auto proposals as the org evolves
- `.state/` — session state; auto-managed
- `CLAUDE.md` — change it if you want, but keep it thin

---

## How knowledge accumulates and the org grows

The organization gets smarter the more you use it.

1. Every time work completes, a learning is recorded
2. Curation runs automatically every 30 minutes (when 5+ entries have accumulated)
3. Curated knowledge is filed by topic
4. When a skill or process change would help, you'll see a proposal
5. If you approve, the improvement takes effect, and the whole org runs with it from then on

---

## Tips

- **Closing the terminal abruptly is OK**: state is saved periodically and is restored next launch. Saying "we're done for today" produces a more accurate save, though.
- **Too many tasks at once?** Just say "one at a time" — the Lead obeys human direction.
- **A learning misses the mark**: say "skip that learning" and it isn't recorded. Improvement proposals can also be rejected.
- **Project registration is automatic**: when you ask about a new project, the Lead confirms its name and location and registers it.
- **The dashboard is always available**: "show me the dashboard" or "show me the big picture" opens it in the browser.
