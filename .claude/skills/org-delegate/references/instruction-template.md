# Worker Instruction Template

Task-specific instructions sent via renga-peers `send_message` (`to_id="worker-{task_id}"`).
Instructions for permissions, reporting destination, SUSPEND handling, and knowledge logging are centralized in `worker-claude-template.md` (via `CLAUDE.md`), so they are not repeated here.

> **Transport — both backends (default `broker` / opt-in `renga`)**: the peer-message and pane operations in this file (and across the skills) are written as `mcp__org-broker__*`. With **`ORG_TRANSPORT` unset = default `broker`**, follow them as-is. With `ORG_TRANSPORT=renga` (opt-in, revertible), the MCP server name becomes `renga-peers`, and the **fully qualified names are mechanically substituted `mcp__org-broker__*` → `mcp__renga-peers__*`** (argument shape and semantics are identical, so the operational logic does not change). The three transport-dependent differences are:
>
> - **Receive model (default = push-primary = `claude/channel` / pull fallback)**: the default broker is designed as **push-primary** (runtime push-first 0.1.24+; design SoT is transport-lab `docs/design/broker-native-roles.md` §9). A **channel sidecar** (`server:org-broker-channel`) co-located with each pane claims the broker queue at ~1s intervals and pushes via `notifications/claude/channel`, injecting the body into an idle session (creating the "respond as soon as it arrives" trigger). Worker ack (`to_id="worker-{task_id}"`), retro-gate ack (`to_id="dispatcher"`), and the dispatcher handover route's `send_message` / `check_messages` / `send_keys` / `inspect_pane` all work under the same tool names (`mcp__org-broker__*`). **Pull is the fallback layer**: when the sidecar is absent or unhealthy (heartbeat timeout flips to `delivery_mode=PULL`), for channel-incapable panes (codex pull-peer), or when claude.ai login is missing, each role actively `check_messages` on its own cadence (per-role cadence: worker = turn boundary / bounded `/loop` after completion; dispatcher = `/loop 3m`; secretary = at turn start; the existing "when you see a nudge, `check_messages`" prose is **not retracted** and should be read as this fallback cadence). With `ORG_TRANSPORT=renga` (opt-in), worker reports and dispatcher responses are pushed in-band as `<channel source="renga-peers" …>` (renga's in-band push and broker push-primary share the same immediate-response trigger). Contract-wise, push-primary is **ratified** on Surface 8 + push-primary amendment (2026-06-15, S3; pull is retained as fallback; renga is unchanged).
> - **Spawn ritual (default = folder-trust approval + dev-channel sidecar approval, 2 steps)**: when spawning a child pane, the default broker injects `--mcp-config <broker>` and mechanically approves Claude Code's **folder-trust prompt** with `send_keys(enter=true)`, **and in addition**, loads the channel sidecar via `--dangerously-load-development-channels server:org-broker-channel` for push-primary and mechanically approves the dev-channel approval prompt (spawn-flow 3-3b) with `send_keys(enter=true)` (folder-trust + dev-channel = 2-step approval; details in [`.dispatcher/references/spawn-flow.md`](../../../../.dispatcher/references/spawn-flow.md) 3-2 / 3-3b, design in broker-native-roles.md §9.5). With `ORG_TRANSPORT=renga` (opt-in), it injects `--dangerously-load-development-channels server:renga-peers` and approves the "Load development channel?" prompt with Enter — 1 step. **Note: the attention watcher is a transport-independent CLI pane and is exempt from both the folder-trust and dev-channel 2-step approvals** (do not pull it into the spawn-ritual inversion).
> - **Error branching (default = broker extended codes included)**: in addition to the shared codes (`pane_not_found` / `last_pane` / `invalid-params`, Surface 6), the default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` / `[unknown_tool]` (unknown codes escalate via the default branch). With `ORG_TRANSPORT=renga`, broker-specific codes never occur — only shared codes + renga-specific codes.
>
> The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../../docs/contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14) + the tail "Ratified amendment (2026-06-15): push-primary delivery" (S3; **broker push-primary is the default contract**, pull is retained as structural fallback). Design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary) / `docs/design/ja-migration-plan.md` §5 and §8. **The opt-in `renga` is not deleted and is maintained as a permanently-available fallback** (the revert safety net). Broker actual-run (dogfood) is in scope for Epic #6 Issue G and is **not** the default operational route in this file (**Two-frame note on "default" (Refs #604)**: "default `broker`" here refers to the **code-default** frame — `tools/transport.py: DEFAULT_TRANSPORT` has been flipped to `broker` in runtime 0.1.28 (Epic #586), and the ja generator / `transport.resolve()` render against this code frame, so the generated surface displays it this way. There is a separate **operational-default** frame in which the operational default route is `renga`, because broker actual-run dogfood is not yet activated through Epic #6 Issue G. The two frames refer to different objects (code constant vs. operational route) and do not contradict each other. The overview is in root [`CLAUDE.md`](../../../../CLAUDE.md), section "Transport — both backends".)

## Template

```
Please carry out the following task. Detailed behavioral rules are documented in CLAUDE.md.

## Task
{Describe the task purpose and expected deliverables in detail}

## Project Setup
Important: your working directory is the absolute path described in CLAUDE.md.
First, run `pwd` and confirm that it matches the working directory in CLAUDE.md.
All file creation must be limited to this directory. Moving to `..` or recreating the claude-org structure is prohibited.
{Include one of the following depending on the directory pattern}

### Pattern A (project directory, first time):
The working directory has already been prepared by the Lead (secretary) before spawn (clone / `git init`, etc. have already been completed on the Lead side).
Your first action after startup: run `pwd` and confirm that it matches the expected directory described in CLAUDE.md.
Do not run `git clone` / `git init` on the Worker side. Do not create directories that imitate the claude-org structure (`.claude/`, `.state/`, etc.).
{Include only information such as the clone source URL / local path / whether it is a new project, as needed}

### Pattern A (project directory, reused):
This directory is a project directory used in a previous task. Existing files and git history remain.
No clone is required. {Add handoff notes if any}

### Pattern B (worktree):
This directory has already been prepared as a git worktree. It is checked out to branch `{branch_name}`.
No clone is required. Start working as-is.

### Pattern C (ephemeral):
The working directory has already been prepared by the Lead (secretary) before spawn (clone / `git init`, etc. have already been completed on the Lead side).
Your first action after startup: run `pwd` and confirm that it matches the expected directory described in CLAUDE.md.
Do not run `git clone` / `git init` on the Worker side. Do not create directories that imitate the claude-org structure (`.claude/`, `.state/`, etc.).
{Include only information such as the clone source URL / local path / whether it is a new project, as needed}

## Branch Strategy
{Specify the branch name, or whether to work directly on main, etc.}

## How to Proceed
Work directly in auto mode. Do not use Plan mode.

## Constraints
{Include any language, framework, test requirements, etc.}

## Verification Depth: {full | minimal}
Do **not** delete this line from the template; always send it. The Lead must fill in exactly one of the two values.
The default is `full`. Only for a trivial fix should the Lead choose and fill in `minimal`.

- **full** (new feature implementation / fix / refactor / test addition / hook, skill, or config edits, and anything else involving code or behavior changes)
  - **Knowledge layer privacy (applies only in full mode when recording to `knowledge/raw/`)**: `knowledge/raw/` and `knowledge/curated/` are committed to a public OSS repository. Do not write operator-private content such as operator personal names, internal system identifiers, customer data, secrets, or internal URLs into these directories. If you learn something that includes such information, do not record it; escalate to the Lead (secretary) instead.
  - **Required regardless of whether codex is present**: run the repository's normal verification steps such as the existing test suite / lint / type-check until green, and report using the normal completion format (deliverable summary, remaining work, PR draft / retrospective record)
  - **Additional gate (optional)**: after completing the commit, if the `codex` CLI is available, run a Codex self-review with `codex exec --skip-git-repo-check`
    - Check command: `command -v codex` (Bash/zsh) / `Get-Command codex -ErrorAction SilentlyContinue` (PowerShell)
    - In environments where codex is not installed, skip the self-review and proceed to the completion report with only the normal verification above (the round rules below do not apply)
  - **The following applies only if codex is run**:
    - For Blocker / Major findings, add a fix commit before the completion report
    - **If the same finding category (for example: tightening a loose match / narrowing a type) cannot be cleared after 3 rounds, it is a design problem**. Report completion immediately and ask the Lead to decide whether to reduce scope (prevents infinite loops)
    - Minor / Nit findings should generally be left as-is. Document them as known limitations in the README / Issue / PR body
    - Do not use the `codex:rescue` skill (there have been hangs longer than 18 minutes; running `codex exec` directly is more stable)
  - Review instruction example: `codex exec --skip-git-repo-check "Review the diff in this branch from main. Classify findings as Blocker/Major/Minor/Nit, and for each finding include the target file:line number and rationale, concisely in Japanese"`

- **minimal** (trivial fix: CI output formatting / typo / comment correction / aligning to an existing test format, etc., where the instructed changes are limited to a few lines in a single file)
  - Apply the instructed fix → `git add` → go straight to `git commit`
  - Codex self-review, additional test execution, and any behavioral verification beyond checking the diff are **strictly prohibited**
  - Send the completion report to the Lead (`secretary`) as a single line:
    - `done: {short commit SHA} {changed filename}` (example: `done: be8f497 tests/test-block-pretooluse-hooks.sh`)
    - Use `git rev-parse --short HEAD` for the SHA. For filenames, send one if only one file changed, or separate multiple filenames with spaces
    - No other information is needed (deliverable summary, PR draft, remaining issues, etc.). Push / PR creation will be handled by the Lead side
  - A retrospective record (`knowledge/raw/`) is **not required** for minimal mode (on the assumption that there is no reusable learning in a trivial fix). If there is a non-obvious finding, you may create one entry just as in `full`

**The choice is the Lead's responsibility**. The Worker must follow the value written in the instruction (`full` or `minimal`) as-is and must not decide to switch it independently. If this line itself was not sent at dispatch time, or if the value was ambiguous, the Worker must ask the Lead for confirmation (do not unilaterally fall back to `full`).
```

## Consistency grep target list for cross-cutting operational changes

When delegating **cross-cutting changes** such as operating mode changes, shared configuration changes, or naming convention changes (changes that are not confined to one file and span multiple roles / skills / settings / documents), explicitly specify the grep scope for consistency checking in the Worker's "Constraints" or "Task" section. If you do not specify the scope, the Worker may fix only the files they happen to notice and miss same-name references on other roles or documentation sides, which is especially common in renames and mode changes.

### Examples of changes that should be classified as "cross-cutting"

- **Operating mode changes**: switching defaults such as Plan / auto / `bypassPermissions`
- **Wholesale changes to permissions / hook settings**: rewriting allow / deny / hooks across `.claude/settings*.json`
- **Communication channel / MCP server name changes**: renaming renga-peers peer names, MCP server names, or role identifiers (example: `foreman` → `dispatcher`)
- **Adding or removing shared flags / env vars**: environment variables or CLI flags read by all roles or multiple skills

Conversely, behavior changes confined within a single skill or a single role (for example, format adjustments within `org-retro`) are not cross-cutting, so this section is unnecessary.

### Recommended grep target directories

If a change is judged to be cross-cutting, **list at least the following as grep scope in the Worker instructions**. Remove any that do not exist in the project structure:

- `.claude/` — include not only the skill bodies (`skills/`) but also `settings.json` / `settings.local.json`. Permission / hook / env changes often remain in the settings themselves, and scanning only `.claude/skills/` can miss the canonical configuration
- `registry/` — `projects.md` / `org-config.md` / `worker-directory.md`
- `knowledge/curated/` — accumulated operational knowledge (patterns written under old names tend to remain)
- `dashboard/` — JSON generation scripts and templates
- `.dispatcher/` — Dispatcher role runtime / prompts
- `.curator/` — Curator role runtime / prompts
- `.hooks/` — PreToolUse / PostToolUse hook scripts themselves (references to hook filenames and role identifiers tend to remain)
- `docs/` — public documentation
- `tools/` — checkers and helper scripts (`check_role_configs.py`, etc.)
- `tests/` — tests for hooks / runners / checkers (if fixture names are missed in a rename or mode change, CI can break)

Example Worker instructions:

```
## Constraints
- Grep the following directories to ensure no references to the old name `foo` remain, and if found, replace all of them with the new name `bar`:
  - .claude/                (including settings.json / settings.local.json)
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

If the old name / new name has not yet been finalized at the time of delegation, have the Worker operate in two stages: "detect and list target patterns → confirm with the Lead → replace".

## doc-audit role only: chunked transfer method for write artifacts

In the doc-audit role, Edit / Write / MultiEdit / NotebookEdit are denied, and Bash heredoc is also blocked by the deny-circumvention safeguard. In tasks that require writing out artifacts such as `AUDIT.md`, incidents reproducibly occur where the Worker gets stuck holding the body text (example: 2026-05-03 readme-drift-audit, 26 findings × 7 repos).

For delegations with the doc-audit role plus a write artifact, **always add** the following text to the "Constraints" section:

> Do not write the artifact (`{ARTIFACT_NAME}`) to a file. Instead, split the body into chunks of about 8000 characters and send them sequentially via renga-peers `mcp__renga-peers__send_message(to_id="secretary")`. Add a `[CHUNK n/N]` header at the start of each chunk, and send `[CHUNK_END]` at the end. The Lead side will concatenate them and write them out as `{worker_dir}/{ARTIFACT_NAME}`. Do not attempt Edit/Write (it will be denied).

Replace `{ARTIFACT_NAME}` with the actual filename such as `AUDIT.md` or `REPORT.md`.

## Notes for Use

- Describe the task concretely. Ambiguous instructions increase the Worker's decision cost
- If there are constraints, always state them explicitly

## Auto-Expansion Template (helper-rendered)

If the task JSON includes `instruction_vars`, `claude-org-runtime dispatcher delegate-plan --locale-json <path-to-ja_locale.json>` expands the variables in the following strict template and writes the result as Worker instructions (defaults such as Japanese greeting text or `(none)` are overridden in `tools/ja_locale.json` directly under the repository root. Because the Dispatcher runs with `cwd=".dispatcher/"`, the actual invocation should point one level up, such as `--locale-json ../tools/ja_locale.json --template-repo ..`. See the command example in `.dispatcher/CLAUDE.md` for details). If the `instruction` field is specified directly, that takes precedence and this template is not used (backward-compat).

Variable list (referenced by the helper side):

- `task_description` (required): the task purpose and expected deliverables
- `dir_setup` (required): project setup instructions. The Lead passes a resolved string for Pattern A/B/C
- `branch_strategy` (required): branch strategy. Required because defaulting to main when deploying a worktree would be misleading
- `verification_depth` (required): `full` or `minimal`
- `constraints` (optional): constraints. Defaults to "(none)" when omitted
- `report_target` (optional): peer name for completion reports. Defaults to `secretary` when omitted
- `claude_md_filename` (optional): filename of the behavioral rules file the Worker reads. Defaults to `CLAUDE.md`. For claude-org self-edit tasks, pass `CLAUDE.local.md` (see `references/claude-org-self-edit.md`)

Unknown variable keys are rejected as input_invalid. `verification_depth` is also input_invalid if it is anything other than `full` / `minimal`.

<!-- AUTO-EXPAND-TEMPLATE-START -->
```
Please carry out the following task. Detailed behavioral rules are documented in {claude_md_filename}.

## Task
{task_description}

## Project Setup
Important: your working directory is the absolute path described in {claude_md_filename}.
First, run `pwd` and confirm that it matches the working directory in {claude_md_filename}.
All file creation must be limited to this directory. Moving to `..` or recreating the claude-org structure is prohibited.

{dir_setup}

## Branch Strategy
{branch_strategy}

## How to Proceed
Work directly in auto mode. Do not use Plan mode.

## Constraints
{constraints}

## Verification Depth: {verification_depth}
- full: run normal verification such as the existing test suite / lint / type-check until green, and after completing the commit, if the codex CLI is available, run a self-review with `codex exec --skip-git-repo-check`. For Blocker / Major findings, add a fix commit before the completion report. If the same finding category cannot be cleared after 3 rounds, report completion immediately. Minor / Nit findings should be left as-is (document them as known limitations). **Knowledge layer privacy (applies only in full mode when recording to `knowledge/raw/`)**: `knowledge/raw/` and `knowledge/curated/` are committed to a public OSS repository. Do not write operator-private content such as operator personal names, internal system identifiers, customer data, secrets, or internal URLs. Do not record learnings that include such information; escalate them to the Lead (secretary).
- minimal: only for trivial fixes. Codex self-review and additional verification are prohibited. Send the completion report to the Lead as a single line (`done: <SHA> <files>`).

## Reporting Destination
Send completion / progress / block reports via renga-peers to `to_id="{report_target}"`. Push / PR creation will be handled by the Lead side.

## SUSPEND Handling
If you receive a message starting with `SUSPEND:`, stop work and report the situation.
```
<!-- AUTO-EXPAND-TEMPLATE-END -->

This template body is read by the helper, so do not change the position of the marker comments or the code fence above (if you modify them, also verify consistency with the parser implementation on the `claude-org-runtime` side: `claude_org_runtime.dispatcher.runner.load_instruction_template`).
