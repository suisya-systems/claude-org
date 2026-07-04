---
name: pr-watch-pane
description: >
  Run PR CI / merge monitoring (tools/pr-watch.sh) in a dedicated pane
  pr-watch-<PR> inside the broker tmux session. When the Lead starts it with
  `/pr-watch-pane <PR>` right after creating a PR, the monitoring runs in ja-root
  cwd, outside the sandbox, and continues independently of /clear or the Lead
  session's lifetime. Idempotent start via the pane name (no double monitoring),
  identity registration with role=watcher, and the pane auto-closes when
  monitoring ends (CI green / PR merged / timeout). The Bash tool's background
  mode is session-lifetime-bound and unsuitable for a long-running watcher, so
  this skill is the recommended path.
  Triggered by "watch CI in a pane", "run pr-watch in a pane",
  "watch PR <N>'s CI", etc.
effort: low
allowed-tools:
  - Read
  - Bash(git rev-parse:*)
  - Bash(gh repo view:*)
  - Bash(bash tools/journal_append.sh:*)
  - Bash(py -3 tools/journal_append.py:*)
  - mcp__org-broker__list_panes
  - mcp__org-broker__spawn_pane
  - mcp__org-broker__set_pane_identity
  - mcp__org-broker__inspect_pane
  - mcp__org-broker__close_pane
---

# pr-watch-pane: run CI / merge monitoring in a dedicated pane

Start `tools/pr-watch.sh <PR> --repo <owner/repo> --merge-watch` in a dedicated pane
(`name="pr-watch-<PR>"`) inside the broker tmux session. The Bash tool's background start is
session-lifetime-bound and unsuitable for a long-running watcher like CI monitoring (outside the
official design). Going through a broker pane spawn keeps the monitoring running **outside the
sandbox and independent of the Lead session** (unrelated to `/clear` or the Lead's context reset),
and since a human can see it directly in the tmux pane, visibility is also high
(consistent with feedback-dispatcher-visibility).

The monitoring results are preserved along two paths (both are existing `pr_watch.py` behavior;
this skill does not change their shape):

- **`.state/state.db` events table** … the canonical event rows for `ci_completed` /
  `pr_merge_watch_timeout` (the payload shape and the `CI_COMPLETED` / `PR_MERGED` /
  `PR_MERGE_WATCH_TIMEOUT` message shapes are unchanged). **This is the canonical record of the verdict.**
- **`.state/pr-watch-<PR>.log` + tmux scrollback buffer** … the human-readable raw log, two layers.

> **peer push is best-effort**: `pr_watch.py` tries to send `CI_COMPLETED` / `PR_MERGED` peer
> messages to the Lead when CI is decided / on merge, but this is best-effort via
> `tools/peer_notify.py` (a no-op on panes where the broker send CLI is absent / `ORG_TRANSPORT` /
> `RENGA_SOCKET` is unset). In environments where the daemon runs on a non-default state dir
> (herdr dogfood, etc.), if the pane env lacks `ORG_BROKER_STATE_DIR` the broker send grabs the
> default `.state/broker` and the push is dropped (a drop does not affect the canonical events DB
> rows). **The correct path to wait on is the events DB rows above and the visible pane**, and do
> not make push delivery a precondition of the merge gate (org-pull-request's CI/merge gate uses
> the events DB as its primary source).

> **Transport (dual-rail) - default `broker` / opt-in `renga`**: This file (and each skill) writes its peer-message / pane operations as `mcp__org-broker__*`, so with **`ORG_TRANSPORT` unset = default `broker`** you can follow the prose as-is. Under `ORG_TRANSPORT=renga` (opt-in, revertible) the MCP server name becomes `renga-peers`, and the **fully-qualified names mechanically rewrite from `mcp__org-broker__*` to `mcp__renga-peers__*`** (the argument shape and semantics are identical, so the operation logic does not change). Only the following three points differ between the rails:
>
> - **Receive model (default = push-primary = `claude/channel` / pull fallback)**: Default broker is designed as **push-primary** (runtime push-first 0.1.24+, design SoT in transport-lab `docs/design/broker-native-roles.md` §9): each pane's co-resident **channel sidecar** (`server:org-broker-channel`) claims the broker queue at ~1s intervals and pushes by injecting bodies into idle sessions via `notifications/claude/channel` (a "receive then immediately respond" moment arises). Worker acks (`to_id="worker-{task_id}"`), retro-gate acks (`to_id="dispatcher"`), and the dispatcher-handover path all use the same tool names (`mcp__org-broker__*`) for `send_message` / `check_messages` / `send_keys` / `inspect_pane`. **Pull is the fallback layer**: when the sidecar is absent / unhealthy (heartbeat timeout flips `delivery_mode=PULL`) / on channel-unsupported panes (codex pull-peer) / when claude.ai login is missing, each role actively `check_messages` at its own cadence (per-role cadence: worker = turn boundary / bounded `/loop` after completion; dispatcher = `/loop 3m`; secretary = top-of-turn). The existing "if a nudge arrives, then `check_messages`" prose is **not retracted** and should be read as this fallback cadence. Under `ORG_TRANSPORT=renga` (opt-in), worker reports and dispatcher responses are pushed in-band as `<channel source="renga-peers" ...>` (renga's in-band push and broker push-primary share the same immediate-response moment). On contract surface, push-primary is **ratified** under Surface 8 + push-primary amendment (2026-06-15, S3; pull retained as fallback; renga unchanged).
> - **Spawn ritual (default = folder-trust approval + dev-channel sidecar approval, two-step)**: When spawning child panes, default broker injects `--mcp-config <broker>` and machine-approves Claude Code's **folder-trust prompt** via `send_keys(enter=true)`, **and in addition** loads the channel sidecar via `--dangerously-load-development-channels server:org-broker-channel` for push-primary and machine-approves the dev-channel approval prompt (spawn-flow 3-3b) via `send_keys(enter=true)` (the two-step approval = folder-trust + dev-channel; see [`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md) 3-2 / 3-3b; design in broker-native-roles.md §9.5). Under `ORG_TRANSPORT=renga` (opt-in), it injects `--dangerously-load-development-channels server:renga-peers` and Enter-approves "Load development channel?" - a single step. **Note: the attention watcher is a transport-neutral CLI pane and is exempt from both folder-trust and dev-channel two-step approval** (do not drag it into the spawn-ritual flip).
> - **Error branches (default = broker extended codes included)**: Default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` / `[unknown_tool]` in addition to shared codes (`pane_not_found` / `last_pane` / `invalid-params`, Surface 6) (unknown codes are escalated via the default branch). Under `ORG_TRANSPORT=renga`, the broker-specific codes do not occur; only shared codes + renga-specific codes apply.
>
> The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14) + the trailing "Ratified amendment (2026-06-15): push-primary delivery" (S3; **broker push-primary is the contract default**, pull retained as structural fallback). Design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary) / `docs/design/ja-migration-plan.md` §5, §8. **Opt-in `renga` is not removed; it is retained as an always-available fallback** (the revert safety net). Running broker is the default operational path.

> **This skill's spawn target is a "generic CLI pane"**: what it starts is the shell command
> `tools/pr-watch.sh`, not a Claude session (`spawn_claude_pane`), so it uses the
> **generic `mcp__org-broker__spawn_pane`**. Therefore the **spawn ritual from the header above (broker:
> two-step folder-trust + channel-sidecar approval / renga: one-step dev-channel approval) does
> not occur at all in this skill** (there is no `--mcp-config` / `--dangerously-load-development-channels`
> injection, so no approval prompt appears). It is treated as the same kind of CLI pane as the
> attention watcher (equivalent to the note at the end of the shared header, "the attention watcher
> is ... exempt from the two-step approval"). The only thing that switches between the two rails is
> the **tool's fully-qualified name**:
>
> - default broker: `mcp__org-broker__spawn_pane` (`list_panes` / `set_pane_identity` /
>   `inspect_pane` / `close_pane` are likewise `mcp__org-broker__*`)
> - opt-in renga: `mcp__renga-peers__spawn_pane` (likewise `mcp__renga-peers__*`)
>
> The steps below are logically identical on both rails once you read `mcp__org-broker__` as the active
> transport's fully-qualified name. The identity registration and start command right after spawn are
> also common to both rails (no Enter approval, since it is a CLI pane).

## Prerequisites

- This skill is **Lead-only (secretary)**. The generic `spawn_pane` is held only by the secretary on
  broker's auth tier (the dispatcher has only `spawn_claude_pane`; contract
  [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md)
  Surface 8 ops-tier definition).
- The Lead's cwd is ja-root (the repository root). Because the spawned pr-watch needs to resolve
  `.state/` paths and `tools/pr-watch.sh` relative to ja-root, **the skill absorbs the cwd trap**
  (Step 1 passes the absolute path from `git rev-parse --show-toplevel` explicitly as spawn_pane's
  `cwd`, so it resolves correctly even if the Lead's cwd has for some reason moved off ja-root).
- **The assumed environment is a POSIX/tmux broker (WSL2 / Linux / macOS)**. Step 3's `command`
  depends on `bash` execution and self-close via `tmux kill-pane -t "$TMUX_PANE"` (**kill by naming
  the own pane explicitly with `$TMUX_PANE`**; the socket uses `$TMUX` inheritance as-is and is not
  pinned with `-L` = it hits the correct server on any transport, broker / renga / a non-default
  socket. This is a transport-neutral implementation of Issue #647 proposal 1's "explicit target
  specification"). On a Windows native broker (a separate WezTerm GUI window, not going through tmux)
  this skill's self-close does not work, so in that environment use the traditional manual path where
  a human starts `tools/pr-watch.ps1 <PR>` via `!` (this skill does not block that path = the existing
  manual start path is unchanged).

## Step 1: resolve arguments and fix cwd / repo

1. Take the PR number `<PR>` from the arguments (required, positive integer). If omitted, ask the
   user for the PR number and abort.
2. Deterministically resolve the ja-root absolute path and owner/repo (cwd-trap absorption + explicit repo):

   ```bash
   git rev-parse --show-toplevel                          # -> JA_ROOT (absolute path)
   gh repo view --json nameWithOwner -q .nameWithOwner    # -> OWNER/REPO
   ```

   - If `gh repo view` fails, report to the user "cannot auto-resolve the repository; please specify
     `--repo OWNER/REPO`" and abort. pr-watch.sh itself also auto-resolves when `--repo` is omitted,
     but being explicit here **fixes the repo independently of the pane's cwd** (so the cwd trap does
     not spill into repo resolution).

## Step 2: idempotency check (prevent double monitoring of the same PR)

Call `mcp__org-broker__list_panes` and check whether a live pane with `name="pr-watch-<PR>"` already exists.

- **Exists** → already monitoring. **Do not spawn**; report "the CI monitoring pane for PR #<PR>
  (`pr-watch-<PR>`, id={N}) is already running" and finish. If they want to restart, guide them to
  first close that pane with the Step 5 procedure and then re-run.
- **Does not exist** → go to Step 3.

> The pane name `pr-watch-<PR>` is the idempotency key. `<PR>` is numeric, but the `pr-watch-`
> prefix includes letters, so it satisfies the allowed charset `[A-Za-z0-9_-]` and is not all-digits
> (= treated as an id, which would be ambiguous).

## Step 3: spawn the monitoring pane

Start the CLI watcher pane with `mcp__org-broker__spawn_pane` (replace `<...>` with the values fixed in Step 1 / the arguments):

```
mcp__org-broker__spawn_pane(
  target="dispatcher",
  direction="vertical",
  role="watcher",
  name="pr-watch-<PR>",
  cwd="<JA_ROOT absolute path>",
  command="mkdir -p .state; bash tools/pr-watch.sh <PR> --repo <OWNER/REPO> --merge-watch --no-detach 2>&1 | tee -a .state/pr-watch-<PR>.log; tmux kill-pane -t \"$TMUX_PANE\" 2>/dev/null || true"
)
```

- `target="dispatcher"`: a stable anchor for the same-tab scope (like the attention watcher, it uses
  the dispatcher as the split origin). On broker each pane is a detached independent session, but to
  satisfy the addressing scope (same-tab MUST, contract Surface 4.2) it takes an existing pane as the origin.
- `role="watcher"`: a display label to identify the monitoring pane in list_panes (like the attention
  watcher's `role="attention"`, a label outside the canonical 4 roles; on broker the token's auth tier
  is fixed at spawn time and the role label does not change the tier — Surface 8).
- `cwd`: **the JA_ROOT absolute path resolved in Step 1**. This makes `tools/pr-watch.sh` /
  `.state/pr-watch-<PR>.log` inside the pane resolve relative to ja-root (cwd-trap absorption).
- **`--no-detach` is required (Issue #650)**: `tools/pr-watch.sh` self-detaches with setsid + nohup by
  default (as a countermeasure for Issue #641), so without `--no-detach` the parent bash exits right
  after spawn, the broker pane is cleaned up immediately, and the watcher is orphaned (with no pane you
  cannot even peek via `/org-attach` / `Ctrl-b s`). `--no-detach` runs it in the foreground and lets the
  `tee` and trailing self-close self-termination cycle work.
- `command`: runs pr-watch in the foreground and `tee -a`s stdout/stderr to `.state/pr-watch-<PR>.log`
  (two layers, also appearing in the tmux scrollback buffer). The leading `mkdir -p .state` secures the
  tee output destination even on a fresh clone. After pr-watch ends, `tmux kill-pane -t "$TMUX_PANE"`
  **self-closes the pane** (auto-close when monitoring ends; `|| true` swallows the error even in an
  environment without tmux).
  - **`$TMUX_PANE` is a runtime env, not a placeholder**: unlike `<PR>` / `<OWNER/REPO>`, the Lead must
    not substitute a value for `$TMUX_PANE`. It is the own-pane id (e.g. `%16`) automatically exposed in
    the spawned pane's shell, and it resolves **the pane itself** as the explicit target at self-close
    time. The old form `tmux kill-pane` (no target) implicitly infers the current pane, but making it
    explicit with `-t "$TMUX_PANE"` removes the ambiguity (Issue #647 proposal 1's "explicit target
    specification").
  - **the socket uses `$TMUX` inheritance as-is (do not pin with `-L`)**: starting `tmux` without `-L`
    auto-resolves the socket of the tmux server the pane belongs to from `$TMUX`. On broker that is the
    `claude-org-broker` socket; under opt-in renga or a non-default socket setup it is a different
    socket, but in all cases `$TMUX` points at the correct server, so the kill lands. Pinning
    `-L claude-org-broker` here would **hit a different server and silently fail the self-close** under
    renga / a non-default socket, so keep the socket unpinned and transport-neutral.
  - **self-close only cleans up the tmux layer**: `kill-pane` removes the real tmux pane on the broker
    socket, so it stops appearing in `list_panes` immediately after. However, the broker daemon's pane
    registry (name binding) is not popped by a self-close and **can remain stale** (the daemon does not
    detect an external kill of its own pane). If a stale binding remains, a re-spawn of the same-named
    `pr-watch-<PR>` is rejected with `[name_taken]` (the symptom being: it does not appear in
    `list_panes`, yet). This cleanup is done by Step 5's manual fallback
    (`mcp__org-broker__close_pane(target="pr-watch-<PR>")` pops the registry).
  - `--merge-watch`: after emitting `CI_COMPLETED` on CI green, keeps polling until merge (up to 24h),
    emits `PR_MERGED` on merge or `PR_MERGE_WATCH_TIMEOUT` on timeout, and then self-closes. If you want
    to stop at CI decision only, drop `--merge-watch` at call time (then it self-closes on CI green /
    failed decision).
  - The existing message shapes and event payload shapes of pr-watch.sh are **not changed at all by
    this skill** (invariant). The existing manual `tools/pr-watch.sh` start path (via a human's `!`,
    etc.) also works as before.

Note down the N in the return value `"Spawned pane id=N."`.

**Branches on spawn failure** (judge by the `[<code>]` in the MCP result text; details in
[`.claude/skills/org-delegate/references/renga-error-codes.md`](../org-delegate/references/renga-error-codes.md)):

- `[split_refused]` (no broker free-pane / below MIN_PANE) → report "there is no room to create a
  monitoring pane (the terminal is too narrow / pane limit reached); widen the terminal or close
  unneeded panes and re-run" and abort.
- `[pane_not_found]` (no `target="dispatcher"`) → report "the dispatcher pane was not found; run
  `/org-start` first" and abort.
- `[name_in_use]` / `[name_taken]` → **separate a live pane from a stale registry** (self-recover the
  "two-layer inconsistency" where the previous watcher's self-close removed the tmux pane but the name
  binding remains in the broker registry):
  1. Re-check via `mcp__org-broker__list_panes` whether a **live pane with `name="pr-watch-<PR>"` actually exists**.
  2. **A live pane exists** → a genuine race that the idempotency check missed. Fall back to Step 2's
     "already running" report as already monitoring (do not spawn anew).
  3. **No live pane** (does not appear in `list_panes`) → a **stale registry binding** from an
     already-completed self-close. Have `mcp__org-broker__close_pane(target="pr-watch-<PR>")` resolve by name and
     pop the registry (returns `ok closed=%N`; `[pane_not_found]` means it was already cleaned up, which
     is fine), and **retry the Step 3 spawn exactly once**. If `[name_taken]` still continues on the
     retry, report to the user and abort (an unexpected registry state).
- broker-specific (`[no_backend]` / `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` /
  `[peer_not_found]`, etc.) / any other unknown code → report the situation to the user and abort
  (default-branch escalate).

## Step 4: identity registration and start-up health check

1. **Confirm identity (register role=watcher)**: check via `mcp__org-broker__list_panes` whether spawn_pane's
   `name` / `role` were applied. If `name="pr-watch-<PR>"` and `role="watcher"` are attached, it is
   registered. On a backend where one of them happens to be missing, repair it with
   `mcp__org-broker__set_pane_identity(target=<N>, name="pr-watch-<PR>", role="watcher")`.
   - This pane is a CLI process, not a Claude session, so it **has no Claude peer (peer_id)**. "peer
     registration" here means registering name + role=watcher into the pane registry (done by
     spawn_pane / set_pane_identity). No MCP peer / dev-channel registration occurs.
2. **Immediate-crash detection (negative signals only)**: peek at the output with
   `mcp__org-broker__inspect_pane(target=<N>, format="text", lines=40)` and judge "start failed" only if you
   detect one of the following:
   - `command not found` / `is not recognized` / `No such file or directory`
   - gh missing such as `gh: ... not found` / `Traceback (most recent call last)` / `ModuleNotFoundError`
   - a shell prompt at the end of the output (`$ ` / `% ` exposed at the end) = the command exited
     immediately and returned to the shell
   - if none of the above are present (pr-watch's watch-loop output / empty / a quiet moment right after
     start), **treat it as a successful start**; there is no path that inserts a fixed sleep and
     re-inspects (do not falsely kill a healthy quiet start).
   - on start failure, clean up the dead pane with `mcp__org-broker__close_pane(target=<N>)` and report the cause
     (installing `tools/pr-watch.sh` / `gh`, cwd) to the user and abort.

## Step 5: audit record and report / manual close

1. Record the start in the journal, best-effort:

   ```bash
   bash tools/journal_append.sh pr_watch_pane_started pr=<PR> repo=<OWNER/REPO> pane_id=<N>
   ```

   On Windows native: `py -3 tools/journal_append.py pr_watch_pane_started pr=<PR> repo=<OWNER/REPO> pane_id=<N>`.

2. Report to the user:

   ```
   Started the CI / merge monitoring pane pr-watch-<PR> (id={N}) for PR #<PR>.
   - Log: .state/pr-watch-<PR>.log (also output to the tmux scrollback buffer)
   - The pane closes automatically when monitoring ends (merge / CI failure decision / timeout).
     The decided CI verdict remains in the `ci_completed` row of `.state/state.db` and in the log,
     so the verdict is not lost even after the pane closes (the merge gate reads there).
   - To view it directly in tmux, use the `/org-attach` command.
   ```

3. **Manual close (cleanup for cases that do not auto-close, Issue #647 proposal 3)**: self-close only
   removes the tmux pane, and the broker registry's name binding can remain (see "self-close only cleans
   up the tmux layer" above). Clean up in two cases:

   - **(a) the tmux pane remained live / you want to stop monitoring partway**: check the live pane with
     `name="pr-watch-<PR>"` via `mcp__org-broker__list_panes` and `mcp__org-broker__close_pane(target=<N>)` by its **numeric
     pane_id** (`[pane_not_found]` / `[pane_vanished]` are treated as already-closed and skipped). In
     this case where a live pane exists, use the numeric pane_id whose identity you confirmed via
     list_panes rather than a name target (to avoid a wrong close on id recycle).

   - **(b) stale registry binding (does not appear in `list_panes`, yet a re-spawn gets `[name_taken]`)**:
     a state where self-close removed the tmux pane but the name binding remains in the broker registry.
     Since the numeric pane_id does not appear in list_panes and cannot be obtained, use a **name target**
     with `mcp__org-broker__close_pane(target="pr-watch-<PR>")` (broker resolves name → stale pane_id and pops the
     registry, returning `ok closed=%N`; `[pane_not_found]` means it was already cleaned up, which is
     fine). After cleanup, a same-named spawn goes through. Step 3's `[name_taken]` branch self-recovers
     this (b), but you can also clean it up manually with the same procedure.
