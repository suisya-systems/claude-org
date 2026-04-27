# skill-audit checklist

The concrete judgment procedures used by `skill-audit` for the three angles.

## 1. Deprecation candidate check

For each skill, check the following in order.

### 1.1 Mention search (observable)
- Grep `knowledge/raw/` and `knowledge/curated/` for `{skill-name}`
- Grep task logs under `.state/workers/` for `{skill-name}`
- **If there is not a single mention within the last 90 days**, set the "no mention" flag

Note: `org-delegate` embeds work-skills into instructions on a search match,
but does not persist whether "the worker actually adopted / fully used it."
Therefore what is detectable here is only "skills that did not even surface
as search candidates recently"; skills that "surfaced but went unused" are
not observable. This weakness is accepted (until observation logging is added).

### 1.2 origin.task_id reuse status (origin-tagged skills only)
- Check whether SKILL.md frontmatter has `origin.task_id`
- **If absent, skip this item** (applies to many existing skills)
- If present: check whether any similar task after `origin.task_id` exists in
  `knowledge/raw/` or `.state/workers/`
- **If there is not a single match**, set the "not reused" flag

### 1.3 Divergence between description and implementation (observable)
- Check whether the function summarized in the frontmatter `description` matches
  the contents of the Step group in the body of `SKILL.md`
- Set the "divergence" flag if any of the following holds:
  - The description references a procedure that does not appear in the body
  - The Step group in the body adds a separate function that the description
    does not mention
  - Concrete examples / tools / libraries contradict between description and body

### Deprecation candidate judgment
List as a "deprecation candidate" if **one or more** of 1.1 / 1.2 / 1.3 applies.
However **no decision is made**. Report each candidate with its flag rationale
on the assumption that a human makes the final call.
For skills where 1.2 is skipped, list candidacy based only on the 1.1 / 1.3 results.

## 2. Merge candidate check

### 2.1 Description similarity
Compare two skill descriptions pairwise:

- Verbs match (e.g. "judge" vs "judge", "analyze" vs "analyze")
- Objects overlap (the targets / outputs handled are similar)
- Only the modifiers differ ("of X" / "of Y" with the same main function)

If applicable, set the "description overlap" flag.

### 2.2 Triggers overlap
Among skills that have `triggers:` in frontmatter:

- Trigger-condition vocabulary overlaps by 50% or more
- Targets the same input format (Excel, PDF, CSV, etc.)
- Fires in the same situation (task completion, error occurrence, scheduled run, etc.)

If applicable, set the "triggers overlap" flag.

### 2.3 Specialization / generalization relationship
- One skill could run with **parameters** added on top of the other
- One is just the application of the other to a **specific brand or specific
  data set**

If applicable, set the "merge feasibility" flag.

### Merge candidate judgment
Only list pairs where **two or more** of the three items above apply as merge
candidates. A single hit is "they look similar" and is too weak to support a
merge decision.

## 3. Owner-missing check

### 3.1 Read frontmatter
Read the leading YAML frontmatter of each skill's `SKILL.md`.

### 3.2 Field check
Either of the following fields must be present with a non-empty value:

- `owner:`
- `maintainer:`

### 3.3 Listing
If neither is present / the value is empty / the value is a placeholder such
as `TBD`, mark as "owner missing."

## Report format

Follow the message template from `SKILL.md` Step 5, but append the rationale
after each candidate:

```
## Deprecation candidates
- `example-skill`: no call history (0 in 90 days), no origin reuse
- ...

## Merge candidates
- `skill-a` × `skill-b`: description overlap + specialization relationship
- ...

## Owner missing
- `skill-c`, `skill-d`, ...
```

## Notes on judgment thresholds

- **90 days**: observation window for call history. Tunable for this project's
  activity rate.
- **50%**: triggers vocabulary overlap. Too strict gives false negatives, too
  lax gives false positives.
- **2 of 3**: merge judgment threshold. A single hit produces too many false
  detections.

If divergences appear in operation, adjust the numbers above and record the
adjustment in `knowledge/raw/` as "audit operation lessons."
