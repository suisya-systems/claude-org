---
name: org-attach
description: >
  Read-only skill that **only prints** tmux attach commands for **directly entering** the org's
  live panes (secretary / dispatcher / worker). Joins `mcp__org-broker__list_panes` (logical
  panes) with `/usr/bin/tmux -L claude-org-spike list-panes -a` (pane_id <-> session mapping)
  by pane_id (%N) and emits an attach command per pane labeled with role + name(task_id)
  (read-only `-r` / writable without `-r` / detach with `Ctrl-b d`).
  Triggered by "I want to see a worker's pane", "let me attach to a worker pane", "I want to
  watch the dispatcher directly", "let me get into a pane", "I want to peek at that pane",
  "give me the attach command", "connect via tmux", "enter the worker's screen", etc.
  Does not attach by itself and does not change any pane (prints command strings and a pane
  list only). Does not fire for delegating work (org-delegate), the dashboard overview
  (org-dashboard), or stopping the watcher (org-attention-stop).
effort: low
allowed-tools:
  - Read
  - Bash(printenv ORG_TRANSPORT)
  - Bash(/usr/bin/tmux -L claude-org-spike list-panes*)
  - Bash(/usr/bin/tmux -L claude-org-spike list-sessions*)
  - mcp__org-broker__list_panes
  - mcp__org-broker__list_peers
---

# org-attach: generate tmux attach commands for org panes (read-only)

A skill that **generates and prints attach command strings** so a human can attach to the
org's live panes (secretary / dispatcher / worker) **from their own terminal** via tmux.
This skill **does not attach to anything and does not change any pane**. It joins the
logical pane list (broker) with the tmux-side pane_id<->session mapping by pane_id (`%N`)
and prints an attach command per pane, labeled with role + name(task_id). The human copies
the command and pastes it into their own terminal to enter.

> **Transport two-frame model (frame C / two frames) - this skill is broker(tmux) frame only**:
> This skill assumes **attach to detached tmux sessions** on the tmux backend (socket
> `claude-org-spike`). **broker frame**: each broker pane exists as an independent detached
> tmux session named `spike-{pid}-{seq}` (one pane = one session), enterable via
> `tmux attach -t <session>` - this is the primary frame where the attach model of this skill
> makes sense. **renga frame (opt-in, `ORG_TRANSPORT=renga`) is conceptually different**:
> renga uses a **single-screen tiling** model, where panes are **tiles** inside one live
> window and not independent detached sessions. The notion of "re-attaching to a detached
> session" does not map directly, and there is no per-pane `tmux attach -t <session>`. So
> under renga the attach form of this skill is **not applicable**, and you can just look at
> the screen directly (no attach needed). In the renga frame, this skill explicitly says
> "this is a broker(tmux)-only tool" and stops (see Step 0 below).
>
> (**Two-frame note about "default" (Refs #604)**: org-attach is inherently a broker/tmux
> tool, so the header is written from the **broker-primary** axis. The overall transport
> "default" has two frames that refer to different things - the **operational default** is
> renga (because real broker dogfood is not active until Epic #6 Issue G), while the
> **code default** is that `tools/transport.py: DEFAULT_TRANSPORT` was flipped from `renga`
> to `broker` in runtime 0.1.28 (Epic #586). Among the hand-maintained skills that use
> broker tools, [`.claude/skills/org-attention-stop/SKILL.md`](../org-attention-stop/SKILL.md)
> writes its header in the code-default frame as "default `broker` / opt-in `renga`" - this
> skill follows that broker-primary precedent. (Conversely
> [`.claude/skills/org-attention-start/SKILL.md`](../org-attention-start/SKILL.md) is
> written in the operational-default frame as "default `renga`"; the two are not in conflict,
> they just refer to different things.) See the root
> [`CLAUDE.md`](../../../CLAUDE.md) section "Transport two-frame model" for the overview,
> and [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md)
> Surface 8 for the contract side.)

> **Permission frame**: `list_panes` is a broker **ops-tier tool** (granted to secretary /
> dispatcher only; not granted to workers). So org-attach is a **Secretary / Dispatcher-side
> skill**, and the human runs it from the secretary session.

## Why the absolute path `/usr/bin/tmux` is mandatory (most important)

In zsh, `tmux` is **shadowed by an alias** from oh-my-zsh's tmux plugin (`tmux is an alias
for _zsh_tmux_plugin_run`). If you emit a bare `tmux ...`, the moment the human pastes it
into zsh it runs something else (the plugin wrapper) via the alias, and the
`-L claude-org-spike` socket selector or `attach -r -t <session>` will not take effect as
intended. **All generated commands must use the real path `/usr/bin/tmux`**, and the output
must include a one-line note explaining why.

## Step 0: confirm the transport frame (stop if renga)

First read `ORG_TRANSPORT` read-only (this single command is the only thing allowed in Step 0):

```bash
printenv ORG_TRANSPORT
```

If on the renga frame, this skill is not applicable, so stop without generating any attach
commands.

- **If `ORG_TRANSPORT=renga` (explicit)**: stop with this message (do not generate attach
  commands):
  "We are currently running on renga (single-screen tiling). In renga, panes are tiles inside
  one live window, and the concept of attaching to a detached tmux session does not apply
  directly. Use [`/org-dashboard`](../org-dashboard/SKILL.md) to see the pane overview."
- **Otherwise (unset / `broker`)**: proceed to Step 1 as the broker(tmux) frame.

## Step 1: get the logical pane list (broker)

```
mcp__org-broker__list_panes
```

The return is one record per logical pane, with mainly these fields:

- `id`: on the tmux backend, **this is exactly the tmux pane_id (`%N` string)**.
  (runtime `broker_queue_event.schema.json`: "Backend-native pane id: int on WezTerm,
  string (e.g. `"%3"`) on tmux" / `dispatcher/runner.py`: "broker/tmux backend emits tmux
  pane_id strings of the form %N". On the WezTerm backend it is int, but on the tmux socket
  `claude-org-spike` that this skill targets, it arrives as a `%N` string.)
- `name`: pane name (`worker-{task_id}` / `dispatcher` / `secretary`, etc.)
- `role`: `secretary` / `dispatcher` / `curator` / `worker`
- `focused`, geometry (`x` / `y` / `width` / `height`), `cwd`

> **Important - only child panes spawned by broker (dispatcher / worker) are attachable**:
> The secretary (root secretary) is only registered as a **logical pane (bookkeeping entry,
> `register_logical_pane`)** at broker startup, and has **no adapter-backed pane: its `id`
> / pane_id is `null` (no `%N`)**. So it does **not appear in the spike socket's detached
> sessions and is not an attach target** (the secretary just runs in the human's own
> terminal where the org was launched, so attach is not needed in the first place). Only
> records whose `id` is `%N` are attachable.
> Primary reference: [`docs/operations/broker-dogfood-runbook.md`](../../../docs/operations/broker-dogfood-runbook.md)
> §8 (canonical guide for the attach entry path, "Scope (important)" section).

If `list_panes` returns empty / fails, report "no org panes found - please confirm
`/org-start` has been run" and stop. If `list_panes` returns `[tool_not_authorized]`, the
caller lacks ops-tier permission (e.g. invoked from a worker session); guide them to run it
on the secretary / dispatcher side.

If you need extra context, you may cross-reference peer name and cwd via
`mcp__org-broker__list_peers` (read-only); this is not required for the join.

## Step 2: get the tmux-side pane_id <-> session mapping

```bash
/usr/bin/tmux -L claude-org-spike list-panes -a -F '#{pane_id} #{session_name}'
```

- `-L claude-org-spike`: the runtime's `SPIKE_SOCKET`. The org's tmux lives on this socket.
- `-a`: enumerate all panes in all sessions.
- `-F '#{pane_id} #{session_name}'`: format each line as a fixed `%N <session>` two-column
  layout for **robust parsing**. (tmux's default line is
  `session:window.pane: [geometry] [history] %N (active)`, from which you can also extract
  the session name and `%N`, but explicit `-F` is more reliable.)

Example output (one line = one pane, each broker pane is an independent session
`spike-{pid}-{seq}`):

```
%0 spike-1912-1
%5 spike-1912-14
%6 spike-1912-17
```

If the socket connection itself is down, you will get
`error connecting to ... claude-org-spike`. In that case report "cannot connect to tmux
socket `claude-org-spike` (the org may not be up) - please confirm `/org-start` has been
run" and stop.

## Step 3: join on pane_id (%N)

Using the `id` (`%N`) from `list_panes` as the key, match against the `%N -> <session>`
mapping from Step 2:

```
list_panes.id (%N)  join  tmux pane_id (%N)  ->  session name per logical pane
```

Before joining, **exclude logical panes whose `id` is `null` (no `%N`)** first. They are
not attach targets - do not feed them to the join, report them in a separate bucket
(below). Only feed records whose `id` is `%N` to the tmux mapping match.

Unmatched entries on either side **must not fail the run; list them as informational** (this
happens in practice):

- **Logical panes whose `id` is `null` (typically the secretary)**: this is not drift, it's
  **normal**. They have no adapter-backed pane and cannot be attached. Annotate them with
  "(logical pane / not an attach target. The secretary lives in the human's own terminal)"
  and show them in a separate bucket (do not print an attach command).
- **list_panes has `%N` but tmux has no matching `%N`**: drift right after a backend restart
  / a pane dying. Treat as "session unresolvable", do not emit an attach command, and just
  print the row with "(no %N on the tmux side)".
- **tmux has it but list_panes does not**: manual session outside the org / an orphan
  session. Treat as "(unregistered session in broker)" and, with role/name unknown, just
  print the attach command for reference (leave it to human judgment).

## Step 4: generate and print attach commands

For each joined pane, emit the following, labeled with role + name(task_id):

- **Read-only attach (default, safe)**: `/usr/bin/tmux -L claude-org-spike attach -r -t <session>`
  - `-r` = read-only attach. Just peek without breaking the pane via stray input.
    **Always guide the user here first.**
- **Read-write attach (only when you want to type yourself)**: take the same command and
  **drop `-r`**
  -> `/usr/bin/tmux -L claude-org-spike attach -t <session>`
- **Detach**: while attached, press `Ctrl-b d` to detach yourself while leaving the pane
  running (the pane keeps living - this is not close).

Append one line at the end of the output: "`tmux` is alias-shadowed in zsh, so always use
the real path `/usr/bin/tmux`."

## Output format (worked example)

Suppose Step 1 / Step 2 returned the following.

`list_panes` (logical panes; secretary has `id` = `null` as a logical pane):

| id | role | name |
|---|---|---|
| `null` | secretary | secretary |
| `%5` | dispatcher | dispatcher |
| `%6` | worker | worker-feat-org-attach-skill |

`/usr/bin/tmux -L claude-org-spike list-panes -a -F '#{pane_id} #{session_name}'`
(note the secretary is a logical pane and **does not appear** on the spike socket):

```
%5 spike-1912-14
%6 spike-1912-17
```

Exclude logical panes -> join only dispatcher / worker that have `%N` -> emit:

```
Attach commands for org panes (broker/tmux frame, read-only skill: display only, no auto-attach)
* Paste these into your own terminal to enter

# dispatcher (dispatcher)          session=spike-1912-14
  read-only : /usr/bin/tmux -L claude-org-spike attach -r -t spike-1912-14
  read-write: /usr/bin/tmux -L claude-org-spike attach    -t spike-1912-14

# worker (worker-feat-org-attach-skill)   session=spike-1912-17
  read-only : /usr/bin/tmux -L claude-org-spike attach -r -t spike-1912-17
  read-write: /usr/bin/tmux -L claude-org-spike attach    -t spike-1912-17

(logical pane / not an attach target)
- secretary (secretary): the secretary is a logical pane (no pane_id, does not appear on
  the spike socket). It is visible directly in the human's own terminal where the org was
  launched, so no attach is needed.

- Prefer read-only (-r) first. Drop -r only when you want to type yourself.
- Leaving: Ctrl-b d (detach. The pane keeps running while you alone leave).
- Switching sessions: Ctrl-b s (pick from the session list while attached. Currently
  per-session attach).
- tmux is alias-shadowed in zsh, so always use the real path /usr/bin/tmux.
```

Example addendum for unmatched entries:

```
(For reference) entries that could not be joined:
- broker %3 (worker / worker-foo) : no %3 on the tmux side (possibly pane drift, not attachable)
- tmux session spike-1912-9 (%9)  : session not registered with broker (possibly outside the org / orphan)
    /usr/bin/tmux -L claude-org-spike attach -r -t spike-1912-9
```

## What this skill does not do (read-only invariants)

- Does not attach by itself (only emits command **strings**).
- Does not spawn / close / rename / send_keys / send_message any pane.
- Does not modify `.state/` / registry / tmux.
- Write / spawn / send-style broker / tmux tools are not in `allowed-tools` (allowed are
  only `list_panes` / `list_peers` and the read-only tmux `list-panes` / `list-sessions`).
- If you only want a status overview, use [`/org-dashboard`](../org-dashboard/SKILL.md);
  for delegating work, use [`/org-delegate`](../org-delegate/SKILL.md) (this skill is solely
  for emitting attach commands).
