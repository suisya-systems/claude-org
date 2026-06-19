# broker dogfood operations runbook

`claude-org-runtime broker serve` is the daemon for the **pure-backend transport layer (`org-broker`)** that replaces renga-peers. It provides a localhost HTTP MCP server + queue store + nudge delivery in a single process, and injects nudges into child panes via a terminal adapter (tmux / WezTerm). This document captures the startup, shutdown, lifecycle, and rollback procedures for the broker daemon as **the precursor to running production ja with `ORG_TRANSPORT=broker`** under Epic #6 Issue G (#515).

The design SoT is transport-lab `docs/design/ja-migration-plan.md` §5 (ja integration seam) / §5.5 (coexistence / rollback) / §8 Issue G (dogfood gate). The contract source of truth is [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, proposed / awaiting ratification). For the secretary-side operational differences between the two transports, see [`CLAUDE.md`](../../CLAUDE.md) "Transport (two systems)". For the spawn ritual, see [`.dispatcher/references/spawn-flow.md`](../../.dispatcher/references/spawn-flow.md) 3-3b.

> **Scope and untouchable constraints**: This runbook is a "procedure to enable real runs", and **the broker live run of production ja (org-start hijack) will be done later in Track 3 (user hands-on)**. All procedures in this document start and stop the daemon under a **test state-dir (a separate directory, not `.state/broker/`)** and are written on the premise of not polluting the production `.state/`. **The default `renga` is not removed and remains permanently active as an opt-in fallback** (a safety net for rollback).

> **Verification status (2026-06-11, runtime 0.1.17 / tmux 3.2a / WSL2)**: All the startup, shutdown, lifecycle, and dry-run commands in this document were verified on a worker worktree environment with real hardware. Key points from the raw logs are embedded in each section.

---

## 1. Role and prerequisites

- **Inputs / control**:
  - Environment variable `ORG_TRANSPORT` (`renga` | `broker`, unset = default `renga`). The daemon itself does not read the flag, but the ja-side generator (§4) follows the flag and emits the broker surface allowlist.
  - CLI arguments (`--port` / `--host` / `--state-dir` / `--backend` / `--no-nudge`, §2.1).
- **Outputs / side effects**:
  - localhost HTTP MCP endpoint (default `http://127.0.0.1:48720/mcp`).
  - queue store + JSONL journal (`<state-dir>/queue.jsonl`, default state-dir = `.state/broker`).
  - nudge injection into child panes (via the terminal adapter, disabled with `--no-nudge`).
- **Dependency direction (one-way)**: `broker → terminal / dispatcher.choose_split`. **claude-org-ja does not import broker** (inactive at the renga default flag).
- **Observability (important)**: With the tmux backend, the child panes that broker spawns (dispatcher / workers) start as **detached, independent sessions** and do not appear on the screen by default (the secretary stays as a logical pane on the human's local terminal). For the attach path to peek at running child panes read-only, see §8.
- **CLI name caveat (important)**: The startup command is **`claude-org-runtime broker serve`** (a top-level CLI subcommand). `claude-org-runtime-broker` is the CLI's `prog` name (the header notation in `--help`) and **no such console_script exists**. `python -m claude_org_runtime.broker serve` is an equivalent invocation.

```
$ claude-org-runtime broker --help
usage: claude-org-runtime broker [-h] {serve} ...
    serve     Start the org-broker daemon on localhost (Ctrl+C to stop).
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
| `--port` | `48720` (`DEFAULT_PORT`) | localhost bind port. `0` means ephemeral (OS-assigned; the actual port appears in the `listening on` line of the startup log). |
| `--host` | `127.0.0.1` | bind host. Localhost only by design. |
| `--state-dir` | `.state/broker` (`DEFAULT_STATE_DIR`, CWD-relative) | Where `queue.jsonl` is written. **For verification, always pass a separate directory** (§2.3 / §7). |
| `--backend` | auto-selected by OS (POSIX=`tmux` / Windows=`wezterm`) | terminal adapter. `VALID_BACKENDS = (wezterm, tmux)`. Ignored when `--no-nudge` is set. |
| `--no-nudge` | (disabled) | Do not construct a terminal adapter; disable nudge delivery (**queue only**). Use this when you only want to check end-to-end connectivity, independent of the backend. |

`serve` blocks in the foreground (stops on `Ctrl+C` / `SIGINT`). At startup it issues one token for manual verification and prints the JSON to pass to `--mcp-config` on stdout:

```
org-broker listening on http://127.0.0.1:48803/mcp
queue store: /<state-dir>/queue.jsonl
manual test token: <token>
mcp-config: {"mcpServers": {"org-broker": {"type": "http", "url": "...", "headers": {"Authorization": "Bearer <token>"}}}}
```

### 2.2 Startup / stop commands (production form)

The startup form for production ja (Track 3, user hands-on) is the following. **This section presents the command form only; in this document's verification we execute only the test state-dir variant in §2.3.**

```bash
# Start (default state-dir = .state/broker, tmux backend auto-selected)
claude-org-runtime broker serve

# Stop: Ctrl+C (SIGINT) on the foreground serve. The journal records one line of broker_stopped.
# If started in the background, send SIGINT to the PID:
#   kill -INT <pid>
```

### 2.3 Test state-dir startup -> connectivity -> shutdown (procedure proving production `.state` is untouched)

Verification **must never touch production `.state/broker/`**. Pass a temporary directory to `--state-dir` and confirm that `queue.jsonl` is created only under that test path.

> **cwd drift caveat (mandatory)**: The default for `--state-dir` is **CWD-relative** `.state/broker`. A worker worktree and the canonical claude-org root have different `.state/`, so hitting the relative path bare makes "which `.state` am I looking at?" ambiguous and risks a wrong untouchability check / pollution of production `.state`. In this document we **pin the canonical root as an absolute path variable `CANON_ROOT`, and pin the test state-dir as an absolute path variable `TEST_STATE` outside the repo**, and never hit relative `.state/broker` bare-handed.

```bash
# 0) Pin the prerequisite variables (do not hit relative paths bare)
CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root with production .state/broker (adjust to your env)
TEST_STATE=/tmp/claude/broker-smoke-A               # test state-dir (must be an absolute path outside the repo)

# 1) Prepare the test state-dir (create parent dir + use an unused path to avoid mixing existing logs)
mkdir -p "$TEST_STATE"
test -e "$TEST_STATE/queue.jsonl" && echo "WARN: existing queue.jsonl found. Use a different path or move it aside before verifying"

# 2) Start (use --no-nudge to verify connectivity backend-independently. -u flushes stdout immediately)
python3 -u -m claude_org_runtime.broker serve \
    --state-dir "$TEST_STATE" --port 48799 --no-nudge
```

From a separate terminal (or a driver script), hit the HTTP MCP with the token shown in the startup log:

| Step | Expectation |
|---|---|
| `initialize` | `serverInfo = {"name": "org-broker", "version": "0.1.0"}` + `Mcp-Session-Id` header assigned |
| `tools/list` (worker token) | `["check_messages", "list_peers", "send_message", "set_summary"]` -- the **messaging 4 surface only** (tier gating, §3.4) |
| `tools/call send_message` (to self) | `{"ok": true, "delivered_to": "manual-test"}` |
| `tools/call check_messages` | At-most-once drain of the `hello broker` you just sent |

Stop by sending `SIGINT` to serve. **Clean shutdown returns exit code 0.**

**Untouchability check on `.state` (mandatory)**: After verification, confirm that production `.state/broker/` was not created. The queue is written only to the test path you passed.

```bash
# The queue exists only under TEST_STATE
ls "$TEST_STATE/queue.jsonl"
# Production (absolute path under canonical root) must not be generated. Do not use relative .state/broker.
test -e "$CANON_ROOT/.state/broker" && echo "NG: production .state/broker was polluted" || echo "OK: production .state unchanged"
# Make sure no verification debris was left directly under the current worktree either (prevents CWD-relative default mix-ups)
test -e "$PWD/.state/broker" && echo "NG: .state/broker was created directly under the worktree" || echo "OK: worktree root unchanged"
```

> **Verification log (2026-06-11, real hardware)**: Both `--no-nudge` and `--backend tmux` succeeded for the `initialize -> tools/list -> send_message -> check_messages` round trip and **exited with code 0** on `SIGINT`. `tools/list` returned the messaging 4 surface only on a worker tier. Production `.state/broker/` was not generated (`queue.jsonl` only under the test path). The tmux backend's adapter is lazily constructed and start / stop succeeds even without a live tmux server (the messaging probe is skipped because there is no child pane to actually inject nudges into).

---

## 3. start / stop / token / queue lifecycle

The broker's internal state transitions are split across `server` / `store` / `tokens` / `surface` under `claude_org_runtime/broker/`. There are four operationally important flows.

### 3.1 Token issuance (`tokens.py`)

- At spawn time, one **per-agent token** is issued (`issue_token`, `secrets.token_urlsafe(32)`). token <-> `AgentBind` (`agent_id` / `name` / `role` / `auth_role` / `pane_id` / `cwd` / `kind`).
- **`role` (display-only, mutable via `set_pane_identity`) and `auth_role` (immutable permission tier, fixed at issuance) are separated**. Tier gating uses `auth_role` only, and self-claimed display role cannot promote. The `auth_role` of a spawn child is capped by the caller's tier (`capped_auth_role`).
- `mcp_config_for(token)` generates the JSON to pass to `--mcp-config` (it embeds the token in a static `Authorization: Bearer <token>` header; env references `${VAR}` are not used).
- journal: `token_issued`.

### 3.2 Registration (HTTP handler in `server.py`)

- When the Claude / Codex in a child pane reaches `initialize` (MCP), `AgentBind.registered` becomes `True` (`registered_at` recorded). **Only registered binds are delivery targets** (prevents delivery to unconnected / DELETE-d clients).
- journal: `agent_registered`.

### 3.3 Queue store + nudge delivery (`store.py` / `server.py`)

- `send_message` (`enqueue`) creates an entry with **token-derived attribution** (self-claim is not allowed). The destination-registered check and queue append happen atomically in the **same lock scope**, then `_journal` and `_trigger_nudge` are called outside the lock (decoupling queue persistence from PTY injection / avoiding double-acquire deadlock on a non-reentrant Lock).
- Nudge delivery injects **only a fixed 1-line payload via PTY** and does not carry the body (the receiver uses `check_messages` to pull = push -> pull model). On adapter failure or non-arrival, it retries up to `nudge_defer_interval` (default 2.0s) x `nudge_defer_max_tries` (default 30).
- `check_messages` (`drain`) returns by emptying the queue **at-most-once**.
- journal: `message_enqueued` -> `nudge_sent` / `nudge_deferred` / `nudge_failed` -> `queue_drained`.

### 3.4 Tier gating (`surface.py`)

The public surface **changes structurally** by `auth_role` (default-deny allowlist). A tool not listed in `tools/list` is rejected with `[tool_not_authorized]` even if called (the allowlist is one half of double defense).

| auth_role tier | Public surface |
|---|---|
| worker / curator / unknown | messaging 4 (`send_message` / `check_messages` / `list_peers` / `set_summary`) |
| dispatcher | messaging 4 + ops (`list_panes` / `inspect_pane` / `send_keys` / `poll_events` / `close_pane` / `set_pane_identity` / `spawn_claude_pane` / `spawn_codex_pane`) |
| secretary | dispatcher's surface + `spawn_pane` (secretary-only) |

> `new_tab` / `focus_pane` are **not in** the broker surface (intentional exclusion). Initial surface = 12 ported faces + `spawn_codex_pane` = 13 faces.

### 3.5 Shutdown / revocation

- daemon shutdown: `stop()` shuts down + closes the HTTP server and writes `broker_stopped` to the journal.
- session end (MCP `DELETE`): the bind's `session_id` is invalidated and `registered = False` (so a disconnected client is not left in `list_peers` / delivery targets). journal: `session_closed`.
- pane close (`close_pane`): after killing via the adapter, registry pop and token revoke happen atomically in one lock scope. journal: `pane_closed` + event `pane_exited`.

### 3.6 Journal event list (`queue.jsonl`)

Appended one JSON per line to `<state-dir>/queue.jsonl`. Operational observation points:

```
broker_started -> token_issued -> agent_registered -> message_enqueued
  -> nudge_sent / nudge_deferred / nudge_failed -> queue_drained
  -> session_closed / pane_closed -> broker_stopped
```

> **Verification log (real hardware, messaging round trip)**: Confirmed `broker_started -> token_issued -> agent_registered -> message_enqueued(chars=12) -> queue_drained(count=1) -> broker_stopped` in one cycle.

### 3.7 broker additional error codes

In addition to the renga codes, broker can return the following. The secretary / dispatcher routes unknown codes to escalation via the default branch (see [`CLAUDE.md`](../../CLAUDE.md) "Error branches").

| Code | Trigger |
|---|---|
| `[token_invalid]` | Bearer token is not in the bind table / revoked (HTTP 401, JSON-RPC -32001) |
| `[session_invalid]` | A method other than `initialize` was called first |
| `[tool_not_authorized]` | A tool outside the auth_role tier's public surface was called |
| `[no_backend]` | Pane operation called while the terminal adapter is absent (`--no-nudge` startup) (= adapter_unavailable) |
| `[nudge_failed]` | Nudge injection did not arrive within the defer cap |
| `[peer_not_found]` | `send_message` destination is not in a registered bind |
| `[name_taken]` | pane name duplicated |

---

## 4. Settings regeneration dry-run with `ORG_TRANSPORT=broker`

Dry-run the **transport-descriptor-driven generator** that landed in Epic #6 D/E with `ORG_TRANSPORT=broker` and confirm that the broker surface allowlist comes out. **No real files are written.**

### 4.1 Single SoT (descriptor)

The ja-side transport accessor [`tools/transport.py`](../../tools/transport.py) consumes the runtime's transport surface descriptor (`claude_org_runtime.transport`) as its only SoT (no hard-coding). Resolution order is **explicit argument > `ORG_TRANSPORT` env > default `renga`**. Allowlist generation goes through `claude_org_runtime.settings.generator.transport_allowlist(role, transport=...)`.

### 4.2 Per-role allowlist dry-run

```bash
# Compare the projection of default renga (unset) vs broker per role (read-only, no writes)
for role in worker curator dispatcher secretary; do
  echo "--- $role renga(default) ---"
  python3 -c "from claude_org_runtime.settings.generator import transport_allowlist as t; print(t('$role'))"
  echo "--- $role broker ---"
  ORG_TRANSPORT=broker python3 -c "from claude_org_runtime.settings.generator import transport_allowlist as t; print(t('$role'))"
done
```

| role | renga (default) | broker (`ORG_TRANSPORT=broker`) |
|---|---|---|
| worker / curator | `mcp__renga-peers__*` 14 surfaces | `mcp__org-broker__*` messaging 4 |
| dispatcher | `mcp__renga-peers__*` 14 surfaces | messaging 4 + ops 8 (does not include `spawn_pane`) |
| secretary | `mcp__renga-peers__*` 14 surfaces | messaging 4 + ops + `spawn_pane` + `spawn_codex_pane` (13) |

> The renga default is a model where the same surface (14 faces) for all roles is narrowed by the allowlist. broker **structurally** gates by role tier, so the allowlist becomes one half of double defense (safe side).

### 4.3 `~/.claude/settings.json` user_common allowlist regeneration dry-run

[`tools/org_setup_prune.py`](../../tools/org_setup_prune.py) `--user-common-allowlist` projects the user_common (`~/.claude/settings.json`) MCP `permissions.allow` onto the active transport. **For verification, point `--user-common-settings-path` at a test path so the real `~/.claude/settings.json` is not touched, and pass `--dry-run`.**

```bash
# Prepare a test settings file (with renga entries) and dry-run
TEST_SET=/tmp/claude/usercommon-settings.json   # NOT the real ~/.claude/settings.json

# Make a test settings file with renga messaging entries (empty / missing would not produce the expected drop-renga output)
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

# broker: drop renga-peers, guarantee org-broker messaging tier (dry-run is display only)
ORG_TRANSPORT=broker python3 tools/org_setup_prune.py --user-common-allowlist --dry-run \
    --user-common-settings-path "$TEST_SET"
```

Expected output:

```
# renga (default)
[org_setup_prune] user_common allowlist: transport=renga (default); no-op -- ~/.claude/settings.json unchanged ...

# broker
=== user_common allowlist (transport=broker): /tmp/claude/usercommon-settings.json ===
  - mcp__renga-peers__send_message      (renga messaging dropped below)
  + mcp__org-broker__send_message       (org-broker messaging added below)
  ...
```

> **Verification log (real hardware)**: Default renga was a strict no-op (the test file was unchanged down to the byte). With `ORG_TRANSPORT=broker`, the diff renga messaging 4 -> org-broker messaging 4 was shown via dry-run. **Because of `--dry-run`, zero real writes** (the test file's contents were confirmed unchanged). Non-MCP entries such as `Bash(...)` are preserved in order.

---

## 5. Concretizing the 5 rollback conditions (SoT §5.5)

A complete rollback from `ORG_TRANSPORT=broker` -> `renga` is **not immediately restored just by flipping the flag** for running broker-spawned panes (they still hold `--mcp-config` / pull-premised prose). Execute the **5 completion conditions** of SoT §5.5 in order.

> **Prerequisite variables (cwd-drift avoidance)**: The commands below do not hit relative `.state/broker` bare. Pin the state-dir that the daemon actually used in `serve --state-dir` to an absolute path variable, and also pin the canonical root. In production reflection (Track 3), `BROKER_STATE` points at the production `.state/broker`.
>
> ```bash
> CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root (adjust to your env)
> BROKER_STATE="$CANON_ROOT/.state/broker"            # the --state-dir the daemon was given at serve
> ```

### (1) Flag rollback

```bash
# Roll env back to renga (default). Newly spawned panes point at renga.
unset ORG_TRANSPORT
# If you persisted it in shell settings, remove it from there too:
#   grep -rn "ORG_TRANSPORT" ~/.bashrc ~/.zshrc ~/.profile
```

**Check**: `python3 -c "from claude_org_runtime.transport import resolve_transport as r; print(r())"` returns `renga`.

### (2) Regenerate generated artifacts (back to the renga allowlist)

Once the flag is back to renga, **the generator (per-role `settings.local.json`) is identity (bit-equivalent)**. Actually regenerate the artifacts to revert to the renga surface.

```bash
# First check the diff with a dry-run (the diff back to renga shows up if broker surfaces remain)
python3 tools/org_setup_prune.py --all --dry-run

# If there are no issues, apply it (writes back the renga allowlist; .bak is left behind)
python3 tools/org_setup_prune.py --all
```

**user_common (`~/.claude/settings.json`) is handled separately (important)**: `--user-common-allowlist` is a **complete no-op in renga mode** (because the SoT for the renga allowlist is the org-setup skill + permissions.md, not this tool, the file is not touched at all). So if you have applied broker via dogfood (and `mcp__org-broker__*` is in user_common), running `--user-common-allowlist --dry-run` in renga will **not roll back the broker surface**. Roll back user_common explicitly via one of the following:

```bash
# Method A (recommended): restore the .bak created when broker was applied
#   backup naming is settings.json.bak.<YYYYMMDD-HHMMSS> (backup_path)
ls -t ~/.claude/settings.json.bak.* 2>/dev/null | head     # check the most recent backup
# cp <.bak you verified> ~/.claude/settings.json           # visually confirm content and restore

# Method B: if no backup exists, swap the messaging surface manually (org-broker -> renga-peers)
#   In permissions.allow of ~/.claude/settings.json
#   Replace "mcp__org-broker__{send_message,check_messages,list_peers,set_summary}"
#   with "mcp__renga-peers__..." (do not touch non-MCP entries)
```

**Check**: confirm `mcp__org-broker__*` does not remain in **both** the per-role `settings.local.json` and **user_common (`~/.claude/settings.json`)**.

```bash
# Per-role settings under the repo. A glob (*/.claude/) does not pick up hidden role dirs
# (.dispatcher/.claude/ / .curator/.claude/ etc.), and in zsh no-match means grep itself
# does not run and may wrongly report OK. Avoid globs; recursively grep from the repo root
# (grep -r descends into hidden dirs too). Restrict to settings*.json to avoid false hits.
if grep -rl --include="settings*.json" "mcp__org-broker__" . 2>/dev/null | grep -q .; then
  echo "NG: broker surface remains on the repo side:"; grep -rl --include="settings*.json" "mcp__org-broker__" . 2>/dev/null
else
  echo "OK: no broker surface on the repo side"
fi
# Don't forget to check user_common (home settings.json)
grep -l "mcp__org-broker__" ~/.claude/settings.json 2>/dev/null && echo "NG: broker surface remains in user_common" || echo "OK: no broker surface in user_common"
```

### (3) Respawn the active broker panes (restart via the renga route)

Running broker-spawned panes do not come back with just a flag rollback. Suspend / resume or respawn via the renga route.

```bash
# Identify the current broker panes (from the renga secretary / dispatcher)
#   mcp__renga-peers__list_panes  to confirm the pane list
# Close each pane that holds a broker token in turn -> respawn via the renga route (the normal delegation flow of org-delegate)
# Pane control is restricted to dispatcher/secretary, so swap messaging back to renga first, then follow up with panes (the 2 stages of §5.5).
```

**Check**: no panes with broker binds remain in `list_peers` / `list_panes`.

### (4) Broker daemon shutdown order (revoke remaining panes -> daemon stop)

**Order matters**: first revoke (close) the remaining panes to remove them from delivery targets, then finally stop the daemon.

```bash
# 1) Close any remaining broker panes (this revokes the token; close_pane journal: pane_closed)
#    Use close_pane from renga / dispatcher for each broker pane.
# 2) Once all are revoked, stop the daemon (SIGINT to the foreground serve, or)
kill -INT <broker_pid>
# 3) Confirm broker_stopped is recorded at the end of the journal
tail -n 3 "$BROKER_STATE/queue.jsonl"
```

### (5) Confirm old token / queue store disposal (no unread / no bind remnants in `.state/broker/`)

```bash
# Reconcile that no unread (enqueued but not drained) messages remain via the journal.
# queue_drained has count=N, so compare on the sum of N rather than "event count" (avoids misjudging multi-drain).
BROKER_STATE="${BROKER_STATE:?Pin BROKER_STATE first (§5 prerequisite variables)}" \
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
    print("OK: queue.jsonl is gone (already disposed)"); raise SystemExit
unread = enq - drained_msgs
print(f"enqueued={enq} drained_msgs={drained_msgs} unread={unread}")
print("OK: no unread" if unread <= 0 else f"NG: {unread} unread remain (must be drained before stopping the daemon)")
PY

# Token / bind are in-memory in the process (disappear when the daemon stops; not persisted).
# Dispose of the queue store file so no traces remain (in environments where rm is not allowed, truncate / archive):
#   mv "$BROKER_STATE" "$BROKER_STATE.archived-$(date +%Y%m%d)"   # or delete per operational rules
```

> **Token / bind persistence**: `AgentBind` is only in-memory in the daemon process (`token_issued` as an event remains in the journal, but token values and the bind table are not persisted). Stopping the daemon erases binds. What remains is only `queue.jsonl` (journal + undrained messages), so (5) is closed by reconciling unread in this file and disposing of it.

---

## 6. How to take the cost-neutral attestation

Confirm with real argv that every agent broker spawns is an **interactive TUI (no headless)**. This serves as evidence of cost neutrality (no non-interactive startup like `claude -p` / `codex exec` that incurs API billing).

### 6.1 Defense-in-depth structure (spawn-time guard)

Broker's cost neutrality is structurally guaranteed by **spawn-time default-deny allowlist** (`surface.py`):

- `build_claude_argv` / `build_codex_argv` allow only interactive TUI flags, and `_guard_interactive_claude_argv` / `_guard_interactive_codex_argv` **uniformly reject tokens outside the allowlist (post-flag subcommands / bare positionals / `--` / unknown flags / headless flags)**.
- Claude headless blacklist: `-p` / `--print` / `--headless` / `--output-format` / `--input-format`, etc. On the codex side, subcommands (`exec` / `review` / `*-server` / `apply` / `sandbox`, etc.) fall through as bare positionals.
- Flags that take a value have arity (a headless flag in the value position is also blocked at the second stage), and `argv[0]` is judged by basename (so absolute-path invocations are not false-rejected).

### 6.2 Real argv inspection (runtime attestation)

On the production host (a session with live broker panes), inspect the actually running argv with ps. **Confirm that no headless flag / subcommand is present.**

The key is to **scope to broker-spawned panes**. The host may have unrelated headless executions in parallel (CI / manual `claude -p` etc.), so an indiscriminate grep over all claude/codex picks up false positives and conversely misses target identification. Broker-spawned processes have **`--mcp-config` carrying broker's MCP config (which includes `org-broker`)** in their argv; use that to narrow the population.

```bash
# 1) Enumerate argv scoped to broker-spawned (only those whose --mcp-config includes org-broker)
ps -eo pid,args | grep -iE "(^| )(claude|codex)( |$)" | grep -v grep \
  | grep -- "--mcp-config" | grep -i "org-broker"

# 2) Cost-neutral negative check: argv of the broker panes scoped above contains no headless / exec-family
ps -eo args | grep -iE "(^| )(claude|codex)( |$)" | grep -v grep \
  | grep -- "--mcp-config" | grep -i "org-broker" \
  | grep -nE -- "-p( |$)|--print|--headless|--output-format|--input-format| exec | review |--mcp-server" \
  && echo "NG: headless/exec flag detected on a broker pane (billable startup)" \
  || echo "OK: no headless/exec flag on broker panes (interactive TUI = cost-neutral)"

# 3) Population cross-check (optional, recommended): confirm that the broker-bind pane count from list_panes matches the count from (1)
#    (Cross-check pids against the dispatcher / secretary's list_panes to detect missing / surplus identification)
```

Expected: each broker pane's argv is composed only of **interactive flags** such as `--mcp-config <broker>` / `--model` / `--permission-mode`, and the negative check returns `OK`.

> **Caution**: The ps inspection must be done on the **host session where the broker panes are live** (the actual panes are not visible from inside a sandbox with a separated PID namespace). The spawn-time guard (§6.1) is the primary defense and the runtime attestation via ps is the secondary check, securing cost neutrality in two stages. The `--mcp-config` filter is the primary narrowing based on the structural feature of broker panes; when strictness is required, close the gap on the population with the `list_panes` cross-check in (3).

---

## 7. Cleanup of verification debris (dogfooding condition (5))

The test state created by this runbook's verification is closed to a **test directory outside the repo**, and production `.state/broker/` is not generated. After verification, run the procedure in §5(5) **against the test path** and leave no trace.

```bash
CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root (adjust to your env)

# Confirm the test state-dir used in verification (must be outside the repo)
ls -d /tmp/claude/broker-smoke-* /tmp/claude/usercommon-settings.json 2>/dev/null

# Reconcile journal unread (run the §5(5) script against BROKER_STATE=test path) -> dispose if OK
# (/tmp is ephemeral. Archive or delete per operational rules.)

# Final confirmation that production .state/broker has not been created (both canonical root absolute path and current worktree root)
test -e "$CANON_ROOT/.state/broker" && echo "NG: production .state/broker exists" || echo "OK: production .state unchanged"
test -e "$PWD/.state/broker" && echo "NG: .state/broker exists directly under the worktree" || echo "OK: worktree root unchanged"
```

---

## 8. Observability -- peek at a running org (attach path)

Broker (tmux backend) starts the **child panes it spawns (dispatcher / workers)** as **detached, independent tmux sessions** on a dedicated socket. Unlike renga's "visible split panes in the same tab", these child panes do not appear on the human screen by default, and *ambient awareness* -- "how many workers are running and which ones are stuck" being visible without any effort -- is quietly lost. The existing overview means cannot fill this experience by themselves:

| Means | Provides | Missing |
|---|---|---|
| Dashboard (`localhost` status UI) | `state.db`-based status overview (worker list, transitions, activity) | Not the **raw screen** of each pane |
| attention watcher ([`attention-watch.md`](attention-watch.md)) | Push notifications on anomalies / gates | Not the kind of "watch when healthy and be reassured" continuous observation |
| **tmux attach (this section)** | **Raw screen of broker-spawned child panes (dispatcher / workers)** | Currently per-session attach as noted below (single-session is the future form in §8.2) |

This section shows the **read-only attach path to peek at the running broker org**. **This path is tmux-backend (POSIX / WSL2) specific**. The WezTerm backend (Windows, `isolated_session=False`) spawns each pane as a GUI window so the screen is visible from the start and attach is not needed.

> **Scope (important)**: What attach lets you see is **only the child panes that broker `adapter.spawn`-ed (dispatcher / workers)**. **The secretary (root secretary) is a logical pane that does not have a real adapter pane** (a bookkeeping entry, `register_logical_pane`, `claude_org_runtime/broker/server.py`), and it runs as-is on the human's local terminal that started the org (it does not appear on the spike socket). So what this path fills is the "workers / dispatcher raw screens are not visible" gap; the secretary is in front of the human to begin with.

### 8.1 Today -- attach to an independent session (runtime terminal adapter)

The current runtime terminal adapter (tmux, `claude_org_runtime.terminal.tmux`) creates the child panes broker spawns (dispatcher / workers) as **independent detached sessions on a dedicated socket `claude-org-spike`** (session name `spike-<pid>-<seq>`, `isolated_session = True`). It is socket-separated from existing tmux servers (renga etc.), so observation requires the explicit socket name `-L claude-org-spike`.

```bash
# 1) List the broker sessions that exist (read-only. Explicit socket is mandatory)
tmux -L claude-org-spike list-sessions
#   Example:  spike-12345-1: 1 windows (created ...)   <- each line is one child pane (seq starts at 1)

# 2) Attach read-only to the session you want to peek at (-r is read-only. Won't break a worker on stray keys)
tmux -L claude-org-spike attach -r -t spike-12345-1
```

Post-attach controls (prefix defaults to `Ctrl-b`):

| Action | Key | Use |
|---|---|---|
| Detach (stop observing and leave) | `Ctrl-b` -> `d` | Leave with the session still alive (does not affect the process) |
| Switch to another session | `Ctrl-b` -> `s` | Pick from the session list. **Today is per-session, so seeing the whole picture requires switching** |

> **Reason `-r` (read-only) is the default**: Attaching to the independent session connects directly to the worker's live TUI. Without `-r`, keystrokes during observation can land in the worker session (interventions are designed to be confined to the secretary/dispatcher `send_keys` route, so a human-hand attach is restricted to observation).

> **Verification log (2026-06-13, runtime 0.1.22)**: Socket name `claude-org-spike` / session name `spike-<pid>-<seq>` / `isolated_session = True` were confirmed in `claude_org_runtime/terminal/tmux.py` (the `SPIKE_SOCKET` constant / `_new_session_name`) on real hardware. The command shapes `list-sessions` (multi-session enumeration) / `attach -r` (read-only flag acceptance) / `kill-server` (cleanup) were end-to-end-tested on a scratch socket (attach against a real broker org was not done in this verification due to interactive blocking).

### 8.2 Future -- one-shot `attach` via single-session (transport-lab design, not yet landed)

transport-lab `docs/design/broker-native-roles.md` §3.4 (defect 4 mitigation) has confirmed a design that restructures the tmux adapter into a **multi-pane/window composition within a single `claude-org` session**. After it lands, the following one command lets you see the broker-managed panes (dispatcher / workers) at a glance, and standard pane nav (`Ctrl-b` arrow keys) works, so the per-session switching of §8.1 becomes unnecessary:

```bash
tmux attach -r -t claude-org   # Path after single-session-ization (§3.4 / R1) (-r = read-only). Socket -L specification also becomes unnecessary.
```

- This is a **change to the runtime's terminal adapter (`claude_org_runtime/terminal/`)**, and ja consumes it via a runtime pin bump (not a procedure of this runbook on the ja side). **In the current runtime (independent sessions), §8.1 is the only attach path.**
- Pane death is handled by differential reconcile by design, and §3.4 concludes that the constant benefit of observability outweighs the trade-off of single-session-ization (session-level failures spreading to all panes).
- An observer-dedicated command (read-only tile display of broker-managed panes) / pane raw-screen tile display on the dashboard, considered for the observability gap, become redundant because `attach -r -t claude-org` (read-only) after single-session-ization provides equivalent overview, so this runbook does not adopt them (necessity is reassessed in real operation after single-session-ization).

---

## 9. Related

- Design SoT: transport-lab `docs/design/ja-migration-plan.md` §5 (integration seam) / §5.5 (coexistence / rollback) / §8 Issue G (dogfood gate)
- Contract: [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, proposed / awaiting ratification)
- Secretary-side operational difference between the two transports: [`CLAUDE.md`](../../CLAUDE.md) "Transport (two systems)"
- Spawn ritual (dev-channel approval -> folder-trust approval): [`.dispatcher/references/spawn-flow.md`](../../.dispatcher/references/spawn-flow.md) 3-3b
- Transport accessor (ja-side single seam): [`tools/transport.py`](../../tools/transport.py)
- user_common allowlist projection: [`tools/org_setup_prune.py`](../../tools/org_setup_prune.py) `--user-common-allowlist`
- attention watcher operational tone: [`attention-watch.md`](attention-watch.md)
- Observability single-session design (the future form of §8.2): transport-lab `docs/design/broker-native-roles.md` §3.4 (defect 4 -- independent tmux session problem)
