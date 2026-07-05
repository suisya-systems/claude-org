# verify integration: applicability classifier + evidence transcription

The details of the verify integration in [`/org-conveyor`](../SKILL.md) Step 2-6. Defines the decision that makes verify **conditionally required** (the applicability classifier) and the discipline for mechanically transcribing its result into the PR body's `## Test plan`. The aim is to prevent "touching app code but flowing a PR through without confirming behavior", while not forcing meaningless verify on docs / config-only diffs.

> **Executor (important)**: `/verify` is a Claude Code **built-in skill** (it launches the app and observes runtime behavior). It is the **worker who runs verify**, and it runs **inside the worker's worktree where the app + the change in question live**. conveyor (the Lead session, at the repository root, holding no worker changes) **does not launch the app** — conveyor's responsibility is only the two things: (1) gate whether verify is required via the applicability classifier, (2) transcribe the evidence the worker returned into PR `## Test plan`. If the built-in `/verify` does not fit the app form, the worker directly runs an equivalent app-launch command and leaves the trace ([`.claude/skills/org-conveyor/SKILL.md`](../SKILL.md) Step 2-6).

## applicability classifier (decided by diff touch domain)

The worker declares the **diff's touch domain** in the completion report, together with the `git diff --name-only <base>..HEAD` output obtained in its own worktree (the worker is the primary source; only the worker has HEAD on the worker's branch). conveyor classifies that declared file list by path and decides deterministically whether `/verify` is required. When the worker's branch is visible locally from the Lead session (object-store-shared Pattern B worktree, etc.), conveyor also re-runs `git diff --name-only <base>..<branch>` itself and cross-checks against the declaration (read-only corroboration). When it is not visible locally (separate clone / before push, etc.), cross-check with the changed-file list after PR creation (`gh pr view --json files`, via [`/org-pull-request`](../../org-pull-request/SKILL.md)).

| touch domain | example | `/verify` |
|---|---|---|
| **app code** | source that changes app implementation / runtime behavior (`*.py` / `*.ts` implementation, CLI, server, tool bodies, hooks, etc.) | **required** |
| **docs** | `*.md` / `docs/` / comments only | not needed |
| **config** | config values / lint / CI config / dependency pins (things that do not change behavior) | not needed (config that changes behavior is treated as app code) |
| **fixture / test data** | golden / fixture / sample-data updates only | not needed (logic changes in the test body itself are treated as app code) |

Decision discipline:

- **Mixed (app code + docs/config/fixture)** → the presence of app code dominates. **`/verify` required**.
- **No app code, only docs / config / fixture** → `/verify` not needed (record the reason in one line in the Test plan: e.g. "docs-only, no behavior change").
- **Undecidable** (the touch domain conflicts with the path classification / it is not mechanically determinable which way to fall / app code vs config is ambiguous) → **halt as a scope edge** ([`.claude/skills/org-conveyor/SKILL.md`](../SKILL.md) INV-2). Better to raise it to the human than to wrongly skip verify and miss a behavior regression.
- A **skill/docs task with no executable app**, such as this skill (editing claude-org's own `.claude/`), can fall into docs treatment, but in that case state it explicitly in the verify policy (the `verify policy` of [`.claude/skills/org-conveyor/references/scope-contract.md`](scope-contract.md)) and leave a not-needed reason in the Test plan such as "skill prose only, no runtime behavior".

> The classifier puts path-based deterministic decision first, and if it conflicts with the worker's declaration, it makes **the conflict itself a halt trigger** (do not take the declaration at face value / do not take the path classification at face value — a double check).

## Evidence transcription (auto-transcribed into PR `## Test plan`)

Once you have run `/verify` (or decided it is not needed), include a reproducible trace in the completion report and, at PR creation via [`/org-pull-request`](../../org-pull-request/SKILL.md) 2b-i, **transcribe it as-is** into the PR body's `## Test plan` section. The requirement is to leave the **repro command and observed result** so the Lead need not read the code closely and a future reviewer can re-test.

Evidence to include in the completion report (prepared by the worker, transcribed by conveyor):

- **repro command**: the command actually run in verify (show dynamic ports by env name; [`.claude/skills/org-conveyor/references/dynamic-ports.md`](dynamic-ports.md)).
- **observed result**: the gist of the command output / exit code / the save path of a screenshot (for UI verify).
- **applicability decision**: whether app code was touched and the classifier's conclusion (required execution or not-needed reason).

Form transcribed into the PR body (`## Test plan`):

````markdown
## Test plan

- applicability: changed app code (`tools/foo.py`) → /verify required
- repro:
  ```
  PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("",0));print(s.getsockname()[1]);s.close()')
  PORT="$PORT" tools/run.sh &       # dynamic port (references/dynamic-ports.md)
  curl -s "localhost:$PORT/health"  # → {"status":"ok"}
  ```
- result: health 200 / exit code 0 / no regression
- screenshot: .state/conveyor/evidence/<task_id>/health.png   # for UI
````

When docs / config / fixture only and verify was not needed, still leave a **one-line not-needed reason** in the Test plan (do not leave it blank):

```markdown
## Test plan

- applicability: docs-only (`.claude/skills/**/*.md` only) → no runtime behavior change, /verify not needed
```

> Transcription is **machine transcription** (the Lead formats and pastes the trace the worker produced), not the Lead fabricating or filling in evidence. If evidence is missing, ask the worker to supply it as ordinary review feedback ([`/org-pull-request`](../../org-pull-request/SKILL.md) 2c).
