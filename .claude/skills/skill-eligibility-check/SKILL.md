---
name: skill-eligibility-check
description: >
  Shared skill that decides whether a work pattern should be promoted
  to a skill. Called from org-retro and org-curate; returns a 3-value
  verdict (skill_recommend / candidate_queue / curated_only) with
  rationale.
  Does not auto-create skills. A "recommend" appends to the
  machine-local knowledge/skill-candidates.local.md, and the Lead
  later batch-asks the human once the queue accumulates — a
  two-stage handoff.
effort: low
allowed-tools:
  - Read
  - Edit
  - Write
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

Append the following entry to `knowledge/skill-candidates.local.md` (the machine-local file holding the real entries, Issue #755). Do not write for `candidate_queue` or `curated_only`.

> **The append target is always `.local.md`, never the public file.** The public
> [`knowledge/skill-candidates.md`](../../../knowledge/skill-candidates.md) holds **the entry-format
> definition only** and its entry list is kept **permanently empty**, so that operator-private
> candidates never reach the OSS repository (`knowledge/skill-candidates.local.md` is gitignored).
> The format definition, status vocabulary, and operating rules are read from the head of the public
> file as the primary reference; only the real entries go into `.local.md`. If `.local.md` does not
> exist yet, create a minimal file carrying the `## エントリ一覧` heading and append to that.
> The threshold count (`tools/check_curate_threshold.py` / `/skill-audit`) reads both files summed.

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
  - `skill_recommend` → queue append only (already done in Step 4). Do not propose to the human immediately.
    The batch ask is performed by the Lead once pending ≥ 5
    (primary reference: top of [`knowledge/skill-candidates.md`](../../../knowledge/skill-candidates.md), Issue #68 policy. Same when `/skill-audit` fires.)
  - `candidate_queue` → record only the technical knowledge under raw/.
  - `curated_only` → recording in raw/ is enough (no report needed).

- **org-curate (curation)**: regardless of the decision value, do the regular Step 3 (consolidate into curated/) + Step 4 (`<!-- curated -->` annotation). Skill promotion and curated notes coexist.
  - `skill_recommend` → only append to the candidate queue (the skill writes it automatically). Asking the human is the Lead's job, performed once the queue reaches the threshold N=5.
  - `candidate_queue` → no extra action ("waiting for the next raw_reappearance" is a signal-side concept, not "leave raw unsorted").
  - `curated_only` → no extra action.

## Handling duplicate calls

If a pending entry for the same `pattern_name` already exists in `knowledge/skill-candidates.local.md`, Step 4 does not add a new entry; instead it merges-appends the new entry's "related tasks" / "related raw files" into the existing entry (the duplicate check also reads `.local.md`, the file that holds the real entries — the public file is always empty). Entries already in `approved` / `rejected` / `merged-into-*` are kept as history, and a new entry is added under a different date (so past rejection reasons are not lost).

If an entry for the same `pattern_name` is already `deferred` (a candidate the human was shown and chose to shelve), Step 4 **neither re-adds it nor moves it back to `pending`** (shelving is treated as settled, so the same candidate is not dredged up — Issue #753). `deferred` is excluded from the threshold count and from re-asking. Only when the human explicitly wants to reconsider should a separate entry be raised under a new date.

## When NOT to call this skill

- A worker simply wants to memo "a useful function" → recording in `knowledge/raw/` is enough. The 5 input fields (especially `steps_outline` and `trigger_description`) cannot be filled.
- One-off investigation / debugging — no expectation of a recurring pattern; the judgment is wasted.
