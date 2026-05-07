# Runbook: auto-mirror-runtime workflow

`.github/workflows/auto-mirror-runtime.yml` mirrors runtime code from
`suisya-systems/claude-org-ja` into this repo when a ja PR merges. This page
covers operational tasks and the phased rollout plan.

Design source: `suisya-systems/claude-org-ja#189` (and Lead decision #171).
P2 implementation tracked under `suisya-systems/claude-org-ja#335`.

## What it does today (Phase P2)

- Triggered by `repository_dispatch` event `ja_pr_merged` from ja repo
  (existing pipeline; no new PAT strictly required, but see Auth below).
- Pulls the changed-file list of the ja PR via `gh api`, with per-file
  status (added / modified / removed / renamed).
- Classifies each file using `tools/sync_classifier.py`:
  - `runtime`: opened as a mirror PR on this repo (P2 behavior).
  - `translation`: handled by existing TRANSLATION-PENDING flow.
  - `divergence-allowed`: intentionally divergent; ignored.
  - `unknown`: surfaced for manual triage on the tracking issue.
- For runtime-class files: shallow-fetches ja at the merge SHA, copies
  the runtime files into a branch `auto-mirror/ja-pr-<N>`, and opens (or
  refreshes) a PR titled `auto-mirror: ja#<N> <title>` against `main`,
  labeled `auto-mirror-runtime`. Force-push is used so reruns are
  idempotent — the auto-mirror branch namespace is exclusively owned by
  this workflow.
- For translation- or unknown-class files (or when `OPEN_PR=false`): opens
  (or comments on) a single tracking issue carrying the same
  `auto-mirror-runtime` / `translation-pending` / `needs-triage` labels
  as before. The `translation-pending` label remains the contract for
  downstream translation-pipeline consumers.
- For divergence-allowed-only batches: no PR, no issue.

This workflow subsumes the previous `notify-ja-changes.yml`; that file
was removed so a single dispatch produces at most one PR + at most one
tracking issue (no duplicates).

## Auth

Two secrets are consulted, in order, for any same-repo write (push +
`gh pr create` / `gh pr edit`):

1. `secrets.AUTO_MIRROR_PAT` — preferred. A classic PAT with `repo`
   scope (or fine-grained PAT with Contents:write + Pull requests:write
   on this repo) issued by a maintainer. Required if you want PRs opened
   by the workflow to trigger `pull_request` workflows such as
   `tests.yml`. GitHub deliberately blocks workflows from triggering
   other workflows when the source PR was opened by `GITHUB_TOKEN`, so
   without `AUTO_MIRROR_PAT` mirror PRs will land with **no CI**.
2. `secrets.GITHUB_TOKEN` — automatic fallback. Push and PR creation
   still succeed, but as above, downstream CI won't fire on the mirror PR.

The ja side continues to use only its existing `secrets.NOTIFY_EN_PAT`,
which never holds write scope on this repo. Issue #189 explicitly kept
the ja side free of new secrets; the optional PAT lives on the en side.

If `AUTO_MIRROR_PAT` is rotated or revoked, the workflow keeps running
under `GITHUB_TOKEN` automatically; reviewers should treat any mirror PR
without CI badges as warranting a manual rerun once the PAT is back.

## Disable temporarily

Two equivalent options:

1. Flip the kill-switch in the workflow file:

   ```yaml
   env:
     OPEN_PR: 'false'    # P1 warn-only — tracking issue, no mirror PR
   ```

   Commit, push, done. The tracking-issue path keeps working.

2. Short-circuit the entire job:

   ```yaml
   jobs:
     classify-and-mirror:
       if: false
       runs-on: ubuntu-latest
   ```

   Use this if you also want to suppress the tracking issue (e.g.,
   during a multi-day backfill).

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

`ja_merge_sha` is optional — the workflow resolves it from the PR via
`gh api`. Title and URL are also optional (the workflow re-fetches them
from the GH API), but setting them keeps the PR / issue body legible if
the ja PR was since edited.

A rerun for the same ja PR number is safe **while the matching mirror
PR is open**: branch `auto-mirror/ja-pr-<N>` is force-updated and the
PR body / title are rewritten in place. If the mirror PR was previously
closed (manually rejected, or merged), a rerun will push the branch but
**will not** reopen or replace the closed PR — the workflow only
detects `--state open`. To re-mirror after a close, delete the branch
first or change the ja PR number you are replaying.

## Conflict handling

P2 does not auto-merge. If `git push` succeeds but the resulting PR
conflicts with `main` (e.g., because en has diverged on a runtime path),
the reviewer has three options:

1. Resolve locally and push to the same `auto-mirror/ja-pr-<N>` branch
   (the workflow won't overwrite until the next ja PR rerun touches the
   same number).
2. Close the mirror PR and apply the ja change by hand. Note this in
   the matching `auto-mirror P2: ja#<N>` tracking issue (if any) for
   audit.
3. Re-run the workflow (`gh workflow run …`) once en is in a state where
   a clean apply is possible. Force-push semantics make rerun safe.

The reverse drift detector (Phase P4) will eventually catch the second
case — en runtime edits without a ja parent — but is out of scope here.

## Phased rollout

| Phase | Status | Behavior | Exit criterion |
|---|---|---|---|
| P1 | superseded | classify + tracking issue, no mirror PR | (rolled into P2) |
| P2 | **active** | open mirror PR per ja merge, manual merge | ≥10 mirror PRs merged, conflict + docstring impact understood |
| P3 | not yet | auto-merge runtime-only mirror PRs (gate TBD by Lead) | ≥4 weeks of P2 stability |
| P4 | not yet | reverse-drift detector (en runtime edits without ja parent) | n/a (additive) |

Reverting P2 → P1 is a single-line change: `OPEN_PR: 'false'`. The
tracking-issue path stays functional under either toggle.

## Pending Lead decisions

These are surfaced for visibility; defaults are applied today and can be
flipped with doc-only edits if Lead changes course:

- **Docstring overwrite policy** (Issue #189 §Open #1): default = ja
  docstrings ride along onto en. No overlay translation in P2.
- **ja-only doc commits** (#163, #168 reference, Issue #189 §Open #4):
  default = status quo (classified as `translation` or `divergence-allowed`,
  not auto-mirrored). No new warn signal in P2.
- **P3 auto-merge gate** (Issue #189 §Open #2, #3): out of scope until
  P2 has accumulated ≥10 merged mirror PRs of empirical data.

## Related files

- Classifier: `tools/sync_classifier.py`
- Tests: `tools/test_sync_classifier.py`
- Workflow: `.github/workflows/auto-mirror-runtime.yml`
- Canonical mapping: `docs/canonical-ownership.md`
- Sibling policy (ja): `docs/sync-policy.md` in `suisya-systems/claude-org-ja`
