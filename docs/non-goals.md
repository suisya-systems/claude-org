# Non-goals (Things this project deliberately doesn't do)

claude-org is an **operational-discipline framework** scoped to running an organization on top of Claude Code. The list below makes explicit which capabilities we have decided not to build, even though they may sound convenient. Stating absences actively is the device we use to communicate the boundary — and the value — of this framework.

> The README summarizes only the five strongest items. This document is the long form and covers all twelve.

---

## 1. We don't hand `--dangerously-skip-permissions` to Workers by default

**What we don't do**: ship `--dangerously-skip-permissions` (= `permission_mode="bypassPermissions"`), which broadly suppresses Claude Code's permission prompts, as a default for the Workers that do real work (and for the Lead that instructs them). We do not adopt the "every role uniformly bypasses" stance.

**Why**: claude-org's core value is **narrow allow-listing plus defense in depth**. Handing a blanket bypass to the role that actually does work eliminates our ability to pre-empt the most catastrophic accident classes — `git push --force`, reads of `.env`, and so on. This is the opposite direction from farm-style "everything fully automatic" tools; we don't accept "dangerous operations quietly running where no one is watching."

That said, claude-org is **deliberately heterogeneous in `permission_mode` across roles**. Pretending "every role runs in `auto`" would diverge from reality, so we lay it out honestly:

| Role | `permission_mode` | Model | Notes |
|---|---|---|---|
| Lead | `auto` | Opus | Narrow allow-list in `settings.local.json` plus PreToolUse hooks |
| Dispatcher | `bypassPermissions` | Sonnet | **Exception.** See below |
| Curator | `auto` | Opus | Minimal allow-list (read-mostly plus the writes needed for curation) |
| Worker | `auto` | Opus | Narrow allow-list + role-specific hooks + per-task working-directory boundary |

The reason only the Dispatcher is pinned to `bypassPermissions` is **a forced consequence of cost optimization**. In Claude Code (TUI), `auto` mode is only available on Opus-class models — Sonnet cannot run `auto` at all. Since we run the Dispatcher on Sonnet, the only realistic value of `permission_mode` is `bypassPermissions`. This isn't classifier evasion; it's the only choice the environment offers.

### What `bypassPermissions` actually does (no fudging)

True to its name, `bypassPermissions` mode bypasses **both** `permissions.allow` and `permissions.deny`. That is, "the deny rules in `permissions.deny` such as `git push --force` are not enforced on the Dispatcher." What Claude Code itself still preserves under bypass is only the write-confirmation prompt for protected directories such as `.git/`, `.claude/`, `.vscode/`, `.idea/`, and `.husky/`.

So the Dispatcher's effective defense layers come out as:

1. **Auto-confirmation prompts for protected directories** (the residual range Claude Code keeps even under `bypassPermissions`)
2. **PreToolUse hooks** (run even under `bypassPermissions`, can block a tool call by exiting with code 2; take precedence over allow rules). The following hooks are deployed for the Dispatcher:
   - `block-dispatcher-out-of-scope.sh` — restricts Edit/Write targets to `.dispatcher/`, `.state/`, and `knowledge/raw/YYYY-MM-DD-{topic}.md`. Direct edits to application code (`tools/`, `dashboard/`, `tests/`, `.claude/skills/`, `docs/`, `registry/`, etc.) are blocked with exit 2
   - `block-git-push.sh` — forbids direct push from the Dispatcher (push goes through the Lead)
   - `block-dangerous-git.sh` — blocks `git push --force` / `git reset --hard` / `git branch -D`
   - `block-workers-delete.sh` — blocks recursive deletion of the workers directory
   - `block-no-verify.sh` — blocks `--no-verify`-style verification bypasses
3. **Self-discipline through the role contract** (the business-scope declarations in the Dispatcher's `CLAUDE.md`, plus lifecycle oversight by the Lead)

Layer (2) — PreToolUse hooks — does run under bypass, so history-rewriting commands like `git push --force` and unintended writes into application code are technically blocked. That said, hooks loose-match against Bash command strings, so they don't catch every extreme workaround such as function definitions or routing through shell variables — which is why "self-discipline through the role contract" remains a complementary necessity. Honest framing: "multiple layers of net are stacked, but each layer has wide gaps."

**Alternative**: each role gets a `settings.local.json` distributed via `/org-setup`, with `tools/role_configs_schema.json` as the canonical source. Allow entries and required hooks are registered in the schema, and CI (`tools/check_role_configs.py`) detects drift. The Dispatcher's `bypassPermissions` exception will be re-evaluated as soon as `auto` mode becomes available on Sonnet.

---

## 2. We don't ship a fixed pool of pre-defined roles (front-end / back-end / QA agents, etc.)

**What we don't do**: provide a pre-defined pool of "front-end agent", "back-end agent", and similar role archetypes.

**Why**: claude-org generates **per-task** working directories and `CLAUDE.md` files freshly each time. A pre-baked role pool assumes "the role is decided before the task arrives", which conflicts with our discipline of remaking the environment per task. Even within "front-end work", the required permissions and context vary by repository, branch, and verification depth; reusing a stock role tends to produce contextual drift.

**Alternative**: `/org-delegate` derives a Worker per task and writes a task-specific `CLAUDE.local.md` into its working directory. If you want to repeat **routine tasks**, factor them out as **work skills** rather than as roles (`/org-retro` → skill candidate queue → `skill-creator`).

---

## 3. We don't run massive parallelism (20+ agents)

**What we don't do**: farm-style operation in which 20–100 agents run in parallel and each tries the same task.

**Why**: claude-org sits in the **3–5 Workers / quality-first** position. Massive parallelism is a "swing for hits at scale" approach that produces more pull requests and commits than human reviewers can keep up with. From the operational-discipline viewpoint — rollback, reproducibility, knowledge accumulation — keeping the Worker count small and reviewing via `/org-retro` is what makes the self-improvement loop spin.

**Alternative**: the Dispatcher today can spawn multiple Workers concurrently, but treat 3–5 as the peak guideline. If you want to handle a large batch of similar tasks, don't multiplex Workers — bundle the tasks into a single Worker and follow progress through the journal.

---

## 4. We don't generate project scaffolds from natural language (auto-create app)

**What we don't do**: features that accept "build me a Twitter clone" and generate a project scaffold from natural language.

**Why**: claude-org is an operational-discipline framework, not a scaffold generator. Scaffold generators shorten "the first five minutes"; claude-org's main field — "maintaining discipline over the long run of operation" — is a different concern. Mixing the two into a single tool blurs both responsibilities.

**Alternative**: if you need a scaffold, use the dedicated tool (`create-react-app`, `cargo new`, `npm init`, etc.), then start operating it with claude-org afterwards.

---

## 5. We don't switch between providers (Aider / Codex / Gemini, etc.)

**What we don't do**: make non-Claude language models (OpenAI / Gemini / DeepSeek, etc.) interchangeable as the primary Worker.

**Why**: claude-org takes a **Claude-only** stance. Multi-provider support is appealing on paper, but each provider has a different permission model, hook mechanism, MCP-server compatibility, context-window shape, and tool-call spec — and "the framework enforces discipline" thins out by exactly the number of providers you support. Going all-in on Claude Code is what lets us fully exploit Claude-Code-native discipline: the `renga-peers` MCP server, hooks, configuration schemas, sandboxing, and so on.

**Alternative**: bringing in another provider as an **optional review hook** — for example via `codex:rescue` or a `codex` self-review gate — for review or second-opinion purposes is in scope (a complement, not a star). If you want to swap providers in the primary role, a provider-agnostic agent framework (Aider / LangGraph / CrewAI, etc.) is the better fit.

---

## 6. We don't host a PTY or terminal-multiplexer layer

**What we don't do**: keep low-level implementations such as pseudo-terminal (PTY) control, pane splitting, or keystroke injection inside this repository.

**Why**: PTY and terminal-multiplexing concerns are separated into **Layer 3 = `renga`** (`suisya-systems/renga`). claude-org is Layer 4, "the operational layer that drives Claude Code as-is", and defers low-level terminal control to the dependency. Hosting both in one repository would cause the operational-discipline track and the PTY-fix track to interfere, slowing release cadence.

**Alternative**: pane operations, structured pane spawning, and peer communication go through the `renga-peers` MCP server (provided by Layer 3, 14 tools).

---

## 7. We don't ship a benchmark suite (SWE-Bench scores, etc.)

**What we don't do**: features that run agent-benchmark suites and publish scores.

**Why**: claude-org is not an agent-performance benchmarking framework. We do care about **whether the operational logic is correct** — "did the Lead's instruction get carried out by the Worker the way it should have?", "did raw notes graduate to curated knowledge correctly?" — but "what score Claude Code gets on a benchmark" is an evaluation of Claude Code itself, outside claude-org's scope.

**Alternative**: use Anthropic's published numbers or dedicated OSS (`swe-bench`, etc.) for SWE-Bench, HumanEval, and the like.

---

## 8. We don't ship a stack-by-stack prompt template library

**What we don't do**: bundle stack-specific prompt template libraries ("Next.js prompts", "Rails prompts", "Django prompts", etc.) with this framework.

**Why**: claude-org's design centers on **building project-specific context**. The repository-level `CLAUDE.md` and the per-task `CLAUDE.local.md` are the canonical context; stack-by-stack prompts tend toward "lowest-common-denominator generic text" and dilute project-specific context.

**Alternative**: if you want a stack-specific prompt, write it into the project's own `CLAUDE.md`, or reference an external prompt library (Awesome-Prompts-style) separately.

---

## 9. We don't adopt the `tools` front-matter form for permission declarations

**What we don't do**: an official form in which a skill or agent definition file declares tool permissions per-file via front matter such as `tools: [Read, Edit, Bash]`.

**Why**: claude-org controls permissions per task via **`settings.local.json` plus deny hooks**. A front-matter declaration is static and can't express the dynamic boundary of "which Worker, when, in which working directory". The same skill needs different permissions in different tasks, so we make the decision dynamic on the role × task axes.

**Alternative**: when you need to extend tool permissions, update `tools/role_configs_schema.json` (the propagation order is schema → `permissions.md` → actual `settings.local.json`). For drift handling see the `tools/check_role_configs.py` section in [docs/getting-started.md](getting-started.md).

---

## 10. We don't allow cross-cutting access via `--add-dir` by default

**What we don't do**: let a Worker freely access locations outside its own working directory (other Workers' working trees, the home directory outside the repo, etc.).

**Why**: claude-org treats **the working-directory boundary as a hard boundary**. Sharing trees or state across Workers introduces concurrent-work conflicts and accidents like overwriting another Worker's commits. Every relaxation of the boundary increases the cost of tracking "who saw what".

**Alternative**: anything that genuinely needs to be shared belongs in Lead-managed areas such as `knowledge/curated/` or `registry/`, and is rewritten only via the Dispatcher or the Lead.

---

## 11. We don't reimplement the bundled official skills (`/simplify`, etc.)

**What we don't do**: rebuild the functionality of skills bundled with Claude Code (`simplify` / `init` / `review` / `security-review`, etc.) inside claude-org.

**Why**: we lean on the official skills. Reimplementing them costs follow-up effort each time the official versions update, and from a user's standpoint it becomes hard to tell "what's different from official". claude-org's scope is limited to the operational-discipline layer that the official skills don't cover.

**Alternative**: use the official skills directly. Only when an organization-context wrapper around an official skill is needed do we wrap it thinly under the `/org-*` family (e.g. `/org-retro` is a retrospective wrapper organized for the org).

---

## 12. We don't expose MCP over HTTP for external integrations

**What we don't do**: expose an MCP server over HTTP so it can be reached from a browser extension or an IDE on a different machine.

**Why**: claude-org's MCP server is consolidated into `renga-peers` (over local stdio), and the canonical communication model is **same-tab P2P**. An HTTP exposure brings in a separate layer of concerns — auth, rate limiting, TLS, network boundary — and breaks the simple guarantee of "operational discipline that completes locally".

**Alternative**: monitor from another machine or another tab via the state files (`.state/`) and the dashboard (`/org-dashboard`). If real-time external integration is needed, you can stand up an additional HTTP MCP server alongside, but that responsibility lies outside claude-org proper.

---

## Revision history

- 2026-04-27: Initial version (split out alongside the README rewrite in Issue #107)
