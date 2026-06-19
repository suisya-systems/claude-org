# renga decoupling (Plan B) -- org-broker / terminal adapter design

> Status: **design only / no implementation**. No implementation of this design exists in this repository. Experiments will be conducted in a fork, and the broker / adapter substance is planned to live on the claude-org-runtime side.
> This document describes "an unimplemented future design", and all of the descriptions below are **proposals / plans**. For the contrast with current behavior (via renga), see [§2 "Relationship between the current state and this design"](#2-relationship-between-the-current-state-and-this-design).
> Primary inputs: user / secretary design-agreement notes (2026-06-07, the uncommitted operational note `notes/renga-decoupling-design-input-2026-06-07.md`), and a Codex design review (same day, uncommitted note under `tmp/`). Both are outside git management and cannot be referenced from this branch, but **the constraints and agreements settled there are transcribed into [§1](#1-background-and-settled-constraints-premises-this-design-does-not-overturn) as body text**, so this design document is readable on its own. This design does not overturn any of those settled constraints.
> Dependent documents (references go one-way only from this design document to existing documents; no reverse references will be added from the existing documents back to this design):
> - [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) (Contract Set D, ratified 2026-05-03. The foundation of this design)
> - [`docs/contracts/state-semantics-contract.md`](../contracts/state-semantics-contract.md) (Set F. The canonical reference for state.db SoT)
> - [`docs/contracts/state-schema-contract.md`](../contracts/state-schema-contract.md) (Set C. The `.state/` file ledger)
> - [`docs/non-goals.md`](../non-goals.md) (especially §6 PTY layer, §12 HTTP external exposure)
> - [`docs/design/core-harness-extraction.md`](./core-harness-extraction.md) (precedent for the design-only header and layer separation)

---

## 1. Background and settled constraints (premises this design does not overturn)

The following 3 points are constraints already settled between user and secretary, and this design is constructed within this frame.

1. **Billing constraint -- headlessification does not hold**: From 2026-06-15, use of `claude -p` / the Agent SDK is charged to a separate "Agent SDK monthly credit" pool (USD 200/month at Max 20x) distinct from interactive use, with overage billed as API metered usage (sources: code.claude.com/docs/en/headless, support.claude.com article 15036540). With this organization's worker usage, overage is certain, so **all agents remain interactive TUI sessions**. The plan to headlessify agents and thereby eliminate the renga dependency is rejected at this point.
2. **IME constraint -- bare WezTerm does not hold**: Even with a single pane, Claude Code's spinner rendering (such as "Cogitated...") steals the IME conversion window's anchor (user-measured). renga solves this with hardware-cursor caret control. Therefore **the terminals where humans type Japanese (the secretary pane) continue to use renga**. The plan to "eliminate renga and go back to bare WezTerm" is also rejected at this point.
3. **Adoption policy = Plan B**: A plan to make **only** the organization's transport layer (messaging / spawn / observation) renga-independent via org-broker + terminal adapter, and demote renga from "a mandatory prerequisite the organization requires" to "the user's terminal choice". The fallback for renga failure is the WezTerm backend. **Eliminating renga is not the goal**.

The approach is also agreed: the thin diffs of rewiring (`mcp__renga-peers__*` -> broker tools) will be **experimented with in a fork**, and on success they will be absorbed back into the main repo in phase units (messaging -> pane operations). The actual code of the broker daemon + terminal adapter will live in claude-org-runtime (an existing separate package) or a new repository, and will not be brought into this repository (consistent with [`docs/non-goals.md`](../non-goals.md) §6 "we do not own a PTY or terminal multiplexer layer"). Pythonization of the dispatcher's deterministic processing is **out of scope for this design** (listed only as a future item, [§9](#9-out-of-scope-future-work)).

## 2. Relationship between the current state and this design

**Current behavior (implemented, in operation)**: This repository's organizational operation runs with the renga-peers MCP server (renga 0.18.0+, 14 tools) as the sole transport layer. Inter-agent messaging uses renga's channel injection (in-band delivery of `<channel source="renga-peers">`), and pane operations / observation use `spawn_claude_pane` / `list_panes` / `inspect_pane` / `send_keys` / `poll_events` / `close_pane` etc. This current surface is ratified as the abstract backend contract in [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) (Set D).

**This design (unimplemented proposal)**: A plan to replace the transport layer with an org-broker daemon + terminal adapter. No broker / adapter implementation exists in this repository, and the current prose and code in `.claude/skills/` / `.dispatcher/` / `tools/` continue to call renga-peers. Until experiments in the fork succeed and pass the phase-by-phase absorption decisions ([§7](#7-phase-plan-and-migration-completion-criteria)), the behavior of the main repo does not change at all.

| Aspect | Current (via renga, implemented) | Proposed (via broker, unimplemented) |
|---|---|---|
| Message delivery | renga server injects via channel (in-band push to Claude, nudge + pull to Codex) | Plan to store in the broker queue store and **convert all agents to pull** (single-line nudge injection + `check_messages`) |
| Sender attribution | renga server attributes `from_id` / `from_name` from pane origin | Plan for broker to attribute from **per-agent token** (same point: not self-asserted) |
| Pane operations | All roles can access the same MCP server's tools (narrowed by permission schema) | Plan to expose only the messaging surface to worker / curator, and keep pane operations to broker internals + minimal exposure to dispatcher / secretary ([§4.2](#42-broker-mcp-surface-per-role-exposed-surface)) |
| Agent connection | Inject `--dangerously-load-development-channels server:renga-peers` at spawn + approval prompt | Plan to inject the broker MCP (localhost HTTP) via `--mcp-config` at spawn ([§4.6](#46-replacement-of-the-startup-flow)) |
| Terminal backend | renga required | Plan to make renga / WezTerm swappable via adapter (default for human-input terminals is renga continued) |
| Human Japanese input | renga's hardware-cursor caret control | No change (renga continues. broker does not touch this layer) |

## 3. Inventory of `mcp__renga-peers__*` call sites

As a preview of Phase 2 (inventory and contract alignment), all references in the repository are fixed into 3 categories (as of 2026-06-07, full census by `grep -rE "mcp__renga-peers__"`). **Only category (a) is the rewiring target**; (b) is a re-declaration in permission schemas, and (c) is updated as documents follow.

### 3.1 Category (a): operational call descriptions (rewiring target)

Descriptions written in role prose / skills that actually fire as MCP calls at runtime. The matrix of caller (role) x tool:

| Tool | secretary | dispatcher | curator | worker |
|---|---|---|---|---|
| `send_message` | ● ack / instruct / forward / suspend notice (`CLAUDE.md`; entry points: org-delegate / org-escalation / org-pull-request / org-suspend / org-retro / skill-audit / dispatcher-handover) | ● escalate / DELEGATE_COMPLETE / nudge / retro gate (`.dispatcher/CLAUDE.md`; spawn-flow / worker-monitoring / pane-close) | ● CURATE_DONE etc. report (`.curator/CLAUDE.md`; org-curate) | ● completion / progress / escalation report (worker brief template family) |
| `check_messages` | ● CI_COMPLETED reception (org-pull-request), drain on suspend / resume | ● worker self-report reception in monitoring loop | -- | -- (reception is via renga's in-band push) |
| `list_peers` | ● peer confirmation at startup / resume | ● waiting for worker registration (spawn-flow 3-4) | -- | ● (auto-discovery of secretary; written in brief) |
| `list_panes` | ● startup / suspend / attention series | ● balanced split input / monitoring reconcile | -- | -- |
| `inspect_pane` | ● dispatcher prompt poll (handover path), org-delegate Step 5 intervention | ● approval-pending / stall observation (worker-monitoring) | -- | -- |
| `send_keys` | ● dispatcher `/clear` -> `/dispatcher-resume` keystrokes, dev-channel approval, Esc intervention | ● dev-channel approval (spawn-flow 3-3b), Shift+Tab / Ctrl+C intervention | -- | -- |
| `poll_events` | ● pane_exited confirmation in org-suspend | ● pane_started / pane_exited monitoring (cursor persisted at: `.state/dispatcher-event-cursor.txt`) | -- | -- |
| `spawn_claude_pane` | ● dispatcher / curator startup (org-start), redispatch | ● worker spawn (spawn-flow 3-2), on-demand curator spawn | -- | -- |
| `spawn_pane` | ● attention watcher startup (org-attention-start) | -- | -- | -- |
| `close_pane` | ● org-suspend / org-attention-stop | ● CLOSE_PANE handling (pane-close), curator retirement | -- | -- |
| `set_pane_identity` / `set_summary` | ● org-start Step 0.3 self-repair, secretary-resume | ● dispatcher-resume | -- | -- |
| `focus_pane` / `new_tab` | (human-facing assistance; no mandatory calls in operational prose) | -- | -- | -- |

Main locations (operational documents containing call descriptions): `CLAUDE.md`, `.claude/skills/{org-start,org-delegate,org-escalation,org-pull-request,org-suspend,org-retro,org-curate,org-attention-start,org-attention-stop,secretary-resume,dispatcher-handover,dispatcher-resume,skill-audit}/SKILL.md`, `.claude/skills/org-delegate/references/{ack-template,instruction-template,pane-layout,renga-error-codes,worker-claude-template,claude-org-self-edit}.md`, `.dispatcher/CLAUDE.md`, `.dispatcher/references/{spawn-flow,worker-monitoring,pane-close}.md`, `.curator/CLAUDE.md`, `tools/templates/worker_brief_{normal,self_edit}.md`.

The scale of the rewiring inferred from this:

- **Worker / curator's required surface is minimal**: only `send_message` (plus `list_peers` for secretary discovery, and the `check_messages` equivalent for reception). They never call pane operations at all. -> It is likely that Phase 3 (messaging migration) alone is sufficient to make worker / curator independent of renga tools.
- **Pane operations are concentrated to dispatcher and secretary callers**: spawn / close / inspect / send_keys / poll_events are limited to these two roles. -> The impact scope of Phase 4 (pane-operation migration) is closed to the prose of these 2 roles.

### 3.2 Category (b): permission schemas / configuration declarations (not call sites)

Items that only enumerate tool names as allowlist entries. At rewiring time, re-declaration with broker tool names is needed:

- `.claude/settings.json` (allows 14 tools)
- `tools/org_extension_schema.json` (per-role allow declaration)
- `.claude/skills/org-setup/references/permissions.md` (schema documentation)

### 3.3 Category (c): documentation / comment / fixture references (not involved in behavior)

- Contracts / design / operations docs under `docs/` (`docs/contracts/backend-interface-contract.md` and others; `docs/getting-started.md`, `docs/verification.md`, `docs/operations/`, `docs/legacy/`, `docs/internal/` etc.)
- Docstring / comment references inside Python tools: `tools/dispatcher_retro_gate.py`, `tools/gen_delegate_payload.py`, `tools/peer_notify.py` (none of these are **code that calls MCP**. From a Python process you cannot reach MCP tools; they only generate / explain instruction text for Claude sessions)
- Test fixtures: `tools/test_org_setup_prune.py` (one entry as an allowlist string)

> Note: `send_plan.json` at the repository root (an uncommitted operational artifact) also contains references, but as it is outside git management it is excluded from the inventory.

## 4. Proposed architecture: org-broker + terminal adapter

### 4.1 Overall picture

```
                  (human)
                     | Japanese input continues on the renga pane (IME constraint)
   +-----------------+--------------------------------------------+
   | Terminal backend (renga / WezTerm on fallback; swappable via adapter) |
   |  +--------+ +-----------+ +--------+ +--------+              |
   |  |secretary| |dispatcher | |curator | |worker-*|              |
   |  +---+----+ +----+------+ +---+----+ +---+----+              |
   +------+-----------+-----------+----------+--------------------+
          | MCP (HTTP, localhost only, per-agent token)
          v           v           v          v
   +-------------------------------------------------+
   | org-broker daemon (planned implementation on the claude-org-runtime side) |
   |  - broker queue store (dedicated subtree at .state/broker/)               |
   |  - token issuance / attribution / role-scoped tool exposure               |
   |  - nudge delivery (single-line keystroke via terminal adapter)            |
   |  +-- terminal adapter (swappable) ----------------+                       |
   |  | renga adapter / WezTerm adapter / (tmux later) |                       |
   |  +------------------------------------------------+                       |
   +-------------------------------------------------+
```

- Each agent will be injected at spawn time with the broker's MCP server (localhost HTTP) via `--mcp-config`, and is planned to authenticate with a per-agent token.
- Sender attribution (`from`) is attributed by the broker from the token, and is not self-asserted (reproduction of renga's server-attribution model = forgery prevention).
- Pane operations (spawn / send-text / close / screen capture / events) are executed by the broker via the adapter. The adapter makes renga / WezTerm swappable.

### 4.2 broker MCP surface (per-role exposed surface)

In contrast to current renga-peers, which shows the same set of tools to all roles and narrows them with the permission schema (category (b)), the broker plans to **change tool exposure itself by the role scope of the token**. The aim is to **structurally** cut, not via the permission setting, the path where a prompt-injected worker would directly keystroke into the secretary pane (`send_keys`).

| Tool (proposed name) | worker / curator | dispatcher | secretary | broker internal only |
|---|---|---|---|---|
| `send_message` | o | o | o | |
| `check_messages` | o | o | o | |
| `list_peers` | o | o | o | |
| `set_summary` | o | o | o | |
| `list_panes` (with geometry) | -- | o | o | |
| `inspect_pane` (grid scrape) | -- | o | o | |
| `send_keys` (raw PTY) | -- | o | o | |
| `poll_events` (long-poll with cursor) | -- | o | o | |
| `close_pane` | -- | o | o | |
| `spawn_agent` (= current `spawn_claude_pane` equivalent) | -- | o | o | |
| `spawn_pane` (generic) | -- | -- | o (for attention watcher) | |
| `set_pane_identity` | -- | o | o | |
| nudge injection (internal mechanism for delivery) | -- | -- | -- | ● (not exposed as a tool) |

- **M1: minimum surface for dispatcher** is fixed as the surfaces required for correctness in the current contract (Set D REQUIRED `list_panes` (geometry) / `inspect_pane` / `send_keys`, and `poll_events` / `close_pane` that the monitoring loop depends on) + spawn family + messaging family. The dispatcher column above is that enumeration.
- **Key clarification**: This is not about "eliminating pane operations". Because nudge delivery itself requires send-text (raw keystroke) as an internal mechanism, **the broker becomes the trusted holder of pane operations and makes them unreachable only from worker / curator**; it is a redrawing of the boundary. Dispatcher / secretary retain pane operations as they are today (without them, monitoring, intervention, and suspend would not work).
- The secretary's exposed surface is held to be almost the same as the dispatcher's (because the org-start dispatcher startup, the attention watcher spawn/close, the `send_keys` + `inspect_pane` in the handover path, and the close/poll in org-suspend are all required by current operations. Corresponds to the [§3.1](#31-category-a-operational-call-descriptions-rewiring-target) inventory).
- renga's `focus_pane` / `new_tab` are human-facing assistance (also non-mandatory in Set D), and are **excluded** from the initial surface of the broker MCP in this proposal. They will be added if and when needed.

### 4.3 Interrupt delivery to the secretary (nudge; hardest part, subject to drop-out)

MCP is request-response and cannot push to a Claude session that is in conversation. As an alternative to renga's channel injection (in-band push), the following 2-stage approach is proposed:

1. **Nudge**: The broker keystrokes a fixed single line "New mail. Run check_messages" + Enter to the destination pane via the terminal adapter (for WezTerm, via `wezterm cli send-text`).
2. **Body retrieval**: The receiving side fetches the body via the broker's `check_messages`. **The body does not go through PTY** (this confines the risk of cross-talk from long text / control characters / multibyte characters to the fixed single-line nudge).

Design-side mitigations (to be verified in Phase 1):

- **Input-field quiescence check before injection**: Before the nudge keystroke, the broker confirms via grid scrape that the destination pane's input field is empty (prompt quiescent); if not, defer + retry. This is a known technique of the same form as the current dispatcher handover path (the procedure of polling for empty prompt at 1-second intervals after `/clear` before the next keystroke, documented in `CLAUDE.md`).
- **Nudge idempotency**: Because delivery is a "you have unread" notification rather than a body, repeated injection still consumes the queue once via `check_messages`. On miss, re-nudge recovers.

> **Drop-out clause**: If this mechanism does not meet the Phase 1 spike pass criteria ([§7.1](#71-phase-1-spike-wezterm--windows-stop-or-go-decision-point)), **the plan as a whole is shelved**. Nudge delivery is the condition for the existence of this entire design.

### 4.4 per-agent token lifecycle

The life of the token that grounds sender attribution and the role-scoped exposure surface is proposed as follows:

| Phase | Proposed behavior |
|---|---|
| **Issuance** | The broker generates one at the time it receives the spawn request, and issues it individually as an environment variable at spawn (settled in primary input). The connection settings passed via `--mcp-config` reference this env. The token is bound to `{agent_id, role, pane_id, session_id}` |
| **Bind** | The token <-> pane/session correspondence table is held only by the broker. The `from` attribution / role scope decision / destination resolution are all derived from this bind table, and no client self-assertion is taken |
| **Revoke (pane retirement)** | Immediate revoke upon adapter `pane_exited` event reception, and upon successful `close_pane` via the broker. Calls with the token of a retired pane are rejected with `token_revoked` error ([§5 Surface 6](#surface-6-error-code-vocabulary--inherited--newly-added)). Even if the env leaks to child processes, it is unusable after pane retirement |
| **TTL** | Issued with TTL (the default value will be decided after Phase 1 measurement. For long-running session operation, the basis is "TTL longer than session lifetime + revoke at retirement", with TTL positioned as insurance against revocation leaks) |
| **Suspend / resume** | All tokens are revoked on `/org-suspend` equivalents, and **reissued** by re-spawn at resume. Token reuse across a suspend is disallowed (to keep the bind table consistent with pane id variation at resume) |
| **Storage and leak surface** | Tokens exist only in host env / broker bind table, and are not written in cleartext to the queue store, logs, or journal. Child-process leakage via env is constrained in blast radius by revoke-on-exit + TTL + localhost bind (for stricter constraint, compare via temporary per-agent mcp-config files (0600) in Phase 1) |

### 4.5 broker queue store (dedicated subtree at `.state/broker/`)

The broker's write area is **restricted to the dedicated subtree at `.state/broker/`**, and this area is named "**broker queue store**" (the name "message store" is not used -- to avoid confusion with state.db).

- The broker queue store is **not state.db, and not the events table**. It is **kept from colliding** with the state.db SoT (runs / org_sessions / events / worker_dirs) defined in [`docs/contracts/state-semantics-contract.md`](../contracts/state-semantics-contract.md) (Set F), and with the file ledger in [`docs/contracts/state-schema-contract.md`](../contracts/state-schema-contract.md) (Set C). The broker does not write to state.db at all.
- The sole writer of the broker queue store is the broker daemon. Conversely, existing state writers (StateWriter / journal_append family) do not write to `.state/broker/`. Ownership is cut symmetrically by "one writer per subtree".
- Contents (proposed): pending-delivery queue, delivered cursor, token bind table (or bind held in-memory + reconstructed on restart), nudge delivery attempt log. The format (separate SQLite file `queue.db` vs. JSONL) will be decided at implementation time.
- If audit events (e.g., delivery-failure escalation) need to be recorded into the organization's journal, the broker does not write directly; the **operational side** that invokes the existing sanctioned writer (`tools/journal_append.*`) does the recording. The broker's responsibility is restricted to transport.
- **Set C revision is required**: Because [`docs/contracts/state-schema-contract.md`](../contracts/state-schema-contract.md) (Set C) covers the entire persistent file group under `.state/` as the contract subject, "not colliding" is not enough; the **establishment of the `.state/broker/` subtree itself is an addition revision to Set C's state files inventory (path / format / owner=broker / readers / migration)**. The contract revision PR at Phase 3 absorption time will include the Set C revision ([§7.3](#73-phase-3-messaging-migration-messaging-adapter)). This design document is the revision proposal; it does not modify the Set C body itself.

### 4.6 Replacement of the startup flow

Contrast between the current canonical path (`.dispatcher/references/spawn-flow.md` Steps 3-2 through 3-5) and the proposal:

| Stage | Current (renga, implemented) | Proposed (broker, unimplemented) |
|---|---|---|
| 1. spawn | `spawn_claude_pane(...)` -- renga synthesizes `--dangerously-load-development-channels server:renga-peers` | The dispatcher calls the broker's `spawn_agent(...)` -> the broker issues a token and spawns the pane via the adapter. The plan is to synthesize `--mcp-config <broker connection settings>` (+ `--strict-mcp-config` if needed) into the Claude startup args |
| 2. Startup confirmation | Waits up to 3 seconds for `pane_started` via `poll_events` | Equivalent (the broker's `poll_events` normalizes adapter events and returns them) |
| 3. Channel approval | `send_keys(enter=true)` approves the "Load development channel?" prompt | **The dev-channel prompt does not exist** (because the dev-channel flag is not used). The presence/absence of the Claude Code trust-confirmation prompt against the server injected via `--mcp-config` is a **Phase 1 measurement item**. If a prompt appears, leave the `send_keys(enter=true)` approval as today in the after_spawn column |
| 4. Registration wait | Retry every 2 seconds (up to 30 seconds) until the worker appears in `list_peers` | **Canonical path preserves the same form as today**: when the worker-side Claude's MCP client connects to the broker (initialize handshake), the broker transitions the bind table to "registered", and the dispatcher waits via the same poll as the current 3-4 until the worker appears in the broker's `list_peers` (bind table-based). As an auxiliary, the broker emits an `agent_ready` event and provides a latency-improving alternative path that waits via `poll_events` (optional. The canonical wait is `list_peers` poll, and does not depend on `agent_ready`) |
| 5. Instruction send | `send_message(to_id="worker-{task_id}", ...)` -- renga channel-injects | `send_message` -> broker queue store enqueue -> nudge delivery (the worker, just after startup, has an empty input field; the quiescence check passes immediately as assumed) -> the worker fetches the body via `check_messages` |

With the dev-channel prompt's disappearance, the coupling between current spawn-flow 3-3b (Enter approval) and "list_peers wait times out unless approved" is expected to be resolved, while a new unknown of "trust confirmation of MCP server connection" enters. **The successful establishment of the replacement of stages 1, 3, 4 (spawn -> connect -> attribute -> deliver one round trip) is Phase 1 spike pass criterion AC-2** ([§7.1](#71-phase-1-spike-wezterm--windows-stop-or-go-decision-point)). If a ritual equivalent to 3-3b / 3-4 cannot be replaced and remains, do not proceed to Phase 2 or later.

### 4.7 Terminal adapter boundary and capability table

The adapter is **defined as 2 different things in two stages: "messaging adapter (minimum capability required by Phase 3)" and "full backend adapter (full capability required by Phase 4)"**. The claim "anything is swappable via adapter" is not made -- per-backend capability differs, and as shown in the table below some differences are unfillable.

| Capability | renga | WezTerm (`wezterm cli`) | tmux (future, reference) | Required phase |
|---|---|---|---|---|
| send-text to pane (nudge injection) | o `send_keys` | o `send-text` | o `send-keys` | **Phase 3 (messaging)** |
| Pane-identification stable-name management | o (name/role server-managed) | △ (only pane id. adapter holds name <-> id mapping) | △ (same) | **Phase 3 (messaging)** |
| split spawn (with cwd / command spec) | o | o `split-pane` | o `split-window` | Phase 4 |
| list_panes with geometry (cell-unit rect) | o | o `list --format json` (rows/cols/position) | o `list-panes -F` (pane_left/top/width/height) | Phase 4 |
| Grid scrape (`inspect_pane` equivalent) | o | o `get-text` | o `capture-pane` | Phase 4 |
| Scrape with cursor position | o (`include_cursor`) | △ (not via `get-text` alone. Requires separate retrieval; needs verification) | △ (combined with `display-message -p '#{cursor_x}'`) | Phase 4 |
| poll_events with cursor (lifecycle events) | o (long-poll + next_since) | x **No native event stream** -> adapter **synthesizes** `pane_started` / `pane_exited` from list polling (granularity / latency degrade) | △ (hooks partially cover) | Phase 4 |
| single-tab addressing (Set D §4.2 MUST) | o (server enforces) | △ (tab concept exists. adapter implements scope enforcement) | △ (similar at window unit) | Phase 4 |
| IME-safe caret (hardware cursor control) | o | x | x | **Out of scope** (the basis for the human-input terminal continuing with renga) |

- **Messaging adapter** (Phase 3): required capability is only "send-text + pane identification". renga / WezTerm / tmux can all satisfy it, so messaging migration is highly likely to be made backend-independent.
- **Full backend adapter** (Phase 4): The `poll_events` synthesis (WezTerm) entails degradation of event granularity / latency. Set D §3.1 tolerates cursor-loss with best-effort + `list_panes` reconcile (Q9), so **the polling synthesis does not violate the contract**, but the effective latency of the dispatcher monitoring loop increases relative to renga. Measure at the Phase 4 absorption decision ([§7.4](#74-phase-4-pane-operation-migration-full-backend-adapter)).
- WezTerm residency becomes a new prerequisite (the dependency-replacement aspect). However, because the adapter boundary exists, the secondary migration to tmux etc. is positioned as inexpensive.

## 5. Alignment with Contract Set D (diff table)

The position of this design with respect to [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) (ratified 2026-05-03) is fixed in Surface units. **This section is a "revision proposal", and does not modify the body of the ratified contract**. The execution of the revision is planned to be done separately as a formal contract-revision PR (the Set D amendment procedure) along with the phase absorption after the fork experiment succeeds. To avoid creating dual canonical sources, **the canonical source until the revision is ratified is the current Set D body**.

| Set D Surface | Class | Diff summary |
|---|---|---|
| Surface 1: Pane control (1.1-1.9) | **Inherit** (only the exposure boundary is the revision proposal) | The semantics of operations (spawn / close / list_panes geometry / inspect_pane / send_keys / set_pane_identity, error codes, idempotency) are all inherited. The change is only "to whom we show it": unreachable from worker / curator, restricted to dispatcher / secretary + broker internal ([§4.2](#42-broker-mcp-surface-per-role-exposed-surface)). The 1.2 dev-channel flag injection mandate is proposed to be replaced by `--mcp-config` injection mandate in coordination with the Surface 5 revision |
| Surface 2: Messaging (2.1-2.4) | **Revision proposal** (the largest change in this design) | Proposal to abolish 2.1's push-mode in-band delivery (channel injection to Claude) and **unify all receivers to pull-mode** (nudge + `check_messages`. Generalization of the current pull path to Codex). The attribution fields `from_id` / `from_name` / `sent_at` **inherit the semantics** (remaining HYBRID canonical), but the **attribution mechanism is revised**: from renga server's pane-origin attribution -> broker's token-origin attribution as planned. 2.2 `list_peers` / 2.3 `check_messages` (at-most-once drain) / 2.4 `set_summary` inherit semantics (only the implementation subject changes to broker) |
| Surface 3: Events (3.1) | **Inherit** | Cursor-based long-poll, the first-time "from now" semantics, the minimum event vocabulary (`pane_started` / `pane_exited` / `events_dropped`), the 30-second cap, best-effort + reconcile (Q9) are all inherited. The broker normalizes adapter events and provides them on the same surface. On the WezTerm backend events become polling synthesis, but within the range of Q9 best-effort tolerance ([§4.7](#47-terminal-adapter-boundary-and-capability-table)). The auxiliary event `agent_ready` ([§4.6](#46-replacement-of-the-startup-flow)) is positioned as an optional addition within the existing "MAY emit + unknown type is non-fatal" provision, and **the harness's canonical registration wait does not depend on it** (`list_peers` poll is the canonical path. Closed within the Surface 2.2 inheritance) |
| Surface 4: Identity & addressing (4.1-4.3) | **Inherit** | numeric id + stable name, all-digits = id interpretation, single-tab MUST (Q10) are inherited. The adapter implements scope enforcement per backend. **Newly added element**: the token <-> pane/session bind ([§4.4](#44-per-agent-token-lifecycle)) is a new layer of identification, and is placed not as a Surface 4 revision but in a new Surface (below) |
| Surface 5: Authentication / channel (5.1-5.2) | **Revision proposal** | Proposal to **abolish 5.1 dev-channel injection (flag injection + `send_keys(enter)` approval), and replace it with broker MCP injection via `--mcp-config` + per-agent token authentication**. 5.2 "transport is backend's freedom (MAY)" is inherited -- localhost HTTP is within this MAY range, but the authentication requirement (token mandatory) is newly added, and placed in a new Surface |
| Surface 6: Error code vocabulary (6.1-6.3) | **Inherit + new** | The `[<code>] <message>` format and minimum vocabulary, ABI stability (6.2), `backend_unreachable` normalization (Q11, Issue #242) are inherited. **Newly added codes** (within 6.2 "MAY add" provision): `token_invalid` / `token_revoked` / `token_expired` / `nudge_failed` (quiescence-check retry exhaustion) / `adapter_unavailable` (broker is alive but the terminal-backend side is unreachable -- distinguished from `backend_unreachable` (broker itself unreachable)) |
| Surface 7: Backwards-compatibility | **Inherit** | The SemVer obligation also applies to the broker MCP surface as-is |
| (New) Surface 8 proposal: Broker auth & delivery | **New** | per-agent token lifecycle ([§4.4](#44-per-agent-token-lifecycle)), role-scoped tool exposure ([§4.2](#42-broker-mcp-surface-per-role-exposed-surface)), nudge delivery contract (quiescence check / idempotency / failure escalation, [§4.3](#43-interrupt-delivery-to-the-secretary-nudge-hardest-part-subject-to-drop-out)), broker queue store ownership ([§4.5](#45-broker-queue-store-dedicated-subtree-at-statebroker). The on-disk surface is **coupled with Set C's inventory addition revision** and does not close in Set D lineage alone). Whether to make this a Set D supplemental Surface or an independent contract (Set G etc.) will be decided at the time of the contract revision PR |

Particular non-compat to be aware of (places where harness prose rewrites are needed at migration):

1. **Change in reception model**: Current prose is written on the assumption that `<channel source=...>` arrives in-band (e.g., "Ack on receiving a peer message" in worker brief). After pull unification, it needs to be rewritten to "When you see a nudge, run `check_messages`". Because Set D 2.1's HYBRID provision already constrains "do not route by source string", prose that depends on `from_*` / `sent_at` survives as-is.
2. **Change in the ritual just after spawn**: The dev-channel approval (spawn-flow 3-3b) disappears, and changes to trust-confirmation prompt handling (presence/absence and machine-approval feasibility measured at Phase 1 AC-2). The `list_peers` registration wait (3-4) is **maintained in the same form as the broker's bind-table-based `list_peers` poll** (`agent_ready` is a latency-improvement auxiliary, not the canonical path).
3. **Error branch additions**: Branches for `token_*` / `nudge_failed` / `adapter_unavailable` are added to dispatcher / secretary error handling prose. Because of the unknown-code non-fatal provision (6.2), the addition itself is non-breaking.

## 6. Relationship with non-goals

- **[`docs/non-goals.md`](../non-goals.md) §12 "We do not own external integrations of MCP's HTTP-exposed form"**: The broker MCP is localhost HTTP (**host-local only**, bound to 127.0.0.1 + per-agent token mandatory), and does not correspond to the "external exposure" that §12 negates (connections from browser extensions / IDEs on other machines, TLS / network-boundary issues). It also aligns with §12's alternative-means clause: "It is also possible to set up a separate MCP HTTP server alongside, but it is out of the claude-org-ja main repo's responsibility", and keeps "out of main repo's responsibility" by locating the broker substance on the claude-org-runtime side. However, the reasoning notes in §12 -- "consolidate on `renga-peers` (via local stdin/stdout)" and "intra-tab P2P is the canonical communication model" -- will diverge from reality at the time of Phase 3 absorption, so **at that time we propose to include the §12 revision (explicit codification of the host-local exception) in the contract revision PR** (only as a proposal from this design document; the normative document is not modified).
- **§6 "We do not own a PTY or terminal multiplexer layer"**: broker / adapter is a Layer 3-equivalent responsibility including PTY injection / pane control, and is not brought into this repository. The substance is placed in claude-org-runtime or a new repository ([§1](#1-background-and-settled-constraints-premises-this-design-does-not-overturn)).
- **§5 "Do not switch between multiple providers"**: The broker is a swap of terminal backends, not a swap of agents (Claude Code). The Claude-only stance is unchanged.

## 7. Phase plan and migration completion criteria

For each phase, "what needs to pass to declare migration complete" is fixed up front. All are demonstrated on a fork before absorption into the main repo.

### 7.1 Phase 1: spike (WezTerm / Windows, stop-or-go decision point)

Minimum demonstration: interactive pane spawn -> broker MCP connection (`--mcp-config` injection) -> token-attributed nudge -> `check_messages` for one round trip.

Pass criteria are a **2-track combination of AC-1 (nudge 4-state) and AC-2 (connection chain); both must pass to proceed to Phase 2 or later**.

**AC-1 -- nudge-injection 4-state test (go/no-go, with a plan-cancellation clause)**:

When the receiving (secretary-role) pane is in each of the following **4 states, inject a nudge, and in every state the secretary's input must not be broken**:

| # | Receiver state | Pass criterion |
|---|---|---|
| 1 | **idle** (input field empty and prompt quiescent) | The nudge reaches the Claude session as one message, and the display / history is not disturbed |
| 2 | **mid-IME conversion** (Japanese-input conversion window is open) | The mid-conversion string / conversion window / confirmation operation is not destroyed. The nudge is deferred and delivered after confirmation (input field quiescent) |
| 3 | **long-text input in progress** (unsent multi-line text in input field) | The nudge string does not mix into the in-progress text. The user's unsent text is not submitted on its own |
| 4 | **Claude output streaming** (spinner / mid-response generation) | The output rendering is not disturbed, and the nudge is correctly handled after response completion (does not vanish while sitting in the input queue, etc.) |

- Judgment **requires all 4 states to pass**. If even one results in "breaking secretary input" reproducibly, and even after exhausting mitigations (the quiescence-check defer in [§4.3](#43-interrupt-delivery-to-the-secretary-nudge-hardest-part-subject-to-drop-out) etc.) it cannot be resolved, **the plan itself is cancelled (shelved)**. AC-1 alone is the drop-out clause that leads to "plan cancellation".

**AC-2 -- successful replacement of the startup / connection chain (precondition for proceeding to Phase 2 or later)**:

The one round trip of the current spawn-flow 3-2 to 3-5 ritual ([§4.6](#46-replacement-of-the-startup-flow)) replaced by the broker method must succeed. Specifically, all of the following:

1. The Claude on the interactive pane spawned with `--mcp-config` injection can connect to the broker MCP. **If a trust-confirmation prompt appears, the orchestrator must be able to mechanically approve it with `send_keys`** (fail if human handwork is needed).
2. The env handoff and authentication of the per-agent token must succeed, and the broker must correctly attribute `from` from the token.
3. Registration detection must succeed: the broker's `list_peers` (bind table-based) poll can detect the just-spawned agent's appearance within timeout sense equivalent to the current 3-4 (~30 seconds).
4. send-text on Windows (PowerShell / ConPTY) must have no mojibake or drops.

- An AC-2 failure, unlike AC-1, is not immediately "plan cancellation" (it can be resolved by implementation-means change), but **does not proceed to Phase 2 or later until resolved**. The intermediate state of "proceed using renga together" while the 3-3b / 3-4 equivalent replacement does not succeed is not adopted.

### 7.2 Phase 2: inventory and contract alignment

- Completion criterion: the 3-category inventory of all call sites ([§3](#3-inventory-of-mcp__renga-peers__-call-sites)) and the Set D diff table ([§5](#5-alignment-with-contract-set-d-diff-table)) are fixed as this design document and pass review. **The creation of this document corresponds to this phase's deliverable** (but the contract revision itself is not included).

### 7.3 Phase 3: messaging migration (messaging adapter)

In the fork, rewire the calls of `send_message` / `check_messages` / `list_peers` / `set_summary` to broker tools, and when the following pass, absorb into the main repo:

- All message paths among worker / curator / dispatcher / secretary (completion reports / ack / escalation / DELEGATE / CURATE_* / retro gate) go through the broker (1 delegation cycle is completed without using the renga channel).
- Practical establishment of nudge delivery: the quiescence-check defer coexists with IME / long-text input, and the delivery latency is operationally acceptable (including not breaking the attention watcher's notification path).
- Attribution verification: all messages' `from` is correctly attributed from the token, and impersonation attempts (trying to send by pretending another agent's to_id) are structurally impossible.
- Simultaneous changes at absorption: re-declaration of category (b) permission schemas, prose rewrites of category (a) messaging family, contract revision PRs of Set D Surfaces 2 / 5, **addition revision to Set C's state files inventory for the `.state/broker/` subtree** ([§4.5](#45-broker-queue-store-dedicated-subtree-at-statebroker)), revision proposal of non-goals §12.

### 7.4 Phase 4: pane-operation migration (full backend adapter)

In the fork, rewire spawn / close / list_panes / inspect_pane / send_keys / poll_events to broker + adapter, and when the following pass, absorb into the main repo:

- The 1 cycle of delegate -> spawn -> monitoring (including stall detection / approval-pending observation) -> completion report -> CLOSE_PANE -> retro completes with the WezTerm backend only (without using renga).
- The effective latency of `poll_events` polling synthesis does not impair the dispatcher monitoring loop (3-minute cadence) correctness (pane_exited drops recover via list_panes reconcile).
- balanced split works equivalent to the current with WezTerm geometry information.
- Simultaneous changes at absorption: prose rewrites and contract revision PRs related to Surface 1 / 3 / 4, ratification of Surface 8 proposal (or Set G) creation.

### 7.5 Parallel experiment separation

If running a forked organization in parallel with the main repo, separation of dashboard ports, workers_dir, and `.state/` (state.db / broker queue store) is needed. Avoid collisions with the fork-side configuration (the experiment-procedure details are planned to live in the fork-side README and not brought into the main repo).

## 8. Remaining risks (known, design-time)

| Risk | Disposition |
|---|---|
| Nudge-injection cross-talk | When the receiver is mid-long-text input, the result is one step worse than renga's channel injection. Mitigated by the quiescence-check defer ([§4.3](#43-interrupt-delivery-to-the-secretary-nudge-hardest-part-subject-to-drop-out)), but the final verdict is the Phase 1 4-state AC-1 ([§7.1](#71-phase-1-spike-wezterm--windows-stop-or-go-decision-point)). **If it breaks, the plan as a whole is cancelled** |
| WezTerm residency becoming a new prerequisite | In exchange for removing the renga dependency, WezTerm (the fallback target) + broker daemon are added as prerequisites. Because of the adapter boundary, the secondary migration to tmux etc. is positioned as inexpensive |
| Event synthesis degradation | WezTerm has no native pane-lifecycle events, so it becomes polling synthesis ([§4.7](#47-terminal-adapter-boundary-and-capability-table)). Within Set D Q9 best-effort tolerance, but the monitoring effective latency increases |
| Broker as a single point of failure | The current renga server is also a similar single point, but the broker brings the new operational responsibility of daemon management (start / restart / queue store recovery). Prepare the startup / liveness runbook at Phase 3 absorption time |
| Token leakage | Child-process leakage via env is theoretically possible. The blast radius is constrained by revoke-on-exit + TTL + localhost bind + role scope ([§4.4](#44-per-agent-token-lifecycle)) |

## 9. Out of scope (future work)

- **Pythonization of dispatcher deterministic processing**: There is an idea to consolidate the monitoring loop etc. into broker-side code, but it is out of scope for this design (settled in primary input).
- **Strengthening to at-least-once delivery**: Inherits the at-most-once drain of Set D 2.3 ([§5](#5-alignment-with-contract-set-d-diff-table)). The broker queue store has persistence, so there is room to strengthen to ack-based redelivery in the future, but it is not treated in this design because it entails contract changes.
- **tmux adapter**: Only listed for reference in the capability table ([§4.7](#47-terminal-adapter-boundary-and-capability-table)). No implementation plan.
- **broker exposure of focus_pane / new_tab**: Excluded from the initial surface ([§4.2](#42-broker-mcp-surface-per-role-exposed-surface)). Consider adding when human-facing assistance is needed.

## Change log

- 2026-06-07: First edition (design only. Deliverable of the renga-decoupling-design delegation task).
