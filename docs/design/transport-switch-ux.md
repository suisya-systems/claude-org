# Conversational interface for transport switching — UX design

> Status: **design only / no implementation**. This document is a "future, unimplemented design (proposal / plan)"; the descriptions below are all **proposals**. No implementation of this design exists in this repository, and the normative documents ([`CLAUDE.md`](../../CLAUDE.md) / `.claude/skills/**/SKILL.md` / `docs/contracts/**`), operations runbooks, and generator code are all **not changed** by this design. References go in **one direction only** from this design document to existing documents (do not add references to this design document on the existing-document side). Do not write in the present tense as if already implemented.
>
> **Scope (Issue #535)**: Limited to **the design of making transport switching conversational**. Specifically, the following 3 mechanisms are designed:
> 1. A mechanism by which the Secretary / `org-start` hides the raw env `ORG_TRANSPORT` from the user and proxies env setup and child-pane inheritance via a conversational interface ("start with broker" / "go back to renga") ([§5](#5-mechanism-1-proxying-env-setup-and-child-pane-inheritance-via-the-conversational-interface)).
> 2. Always-on 1-line visualization of the current transport in the `org-start` startup report ([§6](#6-mechanism-2-always-on-1-line-visualization-of-the-current-transport-in-the-org-start-startup-report)).
> 3. A **policy** for relegating the raw-env steps of the broker-dogfood-runbook to the appendix + adding PowerShell equivalents ([§7](#7-mechanism-3-policy-for-relegating-raw-env-steps-of-the-broker-dogfood-runbook-to-the-appendix--adding-powershell-equivalents); the runbook body itself is not modified).
>
> **Untouchable premises (the confirmed constraints this design does not overturn, [§2](#2-explicit-statement-of-untouchable-premises-constraints))**: (a) **Default `renga` (`ORG_TRANSPORT` unset) = bit-equivalent non-destructive invariant** is untouchable; (b) The **resolution order (explicit argument > `ORG_TRANSPORT` env > default `renga`) and SoT (runtime transport descriptor) are not modified**; (c) This design is **independent of Epic #6 Issue G Track 3 (production ja broker real-run / dogfood execution)** ([§8](#8-independence-from-issue-g-track-3)).
>
> Dependent documents (references go one-way only, from this design to existing documents):
> - [`tools/transport.py`](../../tools/transport.py) (ja-side transport accessor; the single seam that reads the runtime descriptor)
> - [`docs/operations/broker-dogfood-runbook.md`](../operations/broker-dogfood-runbook.md) (current state of the raw env steps; target of the §7 appendix relegation proposal)
> - [`docs/design/renga-decoupling.md`](./renga-decoupling.md) (upper-level design of renga dependency removal; this design is its UX layer)
> - [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) (Set D / Surface 8 proposal; broker auth & delivery)
> - [`.claude/skills/org-start/SKILL.md`](../../.claude/skills/org-start/SKILL.md) (location of the startup report; target of the §6 visualization proposal)
>
> **Two-frame note (Refs #586 #604, added 2026-06-17 — design only body is not modified)**: This design document is written in the **operational frame** as of the 2026-06-11 writing time, and the references throughout to "default `renga` (`ORG_TRANSPORT` unset)" and the non-destructive invariant of "env absent → `resolve()` returns default renga → `rewrite_allow_entries` is identity → bit-equivalent" in [§2](#2-explicit-statement-of-untouchable-premises-constraints)-1 / [§5.5](#55-causal-chain-of-the-non-destructive-invariant) are expressions referring to the **operational default route** of the runtime at writing time (0.1.27, `DEFAULT_TRANSPORT = "renga"`). Separately, in the **code-constant frame**, `DEFAULT_TRANSPORT` has flipped `renga` → `broker` in runtime 0.1.28 (Epic #586 Phase 2), and at the code level `resolve(env={})` returns `broker`. The two frames point at different objects (operational default route vs code constant) and do not conflict. The persisted-choice mechanism ([§5.4](#54-the-proposed-persisted-choice-mechanism)) / conversational IF proposed in this design is a thin layer that **holds whether the built-in default is renga or broker** (as [§5.1](#51-conversational-trigger-intent--transport-selection) L97 makes explicit, "holds before and after the flip"), and the operational default route (production broker real-run = Epic #6 Issue G **Track 3** ([§8](#8-independence-from-issue-g-track-3)) is renga until activated; the Issue G #515 coexistence dogfood itself is ratified, only the production promotion = Track 3 remains) is realized by persisted choice acting as proxy setter for `ORG_TRANSPORT`. Therefore, this note does not revise the design body; it is a consistency note for reading the "default renga" prose above as an expression of the operational frame (no flip / revert).

---

## 1. Background and purpose

### 1.1 Current state: raw env is exposed to the user

The transport layer has both tracks of default `renga` / opt-in `broker` ([`tools/transport.py`](../../tools/transport.py), [`docs/design/renga-decoupling.md`](./renga-decoupling.md)). The sole control point for switching is the environment variable `ORG_TRANSPORT` (`renga` | `broker`, unset = default `renga`); currently, the switching means is that **the user sets this raw env in their shell themselves**. Users trying the broker track follow the [`docs/operations/broker-dogfood-runbook.md`](../operations/broker-dogfood-runbook.md) procedure to prepend env as in `ORG_TRANSPORT=broker python3 ...`, and to roll back they strike `unset ORG_TRANSPORT` (§5(1)).

This current state has the following frictions (**all of these are motivations for proposal, not claims that the current state is broken** — the default renga route is fully functional):

- **Raw env is not business language**: The Secretary policy in `CLAUDE.md` is to "avoid technical terms and converse in business language," but `ORG_TRANSPORT=broker` is technical jargon itself, falling outside the Secretary's conversation model.
- **Where to set and the inheritance scope depend on the user's implicit knowledge**: Secretary, Dispatcher, and Workers run in separate panes (separate processes). Which process's env to set so the switch reaches all roles requires knowledge of the internals of [`tools/transport.py`](../../tools/transport.py) and the generators, invisible to the user ([§5.2](#52-two-propagation-surfaces)).
- **Which track is currently active is not visible**: There is no transport display in the startup report; the user cannot confirm "is it renga or broker right now" without reading env.
- **Raw env steps of the runbook assume POSIX**: The env operations of [`docs/operations/broker-dogfood-runbook.md`](../operations/broker-dogfood-runbook.md) are written in bash (`export` / `unset` / `kill -INT`), and Windows (PowerShell) users cannot use them as-is.

### 1.2 Purpose

**Hide the raw env `ORG_TRANSPORT` from the user's operational surface**, and put transport switching on the **Secretary's conversational interface**. At the same time, always **visualize 1 line of the current transport** in the startup report, and define the policy of **relegating the raw env steps of the runbook to the last resort (appendix)** with PowerShell equivalents alongside. **Do not abolish raw env** — the bottom-layer control point of the resolution order (env) remains invariant as part of the SoT chain, and the conversational interface is layered on top as a **thin upper layer that proxies the env setting** ([§3](#3-central-thesis-the-conversational-interface-is-a-thin-layer-on-top-of-the-resolve-chain)).

---

## 2. Explicit statement of untouchable premises (constraints)

The confirmed constraints this design **does not overturn**. The entire design sits under these three.

1. **Default `renga` (unset) = bit-equivalent non-destructive invariant is untouchable**. With `ORG_TRANSPORT` unset, generators (settings / allowlist etc. outputs) do not change by even 1 byte from the current. This is structurally guaranteed by `rewrite_allow_entries` (identity that returns input as-is under default `renga`) in [`tools/transport.py`](../../tools/transport.py) and the runtime descriptor. **Even adding the conversational interface preserves bit equivalence under default renga: as long as broker has not been selected in the conversational IF (= persistent choice unset / renga), env is not set** (the condition is not "did you converse in this session" but "did you opt in to broker"; [§5.4](#54-the-proposed-persisted-choice-mechanism) cross-session implication / [§5.5](#55-causal-chain-of-the-non-destructive-invariant)).

2. **Resolution order (explicit argument > `ORG_TRANSPORT` env > default `renga`) and SoT are not modified**. The transport-decision logic is closed within `resolve()` in [`tools/transport.py`](../../tools/transport.py) (= `resolve_transport` of the runtime), and its sole SoT is the runtime transport descriptor (`claude_org_runtime.transport`). **The conversational interface does not replace `resolve()`; it only *supplies* its input (env)**. Visualization ([§6](#6-mechanism-2-always-on-1-line-visualization-of-the-current-transport-in-the-org-start-startup-report)) also **consumes** `resolve()` only and does not re-derive (independently judge) the transport.

3. **Independent of Epic #6 Issue G Track 3**. This design is "the UX / human-engineering layer of switching" and **does not depend on or block** Track 3 (production ja broker real-run = dogfood execution) ([§8](#8-independence-from-issue-g-track-3)).

---

## 3. Central thesis: The conversational interface is a thin layer on top of the `resolve()` chain

Issue #535 demands two things that look contradictory — "hide raw env from the user" and "do not modify resolution order / SoT". The core of this design is to show that **these two are compatible**. The key to compatibility is condensed in one sentence:

> **The conversational interface is a thin write-side automation layer (proxy env setting) + read-side display (visualization of the current track) layered *on top of* the unchanged `resolve()` chain; it is not a replacement or re-derivation of `resolve()`.**

- "Start with broker" → this layer **sets** `ORG_TRANSPORT=broker` on the user's behalf (+ propagates to child panes, [§5](#5-mechanism-1-proxying-env-setup-and-child-pane-inheritance-via-the-conversational-interface)).
- "Go back to renga" → this layer **unsets** `ORG_TRANSPORT` (returns to default renga).
- `resolve_transport()` / descriptor does **exactly** the same thing as today. The conversation only *supplies* its input env and does neither bypass nor re-derivation.
- The non-destructive invariant **follows automatically from this layer**: as long as broker has never been selected in the conversational IF (= persistent choice unset / renga) → env unset → default renga → `rewrite_allow_entries` identity → bit equivalent ([§5.5](#55-causal-chain-of-the-non-destructive-invariant)). **Note that what governs the invariant is "the default renga state in which broker has not been selected" rather than "did you converse in this session"** (refined in [§5.5](#55-causal-chain-of-the-non-destructive-invariant)).

The detailed mechanisms below are all under this thesis.

---

## 4. Where the mechanisms live (Secretary + org-start)

The **listener** of the conversational interface and the **subject of visualization** are positioned as follows (consistent with [`CLAUDE.md`](../../CLAUDE.md) declaring the Secretary = the sole point of contact with humans):

| Role | Position in this design |
|---|---|
| **Secretary** | The subject that listens for conversational triggers like "start with broker" / "go back to renga". Translates user intent to transport selection (renga / broker) and triggers the proxy setting in [§5](#5-mechanism-1-proxying-env-setup-and-child-pane-inheritance-via-the-conversational-interface). Transport selection is a judgment accompanied by a human gate (broker is opt-in / rollback-safe); the Secretary is the sole conversational surface for it |
| **`org-start` (and each pane's startup sequence)** | Plays two roles: (i) **Applying the proxy setting** — reads the persistent choice ([§5.4](#54-the-proposed-persisted-choice-mechanism)) at startup time and reflects `ORG_TRANSPORT` into its own pane's env (the subject that, at startup, enacts the choice the Secretary finalized in conversation as "proxy env setting"). (ii) **Visualization** — reads the finalized transport via `resolve()` and always attaches a 1-line note to the startup report ([§6](#6-mechanism-2-always-on-1-line-visualization-of-the-current-transport-in-the-org-start-startup-report)) |

> **Sorting out the responsibility split (mapping to the scope wording of Issue #535)**: The opening scope's "the Secretary / `org-start` proxies env setup and child-pane inheritance via the conversational IF" is realized in two stages: **Secretary = the conversation listener (intent → finalize and persist the choice)**, **`org-start` / each pane's startup sequence = reflecting the finalized choice into env (the enactment point of the proxy setting) + visualization**. The "instruction" of env setting is the Secretary, the "reflection" is the startup sequence; together they form "proxy of env setup and child-pane inheritance by the conversational IF".

> **design only note**: The above is not a **change proposal** to the normative documents (`CLAUDE.md` / each SKILL); it is the design-level positioning of "which role handles which of conversational triggers / visualization / env reflection where". Actual prose reflection is out of scope (after a decision to take this design in is made), and this design document does not touch the normative documents.

---

## 5. Mechanism (1): Proxying env setup and child-pane inheritance via the conversational interface

The most attention-requiring mechanism in this design. The transport choice needs to reach all roles **Secretary → Dispatcher → Worker** (multiple processes), and crosses the `spawn_claude_pane` pane boundary twice.

### 5.1 Conversational trigger (intent → transport selection)

The Secretary translates business-language utterances like the following into transport selection (vocabulary is illustrative; **not normative**):

| User utterance (example) | Translated choice | Proxied operation |
|---|---|---|
| "Start with broker" / "I want to try broker" | `broker` | Equivalent of `ORG_TRANSPORT=broker` set on behalf ([§5.4](#54-the-proposed-persisted-choice-mechanism)) + child-pane inheritance |
| "Go back to renga" / "Run on renga" / "Revert" | `renga` (default) | Equivalent of `ORG_TRANSPORT` unset on behalf (return persistent choice to renga = unset) |
| "Which transport am I on?" | (no change, inquiry) | Consume `resolve()` and report current track (same display path as [§6](#6-mechanism-2-always-on-1-line-visualization-of-the-current-transport-in-the-org-start-startup-report)) |

- **Treat broker selection as an opt-in / rollback-safe judgment**. This is based on the **current transport descriptor semantics** (default = renga / `broker` only when `ORG_TRANSPORT=broker` is explicit; [`tools/transport.py`](../../tools/transport.py) L17-22, [`CLAUDE.md`](../../CLAUDE.md) "Transport (transport) two-track"). The Secretary only proxies the choice setting and does not step into broker daemon startup / dogfood execution (Track 3) ([§8](#8-independence-from-issue-g-track-3)).
  - **Note (relationship to [`docs/design/renga-decoupling.md`](./renga-decoupling.md))**: In the **future end-state** (full migration) of renga-decoupling, the default flips to pure backend and "renga becomes opt-in fallback" (same §1 adoption policy / §2). This design assumes **current semantics** (default renga / broker as opt-in), distinct in time from the end-state flip. The conversational IF in this design is **a layer that, regardless of which is the default now, proxies the choice setting and visualizes it**, and holds before and after the flip (which of renga or broker is the default is decided by the descriptor; this design does not judge).
- Resolution order ([§2](#2-explicit-statement-of-untouchable-premises-constraints)-2) is invariant, so the path where the user passes a transport via **explicit argument** (`explicit`) to an individual call takes precedence over the conversational IF (top of the order). The conversational IF only touches the env layer (middle).

### 5.2 Two propagation surfaces

There are **two distinct propagation surfaces** for the transport selection to "reach" — frequently confused. This design separates them:

- **(A) Generation-time baking**: ja's generators ([`tools/gen_delegate_payload.py`](../../tools/gen_delegate_payload.py) / [`tools/gen_worker_brief.py`](../../tools/gen_worker_brief.py)) read the `ORG_TRANSPORT` of the **env of the generation-executing process** via the [`tools/transport.py`](../../tools/transport.py) accessor and **bake** transport-specific values (server names `renga-peers` / `org-broker`, `spawn_inject` flag, allowlist) into the artifact (delegate payload / worker brief). That is, the choice propagates to the artifact *content* via "the env of the process running the generator".

- **(B) Child-pane process env**: Whether the child pane (Dispatcher / Worker Claude process) launched via `spawn_claude_pane` **has `ORG_TRANSPORT` in its own `os.environ`** at startup. This matters when **the child pane itself runs a generator** (e.g., the Dispatcher runs `delegate-plan` / `gen_delegate_payload` to create artifacts targeted at the Worker).

> **Important distinction**: (A) is "artifact content," (B) is "child process environment." What Issue #535 calls "child-pane inheritance" mainly refers to (B), but the path by which the transport reaches all roles in actual operation also spans (A) (the artifacts baked by the generator are propagated). This design exposes both surfaces and decides which to bet on in [§5.4](#54-the-proposed-persisted-choice-mechanism).

### 5.3 Propagation chain (Secretary → Dispatcher → Worker)

The path that must propagate so the transport is consistent across all roles (making explicit why **a naive "export env in one place" is not enough**):

```
User: "Start with broker"
   |
   v
Secretary (secretary process) -- proxy env setting --+
   | (A) Generation by the Secretary itself uses Secretary process env
   | (B) Will ORG_TRANSPORT be inherited at child-pane spawn?  <- uncertain (below)
   v
Dispatcher (different pane = different process)
   | (A) The portion where the Dispatcher runs gen_delegate_payload / delegate-plan
   |     uses Dispatcher process env
   | (B) Will ORG_TRANSPORT be inherited at Worker spawn?  <- uncertain
   v
Worker (yet another pane = yet another process)
```

- **Uncertain point (empirical verification required, [§9](#9-residual-risks-and-implementation-time-verification-items))**: The env of the child pane started via `spawn_claude_pane` does **not necessarily inherit the `os.environ` of the caller Claude process (as modified mid-session)**. Renga starts panes under the same renga-server process hierarchy, so what the child pane inherits is the shell env at the time of `renga --layout ops` startup, not changes made to the Secretary Claude's `os.environ` mid-session — high probability. **Do not write "mid-session env settings are inherited by child panes via spawn" as established fact** (per advisor advice / grep also confirms there is no description of env inheritance in spawn-flow: [`.dispatcher/references/spawn-flow.md`](../../.dispatcher/references/spawn-flow.md) describes broker spawn as `--mcp-config <broker>` injection and does not mention `ORG_TRANSPORT` inheritance).

### 5.4 The proposed persisted-choice mechanism

In light of the uncertainty in [§5.3](#53-propagation-chain-secretary--dispatcher--worker) (we cannot bet on process env inheritance), this design proposes a **persisted-choice mechanism that does not depend on process env inheritance**. It is more robust than naive reliance on process env and compatible with the constraint of not modifying the resolution order / SoT.

**Proposal: Hold the transport choice as a small persistent state, and have each process reflect it into env at startup.**

- When the Secretary picks broker in conversation, the proxy operation does not bet on "changing the Secretary process's `os.environ`"; instead it **writes the transport choice into one persistent point** (candidates: part of existing state / a small dedicated configuration; the specific location and format are decided at implementation, and if alignment with the inventory of [`docs/contracts/state-schema-contract.md`](../contracts/state-schema-contract.md) Set C is needed, treat as a separate contract-amendment proposal).
- The **startup sequence** of each pane (Secretary / Dispatcher / Worker) reads this persistent choice and reflects `ORG_TRANSPORT` into its own process env. This **aligns both surfaces of (B) child-pane env and (A) generation-time baking on the same choice**.
- **Resolution order / resolution input is invariant (important)**: The persisted choice is **not a new resolution input** for `resolve()`. What `resolve()` sees as non-explicit input is, the same as today, **only** the `ORG_TRANSPORT` env ([`tools/transport.py`](../../tools/transport.py) L18-21 / L62-73). The persisted choice is "the source of the value when each pane's startup sequence writes `ORG_TRANSPORT` into env" = **an env-setting automation mechanism**, equivalent to consistently / automatically replacing the user manually exporting `ORG_TRANSPORT` in each pane's shell. Neither the resolution order (explicit > env > default) nor `resolve()`'s priority logic is touched in any way.
- **Rollback**: "Go back to renga" returns the persisted choice to renga (= equivalent to env unset). From the next start, all panes align to default renga. Immediate return of running broker panes is the operational area governed by the rollback conditions in [`docs/operations/broker-dogfood-runbook.md`](../operations/broker-dogfood-runbook.md) §5, and this design (UX layer) does not step into that.
- **Cross-session implication (explicit)**: The persisted choice persists across sessions. Once broker is picked, subsequent starts also align to broker until "go back to renga" is said explicitly (= the opt-in state continues; this is the intended UX). Therefore, **"did not converse in this session ⇒ renga" cannot be said** — if broker was picked in the past, the persisted choice stays broker. The bit-equivalent invariant only governs "the state in which broker has not been picked (persisted choice unset / renga)"; non-bit-equivalence after opt-in to broker is the **correct consequence of the user's explicit choice** ([§5.5](#55-causal-chain-of-the-non-destructive-invariant)).

> **Alternatives considered and rejected**:
> - "Change Secretary process env and bet on spawn inheritance" — inferior in robustness to persisted choice because renga's spawn has no guarantee of inheriting Secretary Claude's mid-session env ([§5.3](#53-propagation-chain-secretary--dispatcher--worker)).
> - "Do not persist; specify in conversation each time" — has the merit of preserving the simple invariant "if you don't converse, always default renga", but the choice cannot be shared on the (A) path where Dispatcher / Workers independently run generators, and re-selection is required at every startup. This design recommends persisted choice prioritizing cross-pane / cross-session consistency, but if the operation does not accept the cross-session implication (above), this alternative can be picked (final decision is in implementation scope).

> **design only**: The above is a **proposal** for the mechanism; new persistence point and integration into the startup sequence are in implementation scope (normative documents / state schema are not modified in this design document).

### 5.5 Causal chain of the non-destructive invariant

**Proof** (causal chain) that [§2](#2-explicit-statement-of-untouchable-premises-constraints)-1 is preserved even after adding the conversational IF. The condition the invariant governs is **"broker has not been picked in the conversational IF (= persisted choice unset / renga)"**, not "did you converse in this session" ([§5.4](#54-the-proposed-persisted-choice-mechanism) cross-session implication):

```
broker has never been selected in the conversational IF (persisted choice = unset / renga)
   -> each pane startup sequence does not set ORG_TRANSPORT in env
   -> resolve() sees "no env" and returns default renga
   -> rewrite_allow_entries identity-returns input under DEFAULT_TRANSPORT
   -> artifacts do not change by 1 byte (bit equivalent)
```

- That is, the conversational IF is **completely passive against the default renga route (broker not picked)** (if broker is not picked, env is not set and nothing happens). This is the structural ground for "even layering the conversational IF, the non-destructive invariant is untouchable".
- Conversely, after the user opts in to broker, the persisted choice remains broker, and the startup sequence sets `ORG_TRANSPORT=broker` in env. At that time, the artifact changing to the broker surface (becoming non-bit-equivalent) is **not a violation of the invariant but a correct response to the user's explicit choice (opt-in)**. The invariant only promises protection of "the default renga (broker not picked) state" and does not extend to the post-opt-in state.

---

## 6. Mechanism (2): Always-on 1-line visualization of the current transport in the `org-start` startup report

### 6.1 Proposal

To the `org-start` startup completion report (the report-template group in [`.claude/skills/org-start/SKILL.md`](../../.claude/skills/org-start/SKILL.md) Step 4), attach **the current transport always in 1 line**. For both renga / broker, and regardless of whether a choice has been made, **always display** (instead of "show only when broker," resolve the invisibility of "what am I implicitly running on now" by always making the current track explicit).

Display example (**the wording is a proposal, not normative**):

```
Started the organization.
Previous state: {summary}
Started the Dispatcher (Curator is auto-launched temporarily when learnings accumulate).
Transport: renga (default)          <- always 1 line (when broker is picked: "Transport: broker (opt-in)")
What would you like to do?
```

### 6.2 Alignment with untouchable constraints

- **Do not re-derive the SoT**: The transport to display is obtained by **consuming** `resolve()` (= runtime-descriptor-driven) in [`tools/transport.py`](../../tools/transport.py). Do not independently read env to judge or recompute the transport ([§2](#2-explicit-statement-of-untouchable-premises-constraints)-2). This is the way to keep "SoT not modified" on the display side.
- **Do not threaten bit equivalence**: The startup report is **conversational output** and does not write to file. The bit-equivalence invariant governs *artifacts (settings / allowlist)*, not the human-facing 1-line report. Therefore, even if this 1 line is always shown under default renga, there is no effect on bit equivalence of artifacts (state this clearly to avoid confusion).
- **Relationship to the runtime drift line**: The existing `org-start` Step 4 has a mechanism to transcribe the drift line from `tools/check_runtime_version.py` at the end ([`.claude/skills/org-start/SKILL.md`](../../.claude/skills/org-start/SKILL.md) Block C2 / Step 4). Position the transport 1 line as an **independent, always-on line** of that (drift is a conditional warning; transport is an unconditional status display).

> **design only**: Actual reflection into the Step 4 template is out of scope. This design document does not modify the SKILL.

---

## 7. Mechanism (3): Policy for relegating raw env steps of the broker-dogfood-runbook to the appendix + adding PowerShell equivalents

### 7.1 Policy (do not modify the runbook body)

On the premise that the conversational interface in [§5](#5-mechanism-1-proxying-env-setup-and-child-pane-inheritance-via-the-conversational-interface) becomes the **main path**, define the policy of **relegating to the appendix as a last resort** the raw env steps of [`docs/operations/broker-dogfood-runbook.md`](../operations/broker-dogfood-runbook.md) (prepending `ORG_TRANSPORT=broker python3 ...`, rolling back with `unset ORG_TRANSPORT`, etc.). The intent is to give the runbook the following priority order:

1. **Main path**: Conversational interface ("start with broker" / "go back to renga").
2. **Appendix / last resort**: Direct raw env manipulation (limited to scenes where the user explicitly requires low-level control, such as when the conversational IF is unavailable / debugging / CI / automation).

Relegation is not "deletion" — raw env remains as a legitimate control point of the resolution order ([§2](#2-explicit-statement-of-untouchable-premises-constraints)-2) and continues to be accurately documented in the runbook's appendix. **This design document only states this policy and does not edit the runbook body** (design only).

### 7.2 PowerShell equivalents (proposed mapping table to attach to the appendix)

The current runbook's env operations assume bash (`export` / `unset` / `kill -INT`). The policy is to also write the Windows (PowerShell) equivalents in the appendix. Proposed mapping table:

| Operation | bash (current runbook) | PowerShell (proposed equivalent) |
|---|---|---|
| Make broker take effect **only for 1 command** (child-process-only) | `ORG_TRANSPORT=broker python3 ...` (affects only that 1 process; does not remain in shell) | **There is no equivalent prepend form in PowerShell**. `$env:ORG_TRANSPORT = "broker"` rewrites the session env and persists; therefore either **explicitly unset after execution** as in `$env:ORG_TRANSPORT = "broker"; python ...; Remove-Item Env:\ORG_TRANSPORT`, or if child-process-only is mandatory, pass via `Start-Process -Environment` etc. only to the started process (note that bash's child-only equivalent cannot be written obviously) |
| Set broker in this session (remain thereafter) | `export ORG_TRANSPORT=broker` | `$env:ORG_TRANSPORT = "broker"` |
| Check current value | `echo "$ORG_TRANSPORT"` | `$env:ORG_TRANSPORT` |
| Rollback (unset) | `unset ORG_TRANSPORT` | `Remove-Item Env:\ORG_TRANSPORT` (to not error on unset: `Remove-Item Env:\ORG_TRANSPORT -ErrorAction SilentlyContinue`) |
| Stop daemon (SIGINT to foreground serve) | `kill -INT <pid>` | If foreground, `Ctrl+C`. PID-specified stop is `Stop-Process -Id <pid>` (note that SIGINT-equivalent graceful stop is generally difficult on Windows, so foreground `Ctrl+C` is the main means) |

> **Note (non-equivalence of prepend form, important)**: bash's `VAR=val cmd` passes env **only to the started child process** and does not leave it in the shell itself. PowerShell's `$env:VAR = "val"` **rewrites the current session env** and remains for subsequent starts until explicitly unset. Treating them as equivalent makes Windows users unintentionally leave broker behind, so the appendix should state "in PowerShell, set → run → unset (or `Start-Process -Environment`)".

> **Note (resolution order invariance)**: The PowerShell equivalent is an addition of notation; it does not affect resolution order / SoT / bit equivalence (`$env:ORG_TRANSPORT` only places a value in the same env layer as bash's `ORG_TRANSPORT`).
>
> **Note (alignment with the Windows guidance in CLAUDE.local.md)**: On Windows environments in this repository, Python is `py -3` or `python`. The appendix's PowerShell examples should follow this as well (in environments without direct `python3`, use `python` / `py -3`).

> **design only**: The mapping table above is a **proposal** for the runbook appendix; this design document does not edit the runbook.

---

## 8. Independence from Issue G Track 3

Make explicit the boundary between this design (UX layer of switching) and Epic #6 Issue G Track 3 (production ja broker real-run / dogfood execution):

- **What this design handles**: **Human-engineering of transport selection** — switching by conversation, visualization of the current track, the policy for relegating raw env steps. A layer that presents / records / displays choices, holding whichever of renga / broker is picked.
- **What this design does not handle**: broker daemon startup / lifecycle / dogfood real-run / execution of the rollback conditions (these are within the scope of [`docs/operations/broker-dogfood-runbook.md`](../operations/broker-dogfood-runbook.md) and Track 3).
- **Dependency**: This design **does not depend on Track 3** (the conversational IF / visualization / runbook policy can be designed and implemented without a broker real-run). Conversely, it **does not block Track 3** (Track 3 can proceed as-is on the raw env path; the conversational IF only layers the main path and does not block the raw env path — [§7.1](#71-policy-do-not-modify-the-runbook-body)). The two can proceed independently.

---

## 9. Residual risks and implementation-time verification items

| Item | Notes |
|---|---|
| **Empirical child-pane env inheritance behavior ([§5.3](#53-propagation-chain-secretary--dispatcher--worker))** | Whether the child pane started via `spawn_claude_pane` inherits the caller env (as modified mid-session) **requires empirical verification**. This design does not bet on inheritance and proposes persisted choice ([§5.4](#54-the-proposed-persisted-choice-mechanism)), but the concrete path by which the startup sequence reflects the persisted choice into env should be verified at implementation |
| **Persistence-choice location and Set C alignment** | The storage destination of the persisted choice (part of existing state or dedicated configuration) and format are decided at implementation. If newly placed under `.state/`, an amendment proposal to the inventory of [`docs/contracts/state-schema-contract.md`](../contracts/state-schema-contract.md) Set C is needed (this design document does not make that amendment) |
| **Conversational-trigger vocabulary ambiguity** | Natural language like "start with broker" can be ambiguous. Before the Secretary finalizes the choice, ensure that broker is opt-in / rollback-safe and the current track can be confirmed (the inquiry path in [§6](#6-mechanism-2-always-on-1-line-visualization-of-the-current-transport-in-the-org-start-startup-report)). Normativization is out of scope |
| **Inconsistency between generation-time bake and display** | The transport baked into the artifact by the generator ([§5.2](#52-two-propagation-surfaces) (A)) and the display in the startup report ([§6](#6-mechanism-2-always-on-1-line-visualization-of-the-current-transport-in-the-org-start-startup-report)) are guaranteed consistent by consuming the same `resolve()`. If both judge the transport via separate paths, they may drift, so the display must always consume the SoT ([§6.2](#62-alignment-with-untouchable-constraints)) |

---

## Revision history

- 2026-06-11: First version (design only; UX design of Issue #535 "Make transport switching conversational"). Designed hiding raw env `ORG_TRANSPORT` (proxy env setup / child-pane inheritance by the conversational IF / persisted-choice proposal), always-on 1-line visualization of the current transport in the `org-start` startup report, and the policy for relegating raw env steps of the broker-dogfood-runbook to the appendix + PowerShell equivalents. Under the untouchable constraints (default renga = bit equivalence / resolution order and SoT invariant / Issue G Track 3 independence), fixed as the central thesis that the conversational IF is a thin layer layered on top of the `resolve()` chain. Does not touch normative documents / runbook / runtime (one-way reference only).
