---
name: org-attention-start
description: >
  Start the attention notification watcher (active OS notification + sound for awaiting approval /
  awaiting decision / CI failures, etc.) resident as a vertical split on the right side of the
  dispatcher pane. If `.state/attention.json` is not in place yet, the ja default template is
  auto-copied from `tools/templates/attention.example.json`. After startup, the pane id is recorded
  in `.state/attention_pane.json` and consumed by `/org-attention-stop`.
  Triggered by "start attention", "begin notification monitoring", "spin up the watcher", etc.
  `/org-start` does **not** auto-start it (explicit-start policy).
effort: low
allowed-tools:
  - Read
  - Write
  - Bash(mkdir:*)
  - Bash(cp:*)
  - Bash(copy:*)
  - Bash(test:*)
  - Bash(rm:*)
  - Bash(del:*)
  - Bash(bash tools/journal_append.sh:*)
  - Bash(py -3 tools/journal_append.py:*)
  - mcp__renga-peers__*
---

# org-attention-start: launch the attention watcher resident

Start `claude-org-runtime attention watch` resident as a vertical split on the right side of the
dispatcher pane, and record the pane_id as a sidecar in `.state/attention_pane.json`. Use
[`/org-attention-stop`](../org-attention-stop/SKILL.md) to stop it.

> **Transport — both rails (`ORG_TRANSPORT`: default `renga` / opt-in `broker`)**: this skill's `mcp__renga-peers__*` (`spawn_pane` / `list_panes` / `inspect_pane` / `close_pane`) is written for **default `renga`**, and with `ORG_TRANSPORT` unset you can follow it as-is (default behavior unchanged). With `ORG_TRANSPORT=broker` (opt-in, revertible) the fully qualified names are mechanically replaced from **`mcp__renga-peers__*` -> `mcp__org-broker__*`** (argument shape and semantics are identical, so the logic of spawn / monitoring operations does not change). The attention watcher is a `claude-org-runtime` CLI, not a Claude pane, so **dev-channel / folder-trust approvals are unnecessary on both rails** (the spawn-ritual difference only takes effect for Claude-pane spawns). Errors gain broker-added codes (`[no_backend]` (= adapter_unavailable) / `[token_invalid]` etc.; see the broker section in [`.claude/skills/org-delegate/references/renga-error-codes.md`](../org-delegate/references/renga-error-codes.md)). `new_tab` / `focus_pane` are **not** on the broker surface, but this skill does not use them. The contract source of truth is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (ratified 2026-06-14). The design SoT is transport-lab `docs/design/ja-migration-plan.md` §5.2(ii). The default-renga procedure is unchanged (broker is additive). (**Two-frame note on "default" (Refs #604)**: "default `renga`" here means the **operational default** (broker live-run dogfood is not yet active until Epic #6 Issue G). Separately, the **code default** `tools/transport.py: DEFAULT_TRANSPORT` was flipped to `broker` in runtime 0.1.28 (Epic #586) — the ja generators and `transport.resolve()` render in this code frame, so the generated side displays "default `broker`". The two frames refer to different things (operational path vs. code constant) and do not contradict. The overview is in the "Transport (both rails)" section of the root `CLAUDE.md`.)

> **Premise**: this skill is invoked from the Secretary's cwd (= the repo root).
> The attention watcher itself is a `claude-org-runtime` console_scripts entrypoint, and the
> relative paths `--state-dir .state` / `--config .state/attention.json` must resolve from the
> repo root. The dispatcher pane's cwd is `.dispatcher`, so explicitly set `cwd="."` on
> `spawn_pane` to bind to the Secretary's cwd (= the repo root).
>
> **Design choice (sidecar)**: pane_id recording uses a sidecar JSON
> (`.state/attention_pane.json`) instead of extending the `.state/state.db` schema. This matches
> the same "auxiliary-process tracking" pattern as `.state/dashboard.pid` /
> `.state/attention_notified.json`, and avoids ripple effects on
> importer / writer / snapshotter / converter / drift_check. The attention watcher is an OS
> subprocess (not a Claude peer), so it has no peer_id, and dashboard surfacing is currently
> unnecessary (human judgment, 2026-05-17).

## Step 1: double-start check

Detecting a double-start requires looking at **both the sidecar presence and the live pane** (even
when the sidecar is absent, an orphaned `name="attention"` pane from a past manual spawn / crash
can still be live, and looking at the sidecar alone causes Step 3's
`spawn_pane(..., name="attention")` to fail with `[name_in_use]`).

1. Call `mcp__renga-peers__list_panes` and check whether a `name="attention"` / `role="attention"`
   pane is live.
2. Check whether `.state/attention_pane.json` exists:
   ```bash
   test -f .state/attention_pane.json && echo exists || echo absent
   ```
3. Branch:
   - **live pane present + sidecar present + sidecar pane_id matches the live pane** → already
     running normally. Report "the attention watcher is already running at pane id={N}. If you
     want to restart it, run `/org-attention-stop` first" and **abort**.
   - **live pane present + sidecar absent / pane_id mismatch** → orphaned pane or sidecar drift.
     Report the situation to the user with "clean up the orphan pane with
     `/org-attention-stop`, then retry" and **abort** (do not auto-close: the orphan's contents
     are unknown).
   - **live pane absent + sidecar present** → stale sidecar. Delete it and proceed to Step 2:
     ```bash
     rm .state/attention_pane.json
     ```
     Windows native: `del .state\attention_pane.json`.
   - **live pane absent + sidecar absent** → clean state. Proceed to Step 2.

## Step 2: place the config file (only if missing)

1. Check whether `.state/attention.json` exists:
   ```bash
   test -f .state/attention.json && echo exists || echo absent
   ```
2. **If missing**: copy the ja default template (`.state/` is gitignored and may not exist on a
   fresh clone, so run `mkdir` at the same time):
   ```bash
   mkdir -p .state
   cp tools/templates/attention.example.json .state/attention.json
   ```
   On Windows native (PowerShell) you can also use `copy`:
   ```powershell
   if (!(Test-Path .state)) { mkdir .state }
   copy tools\templates\attention.example.json .state\attention.json
   ```
3. **If already in place**: do not overwrite (respect the user's tuning). Proceed to Step 3.

## Step 3: split the dispatcher and start the watcher

Create a pane for the attention watcher on the right half (vertical split) of the dispatcher pane:

```
mcp__renga-peers__spawn_pane(
  target="dispatcher",
  direction="vertical",
  role="attention",
  name="attention",
  cwd=".",
  command="claude-org-runtime attention watch --state-dir .state --config .state/attention.json"
)
```

- `target="dispatcher"`: resolved via the stable name established at org-start Block A-1.
- `direction="vertical"`: dispatcher pane = left, attention pane = right.
- `cwd="."`: relative resolution is anchored at the Secretary's cwd (= the repo root) so `.state/`
  paths resolve correctly. Omitting it inherits the dispatcher's cwd (`.dispatcher`), making
  `.state` resolve to `.dispatcher/.state` and the watcher ends up looking at empty state.
- `name="attention"`: referenced by the later `/org-attention-stop` via
  `close_pane(target="attention")` or the recorded pane_id.
- Return value: text `"Spawned pane id=N."`. N is the attention watcher's pane_id.

**Failure branches**:
- `[split_refused]`: the dispatcher pane is below the split lower bound (MIN_PANE_WIDTH=20).
  Report "the dispatcher pane is too small to split. Shrink the secretary side or widen the
  terminal and retry" to the user and abort.
- `[pane_not_found]`: the dispatcher pane does not exist (org-start was not run, or dispatcher
  crashed). Report "dispatcher pane not found. Run `/org-start` first" to the user and abort.
- `[name_in_use]`: a live pane that Step 1's double-start check missed (a race where it
  re-appeared just before this call). Report "an attention pane came up in parallel just before
  this. Clean it up with `/org-attention-stop`" to the user and abort.
- Other `[<code>]`: see [`renga-error-codes.md`](../org-delegate/references/renga-error-codes.md).

## Step 4: startup health check (negative-signal detection for immediate crashes only)

`spawn_pane` success only guarantees up to "the shell came up and fired the command." If
`claude-org-runtime` is not installed / config is invalid / there's an import error and the
watcher process exits immediately, a stale pane_id ends up recorded in the sidecar and breaks all
downstream checks. On the other hand, **what the watcher prints on a healthy startup** is not
fixed by `claude-org-runtime`'s contract (an implementation that quietly enters the polling loop
and waits is also valid). Treating "wait for the startup banner" / "no output = fail" as the
criterion creates a path that **wrongly kills a healthy quiet start**. So this skill **only flags
explicit failure signals as failures**; anything else (empty output / unknown output) is treated
as "successful startup":

```
mcp__renga-peers__inspect_pane(target="attention", format="text", lines=60)
```

The inspect round trip itself (a few hundred ms) is enough for cases where the shell terminated
immediately to leave a prompt or error captured in the pty buffer. **Treat the startup as a
failure only if one of the following holds**:

- The output ends with an exposed shell prompt (`PS C:\...> ` / `$ ` / `% ` / `> ` at the tail)
  → the command exited immediately and returned to the shell.
- The output contains one of:
  - `command not found` / `is not recognized` / `not recognized as an internal or external command`
  - `ModuleNotFoundError` / `ImportError` / `Traceback (most recent call last)`
  - `[error]` / `[ERROR]` / `FATAL` / `fatal:`

**If none of the above is detected** (empty output / startup banner / polling wait / unknown lines
only, etc.) → **treat as successful startup** and proceed to Step 5. Do not introduce a fixed
sleep + re-inspect path (so as not to create a path that wrongly kills a healthy quiet start).

**On startup failure**:
1. `mcp__renga-peers__close_pane(target="<pane_id returned from spawn>")` to clean up the dead pane.
2. **Do not** write the sidecar.
3. Record `attention_watch_start_failed` in the journal:
   ```bash
   bash tools/journal_append.sh attention_watch_start_failed pane_id=<N> reason=immediate_exit
   ```
4. Report to the user: "the watcher exited immediately after startup (output excerpt: <inspect
   excerpt>). Verify the install with `claude-org-runtime --version`, and also check the syntax of
   `.state/attention.json` with
   `claude-org-runtime attention scan --state-dir .state --config .state/attention.json --dry-run --json`."
   Then abort.

## Step 5: record the pane_id in the sidecar

Write the parsed pane_id from the return value to `.state/attention_pane.json`:

```json
{
  "pane_id": "<N>",
  "name": "attention",
  "started_at": "<ISO8601 UTC>",
  "config_path": ".state/attention.json"
}
```

Save with the `Write` tool, overwriting (any pre-existing file was deleted in Step 1).

Append a single journal event line:

```bash
bash tools/journal_append.sh attention_watch_started pane_id=<N> config=.state/attention.json
```

On Windows native: `py -3 tools/journal_append.py attention_watch_started pane_id=<N> config=.state/attention.json`.

## Step 6: report

```
Started the attention watcher (pane id={N}, on the right side of the dispatcher).
Config: .state/attention.json
Run /org-attention-stop to stop it.
```

For the Windows notification center integration (`wsl-notify-send.exe`), per-OS backend behavior,
and troubleshooting, see [`docs/operations/attention-watch.md`](../../../docs/operations/attention-watch.md).
