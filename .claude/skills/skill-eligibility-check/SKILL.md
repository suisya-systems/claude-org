---
name: skill-eligibility-check
description: >
  Shared skill that decides whether a work pattern should be promoted
  to a skill. Called from org-retro and org-curate; returns a 3-value
  verdict (skill_recommend / candidate_queue / curated_only) with
  rationale.
  Does not auto-create skills. A "recommend" appends to
  knowledge/skill-candidates.md, and the Lead later batch-asks the
  human once the queue accumulates — a two-stage handoff.
---

# skill-eligibility-check: skill-promotion judgment

Score a work pattern against 5 signals to decide whether it is worth carving out as a new work-skill, and return one of 3 verdicts (skill_recommend / candidate_queue / curated_only).
This skill itself never creates a skill or asks the human — it is judgment-only.

## Why a shared skill

If the criteria lived in both org-retro and org-curate they would inevitably drift. This skill is the single source of truth and is called from both.

## Input contract

The caller passes the following structure:

```yaml
context: post_retro | curation
pattern_name: <kebab-case candidate skill name>
summary: <1–2 sentences on what is reusable>
task_ids: [<related task id>, ...]          # optional. post_retro typically has 1, curation may pass an empty array.
raw_files: [<knowledge/raw/ file path>, ...]
steps_outline:                              # bullet list of the main procedure
  - <step 1>
  - <step 2>
  - ...
trigger_description: <can the situation in which this pattern applies be put into words? leave empty if not>
decision_criteria: <are there decision criteria or thresholds? leave empty if not>
output_format: <reusable artifact format, or empty>
```

**Required**: only `context` / `pattern_name` / `summary` / `raw_files` / `steps_outline`.
`task_ids` is not part of the standard raw-note schema, so the curation context can pass an empty array.
`trigger_description` / `decision_criteria` / `output_format` are themselves the things being scored; if left empty, the corresponding signal scores 0.

## Step 1: score the 5 signals

Score each signal 0 / 1 per the definitions in `references/signals.md`.

| Signal | Scores 1 if |
|---|---|
| raw_reappearance | At least 3 raw records cover the same pattern. |
| steps_complexity | `steps_outline` has ≥ 3 items AND contains non-obvious judgment. |
| trigger_articulable | `trigger_description` is concrete and written in searchable vocabulary. |
| criteria_articulable | `decision_criteria` contains a quantitative threshold or a classification rule. |
| reusable_output | `output_format` has a structure that is reusable across other tasks. |

For the detailed scoring procedure see `references/signals.md`.

## Step 2: branch on total score (3-way)

| Total | Verdict | Meaning |
|---|---|---|
| ≥ 3 | `skill_recommend` | Recommend promotion. Add to the candidate queue. |
| 2 | `candidate_queue` | Stays a candidate. Append to raw and wait for the next raw_reappearance. |
| ≤ 1 | `curated_only` | A curated note is sufficient. |

Rationale for the 3-point threshold: slightly more conservative than the old org-retro rule of "2 or more = recommend"; explicitly creating a "candidate" tier prevents "skill-search-surface noise".

## Step 3: output

Return the following structure to the caller:

```yaml
decision: skill_recommend | candidate_queue | curated_only
score: 0-5
matched_signals: [<signal names that scored 1>, ...]
rationale: <1–2 line rationale>
proposed_skill_name: <pattern_name>    # only for skill_recommend / candidate_queue
```

## Step 4: write to candidate queue (only on skill_recommend)

Append the following entry to `knowledge/skill-candidates.md`. Do not write for `candidate_queue` or `curated_only`.

```markdown
### {YYYY-MM-DD} {pattern-name}
- **score**: {score}/5
- **matched signals**: {matched_signals}
- **rationale**: {rationale}
- **related tasks**: {task_ids; "[]" allowed in the curation context}
- **related raw files**: {raw_files}
- **caller**: {context}
- **proposed skill name**: {proposed_skill_name}
- **status**: pending
- **decision date**: TBD
- **rejection reason**: (filled when status transitions to rejected; otherwise omit)
- **merge target**: (filled when status is merged-into-*; otherwise omit)
```

After writing, still return the output YAML to the caller (the queue append is a side effect and counts as complete).

## Caller responsibilities

This skill only decides and appends to the queue. Subsequent actions are the caller's responsibility:

- **org-retro (post_retro)**:
  - `skill_recommend` → propose to the human; on approval, create a new work-skill from work-skill-template.md.
  - `candidate_queue` → record only the technical knowledge under raw/.
  - `curated_only` → recording in raw/ is enough (no report needed).

- **org-curate (curation)**: regardless of the decision value, do the regular Step 3 (consolidate into curated/) + Step 4 (`<!-- curated -->` annotation). Skill promotion and curated notes coexist.
  - `skill_recommend` → only append to the candidate queue (the skill writes it automatically). Asking the human is the Lead's job, performed once the queue reaches the threshold N=5.
  - `candidate_queue` → no extra action ("waiting for the next raw_reappearance" is a signal-side concept, not "leave raw unsorted").
  - `curated_only` → no extra action.

## Handling duplicate calls

If a pending entry for the same `pattern_name` already exists in `knowledge/skill-candidates.md`, Step 4 does not add a new entry; instead it merges-appends the new entry's "related tasks" / "related raw files" into the existing entry. Entries already in `approved` / `rejected` / `merged-into-*` are kept as history, and a new entry is added under a different date (so past rejection reasons are not lost).

## When NOT to call this skill

- A worker simply wants to memo "a useful function" → recording in `knowledge/raw/` is enough. The 5 input fields (especially `steps_outline` and `trigger_description`) cannot be filled.
- One-off investigation / debugging — no expectation of a recurring pattern; the judgment is wasted.
