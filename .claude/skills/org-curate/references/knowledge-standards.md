# Knowledge management standards

Shared standards for recording and curating knowledge, referenced by both org-curate and org-retro.

## Recording format

```markdown
# {Title}

## Facts
{What happened — describe observed facts objectively.}

## Decision
{What decision was made, what was chosen.}

## Rationale
{Why that decision was reached. Technical reasons, tradeoffs, constraints, etc.}

## When it applies
{Concrete situations where this knowledge is useful. When / under what circumstances should it be referenced?}
```

**Recording bar**: reproducible / non-obvious / not knowable from reading the code alone. General programming knowledge or things in official documentation do not need to be recorded.

## Standards for consolidation (curation)

### Merge when
- Multiple knowledge entries cover the same technology or service.
- One is the detailed version of another.
- They describe different facets of the same problem.

### Do not merge when
- The themes are close but the application contexts differ.
- They contradict each other (keep both and explicitly note the contradiction).

## Standards for proposing improvements

### Propose when
- At least three entries of the same kind have accumulated (a pattern is forming).
- An existing skill's procedure has an obvious gap.
- A clear preventive measure for a recurring problem has been identified.

### Do not propose when
- Generalizing from a single entry is premature.
- The improvement effect is small (a minor procedural tweak).
- It is already documented in the skill but the worker simply skipped over it.

## Delegation of skill-promotion judgment

The decision about whether a new skill is needed is centralized in `.claude/skills/skill-eligibility-check/SKILL.md`.
This file remains a reference source for knowledge-consolidation standards and does not duplicate the skill-promotion criteria.
Both org-retro and org-curate call `skill-eligibility-check` and score against the same criteria.

## Quality bar for curated files

- Each entry should be readable in isolation (understandable without surrounding context).
- The application context should be clear (you can tell when to use it).
- The rationale should be recorded (why the decision was made).
- Stale entries should be removed or annotated.
