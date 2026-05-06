---
name: "{skill-name}"
description: >
  {One-line summary. What does this skill do, what tasks can it be used for?
  org-delegate references this description when matching the skill against task content.}
type: "{implementation | testing | debugging | analysis | infrastructure}"
triggers:
  - "{Situation 1 in which this skill applies (e.g., analyze Excel-format survey data)}"
  - "{Situation 2 in which this skill applies}"
origin:
  task_id: "{The task ID where this pattern was first used (e.g., data-analysis)}"
  date: "{YYYY-MM-DD}"
---

# {skill-name}: {Skill title}

{Summary of what this skill achieves, in 1–2 sentences.}

## Background

{The story of how this pattern emerged. What task was it first used for?
Why was this approach effective?}

## Prerequisites

{List the conditions required to apply this skill.}

- {Prerequisite 1 (e.g., Python 3.8+ installed)}
- {Prerequisite 2 (e.g., input data is in a specific format)}

## Procedure

### Step 1: {First step name}

{Describe the concrete steps. Include command examples or code snippets where helpful.}

```{language}
{Code example}
```

### Step 2: {Next step name}

{Describe the steps. If there are decision criteria, make them explicit.}

### Step 3: {Next step name}

{Describe the steps.}

## Artifacts

{What does running this skill produce?}

- {Artifact 1 (e.g., `report.md` — analysis report)}
- {Artifact 2 (e.g., `analyze.py` — analysis script)}

## Decision criteria / thresholds

{If there are decision criteria or thresholds used inside the skill, document them.
Include concrete numbers for quantitative criteria.}

| Criterion | Value | Rationale |
|---|---|---|
| {Criterion name} | {Value} | {Why this value} |

## Variations

{Guidance for adapting this skill to a different context.}

- **{Variation 1}**: {how to adapt}
- **{Variation 2}**: {how to adapt}

## Caveats

{Caveats and common pitfalls when using this skill.}

- {Caveat 1}
- {Caveat 2}
