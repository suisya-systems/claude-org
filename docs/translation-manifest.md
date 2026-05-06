# Translation manifest

State of every artifact that participates in the en ↔ ja translation pipeline.

Bootstrap source: `suisya-systems/claude-org@926df3943cb5df2d6ee419b020351178a96a88d1`. The en repo was transplanted from this ja commit; rows below cover every file at that snapshot plus every file currently tracked in en.

## Legend

| State | Meaning |
|---|---|
| `translated` | en file is a translation of an explicit ja source. |
| `copied` | en file is byte-equivalent to ja source (e.g., LICENSE, schema JSON, `.gitkeep`). |
| `intentionally omitted` | ja artifact has no en counterpart (per `docs/canonical-ownership.md`). |
| `local-only` | en file has no ja counterpart. |

## Rows

| en path | state | ja path / sha | last sync sha | notes |
|---|---|---|---|---|
| `.claude/settings.json` | copied | `.claude/settings.json` @ `926df394` | `926df394` | byte-equivalent |
| `.claude/skills/org-curate/SKILL.md` | translated | `.claude/skills/org-curate/SKILL.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-curate/references/knowledge-standards.md` | translated | `.claude/skills/org-curate/references/knowledge-standards.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-dashboard/SKILL.md` | translated | `.claude/skills/org-dashboard/SKILL.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-delegate/SKILL.md` | translated | `.claude/skills/org-delegate/SKILL.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-delegate/references/claude-org-self-edit.md` | translated | `.claude/skills/org-delegate/references/claude-org-self-edit.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-delegate/references/instruction-template.md` | translated | `.claude/skills/org-delegate/references/instruction-template.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-delegate/references/pane-layout.md` | translated | `.claude/skills/org-delegate/references/pane-layout.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-delegate/references/renga-error-codes.md` | translated | `.claude/skills/org-delegate/references/renga-error-codes.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-delegate/references/worker-claude-template.md` | translated | `.claude/skills/org-delegate/references/worker-claude-template.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-resume/SKILL.md` | translated | `.claude/skills/org-resume/SKILL.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-retro/SKILL.md` | translated | `.claude/skills/org-retro/SKILL.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-retro/references/work-skill-template.md` | translated | `.claude/skills/org-retro/references/work-skill-template.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-setup/SKILL.md` | translated | `.claude/skills/org-setup/SKILL.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-setup/references/permissions.md` | translated | `.claude/skills/org-setup/references/permissions.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-start/SKILL.md` | translated | `.claude/skills/org-start/SKILL.md` @ `926df394` | `926df394` |  |
| `.claude/skills/org-suspend/SKILL.md` | translated | `.claude/skills/org-suspend/SKILL.md` @ `926df394` | `926df394` |  |
| `.claude/skills/skill-audit/SKILL.md` | translated | `.claude/skills/skill-audit/SKILL.md` @ `926df394` | `926df394` |  |
| `.claude/skills/skill-audit/references/audit-checklist.md` | translated | `.claude/skills/skill-audit/references/audit-checklist.md` @ `926df394` | `926df394` |  |
| `.claude/skills/skill-eligibility-check/SKILL.md` | translated | `.claude/skills/skill-eligibility-check/SKILL.md` @ `926df394` | `926df394` |  |
| `.claude/skills/skill-eligibility-check/references/signals.md` | translated | `.claude/skills/skill-eligibility-check/references/signals.md` @ `926df394` | `926df394` |  |
| `.curator/CLAUDE.md` | translated | `.curator/CLAUDE.md` @ `926df394` | `926df394` |  |
| `.dispatcher/CLAUDE.md` | translated | `.dispatcher/CLAUDE.md` @ `926df394` | `926df394` |  |
| `.gitattributes` | copied | `.gitattributes` @ `926df394` | `926df394` | byte-equivalent |
| `.githooks/pre-commit` | translated | `.githooks/pre-commit` @ `926df394` | `926df394` |  |
| `.github/workflows/install-scripts.yml` | translated | `.github/workflows/install-scripts.yml` @ `926df394` | `926df394` |  |
| `.github/workflows/auto-mirror-runtime.yml` | local-only | — | — | Receives repository_dispatch from ja repo (P1 warn-only auto-mirror, Issue #189); supersedes the prior `notify-ja-changes.yml`. |
| `.github/workflows/tests.yml` | translated | `.github/workflows/tests.yml` @ `926df394` | `926df394` |  |
| `.gitignore` | copied | `.gitignore` @ `926df394` | `926df394` | byte-equivalent |
| `.hooks/block-dangerous-git.sh` | translated | `.hooks/block-dangerous-git.sh` @ `926df394` | `926df394` |  |
| `.hooks/block-dispatcher-out-of-scope.sh` | translated | `.hooks/block-dispatcher-out-of-scope.sh` @ `926df394` | `926df394` |  |
| `.hooks/block-git-push.sh` | translated | `.hooks/block-git-push.sh` @ `926df394` | `926df394` |  |
| `.hooks/block-no-verify.sh` | translated | `.hooks/block-no-verify.sh` @ `926df394` | `926df394` |  |
| `.hooks/block-org-structure.sh` | translated | `.hooks/block-org-structure.sh` @ `926df394` | `926df394` |  |
| `.hooks/block-workers-delete.sh` | translated | `.hooks/block-workers-delete.sh` @ `926df394` | `926df394` |  |
| `.hooks/check-worker-boundary.sh` | translated | `.hooks/check-worker-boundary.sh` @ `926df394` | `926df394` |  |
| `.hooks/lib/segment-split.sh` | translated | `.hooks/lib/segment-split.sh` @ `926df394` | `926df394` |  |
| `.hooks/test-always-block.sh` | translated | `.hooks/test-always-block.sh` @ `926df394` | `926df394` |  |
| `.hooks/test-block-workers-delete.sh` | translated | `.hooks/test-block-workers-delete.sh` @ `926df394` | `926df394` |  |
| `.state/.gitkeep` | copied | `.state/.gitkeep` @ `926df394` | `926df394` | byte-equivalent |
| `.state/workers/.gitkeep` | copied | `.state/workers/.gitkeep` @ `926df394` | `926df394` | byte-equivalent |
| `CLAUDE.md` | translated | `CLAUDE.md` @ `926df394` | `926df394` |  |
| `CONTRIBUTING.md` | translated | `CONTRIBUTING.md` @ `926df394` | `926df394` |  |
| `LICENSE` | copied | `LICENSE` @ `926df394` | `926df394` | byte-equivalent |
| `README.md` | translated | `README.md` @ `926df394` | `926df394` |  |
| `bootstrap-cherry-picks.md` | local-only | — | — | Bootstrap audit trail; en-only. |
| `dashboard/app.js` | translated | `dashboard/app.js` @ `926df394` | `926df394` |  |
| `dashboard/index.html` | translated | `dashboard/index.html` @ `926df394` | `926df394` |  |
| `dashboard/org_state_converter.py` | translated | `dashboard/org_state_converter.py` @ `926df394` | `926df394` |  |
| `dashboard/server.py` | translated | `dashboard/server.py` @ `926df394` | `926df394` |  |
| `dashboard/style.css` | translated | `dashboard/style.css` @ `926df394` | `926df394` |  |
| `docs/canonical-ownership.md` | local-only | — | — | Canonical ownership table; en-canonical. |
| `docs/getting-started.md` | translated | `docs/getting-started.md` @ `926df394` | `926df394` |  |
| `docs/glossary.md` | local-only | — | — | Term lock; en-canonical per docs/canonical-ownership.md. |
| `docs/non-goals.md` | translated | `docs/non-goals.md` @ `926df394` | `926df394` |  |
| `docs/org-state-schema.md` | translated | `docs/org-state-schema.md` @ `926df394` | `926df394` |  |
| `docs/oss-comparison.md` | translated | `docs/oss-comparison.md` @ `926df394` | `926df394` |  |
| `docs/overview-business.md` | translated | `docs/overview-business.md` @ `926df394` | `926df394` |  |
| `docs/overview-technical.md` | translated | `docs/overview-technical.md` @ `926df394` | `926df394` |  |
| `docs/sync-policy.md` | local-only | — | — | Cross-repo sync rules; en-canonical (added in this PR). |
| `docs/test-results/.gitkeep` | copied | `docs/test-results/.gitkeep` @ `926df394` | `926df394` | byte-equivalent |
| `docs/testing.md` | translated | `docs/testing.md` @ `926df394` | `926df394` |  |
| `docs/translation-manifest.md` | local-only | — | — | This file; en-canonical. |
| `docs/verification.md` | translated | `docs/verification.md` @ `926df394` | `926df394` |  |
| `knowledge/curated/.gitkeep` | copied | `knowledge/curated/.gitkeep` @ `926df394` | `926df394` | byte-equivalent |
| `knowledge/raw/.gitkeep` | copied | `knowledge/raw/.gitkeep` @ `926df394` | `926df394` | byte-equivalent |
| `knowledge/skill-candidates.md` | translated | `knowledge/skill-candidates.md` @ `926df394` | `926df394` |  |
| `registry/org-config.md` | translated | `registry/org-config.md` @ `926df394` | `926df394` |  |
| `registry/projects.md` | local-only | — | — | en-side operational state; ja-canonical artifact at same path is divergent (see docs/sync-policy.md). |
| `renga-layouts/ops.toml` | translated | `renga-layouts/ops.toml` @ `926df394` | `926df394` |  |
| `scripts/install-hooks.sh` | translated | `scripts/install-hooks.sh` @ `926df394` | `926df394` |  |
| `scripts/install.ps1` | translated | `scripts/install.ps1` @ `926df394` | `926df394` |  |
| `scripts/install.sh` | translated | `scripts/install.sh` @ `926df394` | `926df394` |  |
| `tests/__init__.py` | translated | `tests/__init__.py` @ `926df394` | `926df394` |  |
| `tests/fixtures/curated/.gitkeep` | copied | `tests/fixtures/curated/.gitkeep` @ `926df394` | `926df394` | byte-equivalent |
| `tests/fixtures/curated/sample-topic.md` | translated | `tests/fixtures/curated/sample-topic.md` @ `926df394` | `926df394` |  |
| `tests/fixtures/journal-sample.jsonl` | translated | `tests/fixtures/journal-sample.jsonl` @ `926df394` | `926df394` |  |
| `tests/fixtures/org-state-sample.md` | translated | `tests/fixtures/org-state-sample.md` @ `926df394` | `926df394` |  |
| `tests/fixtures/projects-sample.md` | translated | `tests/fixtures/projects-sample.md` @ `926df394` | `926df394` |  |
| `tests/fixtures/workers/worker-abc12345.md` | translated | `tests/fixtures/workers/worker-abc12345.md` @ `926df394` | `926df394` |  |
| `tests/run-all.sh` | translated | `tests/run-all.sh` @ `926df394` | `926df394` |  |
| `tests/test-block-dispatcher-out-of-scope.sh` | translated | `tests/test-block-dispatcher-out-of-scope.sh` @ `926df394` | `926df394` |  |
| `tests/test-block-git-push.sh` | translated | `tests/test-block-git-push.sh` @ `926df394` | `926df394` |  |
| `tests/test-block-org-structure.sh` | translated | `tests/test-block-org-structure.sh` @ `926df394` | `926df394` |  |
| `tests/test-block-pretooluse-hooks.sh` | translated | `tests/test-block-pretooluse-hooks.sh` @ `926df394` | `926df394` |  |
| `tests/test-check-worker-boundary.sh` | translated | `tests/test-check-worker-boundary.sh` @ `926df394` | `926df394` |  |
| `tests/test-install-hooks.sh` | translated | `tests/test-install-hooks.sh` @ `926df394` | `926df394` |  |
| `tests/test-precommit-secret-scanner.sh` | translated | `tests/test-precommit-secret-scanner.sh` @ `926df394` | `926df394` |  |
| `tests/test-unwrap-eval-bashc.sh` | translated | `tests/test-unwrap-eval-bashc.sh` @ `926df394` | `926df394` |  |
| `tests/test_check_role_configs.py` | translated | `tests/test_check_role_configs.py` @ `926df394` | `926df394` |  |
| `tests/test_org_state_converter.py` | translated | `tests/test_org_state_converter.py` @ `926df394` | `926df394` |  |
| `tests/test_parsers.py` | translated | `tests/test_parsers.py` @ `926df394` | `926df394` |  |
| `tools/check_renga_compat.py` | translated | `tools/check_renga_compat.py` @ `926df394` | `926df394` |  |
| `tools/check_role_configs.py` | translated | `tools/check_role_configs.py` @ `926df394` | `926df394` |  |
| `tools/dispatcher_runner.py` | translated | `tools/dispatcher_runner.py` @ `926df394` | `926df394` |  |
| `tools/org_setup_prune.py` | translated | `tools/org_setup_prune.py` @ `926df394` | `926df394` |  |
| `tools/role_configs_schema.json` | translated | `tools/role_configs_schema.json` @ `926df394` | `926df394` |  |
| `tools/test_check_renga_compat.py` | translated | `tools/test_check_renga_compat.py` @ `926df394` | `926df394` |  |
| `tools/test_dispatcher_runner.py` | translated | `tools/test_dispatcher_runner.py` @ `926df394` | `926df394` |  |
| `tools/test_org_setup_prune.py` | translated | `tools/test_org_setup_prune.py` @ `926df394` | `926df394` |  |

Total rows: 100 (every file in ja@926df394 plus every file currently tracked in en, including this PR's additions).

## Wave assignment

- Wave B-core filled rows for: README, CLAUDE.md, role docs, overviews, non-goals, getting-started, oss-comparison, org-state-schema.
- Wave B-runtime filled rows for: install / dashboard / tools / all 10 skills / testing / verification / knowledge/curated.
- Wave C closed the manifest by enumerating every remaining file and adding the en-only `docs/sync-policy.md` and `.github/workflows/auto-mirror-runtime.yml` entries (the latter superseded the original `notify-ja-changes.yml` row when Issue #189 P1 landed).
