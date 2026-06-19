# broker dogfood operations runbook

`claude-org-runtime broker serve` is the daemon for the **pure-backend transport
layer (`org-broker`)** that is an **opt-in alternative implementation** of
renga-peers (it co-exists with the default operational frame renga and can be
reverted at any time; "alternative" does not mean replacing renga, but another
opt-in line beside it). It provides an HTTP MCP server on localhost + queue
store + nudge delivery in a single process, and injects nudges into child panes
via the terminal adapter (tmux / WezTerm). This document is the operational
procedure for **starting up, stopping, lifecycle, and rollback** of the broker
daemon, as the prerequisite stage for **running production ja with
`ORG_TRANSPORT=broker`** in Epic #6 Issue G (#515).

The design SoT is transport-lab `docs/design/ja-migration-plan.md` Section 5
(ja integration seam) / Section 5.5 (co-existence and rollback) / Section 8
Issue G (dogfood gate). The canonical contract is
[`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md)
Surface 8 (broker auth & delivery, ratified 2026-06-14). For the dual-system
operational differences from the Secretary's side, see
[`CLAUDE.md`](../../CLAUDE.md) "Transport dual systems"; for the spawn
ceremony, see
[`.dispatcher/references/spawn-flow.md`](../../.dispatcher/references/spawn-flow.md)
3-3b.

> **Scope and untouchability constraints**: this runbook is a "procedure
> manual that makes the run possible", and **production-ja's broker run
> (hijacking org-start) will happen later in Track 3 (user hands-on)**. The
> procedures in this document all start/stop the daemon in a **test
> state-dir (a directory different from `.state/broker/`)** so as to keep
> production `.state/` clean. **The default `renga` is not removed and is
> always active as an opt-in fallback** (the safety device for rollback).
> Note that "default `renga`" here refers to the **operational frame**
> (the operational default path is renga until the production broker run in
> **Track 3** above is activated; Issue G's #515 co-existence dogfood itself
> was passed = broker ratified as opt-in on 2026-06-14, and only the
> production promotion = Track 3 is pending). In contrast, in the **code
> constant frame**, `claude_org_runtime.transport.DEFAULT_TRANSPORT` was
> flipped from `renga` to `broker` in runtime 0.1.28 (Epic #586); the two
> are not contradictory (they refer to different things: operational path vs
> code constant -- two-frame note Refs #604).

> **Verification status**: the startup / stop / lifecycle / dry-run commands
> were verified on actual hardware on 2026-06-11 in a worker worktree
> environment with **runtime 0.1.17** / tmux 3.2a / WSL2 (the key points of
> the raw logs are embedded in each section). The attach path in Section 8
> was verified on 2026-06-13 with **runtime 0.1.22**. **The hardware-verified
> broker-surface descriptions in this document are synced with runtime 0.1.22**
> (Section 1.1 setup / Section 2.1 serve flags `--root-role` / `--root-cwd` /
> Section 3.6 journal / Section 3.8 admin RPC and sidecar / Section 5(4)-(5)
> sidecar disposal). The serve / admin / sidecar surfaces added between
> 0.1.17 and 0.1.22 were cross-checked against
> `claude_org_runtime/broker/{cli,server,sidecar}.py` (0.1.22), as part of
> the D2-D6 reorganization of #515 dogfood. **Push-first addendum (0.1.24+)**:
> the nudge-delivery description in Section 3.3 includes a positioning note
> for push-first (per-pane channel sidecar / claude/channel, runtime
> push-first 0.1.24+, design SoT transport-lab `docs/design/broker-native-roles.md`
> Section 9), but the hardware verification above is at the 0.1.22 surface
> point in time, and **hardware verification of the push-first surface itself
> needs to be redone in a 0.1.24+ environment** (this addendum is positional
> for prose consistency and is not a 0.1.24+ rerun verification).

---

## 1. Role and prerequisites

- **Input / control**:
  - Environment variable `ORG_TRANSPORT` (`renga` | `broker`; unset = default
    `renga`). The daemon itself does not read the flag, but the ja-side
    generator (Section 4) emits the broker-surface allowlist based on the flag.
  - CLI arguments (`--port` / `--host` / `--state-dir` / `--backend` /
    `--no-nudge` / `--root-role` / `--root-cwd`, Section 2.1).
- **Output / side effects**:
  - localhost HTTP MCP endpoint (default `http://127.0.0.1:48720/mcp`) and
    admin RPC endpoint (`/admin`, Section 3.8).
  - queue store + JSONL journal (`<state-dir>/queue.jsonl`; default
    state-dir = `.state/broker`).
  - daemon sidecar (`<state-dir>/daemon.json` discovery metadata, non-secret +
    `<state-dir>/admin.token` 0600 secret, Section 3.8; deleted on graceful
    stop / left behind on SIGTERM).
  - Nudge injection into child panes (via terminal adapter; disabled by
    `--no-nudge`).
- **Dependency direction (one-way)**: `broker -> terminal / dispatcher.choose_split`.
  **claude-org-ja does not import broker** (inactive under the default renga flag).
- **Observability (important)**: on the tmux backend, the child panes that
  broker spawns (dispatcher / workers) launch as **detached independent
  sessions** and do not appear on the screen by default (the Secretary, being
  a logical pane, remains on the human's local terminal). For the read-only
  attach path into the running child panes, see Section 8.
- **Note on the CLI name (important)**: the start command is
  **`claude-org-runtime broker serve`** (a subcommand of the top-level CLI).
  `claude-org-runtime-broker` is the CLI's `prog` name (the header notation
  in `--help`); **no console_script exists** under that name. You can also
  start it equivalently via `python -m claude_org_runtime.broker serve`.

```
$ claude-org-runtime broker --help
usage: claude-org-runtime broker [-h] {serve} ...
    serve     start the org-broker daemon on localhost (Ctrl+C to stop).
```

### 1.1 isolated venv setup (D6)

To isolate dogfood from the production environment, the broker org is run in
an **isolated venv (WSL/tmux isolated clone)**. This venv needs both
**`claude-org-runtime>=0.1.22`** (the version with the D2-D6 surface) and
**`core-harness>=0.3.2`**.

- **runtime 0.1.22 or higher is required**: D2-D6 in this document
  (`--root-role` / `--root-cwd` / `/admin` RPC / sidecar) are **surface added
  in 0.1.22** and are not in 0.1.17-0.1.21. **However, the current pin on the
  ja side is `claude-org-runtime>=0.1.17,<0.2` (lower bound 0.1.17)**, so
  `pip install -e .` does **not guarantee** 0.1.22 (the lower bound 0.1.17 can
  be resolved). For dogfood, install 0.1.22 or higher explicitly with
  `pip install 'claude-org-runtime>=0.1.22,<0.2'` (or bump to the latest 0.1.x
  with `pip install -U`). To permanently raise the lower bound, bump the pin
  in `pyproject.toml` / `requirements.txt` separately (out of scope for this
  runbook).
- **core-harness is not a runtime dependency** (runtime's `Requires-Dist` is
  only `jsonschema`; runtime does not import `core_harness`). On the other
  hand, **claude-org-ja-side tools** (`tools/check_role_configs.py`, etc.)
  import `core_harness`, so it is required for ja org operation. It is not
  installed by `pip install claude-org-runtime` alone, and ja tools will fall
  over with `ImportError` in an isolated venv. So resolve the pin
  **`core-harness>=0.3.2,<0.4`** from `pyproject.toml` / `requirements.txt`
  via **`pip install -e .` from the ja repo** (or, in a minimal-runtime-only
  setup, explicitly add `pip install 'core-harness>=0.3.2,<0.4'`).
- pin rationale: `core-harness` is 0.x, so an x-bump (minor) policy can
  include breaking changes, and we range-pin to `>=0.3.2,<0.4` (see comments
  in `requirements.txt` / design Q9-Q10).

```bash
# isolated venv example (at the root of the isolated clone)
python3 -m venv .venv && . .venv/bin/activate
pip install -e .   # resolves core-harness>=0.3.2 and claude-org-runtime>=0.1.17 per pin
# But the -e . runtime lower bound is 0.1.17. D2-D6 surface needs 0.1.22+, so explicitly override:
pip install 'claude-org-runtime>=0.1.22,<0.2'
# In a minimal runtime-only setup, also add core-harness explicitly:
#   pip install 'core-harness>=0.3.2,<0.4'
# Verify:
python3 -c "from claude_org_runtime import __about__; print(__about__.__version__)"   # 0.1.22 or higher
```

---

## 2. broker daemon startup hardware check

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
| `--port` | `48720` (`DEFAULT_PORT`) | localhost bind port. `0` is ephemeral (OS-assigned; the actual port appears in the `listening on` line in the startup log). |
| `--host` | `127.0.0.1` | bind host. Localhost-only by design. |
| `--state-dir` | `.state/broker` (`DEFAULT_STATE_DIR`, relative to CWD) | Write target for `queue.jsonl` / `daemon.json` / `admin.token`. **Always pass a separate directory during verification** (Section 2.3 / Section 7). |
| `--backend` | OS auto-selected (POSIX=`tmux` / Windows=`wezterm`) | terminal adapter. `VALID_BACKENDS = (wezterm, tmux)`. Ignored under `--no-nudge`. |
| `--no-nudge` | (disabled) | Do not create a terminal adapter; turn off nudge delivery (**queue only**). Use when you want to verify wire-level reachability backend-independently. |
| `--root-role` | `worker` (`DEFAULT_ROOT_ROLE`) | The **permission tier (auth_role) the manual-verification root token binds to**. The `tools/list` public surface is structurally narrowed by this tier (Section 3.4). Accepted set `ROOT_ROLE_CHOICES = (worker, curator, dispatcher, secretary)`. Default `worker` = messaging 4 (current behavior unchanged); `secretary` = all 13. |
| `--root-cwd` | (when omitted, the daemon's startup cwd = `os.getcwd()`) | **Make the bind carry the cwd of the root pane (human-driven secretary)** (runtime#61). `spawn_*` relative cwd is resolved relative to this cwd (absolute is as-is). Even if you pass a relative path, it is **absolutized** relative to the daemon startup cwd at bind time (the resolution anchor is always absolute). The **operational contract is that the daemon is started from the session root**, and that startup directory is the resolution anchor for relative spawns. If you launch from somewhere other than the session root, make it explicit with this flag. |

> **0.1.17 -> 0.1.22 diff (D2)**: `--root-role` / `--root-cwd` are flags added
> in 0.1.22 (runtime#61). The root cause of runtime#61 was that, without the
> bind carrying cwd, `spawn_*` calls from a human-driven secretary that pass
> relative cwd would lose the resolution anchor and be rejected / fall back to
> a wrong base. When `--root-cwd` is omitted, the daemon startup cwd is used,
> so **always start the daemon from the session root** (or specify `--root-cwd`
> explicitly).

`serve` blocks in the foreground. Two stop paths exist: (a) `Ctrl+C` / `SIGINT`,
or (b) admin RPC `shutdown` (Section 3.8) (both go through `run()`'s `finally`
to stop gracefully and record `broker_stopped` + delete the sidecar). At
startup, it generates one admin token and writes it 0600 to the sidecar
(Section 3.8), issues one root token for manual verification, and prints to
stdout the JSON to pass to `--mcp-config`:

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

> **Side effects at startup (0.1.22)**: as noted above, at startup it writes
> `<state-dir>/daemon.json` (discovery metadata, non-secret) and
> `<state-dir>/admin.token` (admin RPC auth token, 0600 secret), and registers
> the root token as a **logical pane** in the pane registry
> (`logical_pane_registered` journal, Section 3.6). For details see Section 3.8.

### 2.2 startup / stop commands (production form)

The startup form for production ja (Track 3, user hands-on) is as follows.
**This section just presents the command shapes; the verification in this
document only runs the test-state-dir version in Section 2.3.**

```bash
# Start (default state-dir = .state/broker, tmux backend auto-selected)
claude-org-runtime broker serve

# Stop (split by startup form):
#   - Foreground serve (blocking in this shell): Ctrl+C (SIGINT). Graceful stop path:
#     run()'s finally calls stop(); journal tail gets one line of broker_stopped;
#     daemon.json / admin.token sidecar are also deleted.
#   - Background daemon (started with nohup ... & etc.): send SIGTERM:
#       kill -TERM <pid>
#     SIGINT (kill -INT) does not work on a background daemon and the process
#     remains (reproduced twice in the 2026-06-13 rollback drill). Use SIGTERM
#     to stop the background daemon.
#     However, since SIGTERM does not go through run()'s finally, broker_stopped
#     is not emitted, and the daemon.json / admin.token sidecar are not deleted
#     and are left behind (explicit teardown in Section 5(5)).
#     Background-stop confirmation is done by "process gone + unread crosscheck
#     + sidecar teardown" (Section 5(4)/(5)).
#   - Graceful alternative (recommended, signal-independent): call admin RPC
#     shutdown (Section 3.8). It does broker_stopped recording + automatic
#     sidecar deletion in one shot, even for a background daemon.
```

### 2.3 Start -> reach -> stop with a test state-dir (proof of production `.state` inviolability)

Verification **absolutely must not touch production `.state/broker/`**. Pass a
temporary directory via `--state-dir` and confirm that `queue.jsonl` is
created only under that test path.

> **cwd drift note (mandatory)**: the default of `--state-dir` is **relative
> to CWD** `.state/broker`. In a worker worktree and in the canonical
> claude-org root, `.state/` are different things, so directly hitting the
> relative path makes "which `.state` are you looking at" ambiguous and risks
> mis-applied inviolability checks / production `.state` contamination. In
> this document we **fix the canonical root in absolute-path variable
> `CANON_ROOT` and also fix the test state-dir in absolute-path variable
> `TEST_STATE` (outside the repo)**, so we never poke `.state/broker` bare-relative.

```bash
# 0) Fix the prerequisite variables (never poke relative paths bare-handed)
CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root holding the production .state/broker (adjust per env)
TEST_STATE=/tmp/claude/broker-smoke-A               # test state-dir (must be an absolute path outside the repo)

# 1) Prepare the test state-dir (mkdir parent + use an unused path to avoid mixing in existing logs)
mkdir -p "$TEST_STATE"
test -e "$TEST_STATE/queue.jsonl" && echo "WARN: existing queue.jsonl present. Use another path or move aside before verifying"

# 2) Start (use --no-nudge for backend-independent reachability only; -u flushes stdout immediately)
python3 -u -m claude_org_runtime.broker serve \
    --state-dir "$TEST_STATE" --port 48799 --no-nudge
```

From another terminal (or driver script), hit the HTTP MCP with the token
shown in the startup log:

| Step | Expected |
|---|---|
| `initialize` | `serverInfo = {"name": "org-broker", "version": "0.1.0"}` + `Mcp-Session-Id` header issued |
| `tools/list` (worker token) | **only the messaging 4** `["check_messages", "list_peers", "send_message", "set_summary"]` (tier gating, Section 3.4) |
| `tools/call send_message` (self-addressed) | `{"ok": true, "delivered_to": "manual-test"}` |
| `tools/call check_messages` | drain the `hello broker` you just sent, at-most-once |

To stop, send `SIGINT` to serve. **On a clean shutdown, exit code 0**.

**Inviolability check on `.state` (mandatory)**: after verification, confirm
that production `.state/broker/` was not created. The queue is written only
under the test path you passed.

```bash
# queue exists only under TEST_STATE
ls "$TEST_STATE/queue.jsonl"
# Production side (canonical root's absolute path) must not have been created.
# Do not use relative .state/broker.
test -e "$CANON_ROOT/.state/broker" && echo "NG: production .state/broker was contaminated" || echo "OK: production .state is unchanged"
# Also no test garbage was dropped directly under the current worktree (prevents CWD-relative default confusion).
test -e "$PWD/.state/broker" && echo "NG: .state/broker was created directly under the worktree" || echo "OK: directly under the worktree also unchanged"
```

> **Verification log (2026-06-11, hardware)**: both `--no-nudge` and
> `--backend tmux` were successful round-trip on
> `initialize -> tools/list -> send_message -> check_messages`, with
> **exit 0** on `SIGINT`. `tools/list` showed only the messaging 4 at the
> worker tier. Production `.state/broker/` was not created (the test path
> only had `queue.jsonl`). The tmux backend works without a live tmux
> server -- the adapter is lazily created, so startup / stop completes
> (messaging probe is skipped because there is no child pane to actually
> inject a nudge into).

---

## 3. start / stop / token / queue lifecycle

The broker's internal state transitions are split across
`claude_org_runtime/broker/`'s `server` / `store` / `tokens` / `surface`.
The four operational flows you need to understand are:

### 3.1 token issuance (`tokens.py`)

- One **per-agent token** is issued at spawn (`issue_token`,
  `secrets.token_urlsafe(32)`). token <-> `AgentBind`
  (`agent_id` / `name` / `role` / `auth_role` / `pane_id` / `cwd` / `kind`).
- **`role` (display-only, mutable via `set_pane_identity`) and `auth_role`
  (immutable permission tier, fixed at issuance) are separated**. Tier gating
  is determined only by `auth_role`; the self-reported display role cannot
  escalate privileges. The `auth_role` of a spawn child is capped by the
  caller's tier (`capped_auth_role`).
- `mcp_config_for(token)` generates the JSON to pass to `--mcp-config`
  (embedding the token in the static header `Authorization: Bearer <token>`;
  env reference `${VAR}` is not used).
- journal: `token_issued`.

### 3.2 registration (HTTP handler in `server.py`)

- The moment the child pane's Claude / Codex reaches `initialize` (MCP),
  `AgentBind.registered = True` (with `registered_at` recorded). **Only
  registered binds are delivery targets** (this prevents delivery to
  not-yet-connected / DELETEd clients).
- journal: `agent_registered`.

### 3.3 queue store + nudge delivery (`store.py` / `server.py`)

- `send_message` (`enqueue`) creates the entry with the **token-derived
  attribution** (self-report not allowed). The destination registered-check
  and the queue append are done atomically **in the same lock scope**, after
  which `_journal` and `_trigger_nudge` are called outside the lock (so that
  queue persistence is not coupled with PTY injection / to avoid the
  double-acquisition deadlock on the non-reentrant Lock).
- Nudge delivery injects **only one stereotyped line via PTY**; the body is
  not passed through (the receiver pulls it via `check_messages`).
  **After the push-first redesign (runtime push-first, 0.1.24+), this PTY
  nudge + pull is positioned as the *fallback* delivery path* used when the
  per-pane channel sidecar (`server:org-broker-channel`'s `claude/channel`
  injection) does not work**, and push-first becomes the runtime default
  **delivery mode** (the broker's internal push-vs-pull default, which is
  a separate axis from the `renga`/`broker` default selection of transport;
  design SoT: transport-lab `docs/design/broker-native-roles.md` Section 9.
  Actual behavior on the runtime surface version this runbook is synced
  with follows that version). If the adapter is unreachable or the target
  has not arrived, retry up to
  `nudge_defer_interval` (default 2.0s) x `nudge_defer_max_tries`
  (default 30).
- `check_messages` (`drain`) drains the queue **at-most-once** and returns.
- journal: `message_enqueued` -> `nudge_sent` / `nudge_deferred` /
  `nudge_failed` -> `queue_drained`.

### 3.4 tier gating (`surface.py`)

The public surface **changes structurally** by `auth_role` (default-deny
allowlist). Tools not in `tools/list` are also blocked by
`[tool_not_authorized]` if called (the allowlist is one half of two-layer
defense).

| auth_role tier | Public surface |
|---|---|
| worker / curator / unknown | messaging 4 (`send_message` / `check_messages` / `list_peers` / `set_summary`) |
| dispatcher | messaging 4 + ops (`list_panes` / `inspect_pane` / `send_keys` / `poll_events` / `close_pane` / `set_pane_identity` / `spawn_claude_pane` / `spawn_codex_pane`) |
| secretary | dispatcher's surface + `spawn_pane` (secretary-only) |

> `new_tab` / `focus_pane` are **not on the broker surface** (intentional
> exclusion). Initial surface = ported 12 + `spawn_codex_pane` = 13.

### 3.5 stop / invalidation

- Graceful stop (`run()`'s `finally` -> `stop()` + sidecar deletion):
  the graceful stop paths are **(a) SIGINT / Ctrl-C on a foreground serve**
  and **(b) admin RPC `shutdown` (Section 3.8)**. Both go through `run()`'s
  `finally`, which is the only invoker of `stop()` -- `stop()` shuts down
  and closes the HTTP server, leaves `broker_stopped` in the journal, and
  then deletes the `daemon.json` / `admin.token` sidecar (`remove_sidecar`,
  Section 3.8). **`broker_stopped` emission and sidecar deletion happen
  only on the graceful path (SIGINT / admin RPC shutdown)**. If you stop a
  background daemon with `kill -TERM`, it does not go through `run()`'s
  `finally`, so `broker_stopped` is not left behind, and the
  **`daemon.json` / `admin.token` sidecar is not deleted and remains in
  place** (stop confirmation goes by process disappearance + unread
  crosscheck; cleanup is done by explicit sidecar teardown, Section
  5(4)/(5)). Note that SIGINT (`kill -INT`) does not work on a background
  daemon and the process remains (reproduced twice in the 2026-06-13
  rollback drill).
- Session termination (MCP `DELETE`): invalidates the `session_id` of that
  bind and drops `registered = False` (so disconnected clients do not
  remain in `list_peers` / as delivery targets). journal: `session_closed`.
- Pane close (`close_pane`): after killing in the adapter, the registry pop
  and token revoke happen atomically in one lock scope. journal:
  `pane_closed` + event `pane_exited`.

### 3.6 journal events (`queue.jsonl`)

Appended one JSON per line to `<state-dir>/queue.jsonl`. Observation points
during operation:

```
broker_started -> token_issued -> logical_pane_registered (root pane on startup)
  -> agent_registered -> message_enqueued
  -> nudge_sent / nudge_deferred / nudge_failed -> queue_drained
  -> pane_spawned / pane_identity_set (on spawn / identity operations)
  -> session_closed / pane_closed -> broker_stopped
```

> **Events added in 0.1.22 (D3)**: `logical_pane_registered` (registers the
> root token as a logical pane at startup, Section 3.8) / `pane_spawned`
> (`spawn_claude_pane` / `spawn_codex_pane` / `spawn_pane`) /
> `pane_identity_set` (`set_pane_identity`). `broker_stopped` remains at
> the tail only on graceful stop (SIGINT / admin RPC shutdown)
> (Section 3.5 / Section 5(4)).

> **Verification log (hardware, messaging round-trip)**: confirmed
> `broker_started -> token_issued -> agent_registered ->
> message_enqueued(chars=12) -> queue_drained(count=1) -> broker_stopped`
> in one cycle.

### 3.7 broker extra error codes

In addition to the renga codes, broker can return the following. The
secretary / dispatcher route unknown codes to escalate via the default
branch ([`CLAUDE.md`](../../CLAUDE.md) "Error branching").

| Code | Trigger |
|---|---|
| `[token_invalid]` | Bearer token not in the bind table / revoked (HTTP 401, JSON-RPC -32001) |
| `[session_invalid]` | Called other methods before `initialize` |
| `[tool_not_authorized]` | Called a tool outside the auth_role tier's public surface |
| `[no_backend]` | Called a pane operation while the terminal adapter is absent (`--no-nudge` startup) (= adapter_unavailable) |
| `[nudge_failed]` | Nudge injection did not arrive up to the defer cap |
| `[peer_not_found]` | `send_message` destination is not in a registered bind |
| `[name_taken]` | Pane name duplication |
| `[admin_unauthorized]` | Called the `/admin` RPC without an admin token / with an invalid token (HTTP 401, Section 3.8) |

> The table above adds `[admin_unauthorized]` (the auth gate of the admin
> surface, included because of high operational frequency) to the codes of
> the `/mcp` (messaging / ops) surface. The admin surface (`/admin`) is
> authenticated by a separate `admin_token` from the per-agent bearer, and
> in addition to `[admin_unauthorized]` it can also return `[parse_error]`
> / `[invalid_params]` / `[unknown_admin_method]` / `[invalid_role]` /
> `[invalid_cwd]` / `[invalid_name]`. **The admin RPC code list is in
> Section 3.8** (the path is separate, so it is not aggregated in the
> table above).

### 3.8 admin RPC (token mint / graceful shutdown) and daemon sidecar

0.1.22 added the **admin surface for externally controlling a running
daemon** and the **discovery sidecar** (runtime#61 / #63, `_handle_admin`
in `server.py` / `sidecar.py`). This is an independent control surface
from messaging / ops (`/mcp`).

**admin RPC (`/admin`)**:

- The endpoint is `http://<host>:<port>/admin` (`broker.admin_url`). A
  separate path from `/mcp` (messaging / ops).
- Authentication is not via the per-agent bearer but via **`admin_token`**
  (`secrets.token_urlsafe(32)`, generated at startup). `Authorization:
  Bearer <admin_token>` compared in constant time (`hmac.compare_digest`).
  **If no admin token is configured, the path itself is hidden (HTTP 404)**
  -- you can disable the admin surface for internal tests. Invalid /
  missing token is HTTP 401 `[admin_unauthorized]`.
- Methods (JSON-RPC-ish `{"method": ..., "params": {...}}`):
  - `mint_token` -- mint a new root token against a running daemon (`role`
    = auth_role). Like the root token, since it is not a spawn child, the
    tier capping (`capped_auth_role`) is not applied; binds at the
    requested tier. `params.cwd` is the resolution anchor for relative
    spawns (absolutized as on the CLI).
  - `shutdown` -- request a graceful shutdown. Returns ack
    (`{"ok": true, "shutting_down": true}`) first, then calls
    `request_shutdown()`; the actual stop (`stop()` + sidecar deletion)
    is performed by the foreground loop in `run()` (this avoids a deadlock
    where calling `shutdown` directly from the handler thread would block
    on itself). **A signal-independent stop path**; this becomes the
    graceful-stop method in environments where SIGTERM/SIGINT is hard to
    send (e.g. Windows).
- **Error codes for `/admin` (separate from the `/mcp` table in Section 3.7)**:
  in addition to the auth failure `[admin_unauthorized]` (401, listed in
  Section 3.7), there are: JSON body invalid `[parse_error]` (400) /
  `params` not an object `[invalid_params]` (400) / unknown method
  `[unknown_admin_method]` (400). `mint_token` returns `[invalid_role]`
  (unaccepted role) / `[invalid_cwd]` (cwd is not a string) /
  `[invalid_name]` (name is not a string) at argument validation (all
  400 / `{"ok": false, "error": ...}`). The secretary / dispatcher route
  unknown codes to escalate via the default branch (same policy as
  Section 3.7).

**daemon sidecar (2 files under `<state-dir>/`, `sidecar.py`)**:

| File | Contents | Secret | Permissions | At stop |
|---|---|---|---|---|
| `daemon.json` (`SIDECAR_NAME`) | Discovery metadata (`pid` / `host` / `port` / `state_dir`(absolute) / `backend`(resolved actual value) / `started_at` / `journal_offset`) | No | Normal | Deleted on graceful stop (left on SIGTERM) |
| `admin.token` (`ADMIN_TOKEN_NAME`) | admin RPC auth token | **Yes** | 0600 (temp -> atomic rename to avoid torn reads. **On Windows NTFS, only the read-only bit is set**, group/other read is a known limitation that does not actually drop) | Deleted on graceful stop (left on SIGTERM -> explicit teardown in Section 5(4)/(5)) |

- Both are published atomically via `os.replace` so partial writes / torn
  reads are not exposed. `journal_offset` is the byte length of
  `queue.jsonl` at the start of the run, and serves as the starting point
  for limiting stop confirmation (`broker_stopped` detection) to a slice
  of that run, **to avoid false positives from residue of past runs**.
- **logical pane registration**: at startup, the root token is loaded into
  the pane registry as a **logical pane** (`register_logical_pane`,
  journal `logical_pane_registered`). Because `bind.pane_id = None`, no
  PTY nudge is sent (the human reads via `check_messages`); having the
  secretary appear in `list_panes` means that even with only one spawned
  child, `close_pane` does not misfire `[last_pane]` and can close the
  child (consistent with "the secretary is a logical pane" in Section 8).

---

## 4. settings regeneration dry-run with `ORG_TRANSPORT=broker`

Dry-run the **transport-descriptor-driven generator** added in Epic #6 D/E
with `ORG_TRANSPORT=broker` to confirm that the broker-surface allowlist is
emitted. **Do not write actual files.**

### 4.1 single SoT (descriptor)

The ja-side transport accessor [`tools/transport.py`](../../tools/transport.py)
consumes runtime's transport surface descriptor
(`claude_org_runtime.transport`) as the sole SoT (no hardcoding). The
resolution order is **explicit argument > `ORG_TRANSPORT` env > default
`renga`**. Allowlist generation goes through
`claude_org_runtime.settings.generator.transport_allowlist(role, transport=...)`.

### 4.2 per-role allowlist dry-run

```bash
# Compare default renga (unset) and broker projections per role (read-only, no writes)
for role in worker curator dispatcher secretary; do
  echo "--- $role renga(default) ---"
  python3 -c "from claude_org_runtime.settings.generator import transport_allowlist as t; print(t('$role'))"
  echo "--- $role broker ---"
  ORG_TRANSPORT=broker python3 -c "from claude_org_runtime.settings.generator import transport_allowlist as t; print(t('$role'))"
done
```

| role | renga (default) | broker (`ORG_TRANSPORT=broker`) |
|---|---|---|
| worker / curator | `mcp__renga-peers__*` 14 | `mcp__org-broker__*` messaging 4 |
| dispatcher | `mcp__renga-peers__*` 14 | messaging 4 + ops 8 (does not include `spawn_pane`) |
| secretary | `mcp__renga-peers__*` 14 | messaging 4 + ops + `spawn_pane` + `spawn_codex_pane` (13) |

> The renga default is a model where all roles share the same surface (14)
> and are narrowed by the allowlist. Broker **structurally** blocks role
> tiers, so the allowlist becomes one half of the two-layer defense (on
> the safe side).

### 4.3 `~/.claude/settings.json` user_common allowlist regeneration dry-run

[`tools/org_setup_prune.py`](../../tools/org_setup_prune.py)
`--user-common-allowlist` projects the MCP `permissions.allow` of
user_common (`~/.claude/settings.json`) into the active transport. **During
verification, do not touch the actual `~/.claude/settings.json`** -- point
`--user-common-settings-path` to a test path and add `--dry-run`.

```bash
# Prepare test settings (with renga entries) and dry-run
TEST_SET=/tmp/claude/usercommon-settings.json   # not the actual ~/.claude/settings.json

# Create test settings with renga messaging entries (empty / missing would not produce the drop-renga expected output)
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

# Default renga: strict no-op (touches the file 0 bytes)
python3 tools/org_setup_prune.py --user-common-allowlist --dry-run \
    --user-common-settings-path "$TEST_SET"

# broker: drop renga-peers, ensure org-broker messaging tier (dry-run = display only)
ORG_TRANSPORT=broker python3 tools/org_setup_prune.py --user-common-allowlist --dry-run \
    --user-common-settings-path "$TEST_SET"
```

Expected output:

```
# renga (default)
[org_setup_prune] user_common allowlist: transport=renga (default); no-op -- ~/.claude/settings.json unchanged ...

# broker
=== user_common allowlist (transport=broker): /tmp/claude/usercommon-settings.json ===
  - mcp__renga-peers__send_message      (drop renga messaging, below)
  + mcp__org-broker__send_message       (add org-broker messaging, below)
  ...
```

> **Verification log (hardware)**: default renga is strict no-op (the test
> file is not changed by even 1 byte). With `ORG_TRANSPORT=broker`, the
> renga-messaging-4 -> org-broker-messaging-4 diff is shown in dry-run.
> **Zero actual writes due to `--dry-run`** (confirmed the test file
> contents are unchanged). Non-MCP entries like `Bash(...)` are preserved
> in order.

---

## 5. Specifying the 5 rollback conditions as commands (SoT Section 5.5)

A full rollback of `ORG_TRANSPORT=broker` -> `renga` is not instant just by
flag flipping (**running broker-spawned panes do not return immediately**;
they hold `--mcp-config` / pull-premise prose). Run the SoT Section 5.5
**5 completion conditions** in order.

> **Prerequisite variables (avoid cwd drift)**: the commands below do not
> poke relative `.state/broker` bare-handed. Fix the state-dir the daemon
> actually used via `serve --state-dir` in an absolute-path variable, and
> also fix the canonical root explicitly. In production rollout (Track 3),
> `BROKER_STATE` points to the production `.state/broker`.
>
> ```bash
> CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root (adjust per env)
> BROKER_STATE="$CANON_ROOT/.state/broker"            # the --state-dir passed to the daemon at serve time
> ```

### (1) flag flip back

```bash
# Flip env back to renga (default). The next spawned pane will point to renga.
unset ORG_TRANSPORT
# If you had written it into persistent shell config, also remove from there:
#   grep -rn "ORG_TRANSPORT" ~/.bashrc ~/.zshrc ~/.profile
```

**Check**: `python3 -c "from claude_org_runtime.transport import resolve_transport as r; print(r())"`
returns `renga`.

### (2) regenerate artifacts (back to renga allowlist)

If the flag is back to renga, **the generator (per-role `settings.local.json`)
returns to identity (bit-equivalent)**. Actually regenerate the artifacts to
go back to the renga surface.

```bash
# First dry-run to confirm the diff (if broker surface remains, you should see the diff back to renga)
python3 tools/org_setup_prune.py --all --dry-run

# If OK, apply (writes back the renga allowlist; .bak is left)
python3 tools/org_setup_prune.py --all
```

**user_common (`~/.claude/settings.json`) is handled separately (important)**:
`--user-common-allowlist` is **a complete no-op in renga mode** (the SoT of
the renga allowlist is the org-setup skill + permissions.md, not this tool,
so it does not touch the file). Therefore if you have applied broker in
dogfood (`mcp__org-broker__*` is in user_common), running
`--user-common-allowlist --dry-run` in renga **will not bring broker
surface back**. Explicitly revert user_common with one of the following:

```bash
# Method A (recommended): restore the .bak made when broker was applied
#   Backup naming is settings.json.bak.<YYYYMMDD-HHMMSS> (backup_path)
ls -t ~/.claude/settings.json.bak.* 2>/dev/null | head     # check the most recent backup
# cp <the confirmed .bak> ~/.claude/settings.json          # restore after eyeballing contents

# Method B: if no backup, manually swap the messaging surface (org-broker -> renga-peers)
#   In ~/.claude/settings.json's permissions.allow, replace
#   "mcp__org-broker__{send_message,check_messages,list_peers,set_summary}" with
#   "mcp__renga-peers__..." (do not touch non-MCP entries)
```

**Check**: `mcp__org-broker__*` does not remain in either the per-role
`settings.local.json` or the **user_common (`~/.claude/settings.json`)**.

```bash
# Per-role settings under the repo. The glob (*/.claude/) does not pick up
# hidden role dirs (.dispatcher/.claude/ / .curator/.claude/ etc.) and in zsh
# fails to match, so grep itself does not run and you get a false OK. Don't
# use the glob; grep recursively from the repo root (grep -r descends into
# hidden dirs as well). Limit to settings*.json to avoid false hits.
if grep -rl --include="settings*.json" "mcp__org-broker__" . 2>/dev/null | grep -q .; then
  echo "NG: broker surface remains on the repo side:"; grep -rl --include="settings*.json" "mcp__org-broker__" . 2>/dev/null
else
  echo "OK: no broker surface on the repo side"
fi
# Don't forget user_common (the home's settings.json)
grep -l "mcp__org-broker__" ~/.claude/settings.json 2>/dev/null && echo "NG: broker surface remains in user_common" || echo "OK: no broker surface in user_common"
```

### (3) respawn active broker panes (restart via the renga path)

Running broker-spawned panes do not return on flag flip alone. Suspend/resume
or respawn via the renga path.

```bash
# Get the current broker panes (from the renga secretary / dispatcher)
#   mcp__renga-peers__list_panes  to check the pane list
# Close broker-token panes one by one -> respawn via the renga path (the normal org-delegate flow)
# Pane control is closed to dispatcher/secretary, so move messaging back to renga first and chase the panes after (the 2-stage in Section 5.5).
```

**Check**: no broker-bound panes remain in `list_peers` / `list_panes`.

### (4) broker daemon stop order (revoke remaining panes -> daemon stop)

**Order matters**: first revoke (close) the remaining panes to take them out
of delivery targets, then stop the daemon last.

**The stop signal differs by startup form (reflecting hardware-measured
results from the 2026-06-13 rollback drill)**: a foreground serve stops
gracefully on Ctrl-C (SIGINT) and emits `broker_stopped`, but a daemon
started in the background with `nohup ... &` etc. **does not respond to
SIGINT (`kill -INT`) and the process remains** (reproduced twice in the
drill). Stop the background daemon with **SIGTERM (`kill -TERM`)**.
However, since SIGTERM does not go through `run()`'s `finally` (= the only
path of `stop()` + sidecar deletion), **(i) `broker_stopped` is not
emitted** (the journal tail remains at `broker_started` / `token_issued`,
etc.) and **(ii) `daemon.json` / `admin.token` sidecar is not deleted
and remains in the state-dir** (D4). `admin.token` is the admin RPC's
authentication secret, so its residue is explicitly torn down in (5). The
stop confirmation method and the cleanup also differ by path.

> **When you want to gracefully stop a background daemon (recommended
> alternative)**: instead of SIGTERM, hit **admin RPC `shutdown`
> (Section 3.8)** and it goes through `run()`'s `finally` to do
> `broker_stopped` recording + automatic sidecar deletion in one shot
> (signal-independent). The admin token is read from
> `<state-dir>/admin.token`. Sidecar teardown in (5) is only required if
> you stopped via SIGTERM.

```bash
# 1) Close remaining broker panes (token revoked; close_pane journal: pane_closed)
#    From renga/dispatcher, close_pane each broker pane.
# 2) Once everything is revoked, stop the daemon (split by startup form):
#    - Foreground serve (blocking in this shell): do not run this command; press Ctrl-C (SIGINT). Graceful stop.
#    - Background daemon (nohup ... & etc.): send SIGTERM. SIGINT (kill -INT) does not work.
kill -TERM <broker_pid>   # background daemon stop; if foreground serve, press Ctrl-C instead
# 3) Stop confirmation (method differs by path):
#    a) Only on graceful stop (foreground SIGINT / Ctrl-C) does broker_stopped remain in the journal tail:
tail -n 3 "$BROKER_STATE/queue.jsonl"
#    b) For SIGTERM (background daemon), broker_stopped is not emitted, so confirm
#       via process disappearance + unread crosscheck (consistent with the unread
#       crosscheck script in Section 5(5)).
#       Right after SIGTERM there is termination processing, which can give a
#       false judgement, so wait for disappearance in a short timeout loop:
for i in $(seq 1 10); do
  kill -0 <broker_pid> 2>/dev/null || { echo "OK: daemon process gone"; break; }
  sleep 1
done
kill -0 <broker_pid> 2>/dev/null && echo "NG: daemon is still alive"
#       Run the unread crosscheck (enqueued vs drained) using the script in
#       Section 5(5) (don't duplicate it here).
```

> **runtime follow-up candidate (implementation out of scope for this
> task)**: if the runtime-side SIGTERM handler routes through `run()`'s
> `finally` path (`stop()` + `remove_sidecar`), then even on SIGTERM stop,
> `broker_stopped` emit and automatic sidecar deletion
> (`daemon.json` / `admin.token`) will run, and **both the stop-confirmation
> path split and the manual sidecar teardown in (5) become unnecessary**.
> This runbook stops at clarifying the procedure; the runtime implementation
> is considered as a separate Issue. The current graceful alternative is
> admin RPC `shutdown` (Section 3.8).

### (5) confirmation of teardown of old token / queue store / sidecar (no residue under `.state/broker/`)

```bash
# Crosscheck the journal to ensure no unread (messages enqueued but not drained) remain.
# queue_drained carries count=N, so compare against the sum of N rather than "event count" (avoids false judgement across multiple drains).
BROKER_STATE="${BROKER_STATE:?fix BROKER_STATE first (Section 5 prerequisite variables)}" \
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
    print("OK: queue.jsonl missing (already torn down)"); raise SystemExit
unread = enq - drained_msgs
print(f"enqueued={enq} drained_msgs={drained_msgs} unread={unread}")
print("OK: no unread" if unread <= 0 else f"NG: {unread} unread remain (must be drained before daemon stop)")
PY

# Sidecar residue check and teardown (D4). On graceful stop (SIGINT / admin
# RPC shutdown), run()'s finally has already auto-deleted daemon.json /
# admin.token. On SIGTERM stop, both remain, so tear them down explicitly.
# admin.token is the admin RPC auth secret -- always destroy it.
for f in admin.token daemon.json; do
  if [ -e "$BROKER_STATE/$f" ]; then
    echo "residue: $BROKER_STATE/$f (leftover from SIGTERM stop, tearing down)"
    rm -f "$BROKER_STATE/$f"   # in environments where rm is not allowed, use shred/truncate per operational rules
  else
    echo "OK: no $f (deleted on graceful stop or never created)"
  fi
done

# Per-agent token / bind table is in-process in-memory (gone when the daemon stops; not persisted).
# What persists is the journal (queue.jsonl) and, on SIGTERM residue, the 2 sidecar files.
# Tear down the queue store file to leave no trace (in environments where rm is not allowed, use truncate / archive):
#   mv "$BROKER_STATE" "$BROKER_STATE.archived-$(date +%Y%m%d)"   # or delete per operational rules
```

> **Persistence of token / bind / sidecar (D4)**: per-agent `AgentBind`
> (token value, bind table) is only in-memory in the daemon process and is
> not persisted (the journal keeps the *fact* of `token_issued`, but not
> the value). **The exception is the admin token**: this is a secret
> written to disk as `<state-dir>/admin.token` (0600); on graceful stop
> (SIGINT / admin RPC shutdown), `run()`'s `finally` (`remove_sidecar`)
> auto-deletes it along with `daemon.json`, but **on SIGTERM stop it is
> not deleted and remains**. Therefore what can remain in state-dir is
> `queue.jsonl` (journal + un-drained messages) plus, on SIGTERM residue,
> `admin.token` / `daemon.json` for a total of 3 files. (5) is closed by
> this unread crosscheck and the teardown of those 3 files.

---

## 6. How to take the billing-neutral attestation

Confirm that every agent spawned by broker is **interactive TUI (no
headless)** via the actual argv. This is evidence of billing neutrality
(no non-interactive launches like `claude -p` / `codex exec` that would
incur API billing).

### 6.1 Structure of the multi-layer defense (guard at spawn)

Broker's billing neutrality is structurally guaranteed by a
**default-deny allowlist at spawn time** (`surface.py`):

- `build_claude_argv` / `build_codex_argv` only allow flags for interactive
  TUI, and `_guard_interactive_claude_argv` / `_guard_interactive_codex_argv`
  **uniformly reject tokens outside the allowlist** (subcommand after flag /
  bare positional / `--` / unknown flag / headless flag).
- claude-side headless blacklist: `-p` / `--print` / `--headless` /
  `--output-format` / `--input-format`, etc. On the codex side, subcommands
  (`exec` / `review` / `*-server` / `apply` / `sandbox`, etc.) fall in as
  bare positionals.
- Flags that take values carry arity (so headless flags at the value
  position are also caught at a second stage), and `argv[0]` uses basename
  matching (so absolute-path launches are not false-rejected).

### 6.2 Actual argv inspection (runtime attestation)

On the production host (in a session where broker panes are live), inspect
the actual running argv with ps. **Confirm there is not a single
headless flag / subcommand**.

The point is **scoping to broker-spawned panes**. The host can have headless
runs unrelated to this attestation running in parallel (CI / manual
`claude -p` etc.), so indiscriminately grepping all claude/codex picks up
false positives and misses target identification. Broker-spawned processes
carry the broker's MCP config (**including `org-broker`) in argv via
`--mcp-config`**, so use that to narrow the population.

```bash
# 1) Enumerate argv limited to broker-spawned (only those with --mcp-config including org-broker)
ps -eo pid,args | grep -iE "(^| )(claude|codex)( |$)" | grep -v grep \
  | grep -- "--mcp-config" | grep -i "org-broker"

# 2) Billing-neutral negative check: the argv of broker panes narrowed above has no headless / exec
ps -eo args | grep -iE "(^| )(claude|codex)( |$)" | grep -v grep \
  | grep -- "--mcp-config" | grep -i "org-broker" \
  | grep -nE -- "-p( |$)|--print|--headless|--output-format|--input-format| exec | review |--mcp-server" \
  && echo "NG: detected headless/exec flag in broker pane (launch that incurs billing)" \
  || echo "OK: no headless/exec flag in broker panes (interactive TUI = billing-neutral)"

# 3) Population crosscheck (optional, recommended): confirm that the broker bind pane count in list_panes
#    matches the count in (1) (crosscheck pid against dispatcher/secretary's list_panes to detect missing identification / surplus)
```

Expected: the argv of each broker pane is composed only of **interactive
flags** like `--mcp-config <broker>` / `--model` / `--permission-mode`, and
the negative check returns `OK`.

> **Note**: ps inspection must be done in the **host session where broker
> panes are live** (the actual panes are not visible from a sandbox with a
> separated PID namespace). Two-stage assurance: the spawn-time guard
> (Section 6.1) is the primary defense, and ps-based runtime attestation
> is the secondary check. Filtering by `--mcp-config` is a primary narrow
> based on the structural feature of broker panes; when strictness is
> required, close the population gap with the `list_panes` crosscheck in (3).

---

## 7. Verification garbage cleanup (dogfooding of condition (5))

The test state created in this runbook's verification is closed within a
**test directory outside the repo** and does not create production
`.state/broker/`. After verification, run the Section 5(5) procedure
**against the test path** and leave no trace.

```bash
CANON_ROOT=/home/happy_ryo/work/org/claude-org-ja   # canonical root (adjust per env)

# Check the test state-dir used in verification (must be outside the repo)
ls -d /tmp/claude/broker-smoke-* /tmp/claude/usercommon-settings.json 2>/dev/null

# Crosscheck unread in the journal (run the Section 5(5) script with BROKER_STATE=test path) -> tear down if no issue
# (Under /tmp is ephemeral; archive or delete per operational rules)

# Final confirmation that production .state/broker is not created
# (canonical root's absolute path + directly under the current worktree)
test -e "$CANON_ROOT/.state/broker" && echo "NG: production .state/broker exists" || echo "OK: production .state is unchanged"
test -e "$PWD/.state/broker" && echo "NG: .state/broker exists directly under the worktree" || echo "OK: directly under the worktree also unchanged"
```

---

## 8. Observability -- peek into the running org (attach path)

Broker (tmux backend) launches **child panes it spawns (dispatcher and
workers)** as **detached independent tmux sessions** on a dedicated socket.
Unlike renga's "visible split panes in the same tab", these child panes are
not on the human's screen by default, and the *ambient awareness* (the
"how many workers are running, which ones are stuck" you get just by having
the whole picture in view) is quietly lost. Existing overview means alone
do not fill this experience:

| Means | Provides | Lacks |
|---|---|---|
| Dashboard (`localhost` state UI) | State overview based on `state.db` (worker list / transitions / activity) | Not the **live screen** of each pane |
| attention watcher ([`attention-watch.md`](attention-watch.md)) | Push notifications on anomalies / at gates | Not a constant observation that "looks calm at a glance" |
| **tmux attach (this section)** | **Live screens of broker-spawned child panes (dispatcher / workers)** | As described below, currently per-session attach (single-session unification is the future form in Section 8.2) |

This section describes the **read-only attach path** for peeking into the
running broker org. **This path is specific to the tmux backend
(POSIX / WSL2)**. The WezTerm backend (Windows, `isolated_session=False`)
spawns each pane as a GUI window, so the screen is visible from the start
and attach is not needed.

> **Scope (important)**: what you see via attach is **only broker's
> `adapter.spawn`-spawned child panes (dispatcher / workers)**. **The
> Secretary (root secretary) is a logical pane with no adapter-backed real
> pane** (bookkeeping entry; `register_logical_pane`,
> `claude_org_runtime/broker/server.py`), and runs on the human's local
> terminal where the org was started (does not appear on the broker
> socket). So what this path fills is the "live screens of the worker
> group / dispatcher are not visible" gap; the secretary is already in
> front of the human.

### 8.1 Present -- attach to independent sessions (runtime terminal adapter)

The current runtime's terminal adapter (tmux,
`claude_org_runtime.terminal.tmux`) creates the child panes broker spawns
(dispatcher / workers) as **independent detached sessions on the dedicated
socket `claude-org-broker`** (session name `claude-org-broker-<pid>-<seq>`,
`isolated_session = True`). It is socket-separated from existing tmux
servers (renga, etc.), so observation requires the explicit socket name
`-L claude-org-broker`.

```bash
# 1) List existing broker sessions (read-only; socket explicit is mandatory)
tmux -L claude-org-broker list-sessions
#   e.g.:  claude-org-broker-12345-1: 1 windows (created ...)   <- each line is 1 child pane (seq starts at 1)

# 2) Read-only attach to the session you want to peek into (-r is read-only; protects worker from stray keypresses)
tmux -L claude-org-broker attach -r -t claude-org-broker-12345-1
```

Operations after attach (prefix is `Ctrl-b` by default):

| Operation | Key | Use |
|---|---|---|
| detach (stop observing and leave) | `Ctrl-b` -> `d` | Leave while keeping the session alive (no process impact) |
| Switch to another session | `Ctrl-b` -> `s` | Pick from the session list. **Currently per-session, so to see everything you need to switch.** |

> **Why read-only `-r` is the default**: attach to an independent session
> directly connects you to a worker's live TUI. Without `-r`, keypresses
> while observing can leak into the worker session (interventions are
> designed to be closed to the secretary/dispatcher's `send_keys` path, so
> a human's hand attach is limited to observation).

> **Verification log (2026-06-13, runtime 0.1.22)**: socket name
> `claude-org-spike` / session name `spike-<pid>-<seq>` /
> `isolated_session = True` were verified on actual hardware in
> `claude_org_runtime/terminal/tmux.py` (`SPIKE_SOCKET` constant /
> `_new_session_name`). The command shapes `list-sessions` (multiple
> session enumeration) / `attach -r` (read-only flag acceptance) /
> `kill-server` (cleanup) were confirmed reachable on a scratch socket
> (attach to an actual broker org was not done in this verification
> because of interactive blocking).
>
> * Currently renamed to claude-org-broker (breaking change in runtime 0.1.29).

### 8.2 Future -- single-session unification for one-shot `attach` (transport-lab design, not yet landed)

transport-lab `docs/design/broker-native-roles.md` Section 3.4 (defect 4
treatment) has finalized a design that restructures the tmux adapter into
**multiple panes/windows inside a single `claude-org` session**. After
landing, you can see the broker-managed panes (dispatcher / workers) in
one view via the single command below, and standard pane navigation
(`Ctrl-b` arrow) works -- the per-session switching in Section 8.1
becomes unnecessary:

```bash
tmux attach -r -t claude-org   # path after single-session unification (Section 3.4 / R1); -r=read-only; no -L socket needed either
```

- This is a **change to runtime's terminal adapter
  (`claude_org_runtime/terminal/`)**, and ja consumes it via a runtime pin
  bump (it is not a procedure in this runbook on the ja side). **In the
  current runtime (independent sessions), Section 8.1 is the only attach
  path.**
- The design has pane deaths handled by diff reconcile, so Section 3.4
  concludes that the constant observability benefit of single-session
  unification outweighs the trade-off (session-level failure propagating
  to all panes).
- Observer-only commands considered as an observability-gap response
  (read-only tile display of broker-managed panes) / pane live-screen tile
  display in the dashboard are duplicates of `attach -r -t claude-org`
  (read-only) after single-session unification, so this runbook does not
  adopt them (whether they are needed is judged again from actual operation
  after single-session unification).

---

## 9. Related

- Design SoT: transport-lab `docs/design/ja-migration-plan.md` Section 5
  (integration seam) / Section 5.5 (co-existence and rollback) / Section 8
  Issue G (dogfood gate)
- Contract:
  [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md)
  Surface 8 (broker auth & delivery, ratified 2026-06-14)
- Transport dual-system operational differences from the Secretary side:
  [`CLAUDE.md`](../../CLAUDE.md) "Transport dual systems"
- Spawn ceremony (re-introduced folder-trust acceptance + dev-channel sidecar
  acceptance; an addition due to push-first adoption):
  [`.dispatcher/references/spawn-flow.md`](../../.dispatcher/references/spawn-flow.md)
  3-3b
- Transport accessor (single seam on the ja side):
  [`tools/transport.py`](../../tools/transport.py)
- user_common allowlist projection:
  [`tools/org_setup_prune.py`](../../tools/org_setup_prune.py)
  `--user-common-allowlist`
- Operational tone for the attention watcher:
  [`attention-watch.md`](attention-watch.md)
- Single-session unification design for observability (future form in
  Section 8.2): transport-lab `docs/design/broker-native-roles.md` Section 3.4
  (defect 4 -- independent tmux session problem)
