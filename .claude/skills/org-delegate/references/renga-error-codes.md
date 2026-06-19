# renga-peers MCP error codes — Dispatcher / Lead reference

The `renga-peers` MCP server in renga 0.14.0+ includes a stable, machine-readable `code` in error responses. For the Dispatcher / Curator / Lead, branching on **code rather than substring-matching the message text** is recommended.

## Wire format

When an MCP tool (`mcp__renga-peers__*`) fails, `[<code>] <human message>` is embedded at the start of the JSON-RPC error's human-readable message. The `fmt_code` function on the renga side guarantees this format.

```
mcp__renga-peers__send_message(to_id="worker-nonexistent", message="hi")
→ renga refused send: [pane_not_found] pane not found: Name("worker-nonexistent")
```

Extraction method: substring-match the tool result text (for example, `[pane_not_found]`) and branch on that token.

## Known codes

| Code | Meaning | Recommended Dispatcher behavior |
|---|---|---|
| `pane_not_found` | The specified pane name / id / Focused does not exist | Treat the worker as already closed. Transition the status in `.state/workers/worker-*.md` to `pane_closed`, and notify the Lead with `WORKER_PANE_EXITED`. Do not retry. **Note**: `list_panes` / `focus_pane` / `send_message` / `inspect_pane` only see panes in the currently focused tab. A worker in another tab (created via `new_tab`) also returns this code, so `org-delegate` launches all workers in the same tab with `spawn_pane` (suisya-systems/renga#71) |
| `pane_vanished` | Race where the pane disappears after successful resolution | Handle the same as `pane_not_found` |
| `last_pane` | `close_pane` tried to close the only pane in the only tab | This should not occur during normal worker shutdown (the Lead / Dispatcher / Curator share the same tab). If it occurs on the final pane left at the end of `org-suspend` (normally the Lead), that pane should `exit` on its own and terminate naturally. Do not force a retry |
| `split_refused` | `spawn_pane` / `spawn_claude_pane` was refused because of MAX_PANES / too small | If any balanced-split step during worker launch (`org-delegate` Step 3) is refused because of the 16-pane limit, `MIN_PANE_WIDTH`, or `MIN_PANE_HEIGHT`, escalate from Curator to Lead. Typical scenarios are (a) reaching 9+ parallel workers, (b) terminal width not meeting the balanced-split requirement (`W ≥ 160`), or (c) layout tree drift after redispatching a retired worker. `new_tab` fallback is not possible because of the tab-scoped constraint (suisya-systems/renga#71) |
| `cwd_invalid` | The `cwd` for `spawn_pane` / `spawn_claude_pane` / `new_tab` does not exist or is not a directory | Added in renga 0.16.0+. Rejected before pane creation, so the layout is not left half-mutated. On the Dispatcher side, escalate to the Lead and verify that worker-directory preparation (`org-delegate` Step 1.5) completed, and that the relative-path resolution base (`caller` pane `cwd`) was not mistaken |
| `invalid-params` | JSON-RPC-level input validation failure, such as conflicting flags in `spawn_claude_pane` `args[]` or an unknown key name in `send_keys` `keys[]` | In `spawn_claude_pane`, `--dangerously-load-development-channels` / `--permission-mode` / `--model` in `args[]` are rejected. Pass them through structured fields (`permission_mode` / `model`). If this occurs, it is a code bug, so record it in the journal and escalate to the Lead |
| `name_in_use` | `set_pane_identity` tried to assign a name already in use by another existing pane | In `/org-start` Step 0, when repairing secretary identification, catch this code and tell the user that a persistent fix requires `/org-suspend` followed by restart. The short-term workaround is numeric pane id operation |
| `name_invalid` | `set_pane_identity` was given a name that is all digits or contains forbidden characters | Allowed characters are `[A-Za-z0-9_-]`. All-digit names are rejected because they are ambiguous with numeric pane ids. This is a bug, so record it in the journal |
| `io_error` | PTY write / spawn / OS-level failure | Spin for one cycle and retry. If it occurs twice in a row for the same worker, escalate to the Lead with `IO_ERROR_DETECTED` |
| `shutting_down` | The renga core is shutting down | **Stop the monitor loop immediately**. Notify the Lead (`secretary`) over renga-peers with `FOREMAN_STOPPING` (best effort; delivery may fail if renga itself is going down) |
| `app_timeout` | The internal App thread in renga did not respond | Spin for one cycle (renga restart is an operator decision). If it repeats, log it to the Lead |
| `parse` / `protocol` | Should not normally occur (assuming MCP assembles requests correctly) | If it occurs, it is a bug. Record it in the journal and report `IPC_PROTOCOL_ERROR` to the Lead |
| `internal` | renga internal invariant violation (for example parser lock poison) | Handle the same as `app_timeout` |

## Broker (`ORG_TRANSPORT=broker`) additional codes and tool-name projection

This file documents the **default `renga`** (`ORG_TRANSPORT` unset) error codes as canonical. Under `ORG_TRANSPORT=broker` (opt-in, revertible) the MCP server name becomes `org-broker`, and tools' **fully qualified names get machine-substituted from `mcp__renga-peers__*` → `mcp__org-broker__*`** (the extraction of wire format `[<code>] <message>` and branching policy are identical). Broker **reuses `pane_not_found` / `last_pane` / `invalid-params` from the shared codes above with matching meanings**, and **adds** the following broker-specific codes (the renga harness is unaffected; the broker harness also handles unknown codes in the default branch). The canonical contract is [`docs/contracts/backend-interface-contract.md`](../../../../docs/contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, proposed/awaiting ratification) §8.7.

| Code | Meaning | Operations it appears in | Recommended behavior |
|---|---|---|---|
| `token_invalid` | bind token is unknown / malformed / revoked | All operations requiring authentication | Bug or session loss. Journal-record + escalate to Lead |
| `session_invalid` | This agent's broker session has vanished (daemon restart / bind drop) | All operations requiring authentication | Requires redoing spawn (rebind). Escalate to Lead |
| `tool_not_authorized` | The caller's `auth_role` tier does not include this tool (§8.3 tier gating) | Operations with tier restrictions | Misconfiguration. Review the tier design and escalate to Lead (no concept exists in renga) |
| `peer_not_found` | The destination id / name for `send_message` / messaging cannot be resolved | Messaging operations | Equivalent to renga's `pane_not_found` (in messaging context). Treat as a closed peer |
| `name_taken` | Name collision on spawn / `set_pane_identity` | Spawn family / `set_pane_identity` | Broker spelling of renga's `name_in_use`. Same handling (numeric-id operation or persistent repair) |
| `no_backend` | The terminal adapter (tmux/WezTerm) is unavailable = "adapter_unavailable" | Pane control operations | Check the adapter environment and escalate to Lead. Adjacent to renga's `io_error` |
| `nudge_failed` | The pull nudge could not be delivered to the destination pane | `send_message` | The body is queued but the receiver cannot notice. Retry or escalate to Lead |
| `unknown_tool` | A tool absent from the broker surface was called (`new_tab` / `focus_pane` etc.) | All operations | Broker intentionally omits `new_tab` / `focus_pane`. Bug on the caller side |

> **Correspondence with the design §5.2(ii) naming**: `token_*` = `token_invalid` + `session_invalid`, `adapter_unavailable` = `no_backend`, and the tier-gating addition is `tool_not_authorized`. `name_taken` is the broker spelling of the shared `name_in_use`.

> **Broker's ok-return / delivery difference**: the renga exceptions described below (the renga-unreachable ok-text shim for `list_peers` / `send_message`) **do not exist in broker** (§6.3 carve-out does not apply). Under broker, transport loss is also returned as an error code per §8.7. Also, since broker delivers to all peers via pull (no push peers exist), receive is "pane-local nudge → pull the body via `mcp__org-broker__check_messages`" (`receive_mode` is the constant `"poll"`, §8.4/§8.8).

## MCP-tool-specific ok-return rules

The following two MCP tools are exceptions: even when renga is unreachable, they return **ok-text instead of a JSON-RPC error**.

- `mcp__renga-peers__list_peers`: when the renga core is not running / detached mode -> `"(no peers — renga not reachable: <reason>)"`
- `mcp__renga-peers__send_message`: same case -> `"(message dropped — renga not reachable: <reason>)"`

Other renga-peers tools (`spawn_pane` / `close_pane` / `list_panes` / `focus_pane` / `new_tab` /
`check_messages` / `set_summary` / `poll_events` / `inspect_pane` / `send_keys`) use `require_connected` and return a JSON-RPC error when disconnected. For these two tools only, the handling branch should look not only for `[code]` patterns but also for the `(no peers` / `(message dropped` prefixes.

## Shell-side handling example

Case handling against MCP tool call result text (`content[0].text` or the JSON-RPC error message):

```
# MCP ツール呼び出し後、返ってきたテキストを $out に入れた状態を想定
case "$out" in
  *"[pane_not_found]"*|*"[pane_vanished]"*)
    # worker 既に閉じた — lifecycle 処理に回す
    mark_worker_pane_closed worker-foo
    ;;
  *"[last_pane]"*)
    # org-suspend 末端で最後のペインを閉じようとした
    # 強制クローズしない。当該ペインは自分自身で exit
    echo "last pane — leave for self-exit"
    ;;
  *"[shutting_down]"*)
    echo "renga halting — dispatcher stopping"
    exit 0
    ;;
  *"[io_error]"*|*"[app_timeout]"*|*"[internal]"*)
    log_journal "transient renga error: $out"
    ;;
  *"(no peers"*|*"(message dropped"*)
    # list_peers / send_message の renga 非接続時の ok-text
    log_journal "renga peer unreachable: $out"
    ;;
  *)
    log_journal "unexpected renga error: $out"
    ;;
esac
```

## Why `code`, not message substrings

- The message body is human-facing. It may change without notice
  (for example, `"pane not found: Id(3)"` -> `"pane 3 does not exist"`)
- For the renga-side contract, treat the following as the source of truth (this repository cannot verify them, so treat them as an **external dependency**):
  - doc comment on `renga/src/ipc/mod.rs::err_code` — explicit list of public codes and ABI-stability guarantees (renames come with a deprecation window)
  - `renga/src/mcp_peer/mod.rs::fmt_code` — formatting logic for `[<code>] <message>` over MCP
  - wire schema for `renga Response::Err { message, code }` — `code` is `Option<String>`, with `skip_serializing_if = "Option::is_none"`
- Always treat unknown codes as non-fatal. The default branch is required so the Dispatcher does not crash when renga adds new codes in the future

## Event stream — `poll_events` MCP

Long-poll pane lifecycle events (`pane_started` / `pane_exited` / `events_dropped` / `heartbeat` / forward-compatible variants) through `mcp__renga-peers__poll_events`:

```
mcp__renga-peers__poll_events(
  since=<前回の next_since、初回は省略>,
  timeout_ms=5000,
  types=["pane_exited", "events_dropped"]
)
```

The returned `events[]` include `type` / `role` / `name` / `id` / `ts`. The Dispatcher filters on `role == "worker"` and emits `WORKER_PANE_EXITED`. Reuse `next_since` as the next `since` for idempotent resume.

### Handling by `type`

| type | Handling |
|---|---|
| `pane_started` | Skip for now (add later if needed) |
| `pane_exited` | Filter to `role == "worker"` and emit `WORKER_PANE_EXITED` |
| `events_dropped` | Record the dropped-count in the DB `events` table (signal that monitoring is falling behind) |
| `heartbeat` | Normally not placed in the `poll_events` buffer (consumed inside subscribe) |

### `types` filter behavior

The `types` filter advances the cursor across all event types, so there is no duplicate scan. However, a **filter-mismatched event causes the long-poll to return early**, and it returns `events: []` plus an advanced cursor (see renga PR #120). In the Dispatcher monitor loop, do not spin on an empty response; keep `next_since` and call again in the next cycle.

### Initial-call semantics

Omitting `since` returns only events from "now onward" (it does not flood past history). This matches the old `renga events --timeout` contract.

## Raw key input — `send_keys` MCP

Use `mcp__renga-peers__send_keys` for raw PTY key input. This is **different from** logical message delivery via `send_message` (it writes raw bytes to the PTY, so it is visible to the application running in that pane):

```
mcp__renga-peers__send_keys(
  target: string,           # pane name or id (list_panes と同じ解決規則)
  text?: string,            # 送信するテキスト（optional）
  keys?: string[],          # 特殊キー名の配列（optional、text と併用可、text の後に送られる）
  enter?: boolean           # 末尾に Enter (CR, 0x0D) を付ける（optional、keys の後に送られる）
)
```

### Supported key vocabulary

- `Enter` / `Return` (CR, `\r` = 0x0D; byte-identical to `enter: true`)
- `Tab`
- `Shift+Tab` / `BackTab`
- `Esc` / `Escape`
- `Backspace`
- `Delete` / `Del`
- `Up` / `Down` / `Left` / `Right`
- `Home` / `End`
- `PageUp` / `PageDown`
- `Space`
- `Ctrl+<A-Z>` (for example `Ctrl+C`)

An unknown key name returns a `-32602 invalid-params` error.

### Typical call patterns

| Use case | Call |
|---|---|
| Empty Enter (responding to a prompt) | `send_keys(target="X", enter=true)` |
| `"yes"` + Enter (for confirmation prompts, etc.) | `send_keys(target="X", text="yes", enter=true)` |
| Shift+Tab (toggle permission mode) | `send_keys(target="X", keys=["Shift+Tab"])` |
| Esc (dismiss modal) | `send_keys(target="X", keys=["Esc"])` |
| Ctrl+C (interrupt running process) | `send_keys(target="X", keys=["Ctrl+C"])` |
---
