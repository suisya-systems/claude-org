# Pre-fetch for release-class tasks (executed by the Lead)

> **Primary reference source**: [`.claude/skills/org-delegate/SKILL.md`](../SKILL.md) Step 0.6 (trigger determination only). This document is the detailed SoT for trigger conditions, execution commands, and background history.

Tasks that cut a `release/*` branch assume the worker branches from **the target project's latest `main`**. Since Phase 2 worker git guardrails, the worker-side `.claude/settings.json` `permissions.deny` includes `Bash(git fetch)` / `Bash(git pull)` / `Bash(git remote update)`. If you dispatch a worker while local `origin/main` is stale, a "git fetch deny" BLOCKER fires within 5 minutes of work, costing over 10 minutes of Lead round-trip (claude-org-runtime v0.1.10 case).

For this reason, **only for release-class tasks**, the Lead performs the fetch on its side before `gen_delegate_payload.py preview` / `apply`:

```bash
# Local root of the target project (the repository where the release is cut)
cd <target project root>

# Pull in the latest origin/main and fast-forward local main
git fetch origin
git pull --ff-only origin main
```

## Trigger conditions

Fire only when one of the following applies:

- The task description / commit-prefix / planned branch contains words signaling a release promotion such as `release`, `release/`, `vX.Y.Z`
- The target files include release-promotion work such as promoting `CHANGELOG.md`, bumping `__about__.__version__` / `pyproject.toml`'s `version`
- The task_id contains `release` (e.g., `runtime-0-1-10-release`)

Do not execute for ordinary feature / fix / docs tasks. The worker permissions deny is an intentional design that "the worker does not pull in mainline history and self-contains within its sandbox"; only release is the exception flow that requires "branching from the latest main".

## Background

For the detailed history (measured 5-minute-in BLOCKER → 10-minute additional loss for workers, comparison of 4 response options, permissions-side root cause), refer to the "When creating a release branch, the Lead performs `git fetch` on its side" section of [`knowledge/curated/release-process.md`](../../../../knowledge/curated/release-process.md).
