# Phase 3: Sandbox Bootstrap Policy Design (~/.aws/.env deny-map fragility)

**Refs**: Issue #376 (epic) / Issue #392 (Phase 3 implementation). Separate scope from #380 (Linux runbook).
**Branch**: `feat/sandbox-bootstrap-policy-design`
**Date**: 2026-05-09
**Scope**: design (writeup only). Implementation is outside this worker's responsibility and is taken over by a follow-up worker after user judgment.
**Predecessor**: residual items of [`docs/sandbox-probe/notes/iteration-b-round3-results.md`](./notes/iteration-b-round3-results.md) §6, §7.2, §8 (denyRead/denyWrite under symlink breaks sandbox bootstrap)

## 1. Background

In iteration B round 3, when adding `~/.aws/**` / `~/.ssh/**` to `sandbox.filesystem.denyRead` / `denyWrite` of `profile-tightened.json`, we confirmed that in the WSL environment (`~/.aws` is a symlink to `/mnt/c/Users/<windows-user>/.aws`) **the entire sandbox startup fails with `bwrap` exit=1**. In round 3's observation, the principal cause was an error during tmpfs mount (`Can't mount tmpfs on /newroot/home/<user>/.aws`), but in this session (worktree `feat/sandbox-bootstrap-policy-design`), even a profile that narrows deny targets to **individual file enumeration** (`<home>/.aws/.env`, `<home>/.aws/config`, `<home>/.aws/credentials`, `<home>/.aws/sso`) reproduces a state where all sandboxed Bash exits with exit=1 due to a different form of bwrap error:

```text
$ pwd
bwrap: Can't create file at <home>/.aws/.env: No such file or directory
exit=1
```

In other words, the naive workaround "expand wildcard into a file-list to avoid it" does not work. Phase 3 needs to decide **at what layer / how policy-driven** this family of bootstrap failures should be rescued.

## 2. Reproduction (real-machine confirmation in this session)

| item | value |
|---|---|
| Platform | WSL2 (Linux 6.6.87.2-microsoft-standard-WSL2) |
| `~/.aws` | symlink → `/mnt/c/Users/<windows-user>/.aws` (Windows directory on the host side) |
| `~/.aws/.env` | exists on the host (regular file, 35 bytes; accessible via symlink) |
| `~/.ssh` | regular directory (not a symlink) |
| Sandbox `denyOnly` (read) | individual file enumeration (10 entries including `~/.aws/.env`, `~/.aws/config`, `~/.aws/credentials`, `~/.aws/sso`) |
| Observed error | `bwrap: Can't create file at <home>/.aws/.env: No such file or directory`, exit=1 |
| Impact range | **all Bash commands** going through sandbox immediately fail (regardless of deny target) |
| Workaround | `dangerouslyDisableSandbox: true` is required (this doc was also authored entirely under this workaround) |

`bwrap` constructs mounts like `--bind /dev/null <target>` or `--ro-bind <empty> <target>` against deny targets. When trying to **create the new** mount target `<home>/.aws/.env` inside the sandbox namespace, it resolves the parent path `<home>/.aws`; the symlink destination `/mnt/c/Users/<windows-user>/.aws` is not bind-mounted inside the new namespace (`/mnt/c` is not included in the sandbox read allowlist), so parent resolution fails and the operation fails.

This behavior has **the same root cause** for both wildcard form (`~/.aws/**`) and file-list form:

- Wildcard form → tries to deny the whole `~/.aws` as tmpfs, and the tmpfs mount itself fails.
- File-list form → fails when resolving the parent during bind-target creation for individual file deny.

## 3. Root cause (fixed)

The direct cause is that **bwrap's deny mapping requires "a parent dir that is a real directory" inside the sandbox namespace, while the host-side `~/.aws` is a dangling symlink (target is not bound inside the sandbox view)**. This is fixed as a composition of the following three factors:

1. **WSL convention of `~/.aws` symlink** — the practice of mapping `/home/$USER/.aws → /mnt/c/Users/$USER/.aws` to share Windows-side AWS CLI config with WSL is common among WSL users. It does not occur in other environments of this repository (Linux native).
2. **Spec that bwrap's deny mechanism requires "a real directory whose target's parent is resolvable inside the namespace"** — `--bind` / `--ro-bind` try to create the target if it does not exist, but if the parent is a symlink and the target is not bound, creation fails. Not a bug, but the spec.
3. **Claude Code sandbox runtime does not pre-resolve the parent of deny entries** — the current implementation transcribes the profile directly into bwrap arguments. Symlink detection / parent-dir mount strategy is not built in.

If any of the 3 is removed, the symptom does not appear. From a policy standpoint, **since (2) is an external spec that cannot be moved**, either (1) or (3) (or both) must be absorbed via policy.

### Related but excluded phenomena

- Fall-open on bwrap-absent environments (`failIfUnavailable`) → separate from this symptom. Confirmed in round 3 §6 that "bootstrap failure is not converted to fall-open". Setting `failIfUnavailable` to `true` cannot rescue this symptom (in fact makes it worse).
- Credential leakage itself → in rounds 2 / 3, the stdout output of `cat ~/.aws/.env` via the sandbox is **empty even under this symptom** (because bwrap immediately fails, nothing gets to stdout). So in the "whether credentials are leaked" view, this symptom **falls on the inconvenient side, not the unsafe side**. The problem is that "all normal commands via the sandbox are caught up and fail".

## 4. Candidate policies (5 options)

### 4.1 Option A — Skip + warn at profile-gen by symlink-aware inspection

**Summary**: at `claude-org-runtime settings generate` or profile-application time, inspect each entry in `sandbox.filesystem.denyRead` / `denyWrite` for **whether its parent path is a symlink on the host side**. If the symlink destination is not in the sandbox's read allowlist, **exclude** that entry from the output profile and **emit a structured warning to stderr / journal**.

**Pros**:

- Minimum implementation (runtime side only; bwrap is not touched).
- Causes no startup failure; other deny entries / other Bash commands are not affected.
- The fact that "deny written in the profile may not be in effect" is visualized as a warning.

**Cons**:

- The deny effect for the target entry becomes a **silent fall-open** (risk of overlooking the warning).
- Hazard that users believe "`~/.aws/**` is protected" without reading the warning.
- Profiles relying solely on the sandbox layer for credential protection get an effective hole.

**Mitigations**:

- profile-tightened already double-defines with `permissions.deny`'s `Read(~/.aws/*)` ([`profile-tightened.json:52-53`](./profiles/profile-tightened.json)). With Layer 2 (perms.deny) alive, skipping Layer 3 (sandbox denyRead) is within acceptable range.
- Claude Code built-in credential redaction remains as Layer 1.
- Include in the Phase 3 spec the convention that warnings are appended as `sandbox_deny_skipped` events, one line each, to `.state/journal.jsonl`.

### 4.2 Option B — Catch bwrap startup failure during bootstrap and retry-prune entries

**Summary**: when bwrap returns errors like "Can't create file at X" / "Can't mount tmpfs on Y" during sandbox bootstrap, **delete the relevant entry and re-start bwrap**. Within a retry budget (e.g. 5 times), if successful, start; if exceeded, fail-closed or fall-open per policy.

**Pros**:

- Absorbs environment differences on the runtime side without touching the profile.
- Unlike option A, works generically for non-symlink causes (permissions, missing files, etc.).
- Retry logs preserve what could not be denied on real machines.

**Cons**:

- Depends on parsing bwrap stderr strings (breaks when bwrap version bumps).
- Startup cost multiplies by retry (worst case, 5 starts).
- The silent fall-open hazard has the same root as option A.

### 4.3 Option C — Resolve the symlink at profile-gen and rewrite the deny destination

**Summary**: entries like `~/.aws/.env` are `realpath`-resolved at profile-gen and rewritten to `/mnt/c/Users/<windows-user>/.aws/.env`. Simultaneously, **automatically add** `/mnt/c/Users/<windows-user>/.aws` to the sandbox's read allowlist (otherwise bwrap cannot access it).

**Pros**:

- The deny effect actually fires (no silent fall-open).
- Applicable to both file-level / wildcard.

**Cons**:

- WSL-specific logic enters the runtime (`/mnt/c` detection / Windows path handling).
- Side effect of read-allowlist expansion: **`/mnt/c/Users/<windows-user>/` contents that were originally invisible to the sandbox get exposed** (Windows personal files other than credentials may become readable from sandbox).
- Need anti-loop measure when the symlink destination is multi-layer / another symlink.
- The design judgment "do not respect symlinks" violates the profile-as-source-of-truth principle (the runtime silently replaces what the user wrote as `~/.aws/X` with another path).

### 4.4 Option D — Insert stub directories into the namespace before bootstrap

**Summary**: the sandbox runtime inspects parents of deny entries; if they are symlinks on the host, **insert `--tmpfs <parent>` into the bwrap arguments first** to cover the parent with tmpfs, then layer `--bind /dev/null <entry>` on top.

**Pros**:

- Deny fires reliably (deny-target file on tmpfs is bind-able).
- Profile is not rewritten (symlink resolution completes inside the sandbox view).
- Effective for symlink families in general, not just WSL.

**Cons**:

- Complexity in bwrap argument assembly (mount order dependency, avoiding collision with existing mounts).
- Covering parent with tmpfs means **host-side files other than the deny entry disappear from the sandbox view** (e.g. `~/.aws/config` becomes invisible too when `~/.aws` is covered with tmpfs, even though it is not a deny target). This is equivalent to the round 3 wildcard option behavior, which was retired.
- Partial tmpfs (cover only part of it, pass the rest through) is hard to express in bwrap.

### 4.5 Option E — Profile-as-WSL-aware: detect environment and switch deny sets

**Summary**: profile-gen detects the host environment (WSL detection / `~/.aws` symlink detection), and in WSL environments **does not emit** `~/.aws/**` etc. from `sandbox.filesystem.denyRead/denyWrite` in the first place. Instead, narrow to Layer 2 defense via only `Read(~/.aws/*)` / `Read(~/.ssh/*)` in `permissions.deny`. In Linux native environments, keep the conventional Layer 2 + Layer 3 doubling.

**Pros**:

- Guarantees that the profile "works correctly per environment".
- Explicit "do not lay Layer 3 in this environment" decision rather than silent fall-open.
- Bootstrap failure on profile application becomes impossible in principle (no Layer 3 in WSL).

**Cons**:

- Profile output becomes environment-dependent, making it harder for readers to know "which setting denies what" (the same profile gives different effective deny depending on whether the reader is on WSL or Linux native).
- The Phase 1 (Issue #378) design of adding a `sandbox` field to `role_configs_schema.json` needs an "environment branching" concept.
- Without Layer 3 on WSL, defense-in-depth becomes thinner if Layer 2 hooks / classifier are bypassed.

## 5. Comparison summary and adopted option

| view | A: skip+warn | B: retry-prune | C: symlink rewrite | D: tmpfs stub | E: env-aware |
|---|---|---|---|---|---|
| implementation cost | small | medium | medium–large | large | medium |
| resolves startup failure | ◯ | ◯ | ◯ | ◯ | ◯ |
| Layer 3 deny fires | ✗ (skip) | ✗ (prune) | ◯ | ◯ | ✗ (not emitted) |
| profile transparency | ◯ (warning emitted) | △ (unknown until real machine) | ✗ (silent rewrite) | ◯ | ◯ (with env note) |
| generality outside WSL | ◯ | ◯ | △ | ◯ | △ (env branching premise) |
| side effects | silent fall-open hazard | retry cost + string parsing | `/mnt/c` exposure | tmpfs masks whole parent | effective profile diff across envs |
| Layer 1+2 retained | ◯ | ◯ | ◯ | ◯ | ◯ |

### 5.1 Adopted: option E (Layer 3 emit differentiation by env detection) + option A (fallback as warn-only safety net)

Reasons:

1. **"Do not lay Layer 3 in symlink environments" is the straightforward design**, and explicitly tells profile readers "in WSL, defend via the perms layer instead of the sandbox layer". Silent fall-open (option A alone) is hard to accept from a security review standpoint.
2. **Profile transparency** — profile-gen output retains machine-readable metadata "detected platform: wsl, layer-3 ~/.aws denylist suppressed". One line is also recorded in the journal.
3. **Layer 1 + Layer 2 double defense is real-machine confirmed in rounds 2 / 3** (`Read(~/.ssh/*)` / `Read(~/.aws/*)` in [`profile-tightened.json:52-53`](./profiles/profile-tightened.json) and Claude Code built-in credential redaction). Even with Layer 3 absent in WSL, secret leakage is prevented (round 3 §4.3 confirmed `cat ~/.aws/credentials` stdout stays empty).
4. **Option A as fallback** — if the environment-detection logic misses a new symlink pattern (e.g. `~/.config/X` is a symlink), keep it as a safety net that does warn-only skip without bootstrap failure. However, since `~/.aws` etc. on WSL are already eliminated by option E, option A's appearance is limited to edge cases.
5. **Option C (rewrite) not adopted** — bringing `/mnt/c` into the sandbox's view is too large a side effect; the trade-off of making Windows personal files broadly readable from the sandbox is unacceptable.
6. **Option D (tmpfs stub) not adopted** — round 3 retired the behavior where wildcard option tmpfs masks the whole parent. The equivalent side effect (`~/.aws/config` etc. non-deny-targets also become invisible) would recur.
7. **Option B (retry-prune) not adopted** — vs. option A's warn-only skip, the trade-off of string-parse dependency and doubling startup cost is not justified when the same goal is achievable.

### 5.2 Policy requirements of the adopted option (Phase 3 spec)

a. **Environment detection rules**:
   - WSL detection: `/proc/version` includes `Microsoft` / `WSL`, or `/proc/sys/kernel/osrelease` includes `microsoft-standard-WSL`.
   - Per-path detection: `os.path.realpath()` resolve each deny entry; if it resolves under `/mnt/c/` / `/mnt/d/`, judge as "Windows-side file".
   - Two-stage detection (even if not WSL, treat as same when the target path goes outside via another symlink).

b. **profile-gen behavior**:
   - In WSL, when `~/.aws` / `~/.ssh` etc. are dangling symlinks (resolve outside sandbox view), **do not emit** corresponding entries in `sandbox.filesystem.denyRead` / `denyWrite`.
   - At the same time, **always emit** `Read(~/.aws/*)` / `Read(~/.ssh/*)` on the `permissions.deny` side (same as existing design).
   - At the top of profile output, retain machine-readable metadata via `$comment` like "platform=wsl, layer-3 entries suppressed: [list]".

c. **bootstrap fallback (option A)**:
   - When the profile still contains Layer 3 entries at bwrap startup, attempt startup and on detecting errors like `Can't create file at` / `Can't mount tmpfs on`, skip the entry and retry once.
   - On skip, append one `sandbox_deny_skipped` event to `.state/journal.jsonl` (`reason="bwrap_bootstrap_failure"`, `entry`, `bwrap_stderr_excerpt`).
   - If retry also fails, fail-closed or fall-open per the `failIfUnavailable` setting.

d. **Redefinition of failIfUnavailable's meaning** (resolves round 3 §8 residual #3):
   - `failIfUnavailable: true` = fail-closed (process startup failure) on any of bwrap absent / bwrap startup failure / mount failure.
   - `failIfUnavailable: false` (default) = fall-open (start with disabled) only when bwrap is absent; bwrap startup failure / mount failure goes through **the bootstrap fallback (c) skip-and-retry** before judgment.
   - profile-tightened on WSL: Layer 3 peeled off via (c), startup succeeds. On Linux native: startup succeeds with Layer 3 alive.

e. **Observability**:
   - Add a "suppressed entries: [list]" section to `/sandbox` status output.
   - Make `claude-org-runtime settings show` etc. able to display the final deny set after profile-gen.
   - Align journal event namespaces so they can be detected by curator skill / dispatcher monitoring.

## 6. Trade-offs of the adopted option and remaining risks

1. **Absence of Layer 3 in WSL → thinner defense-in-depth** — credentials are confirmed not to leak under Layer 1 + 2 on real machines in rounds 2 / 3, but if Layer 2 breaks due to future hook additions / classifier changes, detection on WSL may be delayed. Mitigation: a proposal to **dual-layer** the `Read(~/.aws/*)` of profile-tightened's `permissions.deny` with a Phase 2 hook (new `block-secret-read.sh` etc.) is separately considered in Issue #379.
2. **False positives / negatives in environment detection** — similar symptoms can occur with `/mnt/d`, `/mnt/wsl`, devcontainer's `/workspaces` symlink, etc. The detection logic uses "the symlink resolves outside the sandbox's read allowlist" as the substantive criterion, and avoids hardcoding `/mnt/c`.
3. **env-dependency in profile diffs** — different sandbox cmd-lines are generated from the same profile-tightened.json (different between WSL / Linux native). Care needed in interpreting diffs during CI / review. `claude-org-runtime settings show --explain` should be able to display "emit suppression reason" to reduce confusion in review.
4. **Phase 1 schema impact** — Issue #378 (adding a `sandbox` field to `role_configs_schema.json`) gets an env-aware emit concept, so we want to split the schema into "profile-as-input" and "emit-as-output", keeping profile-as-input env-independent. Push platform branching to the emit logic side.
5. **Journal event volume** — skip events accumulate per startup. Have the curator side adopt a debounce convention where `sandbox_deny_skipped` counts once per startup for the same configuration, and only when configuration changes are re-detected.

## 7. Out of scope (handover to follow-up worker)

Implementation is outside this worker's responsibility. The following are handled by the follow-up worker (Issue #392 / linked with Issue #378) that implements the adopted option:

- Adding platform detection logic to `claude-org-runtime settings generate`
- Adding the `sandbox` field to `role_configs_schema.json` (Phase 1 / Issue #378)
- Implementing the bwrap stderr parser and retry (bootstrap fallback part of option A)
- Fixing the `sandbox_deny_skipped` event schema for `.state/journal.jsonl`
- Updating profile-tightened.json's `$comment` (suppression metadata note after emit)
- Adding a WSL note to runbook §sandbox real-machine verification ([`docs/verification.md`](../verification.md))

## 8. Related resources

- [`docs/sandbox-probe/notes/iteration-b-round3-results.md`](./notes/iteration-b-round3-results.md) — detailed real-machine symptoms this policy seeks to solve (especially §4.3, §6, §7.2, §8 residual items)
- [`docs/sandbox-probe/profiles/profile-tightened.json`](./profiles/profile-tightened.json) — the profile defining the doubling of Layer 2 (`permissions.deny`) and Layer 3 (`sandbox.filesystem.denyRead/denyWrite`)
- [`docs/sandbox-probe/notes/iteration-b-round2-results.md`](./notes/iteration-b-round2-results.md) — real-machine confirmation that `.env` / credential family flip to deny via Layer 2 perms.deny
- [`docs/verification.md`](../verification.md) §sandbox real-machine verification — bubblewrap prerequisites and current verification procedure
- [`docs/worker-permissions-design.md`](../worker-permissions-design.md) — design notes on `additionalDirectories`
