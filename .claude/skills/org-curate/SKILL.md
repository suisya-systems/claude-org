---
name: org-curate
description: >
  Consolidate and reorganize accumulated raw learnings (knowledge/raw/).
  Periodically called from the Curator Claude's /loop.
  Also fires manually when asked to "organize the knowledge".
---

# org-curate: knowledge curation

Read the raw learnings accumulated under `knowledge/raw/`, classify and consolidate them, and write them to `knowledge/curated/`.

## Step 0: migration sweep (clean up old data)

Run **before** the threshold check, unconditionally. This is a migration cleanup that runs every time, to drain `active raw` files left over from the previous in-place marking scheme:

1. `mkdir -p knowledge/raw/archive/` (idempotent).
2. For each file directly under `knowledge/raw/` that contains `<!-- curated -->` near the top, `move` it to `knowledge/raw/archive/`. No need to add a marker (it is already present).
3. Run this step even when there are 0 raw files.

This way, even on environments where the new raw count is below the threshold (less than 5), files with the old marker are still swept out and do not linger on the active-raw side. After the new scheme stabilizes, this step becomes a no-op as such files reach a steady-state of zero.

## Step 1: threshold check

1. Enumerate files directly under `knowledge/raw/` (**excluding** `knowledge/raw/archive/`); after Step 0's sweep, no marker-bearing files remain in active raw.
2. Count them all as "unsorted".
3. If unsorted files are fewer than 5, do nothing and exit.
4. If 5 or more, proceed to the next step.

> Per Set A § Role: curator, the Curator's write surface is limited to `knowledge/curated/` and `knowledge/raw/archive/` (move permission). Active entries directly under `knowledge/raw/` are immutable. Step 0's migration sweep is a `move`, not a rewrite, so it does not violate this constraint.

## Step 2: read and classify

1. Read every unsorted file.
2. Classify by theme. Use the following granularity as a guide:
   - Technical area (e.g., authentication, database, frontend).
   - Tool / service (e.g., renga, github-api, aws).
   - Process (e.g., code-review, testing, deployment).
3. Read the existing `knowledge/curated/` files too, and check for duplicates.

## Step 2.5: extract skill-promotion candidates

For themes from Step 2 that match either of the following, call `.claude/skills/skill-eligibility-check/SKILL.md`:

- The same theme has **3 or more** unsorted raw files (a candidate for the raw_reappearance signal to fire).
- There is no article on the same theme in `knowledge/curated/`, and the theme contains procedural learnings (content that fits a Step-by-step format).

Construct the input as below (`context: curation`):

```yaml
context: curation
pattern_name: <inferred skill name, kebab-case; derived from the theme>
summary: <1–2 sentences on what is reusable in this theme>
task_ids: []                    # optional. Leave empty if raw notes lack a task_id.
raw_files: <array of paths to the raw/ files for this theme. Step 4 moves these to archive/, so record the post-move path (`knowledge/raw/archive/<entry>.md`) here. `skill-eligibility-check` persists this into `knowledge/skill-candidates.md`, so we want a stable, trackable final path.>
steps_outline: <main steps extracted from the raw set>
trigger_description: <situation in which this theme arises>
decision_criteria: <decision criteria appearing in the theme>
output_format: <theme's artifact format>
```

`task_ids` is not part of the standard raw schema (`Facts / Decision / Rationale / When it applies`), so an empty array is fine in the curation context. If a date or similar is in the file name, including that in `raw_files` is a serviceable substitute.

The decision determines what to do next. **Regardless of the decision, the Step-3 consolidation into curated/ proceeds normally**:

- `skill_recommend` → the skill side has already auto-appended to `knowledge/skill-candidates.md`. No additional action here.
  The corresponding raw files are still **consolidated into curated/ in Step 3 and moved to `knowledge/raw/archive/` with a marker added in Step 4** (skill promotion and curated note coexist; the curated note remains as background, while a separate skill is created as procedure. Failing to do both leaves unsorted raw files behind and breaks the threshold check).
- `candidate_queue` → consolidate into curated/ as usual in Step 3 (waiting for the next raw_reappearance).
- `curated_only` → consolidate into curated/ as usual in Step 3.

Asking the human is the Lead Claude's job; org-curate does not do it.

## Step 3: consolidate and write

For each theme:

1. If a curated file exists already, append the new learnings.
2. Otherwise, create one.
3. File name: `knowledge/curated/{theme}.md`.
4. Format:
   ```markdown
   # {Theme name}

   ## {Learning title 1}
   {Integrated description: facts, decision, rationale, when it applies.}

   ## {Learning title 2}
   ...
   ```
5. Merge duplicate learnings (keep the more concrete / accurate description).
6. When learnings contradict, prefer the more recent date and explicitly note the contradiction.

## Step 4: move to archive and add the processed marker

Consolidated raw files are not written back to active raw; they are moved into `knowledge/raw/archive/` (move-then-mark).

1. Create `knowledge/raw/archive/` (idempotent):
   ```
   mkdir -p knowledge/raw/archive/
   ```
2. Move each consolidated raw file to archive:
   ```
   mv knowledge/raw/<entry>.md knowledge/raw/archive/<entry>.md
   ```
3. After the move, append the visual marker to the top of the archived file:
   ```
   <!-- curated -->
   ```
   The marker is added **to the file after it has been moved to archive**. Files under active `knowledge/raw/` are never rewritten.

The fact that a file lives under archive/ is itself the "curated" signal, but the marker is also added for visual continuity. The Step 1 threshold check excludes archive/, so even just moving alone removes a file from the count for next time.

> Rationale: per the Set E §1.1 (Q1) ratification and Set A § Role: curator, the Curator must not mutate active entries directly under `knowledge/raw/`. Write surface is limited to creating / appending under `knowledge/curated/`, and moving (and editing the moved file) under `knowledge/raw/archive/`.

## Step 5: consider improvement proposals

Take a step back across the curated learnings and consider:

1. **Skill improvements**: do the learnings improve a skill's procedure?
   - Example: "ceiling on number of worker panes" → add a constraint to org-delegate.
2. **CLAUDE.md improvements**: anything to add to the Lead principles?
3. **Need for new skills**: does a recurring pattern justify a new skill?

When you have an improvement proposal:
- Apply the criteria from references/knowledge-standards.md.
- Send the proposal to the Lead Claude via renga-peers.
- Proposal format: "[improvement proposal] {target}: {change}. Reason: {why}".
- **Do not change anything yourself until the Lead obtains approval from the human.**

## Step 6: skill-inventory trigger check

If either of the following holds, launch `.claude/skills/skill-audit/SKILL.md`:

- 5 or more (N=5) entries with `status: pending` exist in `knowledge/skill-candidates.md`.
- 20 or more (M=20) skill directories exist under `.claude/skills/`.

Do nothing if both are below threshold. No time-based periodic trigger.
The thresholds are re-checked by `skill-audit` itself when triggered, so a coarse check here is fine.
