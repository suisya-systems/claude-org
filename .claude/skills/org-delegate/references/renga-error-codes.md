# renga-peers MCP error codes — Dispatcher / Secretary reference

The renga 0.14.0+ `renga-peers` MCP server returns a stable, machine-readable code in error responses. The Dispatcher / Curator / Lead are recommended to **branch on the code**, not by substring-matching the message string.

## Wire format

When an MCP tool (`mcp__renga-peers__*`) fails, the JSON-RPC error's human-readable message is prefixed with `[<code>] <human message>`. renga's `fmt_code` function guarantees this format.

```
mcp__renga-peers__send_message(to_id="worker-nonexistent", message="hi")
→ renga refused send: [pane_not_found] pane not found: Name("worker-nonexistent")
```

Extraction: substring-match on the tool result text (branch on `[pane_not_found]`, etc.).

## Known codes

| Code | Meaning | Recommended Dispatcher behavior |
|---|---|---|
| `pane_not_found` | The specified pane name / id / Focused does not exist | Treat that Worker as already closed. Transition `.state/workers/worker-*.md` status to `pane_closed` and notify the Lead with `WORKER_PANE_EXITED`. Do not retry. **Note**: `list_panes` / `focus_pane` / `send_message` / `inspect_pane` can only see panes in the currently focused tab. Workers in other tabs (originating from `new_tab`) return this code, so org-delegate launches all Workers via `spawn_pane` in the same tab (suisya-systems/renga#71) |
| `pane_vanished` | Race in which the pane disappeared after a successful resolve | Treat the same as `pane_not_found` |
| `last_pane` | `close_pane` tried to close the only pane in the only tab | Does not occur during normal Worker stop (Lead/Dispatcher/Curator coexist in the same tab). If it occurs at the end of `org-suspend` against the very last pane (normally the Lead), let that pane `exit` itself and terminate naturally. Do not force-retry |
| `split_refused` | `spawn_pane` / `spawn_claude_pane` rejected by MAX_PANES / too small | When any step of balanced split during Worker launch (`org-delegate` Step 3) is refused by the 16-pane limit / `MIN_PANE_WIDTH` / `MIN_PANE_HEIGHT`, escalate Curator → Lead. Typical scenarios: (a) reached 9-parallel or more, (b) terminal width does not satisfy balanced split requirements (W ≥ 160), (c) re-dispatch after Worker retirement made the layout tree diverge from expected. `new_tab` fallback is impossible due to tab-scoped constraints (suisya-systems/renga#71) |
| `cwd_invalid` | `cwd` of `spawn_pane` / `spawn_claude_pane` / `new_tab` does not exist or is not a directory | Added in renga 0.16.0+. Rejected before pane creation, so no half-mutated layout. The Dispatcher should escalate to the Lead and verify whether Worker directory preparation (org-delegate Step 1.5) is complete or whether the relative-path resolution base (caller pane's cwd) was misunderstood |
| `invalid-params` | JSON-RPC level input validation failure (e.g. including a conflicting flag in `spawn_claude_pane`'s `args[]`, or an unknown key name in `send_keys`'s `keys[]`) | In `spawn_claude_pane`, putting `--dangerously-load-development-channels` / `--permission-mode` / `--model` into `args[]` is rejected. Pass them via the structured fields (`permission_mode` / `model`). When this occurs it's a code bug, so log to journal and escalate to the Lead |
| `name_in_use` | `set_pane_identity` tried to assign a name already in use by another existing pane | In `/org-start` Step 0 secretary identity recovery, catch this code and present the user with "for permanent fix, `/org-suspend` → restart". Short-term workaround is operating with numeric pane ids |
| `name_invalid` | `set_pane_identity` was given an all-digit / forbidden-character name | Allowed characters are `[A-Za-z0-9_-]`. All-digit names are rejected because they are ambiguous with numeric pane ids. Bug — log to journal |
| `io_error` | PTY write / spawn / OS-level failure | Spin once and retry. If the same Worker hits it twice in a row, escalate to the Lead with `IO_ERROR_DETECTED` |
| `shutting_down` | renga itself is shutting down | **Stop the monitoring loop immediately**. Notify the Lead (`secretary`) with `DISPATCHER_STOPPING` via renga-peers (best-effort — won't arrive if renga itself is going down) |
| `app_timeout` | renga's internal App thread did not respond | Spin one cycle (renga restart is up to the admin). On consecutive occurrences, log to the Lead |
| `parse` / `protocol` | Should not normally occur (MCP is expected to assemble messages correctly) | Bug if it occurs. Log to journal and report to the Lead with `IPC_PROTOCOL_ERROR` |
| `internal` | renga internal invariant violation (parser lock poison, etc.) | Treat the same as `app_timeout` |

## MCP-tool-specific ok-return rules

The following 2 MCP tools are exceptions: even when renga is unreachable, they **return ok-text instead of a JSON-RPC error**.

- `mcp__renga-peers__list_peers`: renga itself not running / detached mode → `"(no peers — renga not reachable: <reason>)"`
- `mcp__renga-peers__send_message`: same as above → `"(message dropped — renga not reachable: <reason>)"`

The other renga-peers tools (`spawn_pane` / `close_pane` / `list_panes` / `focus_pane` / `new_tab` /
`check_messages` / `set_summary` / `poll_events` / `inspect_pane` / `send_keys`) become a JSON-RPC error when not connected, via `require_connected`. Only for these two should handler branches also look for the **`(no peers` / `(message dropped` prefixes** in addition to `[code]` patterns.

## Shell-side handling example

Case branching on the MCP tool result text (`content[0].text` or JSON-RPC error message):

```
# Assume the returned text is in $out after an MCP tool call
case "$out" in
  *"[pane_not_found]"*|*"[pane_vanished]"*)
    # Worker already closed — route to lifecycle handling
    mark_worker_pane_closed worker-foo
    ;;
  *"[last_pane]"*)
    # org-suspend tried to close the very last pane
    # Do not force close; that pane should self-exit
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
    # ok-text returned by list_peers / send_message when renga is not connected
    log_journal "renga peer unreachable: $out"
    ;;
  *)
    log_journal "unexpected renga error: $out"
    ;;
esac
```

## Why codes, not substrings

- The message body is human-facing. It may change without notice for any reason
  (e.g. "pane not found: Id(3)" → "pane 3 does not exist")
- For the renga-side contract, refer to the following as the source of truth (treat them as **external dependencies**, since they cannot be verified inside this repository):
  - The doc comment on `renga/src/ipc/mod.rs::err_code` — declares the public code list and ABI stability (renames go through a deprecation window)
  - `renga/src/mcp_peer/mod.rs::fmt_code` — the formatting logic for `[<code>] <message>` over MCP
  - The wire schema of renga's `Response::Err { message, code }` — `code` is `Option<String>` with `skip_serializing_if = "Option::is_none"`
- Always treat unknown codes as non-fatal — even if renga adds new codes in the future, the Dispatcher must not fall over. A default branch is required

## Event stream — `poll_events` MCP

Pane lifecycle (`pane_started` / `pane_exited` / `events_dropped` / `heartbeat` / forward-compat variants) is cursor-based long-polled via `mcp__renga-peers__poll_events`:

```
mcp__renga-peers__poll_events(
  since=<previous next_since; omit on first call>,
  timeout_ms=5000,
  types=["pane_exited", "events_dropped"]
)
```

The returned `events[]` includes `type` / `role` / `name` / `id` / `ts`. The Dispatcher filters by `role == "worker"` and notifies `WORKER_PANE_EXITED`. Reuse `next_since` as the next call's `since` for idempotent resume.

### Per-type handling

| type | Handling |
|---|---|
| `pane_started` | Currently skipped (added later if needed) |
| `pane_exited` | Filter by `role == "worker"` and notify `WORKER_PANE_EXITED` |
| `events_dropped` | Record the drop count in `.state/journal.jsonl` (signal that monitoring is falling behind) |
| `heartbeat` | Normally not put into the `poll_events` buffer (consumed inside subscribe) |

### `types` filter behavior

The `types` filter advances the cursor on all types, so there are no duplicate scans. However, **arrival of a filter-mismatching event causes long-poll to early-return**, returning `events: []` + an advanced cursor (see renga PR #120). The Dispatcher monitoring loop must not spin on empty responses; instead, retain `next_since` and re-call on the next cycle.

### First-call semantics

Omitting `since` returns "events from now on" (does not flood with past history). Same contract as the legacy `renga events --timeout`.

## Raw key input — `send_keys` MCP

Use `mcp__renga-peers__send_keys` for raw PTY key sending. This is **separate** from `send_message`'s logical message delivery (it writes raw bytes to the PTY, so the application running in that pane sees them):

```
mcp__renga-peers__send_keys(
  target: string,           # pane name or id (same resolution rule as list_panes)
  text?: string,            # text to send (optional)
  keys?: string[],          # array of special key names (optional; can be combined with text; sent after text)
  enter?: boolean           # append Enter (CR, 0x0D) at the end (optional; sent after keys)
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
- `Ctrl+<A-Z>` (e.g. `Ctrl+C`)

Unknown key names return a `-32602 invalid-params` error.

### Typical call patterns

| Use | Call |
|---|---|
| Bare Enter (replying to a prompt) | `send_keys(target="X", enter=true)` |
| "yes" + Enter (replying to a confirmation prompt) | `send_keys(target="X", text="yes", enter=true)` |
| Shift+Tab (toggle permission mode) | `send_keys(target="X", keys=["Shift+Tab"])` |
| Esc (modal escape) | `send_keys(target="X", keys=["Esc"])` |
| Ctrl+C (interrupt running process) | `send_keys(target="X", keys=["Ctrl+C"])` |
