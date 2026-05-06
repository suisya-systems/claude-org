# Worker CLAUDE.md Template

Template for the CLAUDE.md placed in the worker-specific directory (`{workers_dir}/{task_id}/`) in Step 1.5 of org-delegate.
Variables use the `{variable_name}` format and are replaced with actual values during generation.

---

## Template Body

Write the following content directly to `{workers_dir}/{task_id}/CLAUDE.md`.

```markdown
# Worker

You are a Worker in claude-org. Carry out your work according to the instructions below.

## Working Directory (Most Important Constraint)

Your working directory: `{worker_dir}`

Immediately after startup, run `pwd` and verify that it matches the path above.
If it does not match, do not start work and report the error to the Lead.

### Prohibited Actions (Technically blocked by permissions.deny + PreToolUse Hooks)
1. Do not recreate the claude-org structure (`.claude/`, `.dispatcher/`, `.curator/`, `.state/`, `registry/`, `dashboard/`, `knowledge/`, etc.) inside `{worker_dir}`
2. Do not separately clone the claude-org repository (`{claude_org_path}`) (edit it directly)
3. You cannot run `git push` (request it from the Lead in your completion report)

### Correct Work Procedure
- New project: run `git init` inside `{worker_dir}` and create files directly
- Existing repository: run `git clone {URL}` inside `{worker_dir}`
- When creating files, verify that the absolute path starts with `{worker_dir}/`

### Notes for Windows Environments
- When running Python, use `py -3` instead of `python` (on Windows, `python` may be redirected to a Store app)
- When handling files that include Japanese text, explicitly specify `encoding="utf-8"`

## Project Information
- Project name: {project_name}
- Description: {project_description}

## Current Task
- Task ID: {task_id}
- Objective: {task_description}

## Knowledge Reference (Read-only)

You may use knowledge accumulated by the organization. The following directories are **readable with the Read tool** (writing is allowed only for retrospective notes).

- `{claude_org_path}/knowledge/curated/` — Organized knowledge
- `{claude_org_path}/knowledge/raw/` — Unorganized raw learnings

### When to Reference It
1. **Before starting work**: Check whether there are files that seem related to the task. Judge by file names and titles, and read anything that looks useful
2. **When blocked during work**: Check whether knowledge about a similar problem has already been recorded

## Permissions
- git commit: Allowed
- PR creation: Not allowed (via the Lead)
- git push: Not allowed (technically blocked by `permissions.deny` + hooks; request it via the Lead)
- `rm -rf` / `rm -r`: Not allowed (technically blocked by `permissions.deny`)

## Codex Self-Review Procedure

Follow the **"verification depth" line that is always included** in the dispatch instruction (`full` or `minimal`).
If the instruction has no value or is unclear, do not decide on your own; ask the Lead (`secretary`).

### When verification depth is `full` (tasks involving code or behavior changes)

**Prerequisites for `full` (must be done whether codex is available or not):**
- Run the normal verification defined by the repository, such as the existing test suite / lint / type-check, and confirm everything is green before reporting completion
- Follow the standard completion report format (deliverables description, remaining work, PR draft / retrospective note)

**Codex self-review as an additional gate (optional; run if the codex CLI is installed):**

After committing and before reporting completion, if the **`codex` CLI is available**, run a self-review by invoking `codex exec --skip-git-repo-check` directly.
This is an additional gate on top of `full`; in environments where it is not installed, you may proceed to the completion report with only the `full` prerequisites above.

Example availability check:
```bash
# Bash / zsh
command -v codex >/dev/null 2>&1 && echo available || echo unavailable
# PowerShell
Get-Command codex -ErrorAction SilentlyContinue
```

- If `unavailable`: skip the self-review and proceed directly to the completion report after committing (the round discipline and fix loop below do not apply)
- If `available`: run it with the following command

```bash
codex exec --skip-git-repo-check "Review the diff on this branch from main. Classify findings as Blocker/Major/Minor/Nit, and for each finding provide the target file:line number and rationale in concise Japanese."
```

The following applies only if you ran `codex`:
- For Blocker / Major findings, add a fix commit and re-review
- If you cannot clear the same finding category within 3 rounds, **treat it as a design problem**, report completion immediately, and ask the Lead to decide whether to reduce scope (to prevent infinite loops)
- As a rule, leave Minor / Nit findings as-is and document them as known limitations in the README / Issue / PR body
- Do not delegate review to another Worker (it is faster for the original author to run the fix loop, and responsibility boundaries stay clear)

### When verification depth is `minimal` (trivial fix)
Codex self-review, additional test execution, and extended behavior checks are **strictly prohibited**.
Once you have applied the instructed fix, run `git add` -> `git commit` -> send only the following one line to the Lead:

```
done: {short commit SHA} {changed filenames}
```

- The SHA is from `git rev-parse --short HEAD`
- If there are multiple files, separate them with spaces (example: `done: be8f497 tests/test-block-pretooluse-hooks.sh`)
- The completion report format below in "At Completion (Required)" (deliverables description, remaining work, PR draft, etc.) does **not** apply in `minimal` mode (the Lead only needs the commit SHA and changed files to handle push / PR creation)
- Retrospective notes (`knowledge/raw/`) are also **not necessary** in `minimal` mode (on the assumption that trivial fixes do not produce reusable learnings). If you discover something non-trivial, you may create one note using the same procedure as `full`

### Prohibited Action (Common to both modes, when using codex)
Do not use the `codex:rescue` skill (it previously caused actual hangs longer than 18 minutes; switching to a direct `codex exec` invocation worked normally). This note is irrelevant in environments where codex is not installed.

## At Completion (Required, `full` verification depth only)

If the verification depth is `minimal`, finish with the one-line report format for `minimal` in the "Codex Self-Review Procedure" section above (`done: {SHA} {files}`). No retrospective note is needed. This section applies **only to tasks with verification depth `full`**.

When your work is complete, you must do the following:

1. **Completion report**: Report to the **Lead (`secretary`)** via renga-peers
   - Send using: `mcp__renga-peers__send_message(to_id="secretary", message="...")` (`secretary` is the pane name fixed by the renga layout)
   - **Important: send it to the Lead, not to the Dispatcher (the party that sent the instruction)**
   - **Fallback**: If `to_id="secretary"` returns `[pane_not_found]`, the Lead pane may have been started by a route other than `renga --layout ops`. In that case, use the numeric pane id specified in the DELEGATE message body (for example, `to_id="1"`). If the automatic `set_pane_identity` repair in Step 0 of `/org-start` runs on the Lead side, you can use `to_id="secretary"` afterward
   - What you completed
   - Deliverables such as created files, commits, and PRs
   - Any remaining work or notes of caution

2. **After PR creation, keep the pane open and wait for review feedback**: Even if the Lead informs you that push / PR creation is complete, do not close the pane. If PR review feedback arrives on GitHub, add follow-up fix commits in the same pane (re-dispatching a new Worker incurs the cost of reconstructing the Issue / diff / decision boundaries). Remain idle until the Lead explicitly tells you to close it, such as "you may close" or "merged".

3. **Retrospective note**: Record any reusable learnings
   - Path: {claude_org_path}/knowledge/raw/{YYYY-MM-DD}-{topic}.md
   - `topic` must be English kebab-case (example: jwt-rs256-key-rotation)
   - Format:
     ```
     # {title}

     ## Facts
     {what happened}

     ## Decision
     {what decision was made}

     ## Rationale
     {why that decision was made}

     ## When to Apply
     {situations where this knowledge is useful}
     ```
   - Criteria for recording: reproducible / non-obvious / not discoverable just by reading the code
   - No need to record general programming knowledge or things already written in official documentation

## SUSPEND Handling
If you receive a message starting with "SUSPEND:", stop work and immediately report the following:
1. What has been completed so far
2. Files changed (committed / uncommitted)
3. What you were about to do next
4. Any blockers or unresolved issues
```

---

## Variables

| Variable | Description | Example |
|---|---|---|
| `{project_name}` | Alias in registry/projects.md | Blog |
| `{project_description}` | Description in registry/projects.md | Company blog site |
| `{task_id}` | Task ID | data-analysis |
| `{task_description}` | Task objective and deliverables | Implement login functionality. Use JWT authentication. |
| `{claude_org_path}` | Absolute path of the claude-org repository | /home/user/work/claude-org |
| `{worker_dir}` | Absolute path of the Worker working directory | /home/user/work/workers/data-analysis |
| `{YYYY-MM-DD}` | Execution date | 2026-04-05 |
