# skill-audit checklist

Concrete decision procedure that `skill-audit` runs across the 3 audit dimensions.

## 1. Deprecation-candidate check

For each skill, walk through the following in order.

### 1.1 Reference search (observable)
- grep `knowledge/raw/` and `knowledge/curated/` for `{skill-name}`.
- grep task logs under `.state/workers/` for `{skill-name}`.
- **If there is not a single mention within the last 90 days**, raise the "no references" flag.

Note: `org-delegate` embeds a matched work-skill into its instructions, but it does not persist "did the worker actually adopt it / use it through". So all that this check can detect is "skills that have not even appeared as a search candidate recently"; "skills that appeared but went unused" remain unobservable. We accept this gap (until observation logs are added).

### 1.2 origin.task_id reuse (origin-tagged skills only)
- Confirm whether the SKILL.md frontmatter has `origin.task_id`.
- **If absent, skip this item** (which applies to many existing skills).
- If present: are there similar tasks under `knowledge/raw/` or `.state/workers/` after `origin.task_id`?
- **If none**, raise the "not reused" flag.

### 1.3 description-vs-implementation drift (observable)
- Does the frontmatter `description` summarize features that match the body's Step sections?
- Raise the "drift detected" flag if any of the following holds:
  - The description mentions procedures that are not in the body.
  - The body's Steps add separate features that the description does not mention.
  - Concrete examples / tools / libraries contradict between description and body.

### Deprecation-candidate decision
A skill is listed as a "deprecation candidate" if **at least one** of 1.1 / 1.2 / 1.3 fires.
**Do not decide here.** The human makes the final call; report each flag with its supporting evidence.
For skills where 1.2 was skipped, candidate status is determined by 1.1 / 1.3 alone.

## 2. Duplication / consolidation check

### 2.1 description similarity
Compare two skill descriptions pairwise:

- Verbs match ("decide" vs "decide", "analyze" vs "analyse", etc.).
- Objects overlap (similar subjects / outputs).
- Only modifiers differ ("X's" vs "Y's" wrapping the same core function).

If yes, raise the "description duplicate" flag.

### 2.2 triggers overlap
For skills that have `triggers:` in their frontmatter:

- Trigger-condition vocabulary overlaps by 50% or more.
- Targets the same input format (Excel, PDF, CSV, etc.).
- Fires in the same situation (task completion, error, periodic run, etc.).

If yes, raise the "triggers overlap" flag.

### 2.3 specialization / generalization relationship
- One skill could run the other if a **parameter** were added.
- One is just a **brand-specific or data-specific** application of the other.

If yes, raise the "consolidation possible" flag.

### Consolidation-candidate decision
Only pairs that fire **2 or more** of the above are listed as consolidation candidates.
A single flag is "looks similar" — too weak for a consolidation decision.

## 3. owner-missing check

### 3.1 frontmatter read
Read the leading YAML frontmatter of each skill's `SKILL.md`.

### 3.2 field check
Confirm one of the following is present and non-empty:

- `owner:`
- `maintainer:`

### 3.3 listing
If neither field exists, the value is empty, or the value is a placeholder like `TBD`, list the skill under "owner missing".

## Report format

Follow the message template in `SKILL.md` Step 5, but append the supporting evidence after each candidate:

```
## Deprecation candidates
- `example-skill`: no call history (0 mentions in 90 days), no origin reuse
- ...

## Consolidation candidates
- `skill-a` × `skill-b`: description duplicate + specialization relationship
- ...

## owner missing
- `skill-c`, `skill-d`, ...
```

## Notes on thresholds

- **90 days**: observation window for call history. Tune for this project's activity rate.
- **50%**: triggers vocabulary overlap. Too strict → false negatives; too loose → false positives.
- **2-of-3**: consolidation threshold. Listing as a candidate on a single match raises the false-positive rate.

If operations show drift from these numbers, adjust them and record the lesson in `knowledge/raw/` as "audit-operations learning".
