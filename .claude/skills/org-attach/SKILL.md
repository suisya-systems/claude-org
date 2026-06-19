---
name: org-attach
description: >
  Read-only skill that **only emits commands** for the human to use to **directly
  attach via tmux** to live org panes (secretary / dispatcher / worker).
  It joins `mcp__org-broker__list_panes` (logical pane list) with
  `/usr/bin/tmux -L claude-org-broker list-panes -a` (pane_id <-> session mapping)
  on pane_id (%N), and prints an attach command for each pane labeled with
  role + name(task_id) (read-only `-r` / writable without `-r` / detach with `Ctrl-b d`).
  Triggered by "I want to see a worker's pane", "I want to attach to a worker pane",
  "I want to peek at the dispatcher directly", "let me into a pane",
  "tell me the attach command", "connect via tmux", "enter the worker's screen", etc.
  Does not attach itself or change any pane (it only displays command strings and a pane list).
  Does NOT fire for delegation (org-delegate), dashboard listing (org-dashboard),
  or watcher stop (org-attention-stop).
effort: low
allowed-tools:
  - Read
  - Bash(printenv ORG_TRANSPORT)
  - Bash(/usr/bin/tmux -L claude-org-broker list-panes*)
  - Bash(/usr/bin/tmux -L claude-org-broker list-sessions*)
  - mcp__org-broker__list_panes
  - mcp__org-broker__list_peers
---

# org-attach: generate tmux attach commands for org panes (read-only)

A skill that **generates and displays attach command strings** so a human can
directly attach via tmux **from their own terminal** to live org panes
(secretary / dispatcher / worker).
This skill **does not attach to anything and does not modify any pane**. It joins
the logical pane list (from broker) with the tmux side pane_id <-> session
mapping on pane_id (`%N`), and just prints an attach command per pane labeled
with role + name(task_id). The human copies and pastes the command into their
own terminal to get in.

> **Transport dual systems (frame C / two-frame note) -- this skill is broker(tmux) frame only**:
> This skill presupposes **attach to detached tmux sessions** on the tmux backend
> (socket `claude-org-broker`). **broker frame**: each broker pane exists as an
> independent detached tmux session named `claude-org-broker-{pid}-{seq}`
> (1 pane = 1 session), and you enter via `tmux attach -t <session>` --
> this is the primary frame where the attach model of this skill makes sense.
> **The renga frame (opt-in, `ORG_TRANSPORT=renga`) has a different concept**:
> renga is a **single-screen tiling** model where panes are **tiles** inside a
> single live window, not independent detached sessions. The notion of "re-attach
> to a detached session" does not map directly, and there is no per-pane
> `tmux attach -t <session>`. So under renga the attach form of this skill is
> **not applicable** -- you just look at the screen itself (no attach needed).
> Under the renga frame this skill explicitly says "broker(tmux)-only tool" and
> halts (see Step 0 below).
>
> (**Default two-frame note (Refs #604)**: org-attach is essentially a broker/tmux
> tool, so the header is written **broker-primary**. The transport-wide default
> has two frames that refer to different things -- the **operational default** is
> renga (production broker dogfood is inactive until Epic #6 Issue G), but the
> **code default** in `tools/transport.py: DEFAULT_TRANSPORT` was flipped from
> `renga` to `broker` in runtime 0.1.28 (Epic #586). Among manually-maintained
> skills that use broker tools,
> [`.claude/skills/org-attention-stop/SKILL.md`](../org-attention-stop/SKILL.md)
> writes its header in the code-default frame ("default `broker` / opt-in
> `renga`") -- this skill follows that broker-primary precedent.
> ([`.claude/skills/org-attention-start/SKILL.md`](../org-attention-start/SKILL.md)
> conversely is written in the operational-default frame ("default `renga`") and
> the two are not contradictory, they just refer to different things.) The
> overview is in the root [`CLAUDE.md`](../../../CLAUDE.md) "Transport dual
> systems" section, and the contract surface is in
> [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md)
> Surface 8.)

> **Authorization frame**: `list_panes` is a broker **ops-tier tool** (granted to
> secretary / dispatcher only, never to workers). Therefore org-attach is a
> **Secretary / Dispatcher facing skill** that the human runs from the secretary
> session.

## Why the absolute path `/usr/bin/tmux` is mandatory (most important)

Under zsh, `tmux` gets **alias-shadowed** by the oh-my-zsh tmux plugin
(`tmux is an alias for _zsh_tmux_plugin_run`). If you emit a bare `tmux ...`,
the moment the human pastes it into zsh the alias kicks in and runs a different
thing (the plugin wrapper), and `-L claude-org-broker` socket selection or
`attach -r -t <session>` does not work as intended. **All generated commands
must use the absolute path `/usr/bin/tmux`**, and the output should include a
one-line explanation of why.

## Step 0: confirm the transport frame (halt if renga)

First read `ORG_TRANSPORT` read-only (this is the only command allowed in Step 0):

```bash
printenv ORG_TRANSPORT
```

If the frame is renga, this skill does not apply -- halt without generating
attach commands.

- **If `ORG_TRANSPORT=renga` (explicit)** -> halt and report (do not generate
  attach commands): "We are currently running on renga (single-screen tiling).
  Under renga, panes are tiles inside a single live window, so the concept of
  attaching to a detached tmux session does not directly apply. For a list of
  pane status, please use [`/org-dashboard`](../org-dashboard/SKILL.md)."
- **Otherwise (unset / `broker`)** -> treat as broker(tmux) frame and proceed
  to Step 1.

## Step 1: get the logical pane list (broker)

```
mcp__org-broker__list_panes
```

The return value is 1 logical pane = 1 record, with mainly these fields:

- `id`: on the tmux backend **this is literally the tmux pane_id (the `%N`
  string)**.
  (runtime `broker_queue_event.schema.json`: "Backend-native pane id: int on
  WezTerm, string (e.g. `"%3"`) on tmux" / `dispatcher/runner.py`: "broker/tmux
  backend emits tmux pane_id strings of the form %N". WezTerm backend gives
  ints, but on the tmux socket `claude-org-broker` that this skill targets it
  comes through as a `%N` string.)
- `name`: pane name (`worker-{task_id}` / `dispatcher` / `secretary`, etc.)
- `role`: `secretary` / `dispatcher` / `curator` / `worker`
- `focused`, geometry (`x` / `y` / `width` / `height`), `cwd`

> **Important -- only broker-spawned child panes (dispatcher / worker) are
> attachable**:
> The secretary (root secretary) is registered at broker startup as a
> **logical pane (bookkeeping entry, `register_logical_pane`)** only, and
> **has no adapter-backed real pane, so its `id` / pane_id is `null` (no `%N`)**.
> Therefore it **does not appear in the broker socket's detached sessions and is
> not attachable** (the secretary runs in the human's own terminal where they
> started the org, so attach is not needed anyway). Only records whose `id` is a
> `%N` are attachable.
> Primary reference:
> [`docs/operations/broker-dogfood-runbook.md`](../../../docs/operations/broker-dogfood-runbook.md)
> Section 8 (the canonical guide to the attach path -- see the "Scope (important)"
> note).

If `list_panes` returns empty / unobtainable, halt and report "No org panes
found. Please make sure `/org-start` has run." If `list_panes` returns
`[tool_not_authorized]`, you do not have the ops-tier permission (you are
calling from a worker session, etc.), so direct the user to run from the
secretary / dispatcher side.

For extra context you can optionally cross-reference `mcp__org-broker__list_peers`
(read-only) to line peer names up with cwd (not required for the join).

## Step 2: get the tmux side pane_id <-> session mapping

```bash
/usr/bin/tmux -L claude-org-broker list-panes -a -F '#{pane_id} #{session_name}'
```

- `-L claude-org-broker`: runtime's `BROKER_SOCKET`. The org's tmux lives on this
  socket.
- `-a`: enumerate every pane in every session.
- `-F '#{pane_id} #{session_name}'`: shape each line into a fixed 2-column
  `%N <session>` form for **robust parsing** (tmux's default line is
  `session:window.pane: [geometry] [history] %N (active)`-shaped, from which you
  can also extract the session name and `%N`, but the explicit `-F` is more
  reliable).

Example output (1 line = 1 pane; each broker pane is its own session
`claude-org-broker-{pid}-{seq}`):

```
%0 claude-org-broker-1912-1
%5 claude-org-broker-1912-14
%6 claude-org-broker-1912-17
```

If the socket connection itself is down, you get
`error connecting to ... claude-org-broker` back. In that case, report
"cannot connect to tmux socket `claude-org-broker` (the org may not be running).
Please make sure `/org-start` has run." and halt.

## Step 3: join on pane_id (%N)

Using `list_panes`'s `id` (`%N`) as the key, join against the
`%N -> <session>` mapping from Step 2:

```
list_panes.id (%N)  ⨝  tmux pane_id (%N)  ->  session name for each logical pane
```

Before the join, first **exclude logical panes whose `id` is `null` (no `%N`)**.
These are not attachable -- do not send them through the join, report them
separately (see below). Only records whose `id` is `%N` go through the tmux
mapping join.

**Entries that do not match on either side should not be reported as failures;
list them** (this happens in real operation):

- **logical panes with `id` of `null` (typically the secretary)**: this is not
  drift but **normal**. They have no adapter-backed real pane and cannot be
  attached. Note them separately as "(logical pane / not attachable. Secretary
  is on the human's local terminal)" without an attach command.
- **`%N` is in list_panes but the same `%N` is not in tmux**: drift right after
  a backend restart / pane death. As "session cannot be resolved", do not emit
  an attach command, just print the line with "(no %N on tmux side)".
- **In tmux but not in list_panes**: manual / orphan session outside the org.
  As "(broker-unregistered session)", emit the attach command for reference only
  with role/name unknown (leave the judgment to the human).

## Step 4: generate and emit attach commands

For each pane that joined, emit the following, labeled with role + name(task_id):

- **read-only attach (default, safe)**:
  `/usr/bin/tmux -L claude-org-broker attach -r -t <session>`
  - `-r` = read-only attach. Just peek without breaking the pane with a stray
    keypress. **Suggest this first.**
- **read-write attach (only when you want to type yourself)**: take the same
  command and **remove `-r`** -> `/usr/bin/tmux -L claude-org-broker attach -t <session>`
- **detach**: while attached, pressing `Ctrl-b d` detaches just you while the
  pane keeps running (the pane stays alive -- this is not a close).

At the end of the output, add one line "tmux gets alias-shadowed under zsh,
so always use the absolute path `/usr/bin/tmux`."

## Output format (worked example)

Suppose Step 1 / Step 2 returned the following.

`list_panes` (logical panes; the secretary is a logical pane with `id` of
`null`):

| id | role | name |
|---|---|---|
| `null` | secretary | secretary |
| `%5` | dispatcher | dispatcher |
| `%6` | worker | worker-feat-org-attach-skill |

`/usr/bin/tmux -L claude-org-broker list-panes -a -F '#{pane_id} #{session_name}'`
(note: because the secretary is a logical pane it **does not appear** on the
broker socket):

```
%5 claude-org-broker-1912-14
%6 claude-org-broker-1912-17
```

Exclude logical panes -> join only the dispatcher / worker that have `%N` ->
output to generate:

```
Attach commands for org panes (broker/tmux frame, read-only skill: display only,
does not auto-attach)
* Paste these into your own terminal to get in.

[*] dispatcher (dispatcher)          session=claude-org-broker-1912-14
    read-only : /usr/bin/tmux -L claude-org-broker attach -r -t claude-org-broker-1912-14
    read-write: /usr/bin/tmux -L claude-org-broker attach    -t claude-org-broker-1912-14

[*] worker (worker-feat-org-attach-skill)   session=claude-org-broker-1912-17
    read-only : /usr/bin/tmux -L claude-org-broker attach -r -t claude-org-broker-1912-17
    read-write: /usr/bin/tmux -L claude-org-broker attach    -t claude-org-broker-1912-17

(logical pane / not attachable)
- secretary (secretary): the Secretary is a logical pane (no pane_id, does not
  appear on the broker socket). It is visible as-is on the human's terminal
  where the org was started, so attach is not needed.

- Recommended: enter read-only (-r) first. Remove -r only when you want to type.
- To leave: Ctrl-b d (detach; the pane keeps running while you leave).
- Switch sessions: Ctrl-b s (pick from the session list while attached;
  currently this is per-session attach).
- tmux gets alias-shadowed under zsh, so always use the absolute path
  /usr/bin/tmux.
```

Example addendum when unmatched entries exist:

```
(For reference) entries that did not join:
- broker %3 (worker / worker-foo) : no %3 on the tmux side (possible pane drift,
  cannot attach)
- tmux session claude-org-broker-1912-9 (%9)  : session not registered with
  broker (may be outside the org / orphan)
    /usr/bin/tmux -L claude-org-broker attach -r -t claude-org-broker-1912-9
```

## What this skill does NOT do (read-only invariants)

- Does not `attach` on its own (only emits the command **string**).
- Does not spawn / close / rename / send_keys / send_message to any pane.
- Does not modify `.state/`, registry, or tmux.
- Write / spawn / send broker or tmux tools are not in `allowed-tools`
  (allowed: only `list_panes` / `list_peers` and read-only tmux `list-panes` /
  `list-sessions`).
- If you only need a status listing, use
  [`/org-dashboard`](../org-dashboard/SKILL.md); for delegation use
  [`/org-delegate`](../org-delegate/SKILL.md) (this skill is dedicated to
  emitting attach commands).
