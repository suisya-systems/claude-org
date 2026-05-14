# Pane Layout Specification (renga-peers MCP)

renga pane / tab layout rules. Referenced by `org-start` and `org-delegate`.
Pane control goes through the `mcp__renga-peers__*` MCP tools (renga 0.18.0+ required; all 14 tools including `spawn_claude_pane` / `set_pane_identity` are available via MCP).

## Initial layout (result of `renga --layout ops` plus Dispatcher/Curator startup)

The Secretary (`secretary`) / Dispatcher / Curator all come up in the same tab, and Workers are stacked into the same tab via splits.

```
Tab 1: ops (0 workers)
┌────────────────────┬────────────────────┐
│                    │                    │
│                    │     Secretary      │
│                    │     (top half)     │
│                    │                    │
│                    ├──────────┬─────────┤
│                    │ Dispatcher  │ Curator │
│                    │          │         │
└────────────────────┴──────────┴─────────┘
```

> Note: in practice `secretary` may sit on the left while `dispatcher/curator` occupy the bottom half — the precise initial layout is delegated to org-start. What matters in this document is that "we dynamically grow the Worker zone via a role-priority-aware balanced split whose candidates are the four roles `secretary / curator / worker / dispatcher`" (see the algorithm section below for details).

## Placement rules

| Target | Operation | Notes |
|---|---|---|
| Dispatcher | Horizontal split of the Secretary pane, taking the bottom half | `mcp__renga-peers__spawn_claude_pane(target="focused", direction="horizontal", role="dispatcher", name="dispatcher", cwd=".dispatcher", permission_mode="bypassPermissions", model="sonnet")` (org-start Block A-1) |
| Curator | Vertical split of the Dispatcher pane, taking the right half | `mcp__renga-peers__spawn_claude_pane(target="dispatcher", direction="vertical", role="curator", name="curator", cwd=".curator", permission_mode="auto")` (org-start Block A-2) |
| Each Worker | **balanced split**: dynamically pick target and direction from the current rects returned by `list_panes`, and stack into the same tab | See the "Worker balanced split strategy" section below. `mcp__renga-peers__spawn_claude_pane(target={target}, direction={direction}, role="worker", name="worker-{task_id}", cwd="{workers_dir}/{task_id}", permission_mode="auto")` (org-delegate Step 3) |

> **Why use `spawn_claude_pane`**: it is the structured launch tool added in renga 0.18.0+. When you pass `cwd` / `permission_mode` / `model` / `args[]` as structured fields, renga internally synthesizes `claude --permission-mode {mode} --dangerously-load-development-channels server:renga-peers ...`. The old approach (feeding a `cd`-prefixed command string into `spawn_pane`) is **forbidden** — a cwd-changing prefix prevents renga's bare-`claude` auto-upgrade from firing, so `send_message` channel pushes never arrive. Instructions from Secretary→Dispatcher and Dispatcher→Worker stop flowing entirely. Only the Secretary is launched as bare `claude` from `ops.toml` and relies on auto-upgrade.

## Worker balanced split strategy

### Why balanced split is necessary

Each renga split divides the target pane 50/50. If the result drops below the lower bounds `MIN_PANE_WIDTH = 20` / `MIN_PANE_HEIGHT = 5`, the split is rejected with `[split_refused]` (investigation: `<workers_dir>/renga-split-inv/findings.md`).

With a fixed target or an ordinal `k`-based lookup table, the cumulative halving of the dispatcher's width, or re-dispatch after a worker closes mid-flight, caused the assumed layout to diverge from the actual one and triggered `[split_refused]` early.

The current design uses the **rect info (`x / y / width / height`, in cell units)** for each pane returned by `mcp__renga-peers__list_panes`, and **dynamically picks target and direction from the current layout**. It is robust against jitter in worker retirement order and mid-flight closure, has no fixed "N parallel cap," keeps splitting as long as the terminal size and MIN_PANE constraints allow, and auto-escalates when the limit is hit.

### Algorithm

The balanced-split decision logic (target / direction selection, MIN_PANE constraint, secretary safeguard, role-priority sort, rect-adjacency check, `split_capacity_exceeded` detection) is **owned by the `claude-org-runtime` helper as the SoT**. The dispatcher feeds it a `mcp__renga-peers__list_panes` snapshot and the task JSON via one of the entry points below, and then executes `spawn_claude_pane` / escalate according to the returned action plan (`spawn` / `after_spawn` / `escalate` / `state_writes` / `status`):

- CLI (the standard operational entry point): `claude-org-runtime dispatcher delegate-plan --task-json ... --panes-json ... --state-dir ... [--template-repo ...] [--locale-json ...]`. The dispatcher-side procedure has its primary source in the delegate-plan helper section of `.dispatcher/CLAUDE.md`.
- Library: `build_plan(...)` (the full action plan) and `choose_split(panes)` (a low-level helper for when you only need target / direction) in the `claude_org_runtime.dispatcher.runner` module.

The constant values (MIN_PANE_WIDTH / MIN_PANE_HEIGHT / SECRETARY_MIN_WIDTH / SECRETARY_MIN_HEIGHT / role-priority map), the order of checks, and the exact definition of rect adjacency are sourced from the **`claude_org_runtime.dispatcher.runner` module itself** (`_ROLE_PRIORITY` / `MIN_PANE_*` / `SECRETARY_MIN_*` / `choose_split()` / `rect_adjacent()`). The prose values were removed from this document because doc/runtime drift was a cause of mysterious `[split_refused]`-style failures (Issue #307 cleanup).

When there are no candidates, the helper returns `status="split_capacity_exceeded"` and an `escalate.send_message(to_id="secretary", ...)`. The dispatcher does not issue `spawn_claude_pane`, cancels the dispatch for just that one worker, and keeps the main monitor loop running (see `SKILL.md` Step 3-1c).

### Verification trace (Issue #307 scenario, reference)

A hand-traced reference table of `choose_split` behavior for the layout `secretary 280×43 / dispatcher 140×43 / curator 140×43` immediately after startup (terminal ≈ 280×86, assumed to be right after org-start's secretary horizontal split → dispatcher vertical split). **The canonical values live in the runtime SoT**. If the doc disagrees with the runtime's actual behavior, trust the runtime.

| spawn | selected role | direction | intuitive rationale |
|---|---|---|---|
| 1st | secretary | vertical | while secretary still satisfies the splittable-size requirement, role priority puts it first |
| 2nd | curator | vertical | secretary drops out under the SECRETARY_MIN_WIDTH guard, so the next-priority curator is picked |
| 3rd | curator | horizontal | because role priority is strict primary, curator is picked repeatedly until it falls below MIN_PANE |

Once curator falls below MIN_PANE and drops out, the flow moves to the priority-2 worker pool. The design intent of putting the dispatcher last (to avoid halving the viewport of an active monitoring pane often, and because the curator is mostly idle under `/loop 30m /org-curate`) is documented in the `_ROLE_PRIORITY` comment in runner.py.

### Edge cases / operational notes

- **Re-dispatch after a worker closes mid-flight**: the old k-table issue of "compacting closed slots diverges from the table's assumptions" cannot occur in the rect-based model. Because the target is always picked from the actual layout, the decision is always consistent with renga's layout tree.
- **`spawn_claude_pane` errors**: `[split_refused]` / `[pane_not_found]` come back in the MCP result text. Escalate via Curator → Secretary per the procedure in `references/renga-error-codes.md` (same policy as the old design).
- **Race**: if other workers come and go between `list_panes` and `spawn_claude_pane`, the target mismatch surfaces as `[pane_not_found]`. It is absorbed by the existing error-handling path.
- **Responsibility for target selection**: the dispatcher computes it from `list_panes` rect data. The Secretary only needs to pass task_id in the DELEGATE message and does not specify target.

## Operational notes

- **Keep all panes in the same tab**: renga's `list_panes` / `focus_pane` / `send_message` / `inspect` (CLI) can only touch panes in the currently-focused tab, so stack Dispatcher, Curator, and all Workers as splits in the same tab. Putting a worker in a separate tab via `new_tab` makes it unaddressable from the Dispatcher (discovered 2026-04-20; upstream fix tracked at suisya-systems/renga#71).
- **Naming conventions**:
  - Secretary → `secretary`
  - Dispatcher → `dispatcher`
  - Curator → `curator`
  - Worker → `worker-{task_id}` (task_id is a kebab-case unique identifier)
  - **renga-peers target resolution rule**: an all-digit name is interpreted as an id, so the name must contain at least one letter (`worker-1` is OK; `1` would be treated as an id, so it's not).
- **Role labels (`role`)**: four values — `secretary` / `dispatcher` / `curator` / `worker`.
  - The `list_panes` output exposes a `role` field, which is useful for aggregating org state and for picking targets in balanced split.
- **When a worker finishes**:
  1. The Secretary asks the Dispatcher for `CLOSE_PANE`.
  2. The Dispatcher explicitly tears down the pane with `mcp__renga-peers__close_pane(target="worker-{task_id}")`.
     (renga removes the pane → `Event::PaneExited` is emitted once → it disappears from `list_panes` as well.
     `[pane_not_found]` / `[pane_vanished]` is treated as "already closed" and skipped.)
- **Stop order at org-suspend time**: Worker → Dispatcher → Curator (all torn down via `mcp__renga-peers__close_pane`. Only when closing the last remaining pane do you get `[last_pane]` back, and that pane has to `exit` itself).

## Split direction conventions

renga's split directions are defined as follows (shared by `spawn_pane` / `spawn_claude_pane`):
- `direction="vertical"` = left/right split (existing pane = left, new pane = right)
- `direction="horizontal"` = top/bottom split (existing pane = top, new pane = bottom)

## Future features / upstream tracking

- A ratio argument such as `--ratio 0.2` for `spawn_pane` / `spawn_claude_pane` (currently fixed at 50/50).
- Renga-side automatic target selection such as `--target-largest` / `--direction auto` (currently the dispatcher computes it from `list_panes` rects; if this can be pushed upstream, the balanced-split logic can be collapsed into MCP).
