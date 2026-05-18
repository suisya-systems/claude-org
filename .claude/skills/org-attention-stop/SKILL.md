---
name: org-attention-stop
description: >
  Stop the attention watcher pane started by `/org-attention-start`. It reads the pane_id recorded
  in `.state/attention_pane.json`, closes the pane via `mcp__renga-peers__close_pane`, and deletes
  the sidecar.
  Triggered by "stop attention", "halt notification monitoring", "shut down the watcher", etc.
effort: low
allowed-tools:
  - Read
  - Bash(rm:*)
  - Bash(del:*)
  - Bash(bash tools/journal_append.sh:*)
  - Bash(py -3 tools/journal_append.py:*)
  - mcp__renga-peers__*
---

# org-attention-stop: stop the attention watcher

Close the watcher pane started by [`/org-attention-start`](../org-attention-start/SKILL.md) and
clear the sidecar (`.state/attention_pane.json`).

## Step 1: check sidecar and live-pane state

1. Call `mcp__renga-peers__list_panes`. If a live pane with `name="attention"` or
   `role="attention"` exists, record its pane_id (**check both name and role**: an orphaned pane
   from a manual start may have only the role without a name).
2. If `.state/attention_pane.json` can be opened with `Read`, read `pane_id` from it. If it does
   not exist, skip.
3. Branch:
   - **sidecar present** → go to 2-a.
   - **sidecar absent + orphan pane detected** → go to 2-b.
   - **sidecar absent + no orphan pane** → report "the attention watcher is already stopped" and
     exit.

## Step 2: close the pane

### 2-a: close using the recorded pane_id

```
mcp__renga-peers__close_pane(target="<sidecar pane_id>")
```

- On success: text `"Closed pane id=N."` returns.
- `[pane_not_found]` / `[pane_vanished]`: already closed. The sidecar is stale. Proceed to Step 3.
- `[last_pane]`: the attention pane was the tab's only remaining pane (does not normally happen —
  dispatcher / secretary should still be alive). Report the situation to the user and abort
  (defer to manual handling).

If the "attention pane visible in list_panes" obtained in Step 1 does not match the sidecar's
pane_id, **close using the sidecar's id first**, then re-fetch `list_panes`. If something
remains, proceed to 2-b (extra cleanup for drift / orphans).

### 2-b: cleaning up an orphan pane (no sidecar / drift)

Close using the **pane_id (the numeric id, not the name)** obtained from `list_panes` in Step 1:

```
mcp__renga-peers__close_pane(target="<numeric pane_id from list_panes>")
```

Do not use a name target like `target="attention"`: it would not hit an orphan pane that has only
the role and no name. Treat `[pane_not_found]` / `[pane_vanished]` as skip.

## Step 3: delete the sidecar

```bash
rm -f .state/attention_pane.json
```

Windows native: `del .state\attention_pane.json` (already-deleted is harmless — suppress with
`2>nul` etc.).

Append a single journal event line:

```bash
bash tools/journal_append.sh attention_watch_stopped pane_id=<N>
```

On Windows native: `py -3 tools/journal_append.py attention_watch_stopped pane_id=<N>`.

## Step 4: report

```
Stopped the attention watcher (pane id={N}).
Run /org-attention-start to start it again.
```

If there was no sidecar and no orphan pane:

```
The attention watcher is already stopped.
```
