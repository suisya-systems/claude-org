---
name: secretary-handover
description: >
  To avoid continuing a session while the Secretary's context stays bloated,
  write recent interactions, in-flight work, and org state to a handover file,
  then prepare to start a fresh Secretary session via /clear → /secretary-resume.
  Use when the user says "refresh", "I want to hand over the Secretary",
  or "clean up the context", or when the Secretary itself judges that
  context has grown long.
effort: low
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash(py -3 tools/journal_append.py:*)
  - Bash(bash tools/journal_append.sh:*)
---

# secretary-handover: hand off the Secretary

Without dragging the Secretary session on, produce a handover file that
carries over org-member awareness and recent interactions to the next session.
After writing, guide the user through `/clear` → `/secretary-resume`.

> **Key preconditions**:
> - Keep the Dispatcher / Curator / Worker panes alive. `/clear` only resets
>   the Secretary Claude's context, so as long as the new session can recover
>   from state.db and the handover file, the org continues uninterrupted.
> - The state DB (`.state/state.db`) is the single SoT. Pane identities and
>   work state can be drawn from there. The handover file is for things that
>   do not fit into structured data — "the temperature of the conversation",
>   human-side agreements, in-progress judgments, and so on.

## Step 1: collect what to hand over

Before writing, extract the following from the Secretary's (your) context:

1. **Recent agreements / decisions with the human**
   - Adopted directions, rejected options, items still under consideration.
2. **In-flight work**
   - Workers currently dispatched, their task_id, the latest progress status.
3. **Pending Decisions (sent to the human, awaiting reply)**
   - If `.state/pending_decisions.json` exists, read it alongside and note the
     diff between the register and your context.
4. **Next action (from the Secretary's POV)**
   - What you should do next, whose reply you are waiting on.
5. **Excerpts of recent important exchanges**
   - About 3–6 items: a decisive line the user said, a proposal you made
     that was agreed to, etc.

## Step 2: pull structured info from state.db

Embed as reference in the handover. Write the dump to a sandbox-writable
location under `$TMPDIR` (falling back to `/tmp` if unset):

```bash
python3 -c "
from tools.state_db import connect
from tools.state_db.queries import get_org_state_summary
import json, os
conn = connect('.state/state.db')
out_path = os.path.join(os.environ.get('TMPDIR', '/tmp'), 'secretary-handover-state.json')
with open(out_path, 'w') as f:
    json.dump(get_org_state_summary(conn), f, ensure_ascii=False, indent=2, default=str)
print(out_path)
"
```

Shell redirection `> /tmp/...` would fail in sandbox environments where
`/tmp` is read-only. Resolving `TMPDIR` on the Python side before
`open(..., 'w')` is the safe form.

Pull the following out of the result:
- `session.status` / `session.objective`
- `session.dispatcher_pane_id` / `session.dispatcher_peer_id`
- `session.curator_pane_id` / `session.curator_peer_id`
  (**null is the normal state**. The curator is on-demand and not resident;
  org-start explicitly clears these via `StateWriter.CLEAR`. Do not treat
  null as "missing data")
- `active_runs[]` (in-flight tasks)
- `active_worker_dirs[]` (worker directories still alive)
- The top 3–5 entries of `recent_events`

## Step 3: write the handover file

Destination: `.state/secretary-handover.md`.

If a file already exists, back it up to `.state/secretary-handover.prev.md`
before overwriting:

```bash
[ -f .state/secretary-handover.md ] && cp .state/secretary-handover.md .state/secretary-handover.prev.md
```

Format (YAML frontmatter + markdown):

```markdown
---
created_at: <UTC ISO8601>
session_status: <ACTIVE | IDLE | SUSPENDED>
session_objective: <one-line summary or null>
dispatcher_pane: <pane_id> / peer=<peer_id>
curator_pane: null  # residency retired (on-demand model); null is normal
---

# Secretary Handover

## Recent agreements / decisions with the human
- ...

## In-flight work
- worker-<task_id> (<worker_dir>): <latest state / what it is waiting on>
- ...

## Pending Decisions (sent to the human, awaiting reply)
- ...
(If none, write "none" explicitly. Do not leave empty.)

## Next action (Secretary's POV)
- ...

## Excerpts of recent important exchanges
- user: "..."
- secretary: "..."
- ...

## Reference: state.db snapshot
(Briefly transcribe the active_runs / recent_events fetched in Step 2.
 The full data still lives in `.state/state.db`, so keep this minimal.)
```

**Writing notes**:
- Write as a "note to next-you", not a "past log". For example:
  "user wants to proceed with option B", "waiting on retro-gate ack from the worker".
- Never write secrets / tokens / passwords.
- Assume humans will read the file too.

## Step 4: record the event

```bash
py -3 tools/journal_append.py secretary_handover \
    --json '{"reason": "context_compaction", "active_workers": [...]}' 2>/dev/null \
    || echo "(journal_append unavailable; skipping)"
```

## Step 5: guide the user

Close out with this message:

```
I've written the Secretary handover to `.state/secretary-handover.md`.
Please run /clear now to reset the context.
Once the new Secretary session starts, run /secretary-resume — it will
load the handover file and resume with current situational awareness.

The Dispatcher / Curator / Worker panes keep running as-is, so the
organization is not interrupted.
```

**Things the Secretary must not do**:
- Do not run `/clear` yourself (it is a Claude Code command typed by the user).
- Do not send SHUTDOWN to the Dispatcher or Curator (this is not /org-suspend;
  the panes stay alive).
