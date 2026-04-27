---
name: "{skill-name}"
description: >
  {One-line description. What this skill does, and on what kind of tasks it can be used.
  org-delegate references this description when matching a task.}
type: "{implementation | testing | debugging | analysis | infrastructure}"
triggers:
  - "{Situation 1 where this skill applies (e.g. analyze Excel-format survey data)}"
  - "{Situation 2 where this skill applies}"
origin:
  task_id: "{Task ID where this pattern was first used (e.g. data-analysis)}"
  date: "{YYYY-MM-DD}"
---

# {skill-name}: {Skill title}

{1-2 sentences describing what this skill achieves.}

## Background

{The context in which this pattern emerged. What kind of task it was first used on.
Why this approach was effective.}

## Prerequisites

{List the conditions required to apply this skill.}

- {Prerequisite 1 (e.g. Python 3.8+ is installed)}
- {Prerequisite 2 (e.g. the input data is in a specific format)}

## Procedure

### Step 1: {First step name}

{Concrete procedure. Include command examples or code snippets if relevant.}

```{language}
{code example}
```

### Step 2: {Next step name}

{Procedure description. Make decision criteria explicit if any.}

### Step 3: {Next step name}

{Procedure description.}

## Deliverables

{What is produced as a result of running this skill.}

- {Deliverable 1 (e.g. `report.md` — analysis report)}
- {Deliverable 2 (e.g. `analyze.py` — analysis script)}

## Decision criteria / thresholds

{Document any decision criteria or thresholds used inside the skill.
For quantitative criteria, include concrete numbers.}

| Criterion | Value | Rationale |
|---|---|---|
| {criterion name} | {value} | {why this value} |

## Variations / applications

{Guidance for applying this skill in a different context.}

- **{Variation 1}**: {how to change}
- **{Variation 2}**: {how to change}

## Caveats

{Caveats and common pitfalls when using this skill.}

- {Caveat 1}
- {Caveat 2}
