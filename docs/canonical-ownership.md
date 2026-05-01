# Canonical ownership

Which language is the source of truth for each artifact category.
"Canonical" means: edits land here first; the other side mirrors via translation/back-port PRs.

| Category | Canonical | Rationale |
|---|---|---|
| `docs/glossary.md` | en (this repo) | Term lock owner. ja side cross-links here. |
| `docs/canonical-ownership.md` | en (this repo) | Meta about ownership lives with the glossary. |
| `docs/translation-manifest.md` | en (this repo) | Tracks translation status of every artifact. |
| `docs/non-goals.md` | en (this repo) | Strategic positioning is en-first; ja translates. |
| `docs/overview-technical.md` | en (this repo) | Architecture-of-record. ja translates. |
| `README.md` (first impression) | en (this repo) | Pitch / first impression is en-canonical. ja translates. |
| `docs/getting-started.md` | en (this repo) | Onboarding flow is en-canonical. |
| `.claude/skills/*/SKILL.md` | en (this repo) | Skill definitions are en-canonical for OSS. ja back-ports renames as terminology fixes. |
| `knowledge/curated/*.md` | ja (`claude-org-ja`) | Curated learnings are written in ja first; translation is best-effort. |
| `registry/projects.md` | ja (`claude-org-ja`) | Local-only operational state. ja-only; not translated. |
| Runtime code: `tools/**`, `dashboard/**`, `.claude/settings.json`, `.hooks/**`, `tests/**` | ja (`claude-org-ja`), **auto-mirrored** | Behavior-bearing code. ja is SoT per Lead decision 2026-04-30 (Issue #171). en is kept in sync by the auto-mirror-runtime workflow (Issue #189). Issue #189 listed `.claude/hooks/**` but the actual hooks live at `.hooks/**` in both repos; the classifier matches reality. Per default policy, ja docstrings/comments ride along onto en unchanged in P1; revisit if Lead chooses overlay translation later. |

## Conflict resolution

If a PR edits both sides of a row, the canonical side wins.
If the canonical side is en and the PR is ja-only, treat it as a back-port: must reference an en-side issue or PR.
