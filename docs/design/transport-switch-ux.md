# Transport switch conversational interface — UX design

> Status: **design only / not implemented**. This document is a "future design (proposal / plan) that has not been implemented", and all statements below are **proposals**. No implementation of this design exists in this repository, and the normative documents ([`CLAUDE.md`](../../CLAUDE.md) / `.claude/skills/**/SKILL.md` / `docs/contracts/**`), operations runbooks, and generator code are **not changed** by this design. References are **one-way only** from this design document to existing documents (we do not add references back to this design from existing documents). Do not write in the present tense as if it were already implemented.
>
> **Scope (Issue #535)**: This is limited to the **design of a conversational interface for transport switching**. Concretely, three mechanisms are designed:
> 1. A mechanism that hides the raw env `ORG_TRANSPORT` from the user, where the Secretary / `org-start` substitutes for env configuration and child-pane inheritance via a conversational interface ("start with broker", "switch back to renga") ([§5](#5-mechanism-1-conversational-interface-as-substitute-for-env-configuration-and-child-pane-inheritance)).
> 2. Always-on one-line visibility of the current transport in the `org-start` launch report ([§6](#6-mechanism-2-always-on-one-line-visibility-of-the-current-transport-in-the-org-start-launch-report)).
> 3. A **policy** of demoting the raw env steps in broker-dogfood-runbook to an appendix and adding PowerShell alongside ([§7](#7-mechanism-3-policy-of-demoting-raw-env-steps-in-broker-dogfood-runbook-to-an-appendix--adding-powershell)). The runbook body itself is not changed.
>
> **Inviolable premises (fixed constraints this design does not overturn, [§2](#2-inviolable-premises-explicit-constraints))**: (a) **The default `renga` (no `ORG_TRANSPORT`) = bit-equivalent non-destructive invariant is inviolable**, (b) The **resolution order (explicit argument > `ORG_TRANSPORT` env > default `renga`) and the SoT (runtime transport descriptor) are not changed**, (c) This design is **independent of Epic #6 Issue G track 3 (production ja broker live run / dogfood execution)** ([§8](#8-independence-from-issue-g-track-3)).
>
> Dependency documents (references are one-way only from this design to existing documents):
> - [`tools/transport.py`](../../tools/transport.py) (ja-side transport accessor. The single seam that reads the runtime descriptor)
> - [`docs/operations/broker-dogfood-runbook.md`](../operations/broker-dogfood-runbook.md) (current state of raw env steps. Target of the §7 appendix-demotion proposal)
> - [`docs/design/renga-decoupling.md`](./renga-decoupling.md) (upper-level design for decoupling from renga. This design is its UX layer)
> - [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) (Set D / Surface 8 draft. broker auth & delivery)
> - [`.claude/skills/org-start/SKILL.md`](../../.claude/skills/org-start/SKILL.md) (where the launch report lives. Target of the §6 visibility proposal)
>
> **Two-frame note (Refs #586 #604, added 2026-06-17 — the design-only body is not changed)**: This design document is written in the **operational frame** as of 2026-06-11. The "default `renga` (no `ORG_TRANSPORT`)" phrasing throughout, and the non-destructive invariant "no env -> `resolve()` returns default renga -> `rewrite_allow_entries` is identity -> bit-equivalent" in [§2](#2-inviolable-premises-explicit-constraints)-1 / [§5.5](#55-causal-chain-of-the-non-destructive-invariant), refer to the **operational default path** of the runtime at the time of writing (0.1.27, `DEFAULT_TRANSPORT = "renga"`). Separately, there is a **code-constant frame**: `DEFAULT_TRANSPORT` was flipped from `renga` to `broker` in runtime 0.1.28 (Epic #586 Phase 2), and on the code side `resolve(env={})` returns `broker`. The two frames refer to different things (operational default path vs code constant) and do not contradict. The persisted-choice mechanism ([§5.4](#54-proposed-persisted-choice-mechanism)) / conversational IF proposed by this design is a thin layer that **holds whether the built-in default is one or the other** ([§5.1](#51-conversational-triggers-intent--transport-selection) L97 explicitly states "this holds both before and after the flip"). The operational default path (production broker live run = Epic #6 Issue G **track 3** ([§8](#8-independence-from-issue-g-track-3)) until that activates, remains renga; the #515 co-existence dogfood within Issue G itself is ratified, only production promotion = track 3 is pending) is realized by the persisted choice substituting for `ORG_TRANSPORT` configuration. Therefore this note does not revise the design body; it is an alignment note for reading the above "default renga" prose as an expression of the operational frame (no flip / no revert).

---

## 1. Background and goal

### 1.1 Current state: raw env is exposed to the user

The transport layer has two systems, default `renga` / opt-in `broker` ([`tools/transport.py`](../../tools/transport.py), [`docs/design/renga-decoupling.md`](./renga-decoupling.md)). The single control point for switching is the environment variable `ORG_TRANSPORT` (`renga` | `broker`, unset = default `renga`), and today this raw env being **set by the user in their shell** is the switching mechanism. A user trying the broker system follows [`docs/operations/broker-dogfood-runbook.md`](../operations/broker-dogfood-runbook.md), prefixing env like `ORG_TRANSPORT=broker python3 ...`, and runs `unset ORG_TRANSPORT` (§5(1)) to switch back.

This current state has the following friction (**all of these are motivation for the proposal, not a claim that the current state is broken** — the default renga path works perfectly):

- **Raw env is not business language**: `CLAUDE.md`'s Secretary policy says "avoid technical terms, speak in business language", but `ORG_TRANSPORT=broker` is itself a technical term and falls outside the Secretary's conversational model.
- **The configuration site and inheritance scope depend on the user's tacit knowledge**: The Secretary, dispatcher, and worker all run in separate panes (separate processes). Which process's env needs to be set so the switch reaches all roles requires internal knowledge of [`tools/transport.py`](../../tools/transport.py) and the generators, and is invisible to the user ([§5.2](#52-two-propagation-surfaces)).
- **Which system is currently running is not visible**: The launch report shows no transport, so the user cannot confirm "am I on renga or broker right now" without reading env.
- **Raw env steps in the runbook assume POSIX**: The env operations in [`docs/operations/broker-dogfood-runbook.md`](../operations/broker-dogfood-runbook.md) are written in bash (`export` / `unset` / `kill -INT`), which Windows (PowerShell) users cannot use as-is.

### 1.2 Goal

**Hide the raw env `ORG_TRANSPORT` from the user-facing operation surface** and put transport switching on the **Secretary's conversational interface**. At the same time, **always show the current transport on one line in the launch report** and define a policy of **demoting the raw env steps in the runbook to a last-resort appendix** with PowerShell added. **The raw env is not removed** — the lowest control point of the resolution order (env) remains unchanged as part of the SoT chain, and the conversational interface is layered on top as **a thin layer that substitutes for setting that env** ([§3](#3-central-thesis-the-conversational-interface-is-a-thin-layer-on-top-of-the-resolve-chain)).

---

## 2. Inviolable premises (explicit constraints)

Fixed constraints this design does **not** overturn. Everything in the design sits beneath these three points.

1. **Default `renga` (unset) = bit-equivalent non-destructive invariant is inviolable**. With `ORG_TRANSPORT` unset, the generators (generated artifacts such as settings / allowlist) are not changed by even one byte from the current state. This is structurally guaranteed by `rewrite_allow_entries` in [`tools/transport.py`](../../tools/transport.py) (identity that returns input as-is for default `renga`) and by the runtime descriptor. **Adding a conversational interface, env is not set as long as broker is not selected via the conversational IF (= persisted choice is unset / renga), and the default renga remains bit-equivalent** (the condition is not "did we converse in this session" but "did we opt into broker". [§5.4](#54-proposed-persisted-choice-mechanism) cross-session implication / [§5.5](#55-causal-chain-of-the-non-destructive-invariant)).

2. **The resolution order (explicit argument > `ORG_TRANSPORT` env > default `renga`) and the SoT are not changed**. The decision logic for the transport is closed within `resolve()` (= the runtime's `resolve_transport`) in [`tools/transport.py`](../../tools/transport.py), and its single SoT is the runtime transport descriptor (`claude_org_runtime.transport`). **The conversational interface does not replace `resolve()`; it only *supplies* its input (env)**. The visibility ([§6](#6-mechanism-2-always-on-one-line-visibility-of-the-current-transport-in-the-org-start-launch-report)) only **consumes** `resolve()` and does not re-derive the transport (does not judge independently).

3. **Independent of Epic #6 Issue G track 3**. This design is "the UX / human-factors layer of switching" and **does not depend on or block** track 3 (production ja broker live run = dogfood execution) ([§8](#8-independence-from-issue-g-track-3)).

---

## 3. Central thesis: the conversational interface is a thin layer on top of the `resolve()` chain

Issue #535 requires two seemingly contradictory things — "hide raw env from the user" and "do not change the resolution order / SoT". The core of this design is to show that **these two coexist**. The key to that coexistence is captured in one sentence:

> **The conversational interface is a thin layer of write-side automation (substituting env configuration) + read-side display (visibility of the current system) layered *on top of* the unchanged `resolve()` chain. It is not a replacement or re-derivation of `resolve()`.**

- "Start with broker" -> this layer **sets** `ORG_TRANSPORT=broker` on behalf of the user (+ propagates to child panes, [§5](#5-mechanism-1-conversational-interface-as-substitute-for-env-configuration-and-child-pane-inheritance)).
- "Switch back to renga" -> this layer **clears** `ORG_TRANSPORT` (back to default renga).
- `resolve_transport()` / descriptor does **exactly the same thing** as today. The conversation only *supplies* the input env; it does not bypass or re-derive.
- The non-destructive invariant **follows automatically from this layer**: as long as broker is never selected through the conversational IF (= persisted choice is unset / renga) -> env unset -> default renga -> `rewrite_allow_entries` identity -> bit-equivalent ([§5.5](#55-causal-chain-of-the-non-destructive-invariant)). Note that **the invariant governs "the default renga state where broker is not selected", not "whether or not we conversed in this session"** (refined in [§5.5](#55-causal-chain-of-the-non-destructive-invariant)).

The mechanisms that follow are all details under this thesis.

---

## 4. Where the mechanisms live (Secretary + org-start)

The **listener** of the conversational interface and the **display owner** of visibility are positioned as follows (consistent with [`CLAUDE.md`](../../CLAUDE.md) where Secretary = the sole human contact point):

| Role | Position in this design |
|---|---|
| **Secretary** | The entity listening for conversational triggers like "start with broker" / "switch back to renga". Translates user intent into a transport selection (renga / broker) and initiates the substituted configuration in [§5](#5-mechanism-1-conversational-interface-as-substitute-for-env-configuration-and-child-pane-inheritance). Transport selection is a judgment accompanied by a human gate (broker is opt-in / revertible), and the Secretary is the sole conversational surface for it |
| **`org-start` (and each pane's launch sequence)** | Two roles: (i) **applying the substituted configuration** — at startup, reads the persisted choice ([§5.4](#54-proposed-persisted-choice-mechanism)) and reflects `ORG_TRANSPORT` into its own pane's env (the entity that makes the choice confirmed by the Secretary's conversation take effect at startup as "substituted env configuration"). (ii) **visibility** — reads the confirmed transport via `resolve()` and always appends it as one line to the launch report ([§6](#6-mechanism-2-always-on-one-line-visibility-of-the-current-transport-in-the-org-start-launch-report)) |

> **Responsibility split (mapping to Issue #535 scope wording)**: The opening scope phrase "Secretary / `org-start` substitutes for env configuration and child-pane inheritance via the conversational IF" is realized in two stages: **Secretary = conversation listener (intent -> confirming and persisting the choice)**, **`org-start` / each pane's launch sequence = reflecting the confirmed choice into env (the execution point of substituted configuration) + visibility**. The "instruction" for env configuration belongs to the Secretary, the "reflection" to the launch sequence, and together they make up "substituting env configuration and child-pane inheritance via the conversational IF".

> **design-only note**: The above is **not a change proposal** to normative documents (`CLAUDE.md` / each SKILL); it is a design-level positioning of "which role takes care of which conversational trigger / visibility / env reflection where". Actual prose reflection is out of scope (after a decision on adopting this design), and this design document does not touch the normative documents.

---

## 5. Mechanism (1): conversational interface as substitute for env configuration and child-pane inheritance

This is the mechanism that needs the most care in the design. The transport selection has to reach all roles in **Secretary -> dispatcher -> worker** (multiple processes), and has to cross the `spawn_claude_pane` pane boundary twice.

### 5.1 Conversational triggers (intent -> transport selection)

The Secretary translates utterances in business language like the following into transport selections (vocabulary is illustrative; **not normalized**):

| User utterance (example) | Translated selection | Substituted operation |
|---|---|---|
| "Start with broker", "I want to try broker" | `broker` | Substitute `ORG_TRANSPORT=broker` equivalent ([§5.4](#54-proposed-persisted-choice-mechanism)) + child-pane inheritance |
| "Switch back to renga", "Run on renga", "Revert" | `renga` (default) | Substitute clearing `ORG_TRANSPORT` (return persisted choice to renga = unset) |
| "Which one (transport) am I on now?" | (no change, query) | Consume `resolve()` and report the current system (same display path as [§6](#6-mechanism-2-always-on-one-line-visibility-of-the-current-transport-in-the-org-start-launch-report)) |

- **broker selection is treated as an opt-in / revertible judgment**. This is based on the **current transport descriptor semantics** (default = renga / `broker` only when `ORG_TRANSPORT=broker` is explicit. [`tools/transport.py`](../../tools/transport.py) L17-22, [`CLAUDE.md`](../../CLAUDE.md) "transport (transport) both systems"). The Secretary only substitutes the selection configuration; it does not step into broker daemon startup / dogfood execution (track 3) ([§8](#8-independence-from-issue-g-track-3)).
  - **Note (relation to [`docs/design/renga-decoupling.md`](./renga-decoupling.md))**: In the **future end-state** (full migration) of renga-decoupling, the default flips to a pure backend and "renga becomes an opt-in fallback" (same §1 adopted policy / §2). What this design assumes is **the current semantics** (default renga / broker is opt-in), and the timing is different from the end-state flip. The conversational IF of this design holds both before and after the flip, as "a layer that substitutes for selection configuration and visibility, whichever is currently the default" (whether the default is renga or broker is decided by the descriptor; this design does not judge it).
- The resolution order ([§2](#2-inviolable-premises-explicit-constraints)-2) is unchanged, so the path where the user passes the transport as an **explicit argument** (`explicit`) to an individual call takes priority over the conversational IF (top level). The conversational IF only touches the env layer (middle).

### 5.2 Two propagation surfaces

"The transport selection reaches everywhere" has **two distinct propagation surfaces** that are often confused. This design separates them:

- **(A) Generation-time baking**: ja's generators ([`tools/gen_delegate_payload.py`](../../tools/gen_delegate_payload.py) / [`tools/gen_worker_brief.py`](../../tools/gen_worker_brief.py)) read `ORG_TRANSPORT` from the **env of the process running the generation**, via the [`tools/transport.py`](../../tools/transport.py) accessor, and **bake** transport-specific values (server names `renga-peers` / `org-broker`, `spawn_inject` flag, allowlist) into the artifacts (delegate payload / worker brief). That is, the selection propagates into the *content* of the artifact through "the env of the process running the generator".

- **(B) Child-pane process env**: Whether the child pane (dispatcher / worker Claude process) launched by `spawn_claude_pane` **has `ORG_TRANSPORT` in its own `os.environ`** at launch. This matters when that child pane **runs further generators itself** (e.g. dispatcher runs `delegate-plan` / `gen_delegate_payload` to make artifacts for the worker).

> **Important distinction**: (A) is "artifact content"; (B) is "child-process environment". "Child-pane inheritance" in Issue #535 mainly refers to (B), but in actual operation the path by which the transport reaches all roles also spans (A) (artifacts baked by the generators propagate). This design makes both surfaces explicit and decides which to bet on in [§5.4](#54-proposed-persisted-choice-mechanism).

### 5.3 Propagation chain (Secretary -> dispatcher -> worker)

The path that has to be propagated for the transport to be consistent across all roles (making explicit **why the naive "export env in one place" approach is insufficient**):

```
User: "Start with broker"
   |
   v
Secretary (secretary process) -- substituted env config -+
   | (A) For parts where Secretary itself runs the generator, Secretary process env applies
   | (B) Is ORG_TRANSPORT inherited at child-pane spawn? <- uncertain (see below)
   v
Dispatcher (separate pane = separate process)
   | (A) For parts where dispatcher runs gen_delegate_payload / delegate-plan,
   |     dispatcher process env applies
   | (B) Is ORG_TRANSPORT inherited at worker spawn? <- uncertain
   v
Worker (yet another pane = yet another process)
```

- **Point of uncertainty (needs verification at implementation time, [§9](#9-residual-risks-and-implementation-time-verification-items))**: The env of the child pane that `spawn_claude_pane` launches **does not necessarily inherit the (mid-session-modified) `os.environ` of the calling Claude process**. Because renga launches panes under the same renga server process lineage, what a child pane inherits is the shell env at the time `renga --layout ops` was started, not changes added mid-session to the Secretary Claude's `os.environ`. **Do not write "mid-session env configuration is inherited by child panes via spawn" as if it were established fact** (per advisor feedback / confirmed by grep that spawn-flow contains no env inheritance description: [`.dispatcher/references/spawn-flow.md`](../../.dispatcher/references/spawn-flow.md) describes broker spawn as `--mcp-config <broker>` injection and does not mention `ORG_TRANSPORT` inheritance).

### 5.4 Proposed persisted-choice mechanism

Given the uncertainty in [§5.3](#53-propagation-chain-secretary---dispatcher---worker) (cannot bet on process env inheritance), this design proposes **a persisted-choice mechanism that does not depend on process env inheritance**. It is more robust than naive reliance on process env and coexists with the constraint of not changing resolution order / SoT.

**Proposal: hold the transport selection as a small piece of persistent state, and have each process reflect it into env at startup**.

- When the Secretary selects broker via conversation, the substituted operation does not bet on "changing the Secretary process's `os.environ`" but **writes the transport selection to a single persistence point** (candidates: part of existing state / dedicated small config. Concrete location / format is decided at implementation time, and if there is a need for consistency with [`docs/contracts/state-schema-contract.md`](../contracts/state-schema-contract.md) Set C inventory, a contract revision is handled as a separate proposal).
- Each pane's (Secretary / dispatcher / worker) **launch sequence** reads this persisted choice and reflects `ORG_TRANSPORT` into its own process env. This way both (B) child-pane env and (A) generation-time baking **converge on the same selection**.
- **Resolution order / resolution inputs are unchanged (important)**: The persisted choice is **not a new resolution input** to `resolve()`. The non-explicit input that `resolve()` looks at is still just `ORG_TRANSPORT` env, exactly as today ([`tools/transport.py`](../../tools/transport.py) L18-21 / L62-73). The persisted choice is "the source of the value when each pane's launch sequence writes `ORG_TRANSPORT` into env" = **env configuration automation mechanism**, equivalent to consistently / automatically doing what a user would otherwise do by hand in each pane's shell as `export ORG_TRANSPORT`. Neither the resolution order (explicit > env > default) nor the priority logic of `resolve()` is touched at all.
- **Switch back**: "Switch back to renga" returns the persisted choice to renga (= equivalent to env unset). From the next launch, all panes converge on default renga. Immediate reversion of running broker panes is an operations area following the switch-back conditions in [`docs/operations/broker-dogfood-runbook.md`](../operations/broker-dogfood-runbook.md) §5, and this design (UX layer) does not step into it.
- **Cross-session implication (explicit)**: The persisted choice survives across sessions. Once broker is selected, subsequent launches will continue to converge on broker until the user explicitly says "switch back to renga" (= the opt-in state persists. This is the intended UX). Therefore **you cannot say "did not converse in this session => renga"** — if broker was selected previously, the persisted choice stays at broker. The bit-equivalent invariant governs "the state where broker is not selected (persisted choice unset / renga)", and the non-bit-equivalent state after broker opt-in is **a correct consequence of the user's explicit selection** ([§5.5](#55-causal-chain-of-the-non-destructive-invariant)).

> **Alternatives considered and rejected**:
> - "Change the Secretary process's env and bet on spawn inheritance" — there is no guarantee that renga's spawn inherits the Secretary Claude's mid-session env ([§5.3](#53-propagation-chain-secretary---dispatcher---worker)), so it is less robust than the persisted choice.
> - "Do not persist, ask in conversation every time" — has the advantage that the simple invariant "if we did not converse, always default renga" holds, but the selection cannot be shared on the (A) path where dispatcher / worker run generators independently, and re-selection is required at every launch. This design prefers cross-pane / cross-session consistency and recommends persisted choice, but if an operation does not accept the cross-session implication (above), this alternative is also choosable (final decision is implementation scope).

> **design only**: The above is a **proposal** for the mechanism; introducing a persistence point and embedding into the launch sequence is implementation scope (normative docs / state schema are not changed by this design document).

### 5.5 Causal chain of the non-destructive invariant

**Proof** (causal chain) that [§2](#2-inviolable-premises-explicit-constraints)-1 is preserved even when we add the conversational IF. The condition the invariant governs is **"broker is not selected via the conversational IF (= persisted choice unset / renga)"**, not "did we converse in this session" ([§5.4](#54-proposed-persisted-choice-mechanism) cross-session implication):

```
Broker has never been selected via the conversational IF (persisted choice = unset / renga)
   -> Each pane's launch sequence does not set ORG_TRANSPORT in env
   -> resolve() sees "no env" and returns default renga
   -> rewrite_allow_entries returns input identically under DEFAULT_TRANSPORT
   -> Generated artifacts are not changed by even one byte (bit-equivalent)
```

- That is, the conversational IF is **completely passive** with respect to the default renga path (broker not selected) (if broker is not chosen, env is not set and nothing happens). This is the structural basis for "even when we layer on the conversational IF, the non-destructive invariant remains inviolable".
- Conversely, after a user opts in to broker, the persisted choice remains broker, and the launch sequence sets `ORG_TRANSPORT=broker` in env. The fact that artifacts then change to the broker surface (become non-bit-equivalent) is **not a violation of the invariant but a correct response to the user's explicit selection (opt-in)**. The invariant only promises to protect the "default renga (broker not selected) state" and does not extend to the post-opt-in state.

---

## 6. Mechanism (2): always-on one-line visibility of the current transport in the `org-start` launch report

### 6.1 Proposal

In the launch-completion report of `org-start` (the report template group in [`.claude/skills/org-start/SKILL.md`](../../.claude/skills/org-start/SKILL.md) Step 4), append **the current transport as a one-line, always-on** entry. Whether renga or broker, and regardless of whether a selection exists, **always display it** (rather than "only show when on broker", always make the current system explicit to remove the invisibility of "what am I implicitly running on now").

Display example (**the wording is a proposal and not normalized**):

```
Started the organization.
Previous state: {summary}
Started the dispatcher (the curator is auto-started temporarily when knowledge accumulates).
Transport: renga (default)          <- always one line (when broker is selected: "Transport: broker (opt-in)")
What do you want to do?
```

### 6.2 Consistency with the inviolable constraints

- **Do not re-derive the SoT**: The transport to display is obtained by **consuming** `resolve()` (= runtime-descriptor-driven) in [`tools/transport.py`](../../tools/transport.py). Do not independently read env or recompute the transport ([§2](#2-inviolable-premises-explicit-constraints)-2). This is how "do not change the SoT" is preserved on the display side.
- **Does not threaten bit equivalence**: The launch report is a **conversational output**, not a file write. The bit-equivalent invariant governs *artifacts (settings / allowlist)*, not human-facing one-line reports. Therefore, even with this one-line always-on display under default renga, the bit equivalence of artifacts is completely unaffected (state this explicitly to avoid confusion).
- **Relation to the runtime drift line**: The existing `org-start` Step 4 has a mechanism to append the drift line from `tools/check_runtime_version.py` at the end ([`.claude/skills/org-start/SKILL.md`](../../.claude/skills/org-start/SKILL.md) Block C2 / Step 4). The transport one-liner is positioned as **an independent always-on line** alongside it (drift is a conditional warning; transport is an unconditional status display).

> **design only**: Actual reflection into the Step 4 template is out of scope. This design document does not change the SKILL.

---

## 7. Mechanism (3): policy of demoting raw env steps in broker-dogfood-runbook to an appendix + adding PowerShell

### 7.1 Policy (do not change the runbook body)

On the premise that the conversational interface of [§5](#5-mechanism-1-conversational-interface-as-substitute-for-env-configuration-and-child-pane-inheritance) becomes the **main path**, define a policy of **demoting raw env steps (prefixing `ORG_TRANSPORT=broker python3 ...`, `unset ORG_TRANSPORT` to switch back, etc.) in [`docs/operations/broker-dogfood-runbook.md`](../operations/broker-dogfood-runbook.md) to a last-resort appendix**. The intent is to give the runbook the following priority:

1. **Main path**: Conversational interface ("start with broker", "switch back to renga").
2. **Appendix / last resort**: Direct manipulation of raw env (limited to cases where the conversational IF is unavailable / debugging / CI / automation, where the user explicitly needs low-level control).

Demotion is not "deletion" — the raw env remains as a legitimate control point of the resolution order ([§2](#2-inviolable-premises-explicit-constraints)-2) and continues to be accurately documented in the runbook appendix. **This design document only states the policy; it does not edit the runbook body** (design only).

### 7.2 PowerShell coexistence (proposed correspondence table to add in the appendix)

The current runbook's env operations assume bash (`export` / `unset` / `kill -INT`). The policy is to add Windows (PowerShell) equivalents in the appendix. Proposed correspondence:

| Operation | bash (current runbook) | PowerShell (proposed coexistence) |
|---|---|---|
| Apply broker to **just one command** (child process only) | `ORG_TRANSPORT=broker python3 ...` (applies only to that one process; does not remain in the shell) | PowerShell has **no equivalent prefix form**. `$env:ORG_TRANSPORT = "broker"` overwrites session env and remains afterward, so do `$env:ORG_TRANSPORT = "broker"; python ...; Remove-Item Env:\ORG_TRANSPORT` to **explicitly clear after execution**, or if child-process-only is required, use `Start-Process` with `-Environment` to pass to the launched process only (note that bash's child-only equivalent is not trivially writable) |
| Set broker for the current session (and keep) | `export ORG_TRANSPORT=broker` | `$env:ORG_TRANSPORT = "broker"` |
| Check current value | `echo "$ORG_TRANSPORT"` | `$env:ORG_TRANSPORT` |
| Switch back (unset) | `unset ORG_TRANSPORT` | `Remove-Item Env:\ORG_TRANSPORT` (if you do not want an error when unset: `Remove-Item Env:\ORG_TRANSPORT -ErrorAction SilentlyContinue`) |
| Stop daemon (SIGINT to foreground serve) | `kill -INT <pid>` | If foreground, `Ctrl+C`. Stop by PID is `Stop-Process -Id <pid>` (graceful stop equivalent to SIGINT is generally hard on Windows; note that foreground `Ctrl+C` is the main path) |

> **Note (non-equivalence of the prefix form, important)**: bash's `VAR=val cmd` **passes env only to the launched child process** and does not remain in the shell itself. PowerShell's `$env:VAR = "val"` **overwrites the current session env** and remains for subsequent launches until explicitly cleared. Equating them causes Windows users to unintentionally leave broker set, so the appendix should explicitly state "in PowerShell, set -> run -> clear (or `Start-Process -Environment`)".

> **Note (resolution order is unchanged)**: PowerShell coexistence is an addition of notation and affects neither the resolution order, the SoT, nor bit equivalence (`$env:ORG_TRANSPORT` only places a value in the same env layer as bash's `ORG_TRANSPORT`).
>
> **Note (alignment with CLAUDE.local.md's Windows guidance)**: In this repository's Windows environment, Python is `py -3` or `python`. The appendix's PowerShell examples follow this (use `python` / `py -3` in environments where there is no `python3` invocation).

> **design only**: The above correspondence table is a **proposal** to add to the runbook appendix; this design document does not edit the runbook.

---

## 8. Independence from Issue G track 3

The boundary between this design (switching UX layer) and Epic #6 Issue G track 3 (production ja broker live run / dogfood execution) is made explicit:

- **What this design covers**: The **human factors of transport selection** — conversational switching, current-system visibility, policy of demoting raw env steps. A layer for presenting / recording / displaying the choice that holds whichever of renga / broker is chosen.
- **What this design does not cover**: broker daemon startup / lifecycle / dogfood live run / executing switch-back conditions (these are the scope of [`docs/operations/broker-dogfood-runbook.md`](../operations/broker-dogfood-runbook.md) and track 3).
- **Dependencies**: This design **does not depend on track 3** (the conversational IF / visibility / runbook policy can be designed and implemented without broker actually running). Conversely, it also **does not block track 3** (track 3 can proceed as-is through the raw env path; the conversational IF only overlays a main path and does not close off the raw env path — [§7.1](#71-policy-do-not-change-the-runbook-body)). The two can progress independently.

---

## 9. Residual risks and implementation-time verification items

| Item | Note |
|---|---|
| **Real-world behavior of child-pane env inheritance ([§5.3](#53-propagation-chain-secretary---dispatcher---worker))** | Whether the child pane launched by `spawn_claude_pane` inherits the caller's mid-session-modified env or not **requires real-world verification**. This design does not bet on inheritance and proposes persisted choice ([§5.4](#54-proposed-persisted-choice-mechanism)), but the concrete path by which the launch sequence reflects the persisted choice into env is verified at implementation time |
| **Persisted choice location and Set C consistency** | The storage location (part of existing state or a dedicated config) and format of persisted choice are decided at implementation time. If newly placed under `.state/`, a proposal to revise the inventory in [`docs/contracts/state-schema-contract.md`](../contracts/state-schema-contract.md) Set C is required (this design document does not perform that revision) |
| **Ambiguity of conversational trigger vocabulary** | Natural language like "start with broker" can be ambiguous. Before the Secretary confirms a selection, make it possible to confirm that broker is opt-in / revertible and that the current system can be queried ([§6](#6-mechanism-2-always-on-one-line-visibility-of-the-current-transport-in-the-org-start-launch-report) query path). Normalization is out of scope |
| **Generation-time bake / display discrepancy** | Both the transport baked into artifacts by the generator ([§5.2](#52-two-propagation-surfaces) (A)) and the launch report display ([§6](#6-mechanism-2-always-on-one-line-visibility-of-the-current-transport-in-the-org-start-launch-report)) consume the same `resolve()`, guaranteeing agreement. If the two judge the transport via separate paths, they can drift, so the display must always consume the SoT ([§6.2](#62-consistency-with-the-inviolable-constraints)) |

---

## Revision history

- 2026-06-11: First version (design only. UX design for Issue #535 "transport switch conversational interface"). Hide raw env `ORG_TRANSPORT` (conversational IF substitutes for env configuration / child-pane inheritance / proposes persisted choice), always-on one-line visibility of the current transport in `org-start` launch report, policy of demoting raw env steps in broker-dogfood-runbook to an appendix + PowerShell coexistence. Under the inviolable constraints (default renga = bit equivalent / resolution order / SoT unchanged / independent of Issue G track 3), fixes as a central thesis that the conversational IF is a thin layer on top of the `resolve()` chain. Does not touch normative documents / runbook / runtime (one-way reference only).
