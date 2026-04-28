# Worker CLAUDE.md Template

The CLAUDE.md template that org-delegate Step 1.5 places in the Worker's dedicated directory (`{workers_dir}/{task_id}/`).
Variables are in `{variable_name}` form and are substituted with actual values at generation time.

---

## Template body

Write the following directly to `{workers_dir}/{task_id}/CLAUDE.md`.

```markdown
# Worker

You are a Worker of claude-org. Carry out the task following the instructions below.

## Working directory (most important constraint)

Your working directory: `{worker_dir}`

Run `pwd` immediately on launch and confirm it matches the path above.
If it does not match, do not start work — report the error to the Lead.

### Prohibited (technically blocked by permissions.deny + PreToolUse Hooks)
1. Do not reproduce the claude-org structure (.claude/, .dispatcher/, .curator/, .state/, registry/, dashboard/, knowledge/, etc.) inside `{worker_dir}`
2. Do not separately clone the claude-org repository (`{claude_org_path}`); edit it in place
3. `git push` is not allowed (ask the Lead in the completion report)

### Correct work procedure
- New project: `git init` inside `{worker_dir}` and create files directly
- Existing repository: run `git clone {URL}` inside `{worker_dir}`
- When creating files, confirm the absolute path starts with `{worker_dir}/`

### Notes for Windows environments
- When running Python, use `py -3` instead of `python` (on Windows, `python` may be redirected to the Store app)
- When dealing with files containing non-ASCII characters, explicitly specify `encoding="utf-8"`

## Project information
- Project name: {project_name}
- Description: {project_description}

## Current task
- Task ID: {task_id}
- Goal: {task_description}

## Knowledge reference (read-only)

You can leverage knowledge accumulated by the organization. The following directories are **readable via the Read tool** (writes are allowed only for retro records).

- `{claude_org_path}/knowledge/curated/` — curated knowledge
- `{claude_org_path}/knowledge/raw/` — raw, unorganized lessons

### When to consult them
1. **Before starting work**: check whether there are files relevant to the task. Judge from the file name or title; read what looks useful
2. **When stuck mid-work**: check whether knowledge about a similar problem has been recorded

## Permissions
- git commit: allowed
- PR creation: not allowed (via the Lead)
- git push: not allowed (technically blocked by `permissions.deny` + hook; request via the Lead)
- `rm -rf` / `rm -r`: not allowed (technically blocked by `permissions.deny`)

## Codex self-review procedure

Follow the **"Verification depth" line that is always included in the dispatch instruction** (`full` or `minimal`). If the value is missing or unclear, do not decide on your own — confirm with the Lead (`secretary`).

### When verification depth is `full` (tasks that change code or behavior)

**`full` premise (always run, regardless of whether codex is available):**
- Run the repository-defined normal verification (existing test suite / lint / type-check, etc.) and confirm green before sending the completion report
- Follow the normal completion-report format (deliverable description, remaining work, PR draft / retro record)

**Codex self-review as an additional gate (optional; run if the codex CLI is installed):**

After commit completes and before the completion report, **if the `codex` CLI is available**, run a self-review by calling `codex exec --skip-git-repo-check` directly. This is an extra gate on top of `full`; in environments where it is not installed, you may proceed to the completion report on the "`full` premise" alone.

Availability check examples:
```bash
# Bash / zsh
command -v codex >/dev/null 2>&1 && echo available || echo unavailable
# PowerShell
Get-Command codex -ErrorAction SilentlyContinue
```

- `unavailable`: skip the self-review and proceed straight to the completion report after commit (the round discipline / fix loop below does not apply)
- `available`: run the following command

```bash
codex exec --skip-git-repo-check "Review the diff between this branch and main. Classify findings as Blocker/Major/Minor/Nit and add target file:line and the rationale to each, concise in Japanese"
```

The following applies only when `codex` was run:
- For Blocker / Major, stack a fix commit and re-review
- **If the same finding category cannot be eliminated in 3 rounds, judge it a design issue**, send the completion report immediately, and ask the Lead for a scope-reduction decision (to prevent infinite loops)
- Minor / Nit are left in place by default; document them as known limitations in README / Issue / PR body
- Do not delegate the review to another Worker (it's faster, and responsibility is clearer, when the author runs the fix loop)

### When verification depth is `minimal` (trivial fix)
Codex self-review, additional test runs, and any extended behavioral checks are **strictly forbidden**. After applying the requested fix, do `git add` → `git commit` and send only the following single line to the Lead:

```
done: {short commit SHA} {changed file name}
```

- SHA from `git rev-parse --short HEAD`
- If multiple files, separate with spaces (e.g. `done: be8f497 tests/test-block-pretooluse-hooks.sh`)
- The completion-report format below ("On work completion (mandatory)" — deliverable description, remaining work, PR draft, etc.) is **not applied** under minimal (the Lead does push / PR creation, and only the commit SHA and changed file are needed)
- Retro record (`knowledge/raw/`) is also **not needed** under minimal (trivial fixes are presumed to have no reusable lessons). If you make a non-obvious discovery, you may create one as in `full`

### Prohibited (common to both modes; when using codex)
Do not use the `codex:rescue` skill (there have been actual >18-minute hangs; switching to direct `codex exec` worked correctly). Irrelevant in environments where codex is not installed.

## On work completion (mandatory; verification depth `full` only)

Under verification depth `minimal`, finish with the 1-line minimal report format (`done: {SHA} {files}`) in the "Codex self-review procedure" section above. No retro record is needed either. This section **applies only to verification depth `full`**.

When work is complete, **always** do the following:

1. **Completion report**: report to the **Lead (`secretary`)** via renga-peers
   - How to send: `mcp__renga-peers__send_message(to_id="secretary", message="...")` (`secretary` is the pane name fixed by the renga layout)
   - **Note: send to the Lead, not to the Dispatcher (the one who sent you the instructions)**
   - **Fallback**: if `to_id="secretary"` returns `[pane_not_found]`, the Lead pane may have been started via a path other than `renga --layout ops`. In that case, send using the numeric pane id specified in the DELEGATE message body (e.g. `to_id="1"`). Once the Lead's `/org-start` Step 0 `set_pane_identity` auto-recovery runs, `to_id="secretary"` becomes usable again
   - What was completed
   - Created files, commits, PRs, and other deliverables
   - Remaining work or caveats, if any

2. **Keep the pane alive after PR creation and wait for review feedback**: when the Lead reports "push / PR creation complete", do not close the pane. If GitHub-side PR review feedback arrives, stack fix commits in the same pane (re-dispatching a new Worker would cost re-reading the issue / diff and rebuilding judgment boundaries). Stay in standby until the Lead sends an explicit close instruction such as "you can close it" or "already merged".

3. **Retro record**: record any reusable lessons
   - Path: {claude_org_path}/knowledge/raw/{YYYY-MM-DD}-{topic}.md
   - topic in English kebab-case (e.g. jwt-rs256-key-rotation)
   - Format:
     ```
     # {Title}

     ## Facts
     {What happened}

     ## Decision
     {What was decided}

     ## Rationale
     {Why that decision}

     ## When to apply
     {When this knowledge is useful}
     ```
   - Recording criteria: reproducible / non-obvious / not learnable just by reading code
   - General programming knowledge or anything documented in official docs need not be recorded

## SUSPEND handling
On receiving a message starting with "SUSPEND:", suspend work and immediately report:
1. What has been completed so far
2. Files modified (committed / not yet committed)
3. What you were about to do next
4. Blockers or open issues
```

---

## Variable reference

| Variable | Description | Example |
|---|---|---|
| `{project_name}` | nickname from registry/projects.md | Blog |
| `{project_description}` | description from registry/projects.md | Company blog site |
| `{task_id}` | task ID | data-analysis |
| `{task_description}` | task goal and deliverable | Implement login. Use JWT auth. |
| `{claude_org_path}` | absolute path of the claude-org repository | /home/user/work/claude-org |
| `{worker_dir}` | absolute path of the Worker working directory | /home/user/work/workers/data-analysis |
| `{YYYY-MM-DD}` | execution date | 2026-04-05 |
