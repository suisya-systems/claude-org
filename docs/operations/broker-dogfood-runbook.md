# broker dogfood operations runbook

`claude-org-runtime broker serve` is the daemon for the **pure-backend transport (`org-broker`)** that replaces renga-peers. It provides a localhost HTTP MCP server + queue store + nudge delivery in a single process, and injects nudges into child panes through the terminal adapter (tmux / WezTerm). This document is the **precursor to running production ja with `ORG_TRANSPORT=broker`** under Epic #6 Issue G (#515): it captures the broker daemon's start / stop / lifecycle / rollback as operational procedures.

The design SoT is transport-lab `docs/design/ja-migration-plan.md` §5 (ja integration seam) / §5.5 (coexistence & rollback) / §8 Issue G (dogfood gate). The contract SoT is [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, proposed / awaiting ratification). For the secretary's operational differences between the two transports see [`CLAUDE.md`](../../CLAUDE.md) "transport (transport) both systems"; for the spawn ritual see [`.dispatcher/references/spawn-flow.md`](../../.dispatcher/references/spawn-flow.md) 3-3b.

> **Scope and untouchable constraints**: this runbook is "the procedure that makes a live run possible"; the **actual broker live run on production ja (org-start hijack) is performed later in track 3 (user hands-on)**. Every procedure here starts and stops the daemon under a **test state-dir (some directory other than `.state/broker/`)**, on the premise of never polluting production `.state/`. **The default `renga` is not removed and remains permanently available as an opt-in fallback** (the safety device for rollback).

> **Verification status (2026-06-11, runtime 0.1.17 / tmux 3.2a / WSL2)**: every start / stop / lifecycle / dry-run command in this document has been verified on real hardware in a worker worktree environment. The key points of the raw logs are embedded in each section.

---

## 1. Role and prerequisites

- **Inputs / control**:
  - Environment variable `ORG_TRANSPORT` (`renga` | `broker`, unset = default `renga`). The daemon itself does not read the flag, but the ja-side generator (§4) emits the broker-face allowlist according to the flag.
  - CLI arguments (`--port` / `--host` / `--state-dir` / `--backend` / `--no-nudge`, §2.1).
- **Outputs / side effects**:
  - localhost HTTP MCP endpoint (default `http://127.0.0.1:48720/mcp`).
  - queue store + JSONL journal (`<state-dir>/queue.jsonl`, default state-dir = `.state/broker`).
  - Nudge injection into child panes (via terminal adapter, disabled by `--no-nudge`).
- **Dependency direction (one-way)**: `broker -> terminal / dispatcher.choose_split`. **claude-org-ja does not import broker** (inactive when the flag default is renga).
- **CLI name note (important)**: the launch command is **`claude-org-runtime broker serve`** (a subcommand of the top-level CLI). `claude-org-runtime-broker` is the CLI's `prog` name (the header text in `--help`); **no console_script of that name exists**. `python -m claude_org_runtime.broker serve` launches equivalently.

```
$ claude-org-runtime broker --help
usage: claude-org-runtime broker [-h] {serve} ...
    serve     org-broker daemon を localhost で起動する (Ctrl+C で停止)。
```

---

## 2. Real-hardware verification of broker daemon startup

### 2.1 `serve` options

```
$ claude-org-runtime broker serve --help
usage: claude-org-runtime broker serve [-h] [--port PORT] [--host HOST]
                                       [--state-dir STATE_DIR]
                                       [--backend {wezterm,tmux}] [--no-nudge]
```

| Option | Default | Meaning |
|---|---|---|
| `--port` | `48720` (`DEFAULT_PORT`) | localhost bind port. `0` for ephemeral (OS-assigned; the actual port appears in the startup log's `listening on`). |
| `--host` | `127.0.0.1` | bind host. localhost-only by design. |
| `--state-dir` | `.state/broker` (`DEFAULT_STATE_DIR`, relative to CWD) | Write location for `queue.jsonl`. **Always pass a different directory during verification** (§2.3 / §7). |
| `--backend` | OS auto-selected (POSIX=`tmux` / Windows=`wezterm`) | terminal adapter. `VALID_BACKENDS = (wezterm, tmux)`. Ignored when `--no-nudge`. |
| `--no-nudge` | (disabled) | Skip creating the terminal adapter and cut nudge delivery (**queue only**). Use when you want to check connectivity only, independent of backend. |

`serve` blocks in the foreground (stop with `Ctrl+C` / `SIGINT`). At startup it issues a single token for manual verification and prints the JSON to pass to `--mcp-config` on stdout:

```
org-broker listening on http://127.0.0.1:48803/mcp
queue store: /<state-dir>/queue.jsonl
manual test token: <token>
mcp-config: {"mcpServers": {"org-broker": {"type": "http", "url": "...", "headers": {"Authorization": "Bearer <token>"}}}}
```

### 2.2 Start / stop commands (production form)

The form for production ja startup (track 3, user hands-on) is as follows. **This section is a presentation of the command form; this document's verification only runs the test state-dir version from §2.3.**

```bash
# Start (default state-dir = .state/broker, tmux backend auto-selected)
claude-org-runtime broker serve

# Stop: Ctrl+C (SIGINT) to the foreground serve. One line of broker_stopped is left in the journal.
# If launched in the background, send SIGINT to the PID:
#   kill -INT <pid>
```

### 2.3 Test state-dir startup -> connectivity -> stop (proof procedure that production `.state` is untouchable)

Verification **must never touch production `.state/broker/`**. Pass a temporary directory to `--state-dir` and confirm that `queue.jsonl` is created only at that test path.

> **cwd drift note (mandatory)**: `--state-dir`'s default is **CWD-relative** `.state/broker`. Because `.state/` differs between worker worktrees and the canonical claude-org root, hitting the relative path bare makes "which `.state` are we looking at" ambiguous and invites mistaken untouchable checks / production `.state` pollution. In this document we **pin the canonical root with an absolute-path variable `CANON_ROOT` and pin the test state-dir with an absolute-path variable `TEST_STATE` outside the repo**, and never hit relative `.state/broker` bare-handed.

```bash
# 0) Pin prerequisite variables (do not hit relative paths bare-handed)
CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root holding production .state/broker (adjust to environment)
TEST_STATE=/tmp/claude/broker-smoke-A               # test state-dir (must be an absolute path outside the repo)

# 1) Prepare the test state-dir (create parent dir + use an unused path to avoid mixing with existing logs)
mkdir -p "$TEST_STATE"
test -e "$TEST_STATE/queue.jsonl" && echo "WARN: existing queue.jsonl found. Use a different path or move it aside before verifying"

# 2) Start (--no-nudge verifies connectivity only, independent of backend. -u flushes stdout immediately)
python3 -u -m claude_org_runtime.broker serve \
    --state-dir "$TEST_STATE" --port 48799 --no-nudge
```

From another terminal (or a driver script), hit the HTTP MCP with the token shown in the startup log:

| Step | Expected |
|---|---|
| `initialize` | `serverInfo = {"name": "org-broker", "version": "0.1.0"}` + `Mcp-Session-Id` header assigned |
| `tools/list` (worker token) | **messaging 4 only**: `["check_messages", "list_peers", "send_message", "set_summary"]` (tier gating, §3.4) |
| `tools/call send_message` (self-addressed) | `{"ok": true, "delivered_to": "manual-test"}` |
| `tools/call check_messages` | The `hello broker` sent just before is drained at-most-once |

Stop by sending `SIGINT` to serve. **Clean shutdown -> exit code 0.**

**Confirming `.state` untouchability (mandatory)**: after verification, confirm that production `.state/broker/` has not been generated. The queue is written only to the test path that was passed.

```bash
# The queue exists only under TEST_STATE
ls "$TEST_STATE/queue.jsonl"
# The production side (absolute path under canonical root) must be ungenerated. Do not use relative .state/broker
test -e "$CANON_ROOT/.state/broker" && echo "NG: production .state/broker was polluted" || echo "OK: production .state is unchanged"
# Also confirm no test debris was dropped directly under the current worktree (prevents mix-up with CWD-relative default)
test -e "$PWD/.state/broker" && echo "NG: .state/broker was generated directly under worktree" || echo "OK: directly under worktree is also unchanged"
```

> **Verification log (2026-06-11, real hardware)**: with both `--no-nudge` and `--backend tmux`, the round-trip `initialize -> tools/list -> send_message -> check_messages` succeeds and `SIGINT` yields **exit 0**. `tools/list` shows only the messaging 4 at worker tier. Production `.state/broker/` is not generated (`queue.jsonl` only at the test path). The tmux backend works even without a live tmux server: the adapter is lazily created and start / stop succeed (the messaging probe is skipped because no child pane exists to actually inject a nudge into).

---

## 3. start / stop / token / queue lifecycle

broker's internal state transitions are split across `server` / `store` / `tokens` / `surface` under `claude_org_runtime/broker/`. The four operationally relevant flows are:

### 3.1 token issuance (`tokens.py`)

- At spawn time a **per-agent token** is issued (`issue_token`, `secrets.token_urlsafe(32)`). token <-> `AgentBind` (`agent_id` / `name` / `role` / `auth_role` / `pane_id` / `cwd` / `kind`).
- **`role` (display-only, mutable via `set_pane_identity`) is separated from `auth_role` (immutable permission tier, fixed at issuance)**. Tier gating is decided by `auth_role` only; the self-declared display `role` cannot promote. A spawned child's `auth_role` is capped at the caller's tier (`capped_auth_role`).
- `mcp_config_for(token)` generates the JSON to pass to `--mcp-config` (embeds the token into the static header `Authorization: Bearer <token>`; env references `${VAR}` are not used).
- journal: `token_issued`.

### 3.2 Registration (HTTP handler in `server.py`)

- When the child pane's Claude / Codex reaches `initialize` (MCP), `AgentBind.registered = True` (`registered_at` recorded). **Only registered binds become delivery targets** (preventing delivery to unconnected / DELETE-d clients).
- journal: `agent_registered`.

### 3.3 queue store + nudge delivery (`store.py` / `server.py`)

- `send_message` (`enqueue`) creates the entry with **token-derived attribution** (self-declaration not allowed). The recipient's registered check and queue append are done atomically **within the same lock scope**; only afterwards, outside the lock, are `_journal` and `_trigger_nudge` called (decoupling queue persistence from PTY injection / avoiding double-acquire deadlock of the non-reentrant Lock).
- Nudge delivery **injects only a fixed one-liner via PTY** and does not pass the body (the receiver pulls with `check_messages` = push -> pull model). When the adapter is unreachable or the target has not arrived, retries up to `nudge_defer_interval` (default 2.0s) x `nudge_defer_max_tries` (default 30).
- `check_messages` (`drain`) empties the queue **at-most-once** and returns.
- journal: `message_enqueued` -> `nudge_sent` / `nudge_deferred` / `nudge_failed` -> `queue_drained`.

### 3.4 tier gating (`surface.py`)

The public surface **structurally** varies by `auth_role` (default-deny allowlist). Tools that do not appear in `tools/list` are rejected with `[tool_not_authorized]` even if called (the allowlist is one side of double defense).

| auth_role tier | Public surface |
|---|---|
| worker / curator / unknown | messaging 4 (`send_message` / `check_messages` / `list_peers` / `set_summary`) |
| dispatcher | messaging 4 + ops (`list_panes` / `inspect_pane` / `send_keys` / `poll_events` / `close_pane` / `set_pane_identity` / `spawn_claude_pane` / `spawn_codex_pane`) |
| secretary | dispatcher's surface + `spawn_pane` (secretary-exclusive) |

> `new_tab` / `focus_pane` are **not** on the broker surface (deliberate exclusion). Initial surface = 12 ported tools + `spawn_codex_pane` = 13 tools.

### 3.5 Stop / invalidation

- daemon stop: `stop()` shuts down + closes the HTTP server and leaves `broker_stopped` in the journal.
- session end (MCP `DELETE`): invalidates the bind's `session_id` and drops `registered = False` (does not leave a disconnected client in `list_peers` / as a delivery target). journal: `session_closed`.
- pane close (`close_pane`): after the adapter kills, the registry pop and token revoke are performed atomically in one lock scope. journal: `pane_closed` + event `pane_exited`.

### 3.6 journal event list (`queue.jsonl`)

`<state-dir>/queue.jsonl` is appended one JSON per line. The observation points in operations:

```
broker_started -> token_issued -> agent_registered -> message_enqueued
  -> nudge_sent / nudge_deferred / nudge_failed -> queue_drained
  -> session_closed / pane_closed -> broker_stopped
```

> **Verification log (real hardware, messaging round-trip)**: confirmed `broker_started -> token_issued -> agent_registered -> message_enqueued(chars=12) -> queue_drained(count=1) -> broker_stopped` in one cycle.

### 3.7 broker additional error codes

In addition to the renga codes, broker can return the following. The secretary / dispatcher routes unknown codes through the default branch to escalation ([`CLAUDE.md`](../../CLAUDE.md) "error branches").

| Code | Trigger |
|---|---|
| `[token_invalid]` | Bearer token not in bind table / revoked (HTTP 401, JSON-RPC -32001) |
| `[session_invalid]` | Called another method before `initialize` |
| `[tool_not_authorized]` | Called a tool outside the auth_role tier's public surface |
| `[no_backend]` | Called a pane operation without the terminal adapter (`--no-nudge` startup) (= adapter_unavailable) |
| `[nudge_failed]` | Nudge injection did not arrive within the defer cap |
| `[peer_not_found]` | `send_message` destination is not a registered bind |
| `[name_taken]` | pane name duplicate |

---

## 4. settings regeneration dry-run under `ORG_TRANSPORT=broker`

Dry-run the **transport descriptor-driven generator** introduced in Epic #6 D/E under `ORG_TRANSPORT=broker` and confirm that the broker-face allowlist is emitted. **Do not write actual files.**

### 4.1 Single SoT (descriptor)

The ja-side transport accessor [`tools/transport.py`](../../tools/transport.py) consumes the runtime's transport surface descriptor (`claude_org_runtime.transport`) as the single SoT (no hard-coding). Resolution order is **explicit argument > `ORG_TRANSPORT` env > default `renga`**. Allowlist generation goes through `claude_org_runtime.settings.generator.transport_allowlist(role, transport=...)`.

### 4.2 Per-role allowlist dry-run

```bash
# Compare per-role projection of default renga (unset) vs broker (read-only, no writes)
for role in worker curator dispatcher secretary; do
  echo "--- $role renga(default) ---"
  python3 -c "from claude_org_runtime.settings.generator import transport_allowlist as t; print(t('$role'))"
  echo "--- $role broker ---"
  ORG_TRANSPORT=broker python3 -c "from claude_org_runtime.settings.generator import transport_allowlist as t; print(t('$role'))"
done
```

| role | renga (default) | broker (`ORG_TRANSPORT=broker`) |
|---|---|---|
| worker / curator | `mcp__renga-peers__*` 14 tools | `mcp__org-broker__*` messaging 4 |
| dispatcher | `mcp__renga-peers__*` 14 tools | messaging 4 + ops 8 (does not include `spawn_pane`) |
| secretary | `mcp__renga-peers__*` 14 tools | messaging 4 + ops + `spawn_pane` + `spawn_codex_pane` (13) |

> renga default uses a model that narrows down a single surface (14 tools) shared by all roles with the allowlist. broker **structurally** blocks role tier, so the allowlist becomes one side of double defense (safe side).

### 4.3 `~/.claude/settings.json` user_common allowlist regeneration dry-run

[`tools/org_setup_prune.py`](../../tools/org_setup_prune.py) `--user-common-allowlist` projects the MCP `permissions.allow` in user_common (`~/.claude/settings.json`) onto the active transport. **For verification, point `--user-common-settings-path` at a test path so the real `~/.claude/settings.json` is not touched, and add `--dry-run`.**

```bash
# Prepare test settings (with renga entries) and dry-run
TEST_SET=/tmp/claude/usercommon-settings.json   # NOT the real ~/.claude/settings.json

# Create test settings containing renga messaging entries (an empty/missing file won't produce the drop-renga expected output)
mkdir -p "$(dirname "$TEST_SET")"
cat > "$TEST_SET" <<'JSON'
{
  "permissions": {
    "allow": [
      "Bash(git status:*)",
      "mcp__renga-peers__send_message",
      "mcp__renga-peers__check_messages",
      "mcp__renga-peers__list_peers",
      "mcp__renga-peers__set_summary"
    ]
  }
}
JSON

# Default renga: strict no-op (does not touch the file at all)
python3 tools/org_setup_prune.py --user-common-allowlist --dry-run \
    --user-common-settings-path "$TEST_SET"

# broker: drops renga-peers, guarantees org-broker messaging tier (dry-run is display only)
ORG_TRANSPORT=broker python3 tools/org_setup_prune.py --user-common-allowlist --dry-run \
    --user-common-settings-path "$TEST_SET"
```

Expected output:

```
# renga (default)
[org_setup_prune] user_common allowlist: transport=renga (default); no-op — ~/.claude/settings.json is unchanged ...

# broker
=== user_common allowlist (transport=broker): /tmp/claude/usercommon-settings.json ===
  - mcp__renga-peers__send_message      (drops the renga messaging below)
  + mcp__org-broker__send_message       (adds the org-broker messaging below)
  ...
```

> **Verification log (real hardware)**: default renga is strict no-op (the test file is unchanged down to the byte). Under `ORG_TRANSPORT=broker`, the diff renga messaging 4 -> org-broker messaging 4 is shown as a dry-run. **Zero actual writes thanks to `--dry-run`** (test file content confirmed unchanged). Non-MCP entries like `Bash(...)` are retained in order.

---

## 5. Concrete commands for the 5 rollback conditions (SoT §5.5)

A full rollback `ORG_TRANSPORT=broker` -> `renga` is **not immediately restored on broker-spawned panes already in flight** by just reverting the flag (they still carry `--mcp-config` / pull-based prose). Execute the **5 completion conditions** of SoT §5.5 in order.

> **Prerequisite variables (cwd drift avoidance)**: the commands below do not hit relative `.state/broker` bare-handed. Pin with an absolute-path variable the state-dir that the daemon actually used in `serve --state-dir`, and also clarify the canonical root. In production rollout (track 3), `BROKER_STATE` points to production `.state/broker`.
>
> ```bash
> CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root (adjust to environment)
> BROKER_STATE="$CANON_ROOT/.state/broker"            # --state-dir passed to daemon at serve time
> ```

### (1) Flag rollback

```bash
# Revert env to renga (default). The next spawned pane points to renga.
unset ORG_TRANSPORT
# If written into persistent shell config, remove from there as well:
#   grep -rn "ORG_TRANSPORT" ~/.bashrc ~/.zshrc ~/.profile
```

**Check**: `python3 -c "from claude_org_runtime.transport import resolve_transport as r; print(r())"` returns `renga`.

### (2) Regenerate generated artifacts (back to renga allowlist)

Once the flag is back to renga, **the generator (per-role `settings.local.json`) returns to identity (bit-equivalent)**. Actually regenerate the artifacts to revert to renga-face.

```bash
# First check the diff with dry-run (if broker-face remains, a diff to revert to renga will appear)
python3 tools/org_setup_prune.py --all --dry-run

# If fine, apply (writes back the renga allowlist; .bak is left)
python3 tools/org_setup_prune.py --all
```

**user_common (`~/.claude/settings.json`) is handled separately (important)**: `--user-common-allowlist` is **a complete no-op in renga mode** (because the SoT of the renga allowlist is the org-setup skill + permissions.md, not this tool; it does not touch the file at all). Therefore, if broker was applied during dogfood (with `mcp__org-broker__*` in user_common), running `--user-common-allowlist --dry-run` under renga **will not revert the broker face**. Explicitly revert user_common via one of the following:

```bash
# Method A (recommended): restore the .bak created when broker was applied
#   backup naming is settings.json.bak.<YYYYMMDD-HHMMSS> (backup_path)
ls -t ~/.claude/settings.json.bak.* 2>/dev/null | head     # check the most recent backup
# cp <confirmed .bak> ~/.claude/settings.json               # restore after eyeballing the content

# Method B: if no backup, manually swap the messaging face (org-broker -> renga-peers)
#   In ~/.claude/settings.json permissions.allow
#   replace "mcp__org-broker__{send_message,check_messages,list_peers,set_summary}" with
#   "mcp__renga-peers__..." (do not touch non-MCP entries)
```

**Check**: confirm `mcp__org-broker__*` remains in neither per-role `settings.local.json` **nor user_common (`~/.claude/settings.json`)**.

```bash
# Per-role settings under the repo. The glob (*/.claude/) does not pick up hidden role dirs
# (.dispatcher/.claude/ / .curator/.claude/ etc.); in zsh, no-match makes grep itself
# not run, leading to a mistaken OK. Without glob, grep -r recursively from the repo root
# (grep -r also descends into hidden dirs). Restrict to settings*.json to avoid false positives.
if grep -rl --include="settings*.json" "mcp__org-broker__" . 2>/dev/null | grep -q .; then
  echo "NG: broker face remains in repo side:"; grep -rl --include="settings*.json" "mcp__org-broker__" . 2>/dev/null
else
  echo "OK: no broker face on repo side"
fi
# Do not forget to check user_common (settings.json under home)
grep -l "mcp__org-broker__" ~/.claude/settings.json 2>/dev/null && echo "NG: broker face remains in user_common" || echo "OK: no broker face in user_common"
```

### (3) Respawn active broker panes (restart via the renga path)

Broker-spawned panes already in flight do not recover via flag rollback. suspend/resume or respawn them via the renga path.

```bash
# Grasp the current broker panes (from the renga secretary / dispatcher)
#   mcp__renga-peers__list_panes  to check the pane list
# Close each pane carrying a broker token in turn -> respawn via the renga path (the normal org-delegate delegation flow)
# Pane control is closed to dispatcher/secretary, so first revert messaging to renga, then follow pane afterwards (the 2-step of §5.5).
```

**Check**: no broker-bound pane remains in `list_peers` / `list_panes`.

### (4) broker daemon stop ordering (revoke remaining panes -> daemon stop)

**Ordering matters**: first revoke (close) remaining panes so they are removed from delivery targets, then finally stop the daemon.

```bash
# 1) Close the remaining broker panes (token is revoked. close_pane journal: pane_closed)
#    From renga/dispatcher, close_pane each broker pane.
# 2) Once all are revoked, stop the daemon (SIGINT to foreground serve, or)
kill -INT <broker_pid>
# 3) Confirm broker_stopped is recorded at the end of the journal
tail -n 3 "$BROKER_STATE/queue.jsonl"
```

### (5) Confirm disposal of old token / queue store (no unread messages / lingering binds in `.state/broker/`)

```bash
# Verify against the journal that no unread (enqueued but never drained) messages remain.
# queue_drained carries count=N, so compare by the sum of N rather than "event count" (avoids misjudgment from multiple drains).
BROKER_STATE="${BROKER_STATE:?pin BROKER_STATE first (§5 prerequisite variables)}" \
python3 - <<'PY'
import json, os
p = os.path.join(os.environ["BROKER_STATE"], "queue.jsonl")
enq = drained_msgs = 0
try:
    for line in open(p, encoding="utf-8"):
        rec = json.loads(line); ev = rec.get("event")
        if ev == "message_enqueued": enq += 1
        if ev == "queue_drained": drained_msgs += int(rec.get("count", 0))  # sum N
except FileNotFoundError:
    print("OK: queue.jsonl absent (disposed)"); raise SystemExit
unread = enq - drained_msgs
print(f"enqueued={enq} drained_msgs={drained_msgs} unread={unread}")
print("OK: no unread" if unread <= 0 else f"NG: {unread} unread remain (must be drained before daemon stop)")
PY

# token / bind are in-process in-memory (vanish when the daemon stops; not persisted).
# Dispose of the queue store file to leave no trace (truncate / archive in environments without rm):
#   mv "$BROKER_STATE" "$BROKER_STATE.archived-$(date +%Y%m%d)"   # or delete per operational rule
```

> **token / bind persistence**: `AgentBind` lives only in the daemon process's in-memory (the journal retains the fact of `token_issued`, but token values / bind table are not persisted). Stopping the daemon erases binds. What remains is only `queue.jsonl` (journal + undrained messages), so (5) is closed by the unread reconciliation and disposal of that file.

---

## 6. How to take the billing-neutrality attestation

Confirm via the actual argv that every agent broker spawns is **an interactive TUI (headless not allowed)**. This is the evidence of billing-neutrality (no non-interactive launches like `claude -p` / `codex exec` that incur API billing).

### 6.1 Defense-in-depth structure (spawn-time guard)

broker's billing-neutrality is structurally guaranteed by a **spawn-time default-deny allowlist** (`surface.py`):

- `build_claude_argv` / `build_codex_argv` only allow flags for the interactive TUI, and `_guard_interactive_claude_argv` / `_guard_interactive_codex_argv` **uniformly reject tokens not on the allowlist (post-flag subcommands / bare positional / `--` / unknown flags / headless flags)**.
- claude-side headless blacklist: `-p` / `--print` / `--headless` / `--output-format` / `--input-format` etc. On the codex side, subcommands (`exec` / `review` / `*-server` / `apply` / `sandbox` etc.) fall as bare positional.
- Value-taking flags carry arity (value-position headless flags are rejected with the second stage). `argv[0]` is judged by basename (does not false-reject absolute-path launches).

### 6.2 Actual argv inspection (runtime attestation)

On the production host (a session where the broker pane is live), inspect the actually running argv with ps. **Confirm that not a single headless flag / subcommand is present.**

The key is to **narrow the target to broker-spawned panes**. On the host, there may be coexisting headless executions (CI / manual `claude -p` etc.) unrelated to this attestation, so indiscriminately greping every claude/codex picks up false positives and conversely also misses targets. Processes spawned by broker carry **broker's MCP config (containing `org-broker`) in argv via `--mcp-config`**, so use that to narrow the population.

```bash
# 1) Enumerate argv narrowed to broker-spawned only (only those whose --mcp-config contains org-broker)
ps -eo pid,args | grep -iE "(^| )(claude|codex)( |$)" | grep -v grep \
  | grep -- "--mcp-config" | grep -i "org-broker"

# 2) Billing-neutrality negative check: confirm the broker panes narrowed above have no headless / exec series in argv
ps -eo args | grep -iE "(^| )(claude|codex)( |$)" | grep -v grep \
  | grep -- "--mcp-config" | grep -i "org-broker" \
  | grep -nE -- "-p( |$)|--print|--headless|--output-format|--input-format| exec | review |--mcp-server" \
  && echo "NG: detected headless/exec flag in broker pane (billing-incurring launch)" \
  || echo "OK: no headless/exec flag in broker pane (interactive TUI = billing-neutral)"

# 3) Reconcile the population (optional, recommended): confirm the count from (1) matches the number of broker-bound panes in list_panes
#    (reconcile pid against dispatcher/secretary list_panes to detect missing identification / surplus)
```

Expected: each broker pane's argv is composed only of **interactive flags** like `--mcp-config <broker>` / `--model` / `--permission-mode`, and the negative check returns `OK`.

> **Note**: ps inspection is performed in **a host session where the broker pane is live** (the actual pane is not visible from a sandbox with PID namespace isolation). The spawn-time guard (§6.1) is the primary defense, and the runtime attestation via ps is the secondary confirmation - the two stages guarantee billing-neutrality. Filtering by `--mcp-config` is a primary narrowing based on the structural characteristic of broker panes; when strictness is required, close the population surplus/shortage by reconciling against `list_panes` in (3).

---

## 7. Cleanup of verification debris (dogfooding of condition (5))

The test state created by the verification in this runbook is closed within a **test directory outside the repo**, and does not generate production `.state/broker/`. After verification, execute the §5(5) procedure **against the test path** to leave no trace.

```bash
CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root (adjust to environment)

# Confirm the test state-dirs used in verification (must be outside the repo)
ls -d /tmp/claude/broker-smoke-* /tmp/claude/usercommon-settings.json 2>/dev/null

# Reconcile unread in the journal (run the §5(5) script with BROKER_STATE pointed at the test path) -> dispose if fine
# (/tmp is ephemeral. Archive or delete per operational rule)

# Final confirmation that production .state/broker is ungenerated (both canonical root absolute path and directly under current worktree)
test -e "$CANON_ROOT/.state/broker" && echo "NG: production .state/broker exists" || echo "OK: production .state is unchanged"
test -e "$PWD/.state/broker" && echo "NG: .state/broker exists directly under worktree" || echo "OK: directly under worktree is also unchanged"
```

---

## 8. Related

- Design SoT: transport-lab `docs/design/ja-migration-plan.md` §5 (integration seam) / §5.5 (coexistence & rollback) / §8 Issue G (dogfood gate)
- Contract: [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, proposed / awaiting ratification)
- Secretary's operational differences between the two transports: [`CLAUDE.md`](../../CLAUDE.md) "transport (transport) both systems"
- spawn ritual (dev-channel approval -> folder-trust approval): [`.dispatcher/references/spawn-flow.md`](../../.dispatcher/references/spawn-flow.md) 3-3b
- transport accessor (single ja-side seam): [`tools/transport.py`](../../tools/transport.py)
- user_common allowlist projection: [`tools/org_setup_prune.py`](../../tools/org_setup_prune.py) `--user-common-allowlist`
- attention watcher operational style: [`attention-watch.md`](attention-watch.md)
