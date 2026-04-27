# Glossary

Canonical term mapping between `claude-org-ja` (Japanese source of truth)
and `claude-org` (English source of truth).

This glossary is **locked** by user (Lead) approval as part of Issue #158.
No translation PR may use a different rendering of these terms.

| ja | en | gloss |
|---|---|---|
| 窓口 | Lead | The single human-facing role; routes work, makes judgments, never edits code directly. |
| フォアマン | Dispatcher | Spawns and coordinates worker panes; honors `bypassPermissions` for child-agent spawning (decision H-1). |
| キュレーター | Curator | Periodically organizes raw learnings into curated knowledge. |
| ワーカー | Worker | Short-lived, scoped Claude instance that performs the actual editing/build/test work. |
| 派遣 | dispatch | The act of spawning a worker for a task. |
| 並列ペーン | parallel pane | A renga pane running concurrent work. |
| 知見整理 | knowledge curation | Promoting raw notes to curated, reusable knowledge. |
| 中断 / 再開 | suspend / resume | Saving / restoring full org state to disk. |
| 引き継ぎメモ | handoff note | Per-task memo passed between sessions. |

## Notes

- Additional terms encountered during translation should be added by the corresponding Wave B PR with a one-line rationale.
- Casing: roles are TitleCase (Lead, Dispatcher, ...) when used as proper nouns; the verbs (`dispatch`, `suspend`, `resume`) stay lowercase.
- This file is the source of truth for terminology; if a translation PR conflicts with the glossary, the PR must change.
