# broker dogfood operations runbook

`claude-org-runtime broker serve` is the daemon for the **pure-backend transport layer (`org-broker`)**, an **opt-in alternative implementation** of renga-peers (coexists with renga as the default operational frame, and is rollback-safe at any time; "alternative" does not mean replacing renga, it means an additional track that lines up next to it on an opt-in basis). It provides a localhost HTTP MCP server, queue store, and nudge delivery in a single process, and injects nudges into child panes via a terminal adapter (tmux / WezTerm). This document operationalizes the start, stop, lifecycle, and rollback of the broker daemon as **the preparation for running production ja with `ORG_TRANSPORT=broker`** under Epic #6 Issue G (#515).

The design SoT is the transport-lab `docs/design/ja-migration-plan.md` §5 (ja integration seams) / §5.5 (coexistence and rollback) / §8 Issue G (dogfood gate). The contractual SoT is [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14). For the operational difference at the Secretary between the two transport tracks, see [`CLAUDE.md`](../../CLAUDE.md) "Transport (transport) two-track"; for the spawn ritual, see [`.dispatcher/references/spawn-flow.md`](../../.dispatcher/references/spawn-flow.md) 3-3b.

> **Scope and untouchable constraints**: This runbook is "the procedure document that makes a real run possible"; **the real broker run of production ja (org-start hijack) will be done later under Track 3 (user hands-on)**. All procedures in this document start and stop the daemon under a **test state-dir (a different directory, not `.state/broker/`)**, on the premise of not polluting production `.state/`. **The default `renga` is not removed and stays always available as an opt-in fallback** (a rollback safety device). Here "default `renga`" refers to the **operational frame** (until the **Track 3** production broker real-run above activates, the operational default route is renga. The Issue G #515 coexistence dogfood itself was passed on 2026-06-14, ratifying broker as opt-in; what remains is only the production promotion = Track 3). Separately, in the **code-constant frame**, `claude_org_runtime.transport.DEFAULT_TRANSPORT` has flipped renga → broker in runtime 0.1.28 (Epic #586). The two frames point at different objects (operational route vs code constant) and do not conflict (two-frame note, Refs #604).

> **Verification status**: Each of the start / stop / lifecycle / dry-run commands was verified empirically on 2026-06-11 in a worker worktree environment with **runtime 0.1.17** / tmux 3.2a / WSL2 (the key points of the raw logs are embedded in each section). The §8 attach path was confirmed on 2026-06-13 with **runtime 0.1.22**. **The empirically verified broker-surface descriptions in this document are synchronized to runtime 0.1.22** (§1.1 setup / §2.1 serve flags `--root-role` / `--root-cwd` / §3.6 journal / §3.8 admin RPC and sidecar / §5(4)-(5) sidecar disposal). The serve / admin / sidecar surfaces added between 0.1.17 → 0.1.22 were cross-checked against `claude_org_runtime/broker/{cli,server,sidecar}.py` (0.1.22) (organizing #515 dogfood D2-D6). **Push-first addendum (0.1.24+)**: The §3.3 nudge-delivery description includes a positioning note for push-first (per-pane channel sidecar / claude/channel, runtime push-first 0.1.24+, design SoT transport-lab `docs/design/broker-native-roles.md` §9), but the above empirical verification is at the 0.1.22 surface; **the empirical verification of the push-first surface itself requires a separate run in a 0.1.24+ environment** (this addendum is a positioning note for prose consistency, not a re-verification of 0.1.24+ runs).

---

## 1. Role and prerequisites

- **Inputs / control**:
  - Environment variable `ORG_TRANSPORT` (`renga` | `broker`, unset = default `renga`). The daemon itself does not read the flag, but the ja-side generators (§4) emit the broker-side allowlist according to the flag.
  - CLI arguments (`--port` / `--host` / `--state-dir` / `--backend` / `--no-nudge` / `--root-role` / `--root-cwd`, §2.1).
- **Outputs / side effects**:
  - The localhost HTTP MCP endpoint (default `http://127.0.0.1:48720/mcp`) and the admin RPC endpoint (`/admin`, §3.8).
  - The queue store + JSONL journal (`<state-dir>/queue.jsonl`, default state-dir = `.state/broker`).
  - The daemon sidecar (`<state-dir>/daemon.json` for discovery metadata + `<state-dir>/admin.token` 0600 secret, §3.8; removed on graceful stop, left in place on SIGTERM).
  - Nudge injection into child panes (via the terminal adapter; disabled with `--no-nudge`).
- **Dependency direction (one-way)**: `broker → terminal / dispatcher.choose_split`. **claude-org-ja does not import broker** (with the flag default to renga, it is inert).
- **Observability (important)**: Under the tmux backend, the child panes that broker spawns (Dispatcher, Workers) are started as **detached, independent sessions** and are not on screen by default (the Secretary stays as a logical pane on the human's local terminal). For a read-only attach path to peek at running child panes, see §8.
- **CLI name note (important)**: The start command is **`claude-org-runtime broker serve`** (a subcommand of the top-level CLI). `claude-org-runtime-broker` is the CLI's `prog` name (the header text shown in `--help`); **no console_script exists** for it. You can also launch with `python -m claude_org_runtime.broker serve` for the equivalent effect.

```
$ claude-org-runtime broker --help
usage: claude-org-runtime broker [-h] {serve} ...
    serve     start the org-broker daemon on localhost (stop with Ctrl+C).
```

### 1.1 Isolated venv setup (D6)

To isolate the dogfood from the production environment, the broker org is run in an **isolated venv (a WSL/tmux-isolated clone)**. This venv needs both **`claude-org-runtime>=0.1.22`** (the version that carries the D2-D6 surface) and **`core-harness>=0.3.2`**.

- **Runtime 0.1.22 or higher is required**: The D2-D6 (`--root-role` / `--root-cwd` / `/admin` RPC / sidecar) in this document are **surfaces that landed in 0.1.22**; they do not exist in 0.1.17-0.1.21. **However, ja's current pin is `claude-org-runtime>=0.1.17,<0.2` (lower bound 0.1.17)**, so `pip install -e .` does **not guarantee** 0.1.22 (the lower bound 0.1.17 may be resolved). In the dogfood, install 0.1.22+ explicitly with `pip install 'claude-org-runtime>=0.1.22,<0.2'` (or upgrade to the latest 0.1.x with `pip install -U`). To raise the lower bound permanently, bump the pin in `pyproject.toml` / `requirements.txt` separately (out of scope for this runbook).
- **core-harness is not a runtime dependency** (runtime's `Requires-Dist` is only `jsonschema`; runtime does not import `core_harness`). On the other hand, **ja-side tools** (`tools/check_role_configs.py` etc.) import `core_harness`, so it is required for ja org operation. `pip install claude-org-runtime` alone does not pull it in, and in the isolated venv ja tools will fail with `ImportError`. So **run `pip install -e .` from the ja repo** to resolve the `pyproject.toml` / `requirements.txt` pin **`core-harness>=0.3.2,<0.4`** (in a minimal install where only the runtime is installed, add `pip install 'core-harness>=0.3.2,<0.4'` explicitly).
- Pin rationale: `core-harness` is 0.x, so x-bumps (minors) may include breaking changes by policy, hence the range is pinned at `>=0.3.2,<0.4` (per the `requirements.txt` comment / design Q9-Q10).

```bash
# isolated venv example (at the root of an isolated clone)
python3 -m venv .venv && . .venv/bin/activate
pip install -e .   # resolve core-harness>=0.3.2 and claude-org-runtime>=0.1.17 per the pins
# however, the runtime lower bound from -e . is 0.1.17. The D2-D6 surface needs 0.1.22+, so override explicitly:
pip install 'claude-org-runtime>=0.1.22,<0.2'
# in a minimal install where only the runtime is installed, also add core-harness explicitly:
#   pip install 'core-harness>=0.3.2,<0.4'
# verify:
python3 -c "from claude_org_runtime import __about__; print(__about__.__version__)"   # 0.1.22 or higher
```

---

## 2. Empirical verification of broker daemon startup

### 2.1 `serve` options

```
$ claude-org-runtime broker serve --help
usage: claude-org-runtime broker serve [-h] [--port PORT] [--host HOST]
                                       [--state-dir STATE_DIR]
                                       [--backend {wezterm,tmux}] [--no-nudge]
                                       [--root-role {worker,curator,dispatcher,secretary}]
                                       [--root-cwd ROOT_CWD]
```

| Option | Default | Meaning |
|---|---|---|
| `--port` | `48720` (`DEFAULT_PORT`) | localhost bind port. `0` for ephemeral (OS-assigned; the actual port shows up in `listening on` in the startup log). |
| `--host` | `127.0.0.1` | bind host. Localhost-only by design. |
| `--state-dir` | `.state/broker` (`DEFAULT_STATE_DIR`, CWD-relative) | Write destination for `queue.jsonl` / `daemon.json` / `admin.token`. **For verification, always pass a different directory** (§2.3 / §7). |
| `--backend` | OS auto-select (POSIX=`tmux` / Windows=`wezterm`) | terminal adapter. `VALID_BACKENDS = (wezterm, tmux)`. Ignored under `--no-nudge`. |
| `--no-nudge` | (disabled) | Skip creating a terminal adapter and disable nudge delivery (**queue only**). Use this when you only want to confirm connectivity without backend dependency. |
| `--root-role` | `worker` (`DEFAULT_ROOT_ROLE`) | The **permission tier (auth_role) to bind the manually-verified root token to**. The public surface of `tools/list` is structurally narrowed to this tier (§3.4). Acceptance set `ROOT_ROLE_CHOICES = (worker, curator, dispatcher, secretary)`. Default `worker` = messaging 4 surfaces and behavior unchanged from the current; `secretary` exposes all 13. |
| `--root-cwd` | (when omitted, the daemon's startup cwd = `os.getcwd()`) | **Bind the root pane (the human-driven Secretary) cwd into the bind** (runtime#61). Relative `cwd` in `spawn_*` is resolved with this cwd as the base (absolute stays as-is). Even if a relative path is passed, it is **made absolute** relative to the daemon's startup cwd before being bound (the resolution anchor is always absolute). The **operational contract is that the daemon is started from the session root**, and that startup directory becomes the resolution anchor for relative spawns. If you start from somewhere other than the session root, make this flag explicit. |

> **Diff between 0.1.17 → 0.1.22 (D2)**: `--root-role` / `--root-cwd` are flags added in 0.1.22 (runtime#61). Without a cwd in the bind, a relative-cwd `spawn_*` from the human-driven Secretary loses its resolution anchor and is rejected / falls back to the wrong base; that is the root cause of runtime#61. When `--root-cwd` is omitted the daemon startup cwd is used, so **always start the daemon from the session root** (or make `--root-cwd` explicit).

`serve` blocks in the foreground. Stops have two paths: (a) `Ctrl+C` / `SIGINT`, or (b) the admin RPC `shutdown` (§3.8). Both pass through the `finally` of `run()` and stop gracefully, recording `broker_stopped` and removing the sidecar. On startup, one admin token is generated and written to the sidecar at 0600 (§3.8), and one root token for manual verification is issued; the JSON to pass to `--mcp-config` is printed to stdout:

```
org-broker listening on http://127.0.0.1:48803/mcp
admin RPC: http://127.0.0.1:48803/admin (token in /<state-dir>/admin.token)
daemon sidecar: /<state-dir>/daemon.json (backend=tmux)
queue store: /<state-dir>/queue.jsonl
manual test token (worker): <token>
root pane cwd (relative spawn anchor): /<root-cwd>
mcp-config: {"mcpServers": {"org-broker": {"type": "http", "url": "...", "headers": {"Authorization": "Bearer <token>"}}}}
root pane registered (logical, id=<pane_id>, role=worker)
```

> **Startup side effects (0.1.22)**: As above, on startup `<state-dir>/daemon.json` (discovery metadata, non-secret) and `<state-dir>/admin.token` (admin RPC auth token, 0600 secret) are written, and the root token is registered in the pane registry as a **logical pane** (`logical_pane_registered` journal, §3.6). For details see §3.8.

### 2.2 Start / stop commands (production form)

The form for starting up in production ja (Track 3, user hands-on) is as follows. **This section presents the command form; the verifications in this document only run the test state-dir version in §2.3**.

```bash
# Start (default state-dir = .state/broker, tmux backend auto-selected)
claude-org-runtime broker serve

# Stop (split by startup mode):
#   - Foreground serve (blocking in this shell): Ctrl+C (SIGINT). Graceful stop path =
#     run()'s finally invokes stop(); a broker_stopped line is left at the end of the journal
#     and the daemon.json / admin.token sidecar files are removed.
#   - Background daemon (started with nohup ... & etc.): send SIGTERM:
#       kill -TERM <pid>
#     SIGINT (kill -INT) does not take effect on a background daemon and the process survives
#     (reproduced twice in the 2026-06-13 rollback drill). Stop background daemons with SIGTERM.
#     However, SIGTERM does not pass through run()'s finally, so broker_stopped is not emitted,
#     and the daemon.json / admin.token sidecar files are left behind (must be discarded explicitly in §5(5)).
#     For background stop, confirm via "process gone + unread reconciliation + sidecar disposed" (§5(4)/(5)).
#   - Graceful alternative (recommended, signal-independent): call admin RPC shutdown (§3.8).
#     Even for a background daemon, it covers broker_stopped recording + automatic sidecar removal in one go.
```

### 2.3 Start → smoke → stop with a test state-dir (empirical proof that production `.state` is untouched)

The verification **must never touch production `.state/broker/`**. Pass a temporary directory to `--state-dir` and confirm that `queue.jsonl` is created only at that test path.

> **cwd drift caution (required)**: The default of `--state-dir` is **CWD-relative** `.state/broker`. Between worker worktrees and the canonical claude-org root, `.state/` are different things, so striking the relative path directly makes "which `.state` is being looked at" ambiguous and invites mistaken untouched-checks / production `.state` contamination. In this document, **fix the canonical root with an absolute path variable `CANON_ROOT` and the test state-dir with an absolute path variable `TEST_STATE` outside the repo**, and do not strike the relative `.state/broker` bare-handed.

```bash
# 0) Fix premise variables (do not strike relative paths bare-handed)
CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root holding production .state/broker (adapt to your environment)
TEST_STATE=/tmp/claude/broker-smoke-A               # test state-dir (must be an absolute path outside the repo)

# 1) Prepare the test state-dir (create parent dir + use an unused path to avoid mixing existing logs)
mkdir -p "$TEST_STATE"
test -e "$TEST_STATE/queue.jsonl" && echo "WARN: existing queue.jsonl present. Use a different path or move it aside before verifying"

# 2) Start (with --no-nudge to confirm connectivity independent of backend. -u flushes stdout immediately)
python3 -u -m claude_org_runtime.broker serve \
    --state-dir "$TEST_STATE" --port 48799 --no-nudge
```

From another terminal (or a driver script), hit the HTTP MCP with the token printed in the startup log:

| Step | Expected |
|---|---|
| `initialize` | `serverInfo = {"name": "org-broker", "version": "0.1.0"}` + `Mcp-Session-Id` header issued |
| `tools/list` (worker token) | Only the **messaging 4 surfaces** `["check_messages", "list_peers", "send_message", "set_summary"]` (tier gating, §3.4) |
| `tools/call send_message` (to self) | `{"ok": true, "delivered_to": "manual-test"}` |
| `tools/call check_messages` | At-most-once drain of `hello broker` just sent |

To stop, send `SIGINT` to serve. **Clean shutdown returns exit code 0**.

**Untouched-`.state` check (required)**: After verification, confirm that production `.state/broker/` was not created. The queue is written only at the test path you passed.

```bash
# Queue exists only under TEST_STATE
ls "$TEST_STATE/queue.jsonl"
# Production side (canonical root absolute path) must not be created. Do not use the relative .state/broker
test -e "$CANON_ROOT/.state/broker" && echo "NG: production .state/broker was polluted" || echo "OK: production .state is intact"
# Also no verification garbage directly under the current worktree (prevention against CWD-relative default mix-ups)
test -e "$PWD/.state/broker" && echo "NG: .state/broker created directly under worktree" || echo "OK: also intact directly under worktree"
```

> **Verification log (2026-06-11, empirical)**: For both `--no-nudge` and `--backend tmux`, the `initialize → tools/list → send_message → check_messages` round trip succeeded, and **exit 0** on `SIGINT`. `tools/list` showed only messaging 4 surfaces at worker tier. Production `.state/broker/` not created (only `queue.jsonl` at the test path). Under the tmux backend, even without a live tmux server, the adapter is lazily created and start / stop succeed (since there are no child panes for actual nudge injection, the messaging probe is skipped).

---

## 3. start / stop / token / queue lifecycle

The internal state transitions of broker are split into `server` / `store` / `tokens` / `surface` under `claude_org_runtime/broker/`. The four flows you need to know operationally:

### 3.1 token issuance (`tokens.py`)

- On spawn, issue one **per-agent token** (`issue_token`, `secrets.token_urlsafe(32)`). token ↔ `AgentBind` (`agent_id` / `name` / `role` / `auth_role` / `pane_id` / `cwd` / `kind`).
- **`role` (display-only, mutable via `set_pane_identity`) and `auth_role` (immutable permission tier, fixed at issue time) are separated**. Tier gating is decided by `auth_role` alone; self-reported display roles cannot escalate. The `auth_role` of a spawn child is capped by the caller tier (`capped_auth_role`).
- `mcp_config_for(token)` generates the JSON to pass to `--mcp-config` (the token is embedded in the static header `Authorization: Bearer <token>`; env references like `${VAR}` are not used).
- journal: `token_issued`.

### 3.2 Registration (HTTP handler in `server.py`)

- When the Claude / Codex in a child pane reaches `initialize` (MCP), `AgentBind.registered = True` (with `registered_at` recorded). **Only registered binds are delivery targets** (prevents delivery to unconnected / DELETEd clients).
- journal: `agent_registered`.

### 3.3 Queue store + nudge delivery (`store.py` / `server.py`)

- `send_message` (`enqueue`) creates the entry **by token-based attribution** (no self-reporting). The destination's registered check and queue append are done **atomically in the same lock scope**, and then `_journal` and `_trigger_nudge` are invoked outside the lock (decoupling queue persistence from PTY injection / avoiding deadlocks from double-acquiring a non-reentrant Lock).
- Nudge delivery is **injected via PTY as a fixed one-liner only**; the body does not pass through (the receiver pulls via `check_messages`). **After the push-first redesign (runtime push-first, 0.1.24+), this PTY nudge + pull is positioned as the *fallback* delivery path** when the per-pane channel sidecar (`server:org-broker-channel`'s `claude/channel` injection) does not take effect, with push-first being the runtime default **delivery mode** (the broker's internal push-vs-pull default, on a separate axis from the transport's `renga`/`broker` default selection; design SoT: transport-lab `docs/design/broker-native-roles.md` §9; the actual behavior follows the runtime surface version this runbook is synchronized to). When the adapter is unreachable or the target is absent, retry up to `nudge_defer_interval` (default 2.0s) × `nudge_defer_max_tries` (default 30).
- `check_messages` (`drain`) empties the queue and returns it **at-most-once**.
- journal: `message_enqueued` → `nudge_sent` / `nudge_deferred` / `nudge_failed` → `queue_drained`.

### 3.4 Tier gating (`surface.py`)

The public surface changes **structurally** by `auth_role` (default-deny allowlist). Tools not in `tools/list` are bounced with `[tool_not_authorized]` even if called (allowlist is one side of a double defense).

| auth_role tier | Public surface |
|---|---|
| worker / curator / unknown | messaging 4 (`send_message` / `check_messages` / `list_peers` / `set_summary`) |
| dispatcher | messaging 4 + ops (`list_panes` / `inspect_pane` / `send_keys` / `poll_events` / `close_pane` / `set_pane_identity` / `spawn_claude_pane` / `spawn_codex_pane`) |
| secretary | dispatcher surfaces + `spawn_pane` (secretary-only) |

> `new_tab` / `focus_pane` are **not** in the broker surface (intentionally excluded). Initial surface = 12 ported surfaces + `spawn_codex_pane` = 13 surfaces.

### 3.5 Stop / expiration

- Graceful stop (`run()`'s `finally` → `stop()` + sidecar removal): The graceful stop paths are **(a) SIGINT / Ctrl-C to foreground serve** and **(b) admin RPC `shutdown` (§3.8)** — these two. In both cases, `run()` is the sole caller of `stop()` via `finally`, `stop()` shuts down + closes the HTTP server and leaves `broker_stopped` in the journal, then removes the `daemon.json` / `admin.token` sidecar (`remove_sidecar`, §3.8). **The `broker_stopped` emit and sidecar removal happen only on the graceful path (SIGINT / admin RPC shutdown)**. When a background daemon is stopped with `kill -TERM`, the `finally` of `run()` is not traversed, so `broker_stopped` is not left, and **the `daemon.json` / `admin.token` sidecar files are not removed and remain in place** (confirm stop via process disappearance + unread reconciliation; clean up via explicit sidecar disposal, §5(4)/(5)). Note also that SIGINT (`kill -INT`) has no effect on a background daemon and the process survives (reproduced twice in the 2026-06-13 rollback drill).
- Session end (MCP `DELETE`): Invalidates the `session_id` of that bind, drops `registered = False` (so a disconnected client does not stay in `list_peers` / delivery targets). journal: `session_closed`.
- Pane close (`close_pane`): After kill via the adapter, the registry pop and token revoke are done atomically in the same lock scope. journal: `pane_closed` + event `pane_exited`.

### 3.6 List of journal events (`queue.jsonl`)

Appended one-line-one-JSON to `<state-dir>/queue.jsonl`. Observation points in operation:

```
broker_started → token_issued → logical_pane_registered (root pane at startup)
  → agent_registered → message_enqueued
  → nudge_sent / nudge_deferred / nudge_failed → queue_drained
  → pane_spawned / pane_identity_set (on spawn / identity operations)
  → session_closed / pane_closed → broker_stopped
```

> **Events added in 0.1.22 (D3)**: `logical_pane_registered` (registers the root token as a logical pane on startup, §3.8) / `pane_spawned` (`spawn_claude_pane` / `spawn_codex_pane` / `spawn_pane`) / `pane_identity_set` (`set_pane_identity`). `broker_stopped` is left at the end only on a graceful stop (SIGINT / admin RPC shutdown) (§3.5 / §5(4)).

> **Verification log (empirical, messaging round trip)**: Confirmed `broker_started → token_issued → agent_registered → message_enqueued(chars=12) → queue_drained(count=1) → broker_stopped` in one cycle.

### 3.7 Broker additional error codes

In addition to the renga codes, broker may return the following. The Secretary / Dispatcher route unknown codes to the default branch for escalation ([`CLAUDE.md`](../../CLAUDE.md) "error branching").

| Code | Trigger |
|---|---|
| `[token_invalid]` | Bearer token is not in the bind table / revoked (HTTP 401, JSON-RPC -32001) |
| `[session_invalid]` | Called another method before `initialize` |
| `[tool_not_authorized]` | Called a tool outside the auth_role tier's public surface |
| `[no_backend]` | Pane operation called without a terminal adapter (`--no-nudge` startup) (= adapter_unavailable) |
| `[nudge_failed]` | Nudge injection did not get through within the defer limit |
| `[peer_not_found]` | `send_message` destination not in a registered bind |
| `[name_taken]` | Pane-name duplication |
| `[admin_unauthorized]` | Called `/admin` RPC without admin token / with an invalid token (HTTP 401, §3.8) |

> The table above adds the admin-surface authentication gate `[admin_unauthorized]` (frequent enough operationally to list) to the codes of the `/mcp` (messaging / ops) surface. The admin surface (`/admin`) authenticates with an `admin_token` that is **in a separate channel** from the per-agent bearer, and apart from `[admin_unauthorized]` may also return `[parse_error]` / `[invalid_params]` / `[unknown_admin_method]` / `[invalid_role]` / `[invalid_cwd]` / `[invalid_name]`. **For the full list of admin RPC codes see §3.8** (the path is separate and not aggregated into the table above).

### 3.8 Admin RPC (token mint / graceful shutdown) and daemon sidecar

In 0.1.22, the **admin surface that controls a running daemon externally** and the **discovery sidecar** were added (runtime#61 / #63, `_handle_admin` in `server.py` / `sidecar.py`). It is a control surface independent of messaging / ops (`/mcp`).

**admin RPC (`/admin`)**:

- The endpoint is `http://<host>:<port>/admin` (`broker.admin_url`). A separate path from `/mcp` (messaging / ops).
- Authentication is not the per-agent bearer but the **`admin_token`** (`secrets.token_urlsafe(32)`, generated at startup). `Authorization: Bearer <admin_token>` with constant-time comparison (`hmac.compare_digest`). **If no admin token is configured, the entire path is hidden (HTTP 404)** = useful for disabling the admin surface for internal tests. Invalid / missing token returns HTTP 401 `[admin_unauthorized]`.
- Methods (JSON-RPC style `{"method": ..., "params": {...}}`):
  - `mint_token` — Mints a new root token against the running daemon (`role` = auth_role). Like the root token, it is not a spawn child, so the tier cap (`capped_auth_role`) is not applied; bind at the requested tier as-is. `params.cwd` is the resolution anchor for relative spawns (made absolute the same way as the CLI).
  - `shutdown` — Requests a graceful shutdown. Returns the ack (`{"ok": true, "shutting_down": true}`) first, then calls `request_shutdown()`; the actual stop (`stop()` + sidecar removal) is done by the `run()` foreground loop (to avoid deadlocking by calling `shutdown` from the handler thread directly). **A signal-independent stop path**, useful as a graceful stop means in environments where SIGTERM/SIGINT is hard to send (Windows etc.).
- **`/admin` error codes (separate channel from the `/mcp` table in §3.7)**: In addition to authentication failure `[admin_unauthorized]` (401, listed in §3.7), JSON body invalid `[parse_error]` (400) / `params` not an object `[invalid_params]` (400) / unknown method `[unknown_admin_method]` (400). `mint_token` may return `[invalid_role]` (role outside the acceptance set) / `[invalid_cwd]` (cwd not a string) / `[invalid_name]` (name not a string) at argument validation (all 400 / `{"ok": false, "error": ...}`). The Secretary / Dispatcher route unknown codes to the default branch for escalation (same policy as §3.7).

**daemon sidecar (2 files under `<state-dir>/`, `sidecar.py`)**:

| File | Content | Secret | Permission | On stop |
|---|---|---|---|---|
| `daemon.json` (`SIDECAR_NAME`) | Discovery metadata (`pid` / `host` / `port` / `state_dir`(absolute) / `backend`(resolved actual value) / `started_at` / `journal_offset`) | Does not contain | Normal | Removed on graceful stop (left on SIGTERM) |
| `admin.token` (`ADMIN_TOKEN_NAME`) | admin RPC auth token | **Contains** | 0600 (temp→atomic rename to avoid torn reads. **Note: on Windows NTFS, only the read-only bit is set**, so group/other read is not truly stripped — a known limitation) | Removed on graceful stop (left on SIGTERM → explicit disposal in §5(4)/(5)) |

- Both are published with `os.replace` atomic-publish to avoid exposing partial writes / torn reads. `journal_offset` is the byte length of `queue.jsonl` at the moment the run starts; it is the start point for limiting stop confirmation (`broker_stopped` detection) to the slice of that run, to **avoid false positives from residue of past runs**.
- **Logical pane registration**: On startup, register the root token in the pane registry as a **logical pane** (`register_logical_pane`, journal `logical_pane_registered`). Since `bind.pane_id = None`, no PTY nudge flies (the human reads via `check_messages`); by having the Secretary appear in `list_panes`, even with just one child spawned, `close_pane` will not mistakenly judge `[last_pane]` and can close the child (consistent with "the Secretary is a logical pane" in §8).

---

## 4. settings regeneration dry-run with `ORG_TRANSPORT=broker`

Run the **transport-descriptor-driven generator** that landed in Epic #6 D/E as a dry-run with `ORG_TRANSPORT=broker` and confirm that the broker-side allowlist is emitted. **No real files are written**.

### 4.1 Single SoT (descriptor)

The ja-side transport accessor [`tools/transport.py`](../../tools/transport.py) consumes the runtime's transport surface descriptor (`claude_org_runtime.transport`) as the sole SoT (does not hardcode). Resolution order is **explicit argument > `ORG_TRANSPORT` env > default `renga`**. Allowlist generation goes through `claude_org_runtime.settings.generator.transport_allowlist(role, transport=...)`.

### 4.2 Per-role allowlist dry-run

```bash
# Compare projection of default renga (unset) vs broker per role (read-only, no writes)
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
| dispatcher | `mcp__renga-peers__*` 14 surfaces | messaging 4 + ops 8 (excluding `spawn_pane`) |
| secretary | `mcp__renga-peers__*` 14 surfaces | messaging 4 + ops + `spawn_pane` + `spawn_codex_pane` (13) |

> The renga default is a model of narrowing one surface (14) per role via the allowlist for all roles. broker blocks the role tier **structurally**, so the allowlist becomes one side of a double defense (safety side).

### 4.3 `~/.claude/settings.json` user_common allowlist regeneration dry-run

[`tools/org_setup_prune.py`](../../tools/org_setup_prune.py) `--user-common-allowlist` projects the MCP `permissions.allow` of user_common (`~/.claude/settings.json`) onto the active transport. **For verification, point `--user-common-settings-path` at a test path to avoid touching the real `~/.claude/settings.json`, and add `--dry-run`**.

```bash
# Prepare test settings (with renga entries in) and dry-run
TEST_SET=/tmp/claude/usercommon-settings.json   # not the real ~/.claude/settings.json

# Create test settings with renga messaging entries (otherwise "drop renga" expected output won't appear if empty/absent)
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

# Default renga: strict no-op (touches file at all)
python3 tools/org_setup_prune.py --user-common-allowlist --dry-run \
    --user-common-settings-path "$TEST_SET"

# broker: drop renga-peers, guarantee org-broker messaging tier (dry-run only displays)
ORG_TRANSPORT=broker python3 tools/org_setup_prune.py --user-common-allowlist --dry-run \
    --user-common-settings-path "$TEST_SET"
```

Expected output:

```
# renga (default)
[org_setup_prune] user_common allowlist: transport=renga (default); no-op -- ~/.claude/settings.json unchanged ...

# broker
=== user_common allowlist (transport=broker): /tmp/claude/usercommon-settings.json ===
  - mcp__renga-peers__send_message      (drop renga messaging below)
  + mcp__org-broker__send_message       (add org-broker messaging below)
  ...
```

> **Verification log (empirical)**: Default renga is strict no-op (test file unchanged by even 1 byte). With `ORG_TRANSPORT=broker`, the diff of renga messaging 4 → org-broker messaging 4 is shown as dry-run. **No real writes due to `--dry-run`** (test file content confirmed unchanged). Non-MCP entries like `Bash(...)` remain in order.

---

## 5. Concretizing the 5 rollback conditions into commands (SoT §5.5)

Complete rollback `ORG_TRANSPORT=broker` → `renga` is not done by flipping the flag alone — **the running broker-spawned panes do not return immediately** (they still carry `--mcp-config` / pull-premise prose). Run SoT §5.5's **5 completion conditions** in order.

> **Premise variables (cwd drift avoidance)**: The commands below do not strike relative `.state/broker` bare-handed. Fix the state-dir that the daemon actually used via `serve --state-dir` as an absolute path variable, and make the canonical root explicit. In production rollout (Track 3), `BROKER_STATE` points at the production `.state/broker`.
>
> ```bash
> CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root (adapt to your environment)
> BROKER_STATE="$CANON_ROOT/.state/broker"            # the --state-dir the daemon passed on serve
> ```

### (1) Flip the flag back

```bash
# Return env to renga (default). The next pane spawned will face renga.
unset ORG_TRANSPORT
# If you'd written it into persistent shell config, remove it there too:
#   grep -rn "ORG_TRANSPORT" ~/.bashrc ~/.zshrc ~/.profile
```

**Check**: `python3 -c "from claude_org_runtime.transport import resolve_transport as r; print(r())"` returns `renga`.

### (2) Regenerate the artifacts (to renga allowlist)

Once the flag is back to renga, **the generator (per-role `settings.local.json`) is identity (bit-equivalent)**. Actually regenerate the artifacts to return to the renga surface.

```bash
# First dry-run to confirm the diff (if broker surfaces remain, the diff to return to renga appears)
python3 tools/org_setup_prune.py --all --dry-run

# If OK, apply (write back the renga allowlist; .bak remains)
python3 tools/org_setup_prune.py --all
```

**user_common (`~/.claude/settings.json`) is handled separately (important)**: `--user-common-allowlist` is **completely no-op in renga mode** (the SoT of the renga allowlist is the org-setup skill + permissions.md, not this tool, so it does not touch the file at all). Therefore, if the dogfood applied broker (`mcp__org-broker__*` is in user_common), running `--user-common-allowlist --dry-run` in renga **does not return the broker surface**. Return user_common explicitly via one of the following:

```bash
# Method A (recommended): restore the .bak created when broker was applied
#   backup naming is settings.json.bak.<YYYYMMDD-HHMMSS> (backup_path)
ls -t ~/.claude/settings.json.bak.* 2>/dev/null | head     # check the latest backup
# cp <the confirmed .bak> ~/.claude/settings.json          # restore after eye-checking the content

# Method B: if no backup, manually swap the messaging surface (org-broker → renga-peers)
#   In ~/.claude/settings.json permissions.allow,
#   replace "mcp__org-broker__{send_message,check_messages,list_peers,set_summary}" with
#   "mcp__renga-peers__..." (do not touch non-MCP entries)
```

**Check**: `mcp__org-broker__*` does not remain in either per-role `settings.local.json` **or user_common (`~/.claude/settings.json`)**.

```bash
# Per-role settings under repo. The glob (*/.claude/) misses hidden role dirs
# (.dispatcher/.claude/ / .curator/.claude/ etc.), and in zsh would no-match so
# grep itself wouldn't run and would falsely report OK. So do not use globs and
# do recursive grep from repo root (grep -r descends into hidden dirs too).
# Limit to settings*.json to avoid false positives.
if grep -rl --include="settings*.json" "mcp__org-broker__" . 2>/dev/null | grep -q .; then
  echo "NG: broker surface remains in repo:"; grep -rl --include="settings*.json" "mcp__org-broker__" . 2>/dev/null
else
  echo "OK: no broker surface in repo"
fi
# Don't forget user_common (home settings.json)
grep -l "mcp__org-broker__" ~/.claude/settings.json 2>/dev/null && echo "NG: broker surface remains in user_common" || echo "OK: no broker surface in user_common"
```

### (3) Respawn active broker panes (restart via renga path)

The running broker-spawned panes do not return on a flag flip. suspend/resume or respawn via the renga path.

```bash
# Get a handle on the current broker panes (from the renga Secretary/Dispatcher)
#   mcp__renga-peers__list_panes  shows the pane list
# Close panes carrying broker tokens one by one → respawn via the renga path (normal delegation flow of org-delegate)
# Pane control closes to Dispatcher/Secretary, so return messaging to renga first then chase panes (the 2-step in §5.5).
```

**Check**: No broker-bind panes remain in `list_peers` / `list_panes`.

### (4) broker daemon stop order (revoke residual panes → stop daemon)

**Order matters**: First revoke (close) residual panes to remove them from delivery targets, and stop the daemon last.

**Choose the stop signal by startup form (reflecting the empirical findings of the 2026-06-13 rollback drill)**: Foreground serve stops gracefully on Ctrl-C (SIGINT) and emits `broker_stopped`, but **SIGINT (`kill -INT`) has no effect on a daemon started in the background with `nohup ... &` etc., and the process survives** (reproduced twice in the drill). Stop a background daemon with **SIGTERM (`kill -TERM`)**. However, SIGTERM does not pass through the `finally` of `run()` (= the sole path to `stop()` + sidecar removal), so **(i) `broker_stopped` is not emitted** (the journal end remains as `broker_started` / `token_issued` etc.) and **(ii) the `daemon.json` / `admin.token` sidecar files are not removed and remain in the state-dir** (D4). Because `admin.token` is the auth secret for admin RPC, the residue must be disposed of explicitly in (5). Therefore both stop-confirmation means and cleanup are split per path.

> **When you want to gracefully stop a background daemon (recommended alternative)**: Instead of SIGTERM, call **admin RPC `shutdown` (§3.8)**, which passes through `run()`'s `finally` and covers `broker_stopped` recording + automatic sidecar removal in one go (signal-independent). Read the admin token from `<state-dir>/admin.token`. The sidecar disposal in (5) is only needed when stopped with SIGTERM.

```bash
# 1) Close residual broker panes (their tokens get revoked. close_pane journal: pane_closed)
#    From renga/dispatcher, close_pane each broker pane.
# 2) Once all revoked, stop the daemon (split by startup form):
#    - Foreground serve (blocking in this shell): do not run this command; press Ctrl-C (SIGINT). Graceful stop.
#    - Background daemon (nohup ... & etc.): send SIGTERM. SIGINT (kill -INT) is ineffective.
kill -TERM <broker_pid>   # background daemon stop. For foreground serve, press Ctrl-C instead
# 3) Stop confirmation (different means per path):
#    a) Only on graceful stop (foreground SIGINT / Ctrl-C) is broker_stopped left at the end of the journal:
tail -n 3 "$BROKER_STATE/queue.jsonl"
#    b) When stopped with SIGTERM (background daemon), broker_stopped is not emitted, so
#       confirm via process disappearance + unread reconciliation (consistent with the unread-reconciliation script in §5(5)).
#       Immediately after SIGTERM, false judgment is possible during termination, so wait for disappearance with a short timeout loop:
for i in $(seq 1 10); do
  kill -0 <broker_pid> 2>/dev/null || { echo "OK: daemon process gone"; break; }
  sleep 1
done
kill -0 <broker_pid> 2>/dev/null && echo "NG: daemon still alive"
#       Unread reconciliation (enqueued vs drained) runs the §5(5) script (do not duplicate here).
```

> **Runtime follow-up candidate (implementation out of scope for this task)**: If the runtime's SIGTERM handler comes to pass through the `finally` path of `run()` (`stop()` + `remove_sidecar`), even on SIGTERM stop, the `broker_stopped` emit and automatic sidecar removal (`daemon.json` / `admin.token`) will run, and **neither the stop-confirmation branching nor the manual sidecar disposal in (5) will be needed**. This runbook stays at the documentation of the procedure; runtime implementation may be filed as a separate Issue. The current graceful alternative is admin RPC `shutdown` (§3.8).

### (5) Confirm disposal of old tokens / queue store / sidecar (no unread / bind / sidecar residue in `.state/broker/`)

```bash
# Reconcile via journal that no unread (enqueued but not drained) messages remain.
# queue_drained carries count=N, so compare via the sum of N rather than "event count" (avoid false judgment on multiple drains).
BROKER_STATE="${BROKER_STATE:?fix BROKER_STATE first (the §5 premise variable)}" \
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
print("OK: no unread" if unread <= 0 else f"NG: {unread} unread messages remain (must be drained before daemon stop)")
PY

# Sidecar residue check and disposal (D4). On graceful stop (SIGINT / admin RPC shutdown),
# run()'s finally has already auto-deleted daemon.json / admin.token. When stopped with SIGTERM,
# both remain, so dispose of them explicitly. Because admin.token is the auth secret for admin RPC, always delete it.
for f in admin.token daemon.json; do
  if [ -e "$BROKER_STATE/$f" ]; then
    echo "residue: $BROKER_STATE/$f (vestige of SIGTERM stop; disposing)"
    rm -f "$BROKER_STATE/$f"   # in environments where rm is unavailable, use shred/truncate etc. per operational rules
  else
    echo "OK: no $f (deleted on graceful stop or never created)"
  fi
done

# Per-agent tokens / bind table are in-process in-memory (gone with daemon stop; not persisted).
# What is persisted is the journal (queue.jsonl) and, on SIGTERM residue, the 2 sidecar files.
# Discard the queue store file so no trace remains (in environments where rm is unavailable, truncate / archive):
#   mv "$BROKER_STATE" "$BROKER_STATE.archived-$(date +%Y%m%d)"   # or delete per operational rules
```

> **Persistence of token / bind / sidecar (D4)**: The per-agent `AgentBind` (token values, bind table) only exists in the daemon process in-memory and is not persisted (the journal leaves the *fact* of `token_issued` but not the value). **Exception is admin token**: This is a secret **written to disk** at `<state-dir>/admin.token` (0600). On graceful stop (SIGINT / admin RPC shutdown), `run()`'s `finally` (`remove_sidecar`) automatically removes it along with `daemon.json`, but **on SIGTERM stop it is not removed and remains**. Therefore what may remain in state-dir is `queue.jsonl` (journal + un-drained messages), plus, on SIGTERM residue, `admin.token` / `daemon.json` — 3 files in total. (5) closes on this unread reconciliation and on disposing of these 3 files.

---

## 6. How to take the billing-neutrality attestation

Confirm via actual argv that every agent broker spawns is an **interactive TUI (no headless)**. This is the evidence of billing neutrality (no non-interactive startup like `claude -p` / `codex exec` that would incur API billing).

### 6.1 Multi-layer defense structure (guard at spawn time)

The billing neutrality of broker is structurally guaranteed by the **default-deny allowlist at spawn time** (`surface.py`):

- `build_claude_argv` / `build_codex_argv` only allow interactive-TUI flags, and `_guard_interactive_claude_argv` / `_guard_interactive_codex_argv` **uniformly reject tokens outside the allowlist (subcommands after flags / bare positionals / `--` / unknown flags / headless flags)**.
- claude side headless blacklist: `-p` / `--print` / `--headless` / `--output-format` / `--input-format` etc. On codex side, subcommands (`exec` / `review` / `*-server` / `apply` / `sandbox` etc.) fall as bare positionals.
- Flags that take values have arity (headless flags at the value position are also bounced in two stages), and `argv[0]` is judged by basename (does not false-reject absolute-path startup).

### 6.2 Empirical argv inspection (runtime attestation)

On the production host (the session where the broker panes are live), inspect the actual argv with ps. Confirm that **not a single headless flag / subcommand exists**.

**The point is to narrow the target to broker-spawned panes**. The host may have headless executions unrelated to this attestation (CI / manual `claude -p` etc.) running in parallel, so an indiscriminate grep over all claude/codex will pick up false positives, and target identification may also be missed. Processes broker spawned carry **`--mcp-config` with broker's MCP config (including `org-broker`)** in argv, so narrow the population by this.

```bash
# 1) Enumerate argv limited to broker-spawned (only those including org-broker in --mcp-config)
ps -eo pid,args | grep -iE "(^| )(claude|codex)( |$)" | grep -v grep \
  | grep -- "--mcp-config" | grep -i "org-broker"

# 2) Billing-neutrality negative check: no headless / exec flags in the argv of the broker panes narrowed above
ps -eo args | grep -iE "(^| )(claude|codex)( |$)" | grep -v grep \
  | grep -- "--mcp-config" | grep -i "org-broker" \
  | grep -nE -- "-p( |$)|--print|--headless|--output-format|--input-format| exec | review |--mcp-server" \
  && echo "NG: detected headless/exec flag on broker pane (billing-incurring startup)" \
  || echo "OK: no headless/exec flag on broker pane (interactive TUI = billing-neutral)"

# 3) Reconcile populations (optional / recommended): confirm the count of broker-bind panes in list_panes matches the count from (1)
#    (Reconcile against the Dispatcher/Secretary list_panes and pid to detect identification miss / surplus)
```

Expected: Each broker pane's argv is composed of **only interactive flags** like `--mcp-config <broker>` / `--model` / `--permission-mode`, and the negative check returns `OK`.

> **Caution**: The ps inspection must be done **on the host session where broker panes are live** (real panes are invisible from inside a PID-namespace-isolated sandbox). The spawn-time guard (§6.1) is the primary defense, and the ps runtime attestation is the secondary confirmation — billing neutrality is secured by these two layers. The `--mcp-config` filter is a primary narrowing based on the structural feature of broker panes; when strictness is required, close the population excess / shortage via the `list_panes` reconciliation in (3).

---

## 7. Cleanup of verification garbage (dogfooding condition (5))

The test state created in this runbook's verifications is closed in a **test directory outside the repo** and does not generate production `.state/broker/`. After verification, run the §5(5) steps **against the test path** so no traces remain.

```bash
CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root (adapt to your environment)

# Confirm the test state-dirs used for verification (must be outside the repo)
ls -d /tmp/claude/broker-smoke-* /tmp/claude/usercommon-settings.json 2>/dev/null

# Journal unread reconciliation (run the §5(5) script with BROKER_STATE=test path) → if OK, dispose
# (Anything under /tmp is ephemeral; archive or delete per operational rules)

# Final confirmation that production .state/broker is not created (both canonical-root absolute path and directly under current worktree)
test -e "$CANON_ROOT/.state/broker" && echo "NG: production .state/broker exists" || echo "OK: production .state is intact"
test -e "$PWD/.state/broker" && echo "NG: .state/broker exists directly under worktree" || echo "OK: also intact directly under worktree"
```

---

## 8. Observability — peeking at a running org (attach path)

broker (tmux backend) starts **the child panes it spawns (Dispatcher, Workers)** as **detached independent tmux sessions** on a dedicated socket. Unlike renga's "visible split panes within the same tab," these child panes are off-screen by default, so the *ambient awareness* of "how many workers are running, which are stuck" (the state where the whole picture is somehow visible without doing anything) is quietly lost. The existing overview means do not cover this experience alone:

| Means | What it offers | What it lacks |
|---|---|---|
| Dashboard (`localhost` state UI) | A `state.db`-based overview of state (worker list / transitions / activity) | Not the **raw screen** of each pane |
| Attention watcher ([`attention-watch.md`](attention-watch.md)) | Push notifications on anomalies / gates | Not the always-on observation of "watch when healthy to feel reassured" |
| **tmux attach (this section)** | The **raw screen of broker-spawned child panes (Dispatcher, Workers)** | As below, currently per-session attach (single-session is the future form in §8.2) |

This section presents the **read-only attach path to peek at a running broker org**. **This path is specific to the tmux backend (POSIX / WSL2)**. The WezTerm backend (Windows, `isolated_session=False`) spawns each pane as a GUI window, so screens are visible from the start and attach is unnecessary.

> **Target scope (important)**: What is visible via attach is only the **child panes broker `adapter.spawn`-ed (Dispatcher, Workers)**. **The Secretary (root secretary) is a logical pane that does not own an adapter real pane** (bookkeeping entry; `register_logical_pane`, `claude_org_runtime/broker/server.py`); it runs on the human's local terminal that started the org (does not appear on the spike socket). Therefore, what this path fills is the "raw screen of Worker group / Dispatcher invisible" gap; the Secretary was always in front of the human.

### 8.1 Current — attach to independent sessions (runtime terminal adapter)

The current runtime's terminal adapter (tmux, `claude_org_runtime.terminal.tmux`) creates the child panes broker spawns (Dispatcher, Workers) as **independent detached sessions on a dedicated socket `claude-org-spike`** (session names `spike-<pid>-<seq>`, `isolated_session = True`). Because they are socket-separated from existing tmux servers (renga etc.), observation requires explicit socket name `-L claude-org-spike`.

```bash
# 1) List existing broker sessions (read-only. Socket explicit is required)
tmux -L claude-org-spike list-sessions
#   e.g.,  spike-12345-1: 1 windows (created ...)   <- each line is 1 child pane (seq starts at 1)

# 2) Attach to the session you want to peek in read-only (-r is read-only; doesn't break a worker by mistaken keystrokes)
tmux -L claude-org-spike attach -r -t spike-12345-1
```

Operations after attach (the prefix is the default `Ctrl-b`):

| Operation | Key | Use |
|---|---|---|
| detach (stop observing and leave) | `Ctrl-b` → `d` | Leave while keeping the session alive (no effect on the process) |
| Switch to a different session | `Ctrl-b` → `s` | Select from session list. **Currently per-session, so switching is required for the whole picture** |

> **Why read-only `-r` is the default**: An attach to an independent session is directly connected to the worker's raw TUI. If you attach without `-r`, keystrokes during observation may enter the worker session (intervention is closed to the `send_keys` path of Secretary/Dispatcher by design, so a human hand attach is limited to observation).

> **Verification log (2026-06-13, runtime 0.1.22)**: Socket name `claude-org-spike` / session name `spike-<pid>-<seq>` / `isolated_session = True` was empirically confirmed via `claude_org_runtime/terminal/tmux.py` (constant `SPIKE_SOCKET` / `_new_session_name`). The command forms `list-sessions` (multi-session enumeration) / `attach -r` (read-only flag acceptance) / `kill-server` (cleanup) were each verified for connectivity on a scratch socket (attach to a real broker org was not performed in this verification because it blocks the interaction).

### 8.2 Future — single-session form for `attach` in one shot (transport-lab design, not yet landed)

The transport-lab `docs/design/broker-native-roles.md` §3.4 (defect 4 measure) has confirmed the design of reconstituting the tmux adapter into **a multi-pane/window configuration within a single `claude-org` session**. After land, the following one command will give a panoramic view of broker-managed panes (Dispatcher, Workers), and standard pane navigation (`Ctrl-b` arrows) will work, so the per-session switching of §8.1 will be unnecessary:

```bash
tmux attach -r -t claude-org   # path after single-session form (§3.4 / R1) (-r=read-only). Socket -L specification also becomes unnecessary
```

- This is **a change to the runtime's terminal adapter (`claude_org_runtime/terminal/`)**, and ja consumes it via runtime pin bumps (not a step of this runbook on the ja side). **On the current runtime (independent sessions), §8.1 is the sole attach path**.
- Pane death is processed by differential reconcile by design, so the trade-off of single-session form (a session-level failure affects all panes) is outweighed by the always-on benefit of observability, §3.4 concludes.
- Observer-only commands (read-only tile display of broker-managed panes) / pane raw-screen tile display on the dashboard, considered as countermeasures for the observability gap, are duplicated by the post-single-session `attach -r -t claude-org` (read-only) which gives an equivalent overview, so they are not adopted in this runbook (necessity to be re-judged in actual operation after single-session form).

---

## 9. Related

- Design SoT: transport-lab `docs/design/ja-migration-plan.md` §5 (integration seams) / §5.5 (coexistence and rollback) / §8 Issue G (dogfood gate)
- Contract: [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14)
- Difference in Secretary operation between the two transport tracks: [`CLAUDE.md`](../../CLAUDE.md) "Transport (transport) two-track"
- Spawn ritual (re-introduction of folder-trust approval + dev-channel sidecar approval; addition with push-first adoption): [`.dispatcher/references/spawn-flow.md`](../../.dispatcher/references/spawn-flow.md) 3-3b
- Transport accessor (ja-side single seam): [`tools/transport.py`](../../tools/transport.py)
- user_common allowlist projection: [`tools/org_setup_prune.py`](../../tools/org_setup_prune.py) `--user-common-allowlist`
- Operational style of attention watcher: [`attention-watch.md`](attention-watch.md)
- Single-session form design of observability (future form in §8.2): transport-lab `docs/design/broker-native-roles.md` §3.4 (defect 4 — independent tmux session issue)
