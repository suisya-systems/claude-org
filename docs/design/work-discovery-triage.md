# Autonomous work-discovery (Issue triage) — Design

> Status: **Phases 1-4 implemented (in operation).** This design has been implemented and wired up along the staged rollout plan in [§9](#9-staged-rollout-and-verification-proposal). The artifacts (all paths relative to the repo root):
> - **Phase 1 — Compute layer**: [`tools/work_discovery_scan.py`](../../tools/work_discovery_scan.py) (read-only scan, candidate JSON on stdout, exit-code branching).
> - **Phase 2 — Option B manual entry**: [`.claude/skills/work-discovery/SKILL.md`](../../.claude/skills/work-discovery/SKILL.md) (the Lead invokes it manually or on events to present candidates).
> - **Phase 3 — Option C standing trigger**: wiring that runs the scan at worker close and forwards the result to the Lead ([`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md) and other dispatcher prose).
> - **Phase 4 — post-merge integration**: candidate generation for proactive next-dispatch is replaced with the triage output ([`CLAUDE.md`](../../CLAUDE.md) "Next-task proposals after a PR merge" and [`.claude/skills/org-pull-request/SKILL.md`](../../.claude/skills/org-pull-request/SKILL.md) 2b-iii).
>
> **The body below retains the original design wording as-is.** Phrasings such as "not implemented", "(unimplemented) proposal", "proposed tool", or "this design defines only the interface and does not implement it" reflect the **framing at design time**; the actual artifacts now exist at the paths listed above. The invariants in [§7](#7-safety-rails-invariants) (INV-1 through INV-5) are contracts that remain in force after implementation.
>
> Primary inputs:
> - [`.state/reports/loop-engineering-assessment.md`](../../.state/reports/loop-engineering-assessment.md) — **§5-1 (the only structural gap = no autonomous discovery of work)** and **§7(b) (introducing limited autonomous work-discovery as "auto up to proposal, the start decision stays with the human", +2-3 points)**.
> - Originating Issue: suisya-systems/claude-org-ja#520.
>
> Dependent documents (at design time, references flowed only one way, from this design to existing documents. After implementation, in Phases 2/4, references from [`CLAUDE.md`](../../CLAUDE.md), [`.claude/skills/work-discovery/SKILL.md`](../../.claude/skills/work-discovery/SKILL.md), and [`.claude/skills/org-pull-request/SKILL.md`](../../.claude/skills/org-pull-request/SKILL.md) back to this design have been added):
> - [`CLAUDE.md`](../../CLAUDE.md) (Lead = the only point of contact with humans / all implementation work is delegated / proactive next-dispatch / role boundaries)
> - [`.claude/skills/org-delegate/SKILL.md`](../../.claude/skills/org-delegate/SKILL.md) (the canonical path for starting work = from Step 0 after the human gate)
> - [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py) and [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md) (on-demand spawn at worker close = the delivery precedent for this design)
> - [`.dispatcher/CLAUDE.md`](../../.dispatcher/CLAUDE.md) (the dispatcher's role boundary and monitoring `/loop`)
> - [`docs/journal-events.md`](../journal-events.md) (the journal event ledger)

---

## 1. Background and fixed constraints (premises this design does not overturn)

This organization's loop is **human-initiated**. The loop only turns once the user asks the Lead, and as `.state/reports/loop-engineering-assessment.md` §5-1 notes, there is no self-feeding loop that "scans the issue tracker, triages, and picks the next one". There is a proactive behavior of "suggest the next work after a merge", but **the candidate selection is by the human**, and even the suggestion itself is improvised on the spot by the Lead ([§2](#2-current-state-and-this-designs-relationship-to-it)).

This design materializes the lever from assessment §7(b) — **"automate Issue triage up to the proposal, keep the start decision human"**. The aim is **not** to take the human out of the loop. We raise only the autonomy of **discovery**, while **commitment (the start decision) remains at the human gate as before**.

The following three are fixed constraints that this design does not overturn.

1. **Lead = the only point of contact with humans** ([`CLAUDE.md`](../../CLAUDE.md)). The path by which the triage result reaches a human must always go through the Lead. The discovery mechanism must not reach humans (or human-visible surfaces on GitHub) directly.
2. **All implementation work is delegated; the secretary does not investigate** ([`CLAUDE.md`](../../CLAUDE.md)). The triage scan is designed as a **deterministic tool invocation**, not as "investigation" (in the same class of deterministic ops as [`tools/journal_append.sh`](../../tools/journal_append.sh) / `tools/pending_decisions.py` / [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py)). If deeper analysis of individual candidates is required (feasibility, design), that becomes a delegated worker task after the human gate.
3. **Do not increase comprehension debt** (assessment §5-2). Triage is a mechanism that **surfaces** "what could be done next"; it is not a mechanism that lets work be started by skipping past the human's comprehension. Propose-only is directly tied to this constraint ([§7](#7-safety-rails-invariants)).

## 2. Current state and this design's relationship to it

**Current behavior (implemented, in operation)**: once post-merge cleanup is finished after a PR is merged, the Lead — per the proactive next-dispatch policy in [`CLAUDE.md`](../../CLAUDE.md) — improvises `gh issue list` and similar, and presents 2-4 next-work candidates plus 1 recommendation to the human. This is **the Lead's improvisation**; the decision criteria (dependencies resolved, priority, effort) are not codified, and there is no reproducibility, coverage, or auditability. The trigger is also limited to "immediately after a PR merge"; discovery at the point the organization becomes idle is not performed.

**This design (unimplemented proposal)**: separate the improvisation above into a **deterministic triage compute layer** ([§3](#3-the-two-layer-structure-of-the-design) / [§4](#4-triage-criteria) / [§5](#5-output-format)) and a **delivery layer that triggers and routes it** ([§6](#6-comparison-of-the-three-delivery-options)). The post-merge proactive next-dispatch is then upgraded into one consumer of this triage result ([§8](#8-integration-with-post-merge-proactive-next-dispatch)). Until this design is implemented, the current improvised behavior changes nothing.

| Aspect | Current (improvised, implemented) | Proposed (triage mechanism, unimplemented) |
|---|---|---|
| Decision criteria | Implicit (the Lead's judgment) | Codified (dependencies resolved / priority / effort estimate, [§4](#4-triage-criteria)) |
| Output | Free-form, ad hoc each time | Structured schema (N candidates + 1 recommendation, [§5](#5-output-format)) |
| Trigger | Only immediately after PR merge | post-merge / worker close / manual by the Lead ([§6](#6-comparison-of-the-three-delivery-options)) |
| Start decision | Human (immediate pick by number) | Human (unchanged; propose-only made an invariant, [§7](#7-safety-rails-invariants)) |
| Audit | None | Reproducible from journal events + candidate JSON |

## 3. The two-layer structure of the design

Split triage into "**computation (which Issue is triaged how)**" and "**delivery (when, who runs it, and how it is delivered to a human)**". This is the skeleton of the design.

```
┌─ Compute layer (deterministic, delivery-independent) ─────────┐
│  Input: open Issues / Epics (via gh / rtk)                    │
│  Process: dependency-resolved check -> priority score -> effort estimate -> ranking │
│  Output: candidate JSON (N candidates + 1 recommendation, §5) │
│  Properties: zero side effects. Reads Issues only. No spawn / commit / PR at all │
└───────────────────────────────────────────────────────────────┘
            ▲ Three deliveries share the same tool
┌─ Delivery layer (3 options, §6) ───────────────────────────┐
│  A. Cron cloud routine                                     │
│  B. Local skill (manual / event-triggered by the Lead)     │
│  C. dispatcher-loop extension (on-demand at worker close)  │
│  Common: output always reaches the Lead -> Lead presents to human -> human selects │
└────────────────────────────────────────────────────────────┘
```

**Design implication**: by detaching the compute layer from delivery, the three options collapse from being exclusive choices into "different ways to invoke the same compute tool". The recommendation ([§6.4](#64-recommendation)) picks a single primary delivery, but with the compute layer unified to one, adding another delivery later does not destabilize triage semantics.

The concrete compute layer is, in this design, the proposed tool `tools/work_discovery_scan.py` (a pure-computation + JSON-stdout tool of the same class as [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py)). **This design document defines only the interface; it does not implement it.**

## 4. Triage criteria

The evaluation axes for candidate Issues take the three named by assessment §7(b) — **dependencies resolved / priority / effort estimate** — as primary criteria, plus two auxiliary axes. Each axis is computed by the compute layer from Issue metadata, and the contract is **that the same input produces the same output on each run (reproducibility)**. However, not every axis is determined by a straightforward read of metadata: `dependency` and `priority` (from labels / milestones) are deterministic, but `effort`, `parallelizable`, and `unblocked_by_recent_merge` involve **heuristic estimation**. The latter always have uncertainty flags attached in the output (`*_estimated` / `signals[]`) to make it explicit to the human that "this is a machine estimate, not an assertion" ([§4.4](#44-making-estimated-axes-uncertainty-explicit)). This lets us achieve both propose-only (even when an estimate is wrong, the start decision is the human's) and auditability (you can trace which signals drove the estimate).

### 4.1 Primary criteria

| Axis | Computation source (deterministic signals) | Value domain |
|---|---|---|
| **Dependencies resolved** (`dependency`) | Extract `Blocked by #N` / `Depends on #N` / `Requires #N` / task-list `- [ ] #N` from the Issue body / comments, and judge whether the referenced Issues/PRs are **all closed**. The `blocked` / `on-hold` labels are treated as unresolved immediately. | `resolved` / `blocked` (`blocked` is excluded from the candidate set and shown separately with reason) |
| **Priority** (`priority`) | Labels (`priority:high` / `p0`-`p2` etc.) > milestone > age (stale bonus or penalty is a policy choice). In repositories without a label scheme, computed from milestone and updated timestamp only. | `high` / `medium` / `low` |
| **Effort estimate** (`effort`) | Adopt labels such as `size:S/M/L` if present. Otherwise heuristically **estimate** `S/M/L` (body length / number of acceptance criteria / number of areas expected to change). Always attach `effort_estimated: true` to estimated values so the human is told "this is a machine estimate". | `S` / `M` / `L` (+ `effort_estimated` flag) |

### 4.2 Auxiliary axes (used for ranking)

| Axis | Use |
|---|---|
| **Parallelizability** (`parallelizable`) | Can it be started independently of other Issues and fill a free pane slot? Detection signal: the Issue does **not** reference any other open Issue via `Blocked by` / `Depends on` (= a leaf in the dependency graph). Directly aligned with [`CLAUDE.md`](../../CLAUDE.md)'s proactive policy of "fill the parallel slots with independent open issues". Raises the rank when there are free panes. **Heuristic** (implicit conflicts that do not appear in dependency notation cannot be detected) -> attach `parallelizable_estimated`. |
| **Unblocked by recent merge** (`unblocked_by_recent_merge`) | Is the Issue something that was unblocked by a recent merge / a natural follow-up? Detection signal: the Issue's `Blocked by` / `Depends on` references include "an Issue/PR closed by one of the most recent K merged PRs", or a recent merged PR references this Issue via `Refs #N` and the like. Most important for the upgrade in [§8](#8-integration-with-post-merge-proactive-next-dispatch). In a post-merge trigger this axis matters most. **Heuristic** ("conceptual follow-up" that does not appear in notation cannot be detected) -> attach `unblocked_by_recent_merge_estimated`. |

### 4.3 Ranking and how "one recommendation" is decided

Sort the candidate set (those with `dependency == resolved`) lexicographically by `(priority, unblocked_by_recent_merge, parallelizable fit, smallness of effort)` and return the top N (default N=3, configurable). **The single recommendation** is the top item, but always attach the reason for the recommendation (one sentence saying "why this and not the others"). To avoid the recommendation collapsing into "the top of the machine ranking", emit the recommendation rationale as a structured field (the `recommendation.reason` field in [§5](#5-output-format)), used as evidence when the Lead presents to the human.

> **Important**: the compute layer emits a "recommendation", but it is a **suggestion**, not a decision. The final selection is by the human ([§7](#7-safety-rails-invariants) INV-2). Auto-starting rank 1 is prohibited by design.

### 4.4 Making estimated axes' uncertainty explicit

`effort`, `parallelizable`, and `unblocked_by_recent_merge` involve heuristic estimation ([§4.1](#41-primary-criteria) / [§4.2](#42-auxiliary-axes-used-for-ranking)). Their output must always satisfy:

- Attach the corresponding `*_estimated: true` flag to the estimated value (`effort_estimated` / `parallelizable_estimated` / `unblocked_by_recent_merge_estimated`).
- Enumerate the raw signals that drove the estimate in `signals[]` (e.g., `"label:size:M"`, `"leaf in dependency graph"`, `"follow-up of #528 (merged)"`). The human can trace "why it was estimated that way".
- In the human-readable rendering ([§5.2](#52-human-readable-rendering-lead--human)), append `(estimated)` to estimated values.

This is a device to prevent a human from misreading "the machine has asserted this" and ceding the start decision to the mechanism (cognitive surrender, assessment §5). Operationally, it underpins INV-1 / INV-2.

## 5. Output format

The compute layer has two representations: a machine-readable JSON (the tool's stdout, consumed by the delivery layer), and a human-readable text the Lead uses to present to a human (plain text / markdown-compatible). The JSON is the SoT; the latter is a derived rendering.

### 5.1 Machine-readable JSON (tool stdout)

Modeled on the [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py) contract of "stdout is a single JSON object + branching by exit code".

```json
{
  "status": "candidates_found",
  "generated_for": "post_merge",
  "candidate_count": 1,
  "truncated_count": 0,
  "candidates": [
    {
      "issue": 531,
      "title": "...",
      "summary": "one-line summary (mechanically extracted from body)",
      "dependency": "resolved",
      "blocking_refs": [],
      "priority": "high",
      "effort": "S",
      "effort_estimated": true,
      "parallelizable": true,
      "parallelizable_estimated": true,
      "unblocked_by_recent_merge": true,
      "unblocked_by_recent_merge_estimated": true,
      "rank": 1,
      "signals": ["label:priority:high", "leaf in dependency graph", "follow-up of #528 (merged)"]
    }
  ],
  "recommendation": {
    "issue": 531,
    "reason": "Natural follow-up of recently merged #528, dependencies resolved, effort S, fills a free pane"
  },
  "excluded_blocked": [
    { "issue": 540, "blocking_refs": [537], "note": "excluded because #537 is still open" }
  ]
}
```

(The `candidates` above shows only one entry as an example. In reality `candidate_count` entries are listed in ascending `rank`. JSON does not allow comments, so no abbreviation notation is used.)

- `status`: `candidates_found` / `no_candidates` (zero candidates) / `error`.
- `candidate_count`: the actual length of `candidates[]`. `truncated_count`: the count of "dependencies-resolved-but-out-of-rank" candidates dropped from `candidates[]` due to the N cap (**required field**; do not omit even when `0`. This forbids silent truncation).
- The delivery side branches on the exit code. Following [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py), **do not assign meaning to `1`** (this collides with Python's default exit code on uncaught exceptions, which would cause a scan crash to be misread as "no candidates" and prevent the error from reaching the Lead). The assignment is `0` = no candidates (`no_candidates`), `10` = candidates exist (`candidates_found`), `2` = error. The delivery layer decides behavior by the exit code without depending on JSON parse failure (same policy as the curator threshold tool).
- `excluded_blocked` keeps "Issues excluded due to unresolved dependencies" with reasons. **No silent truncation** (both out-of-rank candidates via `truncated_count` and dependency-excluded ones via `excluded_blocked` are made auditable by the human).

### 5.2 Human-readable rendering (Lead -> human)

The form the Lead presents to the human. Compatible with the current proactive next-dispatch convention (2-4 candidates + 1 recommendation, immediate pick by number), so the human's operations do not change.

```text
Next-work candidates (triage result, proposal only / starting is your decision):

1. [Recommended] #531 ... (priority high / effort S(estimated) / dependencies resolved / parallelizable)
   └ Follow-up of recently merged #528. Fills a free pane.
2. #533 ... (priority medium / effort M(estimated) / dependencies resolved)
3. #529 ... (priority medium / effort S / dependencies resolved / parallelizable)

Excluded (unresolved dependencies): #540 (because #537 is open)

Please specify the one to start by number. After your start decision, /org-delegate will run.
```

- Prefix the recommendation with `[Recommended]`; only one.
- If effort is a machine estimate, always append `(estimated)`.
- Always state "proposal only / starting is your decision" each time (the operational manifestation of INV-1).
- Always show the excluded slot (auditability + the reassurance that "we looked at everything and picked N").

## 6. Comparison of the three delivery options

The compute layer ([§3](#3-the-two-layer-structure-of-the-design)) is the same. The difference is **who triggers it, when, and how it reaches the Lead**.

### 6.1 Option A: cron cloud routine

Put the triage scan on a cloud routine of the `schedule` family (a headless cloud agent that runs on cron).

- **Benefits**: true autonomous discovery on a time-based cadence even when the organization session is not running. Keeps running even when the machine is off.
- **Drawbacks (blocking adoption)**:
  1. **Violates the Lead boundary**: a cloud routine runs outside the organization's renga tabs and cannot inject results in-band into the Lead session. To deliver results to a human, it would have to write **directly** to GitHub (Issue comment / triage Issue) or to notifications, breaking "Lead = the only point of contact with humans". Routing back through the Lead would require a bridge to local anyway, canceling out the cron benefits.
  2. **Live state is invisible**: free-pane counts, in-flight workers, `.state/` / state.db are local and cannot be observed from the cloud. `parallelizable` / free-slot-filling decisions ([§4.2](#42-auxiliary-axes-used-for-ranking)) do not function.
  3. **Operational opacity + billing**: detection through presentation runs decoupled from the organization session, making audit and intervention hard. In addition, headless / Agent SDK families may consume a separate credit billing bucket (cost is not the deciding factor per this organization's policy, but combined with 1 and 2, there is no reason to adopt this).
- **Verdict**: **rejected**. The two issues of Lead boundary and live-state visibility are fatal.

### 6.2 Option B: local skill

A skill the Lead launches locally (provisionally `/work-discovery`). The skill calls the compute-layer tool, and the Lead presents the output to the human. **The initiator is limited to the Lead**: if an already-delegated worker were to start the search for the next work outside its own task, that would break "1 worker = 1 task = 1 scope" and "a separate concern goes from Step 0 of [`/org-delegate`](../../.claude/skills/org-delegate/SKILL.md)" ([`CLAUDE.md`](../../CLAUDE.md)).

- **Benefits**: naturally keeps the Lead boundary (Lead launches, Lead presents). Live state (free panes) can be seen locally. Good fit for manual on-demand use.
- **Drawbacks / cautions**:
  1. **Trigger is passive**: the Lead must consciously decide "when to run it". A standing `/loop` running on time would pollute raw logs and presentations on days with no change (same lesson as `skill-audit`'s "do not launch from a time-based /loop"). Therefore avoid the standing /loop and **limit to event triggers (post-merge / manual)**.
  2. **Who runs the scan**: if the Lead scans directly, it touches the "secretary does not investigate" boundary. Avoid this by confining the scan to a **deterministic tool** ([§1](#1-background-and-fixed-constraints-premises-this-design-does-not-overturn) constraint 2). If deeper analysis of a candidate is needed, delegate to a worker after the human gate.
- **Verdict**: **adopted (as the manual entry)**. However, alone it leaves the "when to run it" problem, so the standing trigger is delegated to Option C.

### 6.3 Option C: dispatcher-loop extension

Extend the already-resident dispatcher monitoring `/loop` (worker monitoring) and the on-demand spawn mechanism at worker close ([`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py) / [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md)) to run the triage scan **the moment a worker closes = a pane slot opens up**, and send the candidate JSON to the Lead via peer message.

- **Benefits**:
  1. **Reuse of an existing standing loop**: does not add a new resident process. Rides the same pattern as on-demand curator: "at worker close, run threshold/condition check -> launch only when the condition is met" (the implementation/operational cognitive cost is known).
  2. **Trigger is semantically correct**: fires at "pane opens = the timing where the next work can be put in". Naturally tied to idle detection too.
  3. **Has live state**: the dispatcher knows the pane topology and present workers, providing material for the `parallelizable` / free-slot-filling decision.
- **Drawbacks / cautions**:
  1. **Expansion of dispatcher role**: the dispatcher's principle is "act as the Lead's delegate; do not talk directly with humans" ([`.dispatcher/CLAUDE.md`](../../.dispatcher/CLAUDE.md)). Triage is a new responsibility, but the dispatcher **only runs a compute tool and forwards the candidate JSON to the Lead** — it does not touch the human or make a start decision. As long as the "dispatcher -> Lead -> human" path is preserved, the boundary is not broken.
  2. **Firing depends on worker close**: while workers are zero and the org is fully idle, it does not fire. Compensate this with Option B (manual).
- **Verdict**: **adopted (as the standing trigger)**.

### 6.4 Recommendation

**Recommendation: Option C as the standing trigger, Option B as the manual override, with both sharing the same compute-layer tool. Option A is rejected.**

| | Lead boundary | Live state visible | Trigger quality | Operational cost | Decision |
|---|---|---|---|---|---|
| A. cron cloud | x breaks | x invisible | o time-autonomous | △ separate billing / opaque | **rejected** |
| B. local skill | o | o | △ passive / manual | o | **adopted (manual)** |
| C. dispatcher-loop extension | o (Lead-routed) | o | o event-driven | o reuses existing loop | **adopted (standing)** |

Rationale: with the compute layer consolidated to one, "C as standing + B as manual" is just two entrances to the same tool, not a double implementation. C reuses the proven on-demand-curator pattern and is the only option satisfying the Lead boundary, live state, and trigger quality simultaneously. B plugs the holes at idle time or any arbitrary timing. A is structurally incompatible due to the Lead boundary and live state.

> This recommendation aligns perfectly with assessment §7(b)'s "auto up to the proposal, the start decision is the human's": **discovery (scan, ranking, presentation) is automated, judgment (selection, starting) is the human's**.

## 7. Safety rails (invariants)

The following are designated **invariants** of this mechanism. They must not be broken regardless of the delivery option or future extensions.

- **INV-1 — propose-only / stop at the proposal**: the mechanism's output is the ranked candidate list only. After emitting it, **stop**. No spawn, delegate, branch creation, commit, PR, or write to an Issue. The compute layer is read-only (only reads Issues; zero side effects).
- **INV-2 — start decision requires the human gate**: candidate selection is made by the human only. The chosen candidate enters the normal delegation flow **from Step 0 of the existing [`/org-delegate`](../../.claude/skills/org-delegate/SKILL.md)**. It is forbidden for the discovery mechanism to call org-delegate by itself. Auto-starting rank 1 (the recommendation) is also forbidden.
- **INV-3 — no auto-PR / no auto-commit**: this mechanism **does not change the source tree, Issues, PRs, or git (commit / branch / push) in any way**. Even if the operation is to commit the triage result to source, that is a separate task by human judgment and is not done by the mechanism automatically.
  - **Exception (= recording org state, not change)**: ordinary operational bookkeeping such as appending a journal event to the `.state/state.db` events table ([§7.1](#71-verifiability-of-the-invariants)) is out of scope of this INV. This is the same class of bookkeeping that all other roles routinely perform, and it does not change git history / source / GitHub. **The read-only compute-layer tool itself does not write to state.db either** ([§7.1](#71-verifiability-of-the-invariants) "ensuring zero side effects"). The separation that the delivery layer (Lead / dispatcher) writes journal entries — not the compute-layer tool — must be maintained.
- **INV-4 — Lead = the only point of contact with humans**: the triage result must always reach the Lead, and the Lead presents to the human. The discovery mechanism (dispatcher / cron / tool) must not directly reach a human or a human-visible surface on GitHub (the direct reason Option A was rejected).
- **INV-5 — all implementation work is delegated / the secretary does not investigate**: the scan is a deterministic tool invocation; it is not "investigation". If deeper feasibility / design work on a candidate is needed, treat it as a delegated worker task after the human gate. The Lead / dispatcher do not investigate or implement the content of a candidate themselves.

> These five mechanically guarantee what assessment §5-1 / §7(b) demands: "raise the autonomy of discovery without removing the human from the loop apex". In particular, **INV-1 + INV-2 are the core of "auto up to the proposal / human gate"**; INV-4 is what excludes Option A; INV-5 is the brake that does not increase comprehension debt (§5-2).

### 7.1 Verifiability of the invariants

- **Audit log**: record the scan execution, candidate count, and recommendation as a journal event (proposed kind example: `work_discovery_scanned` / payload `candidate_count` / `recommendation_issue` / `trigger`) so that "when, how many, what was recommended" can be retraced after the fact. The one doing the recording is the **delivery layer (Lead / dispatcher), not the read-only compute-layer tool** (the separation of the INV-3 exception). As [`docs/journal-events.md`](../journal-events.md) says, the SoT of events is the events table in `.state/state.db`, and emission goes through the DB-routed helpers (`tools/journal_append.sh` / `tools/journal_append.py`) (no more legacy `.state/journal.jsonl` direct writes or direct DB INSERTs). **Adding the proposed event to the ledger and wiring it up is out of scope of this design** (a separate task).
- **Ensuring zero side effects**: the compute-layer tool uses **only read-only APIs** like `gh issue list` / `rtk gh issue view`, and pins by tool contract (and future unit tests) that it does not call any write API or git operation.

## 8. Integration with post-merge proactive-next-dispatch

The current post-merge proactive next-dispatch (the policy in [`CLAUDE.md`](../../CLAUDE.md) + operational memory) has the Lead improvise `gh issue list` after a PR merge and emit candidates. We **upgrade this to a triage-result base**.

### 8.1 Integration approach

1. **Trigger convergence**: trigger the triage scan at the point where PR merge -> post-merge cleanup -> dispatcher CLOSE_PANE confirmation is done (the same moment as worker close in [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md)). Naturally overlaps with Option C's worker-close trigger.
2. **Improvisation -> structured**: instead of having the Lead run `gh issue list` itself, it receives the compute-layer tool's candidate JSON ([§5.1](#51-machine-readable-json-tool-stdout)) and presents to the human in the form of [§5.2](#52-human-readable-rendering-lead--human). The decision criteria (dependencies resolved / priority / effort) are codified, and reproducibility and auditability are added.
3. **Prioritize recent-merge-driven**: in the post-merge context, strongly weight the `unblocked_by_recent_merge` axis ([§4.2](#42-auxiliary-axes-used-for-ranking)) so that "natural follow-ups to the most recent merge" and "Issues unblocked by the most recent merge" (the proactive candidate patterns listed by operational memory) appear near the top. Put `generated_for: "post_merge"` into the JSON to make context explicit.
4. **Invariant of the human operation**: keep the presentation format and the "pick by number" experience compatible with the current behavior ([§5.2](#52-human-readable-rendering-lead--human)). The only change visible to the human is "the basis for candidates is explicit, and the exclusion reasons are visible".

### 8.2 Post-upgrade position

| | Current proactive next-dispatch | After upgrade |
|---|---|---|
| Candidate generation | Lead improvises `gh issue list` | Compute-layer tool (codified criteria) |
| Decision basis | Implicit | `dependency` / `priority` / `effort` + signals |
| Exclusion visibility | None | Presents `excluded_blocked` |
| Trigger | post-merge only | post-merge (converged with Option C) + manual (Option B) |
| Starting | Human (unchanged) | Human (unchanged) |
| Audit | None | journal `work_discovery_scanned` |

> The key to integration: **we do not abolish or replace proactive next-dispatch; we only swap its "candidate generation" part from improvisation to the triage mechanism**. The outer shape "Lead presents to human; human selects" is fully preserved (INV-2 / INV-4).

## 9. Staged rollout and verification (proposal)

Recommended order if implemented (this design document plans only; implementation of each phase is a separate task).

1. **Phase 1 — compute layer**: `tools/work_discovery_scan.py` (read-only, candidate JSON on stdout, exit-code branching, unit tests). Alone it has zero side effects and can be output-verified manually with `python3 tools/work_discovery_scan.py`.
2. **Phase 2 — Option B manual entry**: the path where the Lead manually launches and presents. Adding the skill involves `.claude/` edits, which is out of scope of this worker (a separate task).
3. **Phase 3 — Option C standing trigger**: wiring that runs the scan at worker close and forwards to the Lead (involves prose updates of [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md) / [`.dispatcher/CLAUDE.md`](../../.dispatcher/CLAUDE.md)).
4. **Phase 4 — post-merge integration**: the upgrade in §8. Swap proactive next-dispatch candidate generation to the triage output.

Each phase is reviewed at its gate to confirm that INV-1 through INV-5 are not broken. In particular, "is it read-only?" and "is the human gate not being skipped?" are verified per phase.

## 10. Out of scope / future work

- **Auto-starting**: out of scope of this design (permanently forbidden by INV-1 / INV-2). As assessment §5 says, "keeping the human at the apex of the loop" is the fixed policy of this organization.
- **Cross-repository triage**: dependency resolution across multiple repositories (runtime / ja / renga, etc.) is assumed to be single-repository in this design. Future extension.
- **More sophisticated effort estimation**: the effort in §4.1 is a heuristic. Learning from actual effort on past PRs is future work.
- **Concrete implementation of `.claude/` skill, `.dispatcher/` prose, and `tools/`**: this worker is DESIGN ONLY. All separate tasks.
- **Ledger entry and wiring of the proposed journal event**: ledger updates for `work_discovery_scanned` etc. in [`docs/journal-events.md`](../journal-events.md) and emit wiring are implementation-task side.

## 11. Open points (require human judgment before implementation)

1. **Default value of N**: candidate cap set to N=3 default, but is it variable by free pane count (free slots = N) or fixed?
2. **Priority label scheme**: it is unconfirmed to what extent the Issues in this repository carry a `priority:*` / `p0..p2` label scheme. If absent, the priority computation in §4.1 degenerates to milestone + updated timestamp. Confirm the actual label distribution before implementation.
3. **Variance in dependency notation**: which notations — `Blocked by` / `Depends on` / task list, etc. — are actually used in this repository's Issues? The extraction patterns must be calibrated on real data (to avoid over-matching that misclassifies as blocked -> unjustly excludes from candidates).
4. **Idle-time trigger**: at full idle with zero workers, Option C does not fire. Whether to add a lightweight trigger beyond Option B manual (e.g., "scan once at Lead startup") is an operational judgment.
