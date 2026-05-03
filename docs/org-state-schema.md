# org-state.json schema definition

## Overview

`.state/org-state.json` is the machine-readable snapshot of `.state/org-state.md`.
It was introduced so that programmatic consumers — the dashboard (`dashboard/server.py`) and others — can prefer reading JSON.

### Source-of-truth rule

**Markdown is canonical; JSON is derived.**

- `org-state.md` is always canonical. Claude Code instances read and write it directly.
- `org-state.json` is a derived file. `org_state_converter.py` generates it.
- If you edit `org-state.md` by hand, re-run the converter afterwards.
- When the two disagree, trust `org-state.md`.

### Regenerating the JSON

```bash
py -3 dashboard/org_state_converter.py      # Windows
python3 dashboard/org_state_converter.py     # Mac/Linux
```

### Update points

After the operations below, run the converter to update the JSON:

| Operation | Skill | What is updated |
|---|---|---|
| Worker dispatch | org-delegate Step 4 | Current Objective, Active Work Items, Worker Directory Registry |
| Status change | org-delegate Step 5 | Work Item status (REVIEW/COMPLETED/IN_PROGRESS) |
| Organization suspend | org-suspend Phase 3 | Status=SUSPENDED, Updated, Work Items, Resume Instructions |
| Organization resume | org-resume Phase 4 | Status=ACTIVE |
| Boot (Dispatcher / Curator records) | org-start Steps 2-3 | Dispatcher / Curator peer ID and pane name |

---

## Schema (version 1)

```json
{
  "version": 1,
  "updated": "<ISO 8601 timestamp | null>",
  "status": "ACTIVE | SUSPENDED | IDLE",
  "currentObjective": "<string | null>",
  "workItems": [
    {
      "id": "<kebab-case task ID>",
      "title": "<task title (may be Japanese)>",
      "status": "IN_PROGRESS | COMPLETED | PENDING | BLOCKED | REVIEW | ABANDONED",
      "progress": "<latest progress note | null>",
      "worker": "<peer ID | null>"
    }
  ],
  "workerDirectoryRegistry": [
    {
      "taskId": "<task ID>",
      "pattern": "A | B | C",
      "directory": "<absolute path>",
      "project": "<project name | ->",
      "status": "in_use | available"
    }
  ],
  "dispatcher": {
    "peerId": "<peer ID>",
    "paneId": "<renga pane name>"
  },
  "curator": {
    "peerId": "<peer ID>",
    "paneId": "<renga pane name>"
  },
  "resumeInstructions": "<free text | null>"
}
```

---

## Field descriptions

### Top level

| Field | Type | Description |
|---|---|---|
| `version` | `integer` | Schema version. Currently `1`. Bumped on future incompatible changes |
| `updated` | `string \| null` | The value of `Updated:` in org-state.md (ISO 8601). `null` if unset |
| `status` | `string` | Organization state. `ACTIVE` (running) / `SUSPENDED` (suspended) / `IDLE` (unused) |
| `currentObjective` | `string \| null` | Current objective (the `Current Objective:` field). `null` if unset |
| `workItems` | `array` | List of work items |
| `workerDirectoryRegistry` | `array` | Worker-directory reuse table |
| `dispatcher` | `object \| null` | Dispatcher's peer and pane info. `null` if unrecorded |
| `curator` | `object \| null` | Curator's peer and pane info. `null` if unrecorded |
| `resumeInstructions` | `string \| null` | Notes for resume (written by org-suspend). `null` if absent |

### workItems element

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Task ID (kebab-case English). Examples: `blog-redesign`, `data-analysis` |
| `title` | `string` | Task title (Japanese is allowed). Taken from `- {id}: {title} [{status}]` in org-state.md |
| `status` | `string` | Task status (see below) |
| `progress` | `string \| null` | Latest progress note (the `- 結果:` sub-item). `null` if absent |
| `worker` | `string \| null` | Assigned Worker's peer ID (the `- ワーカー:` sub-item). `null` if absent |

**status values:**

| Value | Meaning |
|---|---|
| `IN_PROGRESS` | In progress |
| `COMPLETED` | Completed (approved by the human) |
| `PENDING` | Pending (not yet started) |
| `BLOCKED` | Blocked (dependency or issue) |
| `REVIEW` | Under review (Worker has reported completion; awaiting human approval) |
| `ABANDONED` | Abandoned |

### workerDirectoryRegistry element

| Field | Type | Description |
|---|---|---|
| `taskId` | `string` | Task ID using the directory |
| `pattern` | `string` | Directory pattern: `A` (project directory) / `B` (worktree) / `C` (ephemeral) |
| `directory` | `string` | Absolute path of the Worker directory |
| `project` | `string` | Project name. `-` for ephemeral |
| `status` | `string` | `in_use` (active) / `available` (completed, reusable) |

### `dispatcher` / `curator`

| Field | Type | Description |
|---|---|---|
| `peerId` | `string` | renga-peers pane name (`worker-{task_id}` / `dispatcher` / `curator` form). Pass to `mcp__renga-peers__send_message` as `to_id` |
| `paneId` | `string` | renga pane name (the value passed via `--id`, e.g. `dispatcher`, `curator`). Older WezTerm builds stored a numeric pane-id; after migrating to renga this became a stable name. In the current spec this is often the same value as `peerId` |

---

## Integration with the dashboard

`dashboard/server.py` reads org-state in this order of preference:

1. If `.state/org-state.json` exists and its mtime is at least `.state/org-state.md`'s → use the JSON
2. Otherwise → parse `.state/org-state.md` with regex (fallback)

This design works correctly even when the converter has not been run, or when the JSON is stale.

---

## Version history

| Version | Changes |
|---|---|
| 1 | Initial version. Introduced in Issue #20 |
