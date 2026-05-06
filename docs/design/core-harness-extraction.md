# Core-harness extraction (Layer 1)

> Related Issue: [#128](https://github.com/suisya-systems/claude-org/issues/128)
> Status: **design only** (this PR includes no implementation; implementation will be split into separate issues from Step B onward)
> Scope: design for extracting claude-org's **permission / sandbox / hooks / journal** primitives as Layer 1 = `core-harness`
> Dependent documents:
> - [core-harness inventory](https://github.com/suisya-systems/claude-org-private/blob/main/core-harness-inventory.md) (measurement doc, outside worker dir)
> - strategic-analysis §13.4 / §15.2 / §16.4.1 (Layer 1 positioning in the four-layer stack)
> - [docs/design/phase-2b-guardrails-refactor.md](./phase-2b-guardrails-refactor.md) (assumption that bash/awk adoption continues)
>
> **Historical note (Issue [#230](https://github.com/suisya-systems/claude-org/issues/230))**: This doc is written from the pre-extraction state, so some sections reference `tools/role_configs_schema.json` and `tools/generate_worker_settings.py` as in-tree paths. Those have since moved into the [`claude-org-runtime`](https://github.com/suisya-systems/claude-org-runtime) package and no longer exist in this repository (the actual files are now `src/claude_org_runtime/settings/role_configs_schema.json` and `src/claude_org_runtime/settings/generator.py`). The text below is preserved in its original form as a historical record of the extraction process.

This PR documents the **final answers to the 12 Lead questions**, the **concrete schema split**, **phased migration**, **test/CI strategy**, and **remaining risks** for the core-harness extraction. This PR does not implement anything. The target level of detail is high enough that Workers for follow-up Steps B-E can write code directly from this doc.

---

## 1. Background

### 1.1 Why extract it

claude-org is the Layer 4 reference distribution in the four-layer stack (see README). In the same way that Layer 4 already depends on Layer 3 (`renga`), this issue (#128) splits out **Layer 1 = `core-harness`**.

The extraction target is the **safety primitives**:

- **permission schema** (`tools/role_configs_schema.json`, 448 LOC): per-role allow/deny/hook policy
- **schema validator + generator** (`tools/check_role_configs.py` 718 LOC + `tools/generate_worker_settings.py` 140 LOC)
- **hook framework** (`.hooks/*.sh` deny scripts 893 LOC + `.hooks/lib/segment-split.sh` 325 LOC)
- **audit journal** (`.state/journal.jsonl` contract + append helper)

The total in inventory Appendix is **~2,520 LOC** plus 12 test files. The goal is to separate this from org doctrine and make it a reusable package.

### 1.2 Design goals

1. **One-way dependency**: only `claude-org → core-harness`. core-harness knows nothing about claude-org doctrine (`secretary` / `dispatcher` / `.dispatcher/` / `block-workers-delete.sh`, etc.).
2. **Compatibility via shim**: do not break existing claude-org CI; keep `tools/check_role_configs.py` as a thin CLI shim that calls `core_harness` internally.
3. **External orgs can assemble schema using core-harness alone**: the boundary test is whether another org can build role schema without reading claude-org.
4. **Phased shippability**: mergeable in order as Step B (schema) → C (hooks) → D (journal) → E (consumer pin), with each phase independently mergeable.

### 1.3 Non-goals

- This PR does **not start implementation** (design only).
- Rust migration is out of scope for this PR ([#194](https://github.com/suisya-systems/claude-org/issues/194)).
- Evolution to a plugin form (Q12 option C) is also out of scope for this PR ([#195](https://github.com/suisya-systems/claude-org/issues/195)).
- Extracting dispatcher / dashboard is out of scope for this PR (Layer 2 = org-runtime responsibility).

---

## 2. Lead decisions (12 questions)

The 12 questions presented to the Lead in inventory §5.3 are resolved below for this design. Implementation workers should follow these decisions by default.

| # | Question | Decision | Rationale |
|---|---|---|---|
| Q1 | Implementation language | **Python only** (pure-Python package; keep bash hooks) | inventory §5.3-1. Rust would impose large rewrite cost for the 1,160 LOC of bash. Establish separation correctness before optimizing distribution ergonomics. Track Rust separately in #194 |
| Q2 | Permission schema SOT | **A — schema split**: framework schema (type definitions) is owned by core-harness as SOT; org-specific entries remain in claude-org | The only way to solve inventory §5.1-6 (framework rules and org doctrine co-located). Details in §3 |
| Q3 | bash/awk hook dependency | **Keep it** (consistent with Phase 2b decisions) | [phase-2b-guardrails-refactor.md §1](./phase-2b-guardrails-refactor.md) already locked in continuing with awk. No reason to relitigate |
| Q4 | Dependency direction from Layer 1 to claude-org | **A — one-way**: core-harness knows nothing about claude-org. org-shaped hooks (`block-workers-delete.sh`, `block-dispatcher-out-of-scope.sh`, `block-org-structure.sh`) stay in claude-org | Avoids the blockers in inventory §5.1-1 to §5.1-3 by not lifting them. Maximize the OSS value of core-harness |
| Q5 | Hook location (`.hooks/` vs `.claude/hooks/`) | **C — path configurable**: core-harness stays neutral; consumers choose | inventory §5.1-7. claude-org already treats `.hooks/` as canonical (per auto-mirror history in canonical-ownership.md). This also does not block `.claude/hooks/` on the English side |
| Q6 | OSS publication timing | **A — bootstrap empty repo first** + design PR (this PR). Implementation (Steps B-D) in weeks 7-12 | inventory §5.3-6. Bootstrap is being done today in parallel by another worker. Lock the contract first so implementation PRs all target an approved design |
| Q7 | Test migration scope | **B**: tests that depend on org strings such as `test-check-worker-boundary.sh` stay in claude-org. core-harness keeps generic hook framework tests (exit code / stdin/stdout contract) | Details in §5. inventory §5.3-7 |
| Q8 | CI structure | **A — via shim**: convert `tools/check_role_configs.py` into a thin CLI shim that calls `from core_harness import ...` internally. Leave CI scripts unchanged | Details in §6. Minimize the cost of not breaking claude-org CI |
| Q9 | semver policy | **C — start pre-1.0 and define 1.0 promotion conditions up front** (same style as renga, but define conditions in the initial version) | Details in §7.1. The schema says `version: 1`, but the migration story is still undefined. Allow breaking changes in pre-1.0, then cut 1.0 once conditions are met |
| Q10 | Distribution method | **A — GitHub Release only**: during pre-1.0, use `pip install git+https://github.com/suisya-systems/core-harness@v0.x.y`. Publish to PyPI at 1.0 | inventory §5.3-10. Little reason to claim a PyPI namespace during pre-1.0, and cleanup is hard, so defer it |
| Q11 | Dispatcher / journal scope | **B**: dispatcher stays in claude-org; **only the journal API is provided by core-harness** (Layer 1 audit primitive) | Details in §3.4. `dispatcher_runner.py` belongs to org-runtime; journal append/iter is a raw primitive |
| Q12 | Plugin / slot interface | **B — library-provided approach**: org-runtime assembles the full schema, and core-harness provides `roles{}` / `worker_roles{}` type definitions plus validator and generator as a library. Revisit evolution to C (schema merger) when Layer 2 work starts | Details in #195. Keep the surface minimal for now |

---

## 3. Concrete schema split (implementation of Q2)

This is the answer to the problem called out in inventory §5.1-6: framework rules and org doctrine live in the same schema today. **Boundary criterion**: "Can an external org create and validate schema using core-harness alone?" If yes, it is framework. If no, it is org-specific.

### 3.1 Framework schema (core-harness owns the SOT)

Provide the following **type definitions** as `core_harness.schema.framework_schema_v0` (module constants / JSON Schema). core-harness owns only the structure, not concrete values (paths / commands / role names).

| Concept | What core-harness owns | Notes |
|---|---|---|
| `forbidden_allow_exact` / `forbidden_allow_regex` | **Type definitions only** (semantics of `list[str]` + match algorithm) | Concrete patterns are injected by the org. Example: `"Bash(git *)"` is claude-org policy and not needed by the framework |
| `required_hook_scripts[]` | **Type definitions + integrity-check logic** ("must be referenced by at least one `required_hooks[].command_contains`"). In addition, core-harness exposes **recommended defaults** for generic ban patterns: `block-no-verify.sh` and `block-dangerous-git.sh` | Concrete hook names such as `block-workers-delete.sh` are not framework concerns |
| `roles{}` schema | **Structural definition** of role entries (`required_allow`, `required_deny`, `disallow_allow_regex`, `closed_world` flag, `required_hooks[]`, `settings_paths[]`, `docs_section`) | Does not include concrete role names such as `secretary`, `dispatcher`, etc. |
| `worker_roles{}` schema | **Structural definition** of worker templates (`permissions{allow,deny}`, `hooks{PreToolUse[]}`, `env{}`, placeholders `{worker_dir}` / `{consumer_root}` / `{core_harness_path}`; org-specific alias `{claude_org_path}` is resolved on the claude-org side) | Does not include concrete template names such as `default`, `claude-org-self-edit`, `doc-audit` |
| Hook framework wire-up contract | **exit code / stdin / stderr contract**: `exit 0` allow / `exit 2` + stderr deny / stdin = PreToolUse JSON / extract `.tool_name` and `.tool_input.command` | Formalizes the de facto contract from inventory §3.2 |
| Generic deny library | `lib/segment-split.sh` family (`split_segments`, `flatten_substitutions`, `collect_assignments`, `expand_known_vars`, `unwrap_eval_and_bashc`) + `lib/path-normalize.sh` (new; currently duplicated across four hooks) | inventory §2.2 / §3.4 |
| Generic deny hooks | `block-no-verify.sh` / `block-dangerous-git.sh` / `check-worker-boundary.sh` (version with org strings externalized via env) | inventory §3.4 |
| Schema validator engine | `validate_config()` / `validate_schema_integrity()` / `closed_world` calculation / `disallow_allow_regex` / placeholder matching (`{worker_dir}` capture) | The **logic layer** from current `tools/check_role_configs.py`. The CLI shim stays in claude-org |
| Generator | `generate_worker_settings()` function (placeholder substitution + `description`/`$comment` stripping) | Current `tools/generate_worker_settings.py` |
| `settings.local.override.json` contract | Semantics of the sibling escape hatch (the override `allow` set is excluded from closed-world checks) | inventory §1.4 |
| Journal event-line schema | Append-only JSONL contract + `ts` (ISO-8601 UTC) + `event` (string) + arbitrary keyset. Reader skips malformed lines and blank lines | inventory §4 overall |
| Journal API | `journal.append(event_type, **fields)` + `journal.iter(path)` | inventory §4.5 |

### 3.2 Org-specific schema (stays in claude-org)

The following are **claude-org organizational policy**, not things external orgs need when adopting core-harness. They therefore stay in claude-org's `tools/role_configs_schema.json` (or its successor file).

| Concept | Concrete values (examples) | Why it stays on the claude-org side |
|---|---|---|
| Role catalog | `secretary`, `dispatcher`, `curator`, `worker`, `repo_shared`, `user_common` | Core claude-org doctrine. Other orgs may choose different role splits |
| `secretary.required_allow` 38 entries | `Bash(gh issue:*)`, `Bash(codex exec:*)`, `mcp__renga-peers__*`, etc. | Tied to the claude-org-specific concept of the Lead |
| `^mcp__claude-peers__` ban list | 1 entry in `forbidden_allow_regex` | claude-peers (now renga-peers) is the predecessor MCP server to renga. Banning it is claude-org policy, not a framework default |
| Org-structure name list | the six names `.dispatcher/`, `.curator/`, `.state/`, `registry/`, `dashboard/`, `knowledge/` | inventory §5.1-3. The contents of the `ALWAYS_BLOCKED` + `ROOT_ONLY_BLOCKED` arrays in `block-org-structure.sh` |
| Workers-dir concept | `workers_dir:` line in `registry/org-config.md` | Required by `block-workers-delete.sh`. "Do not delete workers in bulk" is claude-org-specific |
| Dispatcher write allowlist | `.dispatcher/`, `.state/`, `knowledge/raw/<YYYY-MM-DD>-<kebab>.md` | Policy from `block-dispatcher-out-of-scope.sh`. "Dispatcher may write only a narrow path set" is claude-org-specific |
| Org-shaped hook bodies | `block-workers-delete.sh` (109 LOC), `block-dispatcher-out-of-scope.sh` (108 LOC), `block-org-structure.sh` (154 LOC), `block-git-push.sh` (51 LOC) | Each depends on one of the org-specific concepts above |
| Concrete `worker_role` names | `default`, `claude-org-self-edit`, `doc-audit` | Template names operated by claude-org. core-harness provides types only |
| `permissions.md` (docs projection) | `.claude/skills/org-setup/references/permissions.md` | Lives inside the claude-org skill and uses Japanese headings (`## 窓口`, etc.) as `docs_section` markers. core-harness provides the **projection mechanism**, but the **document itself** stays in claude-org |
| Japanese deny reason for `secretary` | string literals such as `echo "ブロック: …" >&2` | Localization is in claude-org scope. core-harness defines only the **format contract** for deny reasons; the strings are chosen by the org |

### 3.3 Boundary criterion (restated)

> **"core-harness alone must let an external org create and validate schema."**

Applying that mechanically yields:

- "Does core-harness own `block-workers-delete.sh`?" → **No**. It reads `registry/org-config.md`, which is a claude-org-specific file.
- "Does core-harness own `block-no-verify.sh`?" → **Yes**. External orgs likely also want to stop `git commit --no-verify` (generic git safety).
- "Does core-harness know the role name `secretary`?" → **No**. The Lead concept belongs to claude-org doctrine.
- "Does core-harness know `closed_world: bool` in the `roles{}` schema?" → **Yes**. That is a framework primitive: one form of audit constraint.

### 3.4 Journal responsibility split (Q11)

| Layer | Owns |
|---|---|
| **core-harness** (Layer 1) | (a) append-only contract for `journal.jsonl`, (b) reader tolerance for malformed and blank lines, (c) minimal API `append_event(event_type, **fields)` + `iter_events(path)`, (d) minimal envelope that requires only `ts` (ISO-8601 UTC) and `event` (string) |
| **claude-org** (Layer 4 / future Layer 2) | (a) catalog of 35 event types (`worker_spawned` / `pr_merged` / etc.), (b) per-event field contract (currently scattered across `org-delegate/SKILL.md`, etc.), (c) writer calls from dispatcher / Lead skills, (d) dashboard reader (`dashboard/server.py` reads `org-state.json`, so it is separate from the journal path) |

Key point: **core-harness owns "how to write"; claude-org owns "what to write."** Consistent with inventory §4.5.

---

## 4. Migration phasing (final version of the Section 6 worker first cut)

This finalizes the phase split from inventory §6, updated to reflect the Lead decisions in this design. Each step must be mergeable as an independent PR, and claude-org CI must pass at the end of each step.

### Step A — bootstrap empty repo

- **Scope**: create empty repo `suisya-systems/core-harness`
- **Deliverables**: README + LICENSE (MIT, aligned with claude-org) + CI skeleton (pytest + ruff + bash test runner) + `pyproject.toml` (`name = "core-harness"`, `version = "0.0.0"`) + placeholder `CONTRIBUTING.md`
- **Dependencies**: none
- **Status**: in progress today (2026-05-02) by a parallel worker
- **AC**: `pip install -e .` succeeds for an empty package, CI green

### Step B — migrate permission schema + generator + validator

- **Scope**:
  - Split `tools/role_configs_schema.json` into **two files** (addresses inventory §5.2-1):
    - `core_harness/schemas/role_audit_schema.json` (framework: `roles{}` structure + `forbidden_allow_*` types + `required_hook_scripts[]` type + `disallow_allow_regex` type)
    - `core_harness/schemas/worker_role_templates_schema.json` (framework: `worker_roles{}` structure + placeholder spec)
  - Move `tools/generate_worker_settings.py` to `core_harness.generator.generate_worker_settings`
  - Move the **logic layer** from `tools/check_role_configs.py` to `core_harness.validator.validate_config` / `validate_schema_integrity`
  - Normalize placeholders to **neutral naming** (addresses inventory §5.2-6):
    - placeholders defined by the framework: `{worker_dir}`, `{consumer_root}` (= generalized form of old `{claude_org_path}`), `{core_harness_path}` (new; core-harness install location)
    - org-specific placeholder alias: claude-org may keep using `{claude_org_path}` as an alias for `{consumer_root}` (migration path to be defined in a Step B sub-issue)
  - **`required_hook_scripts[]` enumeration stays on the org side**: the reduced claude-org schema must explicitly keep at least these seven entries so `validate_schema_integrity()` can cross-check that they are referenced from `roles[*].required_hooks[].command_contains`:
    - org-specific (bodies also stay in claude-org): `block-git-push.sh`, `block-workers-delete.sh`, `block-org-structure.sh`, `block-dispatcher-out-of-scope.sh`
    - generic (bodies move into core-harness; references still remain in claude-org): `block-no-verify.sh`, `block-dangerous-git.sh`, `check-worker-boundary.sh`
- **claude-org-side changes**:
  - Reduce `tools/role_configs_schema.json` to **org-specific entries only** (concrete role names + `secretary.required_allow` 38 entries + `^mcp__claude-peers__` ban + `worker_roles{default,claude-org-self-edit,doc-audit}`). Declare `"$framework_schema_ref": "core-harness==0.1.0"` at the top (exact pin, §7.1)
  - Reduce `tools/check_role_configs.py` to a **thin CLI shim** (argparse + `from core_harness.validator import validate_config` + preserve current exit-code contract)
  - Do the same for `tools/generate_worker_settings.py`
- **Dependencies**: Step A
- **AC**:
  - `pytest tests/test_check_role_configs.py tests/test_generate_worker_settings.py` is green on the claude-org side
  - `pytest tests/test_validator.py tests/test_generator.py` (new unit tests) is green on the `core-harness` side
  - existing CLI entry points such as `bash scripts/install-hooks.sh` run unchanged

### Step C — migrate hook framework

- **Scope**:
  - Move `.hooks/lib/segment-split.sh` (325 LOC) to `core_harness/hooks/lib/segment-split.sh`
  - Add new `core_harness/hooks/lib/path-normalize.sh` and consolidate the duplicated `portable_realpath` / `normalize_slashes` / `normalize_drive_letter` logic currently repeated across four hooks (`check-worker-boundary.sh`, `block-org-structure.sh`, `block-dispatcher-out-of-scope.sh`, `block-workers-delete.sh`) (inventory §5.2-4)
  - Move **generic deny hooks** `block-no-verify.sh`, `block-dangerous-git.sh`, `check-worker-boundary.sh` into `core_harness/hooks/`. Refactor `check-worker-boundary.sh` so org-specific write allowlists (`<CLAUDE_ORG_PATH>/knowledge/raw/...`, etc.) are supplied via env var `EXTRA_WRITE_ALLOWLIST_GLOBS`
  - Formalize the hook framework wire-up contract as `core_harness/docs/hook-contract.md` (exit code / stdin JSON / stderr format)
- **claude-org-side changes**:
  - Rewrite `worker_roles[*].hooks` `command` strings to `bash "{core_harness_path}/hooks/<script>"` for generic hooks only. Org-specific hooks (`block-org-structure.sh`, `block-git-push.sh`, etc.) still point at `{claude_org_path}/.hooks/...`
  - `.hooks/` keeps the org-specific hooks (`block-workers-delete.sh`, `block-dispatcher-out-of-scope.sh`, `block-org-structure.sh`, `block-git-push.sh`) plus `test-always-block.sh` for the test harness
- **Dependencies**: Step B (requires `{core_harness_path}` placeholder to already exist on the schema side)
- **AC**:
  - all eight existing hook tests are green on the claude-org side (the tests themselves remain there per §5)
  - hook framework tests (exit-code + stdin/stderr contract) are newly added and green on the core-harness side

### Step D — extract journal API

- **Scope**:
  - `core_harness.journal.append_event(path, event_type, **fields)` (Python)
  - `core_harness.journal.iter_events(path)` (Python; skip malformed and blank lines)
  - bash one-liner equivalent: `core_harness/journal/append.sh` (wrap `printf '%s\n' "$json" >> "$path"` with `flock`)
  - duplicate the reader-tolerance test fixture from `tests/fixtures/journal-sample.jsonl` (includes a `not-valid-json` line)
- **claude-org-side changes**:
  - switch the "append via `Bash`" flow around line 63 of `dispatcher/CLAUDE.md` to go through the helper (do not change dispatcher permissions; only change the call target)
  - rewrite writer calls in `org-suspend/SKILL.md`, `org-resume/SKILL.md`, `org-delegate/SKILL.md`, and `org-start` to go through the helper
  - **event type catalog stays in claude-org**. Recommend adding `docs/journal-events.md` to collect all 35 event types (not part of Step D AC, but a likely follow-up issue)
- **Dependencies**: Step A (can merge independently of Steps B/C)
- **AC**:
  - `tests/test_parsers.py` is green on the claude-org side
  - `tests/test_journal.py` (append + iter + malformed tolerance) is newly added and green on the core-harness side

### Step E — draft PR to pin core-harness as a dependency of claude-org

- **Scope**:
  - exact pin in `requirements/core-harness.txt` (§7.1 / Q10): `core-harness @ git+https://github.com/suisya-systems/core-harness@v0.1.0` (during pre-1.0, do not publish to PyPI, so keep the fixed git URL in a requirements file rather than `pyproject.toml` `dependencies`)
  - add `pip install -r requirements/core-harness.txt` to `.github/workflows/tests.yml`
  - verify in CI that the shim CLIs still pass while calling the core-harness API
- **Dependencies**: Steps B + C + D complete
- **AC**: satisfies the #128 requirement for a "draft PR replacing dependencies"

### Phasing diagram

```
Step A (bootstrap)
  ├── Step B (schema)
  │     └── Step C (hooks)  ← depends on Step B placeholder definitions
  │           └── Step E (consumer pin)
  └── Step D (journal)  ← depends only on Step A; can run in parallel with B/C
```

**Estimated effort** (rough, subject to Lead retuning): A small / B medium / C medium / D small / E medium-large (CI + draft PR review cycles).

---

## 5. Test strategy (Q7 B)

Distribute the 12 test files from inventory Appendix as follows.

### 5.1 Tests to move into core-harness

| File | Destination after migration | Why |
|---|---|---|
| `tests/test_generate_worker_settings.py` | `core_harness/tests/test_generator.py` | Pure generator logic. No org-string dependency |
| `tests/test_parsers.py` (journal-sample portion) | `core_harness/tests/test_journal.py` | Verifies malformed-line tolerance in the journal reader |
| `tests/test-block-pretooluse-hooks.sh` (generic portion) | `core_harness/tests/test-pretooluse-contract.sh` | Verifies exit code / stdin / stderr contract. Move only the parts that do not depend on org strings |
| `tests/test-unwrap-eval-bashc.sh` | `core_harness/tests/test-unwrap-eval-bashc.sh` | Focused test of `unwrap_eval_and_bashc` in `lib/segment-split.sh`. Generic |

### 5.2 Tests to keep in claude-org

| File | Why it stays |
|---|---|
| `tests/test-check-worker-boundary.sh` | Path allowlist includes org-specific globs such as `knowledge/raw/...`. core-harness should have only the contract test that env can supply allowed paths; claude-org keeps the end-to-end test with env populated |
| `tests/test-block-workers-delete.sh` | Resolves `workers_dir` from `registry/org-config.md` + depends on claude-org doctrine |
| `tests/test-block-dispatcher-out-of-scope.sh` | Depends on org names such as `.dispatcher/` and `.state/` |
| `tests/test-block-git-push.sh` | "Workers do not push" is an org rule |
| `tests/test-block-org-structure.sh` | Depends on eight hardcoded directory names |
| `tests/test-install-hooks.sh` | `scripts/install-hooks.sh` (precommit secret scanner, claude-org operation) |
| `tests/test-precommit-secret-scanner.sh` | Same |
| `tests/test_check_role_configs.py` (org-specific assertion portion) | The part that verifies the 38 entries for the `secretary` role stays in claude-org. core-harness gets new unit tests for the validator **engine** only |

### 5.3 New tests to add in core-harness

- `tests/test_validator.py`: unit tests for `closed_world`, `disallow_allow_regex`, placeholder matching, and schema integrity (use synthetic role schema fixtures; do not bring in claude-org strings)
- `tests/test_generator.py`: verify placeholder substitution and `$comment` stripping with fixture roles
- `tests/test_journal.py`: append + iter + malformed tolerance + `flock` exclusion
- `tests/test-pretooluse-contract.sh`: verify "`exit 0` allows / `exit 2` + stderr denies / other tools return `exit 0` (out of scope)" using fake hooks
- `tests/test-segment-split.sh`: move fixtures from claude-org and verify `split_segments`, `flatten_substitutions`, `expand_known_vars`

---

## 6. CI strategy (Q8 A)

### 6.1 Invariants for claude-org-side CI

Preserve **full CLI compatibility** for `tools/check_role_configs.py` and `tools/generate_worker_settings.py`. Specifically:

- keep exit-code semantics unchanged (0 = OK, 1 = validation failure, 2 = usage error)
- keep stdout format unchanged (current `[OK] role: ...` / `[FAIL] role: ...`)
- keep existing flags such as `--include-local`, `--include-worker-settings`, `--role`, `--out`, `--schema`

This lets existing steps in `.github/workflows/tests.yml`, local `make check` equivalents, and bash launches inside skills continue to run **unchanged**.

### 6.2 Shim implementation pattern

```python
# tools/check_role_configs.py (Step B 後)
from core_harness.validator import validate_config, validate_schema_integrity, ValidationError
from core_harness.cli import build_check_argparser  # CLI surface も core-harness が提供

def main():
    parser = build_check_argparser()
    args = parser.parse_args()
    schema = load_org_schema(args.schema or "tools/role_configs_schema.json")
    framework_schema = load_framework_schema_pinned()  # core-harness 同梱
    merged = merge(framework_schema, schema)  # org が framework を inject
    try:
        validate_schema_integrity(merged)
        for role in merged["roles"]:
            validate_config(merged, role, ...)
    except ValidationError as e:
        sys.stderr.write(str(e) + "\n")
        sys.exit(1)
```

### 6.3 CI on the core-harness side

- `pytest tests/` (Python unit tests)
- `bash tests/run-shell-tests.sh` (shell hook tests)
- ruff (lint) + mypy (optional; not strict during pre-1.0)
- matrix: Linux (`ubuntu-latest`) + macOS (`macos-latest`) + Windows (`windows-latest` with Git Bash)
- minimum bash matrix is GNU bash 5.x only. Explicitly declare old macOS default bash 3.2 unsupported (aligned with current claude-org policy)

### 6.4 Compatibility gate

Recommend adding a matrix to claude-org CI to check **whether bumping core-harness breaks the shim** (included in Step E AC):

```yaml
# .github/workflows/tests.yml に追加（Step E）
strategy:
  matrix:
    core_harness_ref: ["v0.1.0", "v0.2.0", "main"]  # main は warning 扱い
```

---

## 7. semver policy and 1.0 promotion conditions (Q9)

### 7.1 Rules during pre-1.0

- operate as 0.x.y; x bump = breaking changes allowed, y bump = bugfix only
- claude-org must use **exact pins only** (`core-harness==0.1.3` equivalent), never `core-harness>=0.1,<1.0`. Raise the pin only after validating the new x version on the claude-org side
- every release must include a **Breaking changes** section in `CHANGELOG.md`

### 7.2 Conditions for 1.0 promotion (explicit from the first version)

Cut 1.0 only once **all three conditions** below are satisfied. This follows the same style as renga staying pre-1.0 for a long time, but avoids the "never reaches 1.0" outcome by making the conditions explicit:

1. **External consumers ≥ 2**: at least two orgs besides claude-org actually adopt core-harness (real repos assembling schema, not just forks/stars)
2. **No breaking changes for the last 2 quarters (6 months)**: no add/remove/rename of schema fields
3. **Distribution channel established**: PyPI publication setup is ready (token management, release workflow)

If any of the three is missing, staying on 0.x is fine. Do not rush 1.0.

### 7.3 Distribution (Q10)

- pre-1.0: GitHub Release only, in the form `pip install git+https://github.com/suisya-systems/core-harness@v0.x.y`
- publish to PyPI at 1.0. Namespace-squat risk is reduced by claiming the namespace just before 1.0
- ship bash hook scripts **inside the Python package** (`core_harness/hooks/*.sh`) and provide a helper (`core_harness.hooks_path()`) that resolves the path via `importlib.resources`. This allows generic resolution in worker-role template `command` strings such as `bash "$(python -m core_harness hooks-path)/check-worker-boundary.sh"`

---

## 8. Open risks

### 8.1 Difficulty of separating schema and doctrine (inventory §5.1)

- the current `tools/role_configs_schema.json` mixes framework and org content in one file, and Step B may **fail to split cleanly into exactly two files**
- example: `closed_world: true` is a framework concept, but the value `closed_world: true` on `secretary` is an org choice
- **mitigation**: in a Step B sub-issue, write a PoC for the minimum surface of the framework schema first, list what is missing, then proceed to the full implementation

### 8.2 Naming / API shape concerns (inventory §5.2)

- placeholders `{worker_dir}` / `{claude_org_path}` are string substitution, not a typed contract (inventory §5.2-6)
- keep them as strings in v0; consider typed Placeholder objects in v1
- the sibling concept in `settings.local.override.json` is poorly named if it is made public (inventory §5.2-7). There is room to rename it to `settings.local.user-extension.json` or similar during pre-1.0

### 8.3 Areas not resolved by the 12 questions

- **ownership of the claude-peers (now renga-peers) ban**: `^mcp__claude-peers__` stays in claude-org for now, but another possible choice would be for core-harness to default-deny all legacy MCP servers unrelated to Anthropic Claude Code. This design fixes it on the claude-org side for now, but external orgs may end up reinventing the same decision
- **`description` / `$comment` strip logic**: it is still unclear whether the generator should use a whitelist or blacklist for schema keys it strips. Lock this down in a Step B sub-issue
- **Windows behavior for bash hooks**: claude-org assumes Git Bash. core-harness should inherit that assumption, but it must be explicitly verified in the CI matrix

### 8.4 Typing the hook contract as a protocol

- inventory §5.2-5: the current `exit 2 + stderr` contract is Claude Code-specific
- if other engines such as codex may call this in the future, another option is to switch stderr to a JSON envelope such as `{"deny": true, "reason": "..."}` 
- keep the current convention during pre-1.0; revisit just before 1.0 (absorb the breaking change at the 1.0 boundary)

---

## 9. Follow-up

This PR does not open these issues itself (decide after Lead review), but the following follow-up work is already recognized as attached to this design:

| Issue | Content | Status |
|---|---|---|
| [#194](https://github.com/suisya-systems/claude-org/issues/194) | evaluate Rust migration for core-harness (deferred by Q1) | already opened |
| [#195](https://github.com/suisya-systems/claude-org/issues/195) | evolve plugin interface from Q12 B → C (schema merger) | already opened |
| (not yet opened) | core-harness 0.1.0 release plan (after Steps B-D complete) | open after Lead decision |
| (not yet opened) | ongoing evaluation of 1.0 promotion conditions (consumer count + breaking-change frequency tracking) | open after Lead decision |
| (not yet opened) | add `docs/journal-events.md` and collect all 35 event types (natural follow-up to Step D) | open after Lead decision |
| (not yet opened) | rename `settings.local.override.json` → `settings.local.user-extension.json` (8.2) | any time during pre-1.0 |

---

## 10. Review items for the PR body (Lead review perspective)

Checklist for reviewers:

- [ ] the table of 12 Lead decisions (§2) does not conflict with any other section
- [ ] the framework / org-specific boundary in §3 satisfies the criterion that an external org can build schema independently
- [ ] Steps A-E in §4 are independently mergeable and each AC is objectively testable
- [ ] the test migration list in §5 covers all 12 files from inventory Appendix
- [ ] the shim strategy in §6 does not break claude-org CI (existing CLI compatibility is preserved)
- [ ] the 1.0 promotion conditions in §7 align with claude-org release conventions as a whole
- [ ] decide whether the risks in §8 must be resolved before starting Step B, or whether implementation can start with this design as-is
---
