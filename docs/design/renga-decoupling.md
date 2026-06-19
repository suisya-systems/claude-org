# renga decoupling (Plan B) — org-broker / terminal adapter design

> Status: **design only / no implementation**. There is no implementation of this design in this repository. Experiments are conducted in a fork, and the substantive broker / adapter code is planned to live on the claude-org-runtime side.
> This document is "unimplemented future design", and every statement below is a **proposal / plan** (uptake into the body = claude-org-runtime / ja is not yet done). For the contrast with current behavior (via renga), see [§2 "Relation of current state to this design"](#2-relation-of-current-state-to-this-design).
> **Policy update (2026-06-11, the most important premise change for this document)**: The former §1.2 fixed constraint #2 ("WezTerm bare is not viable because of the IME constraint, so the human-input terminal stays on renga") is **empirically overturned** and therefore **withdrawn** ([§1.2](#1-background-and-fixed-constraints)). **IME non-interference is confirmed**, with grounds being (i) backend parity verification of spinner self-redraw x IME (rendering layer, 2026-06-11) and (ii) manual AC of broker nudge injection x mid-IME-composition (transport layer, 2026-06-08), both demonstrated in the fork claude-org-transport-lab. Accordingly, the premise of this design shifts from the dual structure of "only the transport layer is renga-free, the secretary stays on renga" to **a complete migration in which all panes (including the secretary) start the organization renga-free on the pure tmux / WezTerm backend**. **renga is not abolished** — it is demoted from "a mandatory premise required by the organization" to "an opt-in fallback the user may choose at will (a rollback destination when the pure backend misbehaves / is unsupported, and for people who want to use renga)" (default backend = tmux/WezTerm, minimum disruption, rollback-able). Below, statements that depended on the old premise have been updated to the new premise.
> **Fork demonstration status**: The fork spike of this design (claude-org-transport-lab) has completed Phase 1-4 + the working gate with GO on every item (the canonical backend is fixed to tmux; real-machine WezTerm verification is a follow-up). This repository (ja) is design only, and uptake into the body (prose rewrites, contract amendments, runtime implementation) is a separate scope. The demonstration harness and the raw logs for each AC live on the fork side, and this design document is readable standalone without relying on them.
> Primary inputs: a design-agreement note between the user and the secretary (2026-06-07, an operational note uncommitted to the repository at `notes/renga-decoupling-design-input-2026-06-07.md`) and a Codex design review (same day, an uncommitted note under `tmp/`). Both are outside git management and cannot be referenced from this branch, but **the constraints and agreements fixed there have been transcribed into the body at [§1](#1-background-and-fixed-constraints)**, and this design document is readable standalone.
> Dependent documents (references go one way only, this design document -> existing documents; no references are added from existing documents to this design document):
> - [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) (Contract Set D, ratified 2026-05-03. The foundation of this design)
> - [`docs/contracts/state-semantics-contract.md`](../contracts/state-semantics-contract.md) (Set F. The canonical for state.db SoT)
> - [`docs/contracts/state-schema-contract.md`](../contracts/state-schema-contract.md) (Set C. The `.state/` file ledger)
> - [`docs/non-goals.md`](../non-goals.md) (especially §6 PTY layer, §12 external HTTP exposure)
> - [`docs/design/core-harness-extraction.md`](./core-harness-extraction.md) (a precedent for the design-only header and layer organization)

---

## 1. Background and fixed constraints

Of the constraints below, **#1 (the billing constraint) is maintained as a fixed premise this design does not overturn**. **#2 (the old IME constraint) is withdrawn**, and **#3 (the adoption policy) is revised to a complete-migration premise** (both on 2026-06-11, based on empirical grounds).

1. **Billing constraint — headless is not viable (maintained)**: From 2026-06-15, usage of `claude -p` / Agent SDK is billed under an "Agent SDK monthly credit" (USD 200/month at Max 20x) separated from interactive use, with overages charged on API metered billing (source: code.claude.com/docs/en/headless, support.claude.com article 15036540). Worker usage in this organization will certainly exceed it, so **all agents stay in interactive TUI sessions**. The plan to remove renga dependency by making agents headless is rejected at this point. **This constraint is unchanged under the new premise** (even after complete migration to the pure backend, each agent remains an interactive TUI consuming the broker MCP).

2. **~~IME constraint — WezTerm bare is not viable~~ (withdrawn, 2026-06-11)**:
   - **Old constraint (historical, not the current premise)**: "Even in a single pane, Claude Code's spinner rendering ('✻ Cogitating...' etc.) steals the anchor of the IME conversion window (user measurement). renga solves this with hardware-cursor caret control. Therefore the terminal where a human inputs Japanese (the secretary pane) continues to use renga." Under this constraint, the dual structure of "only the secretary stays on renga, only the transport layer is brokered" was inevitable.
   - **Grounds for withdrawal (new fact = IME non-interference is confirmed)**: This constraint has been **empirically overturned**. (i) **Rendering layer** — backend parity verification of spinner self-redraw (DECSC/DECRC round trips, repeated absolute-CUP redraw at the same position) x IME yields GO on both the bare-tmux and bare-WezTerm backends, and **the user confirmed in actual operation** that Japanese IME is unharmed on both backends even **while the real Claude spinner is running** (2026-06-11). Mechanically, tmux delegates IME drawing to the host terminal's (Windows Terminal's) TSF layer, so the grid cursor jostled by the spinner and the IME anchor separate into different layers (bare WezTerm is also measured unharmed). (ii) **Transport layer** — manual AC of broker nudge injection x mid-IME-composition is GO (Microsoft IME / Windows 11, 2026-06-08; transient redraw shifts recover, and unconfirmed strings, confirmed strings, and unsent text are all undestroyed). Both were demonstrated in the fork claude-org-transport-lab.
   - **New premise (fixed)**: **On the pure tmux / WezTerm backend, neither spinner rendering nor broker nudge injection interferes with Japanese IME**. Therefore **even the secretary pane where humans input Japanese can be operated without renga**. The grounds for "the secretary stays on renga" have evaporated. renga's hardware-cursor caret is positioned as an additional mechanism unnecessary on the pure backend (see the IME-safe caret row of [§4.7.1](#471-cross-backend-capability-comparison-all-capabilities)).

3. **Adoption policy = complete migration (renga remains as an opt-in fallback, revised)**: Migrate the organization's transport layer (messaging, spawn, observation) **and the terminal backend of all panes including human input** to org-broker + terminal adapter (tmux / WezTerm), and make it the default that **the organization starts and completes without renga**. renga is demoted from "a mandatory premise required by the organization" to "**an opt-in fallback the user may choose at will**": (a) default backend = the pure tmux (POSIX) / WezTerm (Windows) backend, (b) renga is **retained optionally** as **a rollback destination when the pure backend is unhealthy / unsupported, and for people who want to use renga** (code / prose are not deleted), (c) minimum disruption, rollback-able (a flag returns to the renga path). **Abolishing renga is not the goal** — it merely becomes no longer mandatory. The dual structure of the old policy ("only the transport layer is decoupled, the secretary stays on renga") is discarded by this revision.

The approach is also agreed: thin diffs for rewiring (`mcp__renga-peers__*` -> broker tools) are **experimented in a fork**, and on success are taken into the body in phase units (messaging -> pane operations). The substantive code for the broker daemon + terminal adapter lives in claude-org-runtime (an existing separate package) or a new repository, and is not brought into this repository (consistent with [`docs/non-goals.md`](../non-goals.md) §6 "do not own a PTY or terminal-multiplexer layer"). Pythonization of the dispatcher's deterministic processing is **out of scope for this design** (only mentioned as a future task, [§9](#9-out-of-scope-future-tasks)).

## 2. Relation of current state to this design

**Current behavior (implemented, in operation)**: The organizational operation of this repository runs with the renga-peers MCP server (renga 0.18.0+, 14 tools) as the sole transport layer. Inter-agent messaging is renga's channel injection (in-band delivery of `<channel source="renga-peers">`), and pane operations / observation use `spawn_claude_pane` / `list_panes` / `inspect_pane` / `send_keys` / `poll_events` / `close_pane` etc. This current face is ratified as the abstract backend contract in [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) (Set D).

**This design (an unimplemented proposal)**: A plan to replace the transport layer with the org-broker daemon + terminal adapter. There is no broker / adapter implementation in this repository, and the current prose / code in `.claude/skills/` / `.dispatcher/` / `tools/` continue to call renga-peers. Until the fork experiments succeed and per-phase uptake decisions ([§7](#7-phase-plan-and-migration-completion-criteria)) pass, behavior in the body does not change at all.

| Aspect | Current (via renga, implemented) | Proposed (via broker, unimplemented) |
|---|---|---|
| Message delivery | The renga server injects via channel (in-band push to Claude, nudge + pull to Codex) | Accumulate in the broker queue store and **make all agents pull-based** (1-line nudge injection + `check_messages`) — planned |
| Sender attribution | The renga server attaches `from_id` / `from_name` from pane origin | The broker attaches from a **per-agent token** — planned (the point of not making it self-reported is the same) |
| Pane operations | All roles can access the same MCP server's tool group (narrowed by the permission schema) | Expose only the messaging face to worker / curator, and keep pane operations broker-internal + minimum exposure to dispatcher / secretary — planned ([§4.2](#42-broker-mcp-surface-public-face-by-role)) |
| Agent connection | At spawn, inject `--dangerously-load-development-channels server:renga-peers` + approval prompt | At spawn, inject the broker MCP (localhost HTTP) via `--mcp-config` — planned ([§4.6](#46-replacing-the-startup-flow)) |
| Terminal backend | renga required | **Default = the pure tmux / WezTerm backend (all panes renga-free)**. renga is retained as an opt-in fallback (swappable via adapter). New premise ([§1.2 withdrawal](#1-background-and-fixed-constraints)) |
| Human Japanese input | renga's hardware-cursor caret control | **IME non-interfering on the pure backend** (neither spinner rendering nor broker nudges break Japanese IME — empirically fixed by backend parity verification in the fork 2026-06-11 + manual AC of broker nudge x IME 2026-06-08). renga's hardware-cursor caret is unnecessary. Continuing renga is optional |

## 3. Inventory of `mcp__renga-peers__*` call sites

As a pre-execution of Phase 2 (inventory, contract alignment), fix all references in the repository in 3 categories (as of 2026-06-07, exhaustive survey by `grep -rE "mcp__renga-peers__"`). **The target of rewiring is (a) only**; (b) is redeclaration of the permission schema, and (c) follows by document update.

### 3.1 Category (a): Operational call descriptions (rewiring target)

Descriptions written in role prose / skills that actually fire as MCP calls at runtime. The matrix of caller (role) x tool:

| Tool | Secretary | Dispatcher | Curator | Worker |
|---|---|---|---|---|
| `send_message` | ● ack / instructions, forwarding, suspend notification (origins: `CLAUDE.md`, org-delegate / org-escalation / org-pull-request / org-suspend / org-retro / skill-audit / dispatcher-handover) | ● escalate / DELEGATE_COMPLETE / nudge / retro gate (`.dispatcher/CLAUDE.md`, spawn-flow / worker-monitoring / pane-close) | ● Reports such as CURATE_DONE (`.curator/CLAUDE.md`, org-curate) | ● Completion, progress, escalation reports (the worker brief template group) |
| `check_messages` | ● CI_COMPLETED receipt (org-pull-request), drain at suspend / resume | ● Worker self-report receipt of the monitoring loop | — | — (receipt is renga's in-band push) |
| `list_peers` | ● Peer check at start / resume | ● Wait for worker registration (spawn-flow 3-4) | — | ● (auto-discovery of the secretary; recorded in the brief) |
| `list_panes` | ● Start / suspend / attention family | ● Balanced split input / monitoring reconcile | — | — |
| `inspect_pane` | ● dispatcher prompt poll (handover path), org-delegate Step 5 intervention | ● Approval-waiting / stall observation (worker-monitoring) | — | — |
| `send_keys` | ● dispatcher `/clear` -> `/dispatcher-resume` keystroke, dev-channel approval, Esc intervention | ● dev-channel approval (spawn-flow 3-3b), Shift+Tab / Ctrl+C intervention | — | — |
| `poll_events` | ● pane_exited confirmation in org-suspend | ● pane_started / pane_exited monitoring (cursor persistence: `.state/dispatcher-event-cursor.txt`) | — | — |
| `spawn_claude_pane` | ● dispatcher / curator start (org-start), redispatch | ● worker spawn (spawn-flow 3-2), on-demand curator spawn | — | — |
| `spawn_pane` | ● attention watcher start (org-attention-start) | — | — | — |
| `close_pane` | ● org-suspend / org-attention-stop | ● CLOSE_PANE handling (pane-close), curator retirement | — | — |
| `set_pane_identity` / `set_summary` | ● org-start Step 0.3 self-repair, secretary-resume | ● dispatcher-resume | — | — |
| `focus_pane` / `new_tab` | (Human-facing helpers; no mandatory calls in operational prose) | — | — | — |

Main locations (operational documents containing call descriptions): `CLAUDE.md`, `.claude/skills/{org-start,org-delegate,org-escalation,org-pull-request,org-suspend,org-retro,org-curate,org-attention-start,org-attention-stop,secretary-resume,dispatcher-handover,dispatcher-resume,skill-audit}/SKILL.md`, `.claude/skills/org-delegate/references/{ack-template,instruction-template,pane-layout,renga-error-codes,worker-claude-template,claude-org-self-edit}.md`, `.dispatcher/CLAUDE.md`, `.dispatcher/references/{spawn-flow,worker-monitoring,pane-close}.md`, `.curator/CLAUDE.md`, `tools/templates/worker_brief_{normal,self_edit}.md`.

What this tells us about the rewiring scale:

- **The required face for worker / curator is minimal**: only `send_message` (+ `list_peers` for secretary discovery, equivalent of `check_messages` for receipt). They make no pane operations at all. -> Worker / curator are expected to be renga-tool-independent with Phase 3 (messaging migration) alone.
- **Pane-operation callers concentrate in dispatcher and secretary**: spawn / close / inspect / send_keys / poll_events are limited to these two roles. -> The blast radius of Phase 4 (pane-operation migration) is closed to the prose of these 2 roles.

### 3.2 Category (b): Permission schema / configuration declarations (not call sites)

Items where the tool name is merely listed as an allowlist entry. At rewiring, redeclaration in broker tool names is necessary:

- `.claude/settings.json` (declares 14 tools as allow)
- `tools/org_extension_schema.json` (per-role allow declarations)
- `.claude/skills/org-setup/references/permissions.md` (documentation of the schema)

### 3.3 Category (c): Document / comment / fixture references (not involved in behavior)

- Contract / design / operational documents under `docs/` (`docs/contracts/backend-interface-contract.md` and others, `docs/getting-started.md`, `docs/verification.md`, `docs/operations/`, `docs/legacy/`, `docs/internal/` etc.)
- docstring / comment references inside Python tools: `tools/dispatcher_retro_gate.py`, `tools/gen_delegate_payload.py`, `tools/peer_notify.py` (none of these are **code that calls MCP**. Since Python processes cannot reach MCP tools, they only generate / explain instruction text for the Claude session)
- Test fixture: `tools/test_org_setup_prune.py` (1 item as an allowlist string)

> Note: The repository-root `send_plan.json` (an uncommitted operational artifact) also contains references, but it is outside git management and is excluded from the inventory.

## 4. Proposed architecture: org-broker + terminal adapter

### 4.1 Overall picture

```
                   (human)
                      | Japanese input also completes on the pure backend (IME non-interfering. New premise §1.2)
   +------------------+-----------------------------------------+
   | Terminal backend (default = tmux / WezTerm. renga is opt-in fallback. swappable via adapter) |
   |  +--------+ +----------+ +--------+ +--------+             |
   |  |secretary| |dispatcher | |curator | |worker-*|             |  <- all panes including the secretary are renga-free
   |  +---+----+ +----+-----+ +---+----+ +---+----+             |
   +------+-----------+-----------+----------+-------------------+
          | MCP(HTTP, localhost only, per-agent token)
          v           v           v          v
   +-----------------------------------------------------+
   | org-broker daemon (planned to live on claude-org-runtime side) |
   |  - broker queue store (a dedicated subtree at .state/broker/)  |
   |  - token issuance, attribution attachment, role-scoped tool exposure |
   |  - nudge delivery (1-line keystroke via terminal adapter)      |
   |  +- terminal adapter (swappable) -----------------+           |
   |  | tmux adapter / WezTerm adapter / renga adapter |           |
   |  +------------------------------------------------+           |
   +-----------------------------------------------------+
```

- Each agent is planned to be injected at spawn with the broker's MCP server (localhost HTTP) via `--mcp-config`, and authenticated by a per-agent token.
- Sender attribution (`from`) is attached by the broker from the token, not self-reported (a reproduction of renga's server-attribution model = impersonation prevention).
- Pane operations (spawn / send-text / close / screen capture / events) are executed by the broker via an adapter. The adapter makes the **tmux / WezTerm (pure backend default) swappable, with renga being an optional opt-in fallback** treated under the same adapter boundary.

### 4.2 broker MCP surface (public face by role)

Whereas the current renga-peers shows the same tool group to all roles and narrows by the permission schema (category (b)), the broker plans to **change the tool exposure itself by the token's role scope**. The aim is to **structurally** cut off — not by permission settings — the path where a worker that has stepped on an injection types directly into the secretary pane (`send_keys`).

| Tool (proposed name) | worker / curator | dispatcher | secretary | broker-internal only |
|---|---|---|---|---|
| `send_message` | o | o | o | |
| `check_messages` | o | o | o | |
| `list_peers` | o | o | o | |
| `set_summary` | o | o | o | |
| `list_panes` (with geometry) | — | o | o | |
| `inspect_pane` (grid scrape) | — | o | o | |
| `send_keys` (raw PTY) | — | o | o | |
| `poll_events` (long-poll with cursor) | — | o | o | |
| `close_pane` | — | o | o | |
| `spawn_agent` (= current `spawn_claude_pane` equivalent) | — | o | o | |
| `spawn_pane` (generic) | — | — | o (for attention watcher) | |
| `set_pane_identity` | — | o | o | |
| Nudge injection (internal delivery mechanism) | — | — | — | ● (not exposed as a tool) |

- **The minimum surface for M1: dispatcher** is fixed as the face required by the current contract for correctness (`list_panes`(geometry) / `inspect_pane` / `send_keys` REQUIRED in Set D, plus `poll_events` / `close_pane` that the monitoring loop depends on) + the spawn family + the messaging family. The dispatcher column above is that enumeration.
- **Important framing**: This is not "elimination of pane operations". Because nudge delivery itself requires send-text (raw keystroke) as an internal mechanism, this is a **rephrasing of the boundary** so that **the broker becomes the trusted holder of pane operations and only worker / curator are made unreachable**. dispatcher / secretary retain pane operations as today (without them, monitoring, intervention, and suspend do not work).
- The secretary's public face is set to be nearly identical to the dispatcher's (the dispatcher start in org-start, attention watcher spawn/close, `send_keys` + `inspect_pane` on the handover path, and close/poll in org-suspend are needed by current operations; corresponds to the inventory in [§3.1](#31-category-a-operational-call-descriptions-rewiring-target)).
- renga's `focus_pane` / `new_tab` are human-facing helpers (Set D also marks them non-mandatory), and the proposal is to **leave them out** of the broker MCP's initial surface. Add them once they become needed.

### 4.3 Interrupting delivery to the secretary (nudge)

MCP is request-response and cannot push to an in-conversation Claude session. As a replacement for renga's channel injection (in-band push), a 2-tier scheme is proposed:

1. **Nudge**: The broker uses a terminal adapter (`wezterm cli send-text` for WezTerm, `send-keys` for tmux) to type a fixed 1-line "📨 New mail. Run check_messages" + Enter into the destination pane.
2. **Body retrieval**: The receiver retrieves the body via the broker's `check_messages`. **The body does not go through the PTY** (the risk of mixing long text, control characters, and multibyte is confined to the fixed 1-line nudge).

Design mitigations (verified in Phase 1):

- **Confirm input-area stillness before injection**: Before keystroke, the broker confirms via grid scrape that the destination pane's input area is empty (prompt still); if not empty, defer + retry. This is the same kind of known technique as the current dispatcher handover path (the procedure of polling for empty prompt at 1-second intervals after `/clear` and only then sending the next keystroke, recorded in `CLAUDE.md`).
- **Nudge idempotency**: Since delivery is a "there is unread" notification rather than the body, duplicate injection still results in single queue consumption on the `check_messages` side. Recovery from drops is via re-nudge.

> **Demonstration status (nudge delivery)**: Nudge delivery met the pass condition of Phase 1 spike ([§7.1](#71-phase-1-spike-demonstrating-renga-free-startup-of-all-panes)) with **AC-1 all 4 states GO** (none of idle / mid-IME-composition / mid long input / mid output streaming break the secretary's input. Mid-IME-composition reached GO by manual AC on 2026-06-08) in the fork claude-org-transport-lab. **The cutoff clause "if unmet, shelve the whole plan" placed by the old design has been resolved by achievement**. In addition, its premise ("because renga is the sole IME-safe shelter, if the broker breaks IME the plan dies") has disappeared with the constraint withdrawal in [§1.2](#1-background-and-fixed-constraints), and **even if a nudge mixes in a particular environment, the renga opt-in fallback acts as a safety valve, so it is no longer a condition for the whole plan's viability** (per-environment degradation is absorbed by renga's optional retention). For the working gate's definition, see [§7.6](#76-working-gate-renga-free-org-start-and-delegation-completion-on-all-panes).

### 4.4 Lifecycle of the per-agent token

The proposed lifecycle of the token that grounds sender attribution and role-scoped exposure:

| Phase | Proposed behavior |
|---|---|
| **Issuance** | The broker generates it when it receives a spawn request, and issues it individually via an environment variable at spawn (per primary-input agreement). The connection settings handed via `--mcp-config` reference this env. The token binds to `{agent_id, role, pane_id, session_id}` |
| **bind** | The token <-> pane/session table is held by the broker only. `from` attribution, role-scope decisions, and recipient resolution are all derived from this bind table; client self-reports are not taken |
| **revoke (pane retirement)** | Revoke immediately on the adapter's `pane_exited` event and on successful `close_pane` via the broker. Calls by tokens of retired panes are rejected with `token_revoked` (Surface 6 of [§5](#5-alignment-with-contract-set-d-diff-table)). Even if env leaks to a child process etc., after pane retirement it cannot be used |
| **TTL** | Set a TTL at issuance (the default is decided after measurement in Phase 1. For long-running sessions the basis is "TTL longer than session lifetime + revoke at retirement", with TTL positioned as insurance against missed expiry) |
| **suspend / resume** | Revoke all tokens at `/org-suspend` equivalent, and **reissue** at respawn during resume. Token reuse across suspend is disallowed (to keep pane id changes at resume and the bind table consistent) |
| **Storage and leak surface** | Tokens exist only in the host's env / broker bind table, and are not written in plaintext to the queue store, logs, or journal. Child-process leakage via env is bounded by revoke-on-exit + TTL + localhost bind in terms of impact surface (for further tightening, comparison study of delivery via per-agent mcp-config ephemeral file (0600) is proposed in Phase 1) |

### 4.5 broker queue store (a dedicated subtree at `.state/broker/`)

The broker's write area is **restricted to a dedicated subtree at `.state/broker/`**, and this area is named the "**broker queue store**" (the term "message store" is not used — to avoid confusion with state.db).

- The broker queue store is **neither state.db nor the events table**. It is **not made to collide** with the state.db SoT (runs / org_sessions / events / worker_dirs) defined by [`docs/contracts/state-semantics-contract.md`](../contracts/state-semantics-contract.md) (Set F) and the file ledger of [`docs/contracts/state-schema-contract.md`](../contracts/state-schema-contract.md) (Set C). The broker writes nothing to state.db.
- The sole writer to the broker queue store is the broker daemon. Conversely, existing state writers (StateWriter / journal_append family) do not write into `.state/broker/`. Ownership is symmetrically cut as "one writer per subtree".
- Contents (proposed): the delivery-pending queue, the delivered cursor, the token bind table (or bind is in-memory + rebuilt at restart), and the nudge delivery attempt log. The format (a separate SQLite file `queue.db` or JSONL) is decided at implementation.
- If audit events (e.g., escalation of delivery failure) are to be left in the organization journal, the broker does not write directly; instead, the **operations side**, which calls existing sanctioned writers (`tools/journal_append.*`), records them. The broker's responsibility is confined to transport.
- **Set C amendment is necessary**: Since [`docs/contracts/state-schema-contract.md`](../contracts/state-schema-contract.md) (Set C) covers the entire persistent file group under `.state/` as the contract target, "not colliding" alone is not enough; **the very creation of the `.state/broker/` subtree constitutes an addition amendment to Set C's state files inventory (path / format / owner=broker / readers / migration)**. Include the Set C amendment in the contract amendment PR at Phase 3 uptake ([§7.3](#73-phase-3-messaging-migration-messaging-adapter)). This design document is that amendment proposal, and does not modify Set C's body.

### 4.6 Replacing the startup flow

Contrast of the current canonical path (`.dispatcher/references/spawn-flow.md` Steps 3-2 to 3-5) and the proposal:

| Stage | Current (renga, implemented) | Proposed (broker, unimplemented) |
|---|---|---|
| 1. spawn | `spawn_claude_pane(...)` — renga synthesizes `--dangerously-load-development-channels server:renga-peers` | The dispatcher calls the broker's `spawn_agent(...)` -> the broker issues a token and spawns the pane via the adapter. The Claude launch args are planned to synthesize `--mcp-config <broker connection config>` (+ `--strict-mcp-config` if needed) |
| 2. Startup confirmation | Wait for `pane_started` via `poll_events` for at most 3 seconds | Equivalent (the broker's `poll_events` normalizes and returns the adapter's events on the same face) |
| 3. Channel approval | Approve "Load development channel?" prompt via `send_keys(enter=true)` | **The dev-channel prompt does not exist** (since the dev-channel flag is not used). For Claude Code's trust confirmation prompt for the MCP server injected via `--mcp-config`, presence and mechanical approvability is **measured in AC-2 ([§7.1](#71-phase-1-spike-demonstrating-renga-free-startup-of-all-panes)) and GO** (fork). If the prompt appears, it was confirmed that machine-approval via `send_keys(enter=true)` as today is possible |
| 4. Registration wait | Retry at 2-second intervals (max 30 seconds) until the worker appears in `list_peers` | **Keep the canonical path identical**: when the MCP client of the worker's Claude connects to the broker (initialize handshake), the broker transitions the bind table to "registered", and the dispatcher waits via the same poll as current 3-4 until the worker appears in the broker's `list_peers` (bind-table-based) — planned. As a supplement, the broker emits an `agent_ready` event, and a latency-improvement path via `poll_events` is also provided (optional. The canonical wait is the `list_peers` poll and does not depend on `agent_ready`) |
| 5. Instruction send | `send_message(to_id="worker-{task_id}", ...)` — renga injects via channel | `send_message` -> broker queue store insertion -> nudge delivery (the worker has empty input area right after startup, so stillness check passes immediately) -> worker retrieves body via `check_messages` |

With the dev-channel prompt's disappearance, the coupling of "3-3b (Enter approval) of the current spawn-flow" with "without approval, list_peers wait times out" is expected to dissolve, while a new check item "trust confirmation for MCP server connection" enters. **Successful replacement of stages 1, 3, 4 (the spawn -> connection -> attribution -> delivery round trip) is the Phase 1 spike pass condition AC-2** and has been achieved in the fork ([§7.1](#71-phase-1-spike-demonstrating-renga-free-startup-of-all-panes)). The gate "if the 3-3b / 3-4 equivalent ritual cannot be replaced, do not proceed to Phase 2 or later" was placed but has been passed by AC-2 GO.

### 4.7 Terminal adapter boundary and capability table

The adapter is **defined as two distinct things in 2 stages**: "messaging adapter (the minimum capability required by Phase 3)" and "full backend adapter (all capabilities required by Phase 4)". The claim of "adapter makes anything swappable" is not made — backends differ in capability, and some differences in the table below do not close.

> **Second-backend tmux status (fork demonstration)**: Implemented tmux as the second backend, and parameterized the WezTerm AC-1 / AC-2 harness by backend (sharing the common face). **AC-1 (3 automatic states) / AC-2 (connection chain) are green on both POSIX (tmux 3.4 / WSL2) and Windows (WezTerm) backends**. With this, the tmux column is promoted from "future / reference" to **implemented / measured**. The tmux columns in the table below are based on fork measurements.

#### 4.7.1 Cross-backend capability comparison (all capabilities)

| Capability | renga | WezTerm (`wezterm cli`) | tmux (`tmux`, fork implementation) | Required phase |
|---|---|---|---|---|
| send-text to a pane (nudge injection) | o `send_keys` | o `send-text` (bracketed paste default) | o `send-keys` (first-class primitive) | **Phase 3 (messaging)** |
| Control-key model (Enter / Ctrl-C etc.) | o (high-level API) | △ `send-text --no-paste` + `CR` / ETX (needs a workaround since paste is default) | o `send-keys Enter` / `C-c` / `-l` (no workaround needed. fork-measured) | **Phase 3 (messaging)** |
| grid scrape (state decision for stillness-check defer) | o | o `get-text` | o `capture-pane -p` (fork-measured) | **Phase 3 (messaging)** |
| Stable name management for pane identification | o (name/role server-managed) | △ (pane id only. name<->id mapping held by adapter) | △ (pane id `%N`. same held by adapter) | **Phase 3 (messaging)** |
| Headless / GUI-independent operation | o | △ (GUI not required. spawn possible with only mux-server. fork-measured) | o (standard behavior in detached session. no display needed. fork-measured) | Operational premise |
| split spawn (with cwd / command specification) | o | o `split-pane` | o `split-window` / `new-session` (spike verified with new-session) | Phase 4 |
| list_panes with geometry (cell-unit rect) | o | o `list --format json` (rows/cols/position) | o `list-panes -F` (`#{pane_left/top/width/height}`. fork-measured) | Phase 4 |
| grid scrape (`inspect_pane` equivalent) | o | o `get-text` | o `capture-pane` (fork-measured) | Phase 4 |
| Cursor-position scrape | o (`include_cursor`) | △ (impossible with `get-text` alone; separate retrieval, requires verification) | o (`#{cursor_x/y}` of `list-panes -F` retrieved in the same call. fork-measured. Superior to WezTerm) | Phase 4 |
| poll_events with cursor (lifecycle events) | o (long-poll + next_since) | x **No native event stream** -> adapter **synthesizes** `pane_started` / `pane_exited` from list polling (granularity / latency degraded) | △ (partial coverage via `pane-died` etc. hooks. spike does list-polling synthesis as with WezTerm. room for improvement combined with hooks) | Phase 4 |
| single-tab addressing (Set D §4.2 MUST) | o (server-enforced) | △ (tab concept exists. adapter implements scope enforcement) | △ (same per session / window unit. adapter implements scope enforcement) | Phase 4 |
| IME-safe caret (hardware-cursor control) | o | x | x | **Not required** (an additional mechanism unique to renga, but it is not mandatory because empirically confirmed that even on pure backend = WezTerm bare / tmux, spinner rendering and nudge injection do not interfere with IME. The old "ground for keeping renga" is withdrawn -> [§1.2](#1-background-and-fixed-constraints), fork backend parity verification 2026-06-11) |

#### 4.7.2 Adapter 2-stage capability boundary (messaging / full backend)

Instead of claiming "adapter makes anything swappable", separate into 2 tables to fix **which face is needed by Phase 3 and which by Phase 4**. The fork spike (WezTerm + tmux) demonstrated the **messaging tier (+ the startup chain)**; the full-backend-tier rewiring (spawn / inspect / poll_events) was verified within Phase 4 scope ([§7.4](#74-phase-4-pane-operation-migration-full-backend-adapter)).

**(a) messaging adapter (the minimum face required by Phase 3)** — demonstrated on both WezTerm + tmux (fork):

| Required face | WezTerm | tmux | Sufficiency status |
|---|---|---|---|
| send-text (fixed 1-line nudge injection) | o paste + `--no-paste` CR | o `send-keys -l` + `Enter` | Both backends green (AC-1 / AC-2 roundtrip) |
| grid scrape (idle/busy/input_pending decision for stillness-check defer) | o `get-text` | o `capture-pane -p` | Both backends green (AC-1 all states / state-classification logic shared) |
| Pane identification (name<->id mapping) | △ held by adapter | △ held by adapter | Sufficient at the adapter layer |
| Startup chain (`--mcp-config` injection + machine approval of trust confirmation + registration detection) | o | o | Both backends green (AC-2) |

-> **Conclusion**: The face needed for the messaging migration is closed to **send-text + grid scrape + pane identification + startup chain**, and renga / WezTerm / tmux all suffice. **The messaging migration is backend-independent** (demonstrated on both WezTerm / tmux, fork).

**(b) full backend adapter (the additional face required by Phase 4)**:

| Required face | WezTerm | tmux | Difference / degradation |
|---|---|---|---|
| split spawn (balanced split with geometry specification) | o `split-pane` | o `split-window` | balanced split structurally guarantees equivalence by reusing the current split-SoT logic ([§7.4](#74-phase-4-pane-operation-migration-full-backend-adapter)) |
| list_panes with geometry | o | o (form measured in the fork) | Equivalent |
| grid scrape (`inspect_pane`) | o | o | Equivalent |
| Cursor-position scrape | △ (separate retrieval, requires verification) | o (`list-panes` bundled) | **tmux superior** |
| poll_events (lifecycle, `pane_started`/`pane_exited`) | x -> polling synthesis | △ hooks + polling synthesis | Both synthesize. Within Set D Q9's best-effort + reconcile allowance, but monitoring latency increases. tmux has room for improvement combined with hooks |
| single-tab addressing (MUST) | △ adapter-enforced | △ adapter-enforced | Equivalent |

-> **Conclusion**: The Phase 4 face is roughly satisfied on both backends. The **practical latency of `poll_events` polling synthesis** (correctness of the dispatcher monitoring loop) and **balanced split's current-equivalence** are demonstrated in the fork on the canonical backend = tmux ([§7.4](#74-phase-4-pane-operation-migration-full-backend-adapter)). WezTerm is expected to suffice per the capability table but real-machine AC is a follow-up.

- **full backend adapter** (Phase 4): The synthesis of `poll_events` degrades event granularity and latency on both backends. Since Set D §3.1 allows cursor-loss with best-effort + `list_panes` reconcile (Q9), **polling synthesis is not a contract violation**, but the dispatcher monitoring loop's practical latency grows relative to renga.
- WezTerm / tmux residence becomes a new premise (the dependency-shift aspect). **Because the fork established the second tmux implementation, the framing "the adapter boundary makes secondary migration cheap" became empirical rather than desk-bound** (the same harness, the same AC, with backend parameter switching, comes green on both systems). It is possible to operate with tmux as canonical for POSIX and WezTerm as canonical for Windows.

## 5. Alignment with Contract Set D (diff table)

Fix this design's positioning relative to [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) (ratified 2026-05-03) per surface. **This section is a "amendment proposal"; the body of the ratified contract is not modified**. The amendment itself is planned to be executed separately as a formal contract amendment PR (Set D's amendment procedure) at the time of body uptake (per-phase uptake) after fork demonstration. To avoid creating dual canonicals, **the canonical until amendment ratification is the current Set D body**.

| Set D Surface | Category | Diff summary |
|---|---|---|
| Surface 1: Pane control (1.1–1.9) | **Inherit** (only the public boundary is an amendment proposal) | All semantics of operations (spawn / close / list_panes geometry / inspect_pane / send_keys / set_pane_identity, error codes, idempotency) are inherited. The change is "who can see them" only: make them unreachable from worker / curator, and limit to dispatcher / secretary + broker internal ([§4.2](#42-broker-mcp-surface-public-face-by-role)). The dev-channel flag injection obligation in 1.2 is proposed to be replaced by `--mcp-config` injection obligation in conjunction with Surface 5 amendment |
| Surface 2: Messaging (2.1–2.4) | **Amendment proposal** (the biggest change in this design) | Abolish 2.1's push-mode in-band delivery (channel injection toward Claude) and **unify all receivers to pull-mode** (nudge + `check_messages`. generalization of the current pull path toward Codex) — proposal. The **semantics** of attribution fields `from_id` / `from_name` / `sent_at` is **inherited** (remaining HYBRID-normative), but the **attachment mechanism is amended**: renga server's pane-derived attachment -> broker's token-derived attachment — planned. 2.2 `list_peers` / 2.3 `check_messages` (at-most-once drain) / 2.4 `set_summary` inherit semantics (only the implementing entity changes to the broker) |
| Surface 3: Events (3.1) | **Inherit** | Inherit cursor-based long-poll, "from now on" semantics on first call, minimum event vocabulary (`pane_started` / `pane_exited` / `events_dropped`), 30-second cap, best-effort + reconcile (Q9), all of it. The broker normalizes the adapter events and serves them on the same face. On the WezTerm backend, events become polling synthesis, but within Q9's best-effort allowance ([§4.7](#47-terminal-adapter-boundary-and-capability-table)). The auxiliary event `agent_ready` ([§4.6](#46-replacing-the-startup-flow)) is an optional addition within the existing "MAY emit + unknown type is non-fatal" rule, and **the harness's canonical registration wait does not depend on it** (`list_peers` poll is the canonical path. Closed within Surface 2.2 inheritance) |
| Surface 4: Identity & addressing (4.1–4.3) | **Inherit** | Inherit numeric id + stable name, all-digit = id interpretation, single-tab MUST (Q10). The adapter implements scope enforcement per backend. **Newly introduced element**: the token <-> pane/session bind ([§4.4](#44-lifecycle-of-the-per-agent-token)) is a new layer of identification; placed in a new Surface (below) rather than as a Surface 4 amendment |
| Surface 5: Authentication / channel (5.1–5.2) | **Amendment proposal** | **Abolish 5.1 dev-channel injection (flag injection + `send_keys(enter)` approval) and replace with broker MCP injection via `--mcp-config` + per-agent token authentication** — proposal. 5.2 "transport is free per backend (MAY)" is inherited — localhost HTTP is within the scope of this MAY, but the authentication requirement (token mandatory) is new, and is placed in a new Surface |
| Surface 6: Error code vocabulary (6.1–6.3) | **Inherit + add** | Inherit the `[<code>] <message>` format and minimum vocabulary, ABI stability (6.2), `backend_unreachable` normalization (Q11, Issue #242). **New codes** (within 6.2's "MAY add" rule): `token_invalid` / `token_revoked` / `token_expired` / `nudge_failed` (stillness-check retry exhaustion) / `adapter_unavailable` (the broker is alive but the terminal backend side is unreachable — distinguished from `backend_unreachable` (broker itself unreachable)) |
| Surface 7: Backwards-compatibility | **Inherit** | Apply SemVer obligation as is to the broker MCP surface |
| (new) Surface 8 proposal: Broker auth & delivery | **New** | Per-agent token lifecycle ([§4.4](#44-lifecycle-of-the-per-agent-token)), role-scoped tool exposure ([§4.2](#42-broker-mcp-surface-public-face-by-role)), nudge delivery contract (stillness check, idempotency, escalation on failure, [§4.3](#43-interrupting-delivery-to-the-secretary-nudge)), broker queue store ownership ([§4.5](#45-broker-queue-store-a-dedicated-subtree-at-statebroker)). The on-disk face is **linked to the Set C inventory addition amendment** and is not closed within the Set D lineage alone. Whether this is an addendum Surface of Set D or an independent contract (Set G etc.) is decided at the time of the contract amendment PR |

Particular incompatibilities to watch (places where harness prose needs rewriting at migration):

1. **Change in receive model**: Current prose is written on the premise of "`<channel source=...>` arrives in-band" (e.g., "ack on receiving a peer message" in the worker brief). After unification to pull, it needs rewriting to "when you see a nudge, run `check_messages`". Since Set D 2.1's HYBRID rule already binds "do not use source strings for routing", prose dependent on `from_*` / `sent_at` survives as is.
2. **Change in post-spawn ritual**: dev-channel approval (spawn-flow 3-3b) disappears, replaced by trust-confirmation prompt handling (presence / machine-approvability measured in Phase 1 AC-2). `list_peers` registration wait (3-4) is **kept identical as a broker bind-table-based `list_peers` poll** (`agent_ready` is an auxiliary for latency improvement, not the canonical path).
3. **Addition of error branches**: `token_*` / `nudge_failed` / `adapter_unavailable` branches are added to the error handling prose of the dispatcher / secretary. The unknown-code non-fatal rule (6.2) means the addition itself is non-breaking.

## 6. Relation to non-goals

- **[`docs/non-goals.md`](../non-goals.md) §12 "No external integration of MCP HTTP-public form"**: The broker MCP is localhost HTTP (**host-local only**, 127.0.0.1 bind + per-agent token mandatory), and does not fall under "external exposure" denied in §12 (browser extensions, connections from IDEs on other machines, issues of TLS / network boundaries). Also consistent with the §12 alternative-means section that allows "a design where a separate MCP HTTP server is co-deployed is also possible, but kept out of claude-org-ja body's responsibility", placing the broker substance on the claude-org-runtime side preserves "out of body responsibility". However, the reasoning section of §12 mentioning "consolidate into `renga-peers` (via local standard input/output)" and "intra-same-tab P2P is the canonical for the communication model" diverges from reality at Phase 3 uptake; therefore, **propose to include §12 amendment (explicit clause for host-local exception) in the contract amendment PR at that point** (this design document only proposes; normative documents are not modified).
- **§6 "No PTY or terminal-multiplexer layer"**: The broker / adapter is a Layer 3-equivalent responsibility including PTY injection and pane control, and is not brought into this repository. The substance is on claude-org-runtime or a new repository ([§1](#1-background-and-fixed-constraints)).
- **§5 "No multi-provider switching"**: The broker swaps the terminal backend, not the agent (Claude Code). The Claude-exclusive positioning is unchanged.

## 7. Phase plan and migration completion criteria

Fix in advance "what to pass to count as migration complete" for each Phase. All are demonstrated in the fork before being taken into the body.

### 7.1 Phase 1: Spike (demonstrating renga-free startup of all panes)

Minimum demonstration: an interactive pane spawn -> broker MCP connection (`--mcp-config` injection) -> token-attributed nudge -> `check_messages` round trip.

The pass condition is **2-pronged**: AC-1 (nudge 4 states) and AC-2 (connection chain). **Both ACs are GO in the fork (claude-org-transport-lab)**.

**AC-1 — nudge injection 4-state test**:

A nudge is injected while the receiver-side (secretary role) pane is in each of the following **4 states**, and **in any state the secretary's input must not break**:

| # | Receiver state | Pass criterion |
|---|---|---|
| 1 | **idle** (input area empty, prompt still) | The nudge arrives at the Claude session as a single message, with no garbling of screen / history |
| 2 | **mid-IME-composition** (Japanese input conversion window open) | The mid-composition string, conversion window, and confirmation operation are not destroyed. The nudge is deferred and delivered after conversion confirmation (input area still) |
| 3 | **mid long input** (multi-line text not yet sent in the input area) | The nudge string is not mixed into the typing-in-progress text. The user's unsent text is not sent without consent |
| 4 | **mid Claude output streaming** (spinner / response generation in progress) | Output rendering is not garbled, and the nudge is properly handled after response completion (including not stagnating in the input queue and being lost) |

- Judgment requires **passing in all 4 states**, and **all 4 states are GO** (state 2 = mid-IME-composition reached GO by manual AC on 2026-06-08; states 1/3/4 reached GO automatically. All demonstrated in the fork).
- **Cutoff clause withdrawal (redefinition, 2026-06-11)**: This AC-1 is read as "**demonstration that all panes (including the secretary) operate renga-free on the pure backend**". The cutoff clause placed by the old design "even if 1 state breaks the secretary's input, shelve the whole plan (cancel)" is **resolved** by both (i) AC-1's full-state GO achievement and (ii) the empirical withdrawal of its premise ("because renga is the sole IME-safe shelter, if the broker breaks IME the plan dies" = the old constraint in [§1.2](#1-background-and-fixed-constraints)). Hereafter, even if nudge mixing recurs in a particular environment, it is treated not as "plan cancellation" but as **degradation absorbed by the renga opt-in fallback** (because renga is retained optionally).

**AC-2 — Replacement of startup / connection chain (precondition for proceeding to Phase 2 or later)**:

The current spawn-flow 3-2 to 3-5 ritual ([§4.6](#46-replacing-the-startup-flow)), replaced by the broker scheme, must complete a round trip. Concretely all of the following:

1. The Claude in the interactive pane spawned with `--mcp-config` injection can connect to the broker MCP. **If the trust-confirmation prompt appears, the orchestrator must be able to mechanically approve it via `send_keys`** (fail if human handwork is required).
2. Env handoff of the per-agent token and authentication succeed, and the broker correctly attaches `from` attribution from the token.
3. Registration detection succeeds: the broker's `list_peers` (bind-table-based) poll detects the agent's appearance right after spawn with a timeout sense equivalent to current 3-4 (~30 seconds).
4. send-text on Windows (PowerShell / ConPTY) has no garbling or dropouts.

- A failure of AC-2 is not immediately "plan cancellation" (it can be resolved by changing implementation means), but **do not proceed to Phase 2 or later until it is resolved**. The intermediate state of "proceeding with renga coexistence" while 3-3b / 3-4 equivalent replacement is unestablished is not adopted.

### 7.2 Phase 2: Inventory and contract alignment

- Completion criterion: the 3-category inventory of all call sites ([§3](#3-inventory-of-mcp__renga-peers__-call-sites)) and the Set D diff table ([§5](#5-alignment-with-contract-set-d-diff-table)) are fixed as this design document and passed review. **The authoring of this document corresponds to the deliverable of this Phase** (the contract amendment itself is not included, however).

### 7.3 Phase 3: Messaging migration (messaging adapter)

In the fork, rewire `send_message` / `check_messages` / `list_peers` / `set_summary` calls to broker tools, and take into the body once the following pass:

- All message paths among worker / curator / dispatcher / secretary (completion reports / ack / escalations / DELEGATE / CURATE_* / retro gate) make a full round via the broker (1 delegation cycle completed without renga channels).
- Operational establishment of nudge delivery: stillness-check defer coexists with IME / long input, and delivery latency is operationally tolerable (including the attention watcher's notification path being unbroken).
- Attribution verification: all messages' `from` is token-derived and correctly attached, and impersonation sends (attempts to spoof another agent's to_id) are structurally impossible.
- Concurrent changes at uptake: redeclaration of category (b) permission schema, rewriting of category (a) messaging-family prose, contract amendment PR for Set D Surface 2 / 5, **the addition amendment of the `.state/broker/` subtree to Set C's state files inventory** ([§4.5](#45-broker-queue-store-a-dedicated-subtree-at-statebroker)), and the amendment proposal for non-goals §12.

### 7.4 Phase 4: Pane-operation migration (full backend adapter)

> **Phase 4 status (fork demonstration)**: Rewired spawn / close / list_panes / inspect_pane / send_keys / poll_events to broker + adapter and demonstrated **GO on every item** of the completion criteria below. Since the real-machine WezTerm is unavailable in this environment (Linux/WSL2), reading was substituted with the canonical backend tmux on the real machine (approved by human judgment via the secretary, following the precedent of tmux real-machine AC at messaging-tier verification). Real-machine WezTerm AC is a follow-up.

In the fork, rewire spawn / close / list_panes / inspect_pane / send_keys / poll_events to broker + adapter, and take into the body once the following pass (all items GO in the fork):

- On the tmux backend (no renga, the canonical backend in this environment), 1 cycle of delegate -> spawn -> monitoring (including stall detection / approval-waiting observation) -> completion report -> CLOSE_PANE -> retro completes.
- The practical latency of `poll_events` polling synthesis does not impair the correctness of the dispatcher monitoring loop (3-minute cadence) (`pane_exited` drops are recovered by `list_panes` reconcile. Synthesis is exactly-once under a single lock, pane meta is retained even after exit, and events_dropped has a count attached).
- balanced split functions equivalently to current with the backend's geometry information (structurally guaranteed equivalent by **reusing** the current split-SoT logic. The prose doc has drifted from the runtime, so do not port).
- Determine the minimum broker MCP surface for the dispatcher (privilege separation hidden from worker / curator. Dual blocking by role-tier `tools/list` filter + `call_tool` `[tool_forbidden]`).
- Concurrent changes at uptake: prose rewrites and contract amendment PR for Surface 1 / 3 / 4-related parts, and new ratification of Surface 8 proposal (or Set G) (in body-uptake scope).

### 7.5 Isolation of concurrent experiments

When running the fork organization concurrent with the body, separation of dashboard ports, workers_dir, and `.state/` (state.db / broker queue store) is necessary. Avoid collisions in the fork-side settings (the detailed experiment procedure is planned to live in the fork-side README and is not brought into the body).

### 7.6 Working gate (renga-free org-start and delegation completion on all panes)

> **Working gate definition (redefined 2026-06-11)**: To match the new premise ([§1.2](#1-background-and-fixed-constraints) constraint withdrawal), the working gate of Plan B (renga decoupling) is defined as: **all panes (including the secretary) can org-start renga-free on the pure tmux or WezTerm backend, and complete the delegation cycle**. The dual-structure premise of the old definition ("transport-only renga-free, secretary on renga for human input") is withdrawn. This redefinition is satisfied by the composition of (i) the already-GO **renga-free transport dogfood** (broker + tmux adapter, multiple delegation cycles completed. Canonical backend = tmux, real-machine WezTerm follow-up) and (ii) **empirical fixing of IME non-interference** (even doing human input in the secretary on the pure backend, spinner rendering and nudge injection do not break Japanese IME. [§1.2](#1-background-and-fixed-constraints), 2026-06-11 + 2026-06-08) — IME was the last grounds binding "only the secretary to renga", so with that withdrawal, all-pane renga-free becomes the formal pass condition of the working gate.

**Working gate = GO (demonstrated in fork claude-org-transport-lab)**. All 4 completion criteria are met with GO:

- **(1) On the backend (tmux) only, renga-free, all-pane startup (org-start equivalent) + multiple completed delegation cycles** -> 3 consecutive cycles completed on a single broker / adapter + cross-cycle isolation (under native id reuse, old handles get `pane_not_found`, and inbox / token / event cursor do not leak between cycles; double spawn is rejected by name collision). The real-machine includes 2 tmux cat cycles + 1 real-Claude worker active cycle.
- **(2) Broker establishment of the 4 failure classes** -> stall detection (consecutive-busy independent observation -> escalation enqueue) / escalation (defer-then-deliver + token attribution + at-most-once worker forwarding of human replies) / handover (pane-retaining handover via ops tier inspect + send_keys + no loss of monitoring cursor) / resume (suspend revokes all tokens + discards unread -> token reissue -> no stale inheritance).
- **(3) Empirical measurement of billing neutrality (interactive TUI only, no fallback to headless)** -> Structurally restrict agent spawn that injects tokens to **the allowlist of interactive claude TUI flags (default-deny)**, and uniformly reject headless flags, non-TUI subcommands, and unknown flags (with the maintenance contract that adding a new canonical interactive flag requires allowlist expansion). For the real Claude's real argv, observed headless-non-inclusion + interactive TUI rendering right after startup (consistent with the [§1](#1-background-and-fixed-constraints) billing constraint).
- **(4) Design document final version (tmux canonical backend promotion + Phase-result reflection)** -> This document (status header + this section + revision history) corresponds.

Verification is mainly non-billed, deterministic, CI-able (FakeAdapter), and real tmux smoke + 1 real-Claude worker active cycle (the secretary, via the human, approves the token cost) is added as the real-machine evidence trail. Body uptake (prose rewrites, contract amendments, runtime implementation) is a separate scope due to the ja design-only constraint.

## 8. Residual risks (known, at design time)

| Risk | Treatment |
|---|---|
| Nudge injection mixing | If the receiver is in mid long input, it may be one notch inferior to renga channel injection. Mitigated by stillness-check defer ([§4.3](#43-interrupting-delivery-to-the-secretary-nudge)), and **all states GO** in Phase 1's 4-state AC-1 ([§7.1](#71-phase-1-spike-demonstrating-renga-free-startup-of-all-panes)) (including mid-IME-composition, fork-demonstrated). **The old "if broken, cancel the whole plan" is withdrawn** ([§1.2](#1-background-and-fixed-constraints) constraint withdrawal + AC-1 achievement). Even if mixing recurs in a particular environment, the renga opt-in fallback absorbs the degradation (the plan does not die) |
| New premise of WezTerm / tmux residence | In exchange for removing renga dependency, the terminal backend (WezTerm / tmux) + broker daemon is added to the premise. Secondary migration is cheap thanks to the adapter boundary — **the fork established the second tmux implementation and empirically demonstrated that the same AC turns green on both systems by backend parameter switching** ([§4.7](#47-terminal-adapter-boundary-and-capability-table)). POSIX=tmux / Windows=WezTerm split is possible |
| Event-synthesis degradation | WezTerm has no native pane lifecycle events, so becomes polling synthesis ([§4.7](#47-terminal-adapter-boundary-and-capability-table)). Within Set D Q9's best-effort allowance, but the practical monitoring latency grows |
| Single point of failure of the broker | The current renga server is also a similar single point, but the broker brings in new operational responsibility of daemon management (startup, restart, queue-store recovery). Prepare a startup / liveness runbook at Phase 3 uptake |
| Token leakage | Child-process leakage via env is theoretically possible. Impact surface is bounded by revoke-on-exit + TTL + localhost bind + role scope ([§4.4](#44-lifecycle-of-the-per-agent-token)) |

## 9. Out of scope (future tasks)

- **Pythonization of dispatcher deterministic processing**: There is a vision of moving the monitoring loop etc. into broker-side code, but it is out of scope for this design (per primary-input agreement).
- **Strengthening to at-least-once delivery**: Inherits at-most-once drain of Set D 2.3 ([§5](#5-alignment-with-contract-set-d-diff-table)). The broker queue store has persistence, so there is room to strengthen to ack-based redelivery in the future, but it accompanies a contract change, so this design does not handle it.
- **tmux adapter**: Implemented in the fork (POSIX canonical backend). The tmux column in the capability table ([§4.7](#47-terminal-adapter-boundary-and-capability-table)) has been updated to measured values. The remaining out-of-scope is tmux-unique functionality beyond messaging / pane-control (copy-mode integration etc.), which is outside this design.
- **focus_pane / new_tab broker exposure**: Excluded from the initial surface ([§4.2](#42-broker-mcp-surface-public-face-by-role)). Consider adding once a human-facing helper becomes needed.

## Revision history

- 2026-06-07: First version (design only. Deliverable of the renga-decoupling-design delegation task).
- 2026-06-11: Reflects design re-derivation (design only). The fixed constraint #2 (WezTerm bare is not viable due to IME constraint, human-input terminal stays on renga) is **withdrawn** based on empirical grounds (rendering-layer backend parity verification 2026-06-11 + transport-layer broker nudge x mid-IME-composition manual AC 2026-06-08), and the adoption policy is revised from the dual structure of "transport-only renga-free, secretary on renga" to "**all panes (including the secretary) completely migrate to renga-free on the pure tmux / WezTerm backend, with renga retained as an opt-in fallback (not abolished, minimum disruption, rollback-able)**". The cutoff (plan cancellation) clause of Phase 1 is withdrawn, and the working gate is redefined as "**renga-free org-start + delegation cycle completion on all panes**" ([§7.6](#76-working-gate-renga-free-org-start-and-delegation-completion-on-all-panes)). Promoted the tmux column of the capability table (§4.7) to measured values, and split the messaging / full backend capability boundaries into 2 tables. Demonstration (the spike's Phase 1-4 + working gate) is complete on the fork claude-org-transport-lab (this repository is design only; does not touch implementation, runtime behavior, other files, or GitHub).
