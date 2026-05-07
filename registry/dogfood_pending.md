# dogfood_pending register

This is the SoT referenced by the paired dogfood follow-up protocol of org-delegate Step 1.8 / Issue #338. For each PR that introduces a new tool / runtime / workflow, append one row to track paired follow-up issue creation and earmarking of the next dogfood pass.

For details, see [`.claude/skills/org-delegate/SKILL.md`](../.claude/skills/org-delegate/SKILL.md) Step 1.8 and [`.claude/skills/org-delegate/references/dogfood-issue-template.md`](../.claude/skills/org-delegate/references/dogfood-issue-template.md).

## Update rules

This is a partial-update register. New rows are appended; existing rows allow per-column updates within a single row (logical deletion / row reordering forbidden). The state transitions and update owners are SoT'd in SKILL.md Step 1.8 §register state transitions.

## `status` semantics

- `pending`: implementation PR is planned / opened, but the paired follow-up issue is not yet created (just appended by org-delegate Step 1.8 §A)
- `open`: paired follow-up issue created / dogfood pass not yet run (org-pull-request transitions `pending → open`)
- `consumed`: dogfood pass completed. Defects already aggregated on the paired issue (transitioned `open → consumed` upon receipt of the dogfood-pass Worker's completion report)
- `closed`: paired issue closed / split into individual fix issues, or no defects (org-pull-request transitions `consumed → closed`)

## entries

| task_id | tool / surface | impl_pr | dogfood_issue | dogfood_run_task_id | status |
|---------|----------------|---------|---------------|---------------------|--------|
| <!-- e.g., issue-NNN-foo --> | <!-- tools/foo.py --> | <!-- #NNN --> | <!-- #NNN --> | <!-- issue-MMM-bar --> | <!-- pending --> |
