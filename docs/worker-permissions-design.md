# Worker permissions design (schema-driven worker permissions)

> Related Issue: [claude-org-ja#99](https://github.com/suisya-systems/claude-org-ja/issues/99)
> Status: Phase 1 complete (PR #169), Phase 2 complete (the PR for this document)

This document captures the rationale and operational notes behind moving Worker Claude `.claude/settings.local.json` permission management away from hand-written JSON by the Lead (Secretary) and toward a **schema-driven generator + static deny + drift CI** scheme.

## Background / motivation

Historically, a Worker's `.claude/settings.local.json` was **hand-written by the Lead inside the org-delegate flow**. Structurally, this leaves room for **over-broad permission grants based on Lead judgment**.

### Concrete case (2026-04-26)

While dispatching `worker-strategic-memo-v5-update`, the Lead added the following "just in case", going beyond the actual need (only `additionalDirectories`):

- A wildcard allow `Edit(.../docs/internal/**)`
- A `Write(...)`-form permission

The PreToolUse hook caught this as a blocked event and it surfaced in retro.

### Root issue

- Memory-based self-discipline (e.g. `feedback_no_secretary_carveouts`) is **reactive** and depends on human judgment.
- It is **asymmetric** with claude-org's existing F-d axis (role_configs schema-driven + drift CI): role_configs is protected by schema-as-SOT, while Worker permissions remain hand-written JSON.
- There is **no structural barrier** to "accidentally granting too widely".

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

Each role has a **fixed permission set**; the Lead cannot ad-hoc extend.

### 2. Generator tool

Introduce `tools/generate_worker_settings.py`:

```bash
python tools/generate_worker_settings.py \
  --role doc-audit \
  --worker-dir <WORKER_DIR> \
  --claude-org-path <CLAUDE_ORG_PATH> \
  > $WORKER_DIR/.claude/settings.local.json
```

Inputs are role name + path variables only. Output is generated deterministically from the schema.

### 3. Lead PreToolUse hook (and static deny)

**Deny** Lead access to `workers/*/.claude/settings.local.json` (and worktree paths) via Claude's `Write` / `Edit` tools:

- Add to the Lead's `.claude/settings.local.json` `permissions.deny`.
- The goal is to close off the main mis-grant path (the Lead hand-editing via `Edit`).
- File writes from Bash / PowerShell (e.g. `Bash(python:*)`) remain allowed elsewhere, so Bash-side modification is technically still possible. Full generator-only enforcement is Phase 3 work, paired with a `block-secretary-write-worker-settings.sh`-equivalent hook.

### 4. `org-delegate` Step 1.5 migration

Replace the current hand-written JSON generation step with a generator call. Update SKILL.md text and the journal event schema.

### 5. drift CI extension

Add `--include-worker-settings` to `tools/check_role_configs.py`. Validate Workers placed at `<workers_dir>/<project>/.claude/settings.local.json` (Pattern A) against the schema. Drift = fail.

> **Current check scope (as of Phase 1)**: `--include-worker-settings` only walks `<BASE_DIR>/*/.claude/settings.local.json`, so Pattern B's `<BASE_DIR>/<project>/.worktrees/<task>/.claude/settings.local.json` is not checked. Recursing into worktrees is Phase 3 work (see below).

## Merits (7 items)

* **Structural prevention of over-grants**: the Lead cannot hand-grant broad permissions.
* **Reproducibility**: same role → same permission set (deterministic).
* **Extension of schema-as-SOT**: aligns with the existing F-d axis (role_configs ↔ schema CI), and is extractable as a Layer 1 (core-harness) primitive.
* **Approval friction concentrates on schema edits**: adding a new role requires a schema PR → user review is traced.
* **One more layer of defense in depth**: hook + tool gate + schema validation + CI = 4 layers.
* **Foundation for OSS portfolio**: a primitive candidate when extracting Layer 1 (core-harness) out of claude-org.
* **Escape from memory-based reactive discipline**: prevents "oops" cases via structural barriers.

## Demerits (7 items)

* **Initial implementation cost**: schema extension + generator + hook + skill rework + CI ≈ 2–3 PRs, ~1 week total.
* **Friction adding new-pattern Workers**: even one-off new tasks require adding a `worker_role` to the schema → slower in emergencies.
* **Schema may grow**: maintenance cost rises as roles increase.
* **Escape-hatch design is hard**: a permissive `worker_roles.adhoc` collapses the barrier; without one, emergencies stall — a tradeoff.
* **Update cost for the existing dispatch flow**: org-delegate Step 1.5 / Step 3 / org-state.md / journal event schema all need to be aligned to the new scheme.
* **Debugging is harder**: looking at `settings.local.json` directly does not reveal intent → the generator logic must be traced.
* **Constrains claude-org itself**: dogfood becomes tight (meta-recursion).

## Alternatives

* **A**: as proposed (schema + generator + hook + CI, full).
* **B**: drop the hook part (schema + generator + CI only, no hook enforcement) → partial barrier, lighter.
* **C**: no schema extension, template-based generator only → lightest, weakest.
* **D**: reject. Tough it out with memory + retro reinforcement (status quo).

## Recommendation

Recommend **A (full proposal)** as the end state. Phasing realistically:

* **Phase 1** (~1 week): equivalent to B — schema extension + generator + drift CI (completed in PR #169).
* **Phase 2**: add hook enforcement (upgrade to A) (completed in this PR).
* **Phase 3**: escape-hatch design (e.g. a limited `worker_roles.adhoc`), drift CI scope expansion (recurse into Pattern B worktrees), accumulate operational know-how (alert paths, retro hookup).

## Acceptance Criteria

* [x] Add `worker_roles` to `tools/role_configs_schema.json` (Phase 1)
* [x] Implement `tools/generate_worker_settings.py` (with unit tests) (Phase 1)
* [x] Replace the hand-written JSON section in `org-delegate` Step 1.5 with a generator call (Phase 2)
* [x] Add `Write(*/workers/*/.claude/settings.local.json)` deny rule to the Lead's settings (Phase 2)
* [x] `tools/check_role_configs.py` validates Worker `settings.local.json` against the schema with `--include-worker-settings` (Phase 1). Currently `<BASE_DIR>/*/.claude/...` only; Pattern B worktrees deferred to Phase 3
* [x] 7 merits / 7 demerits documented in README / internal docs (this document)

## Related

* Direct trigger: 2026-04-26 `worker-strategic-memo-v5-update` permission-extension event (caught by PreToolUse hook).
* Related memory: `feedback_secretary_generation_time_is_blocking`, `feedback_no_secretary_carveouts`.
* Related strategy doc: `docs/internal/strategic-analysis-2026-04-26.md` v5 §16 (Layer 1 OSS extraction candidate).
* Related Issues: claude-org-ja#70 (PreToolUse hook phased rollout), #85 (role config CI consistency), #86 (fail-closed allowlist).
