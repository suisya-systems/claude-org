# Knowledge management standards

Standards for recording and curating knowledge, referenced by both org-curate and org-retro.

## Recording format

```markdown
# {title}

## Facts
{Objective description of what happened or was observed.}

## Decision
{What decision was made or what was chosen.}

## Rationale
{Why that decision was reached. Technical reasons, trade-offs, constraints, etc.}

## When to apply
{The concrete situations where this knowledge is useful. "When" and "in what circumstances" should it be referenced.}
```

**Recording criteria**: reproducible / non-obvious / not derivable from reading the code alone. General programming knowledge or things written in the official documentation do not need to be recorded.

## Curation (consolidation) criteria

### When to merge
- Multiple pieces of knowledge concern the same technology or service
- One is a more detailed version of the other
- They describe different aspects of the same problem

### When NOT to merge
- The themes are similar but the application contexts differ
- One contradicts the other (keep both and clearly note the contradiction)

## Improvement proposal criteria

### When to propose
- 3 or more pieces of knowledge of the same kind have accumulated (a pattern is forming)
- There is a clear gap in an existing skill's procedure
- A clear preventive measure has emerged for a recurring problem

### When NOT to propose
- Generalizing from a single piece of knowledge is premature
- The improvement effect is small (just minor procedural tweaks)
- It is already documented in a skill but the Worker just skipped over it

## Delegation target for skill-eligibility judgment

Judgment of whether a new skill is needed is centralized in `.claude/skills/skill-eligibility-check/SKILL.md`.
This file remains a reference for knowledge consolidation criteria only, and does not duplicate skill-eligibility criteria.
Both org-retro and org-curate call `skill-eligibility-check` and score against the same criteria.

## Quality standards for curated files

- Each piece of knowledge can be read independently (understandable without surrounding context).
- The when-to-apply is clear ("when to use it" is evident).
- The rationale is recorded (why that decision was made).
- Outdated knowledge is removed, or annotated.
