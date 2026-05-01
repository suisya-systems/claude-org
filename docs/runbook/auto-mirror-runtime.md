# Runbook: auto-mirror-runtime workflow

`.github/workflows/auto-mirror-runtime.yml` mirrors runtime code from
`suisya-systems/claude-org-ja` into this repo when a ja PR merges. This page
covers operational tasks and the phased rollout plan.

Design source: `suisya-systems/claude-org-ja#189` (and Lead decision #171).

## What it does today (Phase P1)

- Triggered by `repository_dispatch` event `ja_pr_merged` from ja repo
  (existing pipeline; no new PAT required on this side).
- Pulls the changed-file list of the ja PR via `gh api`.
- Classifies each file using `tools/sync_classifier.py`:
  - `runtime`: would be auto-mirrored in P2+
  - `translation`: handled by existing TRANSLATION-PENDING flow
  - `divergence-allowed`: intentionally divergent; ignored
  - `unknown`: surfaced for manual triage
- Opens a single tracking issue **on this repo** with the classification
  summary, labeled `auto-mirror-runtime` (plus `translation-pending` if any
  translation-class file was touched, and `needs-triage` if any path
  classified as `unknown`).
- **Does NOT open a mirror PR.** The `OPEN_PR` env var defaults to `false`.

This workflow subsumes the previous `notify-ja-changes.yml`; that file has
been removed so a single dispatch produces a single issue (no duplicates).
The `translation-pending` label remains the contract for downstream
translation-pipeline consumers.

Cross-repo writes are deliberately avoided: posting back to the ja PR
would require a PAT on the en side, which Lead chose not to introduce in
P1 (Issue #189 design constraint). The signal lives here instead.

## Disable temporarily

Two equivalent options:

1. Set `OPEN_PR` aside and short-circuit the workflow by editing the file
   header:

   ```yaml
   jobs:
     classify-and-warn:
       if: false              # <-- disables the job entirely
       runs-on: ubuntu-latest
   ```

   Commit, push, done. Re-enable by removing `if: false`.

2. Delete the workflow file. Slower to restore; only do this for permanent
   removal.

GitHub also lets you disable a workflow from the Actions UI
(`Actions` → `Auto-mirror runtime (ja -> en)` → `…` → `Disable workflow`),
which is useful when you cannot land a code change quickly.

## Manually re-run for a missed merge

If `repository_dispatch` failed to fire (e.g., PAT outage on ja side), trigger
the workflow by hand:

```sh
gh workflow run auto-mirror-runtime.yml \
  -R suisya-systems/claude-org \
  -f ja_pr_number=<NUMBER> \
  -f ja_pr_title="<TITLE>" \
  -f ja_pr_url="https://github.com/suisya-systems/claude-org-ja/pull/<NUMBER>"
```

`ja_merge_sha` is optional; the workflow will resolve it from the PR if
omitted. Title and URL are also optional in P1 (the workflow re-fetches
them from the GH API), but setting them keeps the comment body legible if
the ja PR has been since edited.

## Phased rollout

| Phase | Status | Behavior | Exit criterion |
|---|---|---|---|
| P1 | **active** | classify + comment, no mirror PR | ≥1 week clean run, ≥5 ja merges classified correctly by spot check |
| P2 | not yet | open mirror PR per ja merge, manual merge | ≥10 mirror PRs merged, conflict + docstring impact understood |
| P3 | not yet | auto-merge runtime-only mirror PRs (gate TBD by Lead) | ≥4 weeks of P2 stability |
| P4 | not yet | reverse-drift detector (en runtime edits without ja parent) | n/a (additive) |

Switching P1 → P2 is a single-line change: `OPEN_PR: 'true'` in
`.github/workflows/auto-mirror-runtime.yml`. The corresponding mirror-PR
opening step is currently a stub that exits non-zero — implement it before
flipping the toggle.

## Pending Lead decisions

These are surfaced for visibility; defaults are applied today and can be
flipped with doc-only edits if Lead changes course:

- **Docstring overwrite policy** (Issue #189 §Open #1): default = ja
  docstrings ride along onto en. No overlay translation in P1.
- **ja-only doc commits** (#163, #168 reference, Issue #189 §Open #4):
  default = status quo (classified as `translation` or `divergence-allowed`,
  not auto-mirrored). No new warn signal in P1.

P3 gating decisions (#2, #3 in Issue #189) are out of scope for P1.

## Related files

- Classifier: `tools/sync_classifier.py`
- Tests: `tools/test_sync_classifier.py`
- Workflow: `.github/workflows/auto-mirror-runtime.yml`
- Canonical mapping: `docs/canonical-ownership.md`
- Sibling policy (ja): `docs/sync-policy.md` in `suisya-systems/claude-org-ja`
