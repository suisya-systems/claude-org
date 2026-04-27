---
name: skill-audit
description: >
  Skill inventory audit (deprecation candidates / merge candidates / owner-missing check).
  Fires on a state-based trigger: only runs when the candidate queue
  knowledge/skill-candidates.md has 5 or more pending entries, or when the
  number of work-skills under .claude/skills/ (excluding org-*) reaches 20 or more.
  Does not fire on time-based /loop (avoids polluting raw logs on days with no change).
---

# skill-audit: skill inventory audit

To prevent noise in `org-delegate`'s work-skill search as the skill count grows,
the inventory is audited on a **state-based** trigger rather than periodically.

The real concern is not the skill count itself, but "noise on the search surface."
This skill mechanically checks three angles (deprecation / merge / owner-missing)
and sends consolidated change proposals to the Lead's Claude.
It never deletes or modifies skills automatically.

## Step 1: Trigger condition check (state-based)

Exit immediately (without leaving a log) unless one of the following holds.

```bash
# Number of pending entries in the candidate queue
cand_count=$(grep -c '^- \*\*status\*\*: pending' knowledge/skill-candidates.md 2>/dev/null || echo 0)

# Number of work-skills (excludes org-*; aligns with the work-skill search target that produces noise)
work_skill_count=$(find .claude/skills -maxdepth 2 -name SKILL.md \
  | grep -v '/org-' | wc -l)
```

- Continue if `cand_count >= 5` **or** `work_skill_count >= 20`
- Exit otherwise (no report needed in this case)

Rationale for the numbers: defaults are N=5 / M=20. Adjust via PR if they
become heavy in actual operation.
Rationale for excluding `org-*`: the noise source is `org-delegate`'s work-skill
search, and the size of `org-*` does not directly affect that search noise.

## Step 2: Identify deprecation candidates

For each skill, evaluate the following. **Use only currently observable items**
for mechanical judgment; treat unobservable items as "needs review" and leave
them to human judgment. See `references/audit-checklist.md` for details.

Observable (usable for mechanical judgment):
- A clear divergence between the description and the Step contents in `SKILL.md`
  body (assessable from inside the file).
- Grep `knowledge/curated/` / `knowledge/raw/` / `.state/workers/` for `{skill-name}`
  and find zero mentions in the last 90 days (within this project's observation
  scope only).

Unobservable (treated as "needs review"; cannot be used for deprecation):
- `org-delegate` only embeds work-skills into instructions and does not persist
  whether they were "actually adopted." Mention searches therefore yield only
  "matched in search" information.
- Many existing skills lack `origin.task_id`, so reuse-judgment has no anchor.
  Use only origin-tagged skills for the "no reuse" judgment; skip origin-less ones.

**No deprecation decision is made. Items only get added to the proposal list**;
final judgment is left to a human. Sections 1.1 / 1.2 / 1.3 of audit-checklist.md
follow the same policy in detail.

## Step 3: Identify merge candidates

Pair-wise across skills, check for the following:

- Subject words (verb / object) overlap in the descriptions
- Triggers (or fire conditions inside descriptions) overlap
- One is a specialization of the other and could be subsumed by parameter
  substitution

Pairs with merge suspicion are listed as "merge candidates."
The actual merge decision is made by a human, so this step only proposes.

## Step 4: Identify owner-missing skills

Read every skill's SKILL.md frontmatter and check:

- Skills with no `owner:` or `maintainer:` field
- Or where the field is an empty string

These are listed as "owner missing."
It is expected that all existing skills in this project currently lack an owner;
the first audit run will likely produce a bulk proposal.

## Step 5: Report

Send to the Lead's Claude via `renga-peers` `send_message(to_id="secretary", ...)`.

```
[skill-audit] Inventory result
- Deprecation candidates: {n} ({skill-name} list)
- Merge candidates: {m} pairs ({skill-a} × {skill-b} list)
- Owner missing: {k} ({skill-name} list)

Trigger condition: cand_count={cand_count} / skill_count={skill_count}
Details: see the appended list at the end of this message for the rationale.

After human approval, please carry out the deletion / merge / owner addition.
No automatic changes have been made.
```

Even when there are zero candidates (a clean state), still report:
"audit ran, no change proposals." Since the next run will not happen until the
threshold is exceeded again, recording the fact that the audit ran has value
even at zero.

## Trigger paths

This skill never runs autonomously. It is invoked via one of the following:

1. `org-curate` Step 6 (skill-audit firing check) calls it when thresholds are
   met (recommended path)
2. The Lead manually invokes it after looking at `skill-candidates.md`
3. A human asks "do an inventory audit"

Time-based starts such as `/loop` are not used.

## Why automatic changes are avoided

- A wrong deprecation produces a "no usable skill" state on the `org-delegate`
  side (degrading dispatch precision).
- A merge requires reconciling description / triggers / steps and cannot be
  done mechanically.
- For owner addition, manual confirmation is the lightest workflow (automating
  it brings little benefit).

For these reasons, this skill **stops at proposal**, and changes are made
manually by the Lead after human approval.
