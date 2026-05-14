# profiles/

**Handcraft candidate sandbox profiles** that can be applied directly in the worker `.claude/settings.local.json` format.

- The format is a superset of the `settings.local.json` Claude Code reads, with a **`sandbox` block added** to `permissions` / `hooks` / `env`.
- At this spike's point in time, the bundled `role_configs_schema.json` of `claude-org-runtime` (v0.1.2) does **not contain** a `sandbox` field, so these files cannot currently be emitted as-is via `claude-org-runtime settings generate`. They are **handcraft candidates intended to be written back manually into `worker_dir/.claude/settings.local.json` for verification**.
- The plan is to formalize this schema-driven path in Phase 1 (Issue #378) by extending the runtime-side schema, then expanding the ja pin window.

## Files

- `profile-baseline.json` — **minimum defense**. Adds the repo-shared dangerous-git / no-verify hooks and sandbox denyRead for `.env` / `*.pem` / credentials to the current worker template. Assumes Pattern A.
- `profile-tightened.json` — **hardened version**. On top of the baseline, (a) adds `git -C` form dangerous-git deny entries to schema deny, (b) extends sandbox.filesystem.denyWrite to `~/.claude/`, `~/.ssh/`, `~/.aws/`, and (c) explicitly lists only `worker_dir` in `additionalDirectories`.

## How to apply (only at real-machine verification time; this spike does not apply)

1. Prepare one worker dir at the probe iteration (this directory is also acceptable).
2. `cp profiles/profile-baseline.json .claude/settings.local.json`
3. **Placeholder substitution** (forgetting this leaves hook commands pointing at literal `{claude_org_path}` and the defense layers fail to function):
   ```bash
   sed -i "s|{worker_dir}|<absolute path of the probe worker>|g; \
           s|{claude_org_path}|<absolute path of claude-org-ja>|g" \
          .claude/settings.local.json
   jq empty .claude/settings.local.json
   ```
4. Restart Claude Code in the worker dir.
5. Run the corresponding rows in `probes/checklist.md` and record the observations.
6. If needed, switch to `profile-tightened.json` (re-run #2-3) and compare the diff.

## Notes

- The current hooks (`block-dangerous-git.sh`, `block-no-verify.sh`) assume repo-shared placement, so to fire them via the worker dir, the `command` path references `{claude_org_path}/.hooks/...`. This matches the existing hook notation in `worker_roles.default`, so drift is not directly affected.
- `sandbox.failIfUnavailable: false` is kept in this spike too (a verification loop cannot run if worker startup fails in environments where bubblewrap is not installed). Switching to fail-closed for production use is a separate decision in Phase 3 (Issue #380).
- `additionalDirectories` is the helper that lets Claude Code on WSL2 allow writes outside cwd. For a Pattern A worker, cwd === worker_dir, so including `worker_dir` is equivalent to allowing writes to the worker itself. When migrating to Pattern B/C and including the base_repo `.git/`, split the profile (this iteration covers Pattern A only).
