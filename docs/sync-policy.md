# Sync policy

How edits propagate between this repo (`suisya-systems/claude-org`, en) and `suisya-systems/claude-org-ja` (ja).

See `docs/canonical-ownership.md` for which side is the source of truth for each artifact category.

## Release-gated SLA

The ja side is allowed to lag the en side, bounded by release cadence:

- **During a release window** (between en `vX.Y.0` tag and the matching ja release tag): ja must catch up before the ja release ships. Translation gaps that block the ja release block the release.
- **Between release windows** (no active en release in flight): ja may lag by **up to one minor release**. If ja is more than one minor behind en `main`, open a `translation-pending` tracking issue on ja.
- **Hot-fix patches** (en `vX.Y.Z` where Z > 0 and the change is a security or correctness fix): ja must mirror within 14 days, or sooner if the fix is exploitable.

"Lag" is measured in en-side commits to canonical artifacts (per `docs/canonical-ownership.md`); doc-only typo fixes do not count.

## Back-port limit

Edits made directly on the ja side may be back-ported to en **only** in these three categories:

1. **Terminology** — glossary fixes (e.g., `フォアマン` → `ディスパッチャー`) where the ja side discovered a clearer term and the en glossary should track it.
2. **Concept definitions** — a ja explanation of a role, lifecycle, or invariant that turned out to be sharper than the en wording. Back-port the *definition*, not surrounding prose.
3. **API contract** — schema, hook protocol, or CLI surface changes whose ja docs are accidentally more authoritative because the implementation was discussed in ja first.

Anything else (prose polish, examples, structural reorganization on the ja side) stays ja-local. To change canonical-en content, open a PR against en first.

## Divergence-allowed sections

These intentionally diverge and are **not** subject to translation parity:

- `registry/projects.md` — local operational state (ja-canonical per `docs/canonical-ownership.md`; en holds an unrelated en-side projects list).
- `knowledge/curated/*.md` — curated learnings are ja-canonical; en translation is best-effort, not blocking.
- `.state/`, `.curator/`, `.dispatcher/` — runtime/operator state, scoped per repo.
- `bootstrap-cherry-picks.md` (en-only) and `docs/translation-manifest.md` (en-only) — meta/process artifacts.
- README first-impression copy may differ in tone and screenshot/badge selection so long as the technical claims match.

## `docs/getting-started.md` exception (B3)

Per plan-110 §8 Wave C Minor reflection: `docs/getting-started.md` is **ja-canonical** in `docs/canonical-ownership.md`, but en maintains a **B3 parallel SOT** copy. Onboarding flow is sensitive to platform-specific install instructions and en/ja paths diverge enough that pure translation produces awkward output; both sides edit their own file and reconcile structural changes (new sections, removed steps) via a back-port PR within the back-port limits above.

## Cross-repo notify CI

When a ja-side PR merges to `main`, the workflow `.github/workflows/notify-en-changes.yml` (ja side) fires a `repository_dispatch` event of type `ja_pr_merged` to this repo. The receiving workflow `.github/workflows/notify-ja-changes.yml` (this repo) opens a `TRANSLATION-PENDING` issue carrying the ja PR title and URL. The Lead/Curator triages: either close the issue (out of scope or canonical-en) or schedule the translation work.

The reverse direction (en → ja) is symmetric: an en merge fires `en_pr_merged` to the ja repo and opens a translation-pending issue there.

The dispatch step requires a PAT with `repo` scope on the receiving repo, stored as `secrets.NOTIFY_EN_PAT` (ja side) and `secrets.NOTIFY_JA_PAT` (en side, currently unused — en→ja sender is a follow-up). Until the PAT is configured the workflow is dormant; the receiver side fails closed (no spurious issues) because no dispatch arrives.
