# probes/

Storage for the probe checklist of the Issue #376 Pre-Phase 0 spike (probe-worker pattern, Issue #376 issuecomment-4410401705).

## File layout

- `checklist.md` — the probe's 5-column checklist (category / attempted command / expected allow or deny / observation / conclusion). The plan for this iteration.
- `categories.md` — background notes on what each category checks and why. Records the correspondence to audit-issue-376-2026-05-09.md (B0/B1/B2/B3) and to Issues #376/#377/#378/#379/#380.

## Operational rules for the probe-worker pattern (agreed at this spike's point in time)

1. **Probes are limited to read-only verification plus known-safe writes**. Destructive real-environment actions go through manual review by the secretary/dispatcher.
2. **Fill in the "expected allow or deny" column before running**. Dig into the "conclusion" column only when the actual observation deviates from the expectation.
3. Probes can expand on three axes: **role × pattern × profile**. Don't expand too many axes in one iteration; keep verification depth at minimal.
4. Results are appended separately in the form `probes/runs/{YYYY-MM-DD}-{topic}.md` (not created in this iteration; assumed to be created at the start of the next iteration).
5. Real-machine execution is **outside this spike's scope**. This iteration stops at fixing the "expected values" and "observation points".

## Priority probe set for this iteration

`checklist.md` has the category column filled in the following order. The B1-1/B2-1 audit findings are consumed first, with the surrounding dangerous-git surface / network egress / secret denyRead each making one pass:

1. B1-1 — dispatcher `bypassPermissions` × sandbox profile firing
2. B2-1 — repo-shared `.claude/settings.json` deployment status to worker
3. fs-cwd — read/write inside/outside worker cwd
4. fs-pattern-b — base repo Git metadata operations assumed under Pattern B
5. git-surface — history-rewriting push / hard reset / forced worktree removal
6. network — network egress (curl, gh, cargo fetch)
7. secrets — `.env` / credential / `*.pem` / `~/.config/gh/hosts.yml` denyRead

## Terminology

- **allow** = no defense layer (perms / hook / sandbox / claude-builtin) refuses; the Tool succeeds with side effects.
- **deny** = some defense layer refuses, and an error is returned as the Tool result in Claude Code.
- **silent** = no error is raised but the side effect is suppressed (e.g. sandbox is fail-open, hook exits 0).
- **observed** column = write "untested" in this iteration. Fill in once the real-machine probe iteration runs.
