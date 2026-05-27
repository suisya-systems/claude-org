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

## Relation to Issue #480 (Pattern B does not overlap because apply auto-fetches)

Since Issue #480, **new worktree creation** for **Pattern B** (the case where a concurrent run occupies the base clone, so a worktree is cut) has `gen_delegate_payload.py apply` (internally `_ensure_worktree`) **automatically run `git fetch origin` immediately before `git worktree add` and branch off the latest `origin/HEAD` (= `origin/main`)**. This fetch is **fail-closed**: if an `origin` remote is configured and the fetch fails, apply aborts with `WorktreeApplyError` (it never cuts a worktree off a stale `origin/main`, and because it aborts before the DB reservation, no queued row is left behind).

Scope and exceptions (worded exactly as implemented):

- **On new creation** with an `origin` remote configured, the worktree's starting point becomes the latest trunk (guaranteed fail-closed).
- A local-only base with no `origin` remote skips the fetch (there is no remote to pull in).
- The **reuse path for an already-registered worktree** (Issue #309 partial-retry) does not fetch. An already-committed branch tip cannot be advanced by a fetch, and a reset could destroy the worker's work. To refresh a stale reused worktree, the Lead deletes that worktree and lets apply recreate it (recreation goes through the fetch as above).

Therefore, **even without running the Step 0.6 pre-fetch, the worktree's starting point on the new-creation path is the latest trunk**, which overlaps with Step 0.6's purpose of "branching from the latest main" (running both does no harm: the fetch is merely idempotent).

Step 0.6 nonetheless remains required, because its target is **Pattern A** (the case with no concurrent run, where the worker cuts `release/*` directly from local main in the base clone itself):

- A Pattern A worker branches from the **local `main`** inside the base clone. Because the worker-side permissions deny `git fetch` / `git pull`, a stale local main turns into a BLOCKER right after the worker starts. apply's auto-fetch only updates Pattern B's worktree starting point (the `origin/main` remote-tracking ref); it does not fast-forward the **local main branch itself** that Pattern A uses.
- So the Lead-side pre-fetch that "fast-forwards local main to the latest" (`git pull --ff-only origin main`) is still needed for Pattern A release tasks.

In summary: **the freshness of the worktree starting point is guaranteed by Issue #480 inside apply (Pattern B); the freshness of local main is guaranteed by Step 0.6 on the Lead side (Pattern A release).** The two address different targets, and neither makes the other unnecessary.

## Background

For the detailed history (measured 5-minute-in BLOCKER → 10-minute additional loss for workers, comparison of 4 response options, permissions-side root cause), refer to the "When creating a release branch, the Lead performs `git fetch` on its side" section of [`knowledge/curated/release-process.md`](../../../../knowledge/curated/release-process.md).
