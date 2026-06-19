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
| Delegation that adds a blocking wait / lifecycle change to a monitoring role | The description / brief adds a blocking wait (waiting on completion / synchronous join) to a monitoring role (`/loop`-resident, periodically-polling roles such as dispatcher / curator), or changes the org's lifecycle (spawn / close / cadence / resident ⇄ on-demand switch). **Fires even if only 1 file changes** (independent of the file-count condition) |

## Execution procedure

Because a design review runs **before implementation, when no diff exists**, the diff self-review `codex exec review` (review surface) does not apply. Use the **`codex exec` prompt form** that takes the design content, target files, and contract references. The method benchmark ([`knowledge/curated/codex.md`](../../../../knowledge/curated/codex.md)) measures that the heavy multi-perspective `exec` prompt has superior breadth for catching subtle / design-level Blockers; design review is exactly that breadth-required use case, so the `exec` prompt form is appropriate here (a separate judgement from the diff self-review's switch to the review surface).

```bash
codex exec --skip-git-repo-check -m gpt-5.5 -c model_reasoning_effort=medium \
  "Design review for <task-id>.\
  Task description: <description>.\
  Target files: <target paths>.\
  Related contracts / references: <docs paths>.\
  Classify pre-design findings as Blocker / Major / Minor / Nit. For each finding, cite the target file:line and the rationale. Be concise."
```

Do not use the `codex:rescue` skill (prohibited per CLAUDE.local.md). Only direct `codex exec` invocation. The `gpt-5.5-codex` model / API-key surface cannot run on a ChatGPT account, so explicitly pass `-m gpt-5.5`. For hang guards (stdin `< /dev/null`, per-round logs, 5-10 min kill on 0 bytes), see [`knowledge/curated/codex.md`](../../../../knowledge/curated/codex.md).

### 3 additional questions for monitoring-role wait-design changes

When the trigger "Delegation that adds a blocking wait / lifecycle change to a monitoring role" applies, always append the following 3 questions to the prompt above and require the review to answer them:

1. **Who blocks** — which role's which loop / cycle stops
2. **What is the upper bound, in minutes** — the timeout value of the wait, and which side (the spawn caller / the loop) manages it
3. **What becomes undetectable in the meantime** — events missed because polling stops (worker completion reports, escalations, SECRETARY_RELAY_GAP detection, etc.)

For the mandatory brief wording (no blocking wait, immediate return after spawn, completion detection on the loop's regular cycle, timeout managed on the loop side), see the "Mandatory brief wording for delegations involving monitoring-role wait design" section of [`.claude/skills/org-delegate/references/instruction-template.md`](instruction-template.md).

## Incorporating the review summary

- Save the summary to `tmp/codex-review-{task-id}.md`
- When calling `apply`, pass **`--impl-guidance "<summary body>"`**. This expands the summary body into the brief's `[implementation].guidance` so the Worker can read it directly
- As a supplement, adding `--knowledge tmp/codex-review-{task-id}.md` lists the path under the brief's `[references].knowledge`, letting the Worker refer to the full text as needed (`gen_worker_brief.py` only lists the path, it does not embed the body). The responsibility for reliably delivering the body to the Worker lies on the `--impl-guidance` side
- If a Blocker / Major is flagged, escalate to the user to confirm direction-change possibility before proceeding to apply

## Helper script

Optional per the Issue #337 acceptance, not implemented in this PR. The Secretary judges the above table manually.
