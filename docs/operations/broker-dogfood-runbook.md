# broker dogfood operations runbook

`claude-org-runtime broker serve` is the daemon for the **pure-backend transport layer (`org-broker`)** that replaces renga-peers. It provides a localhost HTTP MCP server + queue store + nudge delivery in a single process and injects nudges into child panes via a terminal adapter (tmux / WezTerm). This document operationalizes the broker daemon's start / stop / lifecycle / rollback procedures as a **prelude to running production ja with `ORG_TRANSPORT=broker`** under Epic #6 Issue G (#515).

The design SoT is transport-lab `docs/design/ja-migration-plan.md` §5 (ja integration seam) / §5.5 (coexistence & rollback) / §8 Issue G (dogfood gate). The canonical contract is [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14). For Secretary-side operational differences between the two transports, see [`CLAUDE.md`](../../CLAUDE.md) "Transport (two-systems)"; for the spawn ritual see [`.dispatcher/references/spawn-flow.md`](../../.dispatcher/references/spawn-flow.md) 3-3b.

> **Scope and untouchable constraints**: This runbook is "the procedure to enable real runs"; **the actual broker run on production ja (the org-start hijack) is performed later in track 3 (user hands-on)**. All procedures here assume the daemon is started / stopped under a **test state-dir (a directory other than `.state/broker/`)** so production `.state/` is never touched. **Default `renga` is not removed; it remains an always-available opt-in fallback** (the rollback safety device).

> **Validation status**: The start / stop / lifecycle / dry-run commands were verified on 2026-06-11 on a worker worktree environment with **runtime 0.1.17** / tmux 3.2a / WSL2 (key raw-log excerpts are embedded in each section). The §8 attach path was confirmed on 2026-06-13 with **runtime 0.1.22**. **The broker surface description in this document is synced to runtime 0.1.22** (§1.1 setup / §2.1 serve flags adding `--root-role` / `--root-cwd` / §3.6 journal / §3.8 admin RPC & sidecar / §5(4)-(5) sidecar disposal). The serve / admin / sidecar surfaces added between 0.1.17 and 0.1.22 were cross-checked against `claude_org_runtime/broker/{cli,server,sidecar}.py` (0.1.22) (the D2-D6 cleanup for #515 dogfood).

---

## 1. Role and premises

- **Inputs / control**:
  - Environment variable `ORG_TRANSPORT` (`renga` | `broker`, unset = default `renga`). The daemon itself does not read the flag, but the ja-side generators (§4) emit broker-surface allowlists depending on the flag.
  - CLI arguments (`--port` / `--host` / `--state-dir` / `--backend` / `--no-nudge` / `--root-role` / `--root-cwd`; §2.1).
- **Outputs / side-effects**:
  - localhost HTTP MCP endpoint (default `http://127.0.0.1:48720/mcp`) and admin RPC endpoint (`/admin`, §3.8).
  - queue store + JSONL journal (`<state-dir>/queue.jsonl`, default state-dir = `.state/broker`).
  - daemon sidecar (`<state-dir>/daemon.json` discovery metadata + `<state-dir>/admin.token` 0600 secret, §3.8; deleted on graceful stop, left behind on SIGTERM).
  - nudge injection into child panes (via terminal adapter, disabled by `--no-nudge`).
- **Dependency direction (one-way)**: `broker → terminal / dispatcher.choose_split`. **claude-org-ja does not import broker** (inactive when the flag defaults to renga).
- **Observability (important)**: With the tmux backend, the child panes broker spawns (dispatcher / workers) start as **detached independent sessions** and are not visible on screen by default (the Secretary remains in the human's hands-on terminal as a logical pane). For a read-only attach path to peek at running child panes, see §8.
- **CLI naming caveat (important)**: The launch command is **`claude-org-runtime broker serve`** (a sub-command of the top-level CLI). `claude-org-runtime-broker` is the CLI's `prog` name (the header shown in `--help`); **no such console_script exists**. `python -m claude_org_runtime.broker serve` is an equivalent launch form.

```
$ claude-org-runtime broker --help
usage: claude-org-runtime broker [-h] {serve} ...
    serve     Launch the org-broker daemon on localhost (stop with Ctrl+C).
```

### 1.1 isolated venv setup (D6)

To isolate the dogfood from the production environment, the broker org runs in an **isolated venv (WSL/tmux isolated clone)**. This venv requires both **`claude-org-runtime>=0.1.22`** (the version carrying the D2-D6 surfaces) and **`core-harness>=0.3.2`**.

- **runtime must be 0.1.22 or later**: The D2-D6 surfaces in this document (`--root-role` / `--root-cwd` / `/admin` RPC / sidecar) **landed in 0.1.22** and are absent from 0.1.17-0.1.21. **However the current ja pin is `claude-org-runtime>=0.1.17,<0.2` (lower bound 0.1.17)**, so `pip install -e .` does **not guarantee** 0.1.22 (0.1.17 may resolve as the lower bound). For dogfood, explicitly pin with `pip install 'claude-org-runtime>=0.1.22,<0.2'` to bring in 0.1.22 or later (or use `pip install -U` to upgrade to the latest 0.1.x). Permanently raising the lower bound is a separate pin bump in `pyproject.toml` / `requirements.txt` (out of scope for this runbook).
- **core-harness is not a runtime dependency** (runtime's `Requires-Dist` is only `jsonschema`; runtime does not import `core_harness`). On the other hand, **claude-org-ja-side tools** (`tools/check_role_configs.py` etc.) import `core_harness`, so it is required for ja org operations. `pip install claude-org-runtime` alone does not bring it in, and ja tools will `ImportError` inside an isolated venv, so resolve the pin **`core-harness>=0.3.2,<0.4`** from `pyproject.toml` / `requirements.txt` via **`pip install -e .` from the ja repo** (when set up minimally with runtime only, explicitly add `pip install 'core-harness>=0.3.2,<0.4'` as well).
- Pin rationale: `core-harness` is 0.x, so an x-bump (minor) may include breaking changes by policy; we pin to the range `>=0.3.2,<0.4` (`requirements.txt` comment / design Q9-Q10).

```bash
# Isolated venv example (at the root of the isolated clone)
python3 -m venv .venv && . .venv/bin/activate
pip install -e .   # Resolves core-harness>=0.3.2 and claude-org-runtime>=0.1.17 per the pins
# But the runtime lower bound from -e . is 0.1.17. The D2-D6 surfaces need 0.1.22+, so override explicitly:
pip install 'claude-org-runtime>=0.1.22,<0.2'
# For a minimal setup with runtime only, also add core-harness explicitly:
#   pip install 'core-harness>=0.3.2,<0.4'
# Verify:
python3 -c "from claude_org_runtime import __about__; print(__about__.__version__)"   # 0.1.22 or later
```

---

## 2. Hands-on verification of broker daemon startup

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
| `--port` | `48720` (`DEFAULT_PORT`) | localhost bind port. `0` picks an ephemeral OS-assigned port (the actual port appears in the startup log's `listening on`). |
| `--host` | `127.0.0.1` | bind host. Localhost-only by design. |
| `--state-dir` | `.state/broker` (`DEFAULT_STATE_DIR`, CWD-relative) | Write destination for `queue.jsonl` / `daemon.json` / `admin.token`. **Always pass a separate directory during verification** (§2.3 / §7). |
| `--backend` | OS auto-selected (POSIX=`tmux` / Windows=`wezterm`) | terminal adapter. `VALID_BACKENDS = (wezterm, tmux)`. Ignored under `--no-nudge`. |
| `--no-nudge` | (disabled) | Disables nudge delivery by not creating a terminal adapter (**queue only**). Use for a backend-independent connectivity probe. |
| `--root-role` | `worker` (`DEFAULT_ROOT_ROLE`) | The **privilege tier (auth_role) bound to the root token** for manual verification. The published surface from `tools/list` is structurally narrowed by this tier (§3.4). Accepted set `ROOT_ROLE_CHOICES = (worker, curator, dispatcher, secretary)`. Default `worker` = the 4 messaging surfaces (unchanged from current behavior); `secretary` = all 13. |
| `--root-cwd` | (if omitted, the daemon's launch cwd = `os.getcwd()`) | **Binds the cwd of the root pane (the human-driven Secretary) to the root bind** (runtime#61). The relative cwd in `spawn_*` is resolved relative to this cwd (absolute is used as-is). Relative input is still **absolutized** against the daemon's launch cwd before binding (the resolution anchor is always absolute). The **operational contract is that the daemon is started from the session root**, and that launch directory becomes the resolution anchor for relative spawns. When starting outside the session root, set this flag explicitly. |

> **0.1.17 → 0.1.22 delta (D2)**: `--root-role` / `--root-cwd` are flags added in 0.1.22 (runtime#61). Without a cwd on the bind, the relative cwd in `spawn_*` issued by the human-driven Secretary loses its resolution anchor and is rejected or anchored to the wrong base — that is the root cause behind runtime#61. When `--root-cwd` is omitted, the daemon's launch cwd is substituted, so **always launch the daemon from the session root** (or pass `--root-cwd` explicitly).

`serve` blocks in the foreground. Stop via (a) `Ctrl+C` / `SIGINT`, or (b) the admin RPC `shutdown` (§3.8). Both paths pass through `run()`'s `finally`, so the stop is graceful, records `broker_stopped`, and removes the sidecar. On startup, one admin token is generated and written to the sidecar at 0600 (§3.8), and one root token for manual verification is issued; the JSON to pass to `--mcp-config` is printed on stdout:

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

> **Startup side-effects (0.1.22)**: As above, startup writes `<state-dir>/daemon.json` (discovery metadata, non-secret) and `<state-dir>/admin.token` (admin RPC auth token, 0600 secret), and registers the root token as a **logical pane** in the pane registry (`logical_pane_registered` journal, §3.6). Details in §3.8.

### 2.2 Startup / shutdown commands (production form)

The startup form for production ja (track 3, user hands-on) is below. **This section only presents the command form; the validation in this document runs the test state-dir version in §2.3.**

```bash
# Start (default state-dir = .state/broker, tmux backend auto-selected)
claude-org-runtime broker serve

# Stop (split by launch form):
#   - Foreground serve (blocking in this shell): Ctrl+C (SIGINT). Graceful stop path =
#     stop() runs in run()'s finally, leaving one broker_stopped line at the tail of the journal,
#     and daemon.json / admin.token sidecars are removed.
#   - Background daemon (started with nohup ... & etc.): send SIGTERM:
#       kill -TERM <pid>
#     SIGINT (kill -INT) does not work on a background daemon and the process persists
#     (reproduced twice in the 2026-06-13 rollback drill). Stop background daemons with SIGTERM.
#     However, SIGTERM does not pass through run()'s finally, so broker_stopped is not emitted,
#     and daemon.json / admin.token sidecars are left in place (explicit disposal in §5(5)).
#     Confirm background stop via "process disappearance + unread reconciliation + sidecar disposal" (§5(4)/(5)).
#   - Graceful alternative (recommended, signal-independent): invoke admin RPC shutdown (§3.8).
#     Even for a background daemon, this completes broker_stopped recording + automatic sidecar removal in one step.
```

### 2.3 Start → connectivity → stop on a test state-dir (proof procedure that production `.state` is inviolable)

Verification **never touches production `.state/broker/`**. Pass a temporary directory to `--state-dir` and confirm `queue.jsonl` is created only under that test path.

> **cwd drift caution (required)**: The default for `--state-dir` is **CWD-relative** `.state/broker`. The `.state/` in a worker worktree and in the canonical claude-org root are different, so striking the relative path bare makes "which `.state` am I looking at" ambiguous and invites a wrong inviolability check / production `.state` contamination. This document **pins the canonical root via the absolute-path variable `CANON_ROOT` and pins the test state-dir via the absolute-path variable `TEST_STATE` (outside the repo)**, and never strikes relative `.state/broker` bare.

```bash
# 0) Pin prerequisite variables (do not strike relative paths bare)
CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root with production .state/broker (adjust to environment)
TEST_STATE=/tmp/claude/broker-smoke-A               # test state-dir (must be an absolute path outside the repo)

# 1) Prepare the test state-dir (create parent directory + use an unused path to avoid mixing in existing logs)
mkdir -p "$TEST_STATE"
test -e "$TEST_STATE/queue.jsonl" && echo "WARN: existing queue.jsonl present. Use another path or move it aside before validating"

# 2) Start (--no-nudge for a backend-independent connectivity probe. -u flushes stdout immediately)
python3 -u -m claude_org_runtime.broker serve \
    --state-dir "$TEST_STATE" --port 48799 --no-nudge
```

From another terminal (or a driver script), use the token shown in the startup log to hit the HTTP MCP:

| Step | Expected |
|---|---|
| `initialize` | `serverInfo = {"name": "org-broker", "version": "0.1.0"}` + an `Mcp-Session-Id` header issued |
| `tools/list` (worker token) | **Only the 4 messaging surfaces** `["check_messages", "list_peers", "send_message", "set_summary"]` (tier gating, §3.4) |
| `tools/call send_message` (self-addressed) | `{"ok": true, "delivered_to": "manual-test"}` |
| `tools/call check_messages` | The just-sent `hello broker` is drained at-most-once |

Stop by sending `SIGINT` to serve. **A clean shutdown returns exit code 0**.

**`.state` inviolability confirmation (required)**: After verification, confirm production `.state/broker/` was not created. The queue is written only to the test path you passed.

```bash
# queue exists only under TEST_STATE
ls "$TEST_STATE/queue.jsonl"
# Production side (canonical root absolute path) must not be created. Do not use relative .state/broker
test -e "$CANON_ROOT/.state/broker" && echo "NG: production .state/broker contaminated" || echo "OK: production .state unchanged"
# Confirm no validation debris fell into the current worktree root (prevents CWD-relative default mix-up)
test -e "$PWD/.state/broker" && echo "NG: .state/broker created under worktree root" || echo "OK: worktree root unchanged"
```

> **Validation log (2026-06-11, hands-on)**: With both `--no-nudge` and `--backend tmux`, the `initialize → tools/list → send_message → check_messages` round-trip succeeded and **exit 0** on `SIGINT`. `tools/list` returned only the 4 messaging surfaces at the worker tier. Production `.state/broker/` was not created (`queue.jsonl` exists only on the test path). The tmux backend's adapter is lazily created even without a live tmux server, so startup / shutdown succeeds (messaging probes are skipped because there is no actual child pane to inject the nudge into).

---

## 3. start / stop / token / queue lifecycle

The broker's internal state transitions are split across `server` / `store` / `tokens` / `surface` under `claude_org_runtime/broker/`. The 4 flows operators need to know:

### 3.1 Token issuance (`tokens.py`)

- One **per-agent token** is issued at spawn (`issue_token`, `secrets.token_urlsafe(32)`). token ↔ `AgentBind` (`agent_id` / `name` / `role` / `auth_role` / `pane_id` / `cwd` / `kind`).
- **`role` (display-only, mutable via `set_pane_identity`) is separated from `auth_role` (immutable privilege tier, fixed at issuance)**. Tier gating uses only `auth_role`; self-declaring a display role does not escalate. The `auth_role` of a spawn child is capped at the caller's tier (`capped_auth_role`).
- `mcp_config_for(token)` generates the JSON to pass to `--mcp-config` (the token is embedded as the static header `Authorization: Bearer <token>`; env references like `${VAR}` are not used).
- journal: `token_issued`.

### 3.2 Registration (HTTP handler in `server.py`)

- Once the child pane's Claude / Codex reaches `initialize` (MCP), `AgentBind.registered = True` (records `registered_at`). **Only registered binds are delivery targets** (prevents delivery to unconnected / DELETE-ed clients).
- journal: `agent_registered`.

### 3.3 queue store + nudge delivery (`store.py` / `server.py`)

- `send_message` (`enqueue`) creates an entry with **token-derived attribution** (self-declaration not allowed). The recipient's registered check and queue append are atomic within **the same lock scope**, after which `_journal` and `_trigger_nudge` are called outside the lock (decouples queue persistence from PTY injection; avoids the double-acquire deadlock of a non-reentrant Lock).
- Nudge delivery **injects only a fixed one-liner via PTY** and does not pass the body (the recipient pulls with `check_messages` = push-then-pull model). On adapter unreachable / target unarrived, retries up to `nudge_defer_interval` (default 2.0s) × `nudge_defer_max_tries` (default 30).
- `check_messages` (`drain`) empties the queue **at-most-once** and returns.
- journal: `message_enqueued` → `nudge_sent` / `nudge_deferred` / `nudge_failed` → `queue_drained`.

### 3.4 Tier gating (`surface.py`)

The published surface **structurally** changes by `auth_role` (default-deny allowlist). Tools not in `tools/list` are also rejected on call with `[tool_not_authorized]` (the allowlist is one half of the dual defense).

| auth_role tier | Published surface |
|---|---|
| worker / curator / unknown | messaging 4 (`send_message` / `check_messages` / `list_peers` / `set_summary`) |
| dispatcher | messaging 4 + ops (`list_panes` / `inspect_pane` / `send_keys` / `poll_events` / `close_pane` / `set_pane_identity` / `spawn_claude_pane` / `spawn_codex_pane`) |
| secretary | dispatcher's surface + `spawn_pane` (secretary-only) |

> `new_tab` / `focus_pane` are **not in** the broker surface (intentional exclusion). Initial surface = 12 ported + `spawn_codex_pane` = 13 surfaces.

### 3.5 Stop / invalidate

- Graceful stop (`run()`'s `finally` → `stop()` + sidecar removal): the two graceful stop paths are **(a) SIGINT / Ctrl-C to the foreground serve** and **(b) admin RPC `shutdown` (§3.8)**. Both pass through `run()`'s `finally` as the sole caller of `stop()`; `stop()` shuts down and closes the HTTP server, leaves `broker_stopped` in the journal, and then deletes the `daemon.json` / `admin.token` sidecars (`remove_sidecar`, §3.8). **`broker_stopped` emission and sidecar removal happen only on the graceful paths (SIGINT / admin RPC shutdown)**. If a background daemon is stopped with `kill -TERM`, it does not pass through `run()`'s `finally`, so `broker_stopped` is not left, and **`daemon.json` / `admin.token` sidecars are not removed and persist** (confirm stop via process disappearance + unread reconciliation; clean up via explicit sidecar disposal, §5(4)/(5)). Note that SIGINT (`kill -INT`) to a background daemon does not work and the process persists (reproduced twice in the 2026-06-13 rollback drill).
- Session termination (MCP `DELETE`): invalidates the bind's `session_id` and drops `registered` to `False` (keeps disconnected clients out of `list_peers` / delivery targets). journal: `session_closed`.
- Pane close (`close_pane`): after adapter kill, registry pop and token revoke are atomic within one lock scope. journal: `pane_closed` + event `pane_exited`.

### 3.6 Journal event list (`queue.jsonl`)

Appended one JSON per line to `<state-dir>/queue.jsonl`. Operational observation points:

```
broker_started → token_issued → logical_pane_registered (root pane at startup)
  → agent_registered → message_enqueued
  → nudge_sent / nudge_deferred / nudge_failed → queue_drained
  → pane_spawned / pane_identity_set (during spawn / identity operations)
  → session_closed / pane_closed → broker_stopped
```

> **Events added in 0.1.22 (D3)**: `logical_pane_registered` (registers the root token as a logical pane at startup, §3.8) / `pane_spawned` (`spawn_claude_pane` / `spawn_codex_pane` / `spawn_pane`) / `pane_identity_set` (`set_pane_identity`). `broker_stopped` is left at the tail only on graceful stop (SIGINT / admin RPC shutdown) (§3.5 / §5(4)).

> **Validation log (hands-on, messaging round-trip)**: `broker_started → token_issued → agent_registered → message_enqueued(chars=12) → queue_drained(count=1) → broker_stopped` was confirmed in a single cycle.

### 3.7 broker-additional error codes

In addition to renga codes, broker may return the following. The Secretary / dispatcher routes unknown codes to escalation via the default branch ([`CLAUDE.md`](../../CLAUDE.md) "Error branching").

| Code | Trigger |
|---|---|
| `[token_invalid]` | Bearer token not in bind table / revoked (HTTP 401, JSON-RPC -32001) |
| `[session_invalid]` | A method was called before `initialize` |
| `[tool_not_authorized]` | A tool outside the auth_role tier's published surface was called |
| `[no_backend]` | Pane operation called with no terminal adapter (`--no-nudge` start) (= adapter_unavailable) |
| `[nudge_failed]` | Nudge injection did not reach the destination within the defer limit |
| `[peer_not_found]` | `send_message` recipient not in a registered bind |
| `[name_taken]` | Duplicate pane name |
| `[admin_unauthorized]` | `/admin` RPC called without an admin token or with an invalid token (HTTP 401, §3.8) |

> The table above combines the `/mcp` (messaging / ops) codes with the admin-surface auth gate `[admin_unauthorized]` (listed due to high operational frequency). The admin surface (`/admin`) authenticates via a `admin_token` that is **separate** from the per-agent bearer, and may also return `[parse_error]` / `[invalid_params]` / `[unknown_admin_method]` / `[invalid_role]` / `[invalid_cwd]` / `[invalid_name]` in addition to `[admin_unauthorized]`. **The full admin RPC code list is in §3.8** (not aggregated into the table above because the path is separate).

### 3.8 admin RPC (token mint / graceful shutdown) and daemon sidecar

0.1.22 added **an admin surface that controls a running daemon from outside** and **a discovery sidecar** (runtime#61 / #63, `server.py`'s `_handle_admin` / `sidecar.py`). It is a control surface independent of messaging / ops (`/mcp`).

**admin RPC (`/admin`)**:

- The endpoint is `http://<host>:<port>/admin` (`broker.admin_url`). A separate path from `/mcp` (messaging / ops).
- Auth is not the per-agent bearer but **`admin_token`** (`secrets.token_urlsafe(32)`, generated at startup). `Authorization: Bearer <admin_token>` is constant-time compared (`hmac.compare_digest`). **If the admin token is not set, the path is hidden altogether (HTTP 404)** = the admin surface can be disabled for internal testing. Invalid / missing token returns HTTP 401 `[admin_unauthorized]`.
- Methods (JSON-RPC style `{"method": ..., "params": {...}}`):
  - `mint_token` — mints a new root token on the running daemon (`role` = auth_role). Like the root token, it is not a spawn child, so the tier cap (`capped_auth_role`) is not applied and the bind uses the requested tier. `params.cwd` is the resolution anchor for relative spawns (absolutized as in the CLI).
  - `shutdown` — requests a graceful shutdown. The ack (`{"ok": true, "shutting_down": true}`) is returned first, then `request_shutdown()` is called; the actual stop (`stop()` + sidecar removal) is performed by `run()`'s foreground loop (avoids the deadlock of calling `shutdown` directly from a handler thread). It is a **signal-independent stop path** and becomes the graceful-stop means in environments where sending SIGTERM/SIGINT is awkward (Windows etc.).
- **`/admin` error codes (a system separate from §3.7's `/mcp` table)**: in addition to auth failure `[admin_unauthorized]` (401, listed in §3.7), invalid JSON body `[parse_error]` (400) / `params` not an object `[invalid_params]` (400) / unknown method `[unknown_admin_method]` (400). `mint_token` returns `[invalid_role]` (unaccepted role) / `[invalid_cwd]` (cwd not a string) / `[invalid_name]` (name not a string) on argument validation (all 400 / `{"ok": false, "error": ...}`). The Secretary / dispatcher routes unknown codes to escalation via the default branch (same policy as §3.7).

**daemon sidecar (the 2 files under `<state-dir>/`, `sidecar.py`)**:

| File | Content | Secret | Permissions | At stop |
|---|---|---|---|---|
| `daemon.json` (`SIDECAR_NAME`) | discovery metadata (`pid` / `host` / `port` / `state_dir` (absolute) / `backend` (resolved actual value) / `started_at` / `journal_offset`) | none | normal | removed on graceful stop (persists under SIGTERM) |
| `admin.token` (`ADMIN_TOKEN_NAME`) | admin RPC auth token | **yes** | 0600 (temp→atomic rename to avoid torn read. **On Windows NTFS this becomes the read-only bit only**, and group/other read is not actually denied — a known limitation) | removed on graceful stop (persists under SIGTERM → explicit disposal in §5(4)/(5)) |

- Both are published via `os.replace` atomic publish to avoid exposing partial writes / torn reads. `journal_offset` is the `queue.jsonl` byte length at run start, used as the starting point so the stop check (`broker_stopped` detection) **avoids false positives from leftover past runs** by being limited to the current run's slice.
- **Logical pane registration**: at startup the root token is registered in the pane registry as a **logical pane** (`register_logical_pane`, journal `logical_pane_registered`). Since `bind.pane_id = None`, PTY nudges are not sent (the human reads with `check_messages`), and having the Secretary appear in `list_panes` lets `close_pane` close a child even when only one child has been spawned without misfiring `[last_pane]` (consistent with §8's "Secretary is a logical pane").

---

## 4. settings re-generation dry-run under `ORG_TRANSPORT=broker`

Dry-run the **transport-descriptor-driven generators** that landed in Epic #6 D/E with `ORG_TRANSPORT=broker` and confirm that the broker-surface allowlist is produced. **No actual files are written**.

### 4.1 Single SoT (descriptor)

The ja-side transport accessor [`tools/transport.py`](../../tools/transport.py) consumes the runtime transport surface descriptor (`claude_org_runtime.transport`) as the sole SoT (no hardcoding). Resolution order is **explicit argument > `ORG_TRANSPORT` env > default `renga`**. Allowlist generation goes through `claude_org_runtime.settings.generator.transport_allowlist(role, transport=...)`.

### 4.2 Per-role allowlist dry-run

```bash
# Compare default renga (unset) vs broker projections per role (read-only, no writes)
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
| dispatcher | `mcp__renga-peers__*` 14 surfaces | messaging 4 + ops 8 (excludes `spawn_pane`) |
| secretary | `mcp__renga-peers__*` 14 surfaces | messaging 4 + ops + `spawn_pane` + `spawn_codex_pane` (13) |

> The renga default is a model that narrows the same 14-surface set across all roles with an allowlist. broker **structurally** gates the role tier, so the allowlist becomes one half of the dual defense (the safer side).

### 4.3 `~/.claude/settings.json` user_common allowlist re-generation dry-run

[`tools/org_setup_prune.py`](../../tools/org_setup_prune.py) `--user-common-allowlist` projects the MCP `permissions.allow` in user_common (`~/.claude/settings.json`) onto the active transport. **For verification, point at a test path with `--user-common-settings-path` so the real `~/.claude/settings.json` is not touched, and add `--dry-run`**.

```bash
# Prepare a test settings (with renga entries) and dry-run
TEST_SET=/tmp/claude/usercommon-settings.json   # not the real ~/.claude/settings.json

# Build a test settings with renga messaging entries (empty/missing does not produce the expected "drop renga" output)
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

# broker: drop renga-peers, guarantee the org-broker messaging tier (dry-run is display only)
ORG_TRANSPORT=broker python3 tools/org_setup_prune.py --user-common-allowlist --dry-run \
    --user-common-settings-path "$TEST_SET"
```

Expected output:

```
# renga (default)
[org_setup_prune] user_common allowlist: transport=renga (default); no-op — ~/.claude/settings.json unchanged ...

# broker
=== user_common allowlist (transport=broker): /tmp/claude/usercommon-settings.json ===
  - mcp__renga-peers__send_message      (renga messaging dropped below)
  + mcp__org-broker__send_message       (org-broker messaging added below)
  ...
```

> **Validation log (hands-on)**: Default renga is a strict no-op (the test file is unchanged even by 1 byte). With `ORG_TRANSPORT=broker`, the renga messaging 4 → org-broker messaging 4 diff is shown in dry-run. **Zero actual writes because of `--dry-run`** (test file contents confirmed unchanged). Non-MCP entries like `Bash(...)` are preserved in order.

---

## 5. Rollback 5-condition concrete commands (SoT §5.5)

A complete rollback from `ORG_TRANSPORT=broker` to `renga` is not achieved by flipping the flag alone — **already-running broker-spawned panes do not immediately recover** (they still carry `--mcp-config` / pull-based prose). Execute SoT §5.5's **5 completion conditions** in order.

> **Prerequisite variables (cwd-drift avoidance)**: The commands below do not strike relative `.state/broker` bare. Pin the state-dir the daemon actually used with `serve --state-dir` as an absolute-path variable, and pin the canonical root explicitly. In a production rollout (track 3), `BROKER_STATE` points to production `.state/broker`.
>
> ```bash
> CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root (adjust to environment)
> BROKER_STATE="$CANON_ROOT/.state/broker"            # --state-dir passed to serve
> ```

### (1) Flip the flag back

```bash
# Reset the env to renga (default). The next spawned pane will point at renga.
unset ORG_TRANSPORT
# If it was written to a persistent shell config, also remove it from there:
#   grep -rn "ORG_TRANSPORT" ~/.bashrc ~/.zshrc ~/.profile
```

**Check**: `python3 -c "from claude_org_runtime.transport import resolve_transport as r; print(r())"` returns `renga`.

### (2) Re-generate artifacts (back to the renga allowlist)

Once the flag is back to renga, **the generators (per-role `settings.local.json`) become identity (bit-equivalent)**. Actually re-generate to return artifacts to the renga surface.

```bash
# First dry-run to confirm the diff (if broker surfaces remain, you will see the diff that returns to renga)
python3 tools/org_setup_prune.py --all --dry-run

# If OK, apply (writes back the renga allowlist; .bak is retained)
python3 tools/org_setup_prune.py --all
```

**user_common (`~/.claude/settings.json`) is handled separately (important)**: `--user-common-allowlist` is **a complete no-op in renga mode** (the SoT for the renga allowlist is the org-setup skill + permissions.md, not this tool, so the file is not touched at all). Therefore if broker has already been applied during dogfood (`mcp__org-broker__*` is in user_common), running `--user-common-allowlist --dry-run` in renga **will not bring broker surfaces back**. Restore user_common explicitly by one of:

```bash
# Method A (recommended): restore the .bak created when broker was applied
#   backup naming is settings.json.bak.<YYYYMMDD-HHMMSS> (backup_path)
ls -t ~/.claude/settings.json.bak.* 2>/dev/null | head     # check the latest backup
# cp <the .bak you checked> ~/.claude/settings.json        # restore after visually confirming contents

# Method B: when no backup exists, manually swap the messaging surface (org-broker → renga-peers)
#   In permissions.allow of ~/.claude/settings.json,
#   replace "mcp__org-broker__{send_message,check_messages,list_peers,set_summary}" with
#   "mcp__renga-peers__..." (do not touch non-MCP entries).
```

**Check**: no `mcp__org-broker__*` remains in **either** per-role `settings.local.json` **or** user_common (`~/.claude/settings.json`).

```bash
# Per-role settings under repo. The glob (*/.claude/) does not pick up hidden role dirs
# (.dispatcher/.claude/ / .curator/.claude/ etc.), and under zsh a no-match means
# grep does not run at all and the check passes by mistake. Don't use the glob; recursive-grep
# from repo root (grep -r descends into hidden dirs). Restrict to settings*.json to avoid false hits.
if grep -rl --include="settings*.json" "mcp__org-broker__" . 2>/dev/null | grep -q .; then
  echo "NG: broker surfaces remain in repo:"; grep -rl --include="settings*.json" "mcp__org-broker__" . 2>/dev/null
else
  echo "OK: no broker surfaces in repo"
fi
# Don't forget to check user_common (settings.json under home) as well
grep -l "mcp__org-broker__" ~/.claude/settings.json 2>/dev/null && echo "NG: broker surfaces remain in user_common" || echo "OK: no broker surfaces in user_common"
```

### (3) Respawn active broker panes (restart via renga path)

Running broker-spawned panes do not recover by flipping the flag. suspend/resume or respawn via the renga path.

```bash
# Survey current broker panes (from the renga Secretary/dispatcher)
#   mcp__renga-peers__list_panes  to check the pane list
# Close panes carrying a broker token one by one → respawn via renga (the normal delegation flow in org-delegate)
# Pane control is closed in dispatcher/secretary, so move messaging back to renga first, then chase panes (the 2-stage of §5.5).
```

**Check**: no broker-bind pane remains in `list_peers` / `list_panes`.

### (4) broker daemon stop order (revoke remaining panes → stop daemon)

**Order matters**: first revoke (close) remaining panes to take them off delivery targets, then stop the daemon last.

**Signal choice differs by launch form (reflecting the 2026-06-13 rollback drill)**: a foreground serve stops gracefully on Ctrl-C (SIGINT) and emits `broker_stopped`, but for a daemon started in the background (`nohup ... &` etc.), **SIGINT (`kill -INT`) does not work and the process persists** (reproduced twice in the drill). Stop a background daemon with **SIGTERM (`kill -TERM`)**. However SIGTERM does not pass through `run()`'s `finally` (= the sole path to `stop()` + sidecar removal), so **(i) `broker_stopped` is not emitted** (the journal tail remains at `broker_started` / `token_issued` etc.) and **(ii) the `daemon.json` / `admin.token` sidecars are not removed and persist under the state-dir** (D4). `admin.token` is the admin RPC auth secret, so the leftover is explicitly disposed of in (5). Therefore stop confirmation means and cleanup both diverge by path.

> **To stop a background daemon gracefully (recommended alternative)**: instead of SIGTERM, hit the **admin RPC `shutdown` (§3.8)** to pass through `run()`'s `finally` and complete `broker_stopped` recording + automatic sidecar removal in one step (signal-independent). The admin token is read from `<state-dir>/admin.token`. The sidecar disposal in (5) is only needed when stopped via SIGTERM.

```bash
# 1) Close remaining broker panes (tokens are revoked. close_pane journal: pane_closed)
#    close_pane each broker pane from renga/dispatcher.
# 2) Once everything is revoked, stop the daemon (split by launch form):
#    - Foreground serve (blocking in this shell): do not run this command; type Ctrl-C (SIGINT). Graceful stop.
#    - Background daemon (nohup ... & etc.): send SIGTERM. SIGINT (kill -INT) does not work.
kill -TERM <broker_pid>   # Stop a background daemon. For foreground serve, type Ctrl-C instead
# 3) Confirm stop (means differ by path):
#    a) Only graceful stop (foreground SIGINT / Ctrl-C) leaves broker_stopped at the journal tail:
tail -n 3 "$BROKER_STATE/queue.jsonl"
#    b) When stopped with SIGTERM (background daemon), broker_stopped is not emitted, so
#       confirm via process disappearance + unread reconciliation (consistent with §5(5)'s unread reconciliation script).
#       Immediately after SIGTERM the process may be terminating, leading to false negatives,
#       so wait for disappearance in a short timeout loop:
for i in $(seq 1 10); do
  kill -0 <broker_pid> 2>/dev/null || { echo "OK: daemon process gone"; break; }
  sleep 1
done
kill -0 <broker_pid> 2>/dev/null && echo "NG: daemon still alive"
#       Run the unread reconciliation (enqueued vs drained) script from §5(5) (don't duplicate here).
```

> **runtime follow-up candidate (implementation out of scope for this task)**: if the runtime's SIGTERM handler is changed to pass through `run()`'s `finally` path (`stop()` + `remove_sidecar`), then SIGTERM stops also emit `broker_stopped` and automatically remove the sidecar (`daemon.json` / `admin.token`), and **both the split stop-confirmation and the manual sidecar disposal in (5) become unnecessary**. This runbook stops at codifying the procedure; the runtime change should be tracked in a separate Issue. The current graceful alternative is admin RPC `shutdown` (§3.8).

### (5) Confirm disposal of old tokens / queue store / sidecar (no unread / bind / sidecar leftovers in `.state/broker/`)

```bash
# Reconcile journal to confirm no unread (enqueued but not drained) messages remain.
# queue_drained carries count=N, so compare by sum of N (not by event count), to avoid false negatives across multiple drains.
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
print("OK: no unread" if unread <= 0 else f"NG: {unread} unread remain (need to drain before stopping daemon)")
PY

# Sidecar leftover check and disposal (D4). On a graceful stop (SIGINT / admin RPC shutdown),
# run()'s finally has already removed daemon.json / admin.token automatically. When stopped via SIGTERM,
# both persist, so dispose of them explicitly. admin.token is the admin RPC auth secret — always remove it.
for f in admin.token daemon.json; do
  if [ -e "$BROKER_STATE/$f" ]; then
    echo "leftover: $BROKER_STATE/$f (residue from SIGTERM stop; disposing)"
    rm -f "$BROKER_STATE/$f"   # In environments where rm is not allowed, follow ops rules (shred/truncate etc.)
  else
    echo "OK: $f absent (already removed by graceful stop or never created)"
  fi
done

# per-agent token / bind table are in-process in-memory (gone when daemon stops; not persisted).
# What persists is the journal (queue.jsonl) and the 2 sidecar files left over after a SIGTERM stop.
# Dispose of the queue store file to leave no trace (in rm-restricted environments, truncate / archive):
#   mv "$BROKER_STATE" "$BROKER_STATE.archived-$(date +%Y%m%d)"   # or follow ops rules
```

> **Persistence of token / bind / sidecar (D4)**: per-agent `AgentBind` (token values / bind table) is only in the daemon process's in-memory and is not persisted (the journal carries the fact `token_issued`, but not the value). **The exception is the admin token**: it is a **secret written to disk** as `<state-dir>/admin.token` (0600). On a graceful stop (SIGINT / admin RPC shutdown), `run()`'s `finally` (`remove_sidecar`) removes it along with `daemon.json`, but **on a SIGTERM stop it is not removed and persists**. Therefore, what may remain under state-dir is `queue.jsonl` (journal + undrained messages), plus `admin.token` / `daemon.json` on SIGTERM leftover — 3 files in total. (5) closes on this unread reconciliation and disposal of those 3 files.

---

## 6. How to take a billing-neutral attestation

Confirm via actual argv that every agent broker spawns is an **interactive TUI (no headless)**. This is evidence of billing neutrality (no non-interactive launches such as `claude -p` / `codex exec` that incur API billing).

### 6.1 Defense-in-depth structure (guards at spawn time)

broker's billing neutrality is structurally guaranteed by a **spawn-time default-deny allowlist** (`surface.py`):

- `build_claude_argv` / `build_codex_argv` only allow flags meant for interactive TUI use, and `_guard_interactive_claude_argv` / `_guard_interactive_codex_argv` **uniformly reject tokens outside the allowlist (post-flag sub-commands / bare positionals / `--` / unknown flags / headless flags)**.
- claude-side headless blacklist: `-p` / `--print` / `--headless` / `--output-format` / `--input-format` etc. On the codex side, sub-commands (`exec` / `review` / `*-server` / `apply` / `sandbox` etc.) fall as bare positionals.
- Value-taking flags have arity (headless flags in the value position are caught in the second stage as well), and `argv[0]` uses basename matching (does not false-reject absolute-path launches).

### 6.2 Live argv inspection (runtime attestation)

On the production host (where broker panes are live in a session), inspect the actually-running argv with ps. Confirm **not a single headless flag / sub-command is present**.

**Narrowing to broker-spawned panes** is the point. The host may have unrelated headless executions in parallel (CI / manual `claude -p` etc.), so indiscriminate grep over all claude/codex picks up false positives and conversely misses identifying the targets. broker-spawned processes carry **the broker's MCP config (including `org-broker`) via `--mcp-config`** in their argv, so use that to narrow the population.

```bash
# 1) Enumerate argv, restricted to broker-spawned (those with org-broker in --mcp-config)
ps -eo pid,args | grep -iE "(^| )(claude|codex)( |$)" | grep -v grep \
  | grep -- "--mcp-config" | grep -i "org-broker"

# 2) Billing-neutral negative check: no headless / exec-family flag in the argv of broker panes narrowed above
ps -eo args | grep -iE "(^| )(claude|codex)( |$)" | grep -v grep \
  | grep -- "--mcp-config" | grep -i "org-broker" \
  | grep -nE -- "-p( |$)|--print|--headless|--output-format|--input-format| exec | review |--mcp-server" \
  && echo "NG: detected headless/exec flag in a broker pane (a launch that incurs billing)" \
  || echo "OK: no headless/exec flag in broker panes (interactive TUI = billing-neutral)"

# 3) Population cross-check (optional, recommended): confirm the broker-bind pane count from list_panes matches the count from (1)
#    (Cross-check the dispatcher/secretary's list_panes against pids to detect identification misses / surplus.)
```

Expected: each broker pane's argv is composed of **only interactive flags** like `--mcp-config <broker>` / `--model` / `--permission-mode` etc., and the negative check returns `OK`.

> **Note**: Run the ps inspection in **a host session where the broker panes are live** (you cannot see real panes from inside a PID-namespace-separated sandbox). Billing neutrality is guarded in two stages: spawn-time guards (§6.1) as primary defense, ps-based runtime attestation as the secondary check. Filtering by `--mcp-config` is a primary narrowing based on broker panes' structural characteristic; when stricter accuracy is needed, close the population gaps with the `list_panes` cross-check in (3).

---

## 7. Cleanup of validation debris (dogfooding condition (5))

The test state created by this runbook's validations is closed under a **test directory outside the repo**, and production `.state/broker/` is not generated. After validation, run the §5(5) procedure **against the test path** to leave no trace.

```bash
CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root (adjust to environment)

# Confirm the test state-dirs used in validation (must be outside the repo)
ls -d /tmp/claude/broker-smoke-* /tmp/claude/usercommon-settings.json 2>/dev/null

# Journal unread reconciliation (run §5(5)'s script with BROKER_STATE pointed at the test path) → dispose if OK
# (Under /tmp is ephemeral. Archive or delete per ops rules.)

# Final confirmation that production .state/broker is not created (both canonical root absolute path and current worktree root)
test -e "$CANON_ROOT/.state/broker" && echo "NG: production .state/broker exists" || echo "OK: production .state unchanged"
test -e "$PWD/.state/broker" && echo "NG: .state/broker exists under worktree root" || echo "OK: worktree root unchanged"
```

---

## 8. Observability — peek at the running org (the attach path)

broker (tmux backend) starts the **child panes it spawns (dispatcher / workers)** as **detached independent tmux sessions on a dedicated socket**. Unlike renga's "visible split panes within the same tab", these child panes are not visible by default in the human's screen, so the *ambient awareness* (the state where the whole picture is silently visible without doing anything) of "how many workers are running and which ones have stalled" quietly disappears. Existing overview means alone do not fill this experience:

| Means | What it provides | What it lacks |
|---|---|---|
| Dashboard (the `localhost` status UI) | a `state.db`-based status overview (worker list / transitions / activity) | not the **live screen** of each pane |
| attention watcher ([`attention-watch.md`](attention-watch.md)) | push notifications on anomaly / gate | not a constant observation of "watch a healthy state and feel reassured" |
| **tmux attach (this section)** | the **live screen of broker-spawned child panes (dispatcher / workers)** | as below, currently per-session attach (the single-session future form is in §8.2) |

This section presents a **read-only attach path** for peeking at a running broker org. **This path is specific to the tmux backend (POSIX / WSL2)**. The WezTerm backend (Windows, `isolated_session=False`) spawns each pane as a GUI window, so the screens are visible from the start and attach is unnecessary.

> **Target scope (important)**: What attach can see is **only the child panes broker `adapter.spawn`-ed (dispatcher / workers)**. The **Secretary (root secretary) does not own an adapter actual pane — it is a logical pane** (bookkeeping entry; `register_logical_pane`, `claude_org_runtime/broker/server.py`) and runs directly in the human's hands-on terminal where the org was started (does not appear on the spike socket). Therefore this path fills the "we can't see the live screens of workers / dispatcher" gap; the Secretary is already in front of the human.

### 8.1 Current — attach to independent sessions (runtime terminal adapter)

The current runtime's terminal adapter (tmux, `claude_org_runtime.terminal.tmux`) creates the child panes broker spawns (dispatcher / workers) as **independent detached sessions on a dedicated socket `claude-org-spike`** (session name `spike-<pid>-<seq>`, `isolated_session = True`). The socket is separated from existing tmux servers (renga etc.), so observation requires the explicit socket name `-L claude-org-spike`.

```bash
# 1) List existing broker sessions (read-only; socket must be specified)
tmux -L claude-org-spike list-sessions
#   Example:  spike-12345-1: 1 windows (created ...)   ← each line is 1 child pane (seq starts at 1)

# 2) Attach read-only to the session you want to peek (-r is read-only; misstrokes won't break the worker)
tmux -L claude-org-spike attach -r -t spike-12345-1
```

Operations after attach (the prefix is the default `Ctrl-b`):

| Operation | Key | Use |
|---|---|---|
| detach (stop observing and leave) | `Ctrl-b` → `d` | leave with the session alive (does not affect the process) |
| switch to another session | `Ctrl-b` → `s` | choose from the session list. **Currently per-session, so switching is needed to see the whole** |

> **Why `-r` read-only by default**: Attaching to an independent session connects directly to the worker's live TUI. Without `-r`, observation-time keystrokes may go into the worker session (intervention is closed in the Secretary/dispatcher's `send_keys` path by design, so human-hand attach is restricted to observation).

> **Validation log (2026-06-13, runtime 0.1.22)**: The socket name `claude-org-spike` / session name `spike-<pid>-<seq>` / `isolated_session = True` were confirmed hands-on against `claude_org_runtime/terminal/tmux.py` (the `SPIKE_SOCKET` constant / `_new_session_name`). The command forms `list-sessions` (multi-session enumeration) / `attach -r` (read-only flag accepted) / `kill-server` (cleanup) were connectivity-verified on a scratch socket (attaching to an actual broker org was not done in this verification since it blocks interactively).

### 8.2 Future — single-sessionification for one-shot `attach` (transport-lab design, not yet landed)

transport-lab `docs/design/broker-native-roles.md` §3.4 (defect-4 remedy) has finalized a design that re-organizes the tmux adapter into a **single `claude-org` session with multiple panes/windows**. After landing, the following one command will give an at-a-glance view of broker-managed panes (dispatcher / workers), and standard pane nav (`Ctrl-b` arrows) will work, eliminating the per-session switching of §8.1:

```bash
tmux attach -r -t claude-org   # The path after single-sessionification (§3.4 / R1) (-r=read-only). The -L socket spec also becomes unnecessary.
```

- This is **a change in the runtime's terminal adapter (`claude_org_runtime/terminal/`)**, which ja consumes via a runtime pin bump (not a step in this runbook). **On the current runtime (independent sessions), §8.1 is the only attach path**.
- The diff-reconcile design handles pane death, so the trade-off of single-sessionification (a session-level failure ripples to all panes) is outweighed by the steady benefit to observability — §3.4 concludes.
- The observer-only command considered as an observability-gap remedy (read-only tiled display of broker-managed panes) / dashboard pane live-screen tile display would be duplicative after single-sessionification because `attach -r -t claude-org` (read-only) gives an equivalent overview; this runbook does not adopt them (necessity to be re-evaluated under post-single-sessionification operations).

---

## 9. Related

- Design SoT: transport-lab `docs/design/ja-migration-plan.md` §5 (integration seam) / §5.5 (coexistence & rollback) / §8 Issue G (dogfood gate)
- Contract: [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14)
- Transport-related Secretary operational diffs: [`CLAUDE.md`](../../CLAUDE.md) "Transport (two-systems)"
- Spawn ritual (dev-channel approval → folder-trust approval): [`.dispatcher/references/spawn-flow.md`](../../.dispatcher/references/spawn-flow.md) 3-3b
- transport accessor (ja-side single seam): [`tools/transport.py`](../../tools/transport.py)
- user_common allowlist projection: [`tools/org_setup_prune.py`](../../tools/org_setup_prune.py) `--user-common-allowlist`
- attention watcher operational style: [`attention-watch.md`](attention-watch.md)
- Single-sessionification design for observability (the §8.2 future form): transport-lab `docs/design/broker-native-roles.md` §3.4 (defect 4 — the independent tmux session problem)
