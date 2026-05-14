# sandbox-probe (Issue #376 epic Pre-Phase 0 spike)

This brings the deliverables of the **Pre-Phase 0 spike** of the Issue #376 epic (original commit: 198576c of `workers/sandbox-probe/`, by the `sandbox-probe-pre-phase-0-b1-b2` worker) into this repository.

The spike's goal was to fix a **harness** (checklist / profile / runbook) that lets the following two Blockers raised in audit-issue-376-2026-05-09 be reproduced via a real-machine probe. Executing the real-machine probes themselves was outside the scope of this spike; the probe-worker for the next iteration takes that over.

- **B1-1**: whether dispatcher × `bypassPermissions` × sandbox fires (Issue #377)
- **B2-1**: inheritance status of the repo-shared `.claude/settings.json` to the worker (Issue #379)

Related Issues: #376 (epic) / #377 (Phase 0) / #378 (Phase 1 schema) / #379 (Phase 2 hooks) / #380 (Phase 3 environment-specific fail policy).

## Directory layout

```
docs/sandbox-probe/
├── README.md                        ← this file
├── notes/
│   ├── sandbox-probe-runbook.md     ← real-machine probe reproduction steps (B1-1 / B2-1)
│   ├── baseline-observations.md     ← facts fixed by static analysis alone
│   └── next-iteration-proposals.md  ← 3 options for the next iteration (A: B1-1 single / B: B2-1+git-surface / C: secrets)
├── probes/
│   ├── README.md                    ← probe-worker operational rules
│   ├── categories.md                ← background and intent of the 7 categories
│   └── checklist.md                 ← 5-column checklist (category / attempted / expected / observed / conclusion)
└── profiles/
    ├── README.md                    ← positioning and application method of the handcraft profiles
    ├── profile-baseline.json        ← minimum defense (Pattern A worker assumed)
    └── profile-tightened.json       ← hardened version (git -C form deny / sandbox denyWrite extension / etc.)
```

> The original spike worker placed runbook / observations / proposal memos in a `docs/` subdirectory. When bringing it into this repo, we renamed it to `notes/` to avoid the doubled `docs` of `docs/sandbox-probe/docs/`. At the time of the initial commit (5ee1089), all 9 files have unchanged bodies (sha256 matches the original commit 198576c). The subsequent round1 self-review fix commit (ffe15d6) edits `notes/sandbox-probe-runbook.md`, `probes/checklist.md`, `probes/README.md`, and `profiles/README.md` for safety / terminology clarification (see that commit message for details). Original commit reference: `git -C /home/$USER/work/org/workers/sandbox-probe show 198576c --stat`.

## Reading order

1. [`docs/sandbox-probe/notes/baseline-observations.md`](./notes/baseline-observations.md) — understand what is **fixed by static analysis alone** and what still awaits real-machine verification
2. [`docs/sandbox-probe/probes/categories.md`](./probes/categories.md) — which audit finding each probe category corresponds to
3. [`docs/sandbox-probe/probes/checklist.md`](./probes/checklist.md) — the list of rows to fill with the real-machine probe (all rows are "untested" at this spike's point in time)
4. [`docs/sandbox-probe/notes/sandbox-probe-runbook.md`](./notes/sandbox-probe-runbook.md) — reproduction steps for filling the checklist on real machines
5. [`docs/sandbox-probe/profiles/README.md`](./profiles/README.md) → [`docs/sandbox-probe/profiles/profile-baseline.json`](./profiles/profile-baseline.json) / [`docs/sandbox-probe/profiles/profile-tightened.json`](./profiles/profile-tightened.json) — the handcraft profiles for comparison
6. [`docs/sandbox-probe/notes/next-iteration-proposals.md`](./notes/next-iteration-proposals.md) — which combination to prioritize in the next iteration (3 options A/B/C)

## Placeholders inside the profile JSON

`profiles/profile-baseline.json` and `profiles/profile-tightened.json` are supersets of the worker `.claude/settings.local.json`, but as handcraft candidates intended to be **written back to the worker manually** rather than emitted by `claude-org-runtime settings generate`, they retain environment-specific paths as placeholders:

| placeholder | meaning | example substitution value |
|---|---|---|
| `{worker_dir}` | the cwd of the worker running the probe (Pattern A) | `/home/$USER/work/org/workers/sandbox-probe-iter1` |
| `{claude_org_path}` | the clone path of claude-org-ja (where the hooks and repo-shared `.claude/settings.json` live) | `/home/$USER/work/org/claude-org-ja` |

Example substitution at real-machine verification time (the same flow as §4 of [`docs/sandbox-probe/notes/sandbox-probe-runbook.md`](./notes/sandbox-probe-runbook.md)):

```bash
sed -i "s|{worker_dir}|/home/$USER/work/org/workers/sandbox-probe-iter1|g; \
        s|{claude_org_path}|/home/$USER/work/org/claude-org-ja|g" \
       /home/$USER/work/org/workers/sandbox-probe-iter1/.claude/settings.local.json
jq empty /home/$USER/work/org/workers/sandbox-probe-iter1/.claude/settings.local.json
```

## Operational assumptions of this spike (important)

- **This spike does not run real-machine probes**. The "observed result" / "conclusion" columns of `probes/checklist.md` are left as "untested" / "—" for every row. The probe-worker of the next iteration fills them.
- Verification depth is minimal. fmt/lint are not run; the profile JSON is only syntax-checked via `jq empty`.
- The handcraft profiles all keep `sandbox.failIfUnavailable: false` (a verification loop cannot run if startup fails in a WSL2 environment without bubblewrap installed). The decision to switch to fail-closed is a separate Phase 3 (Issue #380) decision.
- Having the profiles auto-emitted by `claude-org-runtime settings generate` will become possible only after Phase 1 (Issue #378) adds a `sandbox` field to `role_configs_schema.json`. The bundled schema at this spike's point in time has no `sandbox` field.

## Related resources

- audit-issue-376-2026-05-09.md (detailed indications of B0/B1/B2/B3) — outside the claude-org-ja repo: `<workers-root>/claude-org-ja/tmp/audit-issue-376-2026-05-09.md`
- [`docs/verification.md`](../verification.md) §sandbox real-machine verification (bubblewrap/socat prerequisites and current verification procedure)
- [`docs/worker-permissions-design.md`](../worker-permissions-design.md) (design notes on sandbox `additionalDirectories`)
- [`tools/org_extension_schema.json`](../../tools/org_extension_schema.json) (`worker_roles` and `forbidden_allow_exact`)
