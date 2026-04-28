# Organization Config

## Permission Mode
default_permission_mode: auto

選択肢:
- bypassPermissions: 全許可、確認なし（デフォルト）
- auto: 分類器による安全チェック付き（Team/Enterprise/API プランのみ）
- default: 都度確認
- acceptEdits: ファイル編集のみ自動許可
- dontAsk: 明示許可のみ

### Per-role applicability

`default_permission_mode` applies to the Curator and Workers. Other roles are handled as follows:

- **Secretary**: out of scope. Keeps the Claude Code default behavior (confirmation prompts on tool execution) with no `--permission-mode` specified. The Secretary is the human-facing window, so we avoid auto-approving operations that require human judgment. See Issue #10 for details.
- **Dispatcher**: regardless of the `default_permission_mode` value, fixed at `bypassPermissions`. For the rationale, see the "Dispatcher" section of `.claude/skills/org-start/SKILL.md`.

## Workers Directory
workers_dir: ../workers

ワーカー専用ディレクトリの配置先。claude-org リポジトリからの相対パス。
リポジトリ外に配置することで、ワーカーの新規プロジェクト作成時に親リポジトリの git コンテキストが干渉しない。
