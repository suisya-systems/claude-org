# Pane Layout Specification (renga-peers MCP)

Pane/tab layout rules for `renga`. Referenced by `org-start` and `org-delegate`.
Pane control is handled through the `mcp__renga-peers__*` MCP tools (requires renga 0.18.0+, with all 14 tools including `spawn_claude_pane` / `set_pane_identity` available through MCP).

## Initial layout (result of `renga --layout ops` + after starting Dispatcher and Curator)

The policy is to start the Lead (`secretary`), Dispatcher, and Curator in the same tab, then keep stacking Workers as splits within that same tab.

```
Tab 1: ops (ワーカー 0 人)
┌────────────────────┬────────────────────┐
│                    │                    │
│                    │     Secretary      │
│                    │     (上半分)       │
│                    │                    │
│                    ├──────────┬─────────┤
│                    │ Dispatcher  │ Curator │
│                    │          │         │
└────────────────────┴──────────┴─────────┘
```

> Note: in practice, there is also a layout where `secretary` is on the left and `dispatcher/curator` occupy the bottom half; the exact initial layout is left to `org-start`. What matters in this document is that the system builds the worker zone dynamically using balanced splits with role priority over the four candidate roles: `secretary / curator / worker / dispatcher` (see the algorithm section below).

## Layout rules

| Target | Operation | Notes |
|---|---|---|
| Dispatcher | Horizontally split the Lead pane and use the bottom half | `mcp__renga-peers__spawn_claude_pane(target="focused", direction="horizontal", role="dispatcher", name="dispatcher", cwd=".dispatcher", permission_mode="bypassPermissions", model="sonnet")` (org-start Step 2) |
| Curator | Vertically split the Dispatcher pane and use the right half | `mcp__renga-peers__spawn_claude_pane(target="dispatcher", direction="vertical", role="curator", name="curator", cwd=".curator", permission_mode="auto")` (org-start Step 3) |
| Each Worker | **balanced split**: dynamically choose `target` and `direction` from the current rects returned by `list_panes`, then stack within the same tab | See the "Worker balanced split strategy" section below. `mcp__renga-peers__spawn_claude_pane(target={target}, direction={direction}, role="worker", name="worker-{task_id}", cwd="{workers_dir}/{task_id}", permission_mode="auto")` (org-delegate Step 3) |

> **Why use `spawn_claude_pane`**: this is the structured launch tool added in renga 0.18.0+. When `cwd` / `permission_mode` / `model` / `args[]` are passed as structured fields, renga internally composes `claude --permission-mode {mode} --dangerously-load-development-channels server:renga-peers ...`. The old method of passing a `command` string with a `cd` prefix into `spawn_pane` is **forbidden** (if a cwd-change prefix is present, renga's bare-`claude` auto-upgrade does not trigger, and channel push via `send_message` stops working. Instructions from Lead to Dispatcher and from Dispatcher to Worker stop working entirely). Only the Secretary is launched as bare `claude` from `ops.toml` and relies on auto-upgrade.

## Worker balanced split strategy

### Why balanced split is necessary

renga splits the target pane 50/50 on each split. If either side falls below the minimums `MIN_PANE_WIDTH = 20` or `MIN_PANE_HEIGHT = 5`, the split is rejected with `[split_refused]` (investigation: `<workers_dir>/renga-split-inv/findings.md`).

With a fixed target or an ordinal `k`-based lookup table, cumulative halving of the Dispatcher width and redispatch after Workers close caused the assumed layout to diverge from the actual layout, triggering early `split_refused`.

The current design uses each pane's **rect information (`x / y / width / height`, in cells)** returned by `mcp__renga-peers__list_panes`, and **dynamically selects target and direction from the current layout**. It is robust to variation in Worker retirement order and mid-run closes, has no fixed "max N parallelism", continues splitting as long as terminal size and MIN_PANE constraints allow, and automatically escalates when it reaches capacity.

### Algorithm

The balanced split decision logic (target/direction selection, MIN_PANE constraints, Secretary guard, role-priority sorting, rect adjacency checks, and `split_capacity_exceeded` detection) is **defined by the helper in `claude-org-runtime` as the source of truth**. The Dispatcher takes the snapshot from `mcp__renga-peers__list_panes` and the task JSON, then calls one of the following and follows the returned action plan (`spawn` / `after_spawn` / `escalate` / `state_writes` / `status`) to execute `spawn_claude_pane` or escalate:

- CLI (standard operational entrypoint): `claude-org-runtime dispatcher delegate-plan --task-json ... --panes-json ... --state-dir ... [--template-repo ...] [--locale-json ...]`. For Dispatcher-side procedure, the primary reference is the delegate-plan helper section in `.dispatcher/CLAUDE.md`
- Library: `build_plan(...)` in the `claude_org_runtime.dispatcher.runner` module (full action plan), and `choose_split(panes)` (low-level helper when only target/direction is needed)

For constant values (`MIN_PANE_WIDTH` / `MIN_PANE_HEIGHT` / `SECRETARY_MIN_WIDTH` / `SECRETARY_MIN_HEIGHT` / role-priority map), evaluation order, and the exact definition of rect adjacency, the **primary reference is the `claude_org_runtime.dispatcher.runner` module itself** (`_ROLE_PRIORITY` / `MIN_PANE_*` / `SECRETARY_MIN_*` / `choose_split()` / `rect_adjacent()`). Constant prose was removed from this document because drift between runtime and docs causes opaque failures such as `[split_refused]` (Issue #307 cleanup).

If there are no candidates, the helper returns `status="split_capacity_exceeded"` and `escalate.send_message(to_id="secretary", ...)`. The Dispatcher does not issue `spawn_claude_pane`, stops dispatch for that one Worker only, and continues the main monitoring loop (see `SKILL.md` Step 3-1c).

### Verification trace (Issue #307 scenario, reference)

This is a manual trace table showing `choose_split` behavior when given the immediate post-layout state `secretary 280×43 / dispatcher 140×43 / curator 140×43` (terminal ≈ 280×86, assuming `org-start` has just performed Secretary horizontal split then Dispatcher vertical split). **Canonical behavior is the runtime SoT**. If values in this doc differ from runtime behavior, trust the runtime.

| spawn | Selected role | direction | Intuition |
|---|---|---|---|
| 1st | secretary | vertical | Secretary has top role priority as long as it still satisfies splitable size |
| 2nd | curator | vertical | Secretary drops out due to the `SECRETARY_MIN_WIDTH` guard; Curator is selected as the next-highest priority |
| 3rd | curator | horizontal | Role priority is strict primary, so Curator continues until it drops below MIN_PANE |

After Curator drops out for violating MIN_PANE, selection flows to Workers at priority 2. For the design rationale for putting Dispatcher last (avoid repeatedly halving the viewport of the actively monitored pane; Curator is mostly idle under `/loop 30m /org-curate`), see the `_ROLE_PRIORITY` comment in `runner.py`.

### Edge cases / operational notes

- **Redispatch after a Worker closes mid-run**: the old k-table method had the problem that compacting a closed slot diverged from table assumptions. That does not happen with rect-based selection. Target selection always comes from the actual layout, so the decision stays aligned with renga's layout tree
- **`spawn_claude_pane` errors**: `[split_refused]` / `[pane_not_found]` are returned in the MCP result text. Escalate Curator → Lead using the procedure in `references/renga-error-codes.md` (same policy as the old design)
- **Races**: if other Workers are added or removed between `list_panes` and `spawn_claude_pane`, target mismatch surfaces as `[pane_not_found]`. The existing error-handling path absorbs this
- **Responsibility for target selection**: the Dispatcher computes this from `list_panes` rects. The Lead only needs to pass `task_id` in the DELEGATE message and does not specify a target

## Operational notes

- **Place all panes in the same tab**: renga's `list_panes` / `focus_pane` / `send_message` / `inspect` (CLI) currently operate only on panes in the focused tab, so Dispatcher, Curator, and all Workers are stacked as splits within the same tab. If Workers are placed in separate tabs via `new_tab`, they stop being addressable from the Dispatcher side (confirmed 2026-04-20; upstream fix tracked in `suisya-systems/renga#71`)
- **Naming convention**:
  - Lead → `secretary`
  - Dispatcher → `dispatcher`
  - Curator → `curator`
  - Worker → `worker-{task_id}` (`task_id` is a unique kebab-case identifier)
  - **renga-peers target resolution rule**: a name made entirely of digits is interpreted as an id, so names must always include letters (`worker-1` is OK; `1` is invalid because it is treated as an id)
- **Role labels (`role`)**: four values: `secretary` / `dispatcher` / `curator` / `worker`
  - The `role` field is available in `list_panes` output and can be used for organization-state aggregation and balanced-split target selection
- **When a Worker completes**:
  1. The Lead asks the Dispatcher to `CLOSE_PANE`
  2. The Dispatcher explicitly destroys the pane with `mcp__renga-peers__close_pane(target="worker-{task_id}")`
     (renga removes the pane → emits `Event::PaneExited` once → the pane also disappears from `list_panes`.
     `[pane_not_found]` / `[pane_vanished]` are skipped as "already closed")
- **Shutdown order for `org-suspend`**: Workers → Dispatcher → Curator (all destroyed with `mcp__renga-peers__close_pane`. Only when closing the final remaining pane does `[last_pane]` return, so that pane must `exit` on its own)

## split direction conventions

renga split directions are defined as follows (same for `spawn_pane` and `spawn_claude_pane`):
- `direction="vertical"` = left/right split (existing pane = left, new pane = right)
- `direction="horizontal"` = top/bottom split (existing pane = top, new pane = bottom)

## Future features / upstream tracking

- Ratio support for `spawn_pane` / `spawn_claude_pane`, such as `--ratio 0.2` (currently fixed at 50/50)
- renga-side automatic target selection such as `--target-largest` / `--direction auto` (currently computed by the Dispatcher from `list_panes` rects. If moved upstream, the balanced split logic can be collapsed into the MCP side)
