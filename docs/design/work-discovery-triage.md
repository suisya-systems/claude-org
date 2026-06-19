# Autonomous work-discovery (Issue triage) — Design

> Status: **Phase 1 through 4 implemented (in operation)**. This design has been implemented and wired according to the staged rollout plan in [§9](#9-staged-rollout-and-verification-proposal). Implementations (all paths relative to repository root):
> - **Phase 1 — Compute layer**: [`tools/work_discovery_scan.py`](../../tools/work_discovery_scan.py) (read-only scan, candidate JSON to stdout, exit-code branching).
> - **Phase 2 — Plan B manual entry**: [`.claude/skills/work-discovery/SKILL.md`](../../.claude/skills/work-discovery/SKILL.md) (Secretary starts manually / on event and presents).
> - **Phase 3 — Plan C steady trigger**: wiring that launches scan on worker close and forwards to Secretary ([`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md) and other dispatcher prose).
> - **Phase 4 — post-merge integration**: candidate generation for proactive next-dispatch is replaced by triage output ([`CLAUDE.md`](../../CLAUDE.md) "Next-task proposal after PR merge" and [`.claude/skills/org-pull-request/SKILL.md`](../../.claude/skills/org-pull-request/SKILL.md) 2b-iii).
>
> **The body below preserves the original design text as-is.** Expressions in the body such as "not yet implemented", "(unimplemented) proposal", "proposed tool", and "this design defines only the interface; implementation is out of scope" are **framing at design time**; the actual implementations now exist at the paths above. The invariants in [§7](#7-safety-rails-invariants) (INV-1 through INV-5) are contracts that are preserved after implementation.
>
> Primary inputs:
> - [`.state/reports/loop-engineering-assessment.md`](../../.state/reports/loop-engineering-assessment.md) **§5-1 (the sole structural gap = no autonomous discovery of work)** and **§7(b) (introduce limited autonomous work-discovery as "automate up to proposal, keep commitment as a human gate", +2 to +3 points)**.
> - originating Issue: suisya-systems/claude-org-ja#520.
>
> Dependent documents (at design time this was a one-way reference from this design to existing documents only. Post-implementation, Phases 2/4 added references from [`CLAUDE.md`](../../CLAUDE.md) and [`.claude/skills/work-discovery/SKILL.md`](../../.claude/skills/work-discovery/SKILL.md) / [`.claude/skills/org-pull-request/SKILL.md`](../../.claude/skills/org-pull-request/SKILL.md) back to this design):
> - [`CLAUDE.md`](../../CLAUDE.md) (Secretary = sole human contact / full delegation of real work / proactive next-dispatch / role boundaries)
> - [`.claude/skills/org-delegate/SKILL.md`](../../.claude/skills/org-delegate/SKILL.md) (canonical commitment path = Step 0 onward after the human gate)
> - [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py) and [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md) (on-demand spawn at worker close = delivery precedent for this design)
> - [`.dispatcher/CLAUDE.md`](../../.dispatcher/CLAUDE.md) (dispatcher role boundary and monitoring /loop)
> - [`docs/journal-events.md`](../journal-events.md) (journal event ledger)

---

## 1. Background and fixed constraints (premises this design does not overturn)

This organization's loop is **human-triggered**. The loop only spins when a user asks the Secretary, and as `.state/reports/loop-engineering-assessment.md` §5-1 points out, there is no self-feeding loop that "scans an issue tracker, triages, and picks the next item". A proactive behavior of "propose the next item after a merge" exists, but **candidate selection is human**, and that proposal itself is improvised on the spot by the Secretary ([§2](#2-current-state-and-this-designs-relation-to-it)).

This design concretizes the lever in assessment §7(b) —— **"Automate Issue triage up to proposal; keep the commitment decision human"**. The aim is **not** to "take the human out of the loop". It raises only the autonomy of discovery and **keeps the commitment decision behind the existing human gate**.

The following three points are fixed constraints this design does not overturn.

1. **Secretary = sole human contact** ([`CLAUDE.md`](../../CLAUDE.md)). The path by which triage results reach the human must always go through the Secretary. The discovery mechanism must not reach the human (or any human-visible surface on GitHub) directly.
2. **All real work is delegated; the Secretary does not investigate** ([`CLAUDE.md`](../../CLAUDE.md)). The triage scan is designed not as "investigation" but as **deterministic tool execution** (deterministic ops on par with [`tools/journal_append.sh`](../../tools/journal_append.sh) / `tools/pending_decisions.py` / [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py)). Deep dives per candidate (feasibility check, design) become delegated worker tasks after the human gate.
3. **Do not increase comprehension debt** (assessment §5-2). Triage is a mechanism that **visualizes** "what could be done next"; it is not a mechanism that skips the human's comprehension and proceeds to commitment. propose-only is directly connected to this constraint ([§7](#7-safety-rails-invariants)).

## 2. Current state and this design's relation to it

**Current behavior (implemented, in operation)**: After post-merge cleanup following a PR merge, the Secretary follows the proactive next-dispatch policy in [`CLAUDE.md`](../../CLAUDE.md) and improvises by running `gh issue list` etc. on the spot to present 2 to 4 next-work candidates plus 1 recommendation to the human. This is **Secretary improvisation**: the judgment criteria (dependency resolved? priority? effort?) are not codified, and there is no reproducibility, coverage, or auditability. The trigger is also limited to "right after a PR merge", and discovery at the moment the organization becomes idle does not happen.

**This design (unimplemented proposal)**: separate the above improvisation into a **deterministic triage compute layer** ([§3](#3-the-two-layer-structure-of-the-design) / [§4](#4-triage-criteria) / [§5](#5-output-format)) and a **delivery layer that launches and delivers it** ([§6](#6-delivery-method-3-option-comparison)). post-merge proactive next-dispatch is promoted to one consumer of this triage result ([§8](#8-integration-with-post-merge-proactive-next-dispatch)). Until this design is implemented, current improvisation behavior does not change at all.

| Aspect | Current (improvisation, implemented) | Proposal (triage mechanism, unimplemented) |
|---|---|---|
| Judgment criteria | Implicit (Secretary's judgment) | Codified (dependency resolved / priority / effort estimate, [§4](#4-triage-criteria)) |
| Output | Free-form each time | Structured schema (N candidates + 1 recommendation, [§5](#5-output-format)) |
| Trigger | Only right after a PR merge | post-merge / worker close / Secretary manual ([§6](#6-delivery-method-3-option-comparison)) |
| Commitment decision | Human (instant by number) | Human (no change. propose-only as invariant, [§7](#7-safety-rails-invariants)) |
| Audit | None | Reproducible via journal events + candidate JSON |

## 3. The two-layer structure of the design

Split triage into "**compute (which Issues are triaged how)**" and "**delivery (when, who runs, and how it reaches the human)**". This is the skeleton of this design.

```
+- Compute layer (deterministic, delivery-independent) ------+
|  Input: open Issues / Epics (via gh / rtk)                 |
|  Process: dependency resolution -> priority score          |
|           -> effort estimate -> ranking                    |
|  Output: candidate JSON (N candidates + 1 recommended, §5) |
|  Property: zero side effects. Reads Issues only.           |
|            Never spawn / commit / PR.                      |
+------------------------------------------------------------+
            ^ the same tool is shared by 3 deliveries
+- Delivery layer (3 options, §6) --------------------------+
|  A. cron cloud routine                                    |
|  B. local skill (Secretary manual / event-triggered)      |
|  C. dispatcher-loop extension (on-demand at worker close) |
|  Common: output always reaches Secretary                  |
|          -> Secretary presents to human                   |
|          -> human chooses                                 |
+-----------------------------------------------------------+
```

**Design implication**: by decoupling the compute layer from delivery, the 3 options converge to "how to launch the same compute tool" rather than mutually exclusive choices. The recommendation ([§6.4](#64-recommendation)) picks a single primary delivery, but as long as the compute layer is consolidated into one body, adding another delivery later does not perturb triage semantics.

The body of the compute layer is, in this design, the proposed tool `tools/work_discovery_scan.py` (a pure-compute + JSON-to-stdout tool on par with [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py)). **This design defines only the interface; implementation is out of scope.**

## 4. Triage criteria

Use the 3 axes that assessment §7(b) lists —— **dependency resolved / priority / effort estimate** —— as primary criteria, and add 2 auxiliary axes. Each axis is computed by the compute layer from Issue metadata, and the contract is that **the same input yields the same output across runs (reproducibility)**. However, not all axes are determined by "straightforward reading of metadata": `dependency` and `priority` (label/milestone-derived) are deterministic, but `effort` / `parallelizable` / `unblocked_by_recent_merge` include **heuristic estimation**. The latter must always be accompanied by uncertainty flags (`*_estimated` / `signals[]`) in the output to make clear to the human "this is a machine estimate, not an assertion" ([§4.4](#44-uncertainty-disclosure-for-estimated-axes)). This jointly satisfies propose-only (commitment is human even if the estimate is off) and auditability (which signals drove the estimate are traceable).

### 4.1 Primary criteria

| Axis | Computed from (deterministic signals) | Range |
|---|---|---|
| **Dependency resolved** (`dependency`) | Extract `Blocked by #N` / `Depends on #N` / `Requires #N` / task list `- [ ] #N` from Issue body / comments, and judge whether the referenced Issues/PRs are **all closed**. `blocked` / `on-hold` labels are treated as unresolved immediately. | `resolved` / `blocked` (blocked is excluded from candidates and shown separately with reason) |
| **Priority** (`priority`) | Labels (`priority:high` / `p0` through `p2` etc.) > milestone > days elapsed (stale boost or penalty per policy). For repos without a label scheme, compute from milestone and update time only. | `high` / `medium` / `low` |
| **Effort estimate** (`effort`) | Use `size:S/M/L` style labels if present. Otherwise **estimate** `S/M/L` heuristically (body length / number of acceptance criteria / expected number of changed areas). Estimated values must carry `effort_estimated: true` to make "this is a machine estimate" explicit to the human. | `S` / `M` / `L` (+ `effort_estimated` flag) |

### 4.2 Auxiliary axes (used for ranking)

| Axis | Use |
|---|---|
| **Parallelizable** (`parallelizable`) | Whether the Issue can be started independently of other Issues and can fill an open pane slot. Decision signal: the Issue does **not** reference other open Issues via `Blocked by` / `Depends on` (= leaf in the dependency graph). Directly connected to the [`CLAUDE.md`](../../CLAUDE.md) proactive policy of "fill parallelism with independent open issues". Boost rank when there is a free pane. **Heuristic** (implicit conflicts not expressed in dependency notation cannot be detected) -> attach `parallelizable_estimated`. |
| **Unblocked by recent merge** (`unblocked_by_recent_merge`) | Whether the Issue was unblocked by a recent merge / becomes a natural follow-up. Decision signal: the Issue's `Blocked by` / `Depends on` references include "Issues/PRs closed by the most recent K merged PRs", or a recent merged PR references this Issue via `Refs #N` etc. Most important for the [§8](#8-integration-with-post-merge-proactive-next-dispatch) promotion. This axis is dominant in the post-merge trigger. **Heuristic** (conceptual "follow-ups" not expressed in notation cannot be detected) -> attach `unblocked_by_recent_merge_estimated`. |

### 4.3 Ranking and deciding the "single recommendation"

Sort the candidate set (those with `dependency == resolved`) lexicographically by `(priority, unblocked_by_recent_merge, parallelizable fit, smallness of effort)` and return the top N (default N=3, configurable). The **single recommendation** is the top item, but always attach a reason ("why this one and not the others", in one sentence). To prevent the recommendation from becoming just the machine ranking as-is, output the recommendation rationale as a structured field (the `recommendation.reason` in [§5](#5-output-format)) and use it as the basis for the Secretary's presentation to the human.

> **Important**: the compute layer emits a "recommendation", but it is a **proposal**, not a decision. Final selection is human ([§7](#7-safety-rails-invariants) INV-2). Auto-committing to rank 1 is forbidden by design.

### 4.4 Uncertainty disclosure for estimated axes

`effort` / `parallelizable` / `unblocked_by_recent_merge` include heuristic estimation ([§4.1](#41-primary-criteria) / [§4.2](#42-auxiliary-axes-used-for-ranking)). The output must always satisfy the following for them:

- Attach the corresponding `*_estimated: true` flag to the estimated value (`effort_estimated` / `parallelizable_estimated` / `unblocked_by_recent_merge_estimated`).
- List the raw signals that grounded the estimate in `signals[]` (e.g. `"label:size:M"`, `"leaf in dependency graph"`, `"follow-up of #528 (merged)"`). The human can trace "why this was estimated this way".
- In the human-readable rendering ([§5.2](#52-human-readable-rendering-secretary--human)), append `(estimated)` to estimated values.

This is a device to prevent the human from misreading "the machine asserted this" and surrendering commitment to the mechanism (cognitive surrender, assessment §5), and operationally supports INV-1 / INV-2.

## 5. Output format

The compute layer has 2 representations: machine-readable JSON (tool stdout, consumed by the delivery layer), and human-readable text (plain text / markdown-compatible) that the Secretary uses to present to the human. JSON is the SoT; the latter is derived rendering.

### 5.1 Machine-readable JSON (tool stdout)

Follows the contract of [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py): "stdout is a single JSON object, exit code branches".

```json
{
  "status": "candidates_found",
  "generated_for": "post_merge",
  "candidate_count": 1,
  "truncated_count": 0,
  "effort_model": null,
  "candidates": [
    {
      "repo": "suisya-systems/claude-org-ja",
      "issue": 531,
      "title": "...",
      "summary": "one-line summary (machine-extracted from body)",
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
    "repo": "suisya-systems/claude-org-ja",
    "issue": 531,
    "reason": "natural follow-up of recently merged #528; dependency resolved; effort S; fills a free pane"
  },
  "excluded_blocked": [
    { "repo": "suisya-systems/claude-org-ja", "issue": 540, "blocking_refs": [537], "note": "excluded because #537 is open" }
  ]
}
```

(The `candidates` above shows only 1 entry for illustration. In reality `candidate_count` entries appear in ascending `rank`. JSON does not allow comments, so ellipsis notation is not used.)

- `status`: `candidates_found` / `no_candidates` (zero candidates) / `error`.
- `repo` (each entry in candidates / recommendation / excluded): identifies the originating repository (`owner/repo`) of the candidate for cross-repository triage ([§10](#10-cross-repository-triage-implemented)). For single-repository scans (`--repo` omitted or specified once) it is `null`. The `(repo, issue)` pair is the identity of a candidate, so `ja#60` and `runtime#60` do not collide.
- `blocking_refs` (candidates / excluded): canonical representation of dependency references. References to the home repository are raw integers `N` (backward compatibility); cross-repository references are strings `"owner/repo#N"` (the two can be mixed).
- `candidate_count`: actual number in `candidates[]`. `truncated_count`: the number of "dependency-resolved but out-of-rank" candidates dropped from `candidates[]` by the N-item cap (**required field**. Do not omit even if `0`. This forbids silent truncation).
- The delivery side branches on exit code. Following [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py), **do not give meaning to `1`** (exit `1` is the default Python returns on uncaught exceptions; conflating it would let scan crashes be misread as "no candidates" and prevent errors from reaching the Secretary). Assignments: `0` = no candidates (`no_candidates`), `10` = candidates exist (`candidates_found`), `2` = error. The delivery layer decides behavior via exit code, not by relying on JSON-parse failure (same policy as the curator threshold tool).
- `excluded_blocked` retains "Issues excluded due to unresolved dependencies" with reasons. **No silent truncation** (`truncated_count` surfaces the existence of out-of-rank candidates, and `excluded_blocked` surfaces dependency-based exclusions; both are auditable by the human).
- `effort_model`: summary of the learned effort model ([§10](#10-out-of-scope--future-work) Effort estimation sophistication), or `null` when learning is disabled / offline. Because the **schema is fixed**, `effort_model` is always one of `null | object`; in object form it carries `sample_size` / `applies` (whether the data-driven gate may override) / `predictor_correlation` / `realized_cutpoints` / `realized_median_lines` / `coverage` (training-data coverage: number of single-issue-linked PRs, adopted samples, samples dropped due to missing body) / `reason`, etc. When `applies==false`, static heuristics are maintained, and each candidate's `signals[]` makes the reason and actual-effort context explicit. In this repository, body length does not correlate with realized effort, so this is always `applies==false` (gated OFF).

### 5.2 Human-readable rendering (Secretary -> human)

The form the Secretary presents to the human. Compatible with the current proactive next-dispatch practice (2 to 4 candidates + 1 recommendation, instant choice by number) so that the human's operation does not change.

```text
Next-work candidates (triage result / proposal only / commitment is your call):

1. [Recommended] #531 ... (priority high / effort S (estimated) / dependency resolved / parallelizable)
   `- Follow-up of recently merged #528. Fills a free pane.
2. #533 ... (priority medium / effort M (estimated) / dependency resolved)
3. #529 ... (priority medium / effort S / dependency resolved / parallelizable)

Excluded (dependency unresolved): #540 (because #537 is open)

Specify the one to start by number. After your commitment, /org-delegate kicks in.
```

- Prefix the recommendation with `[Recommended]`, one entry only.
- If effort is a machine estimate, always append `(estimated)`.
- Make "proposal only / commitment is your call" explicit every time (the operational expression of INV-1).
- Always show the excluded section (auditability + the assurance of "N items after seeing everything").
- **In cross-repository scan ([§10](#10-cross-repository-triage-implemented))**: when the candidate's `repo` is not `null` (multi-repo cross), display `repo#N` (e.g. `runtime#531`) instead of `#N` to remove ambiguity of origin repo. For single-repo scans (`repo: null`), use the conventional `#N`. The delivery layer (Secretary skill) implements this rendering branch (out of scope for the compute-layer worker; separate task, same as [§9](#9-staged-rollout-and-verification-proposal), since it involves `.claude/` edits).

## 6. Delivery method 3-option comparison

The compute layer ([§3](#3-the-two-layer-structure-of-the-design)) is identical. The differences are **who launches when and how it reaches the Secretary**.

### 6.1 Option A: cron cloud routine

Mount the triage scan on a `schedule`-family cloud routine (a headless cloud agent that runs on cron).

- **Benefit**: true autonomous discovery on a time basis, runs even when the organization session is not started. Runs even when the machine is off.
- **Drawbacks (blocking adoption)**:
  1. **Violation of the Secretary boundary**: cloud routines run outside the organization's renga tab and cannot inject results into the Secretary session in-band. To reach the human, results have to be written **directly** to GitHub (Issue comment / triage Issue) or to a notification, which breaks "Secretary = sole human contact". To route back through the Secretary you still need a bridge to local, which cancels the benefit of cron.
  2. **Cannot see live state**: free pane count, in-flight workers, `.state/` / state.db are local and unobservable from the cloud. The judgment for `parallelizable` / filling free slots ([§4.2](#42-auxiliary-axes-used-for-ranking)) does not work.
  3. **Operational opacity + billing**: detection-to-presentation runs detached from the organization session, making auditing and intervention hard. It may also sit in a separate credit billing tier for headless / Agent SDK paths (cost is not a deciding factor in this organization's policy, but combined with 1 / 2 above there is no reason to adopt).
- **Verdict**: **rejected**. The Secretary boundary and live-state visibility are fatal.

### 6.2 Option B: local skill

A skill launched locally by the Secretary (e.g. tentatively `/work-discovery`). The skill calls the compute-layer tool and the Secretary presents the output to the human. The launcher is **restricted to the Secretary**: if a delegated worker launches next-work discovery outside its task, it breaks "1 worker = 1 task = 1 scope" and "side items go through Step 0 of [`/org-delegate`](../../.claude/skills/org-delegate/SKILL.md)" ([`CLAUDE.md`](../../CLAUDE.md)).

- **Benefit**: the Secretary boundary is preserved naturally (Secretary launches, Secretary presents). Live state (free panes) is visible locally. Good fit for manual on-demand.
- **Drawbacks / cautions**:
  1. **Passive trigger**: the Secretary needs to be aware of "when to run it". A residential `/loop` that fires on time pollutes the raw log / presentation on days with no change (same root as the `skill-audit` lesson that "do not start on a time-based /loop"). Therefore avoid residential /loop and **restrict to event triggers (post-merge / manual)**.
  2. **Who runs the scan**: if the Secretary scans directly, it brushes against the "Secretary does not investigate" boundary. This is avoided by confining the scan to a **deterministic tool** ([§1](#1-background-and-fixed-constraints-premises-this-design-does-not-overturn) constraint 2). Deep-dive candidates are delegated to workers after the human gate.
- **Verdict**: **adopted (as the manual entry)**. However, the "when to run" problem remains in isolation, so leave the steady trigger to Option C.

### 6.3 Option C: dispatcher-loop extension

Extend the already-residential dispatcher monitoring `/loop` (worker monitoring) and the on-demand spawn mechanism at worker close ([`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py) / [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md)) so that **at worker close = the moment a pane slot opens** the triage scan runs and the candidate JSON is sent to the Secretary via peer message.

- **Benefits**:
  1. **Reuse of existing residential loop**: no new residential process. Rides exactly the same "at worker close, check threshold/condition -> start only if condition holds" pattern as the on-demand curator (the cognitive cost for implementation and operation is known).
  2. **Semantically correct trigger**: fires at "a pane opened = a moment one can put in the next item". Naturally tied to idle detection.
  3. **Holds live state**: the dispatcher knows pane topology and resident workers, providing material to judge `parallelizable` / free-slot filling.
- **Drawbacks / cautions**:
  1. **Role extension of the dispatcher**: by principle the dispatcher "acts on behalf of the Secretary's DELEGATE; does not directly talk to the human" ([`.dispatcher/CLAUDE.md`](../../.dispatcher/CLAUDE.md)). Triage is a new responsibility, but the dispatcher **only executes the compute tool and forwards the candidate JSON to the Secretary**; it does not touch the human or make commitment decisions. As long as the "dispatcher -> Secretary -> human" path is preserved, the boundary holds.
  2. **Firing depends on worker close**: while there are zero workers in complete idle, it does not fire. Complement this with Option B (manual).
- **Verdict**: **adopted (as the steady trigger)**.

### 6.4 Recommendation

**Recommendation: Option C as the steady trigger, Option B as the manual override; both share the same compute-layer tool. Option A is rejected.**

| | Secretary boundary | Live-state visibility | Trigger quality | Operational cost | Adoption |
|---|---|---|---|---|---|
| A. cron cloud | X breaks | X invisible | O time-autonomous | -/+ separate billing / opaque | **rejected** |
| B. local skill | O | O | -/+ passive / manual | O | **adopted (manual)** |
| C. dispatcher-loop ext. | O (Secretary path kept) | O | O event-driven | O reuses existing loop | **adopted (steady)** |

Rationale: since the compute layer is consolidated into one body, "C for steady start + B for manual start" are just two entry points to the same tool, not double implementation. C reuses the proven pattern of the on-demand curator and is the only option that simultaneously satisfies the Secretary boundary, live state, and trigger quality. B complements gaps during idle or at arbitrary timing. A is structurally unsuitable on Secretary boundary and live state.

> This recommendation is fully consistent with "automate up to proposal; keep commitment as a human gate" of assessment §7(b): **discovery (scan / ranking / presentation) is automated; judgment (selection / commitment) is human**.

## 7. Safety rails (invariants)

The following are the **invariants** of this mechanism. Regardless of delivery method or future extension, they must not be broken.

- **INV-1 — propose-only / stop at proposal**: the mechanism's output is a ranked candidate list only. After generation it **stops**. It does not spawn, delegate, create branches, commit, PR, or write to Issues. The compute layer is read-only (reads Issues only, zero side effects).
- **INV-2 — commitment requires the human gate**: candidate selection is performed only by the human. The chosen candidate enters the normal delegation flow **from Step 0 of the existing [`/org-delegate`](../../.claude/skills/org-delegate/SKILL.md)**. It is forbidden for the discovery mechanism to call org-delegate by itself. Auto-committing to rank 1 (the recommendation) is also forbidden.
- **INV-3 — no auto PR / no auto commit**: this mechanism **does not change source tree / Issue / PR / git (commit / branch / push) in any way**. Even when triage results are committed to source for operational reasons, that is a separate task by human judgment; the mechanism does not do it automatically.
  - **Exception (= bookkeeping, not change)**: appending a journal event to the events table of `.state/state.db` ([§7.1](#71-verifiability-of-invariants)) as part of normal operational bookkeeping is out of scope of this INV. It is on par with the bookkeeping all other roles do daily and does not change git history / source / GitHub. **The read-only compute-layer tool itself does not write to state.db either** ([§7.1](#71-verifiability-of-invariants) "guarantee of zero side effects"). Journal bookkeeping is the delivery layer's (Secretary / dispatcher) job, not the compute-layer tool's — this separation must be preserved.
- **INV-4 — Secretary = sole human contact**: triage results always reach the Secretary, and the Secretary presents them to the human. The discovery mechanism (dispatcher / cron / tool) must not reach the human or human-visible surfaces on GitHub directly (the direct rationale for rejecting Option A).
- **INV-5 — all real work is delegated / Secretary does not investigate**: a scan is deterministic tool execution, not "investigation". If feasibility deep-dive / design of a candidate is needed, treat it as a delegated worker task after the human gate. The Secretary / dispatcher does not self-investigate / self-implement candidate contents.

> These 5 are devices that mechanically guarantee assessment §5-1 / §7(b)'s requirement "raise the autonomy of discovery but keep the human at the apex of the loop". In particular, **INV-1 + INV-2 is the body of "up to proposal / human gate"**; INV-4 is the basis for excluding Option A, and INV-5 is the brake against increasing comprehension debt (§5-2).

### 7.1 Verifiability of invariants

- **Audit log**: keep scan execution / candidate count / recommendation as journal events (proposed kind example: `work_discovery_scanned` / payload with `candidate_count` / `recommendation_issue` / `trigger`), so one can retroactively trace "when / how many / what was recommended". The recording is done by the **delivery layer (Secretary / dispatcher), not by the read-only compute-layer tool** (the separation of the INV-3 exception). Per [`docs/journal-events.md`](../journal-events.md), the events SoT is the events table in `.state/state.db`; emission is done via DB-routed helpers (`tools/journal_append.sh` / `tools/journal_append.py`) (no more direct writes to the old `.state/journal.jsonl` or direct DB INSERT). **Ledger registration of the proposed event and the actual wiring are out of scope of this design** (separate task).
- **Guarantee of zero side effects**: the compute-layer tool uses **only read APIs** like `gh issue list` / `rtk gh issue view` and is locked by the tool's contract (and future unit tests) to never call write APIs or git operations.

## 8. Integration with post-merge proactive-next-dispatch

The current post-merge proactive next-dispatch (the policy in [`CLAUDE.md`](../../CLAUDE.md) + operational memory) has the Secretary run `gh issue list` improvised after a PR merge to produce candidates. **Promote** this to be based on triage results.

### 8.1 Integration method

1. **Trigger merge**: use as the triage scan trigger the moment after PR merge -> post-merge cleanup -> dispatcher CLOSE_PANE confirmation (same moment as worker close in [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md)). This naturally overlaps with Option C's worker-close trigger.
2. **Improvisation -> structured**: instead of the Secretary running `gh issue list` herself, receive the compute-layer tool's candidate JSON ([§5.1](#51-machine-readable-json-tool-stdout)) and present to the human in the form of [§5.2](#52-human-readable-rendering-secretary--human). Judgment criteria (dependency resolved / priority / effort) are codified, and reproducibility / auditability are added.
3. **Bias toward recently merged origin**: in a post-merge context, strongly weight the `unblocked_by_recent_merge` ([§4.2](#42-auxiliary-axes-used-for-ranking)) axis to rank "natural follow-ups of recently merged" / "Issues unblocked by recent merge" (proactive candidate patterns operational memory lists) at the top. Put `generated_for: "post_merge"` in the JSON to make context explicit.
4. **Invariant human operation**: keep the presentation form / "instant choice by number" experience compatible with current (see [§5.2](#52-human-readable-rendering-secretary--human)). The only change visible to the human is "the basis of candidates is explicit, and exclusion reasons are visible".

### 8.2 Position after promotion

| | Current proactive next-dispatch | After promotion |
|---|---|---|
| Candidate generation | Secretary improvisation `gh issue list` | Compute-layer tool (criteria codified) |
| Judgment basis | Implicit | `dependency` / `priority` / `effort` + signals |
| Visibility of exclusion | None | `excluded_blocked` shown |
| Trigger | post-merge only | post-merge (joined with Option C) + manual (Option B) |
| Commitment | Human (no change) | Human (no change) |
| Audit | None | journal `work_discovery_scanned` |

> Crux of the integration: **rather than abolishing or replacing proactive next-dispatch, replace only its "candidate generation" part, from improvisation to the triage mechanism**. The outward form "Secretary presents to human; human chooses" is fully preserved (INV-2 / INV-4).

## 9. Staged rollout and verification (proposal)

Recommended order if implementing (this design has the plan only; each Phase's implementation is a separate task).

1. **Phase 1 — Compute layer**: `tools/work_discovery_scan.py` (read-only, candidate JSON stdout, exit-code branching, unit tests). It alone has zero side effects; output can be manually verified by `python3 tools/work_discovery_scan.py`.
2. **Phase 2 — Option B manual entry**: a path where the Secretary manually launches and presents. Skill addition involves `.claude/` edits, so out of scope of this worker (separate task).
3. **Phase 3 — Option C steady trigger**: wiring that launches scan on worker close and forwards to Secretary (entails prose updates in [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md) / [`.dispatcher/CLAUDE.md`](../../.dispatcher/CLAUDE.md)).
4. **Phase 4 — post-merge integration**: the promotion in §8. Replace candidate generation of proactive next-dispatch with triage output.

Each Phase confirms via review gate that it does not break INV-1 through INV-5. In particular, "is it read-only" and "does it skip the human gate" are verified per Phase.

## 10. Cross-repository triage (implemented)

> Status: **implemented** (Issue #528). The original premise was "single repository, future extension", but the compute layer ([`tools/work_discovery_scan.py`](../../tools/work_discovery_scan.py)) was additively extended to **cross-repository dependency resolution + cross-repository ranking**. Single-repository behavior (`scan()` entry) is fully preserved, and invariants INV-1 through 5 ([§7](#7-safety-rails-invariants)) are maintained.

Scan multiple repositories (ja / runtime / renga / transport-lab etc.) in one shot and rank next-work candidates across them. The core is the **qualified ref**: all open Issues/PRs, dependency references, and recent merge links are keyed by `(repo, number)`, so `ja#60` and `runtime#60` are treated as distinct and do not collide.

### 10.1 Dependency notation and calibration (2026-06-12, based on real Issues)

- **Notations resolved**: `Blocked by owner/repo#N` / `Depends on owner/repo#N` / `Requires owner/repo#N`, and the GitHub URL form (`https://github.com/owner/repo/issues/N` / `/pull/N`). Bare `#N` of the home repository is qualified to that Issue's repo as before.
- **Most important point confirmed by calibration**: in real Issue groups, cross-repository references all appear in **non-blocking notation** (`Epic:` / `Refs:` / `Found by` / `Design source:`); blocking sections like `Blocked by` currently have zero. Therefore the cross-repository extractor is also **keyword-gated + leading-run anchored** (avoidance of over-matching in [§11-3](#11-open-questions-points-requiring-human-judgment-before-implementation)), so `Epic: owner/repo#6` is not misclassified as a blocker. This feature is **forward-compatibly "enabled"** — it resolves the moment a real Issue adopts blocking notation, and does not misread existing non-blocking references.
- **Deliberate non-coverage** (prefer explicitness over misreading, [§4.4](#44-uncertainty-disclosure-for-estimated-axes)):
  - Owner-less shortened form `ja#467` is ambiguous and is not resolved.
  - Release / version prose dependencies (`claude-org-runtime>=0.1.11`, "awaiting runtime 0.1.20 release") are not Issue references and are not resolved. If a real blocker is written this way, it requires a **human scope decision** (not silently dropped).

### 10.2 Resolution model (scan-set-relative + audit signals)

- Blocking references are resolved against **the open set of the repos included in the scan target**. To resolve `runtime#60`, include runtime in the scan set (natural since cross triage assumes batch-scanning ja/runtime/renga etc.).
- **Keying is always done with the actual repo name (separated from display)**: even when single-repository scans fold display to home (`repo: null` / int `blocking_refs`, §5.1 backward compatibility), dependency-resolution keying uses the actual repo name. This makes **fully qualified self-references** to the same repo (e.g. `Blocked by owner/repo#5` in that repo's scan) resolve correctly against that repo's open set, and `#5` becomes blocked when open (avoids the misclassification "unscanned" that arises if you fold all the way to keying). Display folding is solely the output rendering's responsibility.
- Cross-repository references pointing to a repo **outside** the scan set are **treated resolved** (following the existing misclassification < misincluson policy), but the candidate's `signals[]` always emits "`cross-repo ref owner/repo#N to un-scanned repo — treated resolved`" so the human can distinguish "because it's closed" from "because it's unverified" (auditable silent resolution).
- Recent merge sets are **qualified by the merge source repo** (a runtime PR's `Closes #60` resolves runtime#60 and does not touch ja#60).

### 10.3 Launch (CLI)

- Repeat `--repo` to pass multiple repos: `python3 tools/work_discovery_scan.py --repo suisya-systems/claude-org-ja --repo suisya-systems/claude-org-runtime`. Omitted or specified once means single-repo as before.
- Candidate identity (`repo`+`issue`), canonical `blocking_refs`, and the recommendation's `repo` are per [§5.1](#51-machine-readable-json-tool-stdout). INV-1 (read-only / propose-only) is preserved: only the **read subcommands of gh** are used; even in cross mode, no writes, git operations, or spawn occur.

## 10'. Out of scope / future work

- **Automation of commitment**: out of scope of this design (permanently forbidden by INV-1 / INV-2). As assessment §5 says, "keep the human at the apex of the loop" is this organization's fixed policy.
- **Resolving release/version dependencies**: automatic resolution of prose release dependencies ([§10.1](#101-dependency-notation-and-calibration-2026-06-12-based-on-real-issues)) like `runtime>=0.1.11` is out of scope (scope A confirmed: up to cross resolution of Issue references). Cross-matching against `gh release` is future work.
- **Effort estimation sophistication (implemented, gated OFF in this repository)**: in addition to the static heuristics of §4.1, [`tools/work_discovery_scan.py`](../../tools/work_discovery_scan.py) learns a repo-calibrated effort model from the **realized effort** of recently merged PRs (changed lines / files. Review-round count and start-to-merge time are degenerate signals and are excluded from the composite, recorded only as context) (`--effort-history`, default 60 / disable with `0`). Use `closingIssuesReferences` to bridge PR <-> Issue, and measure whether the only predictor observable at triage time (Issue body length) correlates with realized effort. Override the static estimate only when the **data-driven gate** (sufficient sample size AND Spearman >= threshold) is exceeded; otherwise keep the static estimate and make the reason + realized-effort context explicit in `signals[]`. In this repository's real data, body length does not correlate with realized effort (rho ~ 0, n~23 — body length reflects spec detail, not code change volume), so the gate correctly forgoes overriding and the model avoids the misperception "the machine asserted this" (cognitive surrender, §4.4) while only adding audit context. In future repos where size labels are operated or body-length correlation appears, the same framework will apply learned cutpoints automatically. The learning fetch is **non-fatal** (degrades to static heuristics if gh fails; triage does not abort). The `effort_estimated` + `signals[]` uncertainty disclosure contract is preserved on the learning path as well. The model summary is echoed in the output `effort_model`. **Known limitation (explicit)**: the body used as the predictor is the *current* body of the closed Issue, not the snapshot at merge / triage time (cheap historical body fetch from gh is not available). Post-close body edits could shift learned correlation / cutpoints (spec Issues are rarely edited after close, but `coverage` makes the breadth auditable as a noise source).
- **Actual implementation of `.claude/` skill / `.dispatcher/` prose**: cross-repository delivery layer wiring (multi-repo launch in the Secretary skill, dispatcher extension) and operational wiring for the effort-learning gate are separate tasks.
- **Ledger registration and wiring of proposed journal events**: ledger entries in [`docs/journal-events.md`](../journal-events.md) for `work_discovery_scanned` etc. and emission wiring are on the implementation task.

## 11. Open questions (points requiring human judgment before implementation)

1. **Default value of N**: N=3 candidate cap was set as default, but whether to make it variable with free pane count (free slots = N) or fixed.
2. **Priority label scheme**: how far Issues in this repository have a `priority:*` / `p0..p2` style label scheme is unconfirmed. If absent, priority computation in §4.1 degrades to milestone + update time. Confirmation of real label distribution is needed before implementation.
3. **Variance in dependency notation**: which notation real Issues of this repository use among `Blocked by` / `Depends on` / task lists. The extraction patterns need calibration against real data (avoid over-matching that misclassifies blocked -> unduly excluded from candidates).
4. **Trigger during idle**: during complete idle with zero workers, Option C does not fire. Whether to add a light trigger like "scan once on Secretary start" in addition to Option B manual is an operational decision.
