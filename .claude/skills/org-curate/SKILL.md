---
name: org-curate
description: >
  Consolidate and reorganize accumulated raw learnings (knowledge/raw/).
  Called exactly once by a curator that the dispatcher spawned on demand
  when the threshold check at worker close
  (tools/check_curate_threshold.py) fired (the resident /loop is retired).
  Also fires manually when asked to "organize the knowledge".
effort: medium
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash(mkdir -p knowledge/raw/archive/)
  - Bash(mkdir -p ../knowledge/raw/archive/)
  - Bash(mv knowledge/raw/*)
  - Bash(mv ../knowledge/raw/*)
  - Bash(grep:*)
  - Bash(find knowledge/*)
  - Bash(find ../knowledge/*)
  - Bash(py -3 tools/check_curate_threshold.py:*)
  - Bash(python3 tools/check_curate_threshold.py:*)
  - Bash(py -3 ../tools/check_curate_threshold.py:*)
  - Bash(python3 ../tools/check_curate_threshold.py:*)
  - mcp__renga-peers__send_message
---

# org-curate: knowledge curation

Read the raw learnings accumulated under `knowledge/raw/`, classify and consolidate them, and write them to `knowledge/curated/`.

**Launch model (on-demand)**: this skill executes exactly one cycle per activation (`/loop` is forbidden).
Threshold judgment is consolidated into the external script [`tools/check_curate_threshold.py`](../../../tools/check_curate_threshold.py);
there is **no** internal gate like "exit immediately if fewer than 5 raw entries" inside this skill.
You receive the activation reasons `reasons[]` and execute only the matching steps.

**Path resolution (important)**: the `knowledge/...` / `tools/...` notation in this skill denotes **repo-root-relative
logical paths**. An on-demand-spawned curator pane has cwd `.curator/`, so when running via Bash,
reinterpret them as `../knowledge/...` / `../tools/...` (or absolute paths obtained via `cd .. && pwd`) —
the same convention as the "Paths" section of `.curator/CLAUDE.md` (both forms are allowed in
allowed-tools). When running manually from the repo root, use them as-is.

## Step 0: determine the activation reasons (`reasons`)

`reasons[]` takes the following 4 values:

| reason | meaning | steps to execute |
|---|---|---|
| `raw_threshold` | 5 or more active raw entries | Steps 2–5 (classify, consolidate, archive, improvement proposals) |
| `skill_candidates_pending` | 5 or more pending skill-candidates | Step 6 (fire skill-audit) |
| `work_skill_count` | 20 or more work-skills (excluding org-*) | Step 6 (fire skill-audit) |
| `legacy_marker_sweep` | `<!-- curated -->` remnants directly under raw/ | Step 1 (migration sweep; *always runs anyway*) |

1. **On-demand activation via the dispatcher**: the activation instruction message contains
   the JSON from `tools/check_curate_threshold.py` (`reasons[]` / `counts`).
   Adopt it as-is (do not recompute).
2. **Manual activation (no reasons provided)**: run the script yourself to determine them.
   From the curator pane (cwd=`.curator/`): `py -3 ../tools/check_curate_threshold.py`;
   from the repo root: `py -3 tools/check_curate_threshold.py` (POSIX: `python3`):
   - exit 0 (below_threshold) → no work to execute. Run only the Step 1 sweep, then notify
     `CURATE_SKIPPED` in Step 7 and finish
   - exit 10 (curate_needed) → adopt `reasons[]` from the stdout JSON and continue
   - exit 2 (error) → notify `CURATE_ERROR` in Step 7 and finish

## Step 1: migration sweep (clean up old data) — always runs

Run **unconditionally** every time, regardless of what `reasons[]` contains (an idempotent
cleanup; a no-op when there are no remnants). The `legacy_marker_sweep` reason exists to
guarantee that "the curator gets spawned even if only for this sweep"; the sweep itself runs
no matter what the activation reason was:

1. `mkdir -p knowledge/raw/archive/` (idempotent).
2. For each file directly under `knowledge/raw/` that contains `<!-- curated -->` near the
   top, `move` it to `knowledge/raw/archive/`. No need to add a marker (it is already present).
3. Run this step even when there are 0 raw files.

> Per Set A § Role: curator, the Curator's write surface is limited to `knowledge/curated/` and
> `knowledge/raw/archive/` (move permission). Active entries directly under `knowledge/raw/` are
> immutable. Step 1's migration sweep is a `move`, not a rewrite, so it does not violate this constraint.

**Branching from here**: if `reasons[]` contains `raw_threshold`, go to Step 2. Otherwise skip
Steps 2–5 and proceed to the Step 6 check.

## Step 2: read and classify (reason: raw_threshold)

1. Enumerate files directly under `knowledge/raw/` (**excluding** `knowledge/raw/archive/`).
   Exclude sentinels like `.gitkeep` (entries starting with `.`) (after Step 1's sweep, no
   marker-bearing files remain in active raw).
2. Read them all as "unsorted".
3. Classify by theme. Use the following granularity as a guide:
   - Technical area (e.g., authentication, database, frontend).
   - Tool / service (e.g., renga, github-api, aws).
   - Process (e.g., code-review, testing, deployment).
4. Read the existing `knowledge/curated/` files too, and check for duplicates.

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

## Step 3: consolidate and write (reason: raw_threshold)

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

## Step 4: move to archive and add the processed marker (reason: raw_threshold)

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

The fact that a file lives under archive/ is itself the "curated" signal, but the marker is also added for visual continuity. The `raw_active` count in `tools/check_curate_threshold.py` excludes archive/, so even just moving alone removes a file from the count for next time.

> Rationale: per the Set E §1.1 (Q1) ratification and Set A § Role: curator, the Curator must not mutate active entries directly under `knowledge/raw/`. Write surface is limited to creating / appending under `knowledge/curated/`, and moving (and editing the moved file) under `knowledge/raw/archive/`.

## Step 5: consider improvement proposals (reason: raw_threshold)

Take a step back across the curated learnings and consider:

1. **Skill improvements**: do the learnings improve a skill's procedure?
   - Example: "ceiling on number of worker panes" → add a constraint to org-delegate.
2. **CLAUDE.md improvements**: anything to add to the Lead principles?
3. **Need for new skills**: does a recurring pattern justify a new skill?

When you have an improvement proposal:
- Apply the criteria from references/knowledge-standards.md.
- Send the proposal to the Lead Claude via renga-peers (`to_id="secretary"`).
- Proposal format: "[improvement proposal] {target}: {change}. Reason: {why}".
- **Do not change anything yourself until the Lead obtains approval from the human.**

## Step 6: fire the skill inventory (reason: skill_candidates_pending / work_skill_count)

If `reasons[]` contains `skill_candidates_pending` or `work_skill_count`, launch
`.claude/skills/skill-audit/SKILL.md`. If neither is present, do nothing.

The threshold definitions (5+ pending / 20+ work-skills, excluding org-*) are kept in
exact agreement between `tools/check_curate_threshold.py` and skill-audit Step 1.
`skill-audit` itself re-checks the thresholds when fired, so no recomputation is needed here.

## Step 7: completion notification (always run last)

Report the cycle's outcome via **direct send to the dispatcher**. This is the trigger for
the on-demand curator's pane close, so **the destination must be `to_id="dispatcher"`**
(a channel broadcast or a secretary-addressed message would let the dispatcher's
`check_messages` wait time out, causing pane leaks / premature closes):

```
mcp__renga-peers__send_message(to_id="dispatcher", message="CURATE_DONE: ...")
```

**Ordering rule**: send this only **after** every Step 5 improvement proposal
(secretary-bound) has been sent. The contract allows the dispatcher to close the pane upon
receiving `CURATE_*`, so sending it first risks the pane being destroyed before the
improvement proposals go out.

The message is one of the following 3 kinds:

- `CURATE_DONE: reasons={reasons[]} raw {n} entries → {m} themes consolidated into curated / {k} archived / {s} swept / skill-audit {fired or none}`
  — when one or more steps executed and completed normally
- `CURATE_SKIPPED: below_threshold (counts: raw_active={n}, pending={p}, work_skill={w}, legacy_marker={l})`
  — when (e.g., on manual activation) the thresholds turned out unmet and nothing beyond the sweep was done
- `CURATE_ERROR: {one-line summary}` — when an unrecoverable error occurred mid-cycle (include any partial completion in the one line)

On manual activation (a context such as the secretary pane, where the dispatcher has no
pane-close responsibility), still send it if a dispatcher exists among the peers (harmless
as information sharing); if `[pane_not_found]`, it may be omitted.
