---
name: org-conveyor
description: >
  A belt conveyor in which the Lead receives an "outline of the approved scope" from the human and,
  inside it, self-drives triage → worker dispatch → iteration → verify → push → PR creation → CI watch
  in a completion-driven way, always stopping at the merge gate for every PR. A thin orchestrator that
  calls /work-discovery + /org-delegate + verify + /org-pull-request + /org-escalation.
  Fires when the human explicitly gives a scope approval saying "this range may self-drive" and wants to
  flow multiple candidates through sequentially in a completion-driven way (e.g. "self-drive the top S-class
  bug fixes from triage for as many free panes as there are; I'll decide each merge"). The trigger is
  restricted to the Lead. Whenever it touches an out-of-scope candidate, a judgment boundary, or an exit
  condition, it must halt. Merge is never automated.
effort: medium
allowed-tools:
  - Read
  - Write # first write-out of .state/conveyor/scope-contract.md (Step 1)
  - Edit # updating the scope contract (expansion via re-approval / early stop)
  - Skill
  - TaskCreate # Claude Code's built-in task-list (todo) tool. Observability backbone. Harness-provided, not repo-defined
  - TaskUpdate
  - TaskList
  - Bash(python3 tools/work_discovery_scan.py:*)
  - Bash(py -3 tools/work_discovery_scan.py:*)
  - Bash(bash tools/journal_append.sh:*)
  - Bash(py -3 tools/journal_append.py:*)
  - Bash(git diff:*) # corroborating the verify applicability classifier's touch-domain (read-only; when the worker branch is local)
  - Bash(mkdir -p .state/conveyor:*) # ensure the write-out directory for the Step 1 scope contract (fresh-checkout guard)
  # For the direct transport surface, list only the active transport (code default broker). The union of
  # broker + renga would authorize even the tools of the inactive transport and bypass the per-transport auth
  # model, so it is not allowed (design SoT: notes/broker-skill-generator-design.md #9; union rejected). The send/
  # receive machinery is delegated to sub-skills; what conveyor itself uses directly is only free-pane
  # accounting (list_panes) and draining loop events (check_messages).
  - mcp__org-broker__list_panes # free-pane accounting (backpressure)
  - mcp__org-broker__check_messages # semantic-event drain on broker pull fallback
---

# org-conveyor: self-driving loop within the approved scope (belt conveyor)

The Lead receives an **outline of the approved scope** from the human, articulates it as a machine contract, and inside it **self-drives in a completion-driven way** through `triage → /org-delegate → worker iteration → Codex round → verify (required if applicable) → push → gh pr create → pr-watch CI watch → CI green`, **always stopping at the merge gate for every PR**. The human is left with only "merging a queue of review-waiting PRs" in turn.

This skill is a **thin orchestrator**; the machinery of the actual work is delegated to existing skills. What this skill uniquely holds is only these 4: **(1) articulating and gating the approved-scope contract, (2) the completion-driven loop and backpressure, (3) observability, (4) mechanical exit conditions**. For the receive model / ack / push/PR/CI / escalation machinery, it calls the skills below:

- triage: [`/work-discovery`](../work-discovery/SKILL.md) (propose-only / candidate generation)
- dispatch: [`/org-delegate`](../org-delegate/SKILL.md) (Step 0 onward — lane selection / dispatch / receive model / ack / monitoring)
- verification: `/verify` (a Claude Code **built-in skill**. Launches the app and observes runtime behavior. Run **by the worker inside the worker's worktree** where the app + the change live) + [`.claude/skills/org-conveyor/references/verify-evidence.md`](references/verify-evidence.md) (conveyor's applicability classifier + evidence transcription)
- PR: [`/org-pull-request`](../org-pull-request/SKILL.md) (push / PR / CI watch / review loop / post-merge close)
- judgment escalation: [`/org-escalation`](../org-escalation/SKILL.md) (worker escalation to the human)

## Positioning (difference from other loop skills)

| skill | drive | stop condition | human gate |
|---|---|---|---|
| `/loop` | time-driven | none (re-runs every interval) | none |
| `/work-discovery` | event / manual | hard stop at candidate presentation (propose-only) | human picks a number per candidate |
| `/org-delegate` | one-shot delegation | returns to human at the escalation boundary | per dispatch / per escalation |
| **`/org-conveyor`** | **completion-driven loop** | **halt at the merge gate per PR / exit conditions** | **scope approval at startup (once) + per merge** |

`/org-conveyor` folds `/work-discovery`'s per-candidate human selection into an **"approved-scope contract" taken just once at startup**. Inside the scope contract it auto-admits candidates without re-asking, and **for out-of-scope candidates it does not admit them but halts at the scope edge**. This is the essential difference from propose-only / hard-stop `/work-discovery`.

## Invariants (non-negotiable / must not be broken)

- **INV-1 merge approval is a human gate**: the scope contract can pre-approve dispatch through CI watch, but **merge can never be pre-approved**. On reaching CI green, always stop, present the PR to the human, and seek merge (`feedback-merge-approval` / `feedback-no-overgate-after-decision`'s "re-approve only at irreversible points"). Do not interpret a bare "OK" as merge approval.
- **INV-2 halt whenever a scope boundary is touched**: when a candidate / judgment / diff that does not match the scope-contract predicate appears, stop self-driving and raise it to the human via [`/org-escalation`](../org-escalation/SKILL.md) (`feedback-no-stopgap` / no ad-hoc continuation).
- **INV-3 judgment escalations from a worker go to the human**: a worker's "judgment request" / "approval request" / "scope expansion" / "blocker" is not pre-approved by the Lead but raised to the human via [`/org-escalation`](../org-escalation/SKILL.md). conveyor does not auto-decide escalations.
- **INV-4 inheritance of propose-only**: candidate generation is left to [`/work-discovery`](../work-discovery/SKILL.md) (a deterministic tool), and conveyor only gates its output against the scope contract. It does not investigate / implement candidate contents on its own.
- **INV-5 trigger restricted to the Lead**: an already-delegated worker does not launch this skill (the "1 worker = 1 task = 1 scope" principle. [`CLAUDE.md`](../../../CLAUDE.md) "Role Boundaries").
- **INV-6 does not automate merge / auto-decide escalations / replace `/loop`** (Non-goals section).

## Transport layer (transport) both systems

**Per-transport authorization (no union)**: the only transport tool this skill uses directly is `list_panes` for free-pane accounting, and allowed-tools lists **only the surface of the single transport that is active in this deployment** (listing broker + renga as a union would authorize even the inactive transport's tools and bypass the per-transport auth model. Design SoT: notes/broker-skill-generator-design.md #9; union rejected). This repository's active transport is **`broker`** (code default `DEFAULT_TRANSPORT=broker`, `org-broker-channel` running), so the allowlist is rendered on the broker surface. In a deployment operated on `renga` (opt-in switch-back), regenerate this surface **per-transport** onto the renga surface (`mcp__org-broker__*` → `mcp__renga-peers__*`; the argument shape and semantics are identical. The same boundary as the per-transport generation of settings.local.json. If a full per-transport render is needed, `.md.in` + manifest-ization is a follow-up candidate, like the other transport-referencing skills). The transport-dependent differences of the send/receive machinery (ack / relay / escalation / push / PR), the two-frame relation, spawn rites, and error branching are held per-transport by each skill this one calls, so consult the overview [`CLAUDE.md`](../../../CLAUDE.md) "Transport layer (transport) both systems" section and the same-named note at the top of the full version [`/org-escalation`](../org-escalation/SKILL.md) as the primary reference (this skill does not keep a duplicate copy).

**Reception does not depend on transport tools**: conveyor's transport-specific dependence is concentrated in the **reception of completion / CI transitions**, but here the worker reports and pr-watch's `CI_COMPLETED` / `PR_MERGED` are **injected via in-band push** (broker = the channel sidecar, renga = `<channel source="renga-peers">`. pr-watch's `tools/peer_notify.py: notify_peer` chooses the active transport by raw-env decision). Receiving the in-band injection needs no tool call, and the last fallback on push failure is **polling the events table** (Read / Bash, transport-independent), so it **does not depend on broker's `check_messages` sole listening or fixed-sleep polling**. Therefore conveyor advances the loop by one turn on the trigger of "a semantic event — `CI_COMPLETED` / `PR_MERGED` / a worker report — has arrived". The per-transport details of the receive machinery (pr-watch's two-frame reception note) are left to the callee [`/org-pull-request`](../org-pull-request/SKILL.md) 2b-i.

## Step 1: articulate the approved-scope contract (at startup / human gate)

**Before** turning the loop, articulate the outline of the approval received from the human as a machine contract and get the human's confirmation. The scope contract is the **single pre-loop human gate** placed in lieu of `/work-discovery`'s per-candidate selection, and you must not start the loop without this confirmation.

- For the template, field definitions, and the boundary of "what is pre-approved / what is absolutely never approved", consult [`.claude/skills/org-conveyor/references/scope-contract.md`](references/scope-contract.md) as the primary reference.
- Write the finalized contract to `.state/conveyor/scope-contract.md` (the SoT read back for gate decisions during the loop). Before writing, ensure the parent directory with `mkdir -p .state/conveyor` (`.state/` is under gitignore, so a fresh checkout has no `conveyor/` subdirectory; idempotent).
- **What the contract pre-approves**: for candidates matching the scope predicate, `triage admission → /org-delegate dispatch → worker iteration → verify → push → gh pr create → pr-watch CI watch`. The "explicit user approval" precondition for push / PR creation ([`/org-pull-request`](../org-pull-request/SKILL.md) 2b-i) is **satisfied by this startup scope approval** (a record of a durable scope approval the human explicitly gave, not a bare per-PR OK).
- **What the contract never approves**: **merge** (INV-1). Merge is always an independent per-PR human gate. Halt at CI green and present.
- Write the scope predicate in a mechanically decidable form (e.g. `label:bug AND size:S`, `limited to follow-ups of #637`, `the review-feedback rounds of PR #635 up to ≤6`). Treat undecidable candidates as a scope edge and do not admit them (INV-2).
- The parallelism cap is the **number of free panes at startup** (backpressure section). Also state the exit budget (Codex round cap / consecutive false-positive threshold / time budget / max iterations) in the contract ([`.claude/skills/org-conveyor/references/exit-conditions.md`](references/exit-conditions.md)).

## Step 2: completion-driven loop body (the belt conveyor)

After the scope contract is finalized, turn the following in a **completion-driven** way. Each iteration is one turn of "fill free panes → wait for a completion/CI transition → admit the next by however much progressed". **Do not poll on a fixed sleep** (trigger on the arrival of a state transition).

1. **Emit the observability summary** (at iteration start. "Observability" section).
2. **triage**: launch [`/work-discovery`](../work-discovery/SKILL.md). In the conveyor context, obtain candidate JSON with the equivalent of `tools/work_discovery_scan.py --trigger post_merge --free-panes <free pane count>` (when there are free slots, `parallelizable` candidates rank higher, making the belt easier to fill). Candidate generation is left to the deterministic tool (INV-4).
3. **scope gate**: match each candidate against the scope-contract predicate.
   - **Match + free pane available** → admission target. Dispatch of a matching candidate is pre-approved by the contract, so **do not** do per-candidate human confirmation (this is the difference from `/work-discovery`'s hard stop).
   - **No match / undecidable** → **do not admit**. If the belt is forced to touch that candidate (= scope is used up and only outsiders remain, etc.), stop self-driving, raise it to the human via [`/org-escalation`](../org-escalation/SKILL.md), and halt (INV-2).
4. **dispatch**: run admission targets from Step 0 of [`/org-delegate`](../org-delegate/SKILL.md), up to the free pane count. Lane selection (light / heavy), brief generation, and dispatcher-mediated dispatch are left to org-delegate. Project context is taken as pre-resolved in the scope contract, and if org-delegate **hits a checklist item requiring human input (ambiguous terms / OS preconditions / incorporation strategy, etc.), that is a scope edge** and halts (do not auto-fill the human question).
5. **worker iteration**: the worker runs and reports via the receive model (push-primary / pull fallback). ack, the progress Progress Log, the completion REVIEW transition, and monitoring/intervention are left to [`/org-delegate`](../org-delegate/SKILL.md) Step 5. Judgment requests/blockers go to [`/org-escalation`](../org-escalation/SKILL.md) (INV-3). **This skill does not re-specify these mechanisms**.
6. **verify (conditionally required)**: on worker completion, conveyor applies the applicability classifier of [`.claude/skills/org-conveyor/references/verify-evidence.md`](references/verify-evidence.md). If app code was touched, **the worker must run `/verify` (a Claude Code built-in skill) or an equivalent app launch inside the worktree** (the actual work is delegated to the worker = conveyor itself does not launch the app), conveyor gates whether that ran, and **transcribes the repro command + output / screenshot path the worker returned as evidence into the PR body `## Test plan`**. Undecidable = halt as a scope edge (INV-2). Port collisions in parallel verify are avoided with the dynamic port-allocation discipline of [`.claude/skills/org-conveyor/references/dynamic-ports.md`](references/dynamic-ports.md).
7. **push / PR / CI watch**: fire [`/org-pull-request`](../org-pull-request/SKILL.md) 2b-i (push → `gh pr create` → `pr-watch`). The "explicit user approval" precondition is satisfied by the scope contract's pre-approval (Step 1). Advance on the arrival of `CI_COMPLETED`.
8. **CI green → HALT at the merge gate**: on reaching CI green, **stop without merging**. Emit awaiting_user (`gate=ci_green_merge_gate`, the same canonical emit as [`/org-pull-request`](../org-pull-request/SKILL.md) 2b-i / [`/org-escalation`](../org-escalation/SKILL.md)), present the human-readable understanding summary (full task) and the PR, and seek merge (INV-1). conveyor stops here for this PR (the whole belt does not stop).
9. **backpressure**: once the human merges and post-merge cleanup ([`/org-pull-request`](../org-pull-request/SKILL.md) 2b-ii) frees the pane, **immediately admit the next triage candidate into the freed slot** (back to 2). **Set no cap on the PR queue** (do not stop new triage even if N unmerged PRs pile up). **The human's merge is the natural backpressure (natural gate)**: if the human stops merging, panes are not freed and the belt naturally clogs and stops.
10. **Re-emit the observability summary right after a state transition** ("Observability" section).
11. **Exit-condition check** ([`.claude/skills/org-conveyor/references/exit-conditions.md`](references/exit-conditions.md)). Halt on any match.

> **Re-entry and handover**: when the Lead's context grows long, hand over with [`/secretary-handover`](../secretary-handover/SKILL.md) → `/clear` → [`/secretary-resume`](../secretary-resume/SKILL.md). The scope contract `.state/conveyor/scope-contract.md` and TaskList are the SoT, so after resume you can read the contract back and continue the belt (do not make the loop state depend on memory).

## Observability (required / active output)

Actively output the belt conveyor's running status as a **task-list summary the human can read at a glance**. This is not an optional operational habit but a **skill contract**; do not omit it while the belt is running (keep the human able to grasp "how far it has progressed" without prompting).

- **The state backbone is `TaskCreate` / `TaskUpdate` / `TaskList`** (Claude Code's built-in task-list / todo tool. A standard tool the harness provides to the Lead session, not repo-defined, whose `status` takes `pending` / `in_progress` / `completed`): raise each candidate on the belt as one task and transition its `status` with `TaskUpdate` on each state transition (`pending` → `in_progress` → `completed`). This is the Lead's standard UI, so with zero human cognitive load you can flow the native output straight to the human-facing window. You may put both conveyor's own control tasks tied to the scope contract (triage / dispatch / verify / PR) and the per-candidate tasks onto this backbone.
- **Required format** (formatting the `TaskList`-derived state onto one page):
  ```
  3 tasks (1 done, 1 in progress, 1 open)
  ✔ Added the decision as a comment on Issue #637
  ◼ Dispatching a worker via /org-delegate to draft the SKILL.md …
  ◻ worker completion report → push → PR creation → CI watch → mer…
  ```
  - 1-line summary: `N tasks (X done, Y in progress, Z open)` (`X`=completed / `Y`=in_progress / `Z`=pending).
  - one line per task: state symbol + title. **State symbols** are `✔` = completed / `◼` = in_progress / `◻` = pending.
  - if the title is long, elide the tail with `…` (keep it on one line).
- **Output timing** (spelled out as skill contract):
  1. **at loop-iteration start** (after admitting new triage).
  2. **right after a state transition** (per transition: worker dispatch / verify completion / CI green / PR merged / pane freed, etc.).
  3. **during long verify / CI watch, at a fixed interval** (e.g. every 5 minutes). **But suppress it if there has been no state change since the last output** (do not create notification fatigue with unchanged periodic output).
- When entering a halt (merge gate / exit condition / scope edge), also emit this summary right before stopping to leave "where on the belt it stopped".

## verify integration (conditionally required)

- **applicability classifier**: the worker decides the touch domain of the diff (app code / docs / config / fixture), and **only when app code is touched is `/verify` required**. **Undecidable = treated as a scope edge and stops** (INV-2).
- **evidence transcription**: include the repro command + output / screenshot path in the completion report and auto-transcribe it into the PR body `## Test plan`.
- **port collisions**: parallel verify across worktrees collides for apps that assume fixed ports (Next.js / broker server, etc.), so avoid it with **dynamic port allocation** (the discipline of having the worker / app side receive the port via env).
- For details, consult [`.claude/skills/org-conveyor/references/verify-evidence.md`](references/verify-evidence.md) and [`.claude/skills/org-conveyor/references/dynamic-ports.md`](references/dynamic-ports.md) as the primary reference.

## Exit conditions (mechanical)

On matching any of the following, stop self-driving, present the observability summary + reason to the human, and halt. For details, how to set thresholds, and post-halt handling, consult [`.claude/skills/org-conveyor/references/exit-conditions.md`](references/exit-conditions.md) as the primary reference.

- **Codex round max reached** → stop
- **consecutive false-positive count reaches the threshold** → stop
- **time budget exceeded / max iterations reached** → stop
- **worker escalation** → stop (via [`/org-escalation`](../org-escalation/SKILL.md), INV-3)
- **scope-edge detection** (non-matching candidate / org-delegate checklist item requires human input / verify undecidable) → stop (INV-2)

## Non-goals

- **Does not automate merge** (INV-1. Always to the human at CI green).
- **Does not auto-decide escalations** (delegated to [`/org-escalation`](../org-escalation/SKILL.md), INV-3).
- **Is not a replacement for `/loop`** (completion-driven, not time-driven. No interval polling).
- **Does not auto-admit out-of-scope candidates** (INV-2 / INV-4).
- **Does not do the worker's work** (file edits / commit / tests are the worker's; the Lead is the command tower).
- **Sets no cap on the PR queue** (human merge is the natural gate).

## Trigger and path resolution

- **The trigger is the Lead only** (INV-5). worker / dispatcher / curator do not launch it.
- The `tools/...` / `docs/...` / `.state/...` notations in this skill are relative to the repository root. The Lead session's CWD is the repository root, so they run as-is. On Windows read `python3` as `py -3` (both forms are registered in allowed-tools).
- Links to references (`references/...`) are document-relative from this SKILL.md. The notation convention follows [`docs/contributing/markdown-conventions.md`](../../../docs/contributing/markdown-conventions.md).
