---
name: org-curate
description: >
  Organize and consolidate accumulated raw learnings (knowledge/raw/).
  Periodically invoked from the Curator Claude's /loop.
  Also used when manually told "curate the knowledge".
---

# org-curate: Knowledge curation

Read the raw learnings accumulated in knowledge/raw/, classify and consolidate them, and write them out to knowledge/curated/.

## Step 1: Threshold check

1. Enumerate the files in `knowledge/raw/`.
2. Count files **without** a `<!-- curated -->` marker as un-curated.
3. If there are fewer than 5 un-curated files, do nothing and skip.
4. If there are 5 or more, proceed to the next step.

## Step 2: Read and classify

1. Read all un-curated files.
2. Classify them by theme. Use the following granularity as a guide:
   - Technical area (e.g. authentication, database, frontend)
   - Tool / service (e.g. renga, github-api, aws)
   - Process (e.g. code-review, testing, deployment)
3. Read existing `knowledge/curated/` files as well, and check for duplicates.

## Step 2.5: Extract skill candidates

Among the themes classified in Step 2, for those that match either of the
following, call `.claude/skills/skill-eligibility-check/SKILL.md`:

- 3 or more un-curated raw files belong to the same theme (a candidate where the raw_reappearance signal fires)
- No article on the same theme exists in the existing `knowledge/curated/`, AND it includes procedural knowledge (content describable as a sequence of Steps)

Build the input (`context: curation`) on call as follows:

```yaml
context: curation
pattern_name: <inferred skill name, kebab-case. derive from the theme name>
summary: <1-2 sentences on what is reusable for this theme>
task_ids: []                    # optional. leave empty if raw notes have no task_id
raw_files: <array of raw/ paths for the same theme>
steps_outline: <main steps extracted from the raw set>
trigger_description: <situations where this theme fires>
decision_criteria: <decision criteria appearing within the theme>
output_format: <output format of the theme>
```

`task_ids` is not part of the existing raw standard schema (`facts / decision / rationale / when-to-apply`),
so it may be left as an empty array in the curation context. If a date or similar can be read from the raw filename, including it in `raw_files` is an acceptable substitute.

The handling depends on the resulting decision. **In all decisions, the curated/ consolidation in Step 3 proceeds as usual**:

- `skill_recommend` → the skill side has already auto-appended to `knowledge/skill-candidates.md`. No additional work in this step.
  The raw files in question are **also consolidated into curated/ in Step 3 and tagged with `<!-- curated -->` in Step 4**
  (skill creation and curated note creation coexist. The curated note remains as background knowledge,
  while the skill is created separately as a procedural form. If both are not done, un-curated raw files pile up and the threshold check breaks.)
- `candidate_queue` → consolidate into curated/ in Step 3 as usual (await the next raw_reappearance)
- `curated_only` → consolidate into curated/ in Step 3 as usual

Asking the human is the Lead Claude's role; org-curate does not do it.

## Step 3: Consolidate and write out

For each theme:

1. If a curated file already exists, append the new knowledge to it.
2. Otherwise, create a new one.
3. Filename: `knowledge/curated/{theme}.md`
4. Format:
   ```markdown
   # {theme name}

   ## {knowledge title 1}
   {description integrating facts, decision, rationale, and when-to-apply}

   ## {knowledge title 2}
   ...
   ```
5. Merge duplicate knowledge (keep the more specific / accurate description).
6. When two pieces of knowledge contradict each other, prefer the one with the more recent date and clearly note the contradiction.

## Step 4: Processed marker

Prepend the following to raw files whose consolidation is complete:
```
<!-- curated -->
```
This makes them no longer counted in the next threshold check.

## Step 5: Consider improvement proposals

Take a step back over the curated knowledge and consider:

1. **Skill improvements**: Does the knowledge lead to procedural improvements in a skill?
   - e.g. "Worker pane count limit" → a constraint should be added to org-delegate.
2. **CLAUDE.md improvements**: Should something be added to the Lead's principles?
3. **Need for a new skill**: Can a recurring pattern be split out as a new skill?

When you have improvement proposals:
- Make the judgment per the criteria in references/knowledge-standards.md
- Send the proposal to the Lead Claude via renga-peers
- Proposal format: "[Improvement proposal] {target}: {change}. Reason: {why}"
- **Do not change anything yourself until the Lead has obtained human approval.**

## Step 6: Skill audit firing check

If either of the following is met, launch `.claude/skills/skill-audit/SKILL.md`:

- 5 or more (N=5) entries with `status: pending` in `knowledge/skill-candidates.md`
- 20 or more (M=20) skill directories under `.claude/skills/`

If both are below threshold, do nothing. There is no time-based periodic firing.
The thresholds are re-checked by `skill-audit` itself at firing time, so this step can be coarse.
