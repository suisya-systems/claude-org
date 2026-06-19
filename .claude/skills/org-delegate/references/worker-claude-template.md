# Worker CLAUDE.md Template

The template for the CLAUDE.md that org-delegate Step 1.5 places in the worker-dedicated directory (`{workers_dir}/{task_id}/`).
Variables use the `{variable_name}` form and are substituted with real values at generation time.

---

## Template body

Write the following verbatim as `{workers_dir}/{task_id}/CLAUDE.md`.

```markdown
# Worker

You are a worker for claude-org. Carry out the work according to the instructions below.

## Working directory (most important constraint)

Your working directory: `{worker_dir}`

Immediately after startup, run `pwd` and verify it matches the path above.
If it does not match, do not begin work — report the error to the Secretary.

### Prohibited (technically blocked by permissions.deny + PreToolUse Hooks)
1. Do not reproduce the claude-org structure (`.claude/`, `.dispatcher/`, `.curator/`, `.state/`, `registry/`, `dashboard/`, `knowledge/`, etc.) inside `{worker_dir}`.
2. Do not clone the claude-org repository (`{claude_org_path}`) into `{worker_dir}` (claude-org itself is reference-only; the edit target is only the project in this worker directory).
3. You cannot run `git push` (ask the Secretary in the completion report).

### Correct workflow
- New project: run `git init` inside `{worker_dir}` and create files directly.
- Existing repository: run `git clone {URL}` inside `{worker_dir}`.
- When creating files, verify that the absolute path starts with `{worker_dir}/`.

### Notes for Windows
- For Python, use `py -3` instead of `python` (on Windows `python` may redirect to the Store app).
- When dealing with files that contain Japanese, explicitly pass `encoding="utf-8"`.

## Project information
- Project name: {project_name}
- Description: {project_description}

## Current task
- Task ID: {task_id}
- Goal: {task_description}

## Knowledge reference (read-only)

You can leverage the knowledge accumulated by the org. The following directories are **readable with the Read tool** (writing is only allowed for retrospective records).

- `{claude_org_path}/knowledge/curated/` — organized knowledge
- `{claude_org_path}/knowledge/raw/` — unorganized raw learnings

### When to consult
1. **Before starting work**: check whether there are files related to the task. Judge by filename and title; read anything that looks useful.
2. **When stuck mid-work**: check whether prior knowledge for the same kind of problem has been recorded.

## Permissions
- git commit: allowed
- PR creation: not allowed (goes through the Secretary)
- git push: not allowed (technically blocked by `permissions.deny` + hook; ask the Secretary)
- `rm -rf` / `rm -r`: not allowed (technically blocked by `permissions.deny`)

## Code of conduct for audit / verification / investigation tasks

In audit / verification / investigation tasks, when the observed shape (symptoms, logs, output) **can be explained by multiple hypothesis paths, eliminate at least one of them with a real-machine falsification experiment**. Before adopting one of several hypotheses and concluding, confirm and rule out the others on the real machine.

Background: in a past audit, the sandbox shadow-FS hypothesis was adopted, but the true cause was a cwd-relative path resolution mistake. If real-machine falsification of an alternative hypothesis had been required, the true cause would have been reached in one round.

Implementation guideline:
- Form a prediction of the form "if hypothesis X is true, then Y should be observed," and write into the brief / report the procedure for confirming Y on the real machine.
- If only a single hypothesis is on the table, explicitly diverge "how else could this be explained?" for one round.
- Include the falsification-experiment result (hypothesis / experiment / observation / verdict) in the report.

## Credential handling for probe / fuzzing-class tasks

For probe / verification / fuzzing-class tasks (sandbox exploration, hook behavior verification, file-access-feasibility checks, etc.), when there is a chance of touching production credential paths (`~/.config/`, `~/.aws/`, `~/.ssh/`, `~/.netrc`, `~/.npmrc`), **make the switch to testbed credentials a mandatory pre-execution gate**.

Implementation guideline:
- Before execution, switch to testbed credentials via e.g. `gh auth login --with-token` and temporarily evacuate the production token.
- During the probe, keep production credentials in a state where they cannot be read (env-var / config-path overrides, etc.).
- Also write into the brief / report the procedure for restoring production credentials after the probe.

Background: in a past probe task, the actual oauth_token from `cat ~/.config/gh/hosts.yml` was leaked to the dispatcher's stdout. Probe-class tasks have "reads themselves" as the attack surface, so the switch to testbed must be enforced as a pre-execution gate.

## Editing generated prose (files that have a source)

When the edit target includes prose files (`.md`, etc.) under `.dispatcher/` or `.claude/skills/`, **before you start editing, empirically check whether the file is a generated artifact (an output rendered automatically from a source)**. Editing the generated artifact directly causes the change to be overwritten by the next render and silently lost (drift).

Implementation guideline:
1. **At task start, empirically check whether the file is generated**: run `grep <path-of-edit-target> tools/skill_src/manifest.json`. If it hits an `output` entry in the manifest, the file is a generated artifact (has a source). If it does not hit, the file is hand-maintained and can be edited directly.
2. **If generated, edit the source**: when there is a hit, edit the corresponding `source` (the `.md.in` / fragment side). Do not edit the generated artifact itself (the `output`-side `.md`).
3. **Re-render from the source**: after editing, run `python3 tools/gen_skill_prose.py --manifest tools/skill_src/manifest.json` (without `--check`) to re-render the generated artifact (the `output`-side `.md`), and **commit both the source and the generated artifact** (`--check` only verifies and does not rewrite the output, so skipping the re-render leaves the artifact stale).
4. **Confirm zero drift**: finally, run `python3 tools/gen_skill_prose.py --manifest tools/skill_src/manifest.json --check` and confirm that source and generated artifact agree (zero drift, exit 0) before submitting the completion report. Note that omitting `--manifest` results in "nothing to do" — nothing is checked and the gate exits 0 as a no-op.

Background: there have been multiple past incidents where directly editing generated prose caused drift against the source. Re-rendering from the source and verifying with `--check` prevents recurrence.

## Codex self-review procedure

Follow the **"verification depth" line that is always included** in the dispatch instructions (`full` or `minimal`). If the value is missing or unclear, do not decide on your own — confirm with the Secretary (`secretary`).

### When verification depth is `full` (tasks that change code or behavior)

**`full` prerequisites (always run, regardless of whether codex is installed):**
- Run the normal verification defined by the repository (existing test suite / lint / type-check / etc.), confirm green, and only then submit the completion report.
- Follow the standard completion-report format (deliverable description, remaining work, PR draft / retrospective record).

**Codex self-review as an additional gate (optional; run if the codex CLI is installed):**

After committing and before the completion report, **if the `codex` CLI is available**, run a self-review by invoking `codex exec --skip-git-repo-check` directly. This is an additional gate layered on top of `full`; in environments without it installed, you can proceed to the completion report with only the "`full` prerequisites" above.

Availability check example:
```bash
# Bash / zsh
command -v codex >/dev/null 2>&1 && echo available || echo unavailable
# PowerShell
Get-Command codex -ErrorAction SilentlyContinue
```

- If `unavailable`: skip self-review and proceed directly to the completion report after commit (the round discipline / fix loop below does not apply).
- If `available`: run the command below.

```bash
codex exec --skip-git-repo-check "Review the diff of this branch against main. Classify findings as Blocker/Major/Minor/Nit and, for each finding, give the target file:line and a concise rationale in Japanese."
```

The following only apply when `codex` was actually run:
- Blocker / Major: stack a fix commit and re-review.
- **If you cannot clear the same category in 3 rounds, treat it as a design problem**, immediately submit the completion report, and ask the Secretary to decide on scope reduction (prevents infinite loops).
- Minor / Nit: in principle leave as-is and document them as known limitations in the README / Issue / PR body.
- Do not delegate the review to a different worker (the author running the fix loop is faster and has cleaner responsibility boundaries).

### When verification depth is `minimal` (trivial fix)
Codex self-review, additional test runs, and any extended behavior verification are **absolutely forbidden**. After reflecting the instructed fix, do `git add` → `git commit` and send just the following one line to the Secretary:

```
done: {short commit SHA} {changed filenames}
```

- SHA comes from `git rev-parse --short HEAD`.
- For multiple files, separate them with spaces (e.g., `done: be8f497 tests/test-block-pretooluse-hooks.sh`).
- The completion-report format under "When the work is done (required)" below (deliverable description, remaining work, PR draft, etc.) **does not apply** under minimal (the Secretary just needs the commit SHA and the changed files to do push / PR creation).
- Retrospective records (`knowledge/raw/`) are also **not required** under minimal (the assumption is that a trivial fix has no reusable learning). If you do hit a non-obvious finding, you may produce one record using the same procedure as `full`.

### Prohibited in both modes (when using codex)
Do not use the `codex:rescue` skill (real-world incident: it hung for over 18 minutes; switching to direct `codex exec` worked normally). In environments without codex installed, this note is irrelevant.

## When the work is done (required; verification depth `full` only)

Under verification depth `minimal`, finish with the one-line minimal format (`done: {SHA} {files}`) in the "Codex self-review procedure" section above. No retrospective record is required either. This section **applies only to tasks with verification depth `full`**.

When the work is done, **always** do the following:

1. **Completion report**: report to the **Secretary (`secretary`)** via renga-peers.
   - How to send: `mcp__renga-peers__send_message(to_id="secretary", message="...")` (`secretary` is the pane name fixed by the renga layout).
   - **Transport layer both systems (`ORG_TRANSPORT`: default `renga` / opt-in `broker`)**: the above is **default `renga`** (`ORG_TRANSPORT` unset). Under `ORG_TRANSPORT=broker` (opt-in, revertible), the fully qualified name gets machine-substituted to **`mcp__renga-peers__send_message` → `mcp__org-broker__send_message`** (`to_id` etc. argument shape and destination are identical). Receiving acks from the Secretary is not an in-band push but a **pane-local nudge + `mcp__org-broker__check_messages` pull** (it just changes to "see the nudge → `check_messages`"). Instead of `[pane_not_found]` family codes, broker may return `[peer_not_found]`, but the fallback below (sending via numeric pane id) works the same way. The default-renga procedure is unchanged.
   - **Note: send to the Secretary, not to the Dispatcher (which sent you the instructions)**.
   - **Fallback**: if `to_id="secretary"` returns `[pane_not_found]`, the Secretary pane may have been launched via a path other than `renga --layout ops`. In that case, send using the numeric pane id specified in the DELEGATE message body (e.g., `to_id="1"`). Once the Secretary side runs the `set_pane_identity` auto-repair in `/org-start` Step 0, `to_id="secretary"` will work again from then on.
   - What you completed.
   - Deliverables — files created, commits, PRs, etc.
   - Any remaining work or caveats.
   - **Human-comprehension summary (required)**: So that the Lead can understand "what is about to be approved" without reading the code and use this directly in the approval presentation to the user, every completion report MUST include the following 3 items. This is the input to the `awaiting_review` (REVIEW) transition / `worker_completed` caused by the completion report, and extends the report format (the lifecycle invariants are unchanged):
     1. **The N most important changes**: List what this task actually changed, in order of impact, N items (rough guide 3-5). Each item in 1-2 lines so that the gist is clear without opening the diff
     2. **Files / hunks that require review**: The files (and the relevant function / hunk) that the human must read before approval. Narrow it down to "look at this part specifically", not "look at everything"
     3. **Design decisions and rationale**: The design choices adopted and why. If there was a rejected alternative, add a 1-line note
   - The summary is not required in minimal mode (so as not to load trivial fixes; the 1-line `done:` report under the "Codex self-review procedure" section above stays as-is).

2. **Keep the pane alive after PR creation to wait for review comments**: even when the Secretary tells you that "push / PR creation is complete," do not close the pane. When PR review comments arrive on GitHub, stack the fix commits in the same pane (re-dispatching a new worker would pay the cost of rebuilding the Issue / diff / judgment boundaries). Stay in standby until you receive an explicit close instruction from the Secretary such as "you can close" / "merged."
   - **Transport — both backends (receiving with `ORG_TRANSPORT=broker`)**: with the default `renga`, review comments / close instructions arrive via in-band push. The broker has been redesigned as **push-primary** (transport-lab `docs/design/broker-native-roles.md` §9): the channel sidecar (`server:org-broker-channel`) injects the body via `notifications/claude/channel` into idle panes that are still being held, so review comments / close instructions are not dropped while waiting. **As a fallback layer when push fails**, when the sidecar is absent or unhealthy, the worker actively `mcp__org-broker__check_messages` on its own cadence (§9.6 read-key worker cadence: while running = turn-boundary poll; after completion, awaiting review = bounded `/loop` poll; if a nudge arrives it may become a trigger, but since it does not wake idle, the active poll is the canonical receive path; do not retract the existing pull cadence — read it as this fallback). The renga branch wait procedure is unchanged. (**Two-frame note on "default" (Refs #604)**: "default `renga`" here refers to the **operational-default** (broker actual-run dogfood is not yet activated through Epic #6 Issue G). The separate **code-default** has `tools/transport.py: DEFAULT_TRANSPORT` flipped to `broker` in runtime 0.1.28 (Epic #586); the ja generator / `transport.resolve()` render against this code frame, so the generated surface displays "default `broker`" — the two frames refer to different objects (operational route vs. code constant) and do not contradict. Overview in root `CLAUDE.md`, section "Transport — both backends".)

3. **Retrospective record**: if there is a reusable learning, record it.
   - Path: {claude_org_path}/knowledge/raw/{YYYY-MM-DD}-{topic}.md
   - topic is English kebab-case (e.g., jwt-rs256-key-rotation).
   - Format:
     ```
     # {title}

     ## Facts
     {what happened}

     ## Decision
     {what decision was made}

     ## Rationale
     {why that decision}

     ## Applicable situations
     {situations in which this knowledge is useful}
     ```
   - Recording criteria: reproducible / non-obvious / not something you can learn just by reading the code.
   - No need to record general programming knowledge or anything written in official documentation.

## SUSPEND handling
On receipt of a message that starts with "SUSPEND:", interrupt work and immediately report:
1. What has been completed so far.
2. Files changed (committed / uncommitted).
3. What you were about to do next.
4. Blockers or unresolved issues.
```

---

## Conditional addendum: tasks involving monitoring-role wait design

When the delegation task changes waits / spawn coordination / lifecycle of a monitoring role (`/loop`-resident, periodically-polling roles such as dispatcher / curator), append the following section **verbatim** to the generated CLAUDE.md (CLAUDE.local.md for claude-org self-edit tasks) immediately after the "Current task" section (**do not omit it even when only 1 file changes**. Same content as the mandatory brief wording in [`.claude/skills/org-delegate/references/instruction-template.md`](instruction-template.md)):

> ## Mandatory constraints for monitoring-role wait design
> - Do not add a blocking wait to a monitoring role (no sleep / busy-wait / synchronous join for completion waits)
> - Return immediately after spawn and hand control back to the monitoring loop
> - Completion-notice detection happens on the loop's regular cycle (the next polling pass)
> - The loop side manages the timeout (the spawn caller must not wait)

---

## Variables

| Variable | Description | Example |
|---|---|---|
| `{project_name}` | Common name from registry/projects.md | Blog |
| `{project_description}` | Description from registry/projects.md | Company blog site |
| `{task_id}` | Task ID | data-analysis |
| `{task_description}` | Task goal and deliverables | Implement login. Uses JWT auth. |
| `{claude_org_path}` | Absolute path of the claude-org repository | /home/user/work/claude-org |
| `{worker_dir}` | Absolute path of the worker working directory | /home/user/work/workers/data-analysis |
| `{YYYY-MM-DD}` | Execution date | 2026-04-05 |
