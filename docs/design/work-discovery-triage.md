# Autonomous work-discovery (Issue triage) — design

> Status: **design only / not implemented**. No implementation or wiring of this design exists in this repository. This document describes an "unimplemented future design" and everything below is a **proposal / plan**. No changes are made on this branch to `.claude/` skills, `.dispatcher/` prose, or `tools/` (the only deliverable is this design document).
>
> Primary inputs:
> - [`.state/reports/loop-engineering-assessment.md`](../../.state/reports/loop-engineering-assessment.md) **§5-1 (the sole structural gap = no autonomous work discovery)** and **§7(b) (introduce limited autonomous work-discovery as "auto up to proposal, human keeps the commit decision", +2 to +3 points)**.
> - originating Issue: suisya-systems/claude-org-ja#520.
>
> Dependency documents (references go one-way from this design doc to existing documents only; existing documents are not modified to reference back):
> - [`CLAUDE.md`](../../CLAUDE.md) (Secretary = sole human contact / all real work is delegated / proactive next-dispatch / role boundaries)
> - [`.claude/skills/org-delegate/SKILL.md`](../../.claude/skills/org-delegate/SKILL.md) (canonical path to commit = Step 0 onward after the human gate)
> - [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py) and [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md) (on-demand spawn at worker close = precedent for this design's delivery)
> - [`.dispatcher/CLAUDE.md`](../../.dispatcher/CLAUDE.md) (dispatcher role boundaries / monitoring `/loop`)
> - [`docs/journal-events.md`](../journal-events.md) (journal event ledger)

---

## 1. Background and fixed constraints (premises this design does not overturn)

This organization's loop is **human-initiated**. The loop only spins after the user asks the Secretary, and as `.state/reports/loop-engineering-assessment.md` §5-1 points out there is no self-feeding loop that "scans the issue tracker, triages, and picks the next one." A proactive behavior "propose the next work after merge" exists, but **the candidate selection is human**, and that proposal itself is ad hoc improvisation by the Secretary on the spot ([§2](#2-current-state-and-this-designs-relationship-to-it)).

This design concretizes the lever from assessment §7(b) — **"automate Issue triage up to the proposal, keep the commit decision with the human"**. The aim is **not** to "take the human out of the loop." It only raises the autonomy of *discovery*, while **leaving the *commitment* on the human gate as before**.

The following three points are fixed constraints this design does not overturn.

1. **Secretary = sole human contact** ([`CLAUDE.md`](../../CLAUDE.md)). The route by which triage results reach the human must always go through the Secretary. The discovery mechanism must not reach the human (or any human-visible surface on GitHub) directly.
2. **All real work is delegated; the Secretary does not investigate** ([`CLAUDE.md`](../../CLAUDE.md)). The triage scan is designed not as "investigation" but as **deterministic tool execution** (a peer of [`tools/journal_append.sh`](../../tools/journal_append.sh) / `tools/pending_decisions.py` / [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py) — deterministic ops). If a per-candidate deep dive (feasibility study, design) is needed, it becomes a delegated worker task after passing the human gate.
3. **Do not increase comprehension debt** (assessment §5-2). Triage is a mechanism for **making visible** "what we *could* do next," not for skipping the human's understanding to advance into commitment. Propose-only is the direct expression of this constraint ([§7](#7-safety-rails-invariants)).

## 2. Current state and this design's relationship to it

**Current behavior (implemented, in operation)**: when post-merge cleanup after a PR merge finishes, the Secretary follows the proactive next-dispatch policy in [`CLAUDE.md`](../../CLAUDE.md), runs `gh issue list` etc. on the spot, and presents 2 to 4 next-work candidates + 1 recommendation to the human. This is **Secretary improvisation** — the criteria (dependency resolved? priority? effort?) are not written down, and there is no reproducibility, coverage, or auditability. The trigger is also limited to "right after PR merge," and no discovery happens when the organization becomes idle.

**This design (unimplemented proposal)**: split the above improvisation into a **deterministic triage compute layer** ([§3](#3-two-layer-design) / [§4](#4-triage-criteria) / [§5](#5-output-format)) and a **delivery layer** that triggers and delivers it ([§6](#6-delivery-comparison-of-three-options)). post-merge proactive next-dispatch is promoted to one consumer of these triage results ([§8](#8-integration-with-post-merge-proactive-next-dispatch)). Until this design is implemented, the current improvisation behavior does not change at all.

| Aspect | Current (improvised, implemented) | Proposed (triage mechanism, unimplemented) |
|---|---|---|
| Criteria | Implicit (Secretary's judgment) | Written down (dependency resolved / priority / effort estimate, [§4](#4-triage-criteria)) |
| Output | Free-form each time | Structured schema (N candidates + 1 recommendation, [§5](#5-output-format)) |
| Trigger | Only right after PR merge | post-merge / worker close / Secretary manual ([§6](#6-delivery-comparison-of-three-options)) |
| Commit decision | Human (decides by number) | Human (unchanged; propose-only is an invariant, [§7](#7-safety-rails-invariants)) |
| Audit | None | journal events + candidate JSON, reproducible |

## 3. Two-layer design

Split triage into "**compute (which Issue gets triaged how)**" and "**delivery (when, who runs it, how it reaches the human)**" — two layers. This is the skeleton of the design.

```
+- Compute layer (deterministic, delivery-agnostic) -------+
|  Input:  open Issues / Epics (via gh / rtk)              |
|  Process: dependency check -> priority score -> effort estimate -> rank
|  Output: candidate JSON (N candidates + 1 recommendation, §5)
|  Properties: zero side effects. Only reads Issues. Never spawns / commits / opens PRs.
+----------------------------------------------------------+
            ^ a single tool is shared by three deliveries
+- Delivery layer (three options, §6) ---------------------+
|  A. cron cloud routine                                   |
|  B. local skill (Secretary manual / event-driven)        |
|  C. dispatcher-loop extension (on-demand at worker close)|
|  Common: output always reaches Secretary -> Secretary presents to human -> human chooses
+----------------------------------------------------------+
```

**Design implication**: by decoupling the compute layer from delivery, the three options stop being mutually exclusive and converge to "different ways to trigger the same compute tool." The recommendation ([§6.4](#64-recommendation)) picks a single primary delivery, but as long as the compute layer is consolidated to one, the meaning of triage does not drift when another delivery is added later.

The body of the compute layer is, in this design, the proposed tool `tools/work_discovery_scan.py` (a peer of [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py) — a pure compute + JSON-stdout tool). **This design document defines only the interface; it does not implement it.**

## 4. Triage criteria

The candidate Issue evaluation axes use the three named by assessment §7(b) — **dependency resolved / priority / effort estimate** — as the primary criteria, plus two auxiliary axes. Each axis is computed by the compute layer from Issue metadata, and the contract is that **the same input on the same run yields the same output (reproducibility)**. Not every axis is decided by "straightforward metadata reading," however: `dependency` and `priority` (label/milestone-derived) are deterministic, but `effort`, `parallelizable`, and `unblocked_by_recent_merge` include **heuristic estimation**. For the latter we always attach uncertainty flags (`*_estimated` / `signals[]`) to the output to make explicit to the human that "this is a machine estimate, not a declaration" ([§4.4](#44-explicit-uncertainty-on-estimated-axes)). This keeps propose-only (the human decides even if the estimate is wrong) and auditability (you can trace which signal drove the estimate) compatible.

### 4.1 Primary criteria

| Axis | Computation source (deterministic signals) | Range |
|---|---|---|
| **Dependency resolved** (`dependency`) | Extract `Blocked by #N` / `Depends on #N` / `Requires #N` / task list `- [ ] #N` from Issue body / comments, and check **whether all referenced Issues/PRs are closed**. `blocked` / `on-hold` labels are immediately treated as unresolved. | `resolved` / `blocked` (blocked is excluded from candidates and shown in a separate slot with reason) |
| **Priority** (`priority`) | Labels (`priority:high` / `p0`-`p2` etc.) > milestone > age in days (stale boost or penalty by policy). In a repo with no label system, computed only from milestone and updated-at. | `high` / `medium` / `low` |
| **Effort estimate** (`effort`) | Use `size:S/M/L` etc. labels if present. Otherwise heuristically **estimate** `S/M/L` from body length / number of acceptance criteria / number of areas expected to change. An estimated value must carry `effort_estimated: true` to make it explicit to the human that "this is a machine estimate." | `S` / `M` / `L` (+ `effort_estimated` flag) |

### 4.2 Auxiliary axes (used for ranking)

| Axis | Use |
|---|---|
| **Parallelizable** (`parallelizable`) | Can be picked up independently of other Issues and fills an open pane slot. Decision signal: the Issue does **not** reference other open Issues via `Blocked by` / `Depends on` (= leaf in the dependency graph). Directly tied to [`CLAUDE.md`](../../CLAUDE.md)'s proactive policy "fill parallelism with independent open issues." Boosts rank when there are open panes. **Heuristic** (cannot detect implicit conflicts not expressed in dependency notation) -> attach `parallelizable_estimated`. |
| **Unblocked by recent merge** (`unblocked_by_recent_merge`) | Whether the Issue is unblocked by a recent merge / is a natural follow-up. Decision signal: the Issue's `Blocked by` / `Depends on` targets include "an Issue/PR closed by one of the last K merged PRs," or a recent merged PR references this Issue via `Refs #N` etc. Most important for the promotion in [§8](#8-integration-with-post-merge-proactive-next-dispatch). This axis weighs heavily on the post-merge trigger. **Heuristic** (cannot detect "conceptual follow-ups" that aren't in the notation) -> attach `unblocked_by_recent_merge_estimated`. |

### 4.3 Ranking and choosing "one recommendation"

Sort the candidate set (those with `dependency == resolved`) lexicographically by `(priority, unblocked_by_recent_merge, parallelizable fit, smallness of effort)` and return the top N (default N=3, configurable). The **single recommendation** is the top, but always include a recommendation reason (one sentence on "why this and not another"). To avoid the recommendation being just "the machine's first place," output the recommendation reason as a structured field ([§5](#5-output-format)'s `recommendation.reason`) so the Secretary has grounds when presenting it to the human.

> **Important**: the compute layer produces a "recommendation," but this is a **proposal**, not a decision. The final selection is the human ([§7](#7-safety-rails-invariants) INV-2). Auto-committing to rank 1 is forbidden by design.

### 4.4 Explicit uncertainty on estimated axes

`effort` / `parallelizable` / `unblocked_by_recent_merge` include heuristic estimation ([§4.1](#41-primary-criteria) / [§4.2](#42-auxiliary-axes-used-for-ranking)). The output must always satisfy:

- Estimated values carry the corresponding `*_estimated: true` flag (`effort_estimated` / `parallelizable_estimated` / `unblocked_by_recent_merge_estimated`).
- The raw signals that drove the estimate are listed in `signals[]` (e.g. `"label:size:M"`, `"leaf in dependency graph"`, `"follow-up of #528 (merged)"`). The human can trace "why we estimated it this way."
- In the human-readable rendering ([§5.2](#52-human-readable-rendering-secretary--human)), estimated values are marked with `(estimated)`.

This is a device that prevents the human from misreading "the machine declared" and surrendering the commit decision to the mechanism (cognitive surrender, assessment §5), and operationally supports INV-1 / INV-2.

## 5. Output format

The compute layer has two representations: machine-readable JSON (tool stdout, consumed by the delivery layer) and a human-readable text rendering the Secretary presents to the human (plain text / markdown-compatible). The JSON is the source of truth; the latter is a derived rendering.

### 5.1 Machine-readable JSON (tool stdout)

Follows the contract of [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py): "stdout is a single JSON object + branch by exit code."

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
    "issue": 531,
    "reason": "natural follow-up of the recently merged #528, dependency resolved, effort S, fills an open pane"
  },
  "excluded_blocked": [
    { "issue": 540, "blocking_refs": [537], "note": "excluded because #537 is open" }
  ]
}
```

(The `candidates` above shows only one entry as an example. In practice `candidate_count` entries are listed in ascending `rank`. JSON does not allow comments, so no elision notation is used.)

- `status`: `candidates_found` / `no_candidates` (zero candidates) / `error`.
- `candidate_count`: actual length of `candidates[]`. `truncated_count`: the count of "dependency-resolved but out-of-rank" candidates dropped from `candidates[]` by the N cap (**required field**. Do not omit even when `0`. To forbid silent truncation).
- The delivery side branches on exit code. Following [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py), **do not assign meaning to `1`** (it collides with Python's default exit `1` on uncaught exceptions; a scan crash would be misread as "no candidates" and the error would not reach the Secretary). The assignment is `0` = no candidates (`no_candidates`), `10` = candidates found (`candidates_found`), `2` = error. The delivery layer decides behavior by exit code, not by JSON parse failure (same approach as the curator threshold tool).
- `excluded_blocked` retains "Issues excluded due to unresolved dependencies" with reasons. **No silent truncation** (both the existence of out-of-rank candidates via `truncated_count` and dependency-excluded ones via `excluded_blocked` are auditable by the human).

### 5.2 Human-readable rendering (Secretary -> human)

The form the Secretary presents to the human. Compatible with the current proactive next-dispatch practice (2-4 candidates + 1 recommendation, decided by number) so the human's operation is unchanged.

```text
Next-work candidates (triage result / proposal only / commit is your decision):

1. [recommended] #531 ...(priority high / effort S(estimated) / dependency resolved / parallelizable)
   `- Follow-up of recently merged #528. Fills an open pane.
2. #533 ...(priority medium / effort M(estimated) / dependency resolved)
3. #529 ...(priority medium / effort S / dependency resolved / parallelizable)

Excluded (dependency unresolved): #540 (because #537 is open)

Specify the one to start by number. After your commit decision we will run /org-delegate.
```

- The recommendation is prefixed with `[recommended]` and there is only one.
- If effort is a machine estimate, always mark with `(estimated)`.
- "Proposal only / commit is your decision" is always made explicit (the operational manifestation of INV-1).
- Always show the excluded slot (auditability + the reassurance of "we considered everything and these are N").

## 6. Delivery: comparison of three options

The compute layer ([§3](#3-two-layer-design)) is identical. The difference is **who triggers it, when, and how the result reaches the Secretary**.

### 6.1 Option A: cron cloud routine

Put triage scan on a `schedule`-family cloud routine (a headless cloud agent running on cron).

- **Pros**: true autonomous discovery that runs on a time basis even when the organization session is not up. Runs even if the machine is off.
- **Cons (disqualifying)**:
  1. **Violates the Secretary boundary**: the cloud routine runs outside the organization's renga tabs and cannot inject results in-band into the Secretary session. Delivering results to the human requires writing **directly** to GitHub (Issue comment / triage Issue) or notifications, which breaks "Secretary = sole human contact." Getting back to going via the Secretary needs a bridging layer to local, which negates the cron benefit.
  2. **Live state is invisible**: open pane count, in-flight workers, `.state/` / state.db live locally and are not observable from the cloud. The decisions for `parallelizable` / filling open slots ([§4.2](#42-auxiliary-axes-used-for-ranking)) do not work.
  3. **Operational opacity + billing**: detection-to-presentation runs detached from the organization session, making it hard to audit and intervene. Also it likely sits in a separate credit billing tier (headless / Agent SDK family) (cost is not the deciding factor per this organization's policy, but combined with 1 and 2 above there is no reason to adopt).
- **Verdict**: **rejected**. The Secretary boundary and live-state visibility are both fatal.

### 6.2 Option B: local skill

A skill the Secretary triggers locally (e.g. tentative name `/work-discovery`). The skill calls the compute-layer tool and the Secretary presents the output to the human. **The trigger is restricted to the Secretary**: a delegated worker spawning next-work discovery outside its own task would break "1 worker = 1 task = 1 scope" and "different work starts from Step 0 of [`/org-delegate`](../../.claude/skills/org-delegate/SKILL.md)" ([`CLAUDE.md`](../../CLAUDE.md)).

- **Pros**: naturally preserves the Secretary boundary (Secretary triggers, Secretary presents). Live state (open panes) is visible locally. Good fit for manual on-demand.
- **Cons / caveats**:
  1. **Trigger is passive**: the Secretary must be conscious of "when to run it." Time-triggering with a resident `/loop` has the side effect of polluting raw logs / presentations on days with no change (same root as the lesson "do not start on time-based /loop" for `skill-audit`). So avoid a resident /loop and **limit to event triggers (post-merge / manual)**.
  2. **Who runs the scan**: if the Secretary runs the scan directly it may touch the "Secretary does not investigate" boundary. Avoid this by confining scan to a **deterministic tool** ([§1](#1-background-and-fixed-constraints-premises-this-design-does-not-overturn) constraint 2). Candidates that need deep diving become worker delegations after the human gate.
- **Verdict**: **adopted (as manual entry)**. Single use leaves the "when to run" problem, so the standing trigger is delegated to Option C.

### 6.3 Option C: dispatcher-loop extension

Extend the already-resident dispatcher monitoring `/loop` (worker monitoring) and the on-demand spawn mechanism at worker close ([`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py) / [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md)) so that **at worker close = the moment a pane slot opens**, a triage scan runs and the candidate JSON is peer-messaged to the Secretary.

- **Pros**:
  1. **Reuse of an existing resident loop**: no new resident process. Rides exactly on the same "at worker close check threshold/condition -> start only when condition met" pattern as the on-demand curator (implementation / operational cognitive cost is known).
  2. **Trigger is semantically right**: fires at "a pane opens = it's time to put in the next work." Naturally links to idle detection too.
  3. **Has live state**: the dispatcher knows the pane topology / which workers are present, providing decision material for `parallelizable` / open-slot filling.
- **Cons / caveats**:
  1. **Expanded dispatcher responsibility**: the dispatcher's principle is "stand in for the Secretary's DELEGATE / do not talk to humans directly" ([`.dispatcher/CLAUDE.md`](../../.dispatcher/CLAUDE.md)). Triage is a new responsibility, but the dispatcher **just runs the compute tool and forwards candidate JSON to the Secretary** — it does not touch the human / does not make the commit decision. As long as the path "dispatcher -> Secretary -> human" is preserved, the boundary is not broken.
  2. **Firing depends on worker close**: it does not fire when there are zero workers and the org is fully idle. Option B (manual) supplements this.
- **Verdict**: **adopted (as the standing trigger)**.

### 6.4 Recommendation

**Recommendation: Option C as the standing trigger, Option B as manual override, both sharing the same compute-layer tool. Option A rejected.**

| | Secretary boundary | Live state visible | Trigger quality | Operational cost | Verdict |
|---|---|---|---|---|---|
| A. cron cloud | X breaks | X invisible | O time-autonomous | - separate billing / opaque | **rejected** |
| B. local skill | O | O | - passive / manual | O | **adopted (manual)** |
| C. dispatcher-loop ext. | O (Secretary path preserved) | O | O event-driven | O reuse existing loop | **adopted (standing)** |

Rationale: because the compute layer is consolidated into one, "standing trigger in C + manual trigger in B" is merely two entries to the same tool and not a double implementation. C reuses the proven on-demand curator pattern and is the only option that simultaneously satisfies Secretary boundary, live state, and trigger quality. B plugs the gaps at idle or arbitrary timings. A is structurally unsuitable on two points (Secretary boundary, live state).

> This recommendation aligns perfectly with assessment §7(b)'s "automate to the proposal, keep the commit decision with the human": **discovery (scan, ranking, presentation) is automated, judgment (selection, commit) is the human's**.

## 7. Safety rails (invariants)

The following are the **invariants** of this mechanism. They must not be broken regardless of delivery option or future extension.

- **INV-1 — propose-only / stop at the proposal**: the output of the mechanism is a ranked candidate list only. After generation it **stops**. It does none of spawn / delegate / branch creation / commit / PR / writing to Issues. The compute layer is read-only (only reads Issues / zero side effects).
- **INV-2 — commit decision requires the human gate**: candidate selection is done only by the human. Selected candidates **enter the standard delegation flow from Step 0 of [`/org-delegate`](../../.claude/skills/org-delegate/SKILL.md)**. The discovery mechanism is forbidden from invoking org-delegate itself. Auto-committing to rank 1 (recommendation) is also forbidden.
- **INV-3 — no auto PR / no auto commit**: this mechanism **does not modify the source tree, Issues, PRs, or git (commit / branch / push) at all**. Even if you want to commit the triage result to the source for record, that is a separate task by separate human judgment and the mechanism does not do it automatically.
  - **Exception (= bookkeeping of organization state, not modification)**: appending a journal event to the events table of `.state/state.db` ([§7.1](#71-verifiability-of-invariants)) as ordinary operational bookkeeping is out of scope of this INV. This is on the same footing as the bookkeeping all other roles do daily and does not change git history / source / GitHub. **The read-only compute-layer tool itself does not write to state.db either** ([§7.1](#71-verifiability-of-invariants) "ensuring zero side effects"). Keep the separation that journal bookkeeping is done by the delivery layer (Secretary / dispatcher), not by the compute-layer tool.
- **INV-4 — Secretary = sole human contact**: triage results must reach the Secretary, and the Secretary presents them to the human. The discovery mechanism (dispatcher / cron / tools) must not reach the human or any human-visible surface on GitHub directly (the direct reason Option A is rejected).
- **INV-5 — all real work is delegated / Secretary does not investigate**: scan is deterministic tool execution and is not "investigation." If feasibility deep-dive / design is needed for a candidate, it is treated as a delegated worker task after the human gate. The Secretary / dispatcher does not investigate / implement the candidate contents themselves.

> These five mechanically guarantee what assessment §5-1 / §7(b) require: "raise the autonomy of discovery, but do not take the human off the top of the loop." In particular **INV-1 + INV-2 are the body of "up to proposal / human gate"**, INV-4 is the basis for rejecting Option A, and INV-5 is the brake against increasing comprehension debt (§5-2).

### 7.1 Verifiability of invariants

- **Audit log**: leave scan execution / candidate count / recommendation as journal events (proposed kind example: `work_discovery_scanned` / payload carries `candidate_count` / `recommendation_issue` / `trigger`) so we can trace "when / how many / what was recommended." Bookkeeping is done by the **delivery layer (Secretary / dispatcher), not by the read-only compute-layer tool** (the separation in INV-3 exception). As [`docs/journal-events.md`](../journal-events.md) states, the SoT for events is the events table in `.state/state.db`, and emit goes via DB-routed helpers (`tools/journal_append.sh` / `tools/journal_append.py`) (no direct writes to the old `.state/journal.jsonl` or direct DB INSERTs). **The ledger entry and wiring of the proposed event are out of scope of this design** (separate task).
- **Ensuring zero side effects**: the compute-layer tool uses **only read APIs** like `gh issue list` / `rtk gh issue view` and is contractually (and via future unit tests) prohibited from any write API or git operation.

## 8. Integration with post-merge proactive next-dispatch

The current post-merge proactive next-dispatch (the policy in [`CLAUDE.md`](../../CLAUDE.md) + operational memory) has the Secretary improvise `gh issue list` after a PR merge to produce candidates. We **promote this to a triage-result-based form**.

### 8.1 Integration method

1. **Trigger merge**: the moment "PR merge -> post-merge cleanup -> dispatcher CLOSE_PANE confirmation" finishes (same moment as worker close in [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md)) is the trigger for triage scan. This naturally overlaps with Option C's worker close trigger.
2. **Improvisation -> structured**: instead of the Secretary calling `gh issue list` themselves, they receive the compute-layer tool's candidate JSON ([§5.1](#51-machine-readable-json-tool-stdout)) and present in the [§5.2](#52-human-readable-rendering-secretary--human) form to the human. Criteria (dependency resolved / priority / effort) become explicit, gaining reproducibility / auditability.
3. **Recent-merge follow-up priority**: in the post-merge context, weigh the `unblocked_by_recent_merge` axis ([§4.2](#42-auxiliary-axes-used-for-ranking)) strongly, surfacing "natural follow-ups of the recent merge" / "Issues unblocked by the recent merge" (the proactive candidate patterns operational memory lists). Mark `generated_for: "post_merge"` in the JSON to make the context explicit.
4. **Human operation invariant**: keep the presentation form / "decide by number" experience compatible with the current one ([§5.2](#52-human-readable-rendering-secretary--human)). The only change the human sees is "the basis for the candidates is explicit and exclusion reasons are visible."

### 8.2 Position after promotion

| | Current proactive next-dispatch | After promotion |
|---|---|---|
| Candidate generation | Secretary's improvised `gh issue list` | Compute-layer tool (criteria explicit) |
| Decision basis | Implicit | `dependency` / `priority` / `effort` + signals |
| Visibility of exclusions | None | Presents `excluded_blocked` |
| Trigger | Only post-merge | post-merge (merged with Option C) + manual (Option B) |
| Commit | Human (unchanged) | Human (unchanged) |
| Audit | None | journal `work_discovery_scanned` |

> Crux of integration: **rather than abolishing/replacing proactive next-dispatch, replace only the "candidate generation" part from improvisation to the triage mechanism**. The exterior of "Secretary presents to human, human picks" is fully preserved (INV-2 / INV-4).

## 9. Phased rollout and verification (proposal)

Recommended order if implementing (this design document is plan only; each phase's implementation is a separate task).

1. **Phase 1 — compute layer**: `tools/work_discovery_scan.py` (read-only, candidate JSON stdout, exit code branching, unit tests). This alone has zero side effects and can be output-verified manually with `python3 tools/work_discovery_scan.py`.
2. **Phase 2 — Option B manual entry**: the path where the Secretary manually starts it and presents the result. Adding a skill involves `.claude/` edits and is out of scope for this worker (separate task).
3. **Phase 3 — Option C standing trigger**: wiring that starts the scan at worker close and forwards to the Secretary (involves prose updates to [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md) / [`.dispatcher/CLAUDE.md`](../../.dispatcher/CLAUDE.md)).
4. **Phase 4 — post-merge integration**: the promotion in §8. Replace proactive next-dispatch's candidate generation with the triage output.

Each phase confirms at a review gate that INV-1 through INV-5 are not broken. Verify "is it read-only?" and "are we skipping the human gate?" each phase.

## 10. Out of scope / future work

- **Commit automation**: out of scope of this design (permanently forbidden by INV-1 / INV-2). As assessment §5 says, "keeping the human at the top of the loop" is this organization's fixed policy.
- **Cross-repository triage**: this design assumes a single repository for dependency resolution across multiple repositories (runtime / ja / renga etc.). Future extension.
- **Higher-quality effort estimation**: effort in §4.1 is heuristic. Learning from past PR actual effort etc. is future work.
- **Actual implementation of `.claude/` skills / `.dispatcher/` prose / `tools/`**: this worker is DESIGN ONLY. All separate tasks.
- **Proposed journal event ledger and wiring**: ledger entries / emit wiring for `work_discovery_scanned` etc. in [`docs/journal-events.md`](../journal-events.md) are on the implementation task side.

## 11. Open issues (require human judgment before implementation)

1. **Default value of N**: candidate cap N=3 is the default. Make it variable by open pane count (open slots = N) or fixed?
2. **Priority label system**: it is unconfirmed to what extent the Issues in this repository have `priority:*` / `p0..p2` etc. label systems. Without them, priority computation in §4.1 degrades to milestone + updated-at. Real label distribution should be checked before implementation.
3. **Variations in dependency notation**: which of `Blocked by` / `Depends on` / task lists etc. real Issues in this repository use. Extraction patterns must be calibrated against real data (avoid over-matching that misclassifies as blocked and unjustly excludes candidates).
4. **Trigger at idle**: when workers are zero and fully idle, Option C does not fire. Whether to add a lighter trigger like "scan once on Secretary startup" in addition to Option B manual is an operational decision.
