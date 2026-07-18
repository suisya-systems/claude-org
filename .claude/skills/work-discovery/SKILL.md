---
name: work-discovery
description: >
  Triage open Issues and have the Lead present "next-work candidates (N items + 1 recommendation)" to the human.
  Run the deterministic tool tools/work_discovery_scan.py once and stop after rendering the
  candidate JSON in the human-readable format defined by design doc §5.2 (propose-only).
  The trigger is restricted to the Lead. Manual / event-driven only (no resident /loop).
  Fires when the Lead manually invokes for "show next-work candidates", "triage", "what's next?",
  or for proactive next-dispatch after a PR merge.
effort: low
allowed-tools:
  - Bash(python3 tools/work_discovery_repos.py:*)
  - Bash(py -3 tools/work_discovery_repos.py:*)
  - Bash(python3 tools/work_discovery_scan.py:*)
  - Bash(py -3 tools/work_discovery_scan.py:*)
---

# work-discovery: triage presentation of next-work candidates (propose only)

Triage open Issues and have **the Lead present** dependency-cleared candidates to the human in the form of "N items + 1 recommendation".
The decision (scan / ranking) is owned by a deterministic tool; this skill only formats that output into a human-readable presentation.
**Once candidates are presented, stop. The decision to start work is made by the human.**

- Primary design reference: [`docs/design/work-discovery-triage.md`](../../../docs/design/work-discovery-triage.md)
  (§5.2 human-readable rendering / §6.2 Plan B local skill / §7 invariants INV-1 through INV-5).
- Computation-layer tool: [`tools/work_discovery_scan.py`](../../../tools/work_discovery_scan.py) (read-only, zero side effects. The computation layer that this skill consumes).
- Repo-set resolver tool: [`tools/work_discovery_repos.py`](../../../tools/work_discovery_repos.py) (read-only. Deterministically derives the `--repo owner/repo` set passed to scan from the triage opt-in column of `registry/projects.md` + always-include home repo. Design §10.4).
- This skill is Plan B (manual entry). Resident triggers (Dispatcher extension) and post-merge integration belong to a separate Phase (separate task).

## Trigger subject and triggers (strict)

- **Only the Lead can trigger this** (design §6.2). Already-dispatched Workers do not trigger this skill.
  A Worker triggering "next work" exploration outside its own task would break "1 worker = 1 task = 1 scope"
  (see role boundaries in [`CLAUDE.md`](../../../CLAUDE.md)).
- **Do not attach a resident `/loop`** (design §6.2 note 1). Run only manually, or via event-driven entry such as
  proactive next-dispatch after a PR merge. Time-based resident triggers are avoided because they pollute the
  presentation on days with no change.
- Resident triggers (worker close) are the responsibility of a separate plan (Dispatcher extension, separate Phase), not this skill.

## Invariants (must not be broken / design §7)

- **INV-1 propose-only**: The output of this skill is "candidate list + presentation" only. **Stop** after generation.
  Do **not** perform spawn / delegate / branch creation / commit / PR / writes to Issues or PRs.
  (The fact that allowed-tools is narrowed to just the read-only commands of repo resolution (`tools/work_discovery_repos.py`)
  and scan (`tools/work_discovery_scan.py`) is also a mechanical enforcement of this invariant. The resolver, like scan, is
  read-only — it only performs `git remote get-url` and an optional `gh repo view` read, and does no writes, spawns, or git changes.)
- **INV-2 the start decision requires a human gate**: Candidate selection is human-only. The selected candidate enters
  the normal delegation flow **from Step 0 of the existing [`/org-delegate`](../org-delegate/SKILL.md)**.
  It is forbidden for this skill to call org-delegate itself. Auto-start of the recommendation (rank 1) is also forbidden.
- **INV-3 do not auto-commit / auto-PR**: Do not modify the source tree, Issues, PRs, or git (commit / branch / push)
  in any way. Even when persisting triage results into the source as an ongoing practice, that must be a separate task
  judged by a human; this skill must not do it automatically.
- **INV-4 via the Lead**: Present to the human inside the Lead session's conversation. Do not write directly to
  human-visible surfaces such as GitHub.
- **INV-5 the Secretary does not investigate**: scan is a deterministic tool execution, not "investigation". If
  feasibility deep-dives or design are required for a candidate, those are delegated Worker tasks after the human gate.
  Do not self-investigate or implement the contents of candidates inside this skill.

## Procedure

### Step 1 — resolve the repo set, then run scan once

In this skill, Claude runs two commands **in sequence** (this is not a shell script, so do not use the `$(...)`
assignment form — allowed-tools grants permission by each command's leading prefix, and an assignment wrapper like
`REPO_FLAGS=$(python3 …)` does not match the allowed prefixes `python3 tools/work_discovery_repos.py:*` / `py -3 …`).
Use `python3` on POSIX, `py -3` on Windows.

**1a. Obtain the `--repo` flags from the resolver** (deterministically derives the `--repo owner/repo` sequence
from the triage opt-in column of `registry/projects.md` + always-include home repo. Design §10.4):

```bash
python3 tools/work_discovery_repos.py --format flags
```

- stdout is a single line `--repo a/b --repo c/d`. In the default state with no triage opt-in rows, it is just the
  home repo (a single `--repo <home>` = identical behavior to the conventional single-repo scan). **Skip info and
  signals go to stderr** (stdout stays flags-pure). Running it again with `--format json` and noting `skipped` /
  `signals` gives you material for the audit presentation in Step 3.
- **If the resolver returns exit 2, do not run the 1b scan**. Exit 2 is the abnormal case "the home repo could not be
  resolved via either git origin or `gh repo view`, and there are no valid triage opt-in rows, so repos is empty".
  In this case pass the stderr `error:` line to the human as-is and stop (**running scan with empty flags means no
  `--repo` = a silent fallback to gh's implicit current-repo scan, hiding the resolution failure**). Proceed to 1b
  **only** on exit 0.

**1b. Run scan, pasting in the stdout (`--repo …`) from 1a** (only when exit 0):

```bash
python3 tools/work_discovery_scan.py --trigger manual --repo OWNER/REPO
```

(`--repo OWNER/REPO` above is a placeholder, not the command to run: always replace it by pasting the stdout of 1a
verbatim — do not hand-type a slug. When the opt-in spans multiple repos, multiple `--repo` flags appear in sequence.)
- The resolver is read-only (`git remote get-url` and an optional `gh repo view` read only. No writes, spawns, or git changes).
- `--trigger` is a context label. Use `manual` for manual triggering. When called from proactive next-dispatch
  after a PR merge, pass `--trigger post_merge`, and if possible also pass `--free-panes <number of free panes>`
  (with free slots, the rank of `parallelizable` candidates rises).
- The default candidate cap is `--top-n 3`. Pass `--repo` explicitly with the resolver's flags (the home repo is
  always included). When the triage opt-in spans multiple repos, multiple `--repo` flags appear and the scan becomes
  a cross-repo triage (design §10 / §10.4).
- The tool prints **a single JSON object** to stdout and **branches by exit code** (look at the exit code, not whether JSON parses).
- The tool is read-only (only read-side subcommands of `gh`). This skill must produce no side effects beyond the tool.

### Step 2 — branch by exit code

| exit | status | Lead action |
|---|---|---|
| `0` | `no_candidates` | Zero candidates. Tell the human "there are currently no candidates (dependency-cleared) ready to start." If `excluded_blocked[]` is non-empty, **always enumerate** them in the same "Excluded (dependencies not resolved): #<issue> (<note>)" form as Step 3 (so the human can audit "what was inspected to arrive at zero". design §5.2 "always show the excluded slot" / §5.1). Furthermore, if `input_truncated.open_issues` / `open_prs` is `true` (fetch cap reached), **always append** the same "Issue/PR fetch hit the cap so candidates may not be exhaustive" as Step 3 (to prevent a non-exhaustive scan from being misread as "exhausted and got zero"). **Stop here**. |
| `10` | `candidates_found` | Render in the §5.2 format in Step 3 and present. |
| `2` | `error` | Pass the content of the JSON `error` field directly to the human and report "triage could not be executed". Do not fabricate candidates. **Stop here**. |

> Exit `1` is intentionally unassigned (to prevent Python's default uncaught-exception exit from colliding with this skill — a crash being misread as "no candidates"). If anything other than `0/10/2` is returned, treat as error and escalate to the human.

### Step 3 — present to the human in §5.2 format (when exit 10)

Treat the JSON as the SoT and format into the human-readable format of design §5.2. Stay compatible with the current
proactive next-dispatch convention (2–4 candidates + 1 recommendation, decide by number) so the human's operations do not change.

```text
Next-work candidates (triage result / proposal only / starting is your decision):

1. [Recommended] #531 Add retry to uploader (priority high / effort S(estimated) / dependencies cleared / parallelizable(estimated) / triggered by recent merge(estimated))
   └ Follow-up to recent merge #528 / parallelizable (fills a free pane) / effort S(estimated) / dependencies cleared
2. #533 Refactor config loader (priority medium / effort M / dependencies cleared / parallelizable(estimated))

Excluded (dependencies not resolved): #540 (because #537 is still open)

Specify the number to start. After the start decision, /org-delegate will be run.
```

(In the above example, #531 has `effort_estimated: true` so it shows `effort S(estimated)`, while #533 derives from a `size:M` label with `effort_estimated: false` and shows `effort M` (no `(estimated)`). `triggered by recent merge(estimated)` appears only on #531 because `unblocked_by_recent_merge == true`.)

Rendering rules (JSON field → display):

- Number `candidates[]` in ascending `rank` order. Skeleton of each line: `<issue-ref> <title> (priority <priority> / effort <effort>[(estimated)] / dependencies cleared[ / parallelizable(estimated)][ / triggered by recent merge(estimated)])`. Tokens wrapped in `[...]` are conditional (see below).
- **Repo qualification of `<issue-ref>` (cross-repo scan, design §5.2 / §10.4)**: if the candidate's `repo` is not `null` (a cross-repo scan spanning multiple repos = the resolver returned multiple repos via triage opt-in), display `<repo>#<issue>` (e.g. `aainc/token-tracking#42`) instead of `#<issue>`, removing ambiguity about the repo of origin. In a single-repo scan (`repo: null`), display `#<issue>` as before. The excluded slot (below) and the recommendation are qualified by the same rule. The same rule also applies to displaying `blocking_refs` (home references stay bare `#N`; cross-repo references are `owner/repo#N`. Design §5.1).
- **Exactly one recommendation**. Prefix `[Recommended]` to the candidate matching the `(repo, issue)` pair of `recommendation`, and immediately below it add `└ <recommendation.reason>` (in cross-repo, the `issue` number alone can collide — `ja#60` vs `runtime#60` — so match on `repo` as well).
- **Append `(estimated)` to estimated axes** (to prevent the human from misreading "the machine decided" and handing the start decision over to the mechanism (design §4.4)). Add conditionally per axis based on flags:
  - **effort**: if `effort_estimated == true` (heuristic estimate), display `effort <effort>(estimated)`. If `false` (derived from a `size:S/M/L` label), display `effort <effort>` without `(estimated)`.
  - **parallelizable / triggered by recent merge**: emit the corresponding token (`parallelizable` / `triggered by recent merge`) only when the flag `parallelizable` / `unblocked_by_recent_merge` is `true` (if `false`, omit the notation entirely). Since the corresponding `*_estimated` is always estimated (`true`) for these, they always carry `(estimated)` when emitted. "Triggered by recent merge" also appears naturally inside `recommendation.reason` (e.g., "follow-up to recent merge #N").
- **Always show the excluded slot**: list `excluded_blocked[]` in the form "Excluded (dependencies not resolved): #<issue> (<note>)" (for auditability and the reassurance of "I saw it all, then chose N"). If empty, omit the excluded line.
- **No silent truncation**: if `truncated_count` is 1 or more, append one line:
  "(There are <truncated_count> other dependency-cleared but lower-ranked candidates.)"
  If `input_truncated`'s `open_issues` / `open_prs` is `true` (fetch cap reached), also append "Issue/PR fetch hit the cap so candidates may not be exhaustive".
- **Attach the resolver's skips / signals for audit (cross-repo)**: if the resolver JSON noted in Step 1 has a non-empty
  `skipped[]` (rows that are triage opt-in but whose path column is not a GitHub URL, so owner/repo could not be derived
  and the row was excluded from the scan targets) or `signals[]` (home repo resolution fell back / failed, etc.), append
  them at the end of the candidate presentation as "Scan-target resolution notes:" in one to a few lines (e.g. "triage
  opt-in row '<nickname>' excluded from scan targets because its path is not a GitHub URL (skip)"). The purpose is to let
  the human audit which repos the candidates came from. Omit when empty.
- **Always, every time** emit "proposal only / starting is your decision" (the operational manifestation of INV-1), and at the end emit "specify by number → after the start decision, /org-delegate".

### Step 4 — stop

Once candidates are presented, **end there**. Number selection is performed by the human. When the human picks a number,
that start happens outside this skill, **from Step 0 of [`/org-delegate`](../org-delegate/SKILL.md)** (INV-2). This skill
does not call org-delegate, does not spawn, does not commit / PR.

## Path resolution

- The `tools/...` / `docs/...` notations in this skill are **relative to the repository root**. The Lead session's CWD
  is the repository root (`/home/happy_ryo/work/org/claude-org-ja`), so they can be executed as-is. When called from
  a different CWD, read them as root-relative.
- On Windows, read `python3` as `py -3` (both forms are registered in allowed-tools).

## Things this skill does not do (INV summary)

- Auto-start of candidates / auto-delegation of rank 1 (INV-1 / INV-2).
- spawn / delegate / branch / commit / PR / Issue or PR writes (INV-1 / INV-3).
- Direct presentation to GitHub etc. (always via the Lead's conversation. INV-4).
- Self-investigation or implementation of candidate content (delegated tasks after the human gate. INV-5).
- Time-based triggering via a resident `/loop` (design §6.2 note 1).
- Triggering by a Worker (the trigger subject is restricted to the Lead. design §6.2).
