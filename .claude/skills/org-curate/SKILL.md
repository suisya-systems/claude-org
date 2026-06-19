---
name: org-curate
description: >
  Consolidate and reorganize accumulated raw learnings (knowledge/raw/).
  Called exactly once by a curator that the dispatcher spawned on demand
  when the threshold check at worker close
  (tools/check_curate_threshold.py) fired (the resident /loop is retired).
  Also fires manually when asked to "organize the knowledge".
effort: medium
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash(mkdir -p knowledge/raw/archive/)
  - Bash(mkdir -p ../knowledge/raw/archive/)
  - Bash(mv knowledge/raw/*)
  - Bash(mv ../knowledge/raw/*)
  - Bash(grep:*)
  - Bash(find knowledge/*)
  - Bash(find ../knowledge/*)
  - Bash(py -3 tools/check_curate_threshold.py:*)
  - Bash(python3 tools/check_curate_threshold.py:*)
  - Bash(py -3 ../tools/check_curate_threshold.py:*)
  - Bash(python3 ../tools/check_curate_threshold.py:*)
  - mcp__renga-peers__send_message
---

# org-curate: knowledge curation

Read the raw learnings accumulated under `knowledge/raw/`, classify and consolidate them, and write them to `knowledge/curated/`.

> **Transport layer both systems (`ORG_TRANSPORT`: default `renga` / opt-in `broker`)**: this skill's `mcp__renga-peers__*` calls (`send_message` to secretary / dispatcher) are written for **default `renga`** and can be followed as-is when `ORG_TRANSPORT` is unset (default behavior unchanged). Under `ORG_TRANSPORT=broker` (opt-in, revertible), the fully qualified names get machine-substituted to **`mcp__renga-peers__*` → `mcp__org-broker__*`**, receive is not an in-band push but a **pane-local nudge + `check_messages` pull** (the CURATE_DONE direct `send_message` to the dispatcher → dispatcher-side `check_messages` wait path only changes its tool name under broker; the logic is the same), and errors gain the broker-specific codes (see the broker section in [`.claude/skills/org-delegate/references/renga-error-codes.md`](../org-delegate/references/renga-error-codes.md)). The design SoT is transport-lab `docs/design/ja-migration-plan.md` §5.2(ii); the contract is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (awaiting ratification). The default-renga procedure is unchanged (broker is additive).

**Launch model (on-demand)**: this skill executes exactly one cycle per activation (`/loop` is forbidden).
Threshold judgment is consolidated into the external script [`tools/check_curate_threshold.py`](../../../tools/check_curate_threshold.py);
there is **no** internal gate like "exit immediately if fewer than 5 raw entries" inside this skill.
You receive the activation reasons `reasons[]` and execute only the matching steps.

**Path resolution (important)**: the `knowledge/...` / `tools/...` notation in this skill denotes **repo-root-relative
logical paths**. An on-demand-spawned curator pane has cwd `.curator/`, so when running via Bash,
reinterpret them as `../knowledge/...` / `../tools/...` (or absolute paths obtained via `cd .. && pwd`) —
the same convention as the "Paths" section of `.curator/CLAUDE.md` (both forms are allowed in
allowed-tools). When running manually from the repo root, use them as-is.

## Step 0: determine the activation reasons (`reasons`)

`reasons[]` takes the following 4 values:

| reason | meaning | steps to execute |
|---|---|---|
| `raw_threshold` | 5 or more active raw entries | Steps 2–5 (classify, consolidate, archive, improvement proposals) |
| `skill_candidates_pending` | 5 or more pending skill-candidates | Step 6 (fire skill-audit) |
| `work_skill_count` | 20 or more work-skills (excluding org-*) | Step 6 (fire skill-audit) |
| `legacy_marker_sweep` | `<!-- curated -->` remnants directly under raw/ | Step 1 (migration sweep; *always runs anyway*) |

### 0-A: determine the activation context (on-demand vs explicit manual) — decides Step 7's send obligation

**This determination is the sole basis for whether Step 7 (completion notification) is mandatory or
optional**. Do not loosen it with self-inferred reasoning like "it's probably manual so I can skip"
(that is the root cause of curator orphaning = pane leaks). The judgment is grounded in **"was this
curator instance itself spawned / driven by the dispatcher"** — do not decide by the mere existence
of an external file (the reason is noted under (i) below).

**Primary signals (instance-specific, deterministic; on-demand is confirmed if even one matches)** —
in this case **always send** Step 7's `CURATE_DONE` / `CURATE_SKIPPED` / `CURATE_ERROR` **to the
dispatcher** (regardless of outcome, no exceptions; never re-classify as manual):

- **(ii)** an activation instruction message was received from the dispatcher (peer name `dispatcher`).
  This only happens during on-demand activation and never with a human-typed `/org-curate` (= a
  deterministic discriminator vs manual).
- **(iii)** the activation instruction message includes the JSON from
  `tools/check_curate_threshold.py` (`reasons[]` / `counts`).

**Auxiliary signal (a dispatcher-side marker; not sufficient alone to declare on-demand)**:

- **(i)** `.state/dispatcher/curate-inflight.json` exists (from a curator pane with CWD=`.curator/`,
  that is `../.state/dispatcher/curate-inflight.json`). This is the on-demand activation marker the
  dispatcher writes immediately after spawn at CLOSE_PANE Step 5-3; the dispatcher waits for the
  curator's `CURATE_*` via `check_messages` before closing the pane
  ([`.dispatcher/references/pane-close.md`](../../../.dispatcher/references/pane-close.md) 5-3 /
  [`.dispatcher/references/worker-monitoring.md` Step 5.3](../../../.dispatcher/references/worker-monitoring.md#step-5-3)).
  **This signal corroborates on-demand only when this instance is a curator pane spawned by the
  dispatcher** (CWD=`.curator/`, pane name `curator`; = primary signals (ii)/(iii) are also present).
  The inflight file is a global file not tied to a specific instance, so **a curator that a human
  manually launched in another pane (secretary / repo root, CWD≠`.curator/`, no dispatcher activation
  instruction) must not use a co-existing other on-demand curator's inflight as its own send trigger**
  (an erroneous send risks the dispatcher closing the real, in-flight on-demand curator early —
  addressed for a Codex Major).

**Explicit manual activation** can be assumed only when **none of the primary signals (ii)/(iii)
apply** (= no activation instruction from the dispatcher was received) AND this instance is not a
dispatcher-spawned curator pane either, but a human directly typed `/org-curate` in a secretary-side
pane. Only in this case may Step 7 be omitted (the dispatcher carries no pane-close responsibility).
**If primary signals (ii)/(iii) were received, on-demand is confirmed regardless of inflight presence
and Step 7 send is mandatory**. When in doubt (e.g., a dispatcher-spawned curator pane suspected of
dropping a message), **err on the on-demand side and always send** (sending is harmless as information
sharing; only not sending creates a pane leak).

1. **On-demand activation via the dispatcher**: the activation instruction message contains
   the JSON from `tools/check_curate_threshold.py` (`reasons[]` / `counts`).
   Adopt it as-is (do not recompute).
2. **Manual activation (no reasons provided)**: run the script yourself to determine them.
   From the curator pane (cwd=`.curator/`): `py -3 ../tools/check_curate_threshold.py`;
   from the repo root: `py -3 tools/check_curate_threshold.py` (POSIX: `python3`):
   - exit 0 (below_threshold) → no work to execute. Run only the Step 1 sweep, then notify
     `CURATE_SKIPPED` in Step 7 and finish
   - exit 10 (curate_needed) → adopt `reasons[]` from the stdout JSON and continue
   - exit 2 (error) → notify `CURATE_ERROR` in Step 7 and finish

> **Note**: items 1 (receipt of reasons) and 0-A(iii) above only state the *source* of `reasons`;
> they are independent of the Step 7 send-obligation decision. The send obligation is determined by
> 0-A's **primary signals (ii)/(iii)** (= receipt of a dispatcher activation instruction). A curator
> spawned by the dispatcher remains **on-demand** even if it falls into item 2 above (script self-runs
> without reasons being passed in), and Step 7's send is still mandatory. Do not short-circuit to
> "reasons not passed = manual = optional".

## Step 1: migration sweep (clean up old data) — always runs

Run **unconditionally** every time, regardless of what `reasons[]` contains (an idempotent
cleanup; a no-op when there are no remnants). The `legacy_marker_sweep` reason exists to
guarantee that "the curator gets spawned even if only for this sweep"; the sweep itself runs
no matter what the activation reason was:

1. `mkdir -p knowledge/raw/archive/` (idempotent).
2. For each file directly under `knowledge/raw/` that contains `<!-- curated -->` near the
   top, `move` it to `knowledge/raw/archive/`. No need to add a marker (it is already present).
3. Run this step even when there are 0 raw files.

> Per Set A § Role: curator, the Curator's write surface is limited to `knowledge/curated/` and
> `knowledge/raw/archive/` (move permission). Active entries directly under `knowledge/raw/` are
> immutable. Step 1's migration sweep is a `move`, not a rewrite, so it does not violate this constraint.

**Branching from here**: if `reasons[]` contains `raw_threshold`, go to Step 2. Otherwise skip
Steps 2–5 and proceed to the Step 6 check.

## Step 2: read and classify (reason: raw_threshold)

1. Enumerate files directly under `knowledge/raw/` (**excluding** `knowledge/raw/archive/`).
   Exclude sentinels like `.gitkeep` (entries starting with `.`) (after Step 1's sweep, no
   marker-bearing files remain in active raw).
2. Read them all as "unsorted".
3. Classify by theme. Use the following granularity as a guide:
   - Technical area (e.g., authentication, database, frontend).
   - Tool / service (e.g., renga, github-api, aws).
   - Process (e.g., code-review, testing, deployment).
4. Read the existing `knowledge/curated/` files too, and check for duplicates.

## Step 2.5: extract skill-promotion candidates

For themes from Step 2 that match either of the following, call `.claude/skills/skill-eligibility-check/SKILL.md`:

- The same theme has **3 or more** unsorted raw files (a candidate for the raw_reappearance signal to fire).
- There is no article on the same theme in `knowledge/curated/`, and the theme contains procedural learnings (content that fits a Step-by-step format).

Construct the input as below (`context: curation`):

```yaml
context: curation
pattern_name: <inferred skill name, kebab-case; derived from the theme>
summary: <1–2 sentences on what is reusable in this theme>
task_ids: []                    # optional. Leave empty if raw notes lack a task_id.
raw_files: <array of paths to the raw/ files for this theme. Step 4 moves these to archive/, so record the post-move path (`knowledge/raw/archive/<entry>.md`) here. `skill-eligibility-check` persists this into `knowledge/skill-candidates.md`, so we want a stable, trackable final path.>
steps_outline: <main steps extracted from the raw set>
trigger_description: <situation in which this theme arises>
decision_criteria: <decision criteria appearing in the theme>
output_format: <theme's artifact format>
```

`task_ids` is not part of the standard raw schema (`Facts / Decision / Rationale / When it applies`), so an empty array is fine in the curation context. If a date or similar is in the file name, including that in `raw_files` is a serviceable substitute.

The decision determines what to do next. **Regardless of the decision, the Step-3 consolidation into curated/ proceeds normally**:

- `skill_recommend` → the skill side has already auto-appended to `knowledge/skill-candidates.md`. No additional action here.
  The corresponding raw files are still **consolidated into curated/ in Step 3 and moved to `knowledge/raw/archive/` with a marker added in Step 4** (skill promotion and curated note coexist; the curated note remains as background, while a separate skill is created as procedure. Failing to do both leaves unsorted raw files behind and breaks the threshold check).
- `candidate_queue` → consolidate into curated/ as usual in Step 3 (waiting for the next raw_reappearance).
- `curated_only` → consolidate into curated/ as usual in Step 3.

Asking the human is the Lead Claude's job; org-curate does not do it.

## Step 3: consolidate and write (reason: raw_threshold)

For each theme:

1. If a curated file exists already, append the new learnings.
2. Otherwise, create one.
3. File name: `knowledge/curated/{theme}.md`.
4. Format:
   ```markdown
   # {Theme name}

   ## {Learning title 1}
   {Integrated description: facts, decision, rationale, when it applies.}

   ## {Learning title 2}
   ...
   ```
5. Merge duplicate learnings (keep the more concrete / accurate description).
6. When learnings contradict, prefer the more recent date and explicitly note the contradiction.

## Step 4: move to archive and add the processed marker (reason: raw_threshold)

Consolidated raw files are not written back to active raw; they are moved into `knowledge/raw/archive/` (move-then-mark).

1. Create `knowledge/raw/archive/` (idempotent):
   ```
   mkdir -p knowledge/raw/archive/
   ```
2. Move each consolidated raw file to archive:
   ```
   mv knowledge/raw/<entry>.md knowledge/raw/archive/<entry>.md
   ```
   (Under the normal flow, no file of the same name exists on the archive side and the move targets a fresh path, so even with a `mv -i` alias no overwrite prompt is raised. What the alias breaks is the marker addition in the next sub-step 3, not this normal move. Exceptionally, if the same raw entry reappears or a partial recovery leaves `knowledge/raw/archive/<entry>.md` already in place, `mv -i` will issue an interactive confirmation — in that case stop, inspect the existing archive-side file, resolve the collision via rename etc., and then move.)
3. After the move, prepend the line `<!-- curated -->` as a visual marker to the top of the archived file.
   **Addition must be performed via the Write tool (mandatory procedure)**: Read the target archive
   file's contents, prepend `<!-- curated -->` + a newline, and Write it back to the same path
   (= read -> prepend -> write).
   The marker is added **to the file after it has been moved to archive**. Files under active `knowledge/raw/` are never rewritten.

   > **Why not add it via the shell (preventing recurrence of the past harm: 5 broken 17-byte `.md.tmp` remnants accumulated)**:
   > The shell-style approach of "write marker + body to `<entry>.md.tmp`, then overwrite via `mv <entry>.md.tmp <entry>.md`"
   > breaks under two environmental factors. (1) If `mv` is aliased to `mv -i`, an **overwriting `mv` against an
   > existing file raises an interactive confirmation, and under non-interactive execution (curator runs unattended)
   > it gets rejected on EOF** -- the original without the marker is left in place and only the `.tmp` remains as a
   > stray. (2) zsh's history expansion interprets the `!` inside the marker string, and writing it directly to the
   > shell injects a `\` as in `<\!-- curated -->`.
   > **A prepend via the Write tool uses no `mv` at all (-> avoids (1)) and never passes `!` through the shell
   > (-> avoids (2)), severing both at once.** If you must use the shell anyway, evade the alias on overwriting `mv`
   > via `command mv -f`, and assemble any marker string containing `!` via `chr(33)` or similar rather than writing
   > it directly to the shell (note however that this skill's allowed-tools only permits `Bash(mv knowledge/raw/*)`
   > family, so `command mv -f` falls into a permission prompt under unattended execution -- hence the Write tool
   > path is the default).

The fact that a file lives under archive/ is itself the "curated" signal, but the marker is also added for visual continuity. The `raw_active` count in `tools/check_curate_threshold.py` excludes archive/, so even just moving alone removes a file from the count for next time.

> Rationale: per the Set E §1.1 (Q1) ratification and Set A § Role: curator, the Curator must not mutate active entries directly under `knowledge/raw/`. Write surface is limited to creating / appending under `knowledge/curated/`, and moving (and editing the moved file) under `knowledge/raw/archive/`.

## Step 5: consider improvement proposals (reason: raw_threshold)

Take a step back across the curated learnings and consider:

1. **Skill improvements**: do the learnings improve a skill's procedure?
   - Example: "ceiling on number of worker panes" → add a constraint to org-delegate.
2. **CLAUDE.md improvements**: anything to add to the Lead principles?
3. **Need for new skills**: does a recurring pattern justify a new skill?

When you have an improvement proposal:
- Apply the criteria from references/knowledge-standards.md.
- Send the proposal to the Lead Claude via renga-peers (`to_id="secretary"`).
- Proposal format: "[improvement proposal] {target}: {change}. Reason: {why}".
- **Do not change anything yourself until the Lead obtains approval from the human.**

## Step 6: fire the skill inventory (reason: skill_candidates_pending / work_skill_count)

If `reasons[]` contains `skill_candidates_pending` or `work_skill_count`, launch
`.claude/skills/skill-audit/SKILL.md`. If neither is present, do nothing.

The threshold definitions (5+ pending / 20+ work-skills, excluding org-*) are kept in
exact agreement between `tools/check_curate_threshold.py` and skill-audit Step 1.
`skill-audit` itself re-checks the thresholds when fired, so no recomputation is needed here.

## Step 7: completion notification (always run last)

**Send obligation (check this first)**: if the Step 0-A determination puts you in an **on-demand
context (either primary signal (ii) dispatcher activation instruction / (iii) reasons JSON included,
or, in a dispatcher-spawned curator pane, the (i) inflight corroboration), you must send one of
`CURATE_DONE` / `CURATE_SKIPPED` / `CURATE_ERROR` regardless of outcome**. Even when below_threshold
left nothing done beyond the sweep, send `CURATE_SKIPPED` ("we did nothing, so notification is
unnecessary" is wrong: the dispatcher is waiting on `CURATE_*` via `check_messages`; a missing send
leaves the pane orphaned until timeout). **Omission is allowed only when Step 0-A has confirmed
explicit manual activation**. Self-inferred shortcuts like "this is probably manual so skip" are
forbidden.

Report the cycle's outcome via **direct send to the dispatcher**. This is the trigger for
the on-demand curator's pane close, so **the destination must be `to_id="dispatcher"`**
(a channel broadcast or a secretary-addressed message would let the dispatcher's
`check_messages` wait time out, causing pane leaks / premature closes):

```
mcp__renga-peers__send_message(to_id="dispatcher", message="CURATE_DONE: ...")
```

**Ordering rule**: send this only **after** every Step 5 improvement proposal
(secretary-bound) has been sent. The contract allows the dispatcher to close the pane upon
receiving `CURATE_*`, so sending it first risks the pane being destroyed before the
improvement proposals go out.

The message is one of the following 3 kinds:

- `CURATE_DONE: reasons={reasons[]} raw {n} entries → {m} themes consolidated into curated / {k} archived / {s} swept / skill-audit {fired or none}`
  — when one or more steps executed and completed normally
- `CURATE_SKIPPED: below_threshold (counts: raw_active={n}, pending={p}, work_skill={w}, legacy_marker={l})`
  — when below_threshold turned out true and nothing beyond the sweep was done. **In an on-demand
  context, sending is mandatory even for this below_threshold edge per Step 0-A**. Under explicit
  manual activation, sending is allowed but may be omitted (see below).
- `CURATE_ERROR: {one-line summary}` — when an unrecoverable error occurred mid-cycle (include any partial completion in the one line)

**Send may be omitted only under explicit manual activation (only when confirmed by Step 0-A)**: in
a launch where a human directly typed `/org-curate` in a secretary-side pane (= **none of the primary
signals (ii)/(iii) of Step 0-A were received**, AND **this instance is not a dispatcher-spawned
curator pane (CWD=`.curator/`, pane name `curator`) either**), sending is optional because the
dispatcher carries no pane-close responsibility. **The mere presence of a co-existing other on-demand
curator's `curate-inflight.json` (i) does not make this on-demand** — that inflight is not addressed
to this instance, so if the manual-side sends `CURATE_*` it could close the real on-demand curator
early (do not send). It is fine to send only if the dispatcher exists among the peers and this
instance wants to share information (harmless). Omit only when `[pane_not_found]` is returned.
**The "omission allowed" of this paragraph does not apply in an on-demand context (primary signal
matched or dispatcher-spawned curator pane)** — always send.
