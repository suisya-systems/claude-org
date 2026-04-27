# claude-org — Technical Overview

A self-improving AI organization layer that coordinates multiple Claude Code instances. The human only converses with the Lead; Workers are dispatched and managed automatically behind the scenes.

---

## Architecture

### Instance layout

```
┌──────────────┬──────────┬──────────┐
│              │ Worker1  │ Worker4  │
│    Lead      │ Worker2  │ Worker5  │
│   (large)    │ Worker3  │ Worker6  │
├───────┬──────┤          │          │
│Dspchr │Curat.│  ...     │  ...     │
└───────┴──────┴──────────┴──────────┘
```

| Instance | Resident | Role | Permitted tools |
|---|---|---|---|
| **Lead** | Yes | User dialogue, task decomposition, state management | All tools (but real work is delegated) |
| **Dispatcher** | Yes | Pane spawning, instruction delivery, state recording on the Lead's behalf | Bash, Read, Write, Edit, Glob, Grep, Skill, renga-peers |
| **Curator** | Yes | Knowledge curation via `/loop 30m /org-curate` | Read, Write, Edit, Glob, Grep, Skill, renga-peers |
| **Worker** | No | Real work — code edits, investigation, tests, etc. | Bash, Read, Write, Edit, Glob, Grep, Agent, Skill, renga-peers |

### Communication

- **Between instances**: the `renga-peers` MCP server provides bidirectional messaging between Claude Code instances in the same renga tab, with push-style channel notifications. Calls are made via `send_message` / `list_peers` / `check_messages` / `set_summary`. Peer IDs are pane names (`secretary` / `dispatcher` / `curator` / `worker-{task_id}`).
- **Pane management**: also via `renga-peers` (`spawn_pane` / `spawn_claude_pane` / `close_pane` / `list_panes` / `new_tab` / `focus_pane` / `inspect_pane` / `send_keys` / `poll_events` / `set_pane_identity`, etc. — 14 tools as of renga 0.18.0+). Role and Worker startup is consolidated on the structured fields of `spawn_claude_pane` (`cwd` / `permission_mode` / `model` / `args[]`) per Issue #58. The legacy `cd X && claude ...` composition pattern has been removed.
- **Layered instructions**: CLAUDE.md (persistent baseline) plus `renga-peers` messages (real-time, situational).

### State management

A three-tier structure persists the otherwise volatile state of each instance:

| Tier | File | Purpose | Update timing |
|---|---|---|---|
| Journal | `.state/journal.jsonl` | Append-only log of all important events. Used for crash recovery | On every event |
| Snapshot | `.state/org-state.md` | Human-readable Markdown snapshot of organization state | At milestones |
| Suspend | `.state/org-state.md` (SUSPENDED) | Highest-fidelity state save | On `/org-suspend` |

---

## Tech stack

- **AI**: Claude Code (Opus 4.6, 1M context)
- **Terminal multiplexer**: renga (manages multiple instances via pane splits)
- **Inter-instance communication**: the `renga-peers` MCP server (messaging between Claude Code instances in the same tab + pane control, integrated)
- **Version control**: Git + GitHub (OSS / MIT License)
- **OS**: Primary target is Windows 11 Pro (bash shell). macOS and Linux work too, modulo path-related adjustments.

---

## Directory layout

```
claude-org/
├── CLAUDE.md                      # Behavior guide for the Lead (kept thin)
├── .claude/
│   ├── settings.local.json        # Tool permissions
│   └── skills/                    # Skill bundles (progressive disclosure)
│       ├── org-start/             # Boot the organization
│       ├── org-delegate/          # Dispatch a Worker (Lead → Dispatcher handoff)
│       │   └── references/
│       │       ├── pane-layout.md            # Pane placement rules
│       │       ├── worker-claude-template.md # Worker CLAUDE.md template
│       │       └── instruction-template.md   # Worker instruction template
│       ├── org-suspend/           # Suspend the organization
│       ├── org-resume/            # Resume the organization
│       ├── org-retro/             # Retrospective on the dispatch process
│       ├── org-curate/            # Knowledge curation (Curator-side)
│       │   └── references/
│       │       └── knowledge-standards.md    # Recording / curation standards
│       └── org-dashboard/         # Dashboard generation
├── .dispatcher/
│   └── CLAUDE.md                  # Role guide for the Dispatcher
├── .curator/
│   └── CLAUDE.md                  # Role guide for the Curator
├── .state/                        # Session state (.gitignore)
│   ├── org-state.md               # Organization-state snapshot
│   ├── org-state.prev.md          # Pre-suspend backup
│   ├── journal.jsonl              # Event journal
│   └── workers/
│       └── worker-{peer_id}.md    # Per-Worker state
├── dashboard/                     # HTML dashboard
│   ├── index.html                 # Template (tracked)
│   ├── style.css                  # Styles (tracked)
│   ├── app.js                     # Rendering (tracked)
│   └── server.py                  # Live server (/api/state, SSE)
├── knowledge/
│   ├── raw/                       # Raw notes (.gitignore, transient)
│   └── curated/                   # Curated knowledge (tracked)
├── registry/
│   └── projects.md                # Project list (nickname → path resolution)
└── docs/
    ├── getting-started.md         # Usage guide
    └── verification.md            # Test procedure
```

### Git tracking policy

| Path | Tracked | Reason |
|---|---|---|
| `.state/*` | Excluded | Contains machine-specific data such as pane IDs |
| `knowledge/raw/*` | Excluded | Transient pre-curation notes; redundant once curated |
| `.claude/settings.local.json` | Excluded | Machine-specific tool permissions |

---

## Skill system

CLAUDE.md is kept to the bare minimum (behavioral guidance only); concrete procedures live in skills (`.claude/skills/*/SKILL.md`).

**Design intent**: progressive disclosure — detailed procedures load only when needed, minimizing context consumption.

### Skill index

| Skill | Trigger | Executor |
|---|---|---|
| `org-start` | Run manually right after launch | Lead |
| `org-delegate` | When a request involves real work | Lead → Dispatcher |
| `org-suspend` | "Suspend", "we're done for today", etc. | Lead |
| `org-resume` | At launch when in a suspended state | Lead |
| `org-retro` | After work completes | Lead |
| `org-curate` | Periodic via `/loop 30m` | Curator |
| `org-dashboard` | "Show me the dashboard", etc. | Lead |

### Dispatch flow (org-delegate)

```
Lead                               Dispatcher                         Worker
   │                                  │                              │
   ├─ Resolve project name             │                              │
   ├─ Decompose task (WI-xxx)         │                              │
   ├─ Generate CLAUDE.md              │                              │
   ├─ DELEGATE message ─────────────> │                              │
   │  (Lead is freed here)            ├─ Spawn pane                  │
   │                                  ├─ Wait for peer               │
   │                                  ├─ Send instructions ─────────>│
   │                                  ├─ Record state                │
   │  <────── DELEGATE_COMPLETE ──────┤                              │
   │                                  │                              ├─ Run the work
   │  <──────────────── Completion report ─────────────────────────────┤
   ├─ Report to user                  │                              │
   ├─ CLOSE_PANE ────────────────────>│                              │
   │                                  ├─ Close pane                  │
```

**Key design point**: the Lead handles task decomposition and CLAUDE.md generation, then hands pane spawning and beyond to the Dispatcher. This frees the Lead to immediately resume dialogue with the user.

---

## Self-improvement loop

```
Worker completes → records learning into knowledge/raw/
                ↓ (5+ entries accumulated)
Curator (org-curate) → consolidates into knowledge/curated/
                ↓ (pattern detected)
Improvement proposal → Lead → user approval → skill / CLAUDE.md update
```

- Workers automatically record technical learnings into `knowledge/raw/` (per CLAUDE.md instructions)
- Curator checks the threshold every 30 minutes; runs curation once 5+ entries accumulate
- When 3+ entries of the same kind appear, a process improvement is proposed
- Proposals only take effect after user approval (the safety valve)

---

## Major design decisions

| Decision | Content | Rationale |
|---|---|---|
| Skill-centric design | CLAUDE.md stays thin; procedures live in skills | Minimize context consumption |
| Delegation-first | The Lead is a coordinator; all real work is delegated to Workers | Avoid locking the Lead, keep it responsive to the user |
| Resident Dispatcher | A resident instance handles pane spawning and instruction delivery | Minimize how long the Lead is tied up |
| Layered instructions | CLAUDE.md plus `renga-peers` messages | Avoid relying on volatile communication alone |
| Markdown state | `org-state.md` is Markdown, not JSON | A new instance can grasp the situation just by reading it |
| `.state/` is gitignored | Contains machine-specific data (e.g. pane IDs) | No need to share state between machines |

---

## Extending the system

### Adding a new skill

1. Create `.claude/skills/{skill-name}/SKILL.md` (front matter must have `name` and `description`)
2. If needed, place supporting files under `references/`
3. CLAUDE.md does not need to change — the skill's `description` is what triggers it

### Registering a new project

- When the user requests work, `registry/projects.md` is populated automatically
- You may also edit `registry/projects.md` by hand

### Customizing the dashboard

- Edit `dashboard/index.html`, `style.css`, and `app.js` directly
- The `org-dashboard` skill starts `server.py` and opens `http://localhost:8099` in the browser. Data is served via `/api/state` (REST) and `/api/events` (SSE).
