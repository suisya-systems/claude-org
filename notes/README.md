---
# notes/

This directory is the **free-form writing area for claude-org**.
Structured organizational state (`Status` / `Active Work Items` / `Worker Directory Registry`, etc.)
uses `.state/state.db` as the SoT, and `.state/org-state.md` is a DB-derived dump of it
(do not edit manually). **Write all free-form content here in `notes/`**.

## Background

With the markdown freeze in Issue #267 / M4, `.state/org-state.md` was downgraded to a
generator-only dump. `tools/state_db/snapshotter.py` regenerates markdown from the DB,
and `tools/state_db/drift_check.py` verifies that the DB and markdown match. Because
drift_check operates on the **entire file**, any free-form section written directly into
`org-state.md` is detected immediately in CI.

Move the following kinds of free-form content, which were previously written in
`org-state.md`, into `notes/`:

- Session summaries (`## 2026-05-04 Session #11 Key Outcomes`, etc.)
- Learnings and retrospectives (`## Learnings from This Session`)
- Pending Lead actions (`## Pending Lead`)
- Ad hoc notes and operational notes

## Directory Structure

```text
notes/
├── README.md                       # このファイル
├── .extraction-manifest.json        # extract_freetext.py が書く（commit 必須・人手編集禁止）
├── pending-leads.md                 # Pending Lead アクション（時系列）
├── sessions/                        # セッション成果
│   └── YYYY-MM-DD-session-NN.md
├── learnings/                       # 学び・振り返り
│   └── YYYY-MM-DD.md
└── misc/                            # その他自由記述
    └── <slug>.md
```

Subdirectories are not required; add them as needed. This structure only exists because
the auto-routing path in `extract_freetext.py`, which classifies content from top-level
headings, assumes it.

## Editing Rules

- **Free-form content**: write anything you want in markdown. Style and section structure are free
- **commit required**: preserve state in git. These files are not covered by `.gitignore`
- **Do not touch `.state/org-state.md`**: if you need to change structured state,
  write to the DB via `tools.state_db.writer.StateWriter`, then let the post-commit hook
  regenerate the markdown
- **`.state/journal.jsonl` was removed in M4**: for events, only the DB `events` table is the SoT.
  Append via `tools/journal_append.py`

## Migrate Existing `org-state.md` Free-Form Content

If legacy free-form content still remains in `org-state.md`, extract it into `notes/`
with the following commands, then regenerate `org-state.md` with snapshotter:

```bash
# 1. 何が動くか先に確認
python -m tools.state_db.extract_freetext \
    --org-state .state/org-state.md \
    --notes-dir notes/ \
    --plan

# 2. 実行 (notes/ にファイルが生まれ、org-state.md から該当セクションが消える)
python -m tools.state_db.extract_freetext \
    --org-state .state/org-state.md \
    --notes-dir notes/ \
    --apply

# 3. snapshotter で DB ベースの dump に置き換える
python -c "from pathlib import Path; from tools.state_db import connect; \
  from tools.state_db.snapshotter import post_commit_regenerate; \
  conn = connect('.state/state.db'); post_commit_regenerate(conn, Path('.'))"

# 4. drift_check で 0 を確認
python -m tools.state_db.drift_check --db .state/state.db --markdown .state/org-state.md
```

`extract_freetext` is idempotent, so running it a second time does nothing.
---
