# Intentionally Omitted Features (Non-goals)

claude-org is an **operations-discipline framework** focused specifically on running an organization on Claude Code. This document explicitly lists features that "might look convenient, but are intentionally excluded by design philosophy." Proactively stating what is absent is how the framework communicates its boundaries and value clearly.

> The README summarizes only the five strongest points. This document is the detailed version and covers all 12 items.

---

## 1. Do not default Workers to `--dangerously-skip-permissions`

**What we do not do**: Distribute Claude Code's fully prompt-bypassing `--dangerously-skip-permissions` (`permission_mode="bypassPermissions"`) as the default for Workers that perform real work, or for the Leads that instruct them. We do not adopt an operating model that enables bypass uniformly across all roles.

**Why**: claude-org centers on **narrow permission entries + defense in depth**. If roles that do real work get full permission-boundary bypass, the system can no longer stop the highest-severity organizational failures in advance, such as `git push --force` or reading `.env`. This is the opposite direction from fully automated farm-style systems. We do not allow dangerous operations to run invisibly outside human awareness.

That said, claude-org is designed to **use different permission modes intentionally by role**. Claiming "all roles run in `auto` mode" would be inaccurate, so the actual model is stated here directly:

| Role | `permission_mode` | Model | Notes |
|---|---|---|---|
| Lead | `auto` | Opus | Protected by narrowed permission entries in `settings.local.json` plus PreToolUse hooks |
| Dispatcher | `bypassPermissions` | Sonnet | **Exception**. Reason below |
| Curator | `auto` | Sonnet | Minimal permissions (mostly read, plus only writes needed for knowledge organization). Knowledge curation is a lightweight/mechanical workload, so Sonnet suffices |
| Worker | `auto` | Opus | Narrowed permission entries + role-specific hooks + per-task working-directory boundaries |

The reason only the Dispatcher is fixed to `bypassPermissions` is that `auto` mode's safety classifier judges "child agent launch" (worker dispatch via `spawn_claude_pane`) as "Create Unsafe Agents" and blocks it, so worker dispatch cannot succeed under `auto`. The classifier runs on a dedicated model independent of the session model (https://www.anthropic.com/engineering/claude-code-auto-mode), so this is a constraint orthogonal to the model choice (Sonnet operation) — it is not a convenient evasion of classifier behavior, but the only available choice given that the Dispatcher's job (launching child agents) structurally conflicts with `auto`.

### Actual behavior of `bypassPermissions` (no euphemisms)

As the name implies, `bypassPermissions` bypasses **both** `permissions.allow` and `permissions.deny`. In other words, deny rules such as `git push --force` listed in `permissions.deny` **do not apply on the Dispatcher side**. The only prompts Claude Code still keeps in bypass mode are write-confirmation prompts for protected directories such as `.git/`, `.claude/`, `.vscode/`, `.idea/`, and `.husky/`.

So the Dispatcher's effective defense layers are:

1. **Automatic confirmation prompts for protected directories** (only the scope Claude Code itself preserves even under `bypassPermissions`)
2. **PreToolUse hooks** (these still run under `bypassPermissions`, and can block tool calls with exit code 2; they take precedence over allow rules). The following hooks are already deployed for the Dispatcher:
   - `block-dispatcher-out-of-scope.sh` — Restricts Edit/Write targets to `.dispatcher/`, `.state/`, and `knowledge/raw/YYYY-MM-DD-{topic}.md`. Direct edits to application code (`tools/`, `dashboard/`, `tests/`, `.claude/skills/`, `docs/`, `registry/`, etc.) are blocked with exit 2
   - `block-git-push.sh` — Prohibits direct push from the Dispatcher (push goes through the Lead)
   - `block-dangerous-git.sh` — Blocks `git push --force`, `git reset --hard`, and `git branch -D`
   - `block-workers-delete.sh` — Blocks recursive deletion of the workers directory
   - `block-no-verify.sh` — Blocks verification bypass via `--no-verify`-style flags
3. **Self-discipline through the role contract** (the declared scope of work in the Dispatcher's `CLAUDE.md`, plus lifecycle monitoring by the Lead)

Because PreToolUse hooks in (2) remain active even in bypass mode, history-rewriting commands such as `git push --force` and accidental writes to application code are still technically blocked. However, hooks are only loose matches against Bash command strings and do not catch extreme evasions through function definitions or shell variables. In that sense, "self-discipline based on the role contract" is still a necessary complement. Put plainly: there are multiple overlapping nets, but each net has coarse holes.

**Alternative**: For each role, use the merged schema from the `claude-org-runtime` framework schema and the ja-side `tools/org_extension_schema.json` as the canonical source, and distribute `settings.local.json` through `/org-setup`. Permission entries and hooks are registered in the schema, and CI (`tools/check_role_configs.py`) detects configuration drift. The Dispatcher `bypassPermissions` exception itself will be re-evaluated once `auto` mode's classifier stops blocking child-agent launches (worker dispatch).

---

## 2. Do not provide a fixed role pool (frontend / backend / QA agents, etc.)

**What we do not do**: Provide a pre-defined role pool such as "frontend agent" or "backend agent."

**Why**: claude-org is designed to generate a working directory and `CLAUDE.md` **per task**. A pre-defined role pool assumes the role is decided before the task arrives, which conflicts with per-task discipline, where the environment is rebuilt for each task. Even for the same "frontend work," the required permissions and context differ by repository, branch, and validation depth. Reusing standardized roles makes context drift more likely.

**Alternative**: `/org-delegate` derives a Worker per task and generates `CLAUDE.local.md` (a task-specific instruction file) inside that working directory each time. If you want to handle "standardized tasks," extract them as **work skills**, not roles (`/org-retro` → skill candidate queue → `skill-creator`).

---

## 3. Do not run large-scale parallelism (20+ agents)

**What we do not do**: Adopt a farm-style model that runs 20 to 100 agents in parallel, each exploring the same task by trial and error.

**Why**: claude-org targets **3 to 5 Workers with a quality-first bias**. Large-scale parallelism is an approach of brute-forcing with volume and winning if even one path hits. It produces more pull requests and commits than a human reviewer can realistically track. From the perspective of operational discipline, rollback, reproducibility, and knowledge accumulation, limiting the number of Workers and reflecting through `/org-retro` creates a sustainable self-improvement loop.

**Alternative**: The current Dispatcher can spawn multiple Workers concurrently, but even at peak, use 3 to 5 as the practical upper bound. If you want to process many similar tasks in bulk, it is better to give the batch to one Worker and track progress through the journal than to multiply Workers.

---

## 4. Do not generate project scaffolds from natural language (Auto-create app)

**What we do not do**: Provide a feature that generates a project scaffold from natural language, such as "build a Twitter clone."

**Why**: claude-org is an operations-discipline framework, not a scaffold generator. Scaffold generation is a tool for shortening the first five minutes. claude-org's primary field is maintaining discipline in long-term operation, which is a different concern. Mixing both into one tool blurs the responsibility of each.

**Alternative**: If you need scaffolding, use dedicated tools such as `create-react-app`, `cargo new`, or `npm init`, then start organizational operation with claude-org afterward.

---

## 5. Do not support multi-provider switching (Aider / Codex / Gemini, etc.)

**What we do not do**: Allow non-Claude Code language models (OpenAI / Gemini / DeepSeek, etc.) to be swapped in as primary Workers.

**Why**: claude-org is positioned as **Claude-only**. Multi-provider support looks attractive, but permission models, hook mechanisms, MCP server compatibility, context-window shape, and tool-calling specifications all differ by provider. The more providers you support, the weaker the framework's core property of enforcing discipline becomes. By integrating deeply with Claude Code, claude-org can fully use Claude Code-native discipline mechanisms such as the `renga-peers` MCP server, hooks, configuration schemas, and sandboxing (the transport layer is two-track: both the default `renga-peers` and the opt-in `org-broker` are Claude Code-native transports, and the "deep integration" benefit applies to both; for the two-frame view of the transport, see the §12 host-local exception).

**Alternative**: Calling other providers as **optional review hooks** is in scope only for review or second-opinion use cases, such as `codex:rescue` or a `codex` self-review gate. They are assistants, not the primary system. If you want to use multiple providers as first-class workers, a general-purpose agent framework such as Aider, LangGraph, or CrewAI is a better fit.

---

## 6. Do not include a PTY or terminal-multiplexer layer

**What we do not do**: Carry low-level implementations such as pseudo-terminal (PTY) control, pane splitting, or keystroke injection in this repository.

**Why**: The PTY and terminal-multiplexing layer is separated into **Layer 3 = `renga`** (`suisya-systems/renga`) (here `renga` refers to Layer 3 in the **default operational frame**. The transport layer is two-track: with the opt-in `broker`, the runtime-bundled `org-broker` covers the same Layer 3. Both tracks coexist with rollback available; see the §12 host-local exception). claude-org is Layer 4, the operational layer that drives Claude Code directly, and delegates low-level terminal control to its dependency. If both layers live in the same repository, operational-discipline changes and PTY-layer bug fixes interfere with each other and slow release velocity.

**Alternative**: Use the `renga-peers` MCP server (provided by Layer 3, 14 tools) for pane operations, structured pane creation, and peer communication (default operational frame; when the opt-in `broker` is selected, `mcp__org-broker__*` provides an equivalent surface).

---

## 7. Do not include a benchmark suite (SWE-Bench scores, etc.)

**What we do not do**: Provide benchmark execution or score publishing for agent-performance comparison.

**Why**: claude-org is not an agent-performance comparison framework. It does care about the **correctness of operational logic**, such as whether Lead instructions were executed correctly by Workers, or whether raw knowledge was promoted properly into curated knowledge. But "what score Claude Code gets on a benchmark" is an evaluation of Claude Code itself, outside claude-org's scope.

**Alternative**: For standard benchmarks such as SWE-Bench or HumanEval, use Anthropic-side evaluation or dedicated OSS such as `swe-bench`.

---

## 8. Do not bundle stack-specific prompt templates

**What we do not do**: Ship framework-specific prompt template collections with the framework, such as templates for Next.js, Rails, or Django.

**Why**: claude-org is designed around **project-specific context construction**. `CLAUDE.md` and the working directory's `CLAUDE.local.md` are the project-specific canonical sources. Stack-specific prompts tend to collapse into generic common-denominator text and dilute project-specific context.

**Alternative**: If you need stack-specific prompts, write them in the project's `CLAUDE.md` or refer separately to external prompt collections.

---

## 9. Do not use a `tools` frontmatter permission-declaration format

**What we do not do**: Provide an official format where tool permissions are declared per file in frontmatter, such as `tools: [Read, Edit, Bash]` in skill or agent definition files.

**Why**: claude-org controls permissions **per task through `settings.local.json` + deny hooks**. Frontmatter-style permission declarations are static and cannot express dynamic boundaries like which Worker is acting, when, and in which working directory. Even with the same skill, permission boundaries change by task, so the design decides them dynamically across two axes: role and task.

**Alternative**: If you need to add tool permissions, update `tools/org_extension_schema.json` for ja-specific entries. The framework schema itself is the SoT in the `claude-org-runtime` package, and the rule-addition flow is schema → documentation → actual `settings.local.json`. For drift-remediation procedure, see the `tools/check_role_configs.py` section in [docs/getting-started.md](getting-started.md).

---

## 10. Do not allow cross-boundary access via `--add-dir` by default

**What we do not do**: Allow Workers to freely access locations outside their own working directory, such as another Worker's work area or a home directory outside the repository.

**Why**: claude-org treats the **working-directory boundary as an enforced boundary**. If Workers share working trees or state, concurrent work creates conflicts and risks accidentally overwriting another Worker's commit. Every time the boundary is loosened, the cost of tracking who saw what increases.

**Alternative**: Put shared information in Lead-managed areas such as `knowledge/curated/` or `registry/`, and update it only through the Dispatcher or Lead.

---

## 11. Do not reimplement officially bundled skills (such as `/simplify`)

**What we do not do**: Reimplement features from Claude Code's officially bundled skills (`simplify`, `init`, `review`, `security-review`, etc.) on the claude-org side.

**Why**: The policy is to build on top of official skills. Reimplementation adds follow-up cost every time the official version changes, and from the user's perspective it becomes unclear what differs from the official version. claude-org keeps its scope limited to the operations-discipline layer that the official system does not provide.

**Alternative**: Use official skills as they are. Only when you need a wrapper that invokes an official skill in an organizational-operations context should it be wrapped lightly as an `/org-*` command (for example, `/org-retro` is an organizational wrapper for retrospectives).

---

## 12. Do not provide external integration through MCP-over-HTTP

**What we do not do**: Expose the MCP server externally over HTTP so that browser extensions or IDEs on other machines can connect.

**Why**: In the default operational frame, claude-org's MCP server is consolidated into `renga-peers` (over local stdio), and **same-tab P2P** is the canonical communication model (the opt-in `broker`'s `org-broker` is a **localhost-only** HTTP MCP bound to `127.0.0.1` and is also not "externally exposed"; see the host-local exception below). Exposing it **externally** over HTTP would introduce a different layer of concerns such as authentication, traffic control, TLS, and network boundaries, breaking the simple guarantee of local-only operational discipline.

**Alternative**: For monitoring from another machine or another tab, use state files (`.state/`) and the dashboard (`/org-dashboard`). If real-time external integration is required, you can design a separate MCP HTTP server alongside it, but that is outside the responsibility of claude-org itself.

> **Host-local exception (proposed, 2026-06-11 / Epic #6 / ja#514, pending ratification)**: this non-goal prohibits **external exposure**; an MCP HTTP server **closed to the host only** is out of scope (an exception). The **`org-broker`** used under `ORG_TRANSPORT=broker` (opt-in) is a localhost-only HTTP MCP server bound to `127.0.0.1` — it is not externally reachable, has no TLS / network-boundary / external-auth surface, and does not break the "local-only operational discipline". Therefore broker is not the prohibited target of §12 (external exposure); it is permitted as part of the local transport layer. The default `renga-peers` (over local stdio, same-tab P2P) is unchanged, and this exception is purely an **additive** clarification that only adds broker on an opt-in basis (proposed; ratification follows the Epic #6 dogfood gate). For contractual details see [`docs/contracts/backend-interface-contract.md`](./contracts/backend-interface-contract.md) Surface 8 (§8.6).

---

## Revision history

- 2026-04-27: Initial version (split out alongside the full README rewrite in Issue #107)
- 2026-06-11: Added a host-local MCP HTTP exception note to §12 as a **proposal (pending ratification)** (Epic #6 / ja#514). Clarifies that `org-broker` (localhost-only HTTP MCP, opt-in) is out of scope of the external-exposure prohibition. The description and communication model of the default `renga-peers` are unchanged.
---
