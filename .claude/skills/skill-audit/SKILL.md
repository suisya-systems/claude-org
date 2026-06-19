---
name: skill-audit
description: >
  Skill inventory pass (deprecation / consolidation / owner-missing
  checks). Fires on a state-based trigger only: when the candidate
  queue knowledge/skill-candidates.md has 5 or more pending entries,
  OR when the work-skill count under .claude/skills/ (excluding org-*)
  reaches 20 or more. Not started by a time-based /loop (avoids
  polluting raw logs on quiet days).
effort: medium
allowed-tools:
  - Read
  - Bash(grep:*)
  - Bash(find:*)
  - Bash(wc:*)
  - mcp__renga-peers__send_message
---

# skill-audit: skill inventory pass

To prevent the work-skill search inside `org-delegate` from getting noisy as the skill count grows, do an inventory pass on a **state-based** trigger rather than periodically.

The real concern is "search-surface noise", not the raw skill count.
This skill mechanically checks 3 dimensions (deprecation / consolidation / owner-missing) and sends a consolidated change proposal to the Lead Claude. It never deletes or modifies a skill on its own.

> **Transport — both backends (default `broker` / opt-in `renga`)**: the peer-message and pane operations in this file (and across the skills) are written as `mcp__org-broker__*`. With **`ORG_TRANSPORT` unset = default `broker`**, follow them as-is. With `ORG_TRANSPORT=renga` (opt-in, revertible), the MCP server name becomes `renga-peers`, and the **fully qualified names are mechanically substituted `mcp__org-broker__*` → `mcp__renga-peers__*`** (argument shape and semantics are identical, so the operational logic does not change). The three transport-dependent differences are:
>
> - **Receive model (default = push-primary = `claude/channel` / pull fallback)**: the default broker is designed as **push-primary** (runtime push-first 0.1.24+; design SoT is transport-lab `docs/design/broker-native-roles.md` §9). A **channel sidecar** (`server:org-broker-channel`) co-located with each pane claims the broker queue at ~1s intervals and pushes via `notifications/claude/channel`, injecting the body into an idle session (creating the "respond as soon as it arrives" trigger). Worker ack (`to_id="worker-{task_id}"`), retro-gate ack (`to_id="dispatcher"`), and the dispatcher handover route's `send_message` / `check_messages` / `send_keys` / `inspect_pane` all work under the same tool names (`mcp__org-broker__*`). **Pull is the fallback layer**: when the sidecar is absent or unhealthy (heartbeat timeout flips to `delivery_mode=PULL`), for channel-incapable panes (codex pull-peer), or when claude.ai login is missing, each role actively `check_messages` on its own cadence (per-role cadence: worker = turn boundary / bounded `/loop` after completion; dispatcher = `/loop 3m`; secretary = at turn start; the existing "when you see a nudge, `check_messages`" prose is **not retracted** and should be read as this fallback cadence). With `ORG_TRANSPORT=renga` (opt-in), worker reports and dispatcher responses are pushed in-band as `<channel source="renga-peers" …>` (renga's in-band push and broker push-primary share the same immediate-response trigger). Contract-wise, push-primary is **ratified** on Surface 8 + push-primary amendment (2026-06-15, S3; pull is retained as fallback; renga is unchanged).
> - **Spawn ritual (default = folder-trust approval + dev-channel sidecar approval, 2 steps)**: when spawning a child pane, the default broker injects `--mcp-config <broker>` and mechanically approves Claude Code's **folder-trust prompt** with `send_keys(enter=true)`, **and in addition**, loads the channel sidecar via `--dangerously-load-development-channels server:org-broker-channel` for push-primary and mechanically approves the dev-channel approval prompt (spawn-flow 3-3b) with `send_keys(enter=true)` (folder-trust + dev-channel = 2-step approval; details in [`.dispatcher/references/spawn-flow.md`](../../../.dispatcher/references/spawn-flow.md) 3-2 / 3-3b, design in broker-native-roles.md §9.5). With `ORG_TRANSPORT=renga` (opt-in), it injects `--dangerously-load-development-channels server:renga-peers` and approves the "Load development channel?" prompt with Enter — 1 step. **Note: the attention watcher is a transport-independent CLI pane and is exempt from both the folder-trust and dev-channel 2-step approvals** (do not pull it into the spawn-ritual inversion).
> - **Error branching (default = broker extended codes included)**: in addition to the shared codes (`pane_not_found` / `last_pane` / `invalid-params`, Surface 6), the default broker may return broker-specific `[token_invalid]` / `[session_invalid]` / `[tool_not_authorized]` / `[no_backend]` (= adapter_unavailable) / `[nudge_failed]` / `[peer_not_found]` / `[name_taken]` / `[unknown_tool]` (unknown codes escalate via the default branch). With `ORG_TRANSPORT=renga`, broker-specific codes never occur — only shared codes + renga-specific codes.
>
> The contract SoT is [`docs/contracts/backend-interface-contract.md`](../../../docs/contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery, ratified 2026-06-14) + the tail "Ratified amendment (2026-06-15): push-primary delivery" (S3; **broker push-primary is the default contract**, pull is retained as structural fallback). Design SoT is transport-lab `docs/design/broker-native-roles.md` §9 (push-primary) / `docs/design/ja-migration-plan.md` §5 and §8. **The opt-in `renga` is not deleted and is maintained as a permanently-available fallback** (the revert safety net). Broker actual-run (dogfood) is in scope for Epic #6 Issue G and is **not** the default operational route in this file (**Two-frame note on "default" (Refs #604)**: "default `broker`" here refers to the **code-default** frame — `tools/transport.py: DEFAULT_TRANSPORT` has been flipped to `broker` in runtime 0.1.28 (Epic #586), and the ja generator / `transport.resolve()` render against this code frame, so the generated surface displays it this way. There is a separate **operational-default** frame in which the operational default route is `renga`, because broker actual-run dogfood is not yet activated through Epic #6 Issue G. The two frames refer to different objects (code constant vs. operational route) and do not contradict each other. The overview is in root [`CLAUDE.md`](../../../CLAUDE.md), section "Transport — both backends".)

## Step 1: trigger condition (state-based)

If neither condition below is met, **exit immediately** (no log, no report).

```bash
# pending entries in the candidate queue
cand_count=$(grep -c '^- \*\*status\*\*: pending' knowledge/skill-candidates.md 2>/dev/null || echo 0)

# work-skill count (excluding org-*; aligns with the work-skill search surface that is the noise source)
work_skill_count=$(find .claude/skills -maxdepth 2 -name SKILL.md \
  | grep -v '/org-' | wc -l)
```

- Continue if `cand_count >= 5` **or** `work_skill_count >= 20`.
- Otherwise exit (no report needed).

Rationale for the numbers: N=5 / M=20 are the defaults. Adjust via PR if operations show drift.
Why exclude `org-*`: the noise source is `org-delegate`'s work-skill search; the count of `org-*` skills does not directly affect search noise.

> **Count-definition sync (important)**: the two count definitions above (pending = line match
> on `^- \*\*status\*\*: pending`; work-skill = `find .claude/skills -maxdepth 2 -name SKILL.md
> | grep -v '/org-'`) must be kept in **exact agreement** with the on-demand curator's
> activation check [`tools/check_curate_threshold.py`](../../../tools/check_curate_threshold.py).
> If you change one, update both
> (the parity test in `tools/test_check_curate_threshold.py` detects drift).

## Step 2: enumerate deprecation candidates

For each skill, evaluate the items below. Use **only what is observable today** for the mechanical check; defer everything else as "needs review" for human judgment. See `references/audit-checklist.md` for details.

Observable (mechanical):
- An obvious mismatch between the description and the body's Step sections (self-contained inside the skill).
- grep `knowledge/curated/` / `knowledge/raw/` / `.state/workers/` for `{skill-name}` and find 0 mentions in the last 90 days (within this project's observable surface).

Not observable ("needs review"; not usable for deprecation alone):
- `org-delegate` only embeds a matched work-skill in instructions; "did the worker actually adopt it" is not persisted.
  → reference search is only "showed up in search" granularity.
- Many existing skills do not have `origin.task_id`, so there is no reuse-detection anchor.
  → the "not reused" verdict applies only to origin-tagged skills; skip otherwise.

**Do not decide deprecation. Just put it on the proposal list** for the human to make the final call.
audit-checklist.md sections 1.1 / 1.2 / 1.3 follow the same policy.

## Step 3: enumerate consolidation candidates

For each pair of skills, check:

- The principal terms (verb / object) of the description overlap.
- triggers (or trigger conditions in the description) overlap.
- One is a specialization of the other and could be replaced via a parameter.

Pairs that look like duplicates are listed as "consolidation candidates". The actual consolidation decision is made by the human; this step lists candidates only.

## Step 4: enumerate owner-missing skills

Read every skill's SKILL.md frontmatter and check:

- Skills missing both `owner:` and `maintainer:` fields.
- Or those that have one of them but with an empty value.

These are listed as "owner missing".
All existing skills in this project are currently without an owner; the first audit run is expected to produce a single batch proposal for them.

## Step 5: report

Send to the Lead Claude via `renga-peers` `send_message(to_id="secretary", ...)`.

```
[skill-audit] inventory result
- Deprecation candidates: {n} ({skill-name} list)
- Consolidation candidates: {m} pair(s) ({skill-a} × {skill-b} list)
- Owner missing: {k} ({skill-name} list)

Trigger: cand_count={cand_count} / skill_count={skill_count}
Detail: see the list at the end of this message for evidence.

After human approval, perform deletion / consolidation / owner annotation.
No automatic changes have been made.
```

Even if the candidates are empty (clean state), still report: "ran inventory, no proposals". Since the next run only occurs when the threshold trips, recording "we ran" is still useful.

## Trigger paths

This skill does not fire autonomously. It runs from one of:

1. `org-curate` Step 6 (recommended path). The flow after the on-demand change:
   the dispatcher runs `tools/check_curate_threshold.py` at worker close, and when
   `skill_candidates_pending` / `work_skill_count` appear in `reasons[]`, a curator is
   launched temporarily and org-curate Step 6 fires this skill.
2. The Lead manually invokes it after looking at `skill-candidates.md`.
3. The human asks "do an inventory".

Never fired from a time-based trigger like `/loop`.

## Why no automatic changes

- A wrong deprecation creates "no skill is available" on the `org-delegate` side (worse delegation precision).
- Consolidation requires aligning descriptions / triggers / procedures; cannot be done mechanically.
- Owner annotation is the lightest human-confirmation operation (automating only this part has a small payoff).

So this skill **stops at the proposal**; changes happen via human approval and the Lead's manual edits.
