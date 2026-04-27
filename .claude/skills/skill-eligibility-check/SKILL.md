---
name: skill-eligibility-check
description: >
  Common skill for judging whether a work pattern should be promoted to a skill.
  Called from org-retro and org-curate; returns a 3-value verdict
  (skill_recommend / candidate_queue / curated_only) with rationale.
  Does not auto-create skills: a recommendation is appended to
  knowledge/skill-candidates.md, and the Lead asks the human in batch once the
  candidate queue has accumulated — a two-stage workflow.
---

# skill-eligibility-check: skill promotion judgment

Score a work pattern across 5 signals to decide whether it is worth carving out
as a new work-skill, returning a 3-value verdict
(skill_recommend / candidate_queue / curated_only).
This skill itself does not generate skills nor query humans — judgment only.

## Why a common skill

If the judgment criteria were split between org-retro and org-curate, they
would inevitably drift apart. This skill is the single source of truth invoked
from both.

## Input contract

The caller passes the following structure:

```yaml
context: post_retro | curation
pattern_name: <kebab-case candidate skill name>
summary: <1-2 sentences on what is reusable>
task_ids: [<related task id>, ...]          # optional. post_retro is usually 1 entry; curation may pass an empty list
raw_files: [<knowledge/raw/ file path>, ...]
steps_outline:                              # bullet list of major steps
  - <step 1>
  - <step 2>
  - ...
trigger_description: <can the situation where this pattern applies be articulated? empty if not>
decision_criteria: <are there judgment criteria or thresholds? empty if not>
output_format: <reusable artifact format / empty if none>
```

**Required fields are only `context` / `pattern_name` / `summary` / `raw_files`
/ `steps_outline`**.
`task_ids` is not part of the standard schema for raw notes, so an empty list
is fine in the curation context.
`trigger_description` / `decision_criteria` / `output_format` are themselves
the subjects of scoring; passing them empty makes the corresponding signal
score 0.

## Step 1: Score the 5 signals

Score each signal as 0 or 1 following the definitions in `references/signals.md`.

| Signal | Condition for 1 point |
|---|---|
| raw_reappearance | Three or more raw records exist for the same pattern |
| steps_complexity | `steps_outline` has 3 or more items and includes non-trivial judgment |
| trigger_articulable | `trigger_description` can be written in concrete, searchable vocabulary |
| criteria_articulable | `decision_criteria` has a quantitative threshold or a classification rule |
| reusable_output | `output_format` has a structure transferable to other tasks |

For detailed judgment procedures, see `references/signals.md`.

## Step 2: Branch from total score into 3 values

| Total | Verdict | Meaning |
|---|---|---|
| 3 or more | `skill_recommend` | Skill recommended. Add to candidate queue |
| 2 | `candidate_queue` | Stays a candidate. Append to raw and wait for the next raw_reappearance |
| 1 or fewer | `curated_only` | A curated note is sufficient |

Rationale for the threshold of 3: slightly more conservative than the previous
"2-or-more recommends" of org-retro, intentionally creating an explicit
"candidate-only" tier to prevent "noise on the skill search surface."

## Step 3: Output

Return the following structure to the caller:

```yaml
decision: skill_recommend | candidate_queue | curated_only
score: 0-5
matched_signals: [<signal name that scored 1>, ...]
rationale: <1-2 line rationale>
proposed_skill_name: <pattern_name>    # only for skill_recommend / candidate_queue
```

## Step 4: Write to candidate queue (skill_recommend only)

Append the following entry to `knowledge/skill-candidates.md`.
Do not write for `candidate_queue` / `curated_only`.

```markdown
### {YYYY-MM-DD} {pattern-name}
- **Score**: {score}/5
- **Matched signals**: {matched_signals}
- **Rationale**: {rationale}
- **Related tasks**: {task_ids; "[]" allowed in the curation context}
- **Related raw files**: {raw_files}
- **Caller**: {context}
- **Proposed skill name**: {proposed_skill_name}
- **status**: pending
- **Decision date**: undecided
- **Reject reason**: (fill in when status transitions to rejected; otherwise omit)
- **Merged into**: (fill in when status is merged-into-*; otherwise omit)
```

The output YAML is still returned to the caller after writing
(the queue append completes as a side effect).

## Caller responsibilities

This skill performs only the judgment and the queue append. Subsequent actions
are the caller's responsibility:

- **org-retro (post_retro)**:
  - `skill_recommend` → propose to the human; on approval, create a new
    work-skill using work-skill-template.md
  - `candidate_queue` → record only the technical knowledge in raw/
  - `curated_only` → recording in raw/ is sufficient (no report needed)

- **org-curate (curation)**: regardless of the decision value, the normal
  Step 3 carries out the curated/ integration and Step 4 attaches the
  `<!-- curated -->` marker (skill promotion and curated-note creation
  coexist).
  - `skill_recommend` → only the candidate queue append (already written by
    this skill). The query to the human is the Lead's job, performed when the
    queue threshold N=5 is reached
  - `candidate_queue` → no additional action (waiting for the next
    raw_reappearance is a signal-level matter, not a license to leave raw
    unprocessed)
  - `curated_only` → no additional action

## Handling duplicate calls

When the same `pattern_name` already exists in `knowledge/skill-candidates.md`
with `status: pending`, Step 4 does not add a new entry — it merges the new
`Related tasks` / `Related raw files` into the existing entry.
Entries whose status is `approved` / `rejected` / `merged-into-*` are kept as
history, and a new entry is added under a different date (so the past reject
reason is not lost).

## When not to call this skill

- A worker simply jotting down "a useful function" → this is sufficient as a
  `knowledge/raw/` record; the 5 input items required by this skill (especially
  `steps_outline` and `trigger_description`) cannot be filled in
- A one-off investigation / debugging session → no expectation of pattern
  emergence, so the judgment cost is wasted
