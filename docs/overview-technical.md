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
| **Curator** | Yes | Organizes knowledge with `/loop 30m /org-curate` | Read, Write, Edit, Glob, Grep, Skill, renga-peers |
| **Worker** | No | Execution work (code edits, research, testing, etc.) | Bash, Read, Write, Edit, Glob, Grep, Agent, Skill, renga-peers |

### Communication

- **Between instances**: `renga-peers` MCP (bidirectional messaging between Claudes in the same tab, with push-based channel notifications). Use `send_message` / `list_peers` / `check_messages` / `set_summary`, and use pane names for peer IDs (`secretary` / `dispatcher` / `curator` / `worker-{task_id}`)
- **Pane management**: `renga-peers` MCP (`spawn_pane` / `spawn_claude_pane` / `close_pane` / `list_panes` / `new_tab` / `focus_pane` / `inspect_pane` / `send_keys` / `poll_events` / `set_pane_identity`, etc.; 14 tools in renga 0.18.0+). Role/worker startup is standardized on the structured fields of `spawn_claude_pane` (`cwd` / `permission_mode` / `model` / `args[]`) (Issue #58). The `cd X && claude ...` composition pattern has been removed
- **Instruction duplication**: CLAUDE.md (persistent baseline) + `renga-peers` messages (real-time supplements)

### State Management

A three-layer structure persists the state of ephemeral instances:

| Layer | File | Purpose | Update Timing |
|---|---|---|---|
| Journal | `.state/journal.jsonl` | Append all important events. Used for crash recovery | When each event occurs |
| Snapshot | `.state/org-state.md` | Human-readable organization state in Markdown format | At milestones |
| Suspend | `.state/org-state.md` (SUSPENDED) | Highest-quality state preservation | When `/org-suspend` runs |

---

## Tech Stack

- **AI**: Claude Code (Opus 4.6, 1M context)
- **Terminal/Multiplexer**: renga (manages multiple instances with pane splitting)
- **Inter-instance communication**: `renga-peers` MCP server (integrates Claude Code messaging within the same tab and pane control)
- **Version control**: Git + GitHub (OSS / MIT License)
- **OS**: Development and operation are intended for Windows 11 Pro (bash shell). Basic operation is also expected on macOS / Linux (only path assumptions need to be adjusted locally)

---

## Directory Structure

```
claude-org/
├── CLAUDE.md                      # Secretary behavior guidelines (keep it thin)
├── .claude/
│   ├── settings.local.json        # Tool permission settings
│   └── skills/                    # Skill set (progressive disclosure)
│       ├── org-start/             # Organization startup
│       ├── org-delegate/          # Worker dispatch (Lead → Dispatcher coordination)
│       │   └── references/
│       │       ├── pane-layout.md           # Pane layout rules
│       │       ├── worker-claude-template.md # CLAUDE.md template for Workers
│       │       └── instruction-template.md  # Instruction template for Workers
│       ├── org-suspend/           # Organization suspension
│       ├── org-resume/            # Organization resume
│       ├── org-retro/             # Delegation process retrospective
│       ├── org-curate/            # Knowledge organization (for the Curator)
│       │   └── references/
│       │       └── knowledge-standards.md   # Standards for recording and organizing knowledge
│       └── org-dashboard/         # Dashboard generation
├── .dispatcher/
│   └── CLAUDE.md                  # Role instructions for the Dispatcher
├── .curator/
│   └── CLAUDE.md                  # Role instructions for the Curator
├── .state/                        # Session state (.gitignore)
│   ├── org-state.md               # Organization state snapshot
│   ├── org-state.prev.md          # Backup at suspend time
│   ├── journal.jsonl              # Event journal
│   └── workers/
│       └── worker-{peer_id}.md    # State for each Worker
├── dashboard/                     # HTML dashboard
│   ├── index.html                 # Template (tracked in git)
│   ├── style.css                  # Styles (tracked in git)
│   ├── app.js                     # Rendering (tracked in git)
│   └── server.py                  # Live server (/api/state / SSE)
├── knowledge/
│   ├── raw/                       # Raw learnings (.gitignore, temporary data)
│   └── curated/                   # Organized knowledge (tracked in git)
├── registry/
│   └── projects.md                # Project list (alias-to-path name resolution)
└── docs/
    ├── getting-started.md         # Usage guide
    └── verification.md            # Test procedures
```

### Git Management Policy

| Path | Git Management | Reason |
|---|---|---|
| `.state/*` | Excluded | Contains machine-specific information such as pane IDs |
| `knowledge/raw/*` | Excluded | Temporary pre-curation data. Unneeded once integrated into curated |
| `.claude/settings.local.json` | Excluded | Machine-specific tool permission settings |

---

## Skill System

Keep CLAUDE.md minimal (behavior guidelines only), and delegate concrete procedures to skills (`.claude/skills/*/SKILL.md`).

**Design intent**: Progressive disclosure — detailed procedures are loaded only when needed, minimizing context consumption.

### Skill List

| Skill | Trigger | Executor |
|---|---|---|
| `org-start` | Manually run right after startup | Lead |
| `org-delegate` | When a request involves execution work | Lead → Dispatcher |
| `org-suspend` | “Pause,” “done for today,” etc. | Lead |
| `org-resume` | On startup from a suspended state | Lead |
| `org-retro` | After work is completed | Lead |
| `org-curate` | Periodically run with `/loop 30m` | Curator |
| `org-dashboard` | “Show me the dashboard,” etc. | Lead |

### Delegation Flow (`org-delegate`)

```
Secretary                          Dispatcher                         Worker
   │                                  │                              │
   ├─ Project name resolution         │                              │
   ├─ Task breakdown (WI-xxx)         │                              │
   ├─ Generate CLAUDE.md              │                              │
   ├─ DELEGATE message ─────────────> │                              │
   │  (the Lead is released here)     ├─ Start pane                  │
   │                                  ├─ Wait for peer               │
   │                                  ├─ Send instructions ─────────>│
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

## Self-Improvement Loop

```
Worker completes → Record learning in knowledge/raw/
                ↓ (5 or more accumulated)
Curator (org-curate) → Organize and consolidate into knowledge/curated/
                ↓ (pattern detected)
Improvement proposal → Secretary → User approval → Update skill/CLAUDE.md
```

- Workers automatically record technical knowledge in `knowledge/raw/` (via instructions in CLAUDE.md)
- The Curator checks the threshold every 30 minutes → runs organization once 5 or more items are accumulated
- If 3 or more pieces of the same kind of knowledge appear, propose a process improvement
- Proposals are only applied after user approval (safety valve)

---

## Major Design Decisions

| Decision | Content | Rationale |
|---|---|---|
| Skill-centered design | Keep CLAUDE.md thin and delegate procedures to skills | Minimize context consumption |
| Delegation first | The Lead is the command center; all execution work is delegated to Workers | Avoid locking the Lead and keep user response always available |
| Dispatcher introduction | A resident instance that handles pane startup and instruction delivery | Minimize the Lead's lock time |
| Instruction duplication | CLAUDE.md + `renga-peers` messages | Avoid depending only on ephemeral communication |
| Markdown state management | `org-state.md` is Markdown, not JSON | A new instance can understand the situation just by reading it |
| `.state/` in `.gitignore` | Contains machine-specific information such as pane IDs | No need to share state across machines |

---

## How to Extend

### Add a New Skill

1. Create `.claude/skills/{skill-name}/SKILL.md` (write `name` and `description` in the frontmatter)
2. Place supporting files in `references/` as needed
3. No changes to CLAUDE.md are required (the skill is triggered by its `description`)

### Register a New Project

- When the user requests work, it is automatically added to `registry/projects.md`
- You may also edit `registry/projects.md` manually

### Customize the Dashboard

- Edit `dashboard/index.html`, `style.css`, and `app.js` directly
- The `org-dashboard` skill starts `server.py` and opens `http://localhost:8099` in the browser. Data is served via `/api/state` (REST) and `/api/events` (SSE)
