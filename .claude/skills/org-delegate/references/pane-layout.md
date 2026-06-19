# Pane Layout Specification (org-broker MCP)

Pane / tab layout rules. Referenced by `org-start` and `org-delegate`.
Pane control goes through the `mcp__org-broker__*` MCP tools (the pane control tool family including `spawn_claude_pane` / `set_pane_identity` is complete via MCP).

> **Transport (transport) dual system -- default `broker` / opt-in `renga`**: The `mcp__org-broker__*` calls in this file are written for **default `broker`** (no `ORG_TRANSPORT` set) and can be followed as-is (default behavior). With `ORG_TRANSPORT=renga` (opt-in, rollback-capable), the MCP server name becomes `renga-peers` and tool **fully-qualified names are mechanically rewritten from `mcp__org-broker__*` -> `mcp__renga-peers__*`** (argument shape and semantics are identical, so the logic of balanced split judgment / operation is unchanged). Only the points where the procedure depends on the transport are noted alongside renga:
>
> - **spawn ceremony (folder-trust approval + dev-channel sidecar approval, 2 steps)**: As described in "Why use `spawn_claude_pane`" below, default broker injects `--mcp-config <broker>` at launch and mechanically approves Claude Code's **folder-trust prompt** with `send_keys(enter=true)` **plus**, for push-primary, the channel sidecar is loaded with `--dangerously-load-development-channels server:org-broker-channel` and the dev-channel approval prompt (spawn-flow 3-3b) is mechanically approved with `send_keys(enter=true)` (folder-trust + dev-channel 2-step approval. This is an addition to, not a replacement of, the folder-trust flow ratified in §5/§8.5. Design: transport-lab `docs/design/broker-native-roles.md` §9.5). Note that the broker spawn helper internally assembles the interactive-TUI argv behind a default-deny billing-neutral guard. With `ORG_TRANSPORT=renga` (opt-in), inject `--dangerously-load-development-channels server:renga-peers` and approve the "Load development channel?" prompt with Enter, a 1-step ceremony.
> - **Receive model (push-primary = `claude/channel` / pull fallback)**: Default broker is designed **push-primary** (runtime push-first 0.1.24+, broker-native-roles.md §9), where the channel sidecar (`server:org-broker-channel`) co-resident in each pane injects the body into an idle session via `notifications/claude/channel`. pull (pane-local nudge + `check_messages`) is the fallback layer, and its receive uses each role's active cadence poll as the canonical path (the nudge does not wake idle, so it is not load-bearing; §9.6 read-through table). With `ORG_TRANSPORT=renga` (opt-in), `send_message` becomes an in-band push of `<channel source="renga-peers" …>`. The layout operations themselves (`list_panes` / `spawn_claude_pane` / `close_pane`, etc.) follow the same logic in both, only the tool names change between `mcp__org-broker__*` <-> `mcp__renga-peers__*`.
> - **Error branches (default = with broker extension codes)**: In addition to shared codes (`split_capacity_exceeded` / `[split_refused]` / `[cwd_invalid]`, etc.), default broker may return `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]`. For the full list, see the broker section of [`.claude/skills/org-delegate/references/renga-error-codes.md`](renga-error-codes.md). Under `ORG_TRANSPORT=renga`, broker-specific codes do not occur.
>
> `new_tab` / `focus_pane` are **not** in the broker surface (intentional exclusion) -- however, the balanced split in this document is designed to use only same-tab splits and does not use `new_tab`, so the absence has no impact on broker. The canonical contract is [`docs/contracts/backend-interface-contract.md`](../../../../docs/contracts/backend-interface-contract.md) Surface 8 (ratified 2026-06-14. The additive amendment S3 for push-primary is ratified (2026-06-15), existing ratified body unchanged), design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary redesign) / `docs/design/ja-migration-plan.md` §5.2(ii). Broker actual run (dogfood) is in Epic #6 Issue G scope and is not the default path for this file.

## Initial layout (after Dispatcher / Curator startup)

In broker, each pane launches in a **tmux detached independent session** (POSIX / WSL2, named `spike-<pid>-<seq>` on the dedicated socket `claude-org-spike`) or a **separate WezTerm GUI window** (Windows, `isolated_session=False`). The Secretary (`secretary`) is a **logical pane** with no actual adapter pane (bookkeeping entry, `register_logical_pane`) and runs as-is in the human's hand-side terminal where the org was started. Therefore, the "visual tiling that arranges multiple panes on one screen" like in renga **does not currently manifest** (broker-spawned child panes do not show on the human's screen by default, and live observation goes through the `tmux -L claude-org-spike attach -r -t spike-<pid>-<seq>` per-session attach path. Unification into a single session = single-screen view is design-confirmed but **not landed yet**).

That said, **the geometry / role-priority balanced split scheduling itself runs transport-neutral by contract** -- `list_panes` geometry is REQUIRED in contract Surface 1.5, and the balanced split is load-bearing in Surface 2.2 ([`docs/contracts/backend-interface-contract.md`](../../../../docs/contracts/backend-interface-contract.md)), so it is retained backend-independent. The "role-priority-aware dynamic worker zone generation whose candidates are the four roles `secretary / curator / worker / dispatcher`" determined by the balanced split (see the algorithm section below for details) is a scheduling order and works the same way without visual tiling. The visual-layout ASCII diagrams (renga-side single-screen tiling) do not correspond to reality on the broker side and are omitted.

> **Design SoT note**: The primary design SoT for the absence of visual tiling and for single-session unification (single-screen view) is transport-lab (`docs/design/broker-native-roles.md` §9 / §8.2 / §3.4, `docs/design/ja-migration-plan.md` §5 / §8), not present locally in this repo. The secondary reference inside this repo is [`docs/operations/broker-dogfood-runbook.md`](../../../../docs/operations/broker-dogfood-runbook.md) §8 (Observability -- attach paths to running orgs. Describes detached independent sessions / logical Secretary / unlanded single-session unification).

## Placement rules

| Target | Operation | Notes |
|---|---|---|
| Dispatcher | Horizontal split of the Secretary pane, taking the bottom half | `mcp__org-broker__spawn_claude_pane(target="focused", direction="horizontal", role="dispatcher", name="dispatcher", cwd=".dispatcher", permission_mode="bypassPermissions", model="sonnet")` (org-start Block A-1) |
| Curator (on-demand only) | Vertical split of the Dispatcher pane, taking the right half | `mcp__org-broker__spawn_claude_pane(target="dispatcher", direction="vertical", role="curator", name="curator", cwd="../.curator", permission_mode="auto")` (pane-close.md Step 5-3; residency is retired, so org-start does not spawn it) |
| Each Worker | **balanced split**: dynamically pick target and direction from the current rects returned by `list_panes`, and stack into the same tab | See the "Worker balanced split strategy" section below. `mcp__org-broker__spawn_claude_pane(target={target}, direction={direction}, role="worker", name="worker-{task_id}", cwd="{workers_dir}/{task_id}", permission_mode="auto")` (org-delegate Step 3) |

> **Why use `spawn_claude_pane`**: It is a structured launch tool (added in renga 0.18.0+, and the broker adapter provides the same API). When you pass `cwd` / `permission_mode` / `model` / `args[]` as structured fields, default broker synthesizes flags that **combine** `claude --permission-mode {mode} --mcp-config <broker>` (daemon, all tools + agent token) + the channel sidecar `--dangerously-load-development-channels server:org-broker-channel` for push-primary, so the first-time approval is **a 2-step folder-trust prompt + dev-channel sidecar approval (spawn-flow 3-3b)**. The old approach (feeding a `cd`-prefixed command string into `spawn_pane`) is **forbidden** -- a cwd-changing prefix prevents the bare-`claude` auto-upgrade from firing, so `send_message` channel pushes never arrive. Instructions from Secretary -> Dispatcher and Dispatcher -> Worker stop flowing entirely. Only the Secretary is launched as bare `claude` from `ops.toml` and relies on auto-upgrade. With `ORG_TRANSPORT=renga` (opt-in), the synthesized flags become a 1-step `--dangerously-load-development-channels server:renga-peers` instead of `--mcp-config <broker>`, and the first-time approval is also a 1-step dev-channel approval (procedure shape is isomorphic; see the dual-system note at the top of this file).

## Worker balanced split strategy

### Why balanced split is necessary

Each split divides the target pane 50/50. If the result drops below the lower bounds `MIN_PANE_WIDTH = 20` / `MIN_PANE_HEIGHT = 5`, the split is rejected with `[split_refused]` (investigation: `<workers_dir>/renga-split-inv/findings.md`).

With a fixed target or an ordinal `k`-based lookup table, the cumulative halving of the dispatcher's width, or re-dispatch after a worker closes mid-flight, caused the assumed layout to diverge from the actual one and triggered `[split_refused]` early.

The current design uses the **rect info (`x / y / width / height`, in cell units)** for each pane returned by `mcp__org-broker__list_panes`, and **dynamically picks target and direction from the current layout**. It is robust against jitter in worker retirement order and mid-flight closure, has no fixed "N parallel cap," keeps splitting as long as the terminal size and MIN_PANE constraints allow, and auto-escalates when the limit is hit.

### Algorithm

The balanced-split decision logic (target / direction selection, MIN_PANE constraint, secretary safeguard, role-priority sort, rect-adjacency check, `split_capacity_exceeded` detection) is **owned by the `claude-org-runtime` helper as the SoT**. The dispatcher feeds it a `mcp__org-broker__list_panes` snapshot and the task JSON via one of the entry points below, and then executes `spawn_claude_pane` / escalate according to the returned action plan (`spawn` / `after_spawn` / `escalate` / `state_writes` / `status`):

- CLI (the standard operational entry point): `claude-org-runtime dispatcher delegate-plan --task-json ... --panes-json ... --state-dir ... [--template-repo ...] [--locale-json ...]`. The dispatcher-side procedure has its primary source in the delegate-plan helper section of `.dispatcher/CLAUDE.md`.
- Library: `build_plan(...)` (the full action plan) and `choose_split(panes)` (a low-level helper for when you only need target / direction) in the `claude_org_runtime.dispatcher.runner` module.

The constant values (MIN_PANE_WIDTH / MIN_PANE_HEIGHT / SECRETARY_MIN_WIDTH / SECRETARY_MIN_HEIGHT / role-priority map), the order of checks, and the exact definition of rect adjacency are sourced from the **`claude_org_runtime.dispatcher.runner` module itself** (`_ROLE_PRIORITY` / `MIN_PANE_*` / `SECRETARY_MIN_*` / `choose_split()` / `rect_adjacent()`). The prose values were removed from this document because doc/runtime drift was a cause of mysterious `[split_refused]`-style failures (Issue #307 cleanup).

When there are no candidates, the helper returns `status="split_capacity_exceeded"` and an `escalate.send_message(to_id="secretary", ...)`. The dispatcher does not issue `spawn_claude_pane`, cancels the dispatch for just that one worker, and keeps the main monitor loop running (see `SKILL.md` Step 3-1c).

### Verification trace (Issue #307 scenario, reference)

A hand-traced reference table of `choose_split` behavior for the layout `secretary 280×43 / dispatcher 140×43 / curator 140×43` immediately after startup (terminal ≈ 280×86, assumed to be right after org-start's secretary horizontal split -> dispatcher vertical split). **The canonical values live in the runtime SoT**. If the doc disagrees with the runtime's actual behavior, trust the runtime.

| spawn | selected role | direction | intuitive rationale |
|---|---|---|---|
| 1st | secretary | vertical | while secretary still satisfies the splittable-size requirement, role priority puts it first |
| 2nd | curator | vertical | secretary drops out under the SECRETARY_MIN_WIDTH guard, so the next-priority curator is picked |
| 3rd | curator | horizontal | because role priority is strict primary, curator is picked repeatedly until it falls below MIN_PANE |

Once curator falls below MIN_PANE and drops out, the flow moves to the priority-2 worker pool. The design intent of putting the dispatcher last (in broker, each pane launches in a detached independent session / separate GUI window, so the halving of a visible viewport does not occur, but the intent of the scheduling order -- suppressing the re-split frequency of active monitoring panes -- works the same. The curator only exists while an on-demand activation is running and is normally absent) is documented in the `_ROLE_PRIORITY` comment in runner.py.

### Edge cases / operational notes

- **Re-dispatch after a worker closes mid-flight**: the old k-table issue of "compacting closed slots diverges from the table's assumptions" cannot occur in the rect-based model. Because the target is always picked from the actual layout, the decision is always consistent with the actual layout tree.
- **`spawn_claude_pane` errors**: `[split_refused]` / `[pane_not_found]` come back in the MCP result text. Escalate via Curator -> Secretary per the procedure in `references/renga-error-codes.md` (same policy as the old design).
- **Race**: if other workers come and go between `list_panes` and `spawn_claude_pane`, the target mismatch surfaces as `[pane_not_found]`. It is absorbed by the existing error-handling path.
- **Responsibility for target selection**: the dispatcher computes it from `list_panes` rect data. The Secretary only needs to pass task_id in the DELEGATE message and does not specify target.

## Operational notes

- **Place all panes in the same-tab scope**: the broker surface does not have `new_tab` / `focus_pane` (intentional exclusion), and pane-addressed operations (`mcp__org-broker__list_panes` / `send_message` / `inspect_pane`, etc.) follow contract Surface 4.2 **SINGLE-TAB MUST** (cross-tab addressing returns `pane_not_found`, the logical addressing scope). Therefore Dispatcher, Curator, and all Workers must be placed in the same-tab scope (in broker each pane launches in a detached independent session / separate GUI window and they do not visually stack, but addressing resolving to a same-tab scope is contractually identical). (Under `ORG_TRANSPORT=renga`, `list_panes` / `focus_pane` / `send_message` / `inspect` (CLI) can only touch panes in the currently-focused tab, and putting a worker in a separate tab via `new_tab` makes it unaddressable from the Dispatcher -- discovered 2026-04-20, upstream fix tracked at suisya-systems/renga#71 -- which leads to the same same-tab requirement.)
- **Naming conventions**:
  - Secretary -> `secretary`
  - Dispatcher -> `dispatcher`
  - Curator -> `curator`
  - Worker -> `worker-{task_id}` (task_id is a kebab-case unique identifier)
  - **org-broker target resolution rule**: an all-digit name is interpreted as an id, so the name must contain at least one letter (`worker-1` is OK; `1` would be treated as an id, so it's not).
- **Role labels (`role`)**: four values -- `secretary` / `dispatcher` / `curator` / `worker`.
  - The `list_panes` output exposes a `role` field, which is useful for aggregating org state and for picking targets in balanced split.
- **When a worker finishes**:
  1. The Secretary asks the Dispatcher for `CLOSE_PANE`.
  2. The Dispatcher explicitly tears down the pane with `mcp__org-broker__close_pane(target="worker-{task_id}")`.
     (The pane is removed -> `pane_exited` is emitted once -> it disappears from `list_panes` as well.
     `[pane_not_found]` / `[pane_vanished]` is treated as "already closed" and skipped.)
- **Stop order at org-suspend time**: Worker -> Dispatcher -> Curator (all torn down via `mcp__org-broker__close_pane`. Only when closing the last remaining pane do you get `[last_pane]` back, and that pane has to `exit` itself).

## Split direction conventions

The split directions are defined as follows (shared by `spawn_pane` / `spawn_claude_pane`):
- `direction="vertical"` = left/right split (existing pane = left, new pane = right)
- `direction="horizontal"` = top/bottom split (existing pane = top, new pane = bottom)

## Future features / upstream tracking

- A ratio argument such as `--ratio 0.2` for `spawn_pane` / `spawn_claude_pane` (currently fixed at 50/50).
- Backend-side automatic target selection such as `--target-largest` / `--direction auto` (currently the dispatcher computes it from `list_panes` rects; if this can be pushed upstream into the backend, the balanced-split logic can be collapsed into the MCP side. The upstream for broker is not renga but the broker adapter / runtime, so the delegation target is also broker-side).
