# Sync Policy

Rules for how edits propagate between this repository (`suisya-systems/claude-org`, en) and its sibling repository `suisya-systems/claude-org-ja` (ja).

See `docs/canonical-ownership.md` for which side is canonical for each artifact category.

## Release-Coupled SLA

The ja side may lag behind the en side, but the upper bound is defined by release cadence.

- **During a release window** (from the en `vX.Y.0` tag until the corresponding ja release tag): ja must fully catch up before the ja release ships. Any translation gap that blocks the release blocks the release.
- **Outside a release window** (when no active en release is in progress): ja may lag by up to **one minor release**. If it falls behind en `main` by two or more minors, open a `translation-pending` tracking issue on the ja side.
- **Hotfixes** (en `vX.Y.Z` where `Z>0` and the change is for security or correctness): ja must reflect the change within 14 days, or sooner for exploitable fixes.

"Lag" is measured by the number of en-side commits to en-canonical artifacts (see `docs/canonical-ownership.md`). Typo-only commits do not count.

## Backport Restrictions

Edits made directly on the ja side may be backported to the en side in only these **three categories**.

1. **Terminology**: glossary fixes (example: `Foreman` -> `Dispatcher`). Use this when the ja side finds clearer terminology and the en glossary should follow.
2. **Concept definitions**: text defining roles, lifecycle, invariants, and similar concepts where ja wording ends up sharper than en. The backport target is the **definition itself**, not surrounding prose.
3. **API contracts**: schema, hook, or CLI surface changes where implementation discussion happened first in ja and the ja docs accidentally became canonical.

Everything else (prose polish, added examples, structural rewrites on the ja side) stays ja-local. If canonical wants to change en-side content, open the PR on the en side first.

## Allowed Divergence Sections

The following may intentionally diverge. They are **not** subject to translation parity.

- `registry/projects.md` - local operational state (`docs/canonical-ownership.md` marks it as ja-canonical; the en side keeps its own unrelated en project list).
- `knowledge/curated/*.md` - curated knowledge is ja-canonical. en translations are best-effort and do not block releases.
- `.state/`, `.curator/`, `.dispatcher/` - runtime/operator state. Scoped per repository.
- en-only: `bootstrap-cherry-picks.md`, `docs/translation-manifest.md` - meta/process artifacts.
- README first-impression copy (tone, screenshots, badge selection) may differ between sides as long as the technical claims match.

## `docs/getting-started.md` Exception (B3)

As recorded in the plan-110 §8 Wave C Minor retrospective, `docs/getting-started.md` is classified as **ja-canonical** in the en repo's `docs/canonical-ownership.md`, but the en side keeps a **B3 parallel SoT** copy. Onboarding is sensitive to platform-specific install steps and paths that diverge between en and ja, so a pure translation becomes unnatural. Each side therefore edits its own file, and structural changes (section additions/removals) are reconciled by backport PRs within the backport-restriction rules.

## Cross-Repository Notification CI

When a PR is merged to `main` on the ja side, `.github/workflows/notify-en-changes.yml` (this repository) fires a `repository_dispatch` event `ja_pr_merged` to the en repo. The receiving `.github/workflows/notify-ja-changes.yml` (en repo) opens a `TRANSLATION-PENDING` issue containing the ja PR title and URL. The Lead/Curator triages it, then either closes the issue (out of scope or determined canonical-en) or schedules translation work.

The reverse direction (en -> ja) is symmetrical: an en-side merge fires `en_pr_merged` to the ja repo and opens a translation-pending issue on the ja side.

The ja -> en `notify-ja-changes.yml` was later folded into the auto-mirror-runtime workflow in Issue #189 and removed on the en side. The en-side workflow that receives `ja_pr_merged` is now only the new `auto-mirror-runtime.yml`, which also took over translation-pending issue creation.

The dispatch step requires a PAT with `repo` scope for the receiving repository. Store it as `secrets.NOTIFY_EN_PAT` on the ja side and `secrets.NOTIFY_JA_PAT` on the en side (the en -> ja sender is not implemented in this PR and will be handled later). Until the PATs are set, the workflow remains dormant, and the receiver does not mis-open issues because no dispatch arrives (fail-closed).

## Auto-mirror runtime

On 2026-04-30, the Lead finalized **Option A (ja = SoT, en = auto-mirror runtime)** (Issue #171 / Issue #189). Based on this, a CI pipeline is being introduced in phases to auto-sync en-side runtime code when PRs are merged to ja `main`.

### Scope (mirror target path globs)

The following paths are ja-canonical and covered by auto-mirror. The en side is synced through the en repo's `auto-mirror-runtime.yml`.

- `tools/**/*.py`, `tools/**/*.json`
- `dashboard/app.js`, `dashboard/server.py`, `dashboard/index.html`
- `.claude/settings.json`, `.hooks/**` (Issue #189 wrote this as `.claude/hooks/**`, but the actual files live under `.hooks/**` in both repos, so the classifier matches that)
- `tests/**`, `tools/test_*.py`

Out of scope (existing translation / allowed-divergence rules continue):

- `.claude/skills/**`, `docs/**`, `README.md`, `CLAUDE.md` - through the translation pipeline
- `knowledge/curated/**`, `registry/projects.md`, `.state/`, `.curator/`, `.dispatcher/` - allowed divergence

The canonical classifier is en-side `tools/sync_classifier.py` (fully covered by pytest).

### en-side workflow

- Implementation: `.github/workflows/auto-mirror-runtime.yml` in `suisya-systems/claude-org`
- Reuses the existing `repository_dispatch` `ja_pr_merged` (fired from `.github/workflows/notify-en-changes.yml`), so no new PAT is required on the ja side
- Operational docs: `docs/runbook/auto-mirror-runtime.md` in the en repo (temporary disable, manual replay for past merges, definitions of each phase)

### Current phase: P2 (mirror PR, manual merge)

When a ja PR is merged, the en-side workflow imports runtime-class files from the ja merge SHA, force-pushes them to branch `auto-mirror/ja-pr-<N>`, and opens a mirror PR named `auto-mirror: ja#<N> <title>` (manual merge). If translation-class or unknown-class files are included, it also opens one tracking issue as before (`auto-mirror P2: ja#<N>` ...) with labels `translation-pending` and `needs-triage`. Batches containing only divergence-allowed files are no-op.

The implementation landed as en-side Issue #335. The kill switch is `OPEN_PR: 'false'` (see the runbook), which drops back to P1 warn-only.

Per Lead decision, authentication on the en side is two-tiered: prefer `secrets.AUTO_MIRROR_PAT` (so mirror PRs trigger `pull_request` CI), and fall back to `GITHUB_TOKEN` if unset (push and PR creation still work, but downstream workflows do not trigger due to GitHub Actions behavior). The ja side remains unchanged and uses only the existing `NOTIFY_EN_PAT` (preserving the constraint from Issue #189).

Roadmap:

| Phase | Behavior | Promotion condition |
|---|---|---|
| P1 | Classify and open tracking issues only. No mirror PR. | (Already folded into P2) |
| P2 (current) | Open mirror PRs on the en side (manual merge) | 10+ merged PRs, conflict/docstring impact understood |
| P3 | Auto-merge runtime-only mirror PRs (gate pending Lead decision) | 4+ weeks of stable P2 operation |
| P4 | Reverse-drift detection (warn on en-side runtime edits with no ja parent) | Additional feature, no blocker |

### No direct edits to en-side runtime (prevent reverse drift)

Do not edit ja-canonical runtime code directly on the en side (the scope above). If a fix is noticed on the en side, open the PR on ja first and let it flow into en through auto-mirror.

Exception (emergency hotfix that touches only en): follow up with a backport PR to ja and record it in the en runbook as a missed mirror. The P4 reverse-drift detector is intended to detect and surface those cases.

### Lead decision points (default applies during P1)

- **docstring overwrite policy** (Issue #189 §Open #1): default is "carry ja docstrings into en as-is". Overlay translation is not used. If the Lead reverses this, updating this section and the corresponding line in en `docs/canonical-ownership.md` is sufficient to switch policy.
- **ja-only doc commits** (#163, #168): in P1, the classifier sends them through the existing `TRANSLATION-PENDING` flow as `translation` class, so the status quo remains. No new warning signal is added.

P3 gating for #2 and #3 is out of scope here.

## Notification CI Smoke-Test Log

| Date/Time (UTC) | Check |
|---|---|
| 2026-04-28 | Trivial PR used to confirm initial `notify-en-changes.yml` dispatch and en-side `TRANSLATION-PENDING` issue creation |
