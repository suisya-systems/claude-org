# dogfood follow-up issue protocol (Lead + org-pull-request coordination, Issue #338)

> **Primary reference source**: [`.claude/skills/org-delegate/SKILL.md`](../SKILL.md) Step 1.8 (application overview only). This document is the detailed SoT for trigger conditions, the Lead's (A)/(B) responsibilities, org-pull-request coordination, the register format, state transitions, and consumed→closed hygiene.

For PRs that introduce a new tool / runtime / workflow, create a "dogfood follow-up" issue paired with the implementation PR, and explicitly earmark the next delegation that actually uses that new tool as a **dogfood pass**. This protocol is based on the phenomenon in the Curator session #18 retrospective where "PR #288 only surfaced 4 categories of defects on first real use" (also reproduced in session #11).

## Trigger conditions

Fires when the task is one of the following:

- Adding a new CLI tool / script (`tools/*.py`, `tools/*.sh`, `tools/*.ps1`, etc.)
- Introducing a new runtime / new workflow / new protocol
- Re-design of an existing tool that involves a breaking change

## The Lead's (org-delegate) responsibilities

The dogfood protocol spans **2 delegations**: (A) the **implementation delegation** that introduces the new tool, and (B) the subsequent **dogfood pass delegation** that actually uses that tool. The Lead reads and writes `registry/dogfood_pending.md` in both.

### (A) When filing the implementation delegation (same timing as Step 1.7 evaluation)

1. Determine that the trigger conditions apply and, in parallel with preview, mark it as a "dogfood-target task"
2. Append 1 new row to `registry/dogfood_pending.md` with `status=pending` / `dogfood_issue` / `dogfood_run_task_id` empty / `impl_pr` empty (PR number filled in later). At this point the implementation PR itself does not yet exist
3. The brief for the implementation worker need not mention dogfood (neither issue number nor PR number is fixed at this point). The implementation worker simply builds the tool as usual

### (B) When filing the dogfood pass delegation

4. Whenever filing a new delegation, check `registry/dogfood_pending.md`'s `status=open` rows (= paired follow-up issue created / dogfood pass not yet performed) each time
5. If the new task to be filed actually uses the target in the `tool / surface` column, earmark that task as a dogfood pass:
   - Add `--impl-guidance "Dogfood pass for paired follow-up issue #<N>. Report any defects to that issue using the format in references/dogfood-issue-template.md. Refs #<N>, do not Closes."` to the `apply` call
   - Additionally pass `--knowledge .claude/skills/org-delegate/references/dogfood-issue-template.md` to include the defect-reporting format in the brief
6. Update the relevant row: fill `dogfood_run_task_id=<new task_id>`, and leave `status` as `open` (transitions to `consumed` upon receipt of the completion report from the dogfood worker; see §Register state transitions)

## org-pull-request's responsibilities (cross-ref)

Done at the time of implementation PR creation / merge (detailed procedure is maintained separately on the org-pull-request side; Issue #338's scope is to record this protocol):

1. Immediately after implementation PR creation: find the matching `status=pending` row in `registry/dogfood_pending.md`, fill in `impl_pr=#<NNN>`, and create the paired follow-up issue via `gh issue create --body-file <rendered template>` (template: [`dogfood-issue-template.md`](dogfood-issue-template.md))
2. Fill the created issue number into the row's `dogfood_issue=#<MMM>`, and transition `status` from `pending → open`
3. Append `Paired dogfood issue: #<MMM>` to the bottom of the implementation PR body
4. When the paired issue is closed, transition the row's `status` from `consumed → closed`

## dogfood_pending register format

`registry/dogfood_pending.md` is **a partial-update register, not append-only**: row additions are append; updates to each column (`impl_pr` / `dogfood_issue` / `dogfood_run_task_id` / `status`) are allowed. Logical deletion and row reordering are prohibited.

```
| task_id | tool / surface | impl_pr | dogfood_issue | dogfood_run_task_id | status |
|---------|----------------|---------|---------------|---------------------|--------|
| issue-XXX-new-tool | tools/foo.py | #YYY | #ZZZ | issue-MMM-bar | open |
```

## Register state transitions

```
[Row added] (org-delegate Step 1.8 §A.2)
  status = pending      ← issue not created / impl_pr also empty
       │
       │ Implementation PR created + paired issue created (org-pull-request §1-2)
       ▼
  status = open         ← paired issue created / dogfood pass not yet performed
       │
       │ Earmarked by a subsequent delegation (org-delegate Step 1.8 §B.5-6)
       │ Fill dogfood_run_task_id. status stays open
       │
       │ Dogfood pass worker completion report received → defects aggregated into paired issue
       ▼
  status = consumed     ← defect monitoring period
       │
       │ Paired issue closed (org-pull-request §4)
       ▼
  status = closed       ← terminal
```

Each transition is a **single-column diff rewrite** on a single row of the table. Rewriting multiple columns simultaneously (e.g., pending → open is a batched update of `impl_pr`, `dogfood_issue`, and `status`) is allowed as long as it stays on the same row.

## consumed → closed observation timing (Lead's register hygiene responsibility)

Because the paired follow-up issue can be closed outside the implementation PR's lifecycle (manual close / split into individual fix issues / cleanup after long idle), relying only on `org-pull-request`'s trigger events (PR creation / review / post-merge close) will cause detection gaps. The Lead performs the following hygiene check at **every opportunity it writes to `registry/dogfood_pending.md`** (= implementation delegation filing / dogfood pass earmarking / dogfood pass completion receipt / status check):

```bash
# For status=consumed rows, transition to closed if the paired dogfood_issue is closed
gh issue view <dogfood_issue> --json state -q .state
  # → if "CLOSED", rewrite status from consumed to closed
```

In addition, the briefing at `/org-resume` startup also scans `status=consumed` rows once each and closes them (resume-time hygiene). This ensures that even if consumed lingers in the register, it is always reaped by the next register operation.
