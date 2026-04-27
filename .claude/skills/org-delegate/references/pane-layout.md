# Pane Layout Specification (renga-peers MCP)

renga pane / tab placement rules. Referenced by `org-start` and `org-delegate`.
Pane control happens via the `mcp__renga-peers__*` MCP tools (assumes renga 0.18.0+; all 14 tools, including `spawn_claude_pane` / `set_pane_identity`, are MCP-complete).

## Initial layout (after `renga --layout ops` plus Dispatcher / Curator launch)

The Lead (`secretary`) / Dispatcher / Curator come up in the same tab; Workers are also stacked into the same tab via splits.

```
Tab 1: ops (zero workers)
┌────────────────────┬────────────────────┐
│                    │                    │
│                    │       Lead         │
│                    │     (top half)     │
│                    │                    │
│                    ├──────────┬─────────┤
│                    │ Dispatcher  │ Curator │
│                    │          │         │
└────────────────────┴──────────┴─────────┘
```

> ※ In practice, the Lead pane is sometimes on the left and `dispatcher/curator` occupy the bottom half — initial layout details are entrusted to org-start. The point that matters here is "build the Worker zone via balanced splits from the dispatcher pane's rect".

## Placement rules

| Target | Operation | Notes |
|---|---|---|
| Dispatcher | Horizontally split the Lead pane and take the bottom half | `mcp__renga-peers__spawn_claude_pane(target="focused", direction="horizontal", role="dispatcher", name="dispatcher", cwd=".dispatcher", permission_mode="bypassPermissions", model="sonnet")` (org-start Step 2) |
| Curator | Vertically split the Dispatcher pane and take the right half | `mcp__renga-peers__spawn_claude_pane(target="dispatcher", direction="vertical", role="curator", name="curator", cwd=".curator", permission_mode="{default_permission_mode}")` (org-start Step 3) |
| Each Worker | **Balanced split**: dynamically pick target and direction from the current rect returned by `list_panes`, and stack into the same tab | See "Worker balanced split strategy" below for details. `mcp__renga-peers__spawn_claude_pane(target={target}, direction={direction}, role="worker", name="worker-{task_id}", cwd="{workers_dir}/{task_id}", permission_mode="{default_permission_mode}")` (org-delegate Step 3) |

> **Why we use `spawn_claude_pane`**: structured launch tool added in renga 0.18.0+. Passing `cwd` / `permission_mode` / `model` / `args[]` as structured fields makes renga internally compose `claude --permission-mode {mode} --dangerously-load-development-channels server:renga-peers ...`. The old method (feeding a `cd`-prefixed command string into `spawn_pane`) is **prohibited** (the cwd-changing prefix prevents renga's bare-`claude` auto-upgrade from firing, and `send_message`'s channel push fails to arrive — Lead → Dispatcher / Dispatcher → Worker instructions stop working entirely). Only the Lead is started as a bare `claude` from `ops.toml` and relies on auto-upgrade.

## Worker balanced split strategy

### Why balanced split is necessary

renga splits each target pane 50/50. Going below `MIN_PANE_WIDTH = 20` / `MIN_PANE_HEIGHT = 5` causes a `[split_refused]` rejection (investigation: `<workers_dir>/renga-split-inv/findings.md`).

With a fixed target or an ordinal-`k`-based lookup table, the cumulative halving of dispatcher width and re-dispatch after a Worker closed in the middle made the assumed layout diverge from the actual layout, easily inducing `split_refused`.

The current design uses each pane's **rect (`x / y / width / height`, in cell units)** returned by `mcp__renga-peers__list_panes` and **picks target and direction dynamically from the current layout**. It is robust to shifting Worker retirement order and mid-flight closures, has no fixed "N parallel cap", continues splitting as far as terminal size and the MIN_PANE constraint allow, and auto-escalates when the limit is hit.

### Algorithm

The Dispatcher launching a new Worker runs the following before calling `spawn_pane`. See SKILL.md Step 3-1 for the detailed decision steps (Claude interprets the result text of `list_panes` and runs the logic).

1. Get all panes and their attributes (id / name / role / focused / x / y / width / height) via `mcp__renga-peers__list_panes`
2. **Candidate set**: panes with `role ∈ {worker, dispatcher, secretary}` (curator is always excluded)
3. **Filter candidates**:
   - **Maintain dispatcher-curator adjacency**: keep dispatcher only when it is rect-adjacent (defined below) to curator. The dispatcher-curator adjacency is an organizational premise. Splitting dispatcher could break the adjacency, so dispatchers already non-adjacent are removed from candidates
   - **Lead pane protection**: secretary is a candidate only when post-split new pane width `new_w >= 125` **and** new pane height `new_h >= 45`. Insurance clause; rarely fires in practice. Width passing alone is not enough; height must also pass
4. **Direction decision** (from each candidate's aspect ratio):
   - `width > height * 2` → `vertical` (left/right split)
   - Otherwise → `horizontal` (top/bottom split)
   - Terminal cells are tall (height:width ≈ 2:1), so per-character `width = 2 * height` is roughly square physically. `width > height * 2` is a reasonable "physically wide" criterion
5. **MIN_PANE constraint**: remove candidates whose post-split new size `(new_w, new_h)` does not satisfy `new_w >= 20` and `new_h >= 5`
   - vertical split: `(new_w, new_h) = (floor(width / 2), height)`
   - horizontal split: `(new_w, new_h) = (width, floor(height / 2))`
6. **Target selection**: pick the candidate with the largest "new size in the split-axis direction" (`new_w` for vertical, `new_h` for horizontal). Tie-break by ascending pane id at that moment (reproducible within a snapshot; cross-session stability is not guaranteed)
7. **Empty candidate set → escalate**: escalate to the Lead via the `SPLIT_CAPACITY_EXCEEDED` path in SKILL.md Step 3-1c (do not issue `spawn_pane`; cancel only the one Worker dispatch and continue the Dispatcher main loop)

### Definition of rect adjacency

Rects `A, B` are adjacent if they satisfy one of:

- **Left-right adjacency**: `A.x + A.width == B.x` or `B.x + B.width == A.x`, and y intervals overlap (`max(A.y, B.y) < min(A.y + A.height, B.y + B.height)`)
- **Top-bottom adjacency**: `A.y + A.height == B.y` or `B.y + B.height == A.y`, and x intervals overlap (`max(A.x, B.x) < min(A.x + A.width, B.x + B.width)`)

renga's cell coordinates are integers, so judgment uses exact equality with no tolerance.

### Initial state and typical behavior

With zero workers, the only candidate is normally `dispatcher` (secretary is normally excluded by the `new_w >= 125` / `new_h >= 45` condition or the adjacency condition; curator is always excluded). The dispatcher is typically wide, so it gets a vertical split, and the first Worker zone is created on the right side of the dispatcher.

After that, among the existing panes the one with the largest post-split size is selected, and direction alternates naturally based on the rect — yielding a near-balanced placement. Fixed 4-parallel / 8-parallel diagrams have no meaning (placement is dynamic), so they are omitted.

### Edge cases / operational notes

- **Re-dispatch after a Worker closed mid-flight**: the issue with the old k-table approach — "filling a closed slot diverges from the table assumption" — does not arise with the rect-based approach. The target is always picked from the actual layout, so judgment matches renga's layout tree
- **`spawn_pane` errors**: `[split_refused]` / `[pane_not_found]` are returned in the MCP result text. Follow the procedure in `references/renga-error-codes.md` to escalate Curator → Lead (same policy as the old design)
- **Race**: if other Workers are added or removed between `list_panes` and `spawn_pane`, target inconsistency surfaces as `[pane_not_found]`. Existing error-handling paths absorb it
- **Responsibility for target selection**: the calculation is done by the Dispatcher based on `list_panes` rects. The Lead only passes a task_id in the DELEGATE message; it does not specify the target

## Operational notes

- **Place every pane in the same tab**: renga's `list_panes` / `focus_pane` / `send_message` / `inspect` (CLI) can only handle panes in the currently focused tab, so stack the Dispatcher, Curator, and all Workers into the same tab via splits. Putting Workers in separate tabs via `new_tab` makes them unaddressable from the Dispatcher (discovered 2026-04-20; resolution in renga itself is suisya-systems/renga#71)
- **Naming convention**:
  - Lead → `secretary`
  - Dispatcher → `dispatcher`
  - Curator → `curator`
  - Worker → `worker-{task_id}` (task_id is a unique identifier in kebab-case)
  - **renga-peers target resolution rule**: all-digit names are interpreted as ids, so always include letters in the name (`worker-1` is OK; `1` is treated as an id and is therefore NG)
- **Role labels (`role`)**: 4 kinds — `secretary` / `dispatcher` / `curator` / `worker`
  - The `role` field is available in `list_panes` output and can be used for organizational state aggregation and target selection in balanced splits
- **On Worker completion**:
  1. The Lead asks the Dispatcher with `CLOSE_PANE`
  2. The Dispatcher explicitly disposes the pane via `mcp__renga-peers__close_pane(target="worker-{task_id}")`
     (renga removes the pane → emits `Event::PaneExited` once → it disappears from `list_panes`.
     `[pane_not_found]` / `[pane_vanished]` are skipped as "already closed")
- **Stop order on org-suspend**: Worker → Dispatcher → Curator (all disposed via `mcp__renga-peers__close_pane`. Only when closing the very last pane does `[last_pane]` come back; let that pane self-`exit`)

## spawn_pane direction convention

renga's split direction is defined as follows (same as the legacy `renga split --direction`):
- `direction="vertical"` = left/right split (existing pane = left, new pane = right)
- `direction="horizontal"` = top/bottom split (existing pane = top, new pane = bottom)

## Future features / upstream tracking

- **Pane lifecycle subscription**: currently used together with the `renga events` CLI (Dispatcher monitoring loop, etc.). Once `mcp__renga-peers__poll_events` lands via upstream suisya-systems/renga#117 / renga PR #120, switch to MCP in a follow-up issue
- **Screen scraping**: used together with the `renga inspect` CLI. Once `mcp__renga-peers__inspect_pane` lands via upstream suisya-systems/renga#116 / renga PR #121, switch to MCP in a follow-up issue
- **Raw key send**: used together with the `renga send --text` CLI (development-channel Enter / permission-mode toggle Shift+Tab, etc.). The `send_keys` MCP is being designed in upstream suisya-systems/renga#118; switch to MCP in a follow-up issue once landed
- Ratio specification like `spawn_pane --ratio 0.2` (currently fixed at 50/50)
- renga-side automatic target selection like `spawn_pane --target-largest` / `--direction auto` (currently computed by the Dispatcher from `list_panes` rects; if delegated to upstream, the balanced-split logic could fold into the MCP side)
