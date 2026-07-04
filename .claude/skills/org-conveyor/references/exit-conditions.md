# Mechanical exit conditions (exit conditions) summary

[`/org-conveyor`](../SKILL.md) self-drives in a completion-driven way, but the moment **any of the 5 mechanical exit conditions** applies, it stops self-driving and hands back to the human. An exit is not a failure but a **safety device**: it mechanically detects a situation beyond the reach of automatic judgment (churn / unexpected / the edge of scope), stops the belt, and brings human eyes in. State the exit budget in the scope contract ([`.claude/skills/org-conveyor/references/scope-contract.md`](scope-contract.md)) so it can be read back after a handover.

## List of exit conditions

| # | Condition | Default threshold | What to watch |
|---|---|---|---|
| 1 | **Codex round max reached** | `codex_round_max` (default 3) | a PR's Codex self-review fixes reach the round cap yet Blocker/Major do not converge |
| 2 | **Consecutive false-positive count reached** | `false_positive_streak_max` (default 2) | consecutive rounds where CI red / Codex Blocker / verify failure was chased but none was a change-caused real defect (flaky / benign) |
| 3 | **Time budget exceeded / max iterations reached** | `time_budget` / `max_iterations` | belt-running elapsed time / loop iteration count exceeds the contract budget |
| 4 | **worker escalation** | immediate | "judgment request" / "approval request" / "scope expansion" / "blocker" / "unexpected" / "runbook deviation" arrives from a worker |
| 5 | **scope-edge detection** | immediate | a candidate / diff that does not match / is undecidable against the scope predicate, or an org-delegate checklist item requires human input, or verify is undecidable |

## Details of each condition

### 1. Codex round max reached

- A worker's Codex self-review runs until zero Blocker/Major but caps at 3 rounds ([`/org-delegate`](../../org-delegate/SKILL.md) "Worker monitoring and intervention judgment": Codex 4th round or later is an intervention trigger). conveyor **treats this as a belt exit condition too**: if a PR does not converge at the round cap, drop that candidate from the belt and hand it to the human (the belt for the remaining candidates may continue).
- "Does not converge" mechanically: on the same PR, Codex rounds exceed `codex_round_max` yet Blocker/Major remain.

### 2. Consecutive false-positive count reached

- Count as **false-positive** a round where conveyor's automatic gate (CI interpretation / Codex Blocker / verify failure) **emitted a halt-candidate signal, but when chased was not a change-caused real defect** (flaky CI / a benign Codex finding / an environment-caused verify failure).
- The moment you catch even one real defect, the consecutive counter resets. If **consecutive** false-positives continue `false_positive_streak_max` times, the automatic gate's signals are in an untrustworthy state, so halt (do not keep churning on false signals / `feedback-no-stopgap`).
- Hold the counter tied to TaskList metadata or a conveyor control task so it can be handed over (observability section).

### 3. Time budget exceeded / max iterations reached

- Halt on exceeding `time_budget` (wall clock) or `max_iterations` (loop rounds). Do not leave long unattended self-driving open-ended.
- The elapsed origin is the scope contract's `approved_at` (or the first iteration start). Aligning the iteration count with the number of observability-summary outputs makes it easy to count.

### 4. worker escalation

- A judgment escalation / scope expansion / blocker from a worker is an **immediate halt**; conveyor does not pre-approve and hands to the canonical flow of [`/org-escalation`](../../org-escalation/SKILL.md) (ack → 3-layer state save → convey to human → forward the reply) (INV-3).
- That worker's belt slot is held until the human's judgment returns. The belt for other candidates may continue independently.

### 5. scope-edge detection

- The following are all scope edges → halt (INV-2):
  - a triage candidate **does not match / is undecidable** against the scope predicate ([`.claude/skills/org-conveyor/references/scope-contract.md`](scope-contract.md)).
  - [`/org-delegate`](../../org-delegate/SKILL.md)'s pre-delegation checks (ambiguous terms / OS preconditions / incorporation strategy, etc.) **require human input** (conveyor does not fill them in on the human's behalf).
  - verify's applicability classifier is **undecidable** ([`.claude/skills/org-conveyor/references/verify-evidence.md`](verify-evidence.md)).
- If scope is exhausted and only outside candidates remain, that too is "no further range to self-drive" = a normal exit reported to the human.

## Common behavior on halt

- Stop self-driving and present to the human the **observability summary ([`.claude/skills/org-conveyor/SKILL.md`](../SKILL.md) "Observability" section) + exit reason + the relevant PR/candidate**. Leave a one-pager of "where on the belt what happened and it stopped".
- **Exit conditions are not auto-resolved** (INV-3 / INV-6). Merge / scope expansion / escalation resolution are all human gates.
- In-progress other workers / the unmerged PR queue do not vanish on halt (the human can merge / handle them individually).
- If the human updates the scope (widening requires re-approval, [`.claude/skills/org-conveyor/references/scope-contract.md`](scope-contract.md)) the belt can resume.
