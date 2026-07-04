# Approval scope contract (scope contract): template and discipline

The **single pre-loop human gate** of [`/org-conveyor`](../SKILL.md). It folds the per-candidate human selection that `/work-discovery` takes for every candidate into a **machine contract taken just once at startup**. Only inside this contract does conveyor self-drive without re-asking; the moment it touches something outside the contract it must halt ([`.claude/skills/org-conveyor/SKILL.md`](../SKILL.md) INV-1 through INV-4).

## Why articulate it as a machine contract

An approval like "PR #635 may self-drive up to round 6" or "self-drive the top S-class candidates for as many free panes as there are" has a fuzzy outline when given verbally, and conveyor cannot mechanically decide "how far is inside the approval". Running with that ambiguity risks stepping outside scope (auto-merge / mixing in a separate concern / self-approving unexpected work). So we write the outline of the approval down as a **machine-decidable predicate + budget** and confirm it with the human before running. This lets:

- conveyor **decide deterministically whether to admit** each candidate / each state transition by matching it against the contract.
- the edge of scope (does not match the contract predicate / is undecidable) become **detectable**, mechanizing the halt trigger.
- the same decision be reproduced after a handover ([`/secretary-resume`](../../secretary-resume/SKILL.md)) by reading the contract back, so the loop state does not depend on memory.

## What is pre-approved / what is never approved (boundary, non-negotiable)

| Range | Pre-approved | Rationale |
|---|---|---|
| triage admission (only candidates matching the scope predicate) | ✅ yes | entry point of the completion-driven loop |
| `/org-delegate` dispatch (matching candidates, within free panes) | ✅ yes | folds per-candidate human selection into the contract |
| worker iteration / verify | ✅ yes | in-scope work |
| **push / `gh pr create` / `pr-watch` CI watch** | ✅ yes | the startup scope approval satisfies the "explicit user approval" precondition of [`/org-pull-request`](../../org-pull-request/SKILL.md) 2b-i |
| **merge** | ❌ **never approved** | irreversible point. Always an independent per-PR human gate (`feedback-merge-approval` / `feedback-no-overgate-after-decision`) |
| admitting out-of-scope candidates | ❌ no | scope edge → halt (INV-2 / INV-4) |
| pre-approving worker escalations | ❌ no | routed to the human via [`/org-escalation`](../../org-escalation/SKILL.md) (INV-3) |

> **Why push/PR can be pre-approved (distinguished from merge)**: the **durable scope approval** in which the human explicitly says "this range may self-drive" covers the mechanical pipeline up to in-scope PR creation (`feedback-no-overgate-after-decision`: "after the user's decision is fixed, re-approve only at irreversible points"). Merge is an irreversible point, so it is placed explicitly **outside the reach of this approval** and gated every time. conveyor does not repurpose a bare per-PR "OK" as merge approval.

## Template

Write the finalized contract to `.state/conveyor/scope-contract.md` (the SoT read back for gate decisions during the loop).

```markdown
# Conveyor scope contract

- contract_id: <YYYY-MM-DD>-<topic>            # e.g. 2026-06-23-bugfix-belt
- approved_by: human (via the Lead)            # the human who approved / the route
- approved_at: <YYYY-MM-DD HH:MM>              # time the scope approval was received
- repo: <OWNER/REPO>                           # target repository (gh current resolution is fine)

## scope predicate (machine-decidable predicate)
- include: <predicate>   # e.g. label:bug AND size:S / limited to follow-ups of #637 / the review rounds of PR #635
- exclude: <predicate>   # e.g. label:needs-design / anything involving multi-file design judgment
- treatment of undecidable candidates: do not admit as scope edge (halt)

## project context (pre-resolved, to avoid the Step 0 human questions of org-delegate)
- project: <common name in registry/projects.md>
- branch convention: <feat/... etc.>
- verify policy: </verify required on app-code change / skip for docs-only, etc. Follows references/verify-evidence.md>

## parallelism / budget (exit conditions / backpressure)
- max_parallel: <free pane count at startup>   # references/exit-conditions.md
- codex_round_max: <default 3>
- false_positive_streak_max: <default 2>
- time_budget: <e.g. 2h>  /  max_iterations: <e.g. 10>
- PR queue cap: none (human merge is the natural gate)

## merge gate (non-negotiable)
- merge is not pre-approved. Halt at CI green and present each PR to the human.
```

> Write the fields with fixed keys (predicates like `label:` in a form you can hand straight to grep / gh filters). It is markdown, but it is a **structured contract** that conveyor reads back, so do not rename keys arbitrarily.

## Human-confirmation procedure (once, at startup)

1. Articulate the scope approval received from the human into the template above.
2. **Read it back and get the human's confirmation** (include "I will self-drive within this outline; you decide each merge yourself"). Do not start the loop until confirmation is obtained.
3. After confirmation, write it out to `.state/conveyor/scope-contract.md` and enter the Step 2 loop of [`.claude/skills/org-conveyor/SKILL.md`](../SKILL.md).

## Expanding / changing the contract (re-confirmation required)

- **Widening** the scope (extending the include predicate / adding another label / raising the budget) **always requires the human's re-approval**. conveyor must not self-expand the contract mid-run with "while we're at it, this too" (the same discipline as not pre-approving a worker's scope-expansion proposal; consistent with [`CLAUDE.md`](../../../../CLAUDE.md) "Boundary for follow-up requests to a Worker").
- **Narrowing / early stop** can be instructed by the human at any time (stop merging and panes stop being freed, so the belt naturally clogs up).
