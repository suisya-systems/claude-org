> **This document is historical reference material.** Do not consult it for standard Secretary / Worker / Dispatcher operations. Because this procedure itself depends on the runtime CLI, including `claude-org-runtime settings generate`, it also does not function as a fallback when the runtime CLI is down. If the standard path (`tools/gen_delegate_payload.py apply`) returns unexpected output, do not reproduce it manually; file an Issue and pause the affected delegation until the bug on the resolver / runtime side is fixed. Whether to do any manual work exceptionally is left to the user's explicit judgment; if Secretary reaches this document on its own, that is a protocol violation.

# Legacy hand-typed delegation path (museum copy)

This file preserves the pre-Issue-283 manual delegation procedure for archaeological reference. It was extracted from `.claude/skills/org-delegate/references/delegate-flow-details.md` § "Legacy hand-typed paths" and the `### legacy / fallback path` subsection of `.claude/skills/org-delegate/SKILL.md` (Issue #313).

## Why this is no longer in the active skill

Documenting a hand-typed fallback inside the active skill behaved like an "easy button": when `gen_delegate_payload.py apply` produced an unexpected layout, Secretary defaulted to switching paths instead of treating the resolver output as a regression. Concrete failures historically caused by reaching for the legacy path include:

- **Settings env mismatch** — copying `.claude/settings.local.json` from a sibling worktree without updating `WORKER_DIR`, blocking the new worker on its first Edit/Write via the boundary hook (session #13).
- **drift_check breakage** — manually editing `.state/org-state.md` sections that are DB-owned (`Worker Directory Registry` / `Active Work Items`), causing the next snapshotter run to overwrite the changes and triggering drift_check failures.
- **T1 reservation skipped** — manual `DELEGATE` skips `runs.status='queued'`, so the Dispatcher watch loop loses queue visibility and two delegations on the same project both choose Pattern A and collide on the base clone.
- **Pattern misclassification carry-over** — when the resolver itself was wrong (for example, a Pattern A misjudgment for a self-edit task because the Worker Directory Registry was stale), reaching for the manual path masked the underlying resolver bug instead of filing it.

Today, if `gen_delegate_payload.py apply` errors or produces a wrong layout, the canonical response is to **file an Issue against `gen_delegate_payload.py` (or its resolver) and pause the affected delegation until the underlying bug is fixed**. Whether to invoke any manual workaround at all is a user judgment call; Secretary must not self-grant the exception. Note that the procedure below also depends on `claude-org-runtime` and is therefore not a general fallback when the runtime CLI itself is unavailable; in that case, restoring the runtime CLI is the prerequisite.

## Legacy procedure (verbatim, do not use)

Two pre-Issue-283 paths used to be supported for callers that already worked in that idiom:

- `python tools/gen_worker_brief.py --config <path>.toml --out <CLAUDE.md>` — the original brief renderer. Still works exactly as before. New code should prefer the `from-task` subcommand because it derives `worker.dir` / `worker.pattern` / `worker.role` deterministically from registry and state.db rather than asking the operator to fill them in.
- Manually issuing the `DELEGATE:` message via `mcp__renga-peers__send_message` — fine in the past for one-off ad-hoc dispatches. The `gen_delegate_payload preview` command can still be used to draft the body without writing anything.

Operationally that meant:

- Manually generate the brief with `python tools/gen_worker_brief.py --config <task>.toml --out <CLAUDE.md>`
- Call `claude-org-runtime settings generate` directly, **after fixing `--role` to Lead**
- Hand-write the DELEGATE body following the template below, then send it with `mcp__renga-peers__send_message(to_id="dispatcher", message=…)` (to preserve this museum copy for archaeology, it is kept inline in this document instead of referring to §3 of the active doc. For the latest standard-path spec, see `.claude/skills/org-delegate/references/delegate-flow-details.md` §3):

  ```
  DELEGATE: 以下のワーカーを派遣してください。
  タスク一覧:
  - {task_id}: {description}
    - ワーカーディレクトリ: {worker_dir}
    - ディレクトリパターン: {A|B|C}    # Pattern C のサブモードは variant ラベル
    - プロジェクト: {clone source / reuse / worktree base}
    - ブランチ (planned): {branch}    # Pattern C は null
    - Permission Mode: {mode}        # registry/org-config.md から
    - 検証深度: {full|minimal}
    - 指示内容: CLAUDE.md / CLAUDE.local.md 参照。{1 行サマリ}
  窓口ペイン名: secretary
  ```

  Every line is required. The snapshot test for `tools/gen_delegate_payload.py` (`tests/fixtures/delegate_payload/`) locks this exact format to prevent failures such as the historical "missing verification_depth row".

Both paths skip the T1 reservation and therefore do not surface the queued state to the Dispatcher's watch loop.
---
