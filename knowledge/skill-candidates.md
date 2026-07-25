# skill 化候補キュー

`skill-eligibility-check` が `skill_recommend` と判定した候補を蓄積する。
窓口は pending エントリが **5 件（N=5）** 以上になった時点で、人間にバッチで問い合わせる。

都度問い合わせよりバッチの方が意思決定コストが低い（Issue #68 方針）。

> **This file is the format definition only — its entry list is always empty (Issue #755).** Real
> entries are operator-private working knowledge and must not land in the OSS repository. They are
> appended to the machine-local **`knowledge/skill-candidates.local.md`** (already gitignored).
> This public file holds the **definitions** — entry format, status vocabulary, and operating rules —
> and the entry-list section at the foot of this file is kept empty. (That heading is referenced here
> by description rather than spelled out, because a live-file test splits this file on that exact
> literal; a second occurrence above the entry-format template would silently shrink what the test
> checks.) `skill-eligibility-check` Step 4's append target, and the edit target for status
> transitions, are both the `.local.md` side.
> The threshold count (`tools/check_curate_threshold.py` / `skill-audit`) reads **both files summed**
> (the two files and their order are defined by `CANDIDATE_ENTRY_PATHS` in `check_curate_threshold.py`,
> which is the source of truth).

## エントリフォーマット

各候補は 3 レベル見出し `### {YYYY-MM-DD} {pattern-name}` で始まるブロックとする。

```markdown
### {YYYY-MM-DD} {pattern-name}
- **判定スコア**: {score}/5
- **該当シグナル**: {matched_signals の配列を "[a, b, c]" 形式}
- **根拠**: {1-2 行}
- **関連タスク**: {task_ids、curation 文脈では空 "[]" 可}
- **関連 raw ファイル**: {raw_files のパス列}
- **呼び出し元**: {post_retro | curation}
- **提案 skill 名**: {kebab-case 名}
- **status**: {pending | deferred | approved | rejected | merged-into-*}
- **決定日**: 未定
- **却下理由**: （status が `rejected` に遷移したとき記入、それ以外は省略）
- **統合先**: （status が `merged-into-*` のとき記入、それ以外は省略）
```

## Status transitions

- `pending`: not yet put to the human. Counted by `skill-audit`'s N=5 trigger condition.
- `deferred`: **presented to the human, and the human decided to shelve it for now.** Not terminal (neither approved nor rejected), but it is **excluded from the threshold count** and **is never re-asked**. Because the line does not match the `- **status**: pending` line form, it is automatically excluded from the pending count in `tools/check_curate_threshold.py`'s `count_pending` and in `skill-audit` Step 1. This is the countermeasure for shelved candidates re-firing the threshold on every worker close and needlessly spawning the curator (Issue #753).
- `approved`: the human approved promotion to a skill. Create the corresponding `.claude/skills/{name}/SKILL.md`.
- `rejected`: the human rejected it. Record why in the rejection-reason field.
- `merged-into-{existing-skill}`: merged into an existing skill. Do not create a new one.

**`deferred` is never returned to `pending`** (it is out of scope for re-asking). Shelving is decided once, so the same candidate is not dredged up again. If the human later does want to promote it after all, do **not** rewrite the `deferred` entry — raise a **separate entry under a new date** (the same history-preserving practice as `approved` / `rejected`).

Entries at `deferred` and beyond are **kept, not deleted**, as history.
They are useful reference when the same `pattern_name` comes up again.

## 運用メモ

- `skill-eligibility-check` は判定時にこのファイルを自動追記する（同スキル Step 4）
- 同 `pattern_name` で既に `pending` エントリがある場合は新規追加せずマージ（関連タスク・raw ファイルの追記のみ）
- If a `deferred` entry already exists for the same `pattern_name`, **do not add it again** (do not return `deferred` to `pending`, and do not raise a fresh `pending` either). The principle is that shelved candidates are not dredged up. Only when the human explicitly wants to reconsider should a separate entry be raised under a new date.
- 既に `approved` / `rejected` / `merged-into-*` のエントリがある場合は、新しい日付で別エントリを作る（過去の決定を履歴として残すため）

## エントリ一覧

<!-- 以下にエントリが自動追記される -->
