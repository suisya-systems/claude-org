# Promotion-signal definitions

Scoring criteria for the 5 signals that `skill-eligibility-check` references.
Each scores 0 / 1 (binary); the total drives a 3-way branch.

## 1. raw_reappearance

**Scores 1 if**: there are **3 or more** records about the same pattern under `knowledge/raw/`.

**Procedure**:
1. Merge the input `raw_files` with grep results for `pattern_name` across the existing raw/ tree.
2. Confirm there are 3 or more independent files covering the same pattern.
3. Consecutive records from the same task (same task_id) count as 1.

**Rationale**: 3 occurrences are enough to call it a pattern (same bar as `knowledge-standards.md`). 2 or fewer leaves room for coincidental matches.

## 2. steps_complexity

**Scores 1 if**: `steps_outline` has **3 or more** items AND contains non-obvious judgment.

**Procedure**:
1. Count the items in `steps_outline` (fewer than 3 → score 0 immediately).
2. Check whether each step is "anyone could reproduce by reading the IDE or docs".
3. Score 1 if at least one step contains:
   - Conditional branching ("if error A, then B; if error C, then D", etc.)
   - Tool-selection rationale
   - The reason other approaches fail

**Rationale**: a plain procedure list is README material. A skill earns its keep by crystallizing judgment.

## 3. trigger_articulable

**Scores 1 if**: `trigger_description` is concrete and written in searchable vocabulary.

**Procedure**:
1. If `trigger_description` is empty or only vague phrasing ("when needed", "in appropriate situations"), score 0.
2. Score 1 if it is written in concrete terms (file format, task type, input pattern).
3. Confirm the vocabulary is distinct enough that org-delegate's work-skill search can disambiguate it from other skills' descriptions.

**Rationale**: a skill that cannot be discovered may as well not exist. Avoiding "search-surface noise" requires that triggers are concrete and non-overlapping.

## 4. criteria_articulable

**Scores 1 if**: `decision_criteria` contains a quantitative threshold or a classification rule.

**Procedure**:
1. Empty or only vague phrasing ("judge appropriately") → score 0.
2. Score 1 if any of the following is present:
   - Numeric threshold ("≥ 95%", "≥ 3 times", etc.)
   - Explicit classification ("one of A / B / C")
   - Priority rule ("X takes priority over X'")

**Rationale**: a skill whose decision criteria cannot be put into words is not reproducible by a human reader either; a curated note (reference material) is sufficient.

## 5. reusable_output

**Scores 1 if**: `output_format` has a structure that can be reused across other tasks.

**Procedure**:
1. Empty `output_format` → score 0.
2. Score 1 if any of the following is present:
   - Defined section structure ("Background / Decision / Rationale", etc.)
   - Defined schema (table / YAML / JSON, etc.)
   - Explicit naming convention

**Rationale**: if outputs vary every time, downstream tasks cannot compare or cite them, and even after promotion the skill never gets reused.

## How the result is used

- 3 points or more: `skill_recommend`
- 2 points: `candidate_queue`
- 1 point or fewer: `curated_only`

The 0/1 of each signal is returned to the caller as `matched_signals` and is also stored in the candidate queue `knowledge/skill-candidates.md`. This lets a later inventory pass (`skill-audit`) trace "which signal was weak".
