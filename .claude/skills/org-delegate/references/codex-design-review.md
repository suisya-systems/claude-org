# Codex design review trigger (executed by the Lead, Issue #337)

> **Primary reference source**: [`.claude/skills/org-delegate/SKILL.md`](../SKILL.md) Step 1.7 (trigger determination overview only). This document is the detailed SoT for the trigger table, the execution command, and the procedure for incorporating the review summary.

Looking at the `preview` output's `description` / `--target` count / referenced documents, if **at least one** of the following applies, run a Codex design review before `apply`. This gate is based on the track record from the Curator session #18 retrospective (Issue #283 / session #12) where "a pre-Codex design review caught 2 Blockers + 5 Majors in one round".

## Trigger conditions

| Trigger | Determination method |
|---|---|
| Estimated effort ≥ 3h | Lead judges from the task description (user input / scale sense of preview) |
| Introduction of a new module / new tool | Description contains "新規" / "new tool" / "新ツール" / "新規導入" etc., or the files to be created in the preview are all on new paths |
| File changes ≥ 3 | Count of `--target` + edit targets listed in the preview brief |
| Reference to contract documents under `docs/contracts/` | Description / brief / `--knowledge` references `docs/contracts/` |

## Execution procedure

```bash
codex exec --skip-git-repo-check "Design review for <task-id>.\
  Task description: <description>.\
  Target files: <target paths>.\
  Related contracts / references: <docs paths>.\
  Classify pre-design findings as Blocker / Major / Minor / Nit. For each finding, cite the target file:line and the rationale. Be concise."
```

Do not use the `codex:rescue` skill (prohibited per CLAUDE.local.md). Only direct `codex exec` invocation.

## Incorporating the review summary

- Save the summary to `tmp/codex-review-{task-id}.md`
- When calling `apply`, pass **`--impl-guidance "<summary body>"`**. This expands the summary body into the brief's `[implementation].guidance` so the Worker can read it directly
- As a supplement, adding `--knowledge tmp/codex-review-{task-id}.md` lists the path under the brief's `[references].knowledge`, letting the Worker refer to the full text as needed (`gen_worker_brief.py` only lists the path, it does not embed the body). The responsibility for reliably delivering the body to the Worker lies on the `--impl-guidance` side
- If a Blocker / Major is flagged, escalate to the user to confirm direction-change possibility before proceeding to apply

## Helper script

Optional per the Issue #337 acceptance, not implemented in this PR. The Secretary judges the above table manually.
