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
- For Python, use either `py -3` or `python` (on Windows `python` may redirect to the Store app, and `py -3` may also point to a different Python environment depending on the py launcher configuration. Right after startup, verify the intended version with `--version` and use whichever one works).
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

## Rebase before the completion report (mandatory, `full` only; not needed for `minimal`)

**Scope**: this section applies to "`full` tasks that open a PR on top of `origin/main` (= this branch's PR base) in an existing repository". For the `git init` new project in "Correct work procedure" above, or repositories with no `origin` remote / whose PR base is other than `origin/main` (`origin/develop`, etc.), read `origin/main` as **that branch's actual base upstream**. If the upstream remote itself does not exist (`git remote` is empty), this rebase gate itself does not apply (skip it and proceed to the next Codex self-review). The following is the procedure for the default case (base = `origin/main`):

Before the completion report (and the Codex self-review below), always run the following (excessive for a `minimal`-depth trivial fix, so not applicable there):

1. `git fetch origin` (`git fetch origin main` only fetches into `FETCH_HEAD` and does not reliably update the `origin/main` tracking ref, which can misjudge behind=0 against a stale `origin/main`. If the remote name / base differs, fetch the relevant upstream).
2. `git rebase origin/main` (if the branch policy is merge-based, `git merge origin/main`; the default is rebase. If the base differs, read it as the relevant upstream).
3. If there are conflicts, the worker resolves them (the result of other parallel PRs touching the same integration point = registry / CLI --source routing / `pyproject.toml` extras・markers / README / docs). During conflict resolution, confirm that the local tests (`pytest` / `make demo` / `make test-local` or whatever verification the repository defines) continue to stay green.
4. After the rebase, confirm the branch is a descendant of `origin/main` (= the base upstream) and clean (behind=0): `git rev-list --count HEAD..origin/main` is `0`.
5. Include the one line "rebase clean: HEAD=`<sha>` on top of origin/main `<sha>`" in the completion report.

Background (Refs: 2026-07-08 kura conveyor PR #46/#47 conflict fest): under parallel dispatch, when multiple workers edit the same integration point (`source/__init__.py` registry / CLI `--source` routing / `pyproject.toml` extras・markers / README / docs) from the main at dispatch time, whoever merges first wins and the survivor becomes CONFLICTING on GitHub and does not even start CI. By finishing rebase → conflict resolution → clean push at the worker stage, you avoid the Lead-side rebase cost (a semantic merge cannot be resolved without the worker's context and becomes double work) and the delay from CI not starting.

## Codex self-review procedure

Follow the **"verification depth" line that is always included** in the dispatch instructions (`full` or `minimal`). If the value is missing or unclear, do not decide on your own — confirm with the Secretary (`secretary`).

### When verification depth is `full` (tasks that change code or behavior)

**`full` prerequisites (always run, regardless of whether codex is installed):**
- Run the normal verification defined by the repository (existing test suite / lint / type-check / etc.), confirm green, and only then submit the completion report.
- Follow the standard completion-report format (deliverable description, remaining work, PR draft / retrospective record).

**Codex self-review as an additional gate (optional; run if the codex CLI is installed):**

After committing and before the completion report, **if the `codex` CLI is available**, run a self-review with `codex exec review` (review surface) (the long-prompt direct `codex exec` form is deprecated; on small/medium diffs the review surface is roughly 2x faster and at parity for safety-critical Blocker/Major findings). This is an additional gate layered on top of `full`; in environments without it installed, you can proceed to the completion report with only the "`full` prerequisites" above.

Availability check example:
```bash
# Bash / zsh
command -v codex >/dev/null 2>&1 && echo available || echo unavailable
# PowerShell
Get-Command codex -ErrorAction SilentlyContinue
```

- If `unavailable`: skip self-review and proceed directly to the completion report after commit (the round discipline / fix loop below does not apply).
- If `available`: run the command below in the **foreground** (pass the branch's base, normally `origin/main`, to `--base`. Use the **remote-tracking `origin/main` rather than the local `main`** because a stale local `main` in a shared clone drags another task's diff into the review. Run `git fetch origin` once before referencing it (even if you pulled at the start, refresh it right before the review; if the fetch fails, the review still continues). Close stdin explicitly with `< /dev/null`. Avoid background `&` + log redirect because it leads to reporting completion without waiting for or reading the findings, slipping past the gate).

```bash
codex exec review --base origin/main -m gpt-5.5 -c model_reasoning_effort=medium < /dev/null
```

- The review surface returns Blocker/Major-equivalent findings (P1/P2 etc.) from the built-in review prompt. **Read the output in the foreground before moving on** (you may interrupt and skip only in the rare case the response does not come back). **Do not raise the effort on a large diff (rule of thumb: over 100 lines)** (a high-effort review does not scale on large diffs and has been measured to be slower than the direct form).
- The review surface protects the dangerous-side Major findings (the false-positives that would let the gate pass incorrectly) but can miss benign safe-side Major findings (false negatives in the over-polling direction) and ReDoS-class side bugs. For changes close to design that need deep inspection, consult the Lead about pairing with a design review. For the SoT with measured rationale see [`knowledge/curated/codex.md`](../../../../knowledge/curated/codex.md).

**When the safety mechanism prevents the review from proceeding (`available` but safety block)**: the diff content (a security-verification task, etc.) can trip the model's safety classifier so that the `codex exec review` processing itself cannot complete. **This skip differs in meaning from the "`unavailable` skip" above** — codex is available, yet the gate is **not established**; it is not "codex clean". Do **not** paraphrase or alter the prompt to evade the safety mechanism (the principle is that processing caught by a model safety mechanism is skipped and reported, not evaded). The official recovery is:
- **Official recovery = a fresh session (continuation spawn)**: in the same worktree and on the same branch, start a new worker session that inherits the commits already stacked, and re-run `codex exec review` in that clean context (ask the Lead to restart the session). State the inherited **HEAD SHA** in the completion report so that it is traceable which commit the review was established against
- **If recovery is impossible**: if the review still does not pass even with the above, do **not** report "codex clean". Submit the completion report explicitly stating "Codex gate not established (review incomplete due to safety block, HEAD=`<sha>`)" and ask for the Lead's judgment. Never misrepresent an unestablished gate as clean (do not equate the safety block with the "codex not installed" skip and let it slip through)

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
Do not use the `codex:rescue` skill (real-world incident: it hung for over 18 minutes; the direct `codex exec review` / `codex exec` forms work normally). The `gpt-5.5-codex` model and the API-key surface cannot run on a ChatGPT account (explicitly pass `-m gpt-5.5`). In environments without codex installed, this note is irrelevant.

## When the work is done (required; verification depth `full` only)

Under verification depth `minimal`, finish with the one-line minimal format (`done: {SHA} {files}`) in the "Codex self-review procedure" section above. No retrospective record is required either. This section **applies only to tasks with verification depth `full`**.

When the work is done, **always** do the following:

1. **Completion report**: report to the **Secretary (`secretary`)** via renga-peers.
   - How to send: `mcp__renga-peers__send_message(to_id="secretary", message="...")` (`secretary` is the pane name fixed by the renga layout).
   - **Transport layer both systems (`ORG_TRANSPORT`: default `renga` / opt-in `broker`)**: the above is **default `renga`** (`ORG_TRANSPORT` unset). Under `ORG_TRANSPORT=broker` (opt-in, revertible), the fully qualified name gets machine-substituted to **`mcp__renga-peers__send_message` → `mcp__org-broker__send_message`** (`to_id` etc. argument shape and destination are identical). Receiving acks etc. from the Secretary has been **redesigned to push-primary** (runtime push-first 0.1.24+, transport-lab `docs/design/broker-native-roles.md` §9) = the per-pane channel sidecar (`server:org-broker-channel`) injects the body into the idle session via `notifications/claude/channel`. **Pull is the fallback layer**: only when the sidecar is absent / unhealthy / channel-incapable is it **pane-local nudge + `mcp__org-broker__check_messages` pull** (the existing pull prose is not retracted and is read as fallback cadence — §9.6). Instead of `[pane_not_found]` family codes, broker may return `[peer_not_found]`, but the fallback below (sending via numeric pane id) works the same way. The default-renga procedure is unchanged.
   - **Note: send to the Secretary, not to the Dispatcher (which sent you the instructions)**.
   - **Fallback**: if `to_id="secretary"` returns `[pane_not_found]`, the Secretary pane may have been launched via a path other than `renga --layout ops`. In that case, send using the numeric pane id specified in the DELEGATE message body (e.g., `to_id="1"`). Once the Secretary side runs the `set_pane_identity` auto-repair in `/org-start` Step 0, `to_id="secretary"` will work again from then on.
   - What you completed.
   - Deliverables — files created, commits, PRs, etc.
   - **rebase clean confirmation (mandatory)**: the one line "rebase clean: HEAD=`<sha>` on top of origin/main `<sha>`" confirmed in "Rebase before the completion report" above (i.e., that it is `behind=0`).
   - Any remaining work or caveats.

2. **Keep the pane alive after PR creation to wait for review comments**: even when the Secretary tells you that "push / PR creation is complete," do not close the pane. When PR review comments arrive on GitHub, stack the fix commits in the same pane (re-dispatching a new worker would pay the cost of rebuilding the Issue / diff / judgment boundaries). Stay in standby until you receive an explicit close instruction from the Secretary such as "you can close" / "merged."
   - **Transport layer both systems (receive under `ORG_TRANSPORT=broker`)**: under default `renga`, review comments / close instructions arrive as in-band push. Broker has been **redesigned to push-primary** (transport-lab `docs/design/broker-native-roles.md` §9), and even into a held idle pane the channel sidecar (`server:org-broker-channel`) injects the body via `notifications/claude/channel`, so comments / close instructions are not missed even while in standby. **As a push-failure fallback layer**, when the sidecar is absent / unhealthy the worker actively `mcp__org-broker__check_messages` at its own cadence (the §9.6 reading-substitution table worker cadence: during execution = turn-boundary poll / post-completion review wait = bounded `/loop` poll. A nudge can be a trigger, but it does not wake an idle session, so an active poll is the canonical reception path. The existing pull cadence is not retracted and is read as this fallback). The renga-branch standby procedure is unchanged.

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
