---
name: org-retro
description: >
  Retrospective on the delegation process. When a worker delegation
  finishes, look back at how the delegation itself went and record
  process-improvement learnings. Also decide whether the completed
  task's pattern should be promoted to a work-skill.
  Technical retrospectives on the actual work are done by the worker
  automatically and are not handled here.
---

# org-retro: delegation-process retrospective

After a delegation to a worker finishes, look back at the delegation process itself and improve it.
Also decide whether the completed task's working pattern is reusable as a work-skill.

**Note**: technical learnings about the actual work (gotchas, API quirks, etc.) are recorded automatically by the worker into `knowledge/raw/` per CLAUDE.md instructions. They are not handled here.

## Step 1: retrospective on the delegation process

Sort out the following:
- **Was the task split right?** Was the granularity too coarse / too fine?
- **Were the instructions clear?** Did the worker proceed without confusion? Were there many questions?
- **Was the project chosen correctly?** Did the worker work in the right directory?
- **Was the parallelism right?** Were there too many / too few workers?
- **Was the completion report sufficient?** Did it give enough material to brief the human?

## Step 2: decide what learnings to keep

Use these criteria to decide whether to record:

**Record if**:
- A pattern likely to recur in delegations of the same kind.
- An insight that improves the instruction template.
- A project-specific constraint that will likely affect the next delegation.
- A point where the worker's retrospective recording was insufficient or excessive — an improvement angle.

**Do not record if**:
- A one-off problem specific to this task.
- Already recorded by the worker as a technical learning.

## Step 3: record

If there is a learning, create a file at:

- Path: `knowledge/raw/{YYYY-MM-DD}-delegation-{topic}.md`
- `{topic}` is English kebab-case (e.g., `delegation-task-granularity`, `delegation-frontend-instructions`).
- Prefix with `delegation-` to distinguish from the worker's technical learnings.

### File format

See "Recording format" in `.claude/skills/org-curate/references/knowledge-standards.md`.

## Step 4: work-skill promotion judgment

Call `skill-eligibility-check` against the completed task's working pattern to decide whether to promote it to a work-skill.

The decision criteria themselves live in `.claude/skills/skill-eligibility-check/references/signals.md` and are referenced by both org-retro and org-curate (so the criteria do not drift).

### Step 4.1: call skill-eligibility-check

Construct and pass the following input:

```yaml
context: post_retro
pattern_name: <inferred skill name, kebab-case>
summary: <1–2 sentences on what is reusable>
task_ids: [<this task_id>]
raw_files: <array of paths under knowledge/raw/ that the worker recorded>
steps_outline:
  - <main step 1>
  - <main step 2>
  - ...
trigger_description: <situation in which this pattern applies>
decision_criteria: <decision criteria or thresholds>
output_format: <artifact structure>
```

The skill scores 5 signals and returns `decision`:
- `skill_recommend` (≥ 3 points)
- `candidate_queue` (2 points)
- `curated_only` (≤ 1 point)

For `skill_recommend`, the skill itself appends to `knowledge/skill-candidates.md`.

### Step 4.2: branch on decision

#### decision == skill_recommend

1. Propose to the human:
   ```
   [work-skill proposal] This task's working pattern looks reusable as a work-skill.
   - Proposed skill name: {proposed_skill_name}
   - Reason: {matched_signals} (total {score}/5)
   - Summary: {what is reusable}

   Record it?
   ```
2. If the human approves:
   - **The Lead does NOT directly create / edit the skill file.** Per the ratification of Set E §2.4 (Q7), skill-promotion goes through `org-delegate` as a delegated task to a worker.
   - The Lead launches `org-delegate` and produces a worker task with role `claude-org-self-edit`. The instructions must include:
     - The target skill name `{skill-name}` and write target `.claude/skills/{skill-name}/SKILL.md`.
     - Template reference: `.claude/skills/org-retro/references/work-skill-template.md`.
     - The source (worker artifacts / raw learning files) and the policy of substituting task-specific values for placeholders.
     - That this is a skill-promotion delegation (one of the carve-outs of the Set A worker write-surface).
   - The Dispatcher / Lead does **not** write directly to `.claude/skills/{skill-name}/` or `knowledge/skill-candidates.md`. Per Set E §1.4 / §2.4, the status transition in `skill-candidates.md` (move to `approved`, fill `decision date`) is also the same delegated worker's responsibility; include it in the instructions.
3. If the human rejects:
   - Record the reason in `knowledge/raw/` for future use in similar judgments.
   - Updating the `knowledge/skill-candidates.md` entry (status → `rejected`, append the rejection reason) also goes through worker delegation (`org-delegate`); the Lead / Dispatcher does not edit it directly (per Set E §1.4 owner definition).
4. If the human picks "merge into an existing skill" (terminal status `merged-into-{existing-skill}`):
   - Identify the merge target and delegate to a skill-promotion worker via `org-delegate`: edit `.claude/skills/{existing-skill}/SKILL.md` to incorporate, and update the `knowledge/skill-candidates.md` entry's status to `merged-into-{existing-skill}` (fill the `merge target` field with the existing skill name).
   - Do not create a new skill file. The Lead / Dispatcher does not edit directly.

#### decision == candidate_queue

Stays a candidate. The next time the same pattern reappears in raw, the raw_reappearance signal will fire, so do not promote yet. Recording the technical learning in `knowledge/raw/` proceeds normally (skip if the worker already recorded it).

#### decision == curated_only

Recording the technical learning in `knowledge/raw/` is enough (skip if the worker already recorded it).
No report required.

## Step 5: report

Briefly report to the human:
- If a learning was recorded: "Recorded a learning about the delegation process — {topic}".
- If proposing a work-skill: present the `skill_recommend` format from Step 4.2.
- For `candidate_queue` / `curated_only`: no report (move on silently).
