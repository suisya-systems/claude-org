# Autonomous work-discovery (Issue triage) — design

> Status: **Phases 1-4 implemented (in operation)**. This design has been implemented and wired along the phased rollout plan in [§9](#9-phased-rollout-and-verification-proposal). Entities (all paths relative to the repository root):
> - **Phase 1 — compute layer**: [`tools/work_discovery_scan.py`](../../tools/work_discovery_scan.py) (read-only scan, candidate JSON to stdout, exit-code branching).
> - **Phase 2 — Plan B manual entry**: [`.claude/skills/work-discovery/SKILL.md`](../../.claude/skills/work-discovery/SKILL.md) (the Secretary launches it manually or on an event and presents the result).
> - **Phase 3 — Plan C steady trigger**: wiring that launches the scan at worker close time and forwards it to the Secretary ([`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md) and other dispatcher prose).
> - **Phase 4 — post-merge integration**: candidate generation for the proactive next-dispatch is swapped to the triage output ("Proposing the next task after a PR merge" in [`CLAUDE.md`](../../CLAUDE.md) and [`.claude/skills/org-pull-request/SKILL.md`](../../.claude/skills/org-pull-request/SKILL.md) 2b-iii).
>
> **The body below is preserved as the original design description.** Phrases such as "not yet implemented", "(unimplemented) proposal", "proposed tool", "this design defines only the interface and does not implement it", etc. that appear in the body are **framing as of the design moment**; the current entities exist at the paths above. The invariants in [§7](#7-safety-rails-invariants) (INV-1 through INV-5) are contracts that continue to hold after implementation.
>
> Primary inputs:
> - [`.state/reports/loop-engineering-assessment.md`](../../.state/reports/loop-engineering-assessment.md) **§5-1 (the single structural gap = there is no autonomous discovery of work)** and **§7(b) (introduce a limited autonomous work-discovery as "automatic up to proposal, human stays on commitment", +2-3 points)**.
> - originating Issue: suisya-systems/claude-org-ja#520.
>
> Dependency documents (at design time the only references were one-way from this design to existing documents. Now that Phases 2/4 are implemented, [`CLAUDE.md`](../../CLAUDE.md), [`.claude/skills/work-discovery/SKILL.md`](../../.claude/skills/work-discovery/SKILL.md), and [`.claude/skills/org-pull-request/SKILL.md`](../../.claude/skills/org-pull-request/SKILL.md) also reference back to this design):
> - [`CLAUDE.md`](../../CLAUDE.md) (Secretary = sole human contact / all real work is delegated / proactive next-dispatch / role boundaries)
> - [`.claude/skills/org-delegate/SKILL.md`](../../.claude/skills/org-delegate/SKILL.md) (the canonical entry to commitment = Step 0 of the post-human-gate flow)
> - [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py) and [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md) (on-demand spawn at worker close = the precedent for this design's delivery)
> - [`.dispatcher/CLAUDE.md`](../../.dispatcher/CLAUDE.md) (dispatcher role boundaries / monitoring /loop)
> - [`docs/journal-events.md`](../journal-events.md) (the ledger of journal events)

---

## 1. Background and confirmed constraints (premises this design does not overturn)

This organization's loop is **human-initiated**. The loop only spins after the user asks the Secretary, and as `.state/reports/loop-engineering-assessment.md` §5-1 notes, there is no self-feeding loop that "scans the issue tracker, triages, and picks the next item". A proactive behavior of "proposing the next task after a merge" does exist, but **selection of the candidate is human**, and the proposal itself is improvised by the Secretary on the spot ([§2](#2-current-state-and-this-designs-relationship-to-it)).

This design realizes the lever in assessment §7(b) — **"Make Issue triage automatic up to proposal, keep human on commitment"**. The aim is **not** to "remove the human from the loop". It only raises the autonomy of **discovery**; **commitment stays at the human gate as before**.

The following three points are confirmed constraints that this design does not overturn.

1. **Secretary = sole human contact** ([`CLAUDE.md`](../../CLAUDE.md)). The path by which triage results reach the human must always go through the Secretary. The discovery mechanism must not reach the human (or any human-visible surface on GitHub) directly.
2. **All real work is delegated; the Secretary does not investigate** ([`CLAUDE.md`](../../CLAUDE.md)). Triage scan is designed not as "investigation" but as a **deterministic tool execution** (peer of [`tools/journal_append.sh`](../../tools/journal_append.sh) / `tools/pending_decisions.py` / [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py) — deterministic ops). If a deep dive per candidate (feasibility examination, design) is needed, that becomes a delegated worker task after passing the human gate.
3. **Do not grow understanding debt** (assessment §5-2). Triage is a mechanism to **make visible** "what can be done next"; it is not a mechanism that skips human understanding and advances commitment. Propose-only ties directly to this constraint ([§7](#7-safety-rails-invariants)).

## 2. Current state and this design's relationship to it

**Current behavior (implemented, in operation)**: After post-merge cleanup following a PR merge, the Secretary follows the proactive next-dispatch policy in [`CLAUDE.md`](../../CLAUDE.md), bangs out `gh issue list` etc. on the spot, and presents 2-4 next-task candidates + 1 recommendation to the human. This is **Secretary improvisation**; the decision criteria (dependency resolved? priority? effort?) are not explicit, and there is no reproducibility, coverage, or auditability. The trigger is also limited to "immediately after a PR merge"; discovery at the moment the organization becomes idle is not performed.

**This design (unimplemented proposal)**: Separate the above improvisation into a **deterministic triage compute layer** ([§3](#3-the-designs-two-layer-structure), [§4](#4-triage-criteria), [§5](#5-output-format)) and a **delivery layer that launches and delivers it** ([§6](#6-comparison-of-three-delivery-options)). The post-merge proactive next-dispatch is promoted to one consumer of this triage output ([§8](#8-integration-with-post-merge-proactive-next-dispatch)). Until this design is implemented, the current improvised behavior is not changed at all.

| Aspect | Current (improvised, implemented) | Proposed (triage mechanism, unimplemented) |
|---|---|---|
| Decision criteria | Implicit (Secretary judgment) | Explicit (dependency resolved / priority / effort estimate, [§4](#4-triage-criteria)) |
| Output | Free-form each time | Structured schema (N candidates + 1 recommendation, [§5](#5-output-format)) |
| Trigger | Only immediately after a PR merge | post-merge / worker close / Secretary manual ([§6](#6-comparison-of-three-delivery-options)) |
| Commitment | Human (decided on the spot by number) | Human (unchanged; propose-only made invariant, [§7](#7-safety-rails-invariants)) |
| Audit | None | journal events + candidate JSON enable reproduction |

## 3. The design's two-layer structure

Split triage into two layers: "**compute (which Issues get triaged how)**" and "**delivery (when, who runs it, and how it reaches the human)**". This is the skeleton of this design.

```
+-- compute layer (deterministic, delivery-agnostic) -----------+
|  input: open Issues / Epics (via gh / rtk)                    |
|  process: dependency resolution -> priority score             |
|           -> effort estimate -> ranking                       |
|  output: candidate JSON (N candidates + 1 recommendation, §5) |
|  property: zero side effect. Only reads Issues. Never spawns, |
|            commits, or opens a PR                             |
+---------------------------------------------------------------+
            ^ Three deliveries share the same tool
+-- delivery layer (three plans, §6) --------------------------+
|  A. cron cloud routine                                       |
|  B. local skill (Secretary manual / event-driven)            |
|  C. dispatcher-loop extension (on-demand at worker close)    |
|  shared: output always reaches the Secretary                 |
|          -> Secretary presents to human -> human selects     |
+--------------------------------------------------------------+
```

**Design implication**: By decoupling the compute layer from delivery, the three plans collapse from being exclusive choices to being "different ways to launch the same compute tool". The recommendation ([§6.4](#64-recommendation)) picks a single primary delivery, but as long as the compute layer is consolidated into one piece, adding another delivery later does not shift the meaning of triage.

The body of the compute layer is, in this design, the proposed tool `tools/work_discovery_scan.py` (a pure-compute + JSON-stdout tool peer to [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py)). **This design document defines only the interface; it does not implement.**

## 4. Triage criteria

The evaluation axes for candidate Issues take as primary the three named in assessment §7(b) — **dependency resolved / priority / effort estimate** — and add two auxiliary axes. The compute layer computes each axis from Issue metadata, and **reproducibility (same input -> same output on every run)** is a contract. However, not all axes are decided by a straight read of metadata: `dependency` and `priority` (derived from labels / milestones) are deterministic, but `effort`, `parallelizable`, and `unblocked_by_recent_merge` include **heuristic estimation**. For the latter, the output must always carry an uncertainty flag (`*_estimated` / `signals[]`) to make it explicit to the human that "this is a machine estimate, not an assertion" ([§4.4](#44-explicit-uncertainty-for-estimated-axes)). This way, propose-only (commitment stays human even if the estimate is wrong) and auditability (which signal drove the estimate is traceable) are both satisfied.

### 4.1 Primary criteria

| Axis | Computation source (deterministic signal) | Range |
|---|---|---|
| **Dependency resolved** (`dependency`) | Extract `Blocked by #N` / `Depends on #N` / `Requires #N` / task list `- [ ] #N` from Issue body / comments, and check whether the referenced Issue/PR is **all closed**. Labels `blocked` / `on-hold` are immediately treated as unresolved. | `resolved` / `blocked` (blocked is excluded from candidates and shown in a separate slot with the reason) |
| **Priority** (`priority`) | Label (`priority:high` / `p0`-`p2` etc.) > milestone > elapsed days (stale upweighting or downweighting is a policy choice). Repos without a label scheme use only milestone and update time. | `high` / `medium` / `low` |
| **Effort estimate** (`effort`) | Adopt `size:S/M/L` labels if present. If not, **estimate** `S/M/L` via heuristics (body length / number of acceptance criteria / number of likely-touched areas). Estimated values must carry `effort_estimated: true` to make it explicit to the human that "this is a machine estimate". | `S` / `M` / `L` (+ `effort_estimated` flag) |

### 4.2 Auxiliary axes (used for ranking)

| Axis | Use |
|---|---|
| **Parallelism** (`parallelizable`) | Whether the Issue can be picked up independently of others and fill an empty pane slot. Determining signal: the Issue does **not** reference another open Issue via `Blocked by` / `Depends on` (= leaf in the dependency graph). Ties directly to the proactive policy in [`CLAUDE.md`](../../CLAUDE.md) of "fill parallel slots with independent open issues". Boost the rank when empty panes exist. **Heuristic** (implicit conflicts not expressed in dependency notation cannot be detected) -> attach `parallelizable_estimated`. |
| **Unblocked by recent merge** (`unblocked_by_recent_merge`) | Whether the Issue was unblocked by a recent merge / is a natural follow-up. Determining signal: the Issue's `Blocked by` / `Depends on` references include "an Issue/PR closed by one of the last K merged PRs", or a recent merged PR references the Issue via `Refs #N` etc. Most important for the promotion in [§8](#8-integration-with-post-merge-proactive-next-dispatch). Strongly active on the post-merge trigger. **Heuristic** (conceptual follow-ups not in notation cannot be detected) -> attach `unblocked_by_recent_merge_estimated`. |

### 4.3 Ranking and deciding "one recommendation"

Sort the candidate set (those with `dependency == resolved`) lexicographically by `(priority, unblocked_by_recent_merge, parallelizable fit, small effort)` and return the top N (default N=3, configurable). The **single recommendation** is the top one, but always attach a reason ("why this rather than another" in one sentence). To avoid the recommendation collapsing to the raw machine rank, emit the recommendation reason as a structured field ([§5](#5-output-format) `recommendation.reason`), and use it as the basis when the Secretary presents to the human.

> **Important**: The compute layer issues a "recommendation", but this is a **proposal**, not a decision. The final pick is human ([§7](#7-safety-rails-invariants) INV-2). It is forbidden by design to auto-commit to rank 1.

### 4.4 Explicit uncertainty for estimated axes

`effort` / `parallelizable` / `unblocked_by_recent_merge` include heuristic estimation ([§4.1](#41-primary-criteria) / [§4.2](#42-auxiliary-axes-used-for-ranking)). These must always satisfy the following in output:

- Attach the corresponding `*_estimated: true` flag to estimated values (`effort_estimated` / `parallelizable_estimated` / `unblocked_by_recent_merge_estimated`).
- List the raw signals that drove the estimate in `signals[]` (e.g., `"label:size:M"`, `"leaf in dependency graph"`, `"follow-up of #528 (merged)"`). The human can trace "why it was estimated that way".
- In human-readable rendering ([§5.2](#52-human-readable-rendering-secretary--human)), attach `(estimated)` to estimated values.

This is a device to prevent the human from misreading "the machine asserted it" and surrendering the commitment decision to the mechanism (cognitive surrender, assessment §5). It supports INV-1 / INV-2 operationally.

## 5. Output format

The compute layer has two representations: machine-readable JSON (tool stdout, consumed by the delivery layer), and a human-readable text (plain text / markdown-compatible) that the Secretary presents to the human. The JSON is the SoT; the latter is derived rendering.

### 5.1 Machine-readable JSON (tool stdout)

Follow the convention of [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py): "stdout is a single JSON object + exit code branches".

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
    "reason": "Natural follow-up of recently merged #528, dependency resolved, effort S, fills an empty pane"
  },
  "excluded_blocked": [
    { "repo": "suisya-systems/claude-org-ja", "issue": 540, "blocking_refs": [537], "note": "excluded because #537 is open" }
  ]
}
```

(The `candidates` above shows only one entry as an example. In reality, `candidate_count` entries are laid out in ascending `rank` order. Since JSON does not allow comments, no ellipsis notation is used.)

- `status`: `candidates_found` / `no_candidates` (zero candidates) / `error`.
- `repo` (each candidate / recommendation / excluded entry): identifies the source repo of the candidate (`owner/repo`) for cross-repository triage ([§10](#10-cross-repository-triage-implemented)). In a single-repository scan (`--repo` omitted or used once), this is `null`. Because `(repo, issue)` is the candidate identity, `ja#60` and `runtime#60` do not collide.
- `blocking_refs` (candidates / excluded): canonical representation of dependency references. Home-repo references are bare integers `N` (backward compatible); cross-repo references are strings `"owner/repo#N"` (mixed allowed).
- `candidate_count`: actual length of `candidates[]`. `truncated_count`: number of "dependency-resolved but ranked below cutoff" candidates dropped from `candidates[]` due to the N-item cap (**required field**. Not omitted even when `0`. Forbids silent truncation).
- The exit code branches the delivery side. Following [`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py), **do not assign meaning to `1`** (it would collide with the default Python exit `1` on uncaught exceptions, causing a scan crash to be misread as "no candidates" and the error not reaching the Secretary). The assignment is `0` = no candidates (`no_candidates`), `10` = candidates exist (`candidates_found`), `2` = error. The delivery layer decides behavior by the exit code, not by JSON parse failure (same policy as the curator threshold tool).
- `excluded_blocked` retains "Issues excluded for unresolved dependencies" with reasons. **No silent truncation** (`truncated_count` lets the human audit candidates ranked below cutoff, and `excluded_blocked` lets the human audit dependency exclusions).
- `effort_model`: summary of the learned effort model ([§10](#10-out-of-scope--future-work) effort estimation refinement), or `null` when learning is disabled / offline. **A fixed schema is assumed** so `effort_model` always takes one of the two values `null | object`; the object form carries `sample_size` / `applies` (whether to override the data-driven gate) / `predictor_correlation` / `realized_cutpoints` / `realized_median_lines` / `coverage` (training-data coverage: number of single-issue-linked PRs, adopted samples, dropped-for-missing-body), `reason`, etc. When `applies==false`, the static heuristic is preserved, and each candidate's `signals[]` explicitly carries the reason plus the realized effort context. In this repository, body length does not correlate with realized effort, so `applies==false` is always returned (gated OFF).

### 5.2 Human-readable rendering (Secretary -> human)

The form the Secretary presents to the human. Compatible with the current proactive next-dispatch convention (2-4 candidates + 1 recommendation, decided on the spot by number); does not change the human operation.

```text
Next-task candidates (triage result / proposal only; commitment is your decision):

1. [Recommended] #531 ... (priority high / effort S(estimated) / dependency resolved / parallel-ok)
   `- Follow-up of recently merged #528. Fills an empty pane.
2. #533 ... (priority medium / effort M(estimated) / dependency resolved)
3. #529 ... (priority medium / effort S / dependency resolved / parallel-ok)

Excluded (unresolved dependencies): #540 (because #537 is open)

Please select the one to start by number. After your decision, /org-delegate is invoked.
```

- The recommendation is prefixed with `[Recommended]` and is just one entry.
- If the effort is a machine estimate, always append `(estimated)`.
- Always make explicit "proposal only / commitment is your decision" (operational manifestation of INV-1).
- Always show the excluded slot (auditability + the reassurance of "saw everything and N selected").
- **In cross-repository scans ([§10](#10-cross-repository-triage-implemented))**: if a candidate's `repo` is non-null (multi-repo scan), display `repo#N` (e.g., `runtime#531`) instead of `#N` to eliminate ambiguity about the source repo. In single-repo scans (`repo: null`), display `#N` as before. This rendering branch is implemented in the delivery layer (Secretary skill) (similar to [§9](#9-phased-rollout-and-verification-proposal); it touches `.claude/` editing and is therefore outside the compute-layer worker's scope, a separate task). **Implemented**: this repo-qualified rendering becomes effective in tandem with the path where the delivery layer resolves the scan-target repo set from the triage opt-in column of `registry/projects.md` ([§10.4](#104-registry-driven-repo-set-resolution)). When opt-in rows span multiple repos, `repo` stops being `null` and this branch fires. The resolver's ([`tools/work_discovery_repos.py`](../../tools/work_discovery_repos.py)) `skipped` / `signals` are also attached to the human presentation, making "which repos the candidates came from" auditable.

## 6. Comparison of three delivery options

The compute layer ([§3](#3-the-designs-two-layer-structure)) is shared. The difference is **who launches it, when, and how it reaches the Secretary**.

### 6.1 Option A: cron cloud routine

Put the triage scan on a `schedule` family cloud routine (headless cloud agent running on cron).

- **Pros**: True autonomous discovery on a time basis even when the organization session is not running. Runs even with the machine off.
- **Cons (preventing adoption)**:
  1. **Violation of the Secretary boundary**: A cloud routine runs outside the org's renga tab and cannot inject results in-band into the Secretary session. To deliver results to the human, it ends up writing **directly** to GitHub (Issue comments / triage Issues) or to notifications, breaking "Secretary = sole human contact". Routing back through the Secretary would require an additional bridge layer to local, canceling the cron advantage.
  2. **Live state is invisible**: Number of empty panes, in-flight workers, `.state/` / state.db all live locally and cannot be observed from the cloud. The determinations of `parallelizable` / empty-slot fit ([§4.2](#42-auxiliary-axes-used-for-ranking)) do not function.
  3. **Operational opacity + billing**: Detection-to-presentation runs decoupled from the org session, making audit and intervention difficult. Additionally, it may load on the separate billing pool of headless / Agent SDK series (cost is not a deciding factor under this organization's policy, but together with the above 1-2 there is no reason to adopt).
- **Verdict**: **Not adopted**. Secretary-boundary violation and lack of live-state visibility are fatal.

### 6.2 Option B: local skill

A skill the Secretary launches locally (e.g., tentative name `/work-discovery`). The skill calls the compute-layer tool, and the Secretary presents the output to the human. **Restrict launching to the Secretary**: if a delegated worker launches "search for the next task outside one's own task", that breaks "1 worker = 1 task = 1 scope" and "another item starts from Step 0 of [`/org-delegate`](../../.claude/skills/org-delegate/SKILL.md)" ([`CLAUDE.md`](../../CLAUDE.md)).

- **Pros**: Naturally preserves the Secretary boundary (Secretary launches, Secretary presents). Live state (empty panes) is visible locally. Plays well with manual on-demand.
- **Cons / caveats**:
  1. **Trigger is passive**: The Secretary has to think about "when to run it". A time-based steady `/loop` would dirty the raw logs / presentation on days with no change (same lesson `skill-audit` drew with "do not launch in a time-based /loop"). Therefore, avoid a steady /loop and **limit to event-driven (post-merge / manual)**.
  2. **Who executes the scan**: If the Secretary scans directly, this can brush against the "Secretary does not investigate" boundary. This is avoided by sealing the scan into a **deterministic tool** ([§1](#1-background-and-confirmed-constraints-premises-this-design-does-not-overturn) constraint 2). Candidates that need a deep dive get delegated to a worker post human gate.
- **Verdict**: **Adopted (as the manual entry)**. However, by itself the "when to run" problem remains, so the steady trigger is delegated to Option C.

### 6.3 Option C: dispatcher-loop extension

Extend the dispatcher's already-resident monitoring `/loop` (worker monitoring) and the on-demand spawn mechanism at worker close ([`tools/check_curate_threshold.py`](../../tools/check_curate_threshold.py) / [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md)) so that **at the moment a worker closes = pane slot opens**, run the triage scan and send the candidate JSON to the Secretary via peer message.

- **Pros**:
  1. **Reuse of existing resident loop**: Does not add a new resident process. Rides on exactly the same "at worker close, check threshold/conditions, launch only when conditions hold" pattern as the on-demand curator (cognitive cost of implementation/operation is already known).
  2. **Trigger is semantically correct**: Fires at "pane opens = timing to put the next task in". Connects naturally with idle detection too.
  3. **Holds live state**: The dispatcher knows the pane topology and resident workers, providing the material for `parallelizable` / empty-slot fit determinations.
- **Cons / caveats**:
  1. **Expansion of dispatcher's role**: The dispatcher's principle is "act for the Secretary's DELEGATE; do not converse directly with the human" ([`.dispatcher/CLAUDE.md`](../../.dispatcher/CLAUDE.md)). Triage is a new duty, but the dispatcher **only runs the compute tool and forwards the candidate JSON to the Secretary**; does not touch the human, does not commit. As long as the path "dispatcher -> Secretary -> human" is preserved, the boundary is not broken.
  2. **Firing depends on worker close**: While workers are zero and fully idle, it does not fire. This is supplemented by Option B (manual).
- **Verdict**: **Adopted (as the steady trigger)**.

### 6.4 Recommendation

**Recommendation: Option C as the steady trigger, Option B as the manual override, both sharing the same compute-layer tool. Option A is not adopted.**

| | Secretary boundary | Live state visible | Trigger quality | Operational cost | Adopt? |
|---|---|---|---|---|---|
| A. cron cloud | X breaks | X invisible | O time-autonomous | / separate billing/opaque | **No** |
| B. local skill | O | O | / passive/manual | O | **Yes (manual)** |
| C. dispatcher-loop extension | O (Secretary route preserved) | O | O event-driven | O reuses existing loop | **Yes (steady)** |

Rationale: Because the compute layer is consolidated into one piece, "C for steady launch + B for manual launch" is just two entries to the same tool, not double implementation. C reuses the proven pattern of the on-demand curator and is the only option that simultaneously satisfies the three points of Secretary boundary, live state, and trigger quality. B plugs the hole during idle or at arbitrary timings. A is structurally unfit on the two points of Secretary boundary and live state.

> This recommendation is fully aligned with assessment §7(b)'s "automatic up to proposal, keep human on commitment": **discovery (scan, ranking, presentation) is automated, judgment (selection, commitment) is human**.

## 7. Safety rails (invariants)

The following are the **invariants** of this mechanism. They must not be broken regardless of delivery option or future extensions.

- **INV-1 — propose-only / stop at proposal**: The mechanism's output is only the ranked candidate list. After generation, it **stops**. It does not perform any of: spawn, delegate, branch creation, commit, PR, write to an Issue. The compute layer is read-only (only reads Issues, zero side effects).
- **INV-2 — commitment requires the human gate**: Candidate selection is made by the human only. Selected candidates enter the normal delegation flow **starting from Step 0 of the existing [`/org-delegate`](../../.claude/skills/org-delegate/SKILL.md)**. It is forbidden for the discovery mechanism to call org-delegate by itself. Auto-commit to rank 1 (recommendation) is also forbidden.
- **INV-3 — no auto PR / no auto commit**: This mechanism **does not modify the source tree, Issues, PRs, or git (commit / branch / push) at all**. Even if the operation commits triage results into source for retention, that is a separate task by human judgment and not done automatically by the mechanism.
  - **Exception (= bookkeeping of organization state, not modification)**: Appending journal events to the `events` table of the regular `.state/state.db` ([§7.1](#71-verifiability-of-invariants)) is outside this INV. It is peer to the daily bookkeeping all other roles perform, and does not change git history, source, or GitHub. **The read-only compute-layer tool itself does not write to state.db either** ([§7.1](#71-verifiability-of-invariants) "Guarantee of zero side effects"). Journal entry is done by the delivery layer (Secretary / dispatcher), not the compute-layer tool — keep this separation.
- **INV-4 — Secretary = sole human contact**: Triage results always reach the Secretary, and the Secretary presents them to the human. The discovery mechanism (dispatcher / cron / tool) must not reach the human or any human-visible surface on GitHub directly (the direct grounds for not adopting Option A).
- **INV-5 — all real work is delegated / Secretary does not investigate**: The scan is deterministic tool execution, not "investigation". If feasibility deep dive or design is needed for a candidate, that is handled as a delegated worker task post human gate. The Secretary / dispatcher does not investigate or implement the candidate's contents themselves.

> These five mechanically guarantee what assessment §5-1 / §7(b) demands: "raise the autonomy of discovery, but do not remove the human from the apex of the loop". In particular, **INV-1 + INV-2 are the body of "up to proposal / human gate"**; INV-4 is the basis for excluding Option A; INV-5 is the brake against growing understanding debt (§5-2).

### 7.1 Verifiability of invariants

- **Audit log**: Leave scan execution, candidate count, and recommendation as journal events (proposed kind example: `work_discovery_scanned` with payload `candidate_count` / `recommendation_ref` (`owner/repo#N` form, unified in [§10.4](#104-registry-driven-repo-set-resolution)) / `trigger`) so that "when, how many, what was recommended" can be traced. Entry is done by **the delivery layer (Secretary / dispatcher), not the read-only compute-layer tool** (separation of the INV-3 exception). As [`docs/journal-events.md`](../journal-events.md) says, the SoT for events is the `events` table in `.state/state.db`, and emission goes through DB-routed helpers (`tools/journal_append.sh` / `tools/journal_append.py`) (no direct writes to the old `.state/journal.jsonl` or direct DB INSERT).  **Ledger entry for the proposed event and its actual wiring are out of scope for this design** (separate task).
- **Guarantee of zero side effects**: The compute-layer tool uses **only read APIs** such as `gh issue list` / `rtk gh issue view`, and never calls write APIs or git operations; fix this as a tool contract (and future unit tests).

## 8. Integration with post-merge proactive next-dispatch

The current post-merge proactive next-dispatch (the policy in [`CLAUDE.md`](../../CLAUDE.md) + operational memory) has the Secretary bang out `gh issue list` on the spot after a PR merge to produce candidates. **Promote this to a triage-result base.**

### 8.1 Integration method

1. **Trigger-point merge**: The moment "PR merge -> post-merge cleanup -> dispatcher CLOSE_PANE confirmed" finishes (the same moment as worker close in [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md)) becomes the trigger for the triage scan. It naturally overlaps with Option C's worker-close trigger.
2. **Improvisation -> structuring**: Instead of the Secretary banging out `gh issue list`, receive the candidate JSON from the compute-layer tool ([§5.1](#51-machine-readable-json-tool-stdout)) and present it to the human in the form of [§5.2](#52-human-readable-rendering-secretary--human). Decision criteria (dependency resolved / priority / effort) are made explicit, gaining reproducibility and auditability.
3. **Prioritize the recent-merge basis**: In the post-merge context, strongly activate the `unblocked_by_recent_merge` axis ([§4.2](#42-auxiliary-axes-used-for-ranking)) to bring "natural follow-ups of the recent merge" / "Issues unblocked by the recent merge" (proactive candidate patterns listed in operational memory) to the top. Put `generated_for: "post_merge"` in the JSON to make context explicit.
4. **Human operation invariant**: Keep the presentation format and the "decide on the spot by number" experience compatible with the current ([§5.2](#52-human-readable-rendering-secretary--human)). From the human's view, the only change is "the basis of candidates becomes explicit, and the exclusion reason becomes visible".

### 8.2 Position after promotion

| | Current proactive next-dispatch | After promotion |
|---|---|---|
| Candidate generation | Secretary improvising `gh issue list` | Compute-layer tool (explicit criteria) |
| Decision basis | Implicit | `dependency` / `priority` / `effort` + signals |
| Visibility of exclusions | None | Show `excluded_blocked` |
| Trigger | post-merge only | post-merge (merging with Option C) + manual (Option B) |
| Commitment | Human (unchanged) | Human (unchanged) |
| Audit | None | journal `work_discovery_scanned` |

> Crux of the integration: **do not abolish / replace proactive next-dispatch; just swap its "candidate generation" part from improvisation to the triage mechanism**. The outer form "Secretary presents to human, human picks" is fully preserved (INV-2 / INV-4).

## 9. Phased rollout and verification (proposal)

Recommended ordering if implemented (this design document only plans; implementation of each Phase is a separate task).

1. **Phase 1 — compute layer**: `tools/work_discovery_scan.py` (read-only, candidate JSON to stdout, exit-code branching, unit tests). Alone, this has zero side effects, and the output can be verified manually via `python3 tools/work_discovery_scan.py`.
2. **Phase 2 — Plan B manual entry**: The path where the Secretary launches manually and presents. Adding the skill entails `.claude/` editing, hence outside this worker's scope (separate task).
3. **Phase 3 — Plan C steady trigger**: Wiring that launches the scan at worker close and forwards to the Secretary (entails prose updates to [`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md) / [`.dispatcher/CLAUDE.md`](../../.dispatcher/CLAUDE.md)).
4. **Phase 4 — post-merge integration**: The promotion in §8. Swap proactive next-dispatch's candidate generation to the triage output.

Each Phase confirms via review gate that it does not break INV-1 through INV-5. In particular, "is it read-only" and "is the human gate not skipped" are verified per Phase.

## 10. Cross-repository triage (implemented)

> Status: **Implemented** (Issue #528). The original premise was "single-repository assumed; future extension", but the compute layer ([`tools/work_discovery_scan.py`](../../tools/work_discovery_scan.py)) was additively extended to **multi-repository cross dependency resolution + cross ranking**. Single-repository behavior (`scan()` entry) is fully preserved, and the invariants INV-1 through INV-5 ([§7](#7-safety-rails-invariants)) also hold.

Scan multiple repositories (ja / runtime / renga / transport-lab etc.) at once and rank next-task candidates across them. The core is the **qualified ref**: all open Issues/PRs / dependency references / recent merge links are keyed by `(repo, number)`, so `ja#60` and `runtime#60` are treated as distinct and do not collide.

### 10.1 Dependency notation and calibration (2026-06-12, based on real Issues)

- **Notation resolved**: `Blocked by owner/repo#N` / `Depends on owner/repo#N` / `Requires owner/repo#N`, and GitHub URL form (`https://github.com/owner/repo/issues/N` / `/pull/N`). Bare `#N` in the home repo is qualified to the relevant Issue's repo as before.
- **Most important point confirmed by calibration**: In the real Issue corpus, all cross-repository references appear in **non-blocking notation** (`Epic:` / `Refs:` / `Found by` / `Design source:`); they appear zero times in blocking clauses like `Blocked by`. Therefore the cross-repo extractor, like the home extractor, uses **keyword gate + leading-run anchored** ([§11-3](#11-open-points-requiring-human-judgment-before-implementation) avoidance of over-match) and does not mistakenly treat `Epic: owner/repo#6` as a blocker. This feature is **enabled in a forward-compatible way**: the moment a real Issue adopts blocking notation it resolves it, and existing non-blocking references are not misread.
- **Intentional non-coverage** (prefer explicit to misread, [§4.4](#44-explicit-uncertainty-for-estimated-axes)):
  - Owner-less short form `ja#467` is ambiguous and not resolved.
  - Prose dependencies on releases / versions (`claude-org-runtime>=0.1.11`, "waiting for the runtime 0.1.20 release") are not Issue references and are not resolved. If a real blocker is written in this form, **human scope judgment** is needed (not silently dropped).

### 10.2 Resolution model (scan-set-relative + audit signals)

- Blocking references are resolved against the **open set of repos included in the scan target**. To resolve `runtime#60`, include runtime in the scan set (cross triage assumes batch scanning of ja/runtime/renga etc., which is natural).
- **Keying is always done by the actual repo name (separated from display)**: Even when collapsing display to home (`repo: null` / int `blocking_refs`, §5.1 backward compatible) in single-repo scans, dependency-resolution keying is by the actual repo name. This way, **fully qualified self-references** to the same repo (`Blocked by owner/repo#5` in the scan of that repo) are correctly resolved against that repo's open set, and `#5` becomes blocked when it is open (avoiding the unscanned-misjudgment that would happen if the display collapse were applied to keying). Display collapse is the responsibility of output rendering only.
- Cross-repository references that point to repos **outside** the scan set are **treated as resolved** (following the existing policy of mis-exclusion < mis-inclusion), but the candidate's `signals[]` must always emit `"cross-repo ref owner/repo#N to un-scanned repo — treated resolved"` so the human can distinguish "because closed" vs. "because unverified" (auditable silent resolution).
- The recent-merge set is **qualified by the merging repo** (a runtime PR's `Closes #60` resolves runtime#60, leaving ja#60 untouched).

### 10.3 Launch (CLI)

- Pass multiple repos by repeating `--repo`: `python3 tools/work_discovery_scan.py --repo suisya-systems/claude-org-ja --repo suisya-systems/claude-org-runtime`. With omitted or single use, single-repo as before.
- For candidate identity (`repo`+`issue`), canonical `blocking_refs`, and the recommendation's `repo`, see [§5.1](#51-machine-readable-json-tool-stdout). INV-1 (read-only / propose-only) is preserved: only **read subcommands** of gh are used; cross-repo scans never perform writes, git operations, or spawn.
- **Supply source of the `--repo` set (registry-driven, [§10.4](#104-registry-driven-repo-set-resolution))**: the delivery layer does not hand-type `--repo` improvisationally; it derives the set deterministically through the resolver [`tools/work_discovery_repos.py`](../../tools/work_discovery_repos.py), from the triage opt-in column of `registry/projects.md` + always-include home repo. Both the Secretary skill ([`.claude/skills/work-discovery/SKILL.md`](../../.claude/skills/work-discovery/SKILL.md)) and the dispatcher's worker_close path ([`.dispatcher/references/pane-close.md`](../../.dispatcher/references/pane-close.md) Step 6) splice the output of `resolver --format flags` into the scan command.

### 10.4 Registry-driven repo-set resolution

The layer that makes "who decides the `--repo` set, and how" deterministic and guarantees the auditability of opt-in. The engine (scan) merely receives `--repo`; supplying it is the delivery layer's responsibility (the compute-layer / delivery-layer separation of [§7.1](#71-verifiability-of-invariants)). The resolver [`tools/work_discovery_repos.py`](../../tools/work_discovery_repos.py) is read-only (`git remote get-url` and an optional `gh repo view` read only. No writes, spawns, or git changes) and does not break INV-1 through INV-5.

- **Triage column semantics**: the table in [`registry/projects.md`](../../registry/projects.md) carries a trailing column `triage`. Only the values `yes` / `true` / `on` (case-insensitive, after trim) are opt-in. Anything else (`no` / empty / `-`) — or a legacy table with no such column at all — is non-opt-in (backward compatible: all rows treated as `no`). For opt-in rows, `owner/repo` is derived from the GitHub URL in the path column and added to the `--repo` set.
- **Home repo always included (two-stage resolution)**: claude-org-ja itself is contractually absent from the registry (the note at the top of [`registry/projects.md`](../../registry/projects.md)), so the resolver always includes it in the scan targets from git origin. Resolution: (1) primary — extract `owner/repo` from the URL of `git -C <root> remote get-url origin`; (2) only on primary failure, fall back to `gh repo view --json nameWithOwner`; (3) if both fail, emit a loud signal that home could not be explicitly added (non-fatal; normally it always resolves). Home goes **first** in the `--repo` set, followed by opt-in rows in order with duplicates removed.
- **Skip signal for local-path / `-` rows**: a row that is triage opt-in but whose path column is not a GitHub URL (local path / `-`) cannot yield owner/repo, so it is excluded from the scan targets, leaving a `skipped` entry + a reason in `signals` (`triage opt-in row '<nickname>' has non-URL path '<path>' -- skipped`). The purpose is auditability instead of silently dropping it; the delivery layer (Secretary skill / dispatcher) attaches this to the human presentation.
- **owner/repo normalization**: resolver output is unified to lowercase (the engine's closing-issue join mixes `.lower()` comparisons, so the resolver aligns on its side for consistency).
- **Output**: `--format json` (default; `repos` / `home_repo` / `opted_in` / `skipped` / `signals`) and `--format flags` (a single line `--repo a/b --repo c/d`, for `$(...)` splicing. Skips / signals go to stderr; stdout stays flags-pure). Exit codes: `0` (repos contains at least home) / `2` (error).
- **journal unification of `recommendation_ref`**: the dispatcher's worker_close path unifies the payload of the journal event `work_discovery_scanned` from `recommendation_issue=<number>` to **`recommendation_ref=owner/repo#N`** (when `recommendation.repo` is null = a single-repo scan folded into home, complete it with the resolver's `home_repo`). This prevents `ja#60` and `runtime#60` from colliding in the journal under cross-repo.

## 10'. Out of scope / future work

- **Auto-commitment**: out of scope of this design (permanently forbidden by INV-1 / INV-2). As assessment §5 says, the confirmed policy of this organization is "keep the human at the apex of the loop".
- **Release/version dependency resolution**: Auto-resolution of prose release dependencies in [§10.1](#101-dependency-notation-and-calibration-2026-06-12-based-on-real-issues) (`runtime>=0.1.11` etc.) is out of scope (scope A confirmed: up to cross resolution of Issue references). Cross matching with `gh release` is future work.
- **Effort estimation refinement (implemented; gated OFF in this repository)**: In addition to the static heuristic in §4.1, [`tools/work_discovery_scan.py`](../../tools/work_discovery_scan.py) learns a repo-calibrated effort model from the **realized effort** of recently merged PRs (changed lines / file count. Review-round count and time-to-merge are degenerate signals, so they are excluded from the composite and recorded as context only) (`--effort-history`, default 60, `0` disables). Uses `closingIssuesReferences` to bridge PR<->Issue, and measures whether the only observable predictor at triage time (Issue body length) correlates with realized effort. Only when the **data-driven gate** (sufficient sample size AND Spearman >= threshold) is cleared does it override the static estimate; otherwise the static estimate is preserved, and reason + realized effort context is made explicit in `signals[]`. In the real data of this repository, body length does not correlate with realized effort (rho ~ 0, n~23 — body length reflects the spec's detail, not code change volume), so the gate correctly declines to override, and the model adds only audit context while avoiding the misread that "the machine asserted it" (cognitive surrender, §4.4). Repos that adopt size labels in the future or where a body-length correlation emerges have the same framework auto-applying learned cutpoints. The learning fetch is **non-fatal** (on gh failure, falls back to the static heuristic; triage is not interrupted). The uncertainty-explicit contract of `effort_estimated` + `signals[]` is preserved on the learning path. The model summary is echoed to `effort_model` in the output. **Known limitation (explicit)**: The body used for the predictor is the *current* body of the closed issue, not the snapshot at merge / triage time (because gh does not offer a cheap way to fetch historical bodies). Post-close body edits can move the learned correlation / cutpoint (spec issues are rarely edited post-close, but `coverage` makes the noise source auditable for coverage). **
- **Implementation of `.claude/` skills / `.dispatcher/` prose entities**: Delivery-layer wiring for cross-repository support (Secretary skill multi-repo launch / dispatcher extension) is **implemented** ([§10.4](#104-registry-driven-repo-set-resolution), resolver `tools/work_discovery_repos.py` + the wiring of the Secretary skill / dispatcher worker_close path). The operational wiring of the effort learning gate remains a separate task.
- **Ledger entry and wiring of proposed journal events**: Additions to [`docs/journal-events.md`](../journal-events.md) for `work_discovery_scanned` etc. and the emit wiring are on the implementation task side.

## 11. Open points (requiring human judgment before implementation)

1. **Default value of N**: The candidate upper bound is defaulted to N=3, but whether to make it variable with empty pane count (empty slots = N) or fixed.
2. **Priority label scheme**: It is unconfirmed how far this repository's Issues carry a `priority:*` / `p0..p2` label scheme. If absent, the §4.1 priority computation degenerates to milestone + update time. Confirmation of the actual label distribution is needed before implementation.
3. **Variation in dependency notation**: Which of `Blocked by` / `Depends on` / task list etc. real Issues in this repository use. The extraction patterns need calibration against real data (to avoid over-match -> mistaken blocked judgment -> unfair exclusion from candidates).
4. **Trigger when idle**: When workers are zero and the org is fully idle, Option C does not fire. Whether to add a light trigger like "scan once on Secretary startup" in addition to Option B manual is an operational judgment.
