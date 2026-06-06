# claude-org — Technical Overview

A self-improving AI organization platform that coordinates multiple Claude Code instances.
Humans only interact with the Lead, while Workers are automatically dispatched and managed behind the scenes.

---

## Architecture

### Instance Configuration

```
┌──────────────┬──────────┬──────────┐
│              │ Worker1  │ Worker4  │
│  Secretary   │ Worker2  │ Worker5  │
│  (large)     │ Worker3  │ Worker6  │
├───────┬──────┤          │          │
│Dispatcher│Curat.│  ...     │  ...     │
└───────┴──────┴──────────┴──────────┘
```

| Instance | Resident | Role | Allowed Tools |
|---|---|---|---|
| **Lead** | Yes | User interaction, task breakdown, state management | All tools (but actual work is delegated) |
| **Dispatcher** | Yes | Handles pane startup, instruction delivery, and state logging on behalf of others | Bash, Read, Write, Edit, Glob, Grep, Skill, renga-peers |
| **Curator** | No (on demand) | Launched temporarily when the threshold check fires at worker close; runs `/org-curate` once | Read, Write, Edit, Glob, Grep, Skill, renga-peers |
| **Worker** | No | Execution work (code edits, research, testing, etc.) | Bash, Read, Write, Edit, Glob, Grep, Agent, Skill, renga-peers |

### Communication

- **Between instances**: `renga-peers` MCP (bidirectional messaging between Claudes in the same tab, with push-based channel notifications). Use `send_message` / `list_peers` / `check_messages` / `set_summary`, and use pane names for peer IDs (`secretary` / `dispatcher` / `curator` / `worker-{task_id}`)
- **Pane management**: `renga-peers` MCP (`spawn_pane` / `spawn_claude_pane` / `close_pane` / `list_panes` / `new_tab` / `focus_pane` / `inspect_pane` / `send_keys` / `poll_events` / `set_pane_identity`, etc.; 14 tools in renga 0.18.0+). Role/worker startup is standardized on the structured fields of `spawn_claude_pane` (`cwd` / `permission_mode` / `model` / `args[]`) (Issue #58). The `cd X && claude ...` composition pattern has been removed
- **Instruction duplication**: CLAUDE.md (persistent baseline) + `renga-peers` messages (real-time supplements)

### State Management

The org state is held in **`.state/state.db` (SQLite) as the single source of truth** (M4 cutover, Issues #267 / #284). Refer to [`docs/contracts/state-semantics-contract.md`](contracts/state-semantics-contract.md) as the canonical reference for the vocabulary, transition rules, and derived artifacts.

| Layer | Path | Purpose | Writer / regenerator |
|---|---|---|---|
| **state.db** (authoritative) | `.state/state.db` | SoT for `runs` / `org_sessions` / `worker_dirs` / `events` | `tools/state_db.writer.StateWriter` (`upsert_run` / `update_run_status` etc.) and `tools/journal_append.sh` / `tools/journal_append.py` (DB-routed since M4) |
| **`.state/org-state.md`** (derived) | repo-relative | Human-readable snapshot (referenced by `/org-resume`, retros, etc.). **The dashboard does not consult it** (the dashboard reads state.db directly) | The `StateWriter.transaction()` post-commit hook regenerates it via `tools/state_db.snapshotter`. Manual edits are flagged by `tools/state_db.drift_check` |
| **`.state/org-state.prev.md`** (derived) | repo-relative | Backup of `org-state.md` taken just before `/org-suspend` | `/org-suspend` Phase 3 copies `org-state.md` |
| **`.state/org-state.json`** (derived) | repo-relative | JSON projection for programmable consumers | `dashboard/org_state_converter.py` (the `--source markdown` mode was removed at M4; reads state.db directly) |
| **`.state/workers/worker-{task_id}.md`** (authoritative for pane-liveness + Progress Log) | per-worker | Worker-pane `Status:` mirror + Progress Log | Created by the dispatcher's delegate-plan helper at T2; the Lead appends on each peer message. At T5 completion, the post-commit hook automatically archives it under `.state/workers/archive/` |

**legacy (reference)**: `.state/journal.jsonl` is the legacy journal layer retired at M4. Events are now stored in the `events` table of state.db. New writes are not appended even if a historical jsonl file lingers in a repo. The "Markdown is canonical, JSON is derived" model described in `docs/org-state-schema.md` and `docs/contracts/state-schema-contract.md` § 1.1 is also a pre-M4 view; today state.db is canonical. See [`docs/contracts/state-semantics-contract.md` § 1.3](contracts/state-semantics-contract.md) for details.

**Run-status vocabulary**: a closed seven-value enum, `runs.status ∈ {queued, in_use, review, completed, failed, suspended, abandoned}` ([contract § 2](contracts/state-semantics-contract.md)). `suspended` is reserved for future use (no production write path today), and `/org-suspend` does not change a run's status ([contract I4](contracts/state-semantics-contract.md)).

---

## Tech Stack

- **AI**: Claude Code (Opus 4.6, 1M context)
- **Terminal/Multiplexer**: renga (manages multiple instances with pane splitting)
- **Inter-instance communication**: `renga-peers` MCP server (integrated messaging between Claude Code instances in the same tab + pane control)
- **Version control**: Git + GitHub (OSS / MIT License)
- **OS**: Development and operation are designed for Windows 11 Pro (bash shell). macOS / Linux work in principle (only path assumptions need local adjustments)

---

## Directory Structure

```
claude-org/
├── CLAUDE.md                      # Lead behavior guidelines (keep it thin)
├── .claude/
│   ├── settings.local.json        # Tool permission settings
│   └── skills/                    # Skills (progressive disclosure)
│       ├── org-start/             # Org startup
│       ├── org-delegate/          # Worker dispatch (Lead → Dispatcher coordination)
│       │   └── references/
│       │       ├── pane-layout.md           # Pane placement rules
│       │       ├── worker-claude-template.md # CLAUDE.md template for workers
│       │       └── instruction-template.md  # Instruction template for workers
│       ├── org-suspend/           # Org suspend
│       ├── org-resume/            # Org resume
│       ├── org-retro/             # Delegation-process retrospective
│       ├── org-curate/            # Knowledge curation (for Curator)
│       │   └── references/
│       │       └── knowledge-standards.md   # Standards for recording / organizing knowledge
│       └── org-dashboard/         # Dashboard generation
├── .dispatcher/
│   └── CLAUDE.md                  # Role instructions for the Dispatcher
├── .curator/
│   └── CLAUDE.md                  # Role instructions for the Curator
├── .state/                        # Session state (.gitignored)
│   ├── state.db                   # SQLite. SoT for runs / org_sessions / worker_dirs / events (since M4)
│   ├── org-state.md               # Derived snapshot regenerated automatically from state.db (human-facing)
│   ├── org-state.prev.md          # Backup taken just before /org-suspend
│   ├── org-state.json             # JSON projection generated from state.db (for external consumers)
│   └── workers/
│       ├── worker-{task_id}.md    # Per-worker pane-liveness + Progress Log
│       └── archive/               # The post-commit hook moves files here on T5 completion
├── dashboard/                     # HTML dashboard
│   ├── index.html                 # Template (git-managed)
│   ├── style.css                  # Styles (git-managed)
│   ├── app.js                     # Rendering (git-managed)
│   └── server.py                  # Live server (/api/state / SSE)
├── knowledge/
│   ├── raw/                       # Raw learnings (.gitignored, transient data)
│   └── curated/                   # Curated knowledge (git-managed)
├── registry/
│   └── projects.md                # Project list (common-name → path resolution)
└── docs/
    ├── getting-started.md         # Usage guide
    └── verification.md            # Test procedures
```

### Git-management policy

| Path | Git-managed | Reason |
|---|---|---|
| `.state/*` | Excluded | Contains machine-specific information (pane IDs, etc.) |
| `knowledge/raw/*` | Excluded | Pre-curation transient data; unnecessary once integrated into curated |
| `.claude/settings.local.json` | Excluded | Machine-specific tool permission settings |

---

## Skill System

Keep CLAUDE.md minimal (behavior guidelines only) and defer concrete procedures to skills (`.claude/skills/*/SKILL.md`).

**Design intent**: progressive disclosure — detailed procedures are loaded only when needed, minimizing context consumption.

### Skill list

| Skill | Trigger | Executor |
|---|---|---|
| `org-start` | Manually run right after startup | Lead |
| `org-delegate` | When a request involves execution work | Lead → Dispatcher |
| `org-suspend` | "Pause," "done for today," etc. | Lead |
| `org-resume` | On startup from a suspended state | Lead |
| `org-retro` | After work is completed | Lead |
| `org-curate` | Run on demand when the threshold check fires at worker close | Curator |
| `org-dashboard` | "Show me the dashboard," etc. | Lead |

### Delegation flow (org-delegate)

```
Secretary                          Dispatcher                         Worker
   │                                  │                              │
   ├─ Resolve project name            │                              │
   ├─ Break down task (WI-xxx)        │                              │
   ├─ Generate CLAUDE.md              │                              │
   ├─ DELEGATE message ─────────────> │                              │
   │  (the Lead is released here)     ├─ Start pane                  │
   │                                  ├─ Wait for peer               │
   │                                  ├─ Send instruction ──────────>│
   │                                  ├─ Record state                │
   │  <────── DELEGATE_COMPLETE ──────┤                              │
   │                                  │                              ├─ Execute work
   │  <──────────────── Completion report ───────────────────────────┤
   ├─ Report to user                  │                              │
   ├─ CLOSE_PANE ────────────────────>│                              │
   │                                  ├─ Close pane                  │
```

**Key design point**: The Lead handles task breakdown and CLAUDE.md generation, then hands off everything from pane startup onward to the Dispatcher. This allows the Lead to return immediately to user interaction.

---

## Self-improvement Loop

```
Worker completion → record learnings to knowledge/raw/
                ↓ (5+ entries accumulated)
Curator (org-curate) → consolidate / integrate into knowledge/curated/
                ↓ (pattern detected)
Improvement proposal → Lead → User approval → Update skill / CLAUDE.md
```

- Workers automatically record technical learnings into `knowledge/raw/` (per the CLAUDE.md instructions)
- The Dispatcher checks the threshold at worker close (`tools/check_curate_threshold.py`) → only when exceeded, launches a temporary Curator to run curation
- 3+ similar learnings trigger a process-improvement proposal
- Proposals are applied only after user approval (safety valve)

---

## Key Design Decisions

| Decision | Content | Rationale |
|---|---|---|
| Skill-centric design | CLAUDE.md is thin; procedures live in skills | Minimize context consumption |
| Delegation first | The Lead is the command center; all execution work is delegated to Workers | Avoid locking the Lead and keep user response always available |
| Dispatcher introduction | A resident instance that handles pane startup and instruction delivery | Minimize the Lead's lock time |
| Instruction duplication | CLAUDE.md + `renga-peers` messages | Avoid relying solely on volatile communication |
| state.db as SoT (M4) | Consolidate runs / sessions / worker_dirs / events SoT into SQLite. Markdown / JSON are derived | Transactional integrity + drift detection. Human readability for `/org-resume` is preserved by the snapshotter automatically regenerating `org-state.md` |
| `.state/` is .gitignored | Contains machine-specific info (pane IDs, etc.) | No need to share state across machines |

---

## Extension

### Adding a new skill

1. Create `.claude/skills/{skill-name}/SKILL.md` (with `name`, `description` in frontmatter)
2. Place auxiliary files under `references/` as needed
3. No CLAUDE.md change is required (the skill is triggered by its description)

### Registering a new project

- When the user requests work, the project is automatically registered in `registry/projects.md`
- Manual edits to `registry/projects.md` are also fine

### Customizing the dashboard

- Edit `dashboard/index.html`, `style.css`, `app.js` directly
- The `org-dashboard` skill starts `server.py` and opens `http://localhost:8099` in the browser. Data is delivered via `/api/state` (REST) and `/api/events` (SSE)
