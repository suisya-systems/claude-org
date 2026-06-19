# Pane Layout Specification (org-broker MCP)

Pane / tab layout rules. Referenced by `org-start` and `org-delegate`.
Pane control goes through the `mcp__org-broker__*` MCP tools (the pane-control
tool set, including `spawn_claude_pane` / `set_pane_identity`, is fully
self-contained via MCP).

> **Transport dual systems -- default `broker` / opt-in `renga`**: the
> `mcp__org-broker__*` calls in this file are written for the **default `broker`**
> (with `ORG_TRANSPORT` unset), so you can follow them as-is (default behavior).
> Under `ORG_TRANSPORT=renga` (opt-in, revertable), the MCP server name becomes
> `renga-peers` and the tool **fully-qualified names mechanically rename from
> `mcp__org-broker__*` to `mcp__renga-peers__*`** (the argument shapes /
> semantics are identical, so balanced-split decisions and operation logic do
> not change). Only the points where the procedure differs by transport are
> noted alongside renga:
>
> - **Spawn ceremony (2 stages: folder-trust acceptance + dev-channel sidecar
>   acceptance)**: as in "Why use `spawn_claude_pane`" below, the default broker
>   injects `--mcp-config <broker>` and at startup mechanically approves
>   Claude Code's **folder-trust prompt** with `send_keys(enter=true)`, **and on
>   top of that** loads the channel sidecar for push-first delivery via
>   `--dangerously-load-development-channels server:org-broker-channel`, then
>   mechanically approves the dev-channel acceptance prompt
>   (spawn-flow 3-3b) with `send_keys(enter=true)` (2-stage acceptance:
>   folder-trust + dev-channel; this is an addition to, not a replacement of,
>   the folder-trust flow in ratified Sections 5 / 8.5; design SoT:
>   transport-lab `docs/design/broker-native-roles.md` Section 9.5). Note that
>   the broker spawn helper internally assembles the interactive-TUI argv
>   behind the default-deny billing-neutral guard. Under `ORG_TRANSPORT=renga`
>   (opt-in), the injection is `--dangerously-load-development-channels
>   server:renga-peers` with a single Enter approval for "Load development
>   channel?".
> - **Reception model (push-first = `claude/channel` / pull fallback)**: the
>   default broker is designed **push-first** (runtime push-first 0.1.24+,
>   broker-native-roles.md Section 9). A channel sidecar
>   (`server:org-broker-channel`) co-resident in each pane injects the body
>   into an idle session via `notifications/claude/channel`. Pull (pane-local
>   nudge + `check_messages`) is the fallback layer; its reception is driven
>   by each role's active cadence poll as the main path (nudges do not wake
>   idle, so reception is not nudge-dependent; Section 9.6 mapping table).
>   Under `ORG_TRANSPORT=renga` (opt-in), `send_message` becomes an in-band
>   push of `<channel source="renga-peers" ...>`. The layout operations
>   themselves (`list_panes` / `spawn_claude_pane` / `close_pane`, etc.) follow
>   the same logic on both sides, only the tool name swaps between
>   `mcp__org-broker__*` and `mcp__renga-peers__*`.
> - **Error branching (default = broker extension codes included)**: in
>   addition to the shared codes (`split_capacity_exceeded` / `[split_refused]`
>   / `[cwd_invalid]`, etc.), the default broker can return `[token_invalid]` /
>   `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]`
>   (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` /
>   `[name_taken]`. See the broker section of
>   [`.claude/skills/org-delegate/references/renga-error-codes.md`](renga-error-codes.md)
>   for the full list. Under `ORG_TRANSPORT=renga`, broker-specific codes do
>   not occur.
>
> `new_tab` / `focus_pane` are **not on the broker surface** (intentional
> exclusion) -- but the balanced split in this document only uses
> within-the-same-tab splits and does not use `new_tab`, so even on broker the
> absence has no impact. The canonical contract is
> [`docs/contracts/backend-interface-contract.md`](../../../../docs/contracts/backend-interface-contract.md)
> Surface 8 (ratified 2026-06-14; the additive amendment S3 to push-first is
> ratified as of 2026-06-15; the existing ratified body is unchanged), and the
> design SoT is transport-lab `docs/design/broker-native-roles.md` Section 9
> (push-first redesign) / `docs/design/ja-migration-plan.md` Section 5.2(ii).
> Broker production runs (dogfood) are scoped to Epic #6 Issue G, and are not
> the default path of this file.

## Initial layout (after Dispatcher / Curator startup)

Under broker, each pane is launched as **its own detached tmux session**
(POSIX / WSL2, named `claude-org-broker-<pid>-<seq>` on the dedicated socket
`claude-org-broker`) or as **its own GUI window in WezTerm**
(Windows, `isolated_session=False`). The Secretary (`secretary`) is a
**logical pane** with no adapter-backed real pane (a bookkeeping entry;
`register_logical_pane`), and runs as-is on the human's local terminal where
the org was started. Therefore the renga-style "visual tiling of multiple
panes in a single screen" **does not manifest as things stand**
(broker-spawned child panes are not visible on the human's screen by default,
and observation of an in-flight run is done via the per-session attach path
`tmux -L claude-org-broker attach -r -t claude-org-broker-<pid>-<seq>`; the
single-session unification, i.e. one-screen overview, is design-decided but
**not yet landed**).

That said, **the geometry / role-priority balanced-split scheduling itself
contractually runs transport-neutral** -- the `list_panes` geometry is
REQUIRED by contract Surface 1.5, balanced split is documented as
load-bearing by Surface 2.2 (see
[`docs/contracts/backend-interface-contract.md`](../../../../docs/contracts/backend-interface-contract.md)),
and both are retained backend-independently. Balanced split's decision of
"dynamic worker-zone generation with role priority over the four candidates
`secretary / curator / worker / dispatcher`" (see the algorithm section below
for details) is a scheduling order and is equally effective even without
visual tiling. The visual-layout ASCII diagram (single-screen tiling on the
renga side) does not correspond to a reality on the broker side, so it is
omitted.

> **Design SoT note**: the primary design SoT for "no visual tiling" and
> "single-session unification (one-screen overview)" is transport-lab
> (`docs/design/broker-native-roles.md` Section 9 / Section 8.2 / Section 3.4,
> `docs/design/ja-migration-plan.md` Section 5 / Section 8), which is not
> locally present in this repository. The secondary reference inside this
> repository is
> [`docs/operations/broker-dogfood-runbook.md`](../../../../docs/operations/broker-dogfood-runbook.md)
> Section 8 (observability -- the attach path into the running org;
> describes detached independent sessions / logical secretary / not-yet-landed
> single-session unification).

## Placement rules

| Target | Operation | Notes |
|---|---|---|
| Dispatcher | Horizontal split of the Secretary pane, taking the bottom half | `mcp__org-broker__spawn_claude_pane(target="focused", direction="horizontal", role="dispatcher", name="dispatcher", cwd=".dispatcher", permission_mode="bypassPermissions", model="sonnet")` (org-start Block A-1) |
| Curator (on-demand only) | Vertical split of the Dispatcher pane, taking the right half | `mcp__org-broker__spawn_claude_pane(target="dispatcher", direction="vertical", role="curator", name="curator", cwd="../.curator", permission_mode="auto")` (pane-close.md Step 5-3; residency is retired, so org-start does not spawn it) |
| Each Worker | **balanced split**: dynamically pick target and direction from the current rects returned by `list_panes`, and stack into the same tab | See the "Worker balanced split strategy" section below. `mcp__org-broker__spawn_claude_pane(target={target}, direction={direction}, role="worker", name="worker-{task_id}", cwd="{workers_dir}/{task_id}", permission_mode="auto")` (org-delegate Step 3) |

> **Why use `spawn_claude_pane`**: it is the structured launch tool (added in
> renga 0.18.0+; the broker adapter offers the same API). When you pass
> `cwd` / `permission_mode` / `model` / `args[]` as structured fields, the
> default broker assembles flags that **combine** `claude --permission-mode
> {mode} --mcp-config <broker>` (daemon, full tools + agent token) with the
> channel sidecar `--dangerously-load-development-channels
> server:org-broker-channel` for push-first delivery, and the initial
> acceptance becomes **a 2-stage flow of folder-trust prompt + dev-channel
> sidecar acceptance (spawn-flow 3-3b)**. The old approach (feeding a
> `cd`-prefixed command string into `spawn_pane`) is **forbidden** (a
> cwd-changing prefix prevents the bare-`claude` auto-upgrade from firing, so
> `send_message` channel pushes never arrive, and Secretary->Dispatcher /
> Dispatcher->Worker instructions stop flowing entirely). Only the Secretary
> is launched as bare `claude` from `ops.toml` and relies on auto-upgrade.
> Under `ORG_TRANSPORT=renga` (opt-in), the assembled flag is a single stage
> of `--dangerously-load-development-channels server:renga-peers` instead of
> `--mcp-config <broker>`, and the initial acceptance is also a single stage
> of dev-channel acceptance (the procedure has the same shape; see the
> dual-system note at the top of this file).

## Worker balanced split strategy

### Why balanced split is necessary

Each split divides the target pane 50/50. If the result drops below the lower
bounds `MIN_PANE_WIDTH = 20` / `MIN_PANE_HEIGHT = 5`, the split is rejected
with `[split_refused]` (investigation: `<workers_dir>/renga-split-inv/findings.md`).

With a fixed target or an ordinal `k`-based lookup table, the cumulative
halving of the dispatcher's width, or re-dispatch after a worker closes
mid-flight, caused the assumed layout to diverge from the actual one and
triggered `split_refused` early.

The current design uses the **rect info (`x / y / width / height`, in cell
units)** for each pane returned by `mcp__org-broker__list_panes`, and
**dynamically picks target and direction from the current layout**. It is
robust against jitter in worker retirement order and mid-flight closure, has
no fixed "N parallel cap", keeps splitting as long as the terminal size and
MIN_PANE constraints allow, and auto-escalates when the limit is hit.

### Algorithm

The balanced-split decision logic (target / direction selection, MIN_PANE
constraint, secretary safeguard, role-priority sort, rect-adjacency check,
`split_capacity_exceeded` detection) is **owned by the `claude-org-runtime`
helper as the SoT**. The dispatcher feeds it a `mcp__org-broker__list_panes`
snapshot and the task JSON via one of the entry points below, and then
executes `spawn_claude_pane` / escalate according to the returned action plan
(`spawn` / `after_spawn` / `escalate` / `state_writes` / `status`):

- CLI (the standard operational entry point): `claude-org-runtime dispatcher delegate-plan --task-json ... --panes-json ... --state-dir ... [--template-repo ...] [--locale-json ...]`. The dispatcher-side procedure has its primary source in the delegate-plan helper section of `.dispatcher/CLAUDE.md`.
- Library: `build_plan(...)` (the full action plan) and `choose_split(panes)` (a low-level helper for when you only need target / direction) in the `claude_org_runtime.dispatcher.runner` module.

The constant values (MIN_PANE_WIDTH / MIN_PANE_HEIGHT / SECRETARY_MIN_WIDTH /
SECRETARY_MIN_HEIGHT / role-priority map), the order of checks, and the exact
definition of rect adjacency are sourced from the **`claude_org_runtime.dispatcher.runner`
module itself** (`_ROLE_PRIORITY` / `MIN_PANE_*` / `SECRETARY_MIN_*` /
`choose_split()` / `rect_adjacent()`). The prose values were removed from this
document because doc/runtime drift was a cause of mysterious
`[split_refused]`-style failures (Issue #307 cleanup).

When there are no candidates, the helper returns
`status="split_capacity_exceeded"` and an `escalate.send_message(to_id="secretary", ...)`.
The dispatcher does not issue `spawn_claude_pane`, cancels the dispatch for
just that one worker, and keeps the main monitor loop running (see
`SKILL.md` Step 3-1c).

### Verification trace (Issue #307 scenario, reference)

A hand-traced reference table of `choose_split` behavior for the layout
`secretary 280x43 / dispatcher 140x43 / curator 140x43` immediately after
startup (terminal approx 280x86, assumed to be right after org-start's
secretary horizontal split -> dispatcher vertical split). **The canonical
values live in the runtime SoT**. If the doc disagrees with the runtime's
actual behavior, trust the runtime.

| spawn | selected role | direction | intuitive rationale |
|---|---|---|---|
| 1st | secretary | vertical | while secretary still satisfies the splittable-size requirement, role priority puts it first |
| 2nd | curator | vertical | secretary drops out under the SECRETARY_MIN_WIDTH guard, so the next-priority curator is picked |
| 3rd | curator | horizontal | because role priority is strict primary, curator is picked repeatedly until it falls below MIN_PANE |

Once curator falls below MIN_PANE and drops out, the flow moves to the
priority-2 worker pool. The design intent of putting the dispatcher last
(because under broker each pane launches as a detached independent session /
separate GUI window so halving of the visible viewport does not occur, but
the scheduling-order intent of avoiding frequent re-splits of an active
monitoring pane is the same; and the curator only exists while an on-demand
activation is running and is normally absent) is documented in the
`_ROLE_PRIORITY` comment in runner.py.

### Edge cases / operational notes

- **Re-dispatch after a worker closes mid-flight**: the old k-table issue of
  "compacting closed slots diverges from the table's assumptions" cannot
  occur in the rect-based model. Because the target is always picked from
  the actual layout, the decision is always consistent with the layout tree.
- **`spawn_claude_pane` errors**: `[split_refused]` / `[pane_not_found]`
  come back in the MCP result text. Escalate via Curator -> Secretary per
  the procedure in `references/renga-error-codes.md` (same policy as the
  old design).
- **Race**: if other workers come and go between `list_panes` and
  `spawn_claude_pane`, the target mismatch surfaces as `[pane_not_found]`.
  It is absorbed by the existing error-handling path.
- **Responsibility for target selection**: the dispatcher computes it from
  `list_panes` rect data. The Secretary only needs to pass task_id in the
  DELEGATE message and does not specify target.

## Operational notes

- **Keep all panes in the same tab scope**: the broker surface does not have
  `new_tab` / `focus_pane` (intentional exclusion), and pane-addressed
  operations (`mcp__org-broker__list_panes` / `send_message` / `inspect_pane`,
  etc.) follow contract Surface 4.2's **SINGLE-TAB MUST** (logical addressing
  scope that returns `pane_not_found` for cross-tab addressing). Therefore
  the Dispatcher, Curator, and all Workers are placed in the same tab scope
  (under broker, each pane launches as a detached independent session / a
  separate GUI window and is not visually stacked, but the addressing
  resolves into the same tab scope -- contractually identical). (Under
  `ORG_TRANSPORT=renga`, `list_panes` / `focus_pane` / `send_message` /
  `inspect` (CLI) can only touch panes in the currently-focused tab, and
  putting a worker in a separate tab via `new_tab` makes it unaddressable
  from the dispatcher -- discovered 2026-04-20, fix tracked upstream in
  renga at suisya-systems/renga#71 -- which yields the same single-tab
  requirement.)
- **Naming conventions**:
  - Secretary -> `secretary`
  - Dispatcher -> `dispatcher`
  - Curator -> `curator`
  - Worker -> `worker-{task_id}` (task_id is a kebab-case unique identifier)
  - **org-broker target resolution rule**: an all-digit name is interpreted
    as an id, so the name must contain at least one letter (`worker-1` is OK;
    `1` would be treated as an id, so it's not).
- **Role labels (`role`)**: four values -- `secretary` / `dispatcher` /
  `curator` / `worker`.
  - The `list_panes` output exposes a `role` field, which is useful for
    aggregating org state and for picking targets in balanced split.
- **When a worker finishes**:
  1. The Secretary asks the Dispatcher for `CLOSE_PANE`.
  2. The Dispatcher explicitly tears down the pane with
     `mcp__org-broker__close_pane(target="worker-{task_id}")`.
     (The pane is removed -> `pane_exited` is emitted once -> it disappears
     from `list_panes` as well.
     `[pane_not_found]` / `[pane_vanished]` is treated as "already closed"
     and skipped.)
- **Stop order at org-suspend time**: Worker -> Dispatcher -> Curator (all
  torn down via `mcp__org-broker__close_pane`. Only when closing the last
  remaining pane do you get `[last_pane]` back, and that pane has to `exit`
  itself).

## Split direction conventions

Split directions are defined as follows (shared by `spawn_pane` /
`spawn_claude_pane`):
- `direction="vertical"` = left/right split (existing pane = left, new pane = right)
- `direction="horizontal"` = top/bottom split (existing pane = top, new pane = bottom)

## Future features / upstream tracking

- A ratio argument such as `--ratio 0.2` for `spawn_pane` / `spawn_claude_pane`
  (currently fixed at 50/50).
- Backend-side automatic target selection such as `--target-largest` /
  `--direction auto` (currently the dispatcher computes it from `list_panes`
  rects; if this can be pushed to the upstream backend, the balanced-split
  logic can be collapsed into MCP. For broker, the upstream is the broker
  adapter / runtime rather than renga, so the delegation target is also the
  broker side).
