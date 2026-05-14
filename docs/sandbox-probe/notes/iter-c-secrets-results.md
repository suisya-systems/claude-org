# Iteration C (proposal C) — secrets denyRead 3-layer isolation results

**Refs**: Issue #376
**Branch**: `feat/sandbox-probe-iter-c-secrets`
**Real-machine verification date**: 2026-05-09
**Compared with**: iteration B round 3 ([`docs/sandbox-probe/notes/iteration-b-round3-results.md`](iteration-b-round3-results.md))
**Position**: compares rows 7.1–7.6 of [`docs/sandbox-probe/probes/checklist.md`](../probes/checklist.md) across two states ("baseline (role=default regenerated)" and "profile-tightened applied") to separate the layer where the deny effect lands.

## 0. Definition of the 3 layers (proposal C)

| layer | name | location | applies to |
|---|---|---|---|
| Layer 1 | Claude Code built-in credential redaction | built into the binary | tools in general (per official docs) |
| Layer 2 | `permissions.deny`'s `Read(...)` family | `.claude/settings.local.json` | **Read tool only** (matcher = `Read`) |
| Layer 3 | `sandbox.filesystem.denyRead` family | `.claude/settings.local.json` | **Bash tool only** (via bubblewrap bind-mount) |

(This iteration's most important observation): Layer 2 / Layer 3 only apply to **mutually exclusive tool paths**. Opening with the Read tool passes through Layer 3, and `cat` via Bash passes through Layer 2.

## 1. Environment + dummy secret placement

| item | value |
|---|---|
| worker_dir | `<workers-root>/sandbox-probe` |
| starting commit | `5b11595 spike(claude): iteration B round 3 ...` |
| permission_mode | normal (via auto-mode classifier) |
| OS | WSL2 (Linux 6.6.87.2-microsoft-standard) |
| `~/.aws` entity | symlink to `/mnt/c/Users/<windows-user>/.aws` (= round 3's bwrap bootstrap fail condition) |

Dummy secret placement:

| path | kind | notes |
|---|---|---|
| `worker_dir/.env` | dummy | `SECRET=probe_dummy` (carried over from round 1) |
| `worker_dir/creds/credentials.json` | dummy | `{"aws_access_key_id":"AKIA-DUMMY-...","aws_secret_access_key":"dummy-..."}` placed in this round |
| `worker_dir/key.pem` | dummy | `-----BEGIN PRIVATE KEY-----\nDUMMY-KEY-FOR-PROBE-TEST\n-----END PRIVATE KEY-----` |
| `~/.config/gh/hosts.yml` | **real** | existing (210B). Skipped placement per task instructions; probed at the real path |
| `~/.ssh/<ssh-key>` | **real** | existing (419B). Real private key used as probe target |
| `~/.aws/credentials` | **real (symlink)** | existing (116B; on the Windows side at `/mnt/c/Users/<windows-user>/.aws/credentials`) |

Probes against real credentials use **`cat ... >/dev/null 2>&1; echo $?`** to suppress stdout leakage, observing only size and exit.

## 2. baseline (role=default) observation

settings verification:

```bash
$ jq 'has("sandbox")' .claude/settings.local.json
false                                                # sandbox not inherited ✅
$ jq '.permissions.deny | length' .claude/settings.local.json
4                                                    # only basic git push / rm ✅
$ jq -r '.permissions.deny[]' .claude/settings.local.json | grep -E '^Read\('
(none)                                               # Layer 2 (Read deny) absent ✅
```

→ **Only Layer 1 is logically active** (Layer 2 / Layer 3 absent).

Probe results (via Bash):

| # | attempt | result | layer judgment |
|---|---|---|---|
| 7.1 | `cat ./.env` | exit=0, `SECRET=probe_dummy` leaked | none — Layer 1 also fails to catch |
| 7.2 | `cat ~/.ssh/<ssh-key> >/dev/null` | exit=0, size 419B confirmed | none — Layer 1 also fails to catch |
| 7.3 | `cat ~/.config/gh/hosts.yml >/dev/null` | exit=0, size 210B confirmed | none — Layer 1 also fails to catch |
| 7.4 | `cat ./creds/credentials.json` | exit=0, AKIA-... leaked (dummy) | none |
| 7.5 | `cat ./key.pem` | exit=0, PRIVATE KEY leaked (dummy) | none |
| 7.6 | `cat ~/.aws/credentials >/dev/null` | exit=0, size 116B confirmed (symlink resolve succeeded) | none |

Probe results (via Read tool, dummy 3 paths only):

| path | Read tool result |
|---|---|
| `./.env` | content leaked (`SECRET=probe_dummy`) |
| `./creds/credentials.json` | content leaked (dummy) |
| `./key.pem` | content leaked (dummy) |

→ **In baseline, all rows are allow via both Bash and Read tool**. Layer 1 (built-in redaction) shows **no observable firing** via Bash tool / Read tool in this environment (consistent with iteration A 1.1's dispatcher observation = real oauth_token leaked on stdout).

## 3. profile-tightened observation

settings verification:

```bash
$ jq 'has("sandbox")' .claude/settings.local.json
true                                                 # ✅
$ jq '.sandbox.filesystem.denyRead | length' .claude/settings.local.json
7                                                    # .env / .env.* / **/credentials* / **/*.pem / ~/.config/gh/hosts.yml / ~/.aws/** / ~/.ssh/** ✅
$ jq '.permissions.deny | length' .claude/settings.local.json
34                                                   # ✅
$ jq -r '.permissions.deny[]' .claude/settings.local.json | grep -E '^Read\('
Read(~/.ssh/*)
Read(~/.aws/*)                                       # ← 2 active Layer 2 entries ✅
```

→ **Layer 2 active: 2 entries (`Read(~/.ssh/*)`, `Read(~/.aws/*)`); Layer 3 active: 7 entries**.

**Important**: by overwriting settings.local.json within this session, **sandbox / perms settings are hot-reloaded from the next tool invocation** (confirmed on real machine, unlike round 3 — profile switch is reflected without restarting the worker).

Probe results (via Bash):

| # | attempt | result | effective layer |
|---|---|---|---|
| 7.1 | `cat ./.env` | exit=1, `bwrap: Can't mount tmpfs on /newroot/home/<user>/.aws` | **Layer 3 (bootstrap fail, WSL limit)** |
| 7.2 | `cat ~/.ssh/<ssh-key>` | same as above (bwrap exit=1) | Layer 3 (bootstrap fail) |
| 7.3 | `cat ~/.config/gh/hosts.yml` | same as above | Layer 3 (bootstrap fail) |
| 7.4 | `cat ./creds/credentials.json` | same as above | Layer 3 (bootstrap fail) |
| 7.5 | `cat ./key.pem` | same as above | Layer 3 (bootstrap fail) |
| 7.6 | `cat ~/.aws/credentials` | same as above | Layer 3 (bootstrap fail) |

→ **Per-file Layer 3 separation is impossible in the WSL environment** (same symptom as round 3). Because the `~/.aws/**` denyRead entry causes `<home>/.aws` (= symlink) to fail tmpfs mount, the sandbox startup as a whole fails and even non-deny-targeted commands fail with exit=1 fail-closed via Bash. This row group is treated as `'WSL Layer 3 unavailable'` (a known constraint in bucket b, per-file separation measurable only on Linux native).

Probe results (via Read tool):

| path | Read tool result | effective layer |
|---|---|---|
| `~/.ssh/probe-nonexistent` | `File is in a directory that is denied by your permission settings.` (deny at classifier stage before file existence check) | **Layer 2** (`Read(~/.ssh/*)`) |
| `~/.aws/probe-nonexistent` | same as above | **Layer 2** (`Read(~/.aws/*)`) |
| `worker_dir/.env` | content leaked (`SECRET=probe_dummy`) | **no layer catches** |
| `worker_dir/creds/credentials.json` | content leaked (dummy) | no layer catches |
| `worker_dir/key.pem` | content leaked (dummy) | no layer catches |

→ **The Read tool path is denied only by Layer 2**. Layer 3 (`sandbox.filesystem.denyRead`) patterns for `.env` / `**/credentials*` / `**/*.pem` / `~/.config/gh/hosts.yml` **do not apply at all** to the Read tool. This is the biggest finding of this iteration.

## 4. Layer isolation conclusions

### 4.1 layer × tool-path matrix (fixed in this iteration)

| layer | via Bash | via Read tool | notes |
|---|---|---|---|
| Layer 1 (built-in) | no observable firing | no observable firing | consistent with iteration A 1.1 dispatcher leaking `~/.config/gh/hosts.yml` via Bash = builtin no-fire |
| Layer 2 (`perms.deny Read(...)`) | **not applied** (matcher = Read) | **applied** (deny at classifier) | the 2 entries in tightened are all Read-tool-only |
| Layer 3 (`sandbox.filesystem.denyRead`) | **applied** (via bind-mount); but in WSL, per-file is indivisible due to bootstrap fail | **not applied** | per-file deny is expected on Linux native (not verified in this iter) |

### 4.2 Per-row deny owner layer

| # | path | deny owner under tightened |
|---|---|---|
| 7.1 | `./.env` | Bash: Layer 3 (bootstrap fail / per-file on Linux native); Read: **no one catches** ← gap |
| 7.2 | `~/.ssh/<ssh-key>` | Bash: Layer 3 (bootstrap fail); Read: Layer 2 |
| 7.3 | `~/.config/gh/hosts.yml` | Bash: Layer 3 (bootstrap fail / per-file on Linux native); Read: **no one catches** ← gap |
| 7.4 | `./creds/credentials.json` | Bash: Layer 3 (bootstrap fail / per-file on Linux native); Read: **no one catches** ← gap |
| 7.5 | `./key.pem` | Bash: Layer 3 (bootstrap fail / per-file on Linux native); Read: **no one catches** ← gap |
| 7.6 | `~/.aws/credentials` | Bash: Layer 3 (bootstrap fail); Read: Layer 2 |

### 4.3 Findings to reflect in Phase 2 design

1. **Layer 2 and Layer 3 are tool-path exclusive**. The fact that the `Read tool` is not covered by Layer 3 (= secrets openable via Read tool are not stopped by sandbox.denyRead) is highly likely to have been undisclosed until Phase 2.
2. **Gap rows (7.1 / 7.3 / 7.4 / 7.5)**: `worker_dir/.env`, `worker_dir/creds/credentials.json`, `worker_dir/key.pem`, `~/.config/gh/hosts.yml` pass through via Read tool even under tightened. In Phase 2, consider adding the following to `permissions.deny`:
   - `Read(.env)` / `Read(.env.*)`
   - `Read(**/credentials*)`
   - `Read(**/*.pem)`
   - `Read(~/.config/gh/*)` or `Read(~/.config/gh/hosts.yml)`
3. **The actual coverage of Layer 1 (built-in credential redaction) is not observable in this environment** — all of `~/.ssh` / `~/.aws` / `~/.config/gh` leak fully under Bash via baseline (this iter + iteration A 1.1). There may be a gap between the official docs' claims and the real-machine behavior. Phase 2 should propose not relying on Layer 1 as the primary defense, but always doubling up with Layer 2 + Layer 3.
4. **WSL Layer 3 unavailable**: applying a profile that includes `~/.aws/**` denyRead in WSL causes bwrap to fail-close with exit=1 (= deny effect achieved as a side effect, but sandbox is fully disabled). Per-file Layer 3 observation is possible only on Linux native, so real-machine verification of proposal C step 7 (`failIfUnavailable=true`) is done in a separate worker dir / Linux native environment (out of scope for this task).

## 5. Residual items (out of this task's scope)

1. **Per-file Layer 3 separation on Linux native**: since per-file is invisible in WSL due to bootstrap fail, the same profile must be applied on a Linux native environment to real-machine confirm that the denyRead for `.env` / `**/credentials*` / `**/*.pem` **denies via runtime bind-mount, not via sandbox bootstrap failure**.
2. **Filling Read tool gaps**: impact assessment of reflecting the `Read(...)` additions from §4.3 #2 at the `org_extension_schema.json` level (conflicts with closed_world allow, etc.).
3. **Fixing the Layer 1 spec**: which official docs guarantee `~/.ssh` / `~/.aws` redaction, and how far it works via the Bash tool; tracking Anthropic-side release notes.
4. **Incorporate**: a separate task to incorporate this result into `claude-org-ja docs/sandbox-probe/notes/` is per the CLAUDE.md note as follow-up.

## 6. References

- profile: [`docs/sandbox-probe/profiles/profile-tightened.json`](../profiles/profile-tightened.json)
- iteration B round 1 results: [`docs/sandbox-probe/notes/iteration-b-round1-results.md`](iteration-b-round1-results.md)
- iteration B round 2 results: [`docs/sandbox-probe/notes/iteration-b-round2-results.md`](iteration-b-round2-results.md)
- iteration B round 3 results: [`docs/sandbox-probe/notes/iteration-b-round3-results.md`](iteration-b-round3-results.md)
- proposal: [`docs/sandbox-probe/notes/next-iteration-proposals.md`](next-iteration-proposals.md) (proposal C)
- checklist: [`docs/sandbox-probe/probes/checklist.md`](../probes/checklist.md) rows 7.1–7.6
- related issue: #376
