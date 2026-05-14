# Next probe iteration proposals (Issue #376 Pre-Phase 0 follow-up)

This spike (Iteration 1) stopped at handcraft profile + checklist + runbook. We present 3 options for **which combination to run as a real-machine probe** at the start of the next iteration. Each option is sized to complete with 1 worker dir + 1 dispatcher pane and can run independently in parallel.

## Proposal A — B1-1 single shot (dispatcher × bypassPermissions × sandbox)

**Goal**: measure whether sandbox fires under `bypassPermissions` operation **in the shortest time**. Resolves the biggest branching point of the Phase 1 schema design.

**Steps (run runbook §3)**:

1. Launch a dispatcher pane and verify cwd is `claude_org_path/.dispatcher/`.
2. Use `/sandbox` to put sandbox status in Enabled (= bubblewrap present).
3. Four attempts: `cat ~/.config/gh/hosts.yml` / `cat ./.env` (dummy placed) / `cat ./creds.pem` (dummy placed) / `echo x >> ~/.claude/settings.json.sandbox-test`.
4. Fill checklist 1.1–1.5.

**Time required**: no worker dir needed; reuses existing dispatcher. 30 min / 1 commit.

**Resulting conclusion**: based on whether all four attempts are denied / all allowed / mixed, the Phase 1 schema dispatcher row design is decided.

**Recommendation**: ★★★ (premise before Phase 1 starts. Top priority).

---

## Proposal B — B2-1 + git-surface bundle (impact range of worker × repo-shared non-inheritance)

**Goal**: confirm in real machine that "worker does not inherit repo-shared", and as a side effect, list **how many dangerous git operations pass through** on the current worker. Fixes the Phase 2 (Issue #379) hook deployment targets.

**Steps (runbook §2, §4 in order)**:

1. Set up a new probe worker dir `sandbox-probe-iter1`.
2. Emit the baseline (current schema) settings.local.json via `claude-org-runtime settings generate --role default`.
3. Measure checklist 2.1–2.5 (B2-1).
4. Continue with checklist 5.1–5.5, 5.8 (git-surface, history-destruction family).
5. Apply `profiles/profile-baseline.json`, restart Claude Code.
6. Re-run the same rows and confirm they turn into deny.
7. Apply `profiles/profile-tightened.json` and confirm that the `git -C` form (5.8, 5.9) is also denied.

**Time required**: 1 probe worker dir + 3 Claude Code restarts. 1–1.5 hr / 1–2 commits.

**Resulting conclusion**:
- Validates the design of adding `block-dangerous-git.sh` / `block-no-verify.sh` to the worker schema in Phase 2.
- Demonstration of whether the `git -C <other>` form is caught by the hook (decision input on whether hook extension is needed).
- Whether baseline → tightened diff results in "the expected defense hardening" (including absence of regressions).

**Recommendation**: ★★★ (premise before Phase 2. Can run independently in parallel with Proposal A).

---

## Proposal C — secrets denyRead focus (separating sandbox failIfUnavailable from claude-builtin protection)

**Goal**: isolate which of the 3 layers (perms `Read()` deny / sandbox `denyRead` / claude-builtin) stops the secret denyRead. Input for the Phase 3 environment-specific matrix + decision material for whether to add `Read()` deny in Phase 2.

**Steps**:

1. Reuse probe worker dir `sandbox-probe-iter1` (after Proposal B).
2. Measure checklist 7.1–7.6 against the baseline (= current worker schema).
3. Place 3 dummy secrets: `.env`, `~/.config/gh/hosts.yml` (skip if a real one exists in the environment), `worker_dir/creds/credentials.json`.
4. Record which rows are denied / which pass under baseline.
5. Apply `profile-tightened.json` (Read() deny + sandbox denyRead double), restart Claude Code.
6. Re-run the same rows and observe which layer newly turns deny (check status with `/sandbox` each time).
7. Try `failIfUnavailable: true` (fail-closed) in a separate file and observe startup failure in environments lacking bubblewrap (Phase 3 input).

**Time required**: 30–45 min / 1 commit if you reuse Proposal B's worker dir. `failIfUnavailable: true` experiment is recommended in a separate worker dir (under the premise that startup will fail).

**Resulting conclusion**:
- Demonstrate whether claude-builtin actually protects `~/.ssh` / `~/.aws`.
- Demonstrate whether the sandbox layer alone can protect `~/.config/gh/hosts.yml` (design decision in Phase 2 between adding `Read()` deny and pushing it to sandbox).
- One sample of behavior at fail-closed switching (first entry in the Phase 3 matrix).

**Recommendation**: ★★ (design input for Phase 2/3. Most efficient after Proposal B is complete, but independent is also OK).

---

## Recommended execution order

1. **Proposal A** (B1-1) — top priority as a prerequisite for Phase 1 schema design. No worker dir needed; reuses existing dispatcher.
2. **Proposal B** (B2-1 + git-surface) — prerequisite for Phase 2 hook deployment design. Set up a new worker dir.
3. **Proposal C** (secrets) — reinforcement for Phase 2/3. Reusing Proposal B's worker dir is efficient.

All 3 fill the corresponding rows in `probes/checklist.md`, and if there are surprises, add new rows to the next iteration. The harness from this spike (`probes/`, `profiles/`, `docs/sandbox-probe-runbook.md`) can be reused as-is.
