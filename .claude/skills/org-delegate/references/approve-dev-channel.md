# `approve_dev_channel_prompt(target, timeout_s=30)` — race-free dev-channel approval

Shared sub-procedure used by every site that calls `mcp__renga-peers__spawn_claude_pane`. Replaces the old "blind `send_keys(enter=true)` right after spawn" pattern, which races the dev-channel confirmation prompt and silently leaves panes hung.

## Why this helper exists

`spawn_claude_pane` returns once the **PTY process** has started (zsh runs the `claude ...` command line). Claude Code itself takes a few seconds afterward to take over the terminal and render the dev-channel prompt:

```
WARNING: Loading development channels
...
Channels: server:renga-peers
❯ 1. I am using this for local development
  2. Exit
Enter to confirm · Esc to cancel
```

If the caller fires `send_keys(enter=true)` while zsh is still in control, the Enter is consumed by the shell as a no-op `%` newline, not by Claude Code. When Claude Code finally renders the prompt, no one is left to dismiss it; `--dangerously-load-development-channels server:renga-peers` is never approved, the `server:renga-peers` channel never comes up, and subsequent `send_message` calls are silently dropped. Observed twice in a single org session (suisya-systems/claude-org#23).

The helper waits until the prompt is **actually rendered on screen** before sending Enter, and is a no-op once the prompt has been cleared. It is the single source of truth for all three `spawn_claude_pane` callers (Dispatcher / Curator / Worker).

## Inputs

- `target` — pane name to approve. Same value passed to `spawn_claude_pane(name=...)`.
- `timeout_s` — overall deadline. Default 30 seconds. Increase only when working in known-slow environments (e.g. cold-start of a fresh worktree on a constrained machine).

## Procedure

```
deadline = now + timeout_s seconds

while now < deadline:
    screen = mcp__renga-peers__inspect_pane(target=target, lines=20)
    text   = screen content (the rendered text — the MCP result's text payload)

    # 1) Already past the prompt → no-op. Check this BEFORE the prompt-visible
    #    branch so we never send a spurious Enter into a live Claude prompt
    #    if both states briefly co-occur during transition.
    if "auto mode on (shift+tab to cycle)" in text:
        return ok
    if a line whose only non-whitespace content is "❯" appears in text:
        return ok

    # 2) Prompt visible → approve with Enter.
    if "Loading development channels" in text and "Enter to confirm" in text:
        mcp__renga-peers__send_keys(target=target, enter=true)
        return ok

    # 3) Neither — Claude Code has not finished launching yet. Wait and retry.
    sleep 1 second

# 4) Deadline exceeded.
return timeout
```

The MCP call signature is `mcp__renga-peers__inspect_pane(target=<name>, lines=20)` — `lines=20` trims the response to the bottom 20 rows so the markers below match what's actually on screen. Default text format is fine; `format="grid"` is not needed.

## Marker strings (explicit)

These are the exact substrings the helper looks for. They are anchored on observed behavior of Claude Code 1.x and renga 0.18.0+.

### Prompt visible — send Enter

The bottom 20 rows contain **both**:

- `Loading development channels`
- `Enter to confirm`

Both must be present. The `Loading development channels` line alone can show up briefly during banner rendering before the prompt is actually interactive; gating on `Enter to confirm` waits until the prompt is ready to consume the keystroke.

### Prompt cleared — no-op

The bottom of the screen contains **either**:

- `auto mode on (shift+tab to cycle)` — the auto-mode status line that Claude Code shows once the input loop has taken over.
- A line whose only non-whitespace content is `❯` — the bare input cursor on its own line, indicating the input box is ready for typing.

Either marker is sufficient. Both indicate Claude Code has finished initialization and is past the dev-channel prompt; sending Enter into a live Claude input would inject a stray newline into a real prompt.

If neither set of markers is visible, Claude Code is still launching — keep polling until the deadline.

## Idempotency

The helper is safe to call multiple times against the same pane. Once the prompt-cleared markers are visible, every subsequent call returns immediately without sending any keys.

This matters in practice: a Worker pane that was approved in a previous session and reattached during `/org-resume` will already show the cleared markers. Calling the helper unconditionally is the right thing to do — there is no need for the caller to pre-detect "is this a fresh launch or a reattach".

## Timeout escalation

When the deadline is exceeded the helper returns `timeout`. The caller escalates to the Lead via renga-peers, uniformly across all three call sites:

```
mcp__renga-peers__send_message(
  to_id="secretary",
  message="DEV_CHANNEL_TIMEOUT: {target} did not render the dev-channel prompt within {timeout_s}s after spawn. Pane may be hung; channel push will be lost. Human judgment required."
)
```

- **Dispatcher caller (Worker spawn, `org-delegate` Step 3-3b)**: after sending the message, skip the rest of Step 3 for this Worker (do not run 3-4 / 3-5 — the `list_peers` wait would just retime out for the same reason). Continue the Dispatcher main monitoring loop; do not exit.

- **Lead caller (Dispatcher / Curator spawn, `org-start` Steps 2 and 3)**: when the Lead itself is the caller, `to_id="secretary"` is a send-to-self — that is intentional and matches the issue spec (suisya-systems/claude-org#23). It surfaces in the Lead's own inbox via the standard `<channel source="renga-peers">` notification, which the Lead surfaces to the user. After sending, pause `/org-start` and wait for human direction; do not retry the spawn or proceed to the next role.

In all cases, do **not** silently swallow the timeout, and do **not** retry indefinitely without telling a human. A hung dev-channel prompt is an environmental fault (terminal too small, Claude Code launch crashed, etc.) that needs human eyes.
