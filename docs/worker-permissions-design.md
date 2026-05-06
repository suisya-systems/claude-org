# Worker Permission Management Design (schema-driven worker permissions)

> Related issue: [#99](https://github.com/suisya-systems/claude-org/issues/99)
> Status: Phase 1 complete (PR #169), Phase 2 complete (PR for this document)

This document summarizes the rationale and operating notes for replacing worker Claude `.claude/settings.local.json` permission management in claude-org from hand-written JSON by the Lead to a **schema-driven generator + static deny + drift CI** model.

## Background / Motivation

Previously, worker `.claude/settings.local.json` files were **generated as hand-written JSON by the Lead inside the org-delegate flow**. Structurally, this leaves room for **over-granting permissions based on Lead judgment**.

### Specific case (2026-04-26)

When dispatching `worker-strategic-memo-v5-update`, the Lead added the following beyond the actual need (`additionalDirectories` only), "just in case":

- wildcard allow for `Edit(.../docs/internal/**)`
- `Write(...)`-style permissions

This surfaced in retro after being detected as an event blocked by the PreToolUse hook.

### Root problem

- Memory-based self-discipline (for example, `feedback_no_secretary_carveouts`) is **reactive** and depends on human judgment
- It is **asymmetric** with the existing claude-org F-d axis (schema-driven role_configs + drift CI): role_configs are protected by schema-as-SOT, but worker permissions remain hand-written JSON
- There is **no structural barrier** against "accidentally granting too much"

## Proposal (5 stages)

### 1. Schema extension

Add a `worker_roles` section to `tools/role_configs_schema.json`:

```json
"worker_roles": {
  "default": { "allow": [...], "additionalDirectories": [] },
  "claude-org-self-edit": { ... },
  "doc-audit": { ... },
  "web-research": { ... }
}
```

Each role has a **fixed permission set**, and the Lead cannot extend it ad hoc.

### 2. Generator tool

Introduce `tools/generate_worker_settings.py`:

```bash
python tools/generate_worker_settings.py \
  --role doc-audit \
  --worker-dir <WORKER_DIR> \
  --claude-org-path <CLAUDE_ORG_PATH> \
  > $WORKER_DIR/.claude/settings.local.json
```

Input is only the role name plus path variables. Output is generated deterministically from the schema.

### 3. Lead PreToolUse hook (and static deny)

**Deny** direct edits via Claude `Write` / `Edit` tools to `workers/*/.claude/settings.local.json` (and the same under worktrees):

- add the rule to `permissions.deny` in the Lead's `.claude/settings.local.json`
- the goal is to close the main misgrant path: the Lead hand-writing settings with `Edit`
- file writes from Bash/PowerShell (`Bash(python:*)`, etc.) remain separately allowed, so modification via Bash is still technically possible. Full generator-only enforcement is planned for Phase 3 together with a `block-secretary-write-worker-settings.sh`-equivalent hook

### 4. `org-delegate` Step 1.5 migration

Replace the current hand-written JSON generation step with a generator call. Update the SKILL.md body and journal event schema.

### 5. Drift CI extension

Add `--include-worker-settings` to `tools/check_role_configs.py`. Validate Pattern A workers placed at `<workers_dir>/<project>/.claude/settings.local.json` against the schema. Drift = fail.

> **Current validation scope (as of Phase 1)**: `--include-worker-settings` scans only `<BASE_DIR>/*/.claude/settings.local.json`, so Pattern B at `<BASE_DIR>/<project>/.worktrees/<task>/.claude/settings.local.json` is not yet checked. Recursive extension into worktrees is a Phase 3 item (see below).

## Benefits (7 items)

* **Structural prevention of over-granting**: the Lead cannot hand-write broad permissions
* **Reproducibility**: same role -> same permission set (deterministic)
* **Extension of schema-as-SOT**: aligns with the existing F-d axis (`role_configs` ↔ schema CI) and can be extracted as a Layer 1 (`core-harness`) primitive
* **Approval friction concentrates on schema edits**: adding a new role requires a schema PR -> user review is traceable
* **One more layer in defense in depth**: hook + tool gate + schema validation + CI = 4 layers
* **Foundation for the OSS portfolio**: candidate primitive when splitting Layer 1 (`core-harness`) out of claude-org
* **Move away from memory-based reactive discipline**: prevent "accidental" cases with structural barriers

## Drawbacks (7 items)

* **Initial implementation cost**: schema extension + generator + hook + skill updates + CI ≈ 2-3 PRs, about one week total
* **Friction when adding new worker patterns**: even one-off tasks require adding a `worker_role` to the schema -> slower in urgent cases
* **The schema may grow too large**: maintenance cost rises as roles increase
* **Escape-hatch design is difficult**: a loose `worker_roles.adhoc` weakens the barrier, but omitting it can block urgent response -> tradeoff
* **Cost to update the existing worker dispatch flow**: `org-delegate` Step 1.5 / Step 3 / `org-state.md` / journal event schema all need to align to the new method
* **Debugging becomes harder**: reading `settings.local.json` alone does not immediately show intent -> the generator logic must be traced
* **Adds constraints to claude-org itself**: dogfooding becomes tighter (meta-recursive)

## Alternatives

* **A**: as proposed (schema extension + generator + hook + CI, full)
* **B**: drop the hook portion (schema + generator + CI only, no hook enforcement) -> partial barrier, lighter
* **C**: no schema extension, generator from templates only -> lightest, weakest
* **D**: reject. Rely on stronger memory + retro (status quo)

## Recommendation

Recommend **A (full proposal)** as the target state. Practical phasing is:

* **Phase 1** (about 1 week): equivalent to B — schema extension + generator + drift CI (completed in PR #169)
* **Phase 2**: add hook enforcement (upgrade to A) (completed in this PR)
* **Phase 3**: design an escape hatch (for example, limited `worker_roles.adhoc`), extend drift CI scope (recurse into Pattern B worktrees), accumulate operational knowledge (alert paths and retro integration)

## Acceptance Criteria

* [x] Add a `worker_roles` section to `tools/role_configs_schema.json` (Phase 1)
* [x] Implement `tools/generate_worker_settings.py` (including unit tests) (Phase 1)
* [x] Replace the hand-written JSON section in `org-delegate` Step 1.5 with a generator call (Phase 2)
* [x] Add a deny rule for `Write(*/workers/*/.claude/settings.local.json)` to the Lead settings (Phase 2)
* [x] Make `tools/check_role_configs.py` validate worker `settings.local.json` against the schema with `--include-worker-settings` (Phase 1). For now this covers only `<BASE_DIR>/*/.claude/...`; Pattern B under worktrees is planned for Phase 3
* [x] Document the 7 benefits / 7 drawbacks in the README / internal docs (this document)

## Related

* Direct trigger: the 2026-04-26 permission expansion incident in `worker-strategic-memo-v5-update` (caught by the PreToolUse hook)
* Related memory: `feedback_secretary_generation_time_is_blocking`, `feedback_no_secretary_carveouts`
* Related issues: #70 (staged introduction of the PreToolUse hook), #85 (role config CI consistency), #86 (fail-closed allowlist)
---
