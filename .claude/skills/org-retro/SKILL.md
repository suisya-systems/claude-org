---
name: org-retro
description: >
  Retrospective on the delegation process. After a delegation of work to a Worker is complete,
  reflect on how the delegation itself went, and record process-improvement knowledge.
  In addition, judge whether the work pattern of the completed task should be accumulated as a work-skill.
  Technical retrospectives on the actual work are done by the Worker automatically and are not handled here.
---

# org-retro: Delegation-process retrospective

After a delegation to a Worker is complete, reflect on and improve the delegation process itself.
In addition, judge whether the completed task's work pattern is reusable as a work-skill.

**Note**: Technical knowledge from the actual work (gotchas, API quirks, etc.) is recorded automatically
to `knowledge/raw/` by the Worker per the instructions in CLAUDE.md. It is not handled here.

## Step 1: Retrospective on the delegation process

Sort through:
- **Was the task breakdown appropriate?**: Was the granularity too large or too small?
- **Were the instructions clear?**: Could the Worker work without confusion? Did they ask many questions?
- **Was the project selection correct?**: Could they work in the correct directory?
- **Was the parallelism appropriate?**: Were there too many or too few Workers?
- **Was the completion report sufficient?**: Was the Worker's report enough to explain to the human?

## Step 2: Decide which knowledge to improve

Use the following criteria to decide "should this be recorded":

**Record**:
- A pattern likely to be encountered again in the same kind of delegation
- An insight that leads to improving the instruction template
- A project-specific constraint that will affect us next time
- Improvement points where the Worker's retrospective record was insufficient/excessive

**Do not record**:
- Task-specific one-off problems
- Things the Worker has already recorded as technical knowledge

## Step 3: Record

If you have knowledge worth recording, create a file at the following path:

- Path: `knowledge/raw/{YYYY-MM-DD}-delegation-{topic}.md`
- `{topic}` is English kebab-case (e.g. `delegation-task-granularity`, `delegation-frontend-instructions`)
- Prefix with `delegation-` to distinguish from the Worker's technical knowledge

### File format

See "Recording format" in `.claude/skills/org-curate/references/knowledge-standards.md`.

## Step 4: Judging work-skill creation

Call `skill-eligibility-check` for the work pattern of the completed task and judge
whether it should be accumulated as a work-skill.

The substance of the criteria is centralized in `.claude/skills/skill-eligibility-check/references/signals.md`,
and both org-retro and org-curate reference the same criteria (to prevent divergence in judgment).

### Step 4.1: Call skill-eligibility-check

Build the following input and call:

```yaml
context: post_retro
pattern_name: <inferred skill name, kebab-case>
summary: <1-2 sentences on what is reusable>
task_ids: [<this task_id>]
raw_files: <array of knowledge/raw/ paths recorded by the Worker>
steps_outline:
  - <main step 1>
  - <main step 2>
  - ...
trigger_description: <situations where this pattern applies>
decision_criteria: <decision criteria or thresholds>
output_format: <structure of the deliverables>
```

The skill scores against 5 signals and returns a `decision`:
- `skill_recommend` (3 points or more)
- `candidate_queue` (2 points)
- `curated_only` (1 point or fewer)

For `skill_recommend`, appending to `knowledge/skill-candidates.md` is also handled by the skill.

### Step 4.2: Branch by decision

#### decision == skill_recommend

1. Propose to the human:
   ```
   [work-skill proposal] The work pattern of this task looks reusable as a work-skill.
   - Proposed skill name: {proposed_skill_name}
   - Reason: {matched_signals} (total {score}/5)
   - Summary: {what is reusable}

   Shall I record it?
   ```
2. If the human approves:
   - Create `.claude/skills/{skill-name}/SKILL.md`
   - Template: follow the format of `.claude/skills/org-retro/references/work-skill-template.md`
   - Extract and generalize the procedure from the Worker's deliverables (code, reports, configs, etc.)
   - Replace task-specific values (brand names, file paths, etc.) with placeholders
   - Update the corresponding entry in `knowledge/skill-candidates.md`: status to `approved` and fill in the decision date
3. If the human rejects:
   - Record the reason in `knowledge/raw/` to inform future judgments
   - Update the corresponding entry in `knowledge/skill-candidates.md`: status to `rejected` and append the rejection reason

#### decision == candidate_queue

Stop at candidate. If the same pattern reappears in raw next time, the raw_reappearance signal will fire,
so do not create a skill at this stage. Recording technical knowledge to `knowledge/raw/` proceeds as usual (skip if the Worker has already recorded it).

#### decision == curated_only

Recording technical knowledge to `knowledge/raw/` is sufficient (skip if the Worker has already recorded it).
No report needed.

## Step 5: Report

Briefly report to the human:
- If you recorded knowledge: "I recorded a learning about {topic} for the delegation process."
- If proposing a work-skill: propose using the `skill_recommend` format from Step 4.2
- For `candidate_queue` / `curated_only`: no report needed (silently move on)
