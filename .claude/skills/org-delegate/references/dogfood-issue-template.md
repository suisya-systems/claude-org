# Dogfood follow-up issue template

This is the body template for the follow-up issue created paired with a "PR that introduces a new tool / runtime / workflow" under org-delegate Step 1.8 / Issue #338. Intended use: `gh issue create --title "dogfood follow-up: <tool>" --body-file <this rendered>`.

Always Refs the source PR, and aggregate defects observed during the first real-use (dogfood pass) onto this issue. Once defects have settled, split into individual fix issues / close as appropriate.

---

## Title

```
dogfood follow-up: <tool / surface name>
```

Examples: `dogfood follow-up: tools/gen_delegate_payload.py`, `dogfood follow-up: codex companion runtime`

## Body template

```markdown
## Source

- Implementation PR: #<NNN>
- Originating org-delegate task: `<task-id>`
- Introduced surface: `<file path / module / runtime name>`

## Why this issue exists

This is a paired dogfood follow-up created by org-delegate Step 1.8.
The implementation PR introduces a new tool / runtime / workflow whose
real-world failure modes are not fully observable from unit tests or
self-review. We earmark the next delegation that uses this surface as a
**dogfood pass** and report any defects observed there to this issue
before they spread.

## Expected validation surface

<!-- What aspects we expect the dogfood pass to actually exercise.
     Fill in at issue creation time so the dogfood worker has a checklist. -->
- [ ] <e.g., does the brief generate without breakage on a real Pattern A task>
- [ ] <e.g., is it consistent with claude-org-runtime without --skip-settings>
- [ ] <e.g., on failure, can the cause be identified from the error message>
- [ ] <e.g., does it not collide with existing skills / existing CLAUDE.md>

## Defect reporting format

Append findings as comments on this issue using the following block:

```
### Defect <N>: <one-line summary>

- Severity: Blocker | Major | Minor | Nit
- Observed in: dogfood task `<task-id>` / commit `<SHA>` / PR #<NNN>
- Repro: <minimal steps>
- Expected: <what should have happened>
- Actual: <what did happen>
- Suspected cause: <if any>
- Proposed fix: <if known>
```

## Dogfood pass tracking

The canonical values live in the corresponding row of `registry/dogfood_pending.md` (`task_id` / `tool / surface` / `impl_pr` / `dogfood_issue` / `dogfood_run_task_id` / `status`). Do not duplicate them here — refer to the register as the SoT. In comments on this issue, record only defect reports; check the register for state (`status`) and earmark (`dogfood_run_task_id`).

## Closing criteria

- One round of dogfood pass has completed
- Detected Blockers / Majors have been split into individual fix issues
- Minor / Nit may remain on this issue, but file a cleanup issue if they accumulate too much

Refs #<source PR>
```

---

## Notes

- `gh issue create` is invoked by **org-pull-request** at the same timing as PR creation. org-delegate only appends to `registry/dogfood_pending.md` (org-delegate Step 1.8 §Lead responsibilities).
- Do not use `Closes`. The dogfood observation period continues even after the implementation PR is merged, so use only `Refs #<source PR>`.
- If detected defects span multiple categories, aggregate them under one follow-up issue while splitting into individual fix issues (modeled on the 4-category defects of PR #288).
