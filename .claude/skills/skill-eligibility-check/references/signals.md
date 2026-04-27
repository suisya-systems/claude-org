# Promotion signal definitions

Scoring criteria for the 5 signals referenced by `skill-eligibility-check`.
All are scored as 0 or 1, and the total decides the 3-value branch.

## 1. raw_reappearance

**Condition for 1 point**: there are **3 or more** records of the same pattern
in `knowledge/raw/`.

**Procedure**:
1. Merge the input `raw_files` with the result of grepping existing raw/ for
   `pattern_name`.
2. Confirm there are 3 or more independent files covering the same pattern.
3. Successive records from a single task (with the same task_id) count as one.

**Rationale**: with 3 entries we can call it a pattern (same baseline as
`knowledge-standards.md`). At 2 or fewer, coincidence remains plausible.

## 2. steps_complexity

**Condition for 1 point**: `steps_outline` has **3 or more items** AND includes
non-trivial judgment.

**Procedure**:
1. Count items in `steps_outline` (fewer than 3 ⇒ confirmed 0 points).
2. Check whether each step is "reproducible by anyone reading the IDE or
   documentation."
3. Score 1 point if at least one step contains:
   - Conditional branching ("if error A then B, if error C then D", etc.)
   - Rationale for tool selection
   - Reasons why other approaches fail

**Rationale**: a plain procedure list is fine in a README. The value of carving
out a skill lies in "crystallizing judgment."

## 3. trigger_articulable

**Condition for 1 point**: `trigger_description` can be written in concrete,
searchable vocabulary.

**Procedure**:
1. 0 points if `trigger_description` is empty / contains only vague phrases
   like "when needed" or "in suitable situations."
2. 1 point if written in concrete terms (file format, task type, input pattern).
3. Verify the vocabulary is distinguishable from other skills' descriptions in
   `org-delegate`'s work-skill search.

**Rationale**: a skill that is never discovered may as well not exist. To avoid
adding "noise on the search surface," triggers must be concrete and
non-overlapping.

## 4. criteria_articulable

**Condition for 1 point**: `decision_criteria` has a quantitative threshold or
a classification rule.

**Procedure**:
1. 0 points if empty or only a vague phrase like "judge appropriately."
2. 1 point if any of the following exists:
   - Numeric threshold ("95% or higher", "3 or more times", etc.)
   - Explicit classification ("one of A / B / C")
   - Priority rule ("X has priority over X'")

**Rationale**: a skill whose judgment criteria cannot be put into words cannot
be reproduced by a human reader either, so a curated note (reference
information) is enough.

## 5. reusable_output

**Condition for 1 point**: `output_format` has a structure transferable to
other tasks.

**Procedure**:
1. 0 points if `output_format` is empty.
2. 1 point if any of the following exists:
   - A defined section structure ("Background / Decision / Rationale", etc.)
   - A defined schema (table, YAML, JSON, etc.)
   - An explicit naming convention

**Rationale**: if outputs vary every time, downstream tasks cannot compare or
cite them, so even after promotion to a skill no reuse occurs.

## Handling of scoring results

- 3 or more: `skill_recommend`
- 2: `candidate_queue`
- 1 or fewer: `curated_only`

The 0/1 of each signal is returned to the caller as `matched_signals` and
also remains in the candidate queue `knowledge/skill-candidates.md`.
This lets a later inventory audit (`skill-audit`) trace "which signal was weak."
