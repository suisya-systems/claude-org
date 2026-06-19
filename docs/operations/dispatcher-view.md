# dispatcher-view operations guide

`tools/org-dispatcher-view.sh` is a "self-healing read-only viewer" you place in a pane next to the secretary so that the dispatcher pane running on the broker(tmux) backend stays **continuously visible**. Even when the dispatcher restarts or the broker tmux session name changes due to an auto-compact fork, the viewer re-discovers and re-attaches automatically, so you do not have to attach by hand again.

The header comment in the script itself ([`tools/org-dispatcher-view.sh`](../../tools/org-dispatcher-view.sh)) is the primary specification. This document covers the operational procedure for placing it next to the secretary as a continuous display.

## 1. What you can see

- On the broker(tmux) backend, each pane lives as a separate detached tmux session on broker's dedicated socket (default `claude-org-broker`). The dispatcher pane exists as one of these detached sessions on the same socket.
- This viewer resolves the role purely via tmux by looking for "the session whose pane cwd basename is `.dispatcher`", and attaches to the discovered session with `-r` (read-only).
- When you detach (or when the session name changes because the dispatcher restarts / auto-compact forks), the viewer returns to the re-discovery loop and re-attaches once it finds the session.
- It does not call the broker daemon's HTTP / MCP API at all (pure tmux role resolution). It puts no extra load on the control plane.

## 2. Scope of applicability

| Scope | Applicable | Notes |
|---|---|---|
| broker **tmux backend** (Linux / macOS / WSL) | Applicable | The intended environment for this script |
| broker **Windows backend (wezterm)** | Not applicable | The broker Windows backend is wezterm rather than tmux, so this script does not work there. An equivalent is a follow-up |
| **renga** frame | Not needed | renga uses single-screen tiling and each pane is not split into a separate tmux session, so the "re-attach to a detached session" concept does not map. Not needed |

The viewer itself works regardless of whether the "viewing terminal" is WezTerm or tmux. The out-of-scope case is only **when the broker backend itself is wezterm**.

## 3. WezTerm procedure (recommended)

Split a pane on the WezTerm side, then launch this viewer in the new pane. WezTerm's split keys and the inner dispatcher's `Ctrl-b` prefix are in separate systems, so **there is no key collision** (the biggest advantage compared to the tmux procedure below).

1. With focus on the WezTerm pane of the secretary session, split the pane:
   - Split horizontally (left/right): `Ctrl+Shift+Alt+%`
   - Split vertically (up/down): `Ctrl+Shift+Alt+"`
2. In the newly opened pane, launch the viewer:
   ```bash
   cd /path/to/claude-org
   tools/org-dispatcher-view.sh
   ```
   You should see `socket=claude-org-broker, mode=read-only` in the startup message.
3. If the dispatcher is found, the viewer attaches automatically. If not, it prints "dispatcher tmux pane not found" and enters the re-discovery loop (it will auto-attach once the dispatcher comes up).

### Operation keys (WezTerm)

| Operation | Key |
|---|---|
| Move between panes | `Ctrl+Shift+Left/Right/Up/Down` |
| Detach the inner dispatcher (leave by yourself) | `Ctrl-b d` |
| Exit the viewer itself | Detach with `Ctrl-b d` -> at the re-discovery prompt, press `Ctrl-C` -> `exit` |

This assumes the default WezTerm keybindings. If you customize via `.wezterm.lua` etc., read these as the corresponding keys. Adjust the `cd` path to wherever you cloned the repository.

## 4. tmux procedure (collision caveat)

You end up doing a nested attach from an outer tmux pane, so there are **two caveats**.

1. Prefix the launch command with `TMUX=` (unset the environment variable). Reason: because you are doing a nested attach from inside an outer tmux into a different tmux server (the broker socket), tmux refuses the attach with `sessions should be nested with care` unless `TMUX=` is set.
2. To send a prefix to the inner dispatcher, press `Ctrl-b` **twice** (the outer tmux intercepts the first press).

### Procedure

1. With focus on the tmux pane of the secretary session, split the pane:
   - Split horizontally: `Ctrl-b %`
   - Split vertically: `Ctrl-b "`
2. In the newly opened pane, launch the viewer:
   ```bash
   cd /path/to/claude-org
   TMUX= tools/org-dispatcher-view.sh
   ```
3. If the dispatcher is found, the viewer attaches automatically.

### Operation keys (tmux nested)

| Operation | Key |
|---|---|
| Move between outer panes | `Ctrl-b Left/Right` / `Ctrl-b o` |
| Detach the inner dispatcher (leave by yourself) | `Ctrl-b Ctrl-b d` |
| Exit the viewer itself | Detach with `Ctrl-b Ctrl-b d` -> at the re-discovery prompt, press `Ctrl-C` -> `exit` |

The biggest difference from the WezTerm path is that you send the inner prefix as `Ctrl-b` twice. If you have rebound the outer tmux prefix to another key (for example `Ctrl-a`), substitute that combined with `Ctrl-b`.

## 5. Options

### 5.1 `--rw` (read-write attach)

The default is read-only (`-r`) for safety, but use `--rw` only when you really want to **type directly** into the dispatcher pane:

```bash
tools/org-dispatcher-view.sh --rw
```

Accidental input into the dispatcher pane can break the control plane (it may break the worker monitoring loop or the handover flow). For the continuous-visibility use case, do not pass `--rw`; only launch with it on-spot when writes are truly necessary.

### 5.2 Environment variable `ORG_BROKER_SOCKET`

The broker tmux socket name (default `claude-org-broker`). Set this only if the runtime side uses a different socket name:

```bash
ORG_BROKER_SOCKET=my-broker tools/org-dispatcher-view.sh
```

No setting is needed in normal operation.

## 6. Self-healing behavior

- **Re-discovery when the dispatcher is absent**: When the socket connects but no pane with `.dispatcher` cwd is present, the viewer prints "dispatcher tmux pane not found (degraded / not started). Re-discovering..." and re-discovers every 2 seconds.
- **Retry when the socket is unreachable**: When the tmux socket cannot be reached, for example because the broker daemon is not running, the viewer prints "cannot reach broker tmux socket (...)" and retries every 2 seconds.
- **Auto-recovery after attach**: When the dispatcher restarts / auto-compact forks and the session name changes, the tmux-side attach drops. The viewer detects that, returns to the top of the loop, re-resolves the new session name, and re-attaches.
- **Multiple-candidate warning**: In rare cases where multiple orgs / multiple `.dispatcher` panes exist on the same broker socket, the viewer warns "found N dispatcher candidates" and uses the first one. Because it may attach to an unintended dispatcher, check the broker daemon state.
- **Caveat on exit**: `Ctrl-C` while attached is passed to the tmux client / dispatcher pane and does not reach the viewer's SIGINT trap (with `--rw` it would even send a `^C` to the dispatcher). Always exit in the order **detach (`Ctrl-b d` or `Ctrl-b Ctrl-b d`) -> re-discovery prompt -> `Ctrl-C`**.

## 7. Troubleshooting

### 7.1 Nothing shows on launch / it immediately says "not found"

Check whether sessions are on the broker socket directly:

```bash
/usr/bin/tmux -L claude-org-broker list-panes -a
```

- Nothing appears -> broker daemon is not running / dispatcher has not come up yet. This can happen just after `/org-start` before the broker is ready, or after `/org-suspend`.
- Sessions are listed but no pane has `.dispatcher` cwd -> the dispatcher is degraded (bg-pty fallback) or not started. Verify dispatcher recovery through another path.

### 7.2 `sessions should be nested with care` appears

You launched from inside an outer tmux but forgot to prefix with `TMUX=`. Re-issue the launch command as shown in the tmux procedure (Section 4) with `TMUX=` at the front.

### 7.3 "found N dispatcher candidates" warning

Multiple panes with `.dispatcher` cwd are present on the same broker socket. The viewer uses the first one, but confirm that this is what you intended:

```bash
/usr/bin/tmux -L claude-org-broker list-panes -a \
  -F '#{session_name}\t#{pane_current_path}' | grep '\.dispatcher$'
```

You can resolve this by separating `ORG_BROKER_SOCKET` values or by cleaning up unnecessary dispatcher sessions.

### 7.4 `tmux` command alias mismatches

This script invokes `/usr/bin/tmux` by absolute path internally, so aliases from the zsh + oh-my-zsh tmux plugin are ignored (it is not affected). Be careful about alias mismatches only when you run `tmux -L ... list-panes` manually (use the absolute path or strip the alias with `command tmux ...`).

## 8. Related

- The script itself: [`tools/org-dispatcher-view.sh`](../../tools/org-dispatcher-view.sh)
- General broker operations: [`docs/operations/broker-dogfood-runbook.md`](broker-dogfood-runbook.md)
- attention notifications (active notification of events requiring a human response): [`docs/operations/attention-watch.md`](attention-watch.md)
