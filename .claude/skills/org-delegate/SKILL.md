---
name: org-delegate
description: >
  Dispatch a Worker Claude and delegate work. The Lead is the command center;
  hands-on work is, in principle, dispatched to a Worker.
  Triggered when the user asks for hands-on work such as file edits,
  implementation, or investigation.
---

# org-delegate: Worker dispatch

Delegate work to a Worker Claude. The Lead only does task decomposition and
preparation; pane spawning and instruction sending are entrusted to the
Dispatcher. This minimizes the time the Lead is locked.

## Lead vs. Dispatcher responsibilities

| Stage | Owner |
|---|---|
| Project name resolution | **Lead** |
| work-skill search | **Lead** (newly added) |
| Task decomposition | **Lead** |
| CLAUDE.md generation | **Lead** |
| Request to Dispatcher | **Lead** (Lead is released here) |
| Pane spawning | **Dispatcher** |
| Wait for peer / send instructions | **Dispatcher** |
| Record state | **Dispatcher** |
| Report dispatch completion to Lead | **Dispatcher** |
| Receive progress / completion reports from Workers | **Lead** |
| Close pane on Worker completion | **Dispatcher** (requested by Lead) |

## Pre-dispatch checklist (Lead executes)

Before entering task decomposition, examine the request from the perspectives below. If any apply, ask the user back.

| Check item | Situation to confirm | Example |
|---|---|---|
| **Ambiguous terms / abbreviations** | Tool / service names / abbreviations that may have multiple meanings | "gog" → Google OAuth? gog CLI? |
| **OS-specific prerequisites** | When producing OS-specific deliverables, default settings must be made explicit | Mac=zsh, Windows=py -3, path separators |

- For ambiguous terms: confirm with the user ("Did you mean ○○ by △△?") before proceeding
- For OS-specific tasks: include OS-specific prerequisites in the Worker instruction during Step 1 task decomposition

## Step 0: Project name resolution (Lead executes)

Identify the project from the user's request:

1. Read `registry/projects.md`
2. From the keywords in the request, identify the matching project (match by nickname, project name, or description)
3. If identified, use that path
4. If not identified, present the list of registered project nicknames and have the user choose
5. For a new project:
   - Confirm the path with the user
   - Estimate the nickname / description / typical tasks, confirm with the user, and append to `registry/projects.md`

## Step 0.5: work-skill search (Lead executes) (newly added)

Before task decomposition, search for any existing related work-skill.
Include any matched work-skill in the Worker instruction as reference.

### Search procedure

1. Enumerate all SKILL.md files under `.claude/skills/`
2. Read the frontmatter of each SKILL.md:
   - Identify work-skills via the `type` field (those without the `org-` prefix)
   - Match `description` and `triggers` against the task content
3. Matching judgment:
   - Compare the keywords of the user's request with `description`
   - Check whether `triggers` lists wording that matches the request
   - An exact match is not required; if there is relevance, include it as a candidate

### Using the match results

**On match:**
- Notify the human:
  ```
  Related work-skill(s) found:
  - {skill-name}: {first line of description}
  Will include them in the Worker instruction as reference.
  ```
- Refer to the work-skill's procedure during Step 1 task decomposition
- During Step 1.5 CLAUDE.md generation, add the following section:
  ```markdown
  ## Reference work-skill
  The following work-skill(s) may be useful. Refer to its procedure and judgment criteria.
  Adjust as appropriate where it does not fit this task's requirements.

  - Skill name: {skill-name}
  - Path: .claude/skills/{skill-name}/SKILL.md
  - Summary: {description}
  ```
- Also note the existence of the reference skill in the Worker instruction (instruction-template)

**On no match:**
- No notification needed. Proceed to Step 1.

### Search caveats

- Do not copy the work-skill's procedure verbatim. Present it as reference and let the Worker decide
- If multiple match, include all of them in order of relevance
- Skills with the `org-` prefix (org-retro, org-delegate, etc.) are organization-management skills and are excluded from the search

## Step 1: Task decomposition (Lead executes)

Analyze the human's request and define tasks to delegate to Workers:

- Assign each task a unique ID (English kebab-case, easy to associate with the request. e.g. `data-analysis`, `login-fix`, `dashboard-redesign`)
  - Check `.state/org-state.md` to avoid collisions with existing IDs (on collision, suffix to disambiguate: `login-fix-2`)
- For each task, make the following clear:
  - Goal (what to achieve)
  - Deliverable (what will be produced)
  - Working directory (which project to work in)
  - Constraints (branch name, coding conventions, dependencies, etc.)
  - **Verification depth (`full` / `minimal`)** — the dispatch instruction must always state exactly one of the two values. The default is `full` (any task that changes code or behavior). Under `full`, **regardless of whether codex is available**, the repository's normal verification (tests / lint / type-check, etc.) must be run to green and reported in the normal completion-report format; this is a required gate. As an **additional (optional) gate**, if the codex CLI is available, the rule "Codex self-review with a 3-round cap on identical findings" runs after commit completes (skipped if codex is not installed). Choose `minimal` only for trivial fixes (CI output formatting / typo / comment edits / matching to existing test format), in which case the Worker only does `git add` → `git commit` → `done` report. See the "Verification depth" section in `references/instruction-template.md` and the "Codex self-review procedure" section in `references/worker-claude-template.md` for details. The Lead is responsible for picking the value; the Worker does not decide.
  - **Directory pattern (A / B / C)** — determined by the criteria below
  - **Reference work-skill** (if matched in Step 0.5)
- Note: when the task description includes file paths, make explicit that they are relative to the Worker's working directory. Do not give the value of the "Path" column in registry/projects.md as a deliverable path directly (it will cause the Worker to create paths in unintended locations).

### Pre-check: is the target file gitignored?

Before entering the decision flow, check whether the file to be edited is excluded by `.gitignore`.
**The "target file" is what the Lead extracts from the task description** (paths explicitly mentioned in the request, the issue body, or the user's utterance; do not infer mechanically). Skip this check for tasks where the target file cannot be identified (pure investigation, new creation with an undecided target path, etc.) and proceed to normal judgment.

#### Applicability

This check is run **only for projects where a git repo already exists locally**. Specifically:

- Run only when the "Path" in registry/projects.md is a local absolute path that resolves to a directory (or worktree) with `.git/`
- If the path is a URL (not yet cloned) / `-` / unresolvable, **skip the check itself** and go to normal judgment (the rare case of a tracked existing file becoming gitignored after first clone is caught separately by review)

#### Decision command

At the local repo root (= the absolute path the "Path" points to):

```
git -C {project_path} check-ignore -q -- <target>
```

- Exit code 1 (= not ignored) → tracked or "merely a non-existent new file". **Proceed to normal A / B / C judgment**
- Exit code 0 (= ignored) → **Pattern C forced (gitignored submode)**. See below
- Exit code 128 etc. (command failure, repo not initialized, etc.) → out of applicability. Skip and go to normal judgment

> `git check-ignore` only judges "does it match the current `.gitignore` rules"; it can be evaluated even if the file does not exist. Using `ls-files --error-unmatch` would treat "merely a not-yet-created new file" as untracked and drop it into Pattern C, so do not use that.

#### Pattern C forced (gitignored submode)

Normal Pattern C uses an ephemeral empty directory at `{workers_dir}/{task_id}/`, but that doesn't reach the target file when editing a gitignored target. Special operation:

- **WORKER_DIR**: directly point at the **repo root of the existing local clone** (the "Path" value from the registry as-is)
- **Where to place CLAUDE.md / settings.local.json**: directly under that repo root. If a CLAUDE.md is already there for another purpose, write to `CLAUDE.local.md` instead (see the special case in `references/claude-org-self-edit.md`)
- **Worker Directory Registry**: register Pattern as `C`, Directory as the absolute path of the repo root, Status as `in_use`. On completion, delete the entry (the directory itself is the original project, so it is preserved)
- **Concurrency**: because we grab the repo root directly, do not start it concurrently with Pattern A / B Workers operating on the same repo (the Lead serializes them)
- **Lead memo**: leave a one-liner like "Pattern B unavailable: target `<target>` is gitignored. Operating with WORKER_DIR = existing repo root"

#### Relation to claude-org self-edit

Normal skill / doc edits (`.claude/skills/...`, `references/...`) are tracked and can use Pattern B as before. Only when editing internal memos under `docs/internal/`, `notes/`, `tmp/`, etc. that are gitignored does this pre-check force Pattern C (gitignored submode). See `references/claude-org-self-edit.md`.

### Directory pattern criteria

| Pattern | Name | Condition | Directory |
|---|---|---|---|
| A | Project directory | A clone of the project is needed (clone first time, reuse afterward) | `{workers_dir}/{project_slug}/` |
| B | worktree | Parallel work on the same project is needed (another Worker is already using the same project directory) | `{workers_dir}/{project_slug}/.worktrees/{task_id}/` |
| C | Ephemeral | Temporary work where the deliverable does not need to be kept (investigation, verification, etc.) | `{workers_dir}/{task_id}/` |

**Decision flow:**

0. **Pre-check (only when the target file is identified and a local repo exists)**: run "Pre-check: is the target file gitignored?" above. If not ignored, proceed to step 1 below. If ignored, settle on **Pattern C forced (gitignored submode)** and skip the rest. If outside applicability (URL only, target unidentified, etc.), skip the check and go to normal judgment from step 1
1. When a project clone is needed (the project has a registered path in registry/projects.md):
   a. If there is an `in_use` entry for the same project in the Worker Directory Registry → **Pattern B** (parallel work via worktree)
   b. If there is an `available` entry for the same project → **Pattern A** (reuse the existing directory)
   c. If there is no entry → **Pattern A** (new clone)
2. Otherwise → **Pattern C**
   - Temporary work that doesn't need a clone, investigation tasks where no deliverable is needed, etc.

## Step 1.5: Prepare the Worker directory (Lead executes)

Prepare a dedicated directory for each task and place CLAUDE.md and settings.
Use the template references/worker-claude-template.md.
**The procedure differs by pattern (A/B/C).**

> **For tasks that edit claude-org itself**: in addition to the normal procedure, always apply the special procedure in `references/claude-org-self-edit.md` (excluding the block-org-structure.sh hook, writing instructions to CLAUDE.local.md, and explicitly noting that the root CLAUDE.md should be ignored). **In this section and below, wherever it says "generate / place / verify CLAUDE.md", read it as `CLAUDE.local.md`** (the root CLAUDE.md is for the Lead, so do not overwrite it).

### Common procedure (all patterns)

1. Read `workers_dir` from `registry/org-config.md` and resolve it from a path relative to the repository root to an absolute path

### Choosing the worker role (`<ROLE>`)

`.claude/settings.local.json` is generated by the schema-driven generator (`tools/generate_worker_settings.py`). The Lead **only picks one role per task characteristics**; hand-editing permissions is forbidden (schema → settings drift fails CI).

| Role | Use |
|---|---|
| `default` | Normal implementation / fix tasks (git commit / branch operations allowed; no push, no recursive delete) |
| `claude-org-self-edit` | Tasks that edit the claude-org repo itself (`tools/`, `.claude/skills/`, `docs/`, etc.). Drops `block-org-structure.sh` and relies on `check-worker-boundary.sh` for the boundary |
| `doc-audit` | Read-centric investigation / audit / reporting (Edit/Write/MultiEdit/NotebookEdit denied; commit / branch also forbidden) |

For each role's concrete allow/deny/hooks, see `tools/role_configs_schema.json` `worker_roles[<role>]` (the schema is the SOT). If a new pattern is needed, open a PR that adds a role to the schema (the Lead must not hand-extend).

### Pattern A: project directory

Use a project-dedicated directory (`{workers_dir}/{project_slug}/`). Clone the first time, reuse afterward.

**First time (directory does not exist):**

1. Run `git clone {project_path} {workers_dir}/{project_slug}/`
2. Generate CLAUDE.md directly under the directory (substituting template variables)
3. Generate `.claude/settings.local.json` directly under the directory **with the generator** (the schema is the SOT; see `worker_roles` in `tools/role_configs_schema.json`):
   ```bash
   python tools/generate_worker_settings.py \
     --role <ROLE> \
     --worker-dir {worker_dir} \
     --claude-org-path {claude_org_path} \
     --out {worker_dir}/.claude/settings.local.json
   ```
   For how to pick `<ROLE>`, see the "Choosing the worker role (`<ROLE>`)" table at the top of this Step. Hand-written JSON is forbidden (drift CI fails).
4. Register an entry in the Worker Directory Registry of `.state/org-state.md`

**Reuse (directory exists and status is `available`):**

1. Update with `git -C {workers_dir}/{project_slug}/ fetch origin`
2. Regenerate **only** CLAUDE.md (overwrite with the new task ID and task description)
   - Reuse settings.local.json as-is (no regeneration needed because `{worker_dir}` does not change)
3. Update the Worker Directory Registry of `.state/org-state.md` (associate the new task ID, set status to `in_use`)

### Pattern B: worktree

When parallel work on the same project is needed, use the project directory as a base clone and create a worktree.

1. Confirm the existence of the base clone (`{workers_dir}/{project_slug}/`):
   - If it doesn't exist → run `git clone {project_path} {workers_dir}/{project_slug}/`
   - If it already exists → update with `git -C {workers_dir}/{project_slug}/ fetch origin`
2. Create the worktree:
   - Run `git -C {workers_dir}/{project_slug}/ worktree add .worktrees/{task_id} -b {branch_name}`
   - `{branch_name}` is the branch name decided in Step 1 (if unspecified, use `{task_id}` as the branch name)
   - Worker directory: `{workers_dir}/{project_slug}/.worktrees/{task_id}/`
3. Generate CLAUDE.md directly under the worktree (substituting template variables)
4. Generate `.claude/settings.local.json` directly under the worktree **with the generator** (schema-driven; see `worker_roles` in `tools/role_configs_schema.json`):
   ```bash
   python tools/generate_worker_settings.py \
     --role <ROLE> \
     --worker-dir {worker_dir} \
     --claude-org-path {claude_org_path} \
     --out {worker_dir}/.claude/settings.local.json
   ```
   For how to pick `<ROLE>`, see the "Choosing the worker role (`<ROLE>`)" table at the top of this Step. Hand-written JSON is forbidden.
5. Register an entry in the Worker Directory Registry of `.state/org-state.md`

### Pattern C: ephemeral

Use for temporary work where the deliverable does not need to be kept (investigation, verification, etc.).

1. Create the directory `{workers_dir}/{task_id}/` (e.g. `../workers/data-analysis/`)
2. Generate `{workers_dir}/{task_id}/CLAUDE.md` from the template
3. Generate `{workers_dir}/{task_id}/.claude/settings.local.json` **with the generator** (schema-driven; see `worker_roles` in `tools/role_configs_schema.json`):
   ```bash
   python tools/generate_worker_settings.py \
     --role <ROLE> \
     --worker-dir {worker_dir} \
     --claude-org-path {claude_org_path} \
     --out {worker_dir}/.claude/settings.local.json
   ```
   For how to pick `<ROLE>`, see the "Choosing the worker role (`<ROLE>`)" table at the top of this Step. Hand-written JSON is forbidden.
4. Register an entry in the Worker Directory Registry of `.state/org-state.md`

### Common procedure (all patterns; after placement)

Substitute CLAUDE.md template variables with actual values (settings.local.json substitutions are handled by the generator and are out of scope here):
- `{project_name}` → registry nickname
- `{project_description}` → registry description
- `{task_id}` → task ID (e.g. `data-analysis`)
- `{task_description}` → task goal and deliverable
- `{claude_org_path}` → absolute path of the claude-org repository
- `{worker_dir}` → absolute path of the Worker directory (varies by pattern; see above)

Verify that the generated CLAUDE.md contains the "Working directory (most important constraint)" section. If it doesn't, the template was not applied correctly — regenerate.

**If a reference work-skill exists (matched in Step 0.5):**

Add the following section to CLAUDE.md (place it after the "Files to refer to" section):

```markdown
## Reference work-skill
The following work-skill(s) may be useful. Refer to its procedure and judgment criteria.
Adjust as appropriate where it does not fit this task's requirements.

- Skill name: {skill-name}
- Path: {claude_org_path}/.claude/skills/{skill-name}/SKILL.md
- Summary: {description}
```

## Step 2: Hand off to the Dispatcher (Lead executes → Lead is released here)

Send the following via renga-peers `send_message` to the Dispatcher (pane name = `dispatcher`):

```
DELEGATE: Please dispatch the following Workers.

Task list:
- {task_id}: {task description}
  - Worker directory: {absolute path of the Worker directory} (CLAUDE.md and settings already placed)
  - Directory pattern: {A: project directory / B: worktree / C: ephemeral}
  - Project: {clone URL or local path or new creation or worktree-ready or carried over from previous task}
  - Permission Mode: {value of default_permission_mode read from org-config}
  - Verification depth: {full | minimal} (must match the same line in instruction-template; the Dispatcher transcribes this value verbatim into the Worker instruction)
  - Instructions: {summary of the instruction based on instruction-template. Always keep the "Verification depth" line intact when forwarding}

Lead pane name: `secretary` (registered by the renga layout; serves as the basis when creating new tabs)
```

**The Lead can return to user dialogue immediately after this send.**
Tell the user "Dispatch requested to the Dispatcher. I'll report back as soon as it's ready."

> In renga, "long-lived panes" like Lead / Dispatcher / Curator are addressable by stable name (`--id`).
> Lead (`secretary`) / Dispatcher (`dispatcher`) / Curator (`curator`) are named by `/org-start`.

## Step 3: Spawn Workers and send instructions (Dispatcher executes)

The Dispatcher executes the following:

### 3-1. Choose target / direction via balanced split

The old design picked the target via an ordinal-`k`-based lookup table, but during re-dispatch after a Worker closed in the middle, or with unexpected retirement order, the table assumption diverged from the actual layout, easily inducing `[split_refused]`. Since the renga-peers MCP `mcp__renga-peers__list_panes` returns each pane's `id / name / role / focused / x / y / width / height` (in cell units), we use a **scheme that picks target and direction dynamically from the current layout (rect)**. See the "Worker balanced split strategy" section of `references/pane-layout.md` for the detailed rules.

#### 3-1a. Get the layout

Call `mcp__renga-peers__list_panes` and extract every pane's attributes from the returned text. Each pane has the fields:

- `id`: integer
- `name`: string (only for panes explicitly given a name via `spawn_pane` / `new_tab`; omitted if unset)
- `role`: string (one of "secretary" / "dispatcher" / "curator" / "worker"; omitted if unset)
- `focused`: bool (judged by whether `(focused)` appears on the output line)
- `x / y / width / height`: integers in cell units

#### 3-1b. Balanced split algorithm (Claude executes the decision logic)

**Constants**:
- `MIN_PANE_WIDTH = 20` / `MIN_PANE_HEIGHT = 5`: renga's split lower bounds (findings: renga-split-inv)
- `SECRETARY_MIN_WIDTH = 125` / `SECRETARY_MIN_HEIGHT = 45`: minimum width / height for treating secretary as a split candidate (insurance clause; rarely fires in practice)

**Step 1. Identify the curator**: pick one pane with `role == "curator"` (the first if multiple). Henceforth `$curator`. If none exists, `$curator = null`.

**Step 2. Filter candidates**:
- Candidates are panes with `role ∈ {"secretary", "dispatcher", "worker"}` only
- Keep `role == "dispatcher"` panes **only if they are rect-adjacent to `$curator`** (if `$curator = null`, exclude dispatchers as well)
  - Rect adjacency definition (one of the following):
    - **Vertical-edge shared + y-interval overlap**: `a.x + a.width == b.x` or `b.x + b.width == a.x`, and `max(a.y, b.y) < min(a.y + a.height, b.y + b.height)`
    - **Horizontal-edge shared + x-interval overlap**: `a.y + a.height == b.y` or `b.y + b.height == a.y`, and `max(a.x, b.x) < min(a.x + a.width, b.x + b.width)`

**Step 3. Attach direction / new_w / new_h / metric to each candidate**:
- `direction = (width > height * 2) ? "vertical" : "horizontal"`
  - Terminal cells are roughly 2:1 height:width (characters are tall). `width > height*2` means physically wide → splits cleanly with vertical (left/right)
  - Otherwise horizontal (top/bottom)
- `new_w = (direction == "vertical") ? floor(width / 2) : width`
- `new_h = (direction == "horizontal") ? floor(height / 2) : height`
- `metric = (direction == "vertical") ? new_w : new_h` (new size in the split-axis direction)

**Step 4. MIN_PANE constraint**:
- Keep only panes with `new_w >= MIN_PANE_WIDTH` and `new_h >= MIN_PANE_HEIGHT`

**Step 5. Lead pane insurance clause**:
- Keep `role == "secretary"` panes only when `new_w >= SECRETARY_MIN_WIDTH` **and** `new_h >= SECRETARY_MIN_HEIGHT` (passing width alone is not enough; height must also pass)

**Step 6. Sort & select**:
- Descending by `metric`, tie-break by `id` ascending
- Use the first element's `name` as `$target` and `direction` as `$direction`

On the very first dispatch (zero workers), the dispatcher remains as the sole candidate, and direction is determined by the dispatcher's aspect ratio (typically wide → vertical).

#### 3-1c. When the candidate set is empty

When `$target` is empty (no candidates), the Dispatcher Claude **does not issue `spawn_pane`**, and instead sends an escalate message to the Lead (`secretary`) via renga-peers:

1. Call `mcp__renga-peers__send_message(to_id="secretary", message=...)` with body:
   ```
   SPLIT_CAPACITY_EXCEEDED: no Worker split target found for {task_id}.
   Zero candidates satisfy the rect-based balanced-split MIN_PANE / adjacency conditions.
   Suspect insufficient terminal size or an unexpected layout. Human judgment required.
   ```
2. **Skip** 3-2 onward (`spawn_pane` / launch confirmation / `list_peers` wait / instruction send). Cancel only this one Worker dispatch and **continue** the Dispatcher main monitoring loop. Do not let the Dispatcher exit / return.

### 3-2. Spawn the Worker pane

Use `$target` / `$direction` computed in 3-1 to call `mcp__renga-peers__spawn_claude_pane`. **If `$target` is empty, do not spawn; follow the escalate procedure in 3-1c**:

```
mcp__renga-peers__spawn_claude_pane(
  target=$target,                         # existing pane name computed in 3-1
  direction=$direction,                   # "vertical" or "horizontal"
  role="worker",
  name="worker-{task_id}",                # stable name referenced by subsequent ops; must contain letters
  cwd="{workers_dir}/{task_id}",          # absolute path recommended; relative resolves from caller pane's cwd
  permission_mode="{default_permission_mode}",
  model="opus"                            # required. sonnet prohibited (auto classifier unstable)
)
```

- **`model="opus"` is required (sonnet prohibited).** The safety classifier of the Worker's `auto` permission_mode operates reliably only on Opus; with sonnet, misclassifications happen frequently and the approval flow breaks. Only the Dispatcher is fixed at `bypassPermissions` and bypasses the classifier, so sonnet works there.
- Pane placement rules: see `references/pane-layout.md`. The rect-based target / direction selection rules are consolidated there.
- **Why we spawn within the same tab**: renga's `list_panes` / `focus_pane` / `send_message` / `inspect` (CLI) can only see panes in the currently focused tab. Putting Workers in a separate tab via `new_tab` makes them invisible to the Dispatcher for monitoring and instruction (renga-side issue: suisya-systems/renga#71)
- `name="worker-{task_id}"`: stable name that makes the pane addressable for later `mcp__renga-peers__send_message(to_id="worker-{task_id}", ...)` and `close_pane(target="worker-{task_id}")`. **All-digit names are treated as ids**, so always include letters via a `worker-` prefix etc.
- `role="worker"`: identifies the role in `list_panes` output (also used for target selection in subsequent balanced splits)
- `cwd` / `permission_mode` / `model` / `args[]` are structured fields of `spawn_claude_pane`. renga composes `claude --permission-mode {mode} --dangerously-load-development-channels server:renga-peers ...`. The old method (passing a `cd`-prefixed command string to `spawn_pane`) is **prohibited** — a cwd-changing prefix prevents renga's bare-`claude` auto-upgrade from firing, and channel push is lost
- See the "ClaudeCode launch commands (per role)" section of `.claude/skills/org-start/SKILL.md` for the launch-command spec
- Because `spawn_claude_pane` internally adds `--dangerously-load-development-channels`, the `Load development channel?` confirmation prompt appears on first launch. Approval via `send_keys(enter=true)` is needed in Step 3-3b
- **Error handling**: errors are embedded in the MCP result text in `[<code>] <msg>` form. Main codes:
  - `[split_refused]` (MAX_PANES / too small): follow the procedure in `references/renga-error-codes.md` and escalate Curator → Lead. Balanced split is a best-effort placement hint; in unexpected layouts (e.g. re-dispatch after a Worker closed) it may be refused.
  - `[pane_not_found]`: race in which the existing pane chosen as `$target` closed just before spawn was issued. Same — escalate via the error-code path.
  - `[cwd_invalid]`: the specified cwd does not exist / is not a directory. Rejected before pane creation, so no half-mutated layout. Escalate to the Lead and verify Worker directory preparation (Step 1.5 of org-delegate) is complete.
  - `[invalid-params]`: rejected when `args[]` includes `--permission-mode` / `--model` / `--dangerously-load-development-channels`. Pass via the structured fields.
  - For other codes, see `references/renga-error-codes.md`.

### 3-3. Confirm the pane has started

Wait up to 3 seconds for a `pane_started` event via `mcp__renga-peers__poll_events`. To handle simultaneous spawns of other workers and early returns triggered by filter mismatches, **write it as a re-poll loop within the 3-second deadline**:

```
cursor = None                    # first call omits since (= "events from now on" semantics)
deadline = now + 3 seconds
while now < deadline:
    remaining_ms = (deadline - now) milliseconds
    result = mcp__renga-peers__poll_events(
        since=cursor,                                  # use last call's next_since from second iteration onward
        timeout_ms=min(remaining_ms, 3000),
        types=["pane_started"]
    )
    cursor = result.next_since                          # use on next call
    for ev in result.events:
        if ev.name == "worker-{task_id}":
            return OK                                   # launch confirmed
# deadline exceeded → no launch event detected
# Re-confirm pane existence via mcp__renga-peers__list_panes; if absent, escalate to the Lead
```

- Omitting `since` on first call = same "events from now on" semantics as `renga events --timeout` (does not replay past launch events)
- `types=["pane_started"]` excludes other types (`pane_exited` etc.) while the cursor advances on all types (no duplicate scans)
- **Filter-mismatching events cause early termination of long-poll, returning `events:[]` + an advanced cursor**, so loop on with empty responses (no duplicates because cursor is preserved)
- Break on `pane_started` with `name == "worker-{task_id}"`. If deadline exceeds without detection, re-confirm pane existence via `list_panes`

### 3-3b. Approve the "Load development channel?" prompt with Enter

Because `spawn_claude_pane` internally adds `--dangerously-load-development-channels server:renga-peers`, a Y/n confirmation prompt appears on first launch. Approve with Enter:

```
mcp__renga-peers__send_keys(target="worker-{task_id}", enter=true)
```

Without approval, the `server:renga-peers` channel is not enabled, the `list_peers` wait in 3-4 times out, and `send_message` in 3-5 does not arrive. Enter is written to the PTY as CR (0x0D) (byte-identical to renga `append_enter`).

### 3-4. Wait for the new peer via `mcp__renga-peers__list_peers`

The pane may be live while Claude is still launching, so do a second confirmation. Call `mcp__renga-peers__list_peers` and retry at short intervals (e.g. 2 seconds) until `worker-{task_id}` appears in the peer list (up to ~30 seconds). On timeout, re-confirm pane state via `list_panes` and escalate to the Lead if necessary.

### 3-5. Send the instruction to the Worker via `mcp__renga-peers__send_message`

Follow the format in `references/instruction-template.md`. Specify the pane name with `to_id="worker-{task_id}"`.

### 3-6. Sequential launch of multiple Workers

If there are multiple Workers, repeat 3-1 through 3-5 in order. Because the result of `list_panes` changes each time, **re-fetch every time** and redo the balanced-split decision (wait for the previous Worker's launch to complete in 3-3 / 3-4 before moving on).

## Step 4: Record state (Dispatcher executes)

For each Worker:

1. Create `.state/workers/worker-{task_id}.md` (in renga-peers, the pane name `worker-{task_id}` is the stable identifier; the legacy peer-id is no longer used):
   ```markdown
   # Worker: worker-{task_id}
   Task: {task_id}
   Directory: {working directory}
   Pane ID: {pane_id}
   Started: {ISO timestamp}

   ## Assignment
   {task description}

   ## Progress Log
   - [{time}] Dispatch complete; work started
   ```

2. Update `.state/org-state.md` (create if missing):
   - Record the human's request in Current Objective
   - Add the task to Active Work Items

3. Append an event to `.state/journal.jsonl`:
   ```json
   {"ts":"<ISO timestamp>","event":"worker_spawned","worker":"worker-{task_id}","dir":"<dir>","task":"{task_id}"}
   ```

4. After updating `.state/org-state.md`, regenerate the JSON snapshot:

   ```bash
   py -3 dashboard/org_state_converter.py    # Windows
   python3 dashboard/org_state_converter.py   # Mac/Linux
   ```

5. Register the Worker pane as a monitoring target:
   - After dispatch, record that pane as a monitoring target and periodically check for pending approvals per the "Worker pane monitoring" section of `.dispatcher/CLAUDE.md`

### Worker Directory Registry (section definition inside org-state.md)

Add and maintain the following section in `.state/org-state.md` to track Worker-directory reuse status.

```markdown
## Worker Directory Registry

| Task ID | Pattern | Directory | Project | Status |
|---|---|---|---|---|
| blog-redesign | A | /path/to/workers/blog/ | blog | in_use |
| blog-auth-fix | B | /path/to/workers/blog/.worktrees/blog-auth-fix/ | blog | in_use |
| data-analysis | C | /path/to/workers/data-analysis/ | - | in_use |
```

**Field descriptions:**
- **Task ID**: the task ID currently using that directory
- **Pattern**: A (project directory) / B (worktree) / C (ephemeral)
- **Directory**: absolute path of the Worker directory
- **Project**: nickname from registry/projects.md (`-` if ephemeral and unrelated)
- **Status**: `in_use` (in progress) / `available` (completed, reusable)

**Operational rules:**
- Add the entry during directory preparation in Step 1.5
- Update the status when the human approves in Step 5 (2b) (do not delete the directory)
- The decision flow in Step 1 references this table to determine reusable directories and parallel-work conflicts

5. Report dispatch completion to the Lead (`secretary`) via renga-peers:
   ```
   DELEGATE_COMPLETE: dispatched the Worker for {task_id}.
   Pane: worker-{task_id} (id={pane_id})
   ```

## Step 5: Progress management (Lead executes)

### On receiving DELEGATE_COMPLETE

When the Lead receives the dispatch-complete report from the Dispatcher, send a greeting message to each Worker:
```
mcp__renga-peers__send_message(
  to_id="worker-{task_id}",
  message="This is the Lead. You're working on {task_id}. Send all reports — completion, progress, blockers — via renga-peers with `to_id=\"secretary\"`."
)
```
The Worker side, per the worker-claude-template policy, sends to the fixed pane name `secretary`, so there is no need to keep the Lead's peer-id in history (this greeting is just confirmation that work has started).

### On receiving a message from a Worker

When the Lead receives a message from a Worker via renga-peers:

1. For a progress report:
   - Append to the Progress Log of `.state/workers/worker-{task_id}.md`
   - Append an event to `journal.jsonl`
2a. When a completion report is received from a Worker:
   - Update the corresponding Work Item in `org-state.md` to **REVIEW**
   - Append an event to `journal.jsonl`
   - Regenerate the JSON snapshot: `py -3 dashboard/org_state_converter.py`
   - Report results to the human
   - **Do not close the pane yet**

2b. On human approval ("OK", "looks good", "no problem", etc.):
   - Update the corresponding Work Item in `org-state.md` to **COMPLETED**
   - Make the final update to the Worker's state file
   - Append an event to `journal.jsonl`
   - The Lead does push / PR creation as needed (the Worker has no permission for these)
   - Ask the Dispatcher to close the pane:
     `CLOSE_PANE: please close pane {pane_id}.`
   - **Post-processing per directory pattern**:
     - Pattern A (project directory): keep the directory (reuse for the next task)
     - Pattern B (worktree): run `git -C {workers_dir}/{project_slug}/ worktree remove .worktrees/{task_id}`. Keep the branch (for PR/merge use)
     - Pattern C (ephemeral): keep the directory (consider manual deletion only when capacity becomes an issue)
   - Update the Worker Directory Registry of `.state/org-state.md`:
     - Pattern A: set status to `available` (reusable for the next task)
     - Pattern B: delete the entry (worktree already removed)
     - Pattern C: delete the entry
   - Regenerate the JSON snapshot: `py -3 dashboard/org_state_converter.py`

2c. When the human gives feedback / a correction directive:
   - Send an additional instruction to the Worker via renga-peers (`to_id="worker-{task_id}"`)
   - If the additional instruction is a trivial fix (CI output formatting / typo / comment edits, etc.), explicitly state **verification depth `minimal`** and tell the Worker that the completion report should be the single line `done: {short commit SHA} {changed file name}` (the format follows `references/instruction-template.md` / `references/worker-claude-template.md`)
   - Revert the corresponding Work Item in `org-state.md` to **IN_PROGRESS**
   - Append an event to `journal.jsonl`
   - Regenerate the JSON snapshot: `py -3 dashboard/org_state_converter.py`
   - (Since the pane is still alive, the Worker continues the work as-is)

### Worker monitoring and intervention judgment (Lead executes)

After dispatch, periodically check whether the Worker has fallen into a deep-dive / over-verification loop:

**Intervention triggers** (if any one applies, check the situation via `mcp__renga-peers__inspect_pane`):
- Same task running for over 30 minutes and entering the same phase (implementation / review / verification) for the 3rd or later time
- No progress report for over 1 hour in silence (not waiting on input, no progress log either)
- (When using codex) Codex self-review has entered the 4th round or later (the 3-round cap is a Worker-side directive, but the Lead also checks). Irrelevant in environments where codex is not installed

**Intervention procedure**:
1. Inspect the screen via `inspect_pane` (judge as one of: Running / Codex running / awaiting input)
2. If judged a deep dive, interrupt with `send_keys(target="worker-{task_id}", keys=["Escape"])`
3. Send a tight correction instruction via `send_message`. Examples:
   - "Switching verification depth to minimal. No Codex review or additional tests. Commit what you have and reply with only the single line `done: {short commit SHA} {changed file name}`."
   - "Minor findings can stay. Add a 1-line note as a known limitation in README, then send the completion report (verification depth stays `full`, so use the normal completion-report format)."

**Note**: the Lead committing on behalf of the Worker in the Worker's worktree is blocked by the auto-mode classifier (out of scope). Intervention is always via "re-sending the instruction".
3. For a blocker report:
   - Ask the human for judgment
