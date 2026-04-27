# Multi-Agent AI Coordination Frameworks — OSS Comparison Report

> Survey date: 2026-04-06
> Purpose: comprehensively survey and compare OSS projects similar to claude-org's design philosophy (multi-instance AI coordination, role separation, resident roles, self-improvement loop, progressive disclosure via skills).

---

## 1. claude-org's design characteristics (the basis for comparison)

claude-org has the following characteristics:

| Characteristic | Description |
|---|---|
| **Multi-instance coordination** | Four kinds of Claude Code instance — Lead, Dispatcher, Curator, Worker — coordinate together |
| **Role separation** | Clear division of labor: Lead (dialogue), Dispatcher (pane management), Curator (knowledge curation), Worker (real work) |
| **Resident roles** | Lead / Dispatcher / Curator are resident; Workers boot on demand |
| **State management** | Three-layer structure: journal (JSONL) + snapshot (Markdown) + suspend |
| **Self-improvement loop** | Worker → raw learning → Curator curation → improvement proposal → user approval → skill / CLAUDE.md update |
| **Communication model** | `renga-peers` MCP (same-tab P2P, push-style) + CLAUDE.md (persistent baseline) |
| **Progressive disclosure** | The skill system loads detailed procedures only when needed |

---

## 2. List of OSS projects compared

### 2.1 General-purpose multi-agent frameworks

| # | Project | Developer | GitHub Stars | License |
|---|---|---|---|---|
| 1 | [CrewAI](https://github.com/crewaiinc/crewai) | CrewAI Inc. | 44,300+ | MIT |
| 2 | [LangGraph](https://github.com/langchain-ai/langgraph) | LangChain | 24,800+ | MIT |
| 3 | [Microsoft Agent Framework (AutoGen)](https://github.com/microsoft/autogen) | Microsoft | 40,000+ | MIT |
| 4 | [OpenAI Swarm](https://github.com/openai/swarm) | OpenAI | — | MIT |
| 5 | [Google ADK](https://github.com/google/adk-python) | Google | — | Apache 2.0 |
| 6 | [AWS Agent Squad](https://github.com/awslabs/agent-squad) | AWS Labs | — | Apache 2.0 |

### 2.2 Claude-Code-specific multi-agent

| # | Project | Developer | Notes |
|---|---|---|---|
| 7 | [Claude Code Agent Teams](https://code.claude.com/docs/en/agent-teams) | Anthropic (official) | Official multi-session coordination feature (experimental) |
| 8 | [Ruflo](https://github.com/ruvnet/ruflo) | ruvnet | Swarm-style agent platform for Claude Code |
| 9 | [oh-my-claudecode](https://github.com/yeachan-heo/oh-my-claudecode) | Yeachan Heo | Team-oriented multi-agent orchestration |
| 10 | [claude-code-by-agents](https://github.com/baryhuang/claude-code-by-agents) | baryhuang | @mention-based multi-agent coordination |

### 2.3 Self-improvement / self-evolution

| # | Project | Developer | Notes |
|---|---|---|---|
| 11 | [Agent Zero](https://github.com/agent0ai/agent-zero) | agent0ai | Autonomous tool creation and learning via persistent memory |
| 12 | [OpenSpace](https://github.com/HKUDS/OpenSpace) | HKUDS (Univ. of Hong Kong) | Self-evolving skill engine |
| 13 | [AutoAgent](https://github.com/kevinrgu/autoagent) | Kevin Gu / thirdlayer | Autonomous optimization of the agent harness |
| 14 | [SuperAGI](https://github.com/TransformerOptimus/SuperAGI) | TransformerOptimus | Autonomous agent framework (auto performance improvement) |

---

## 3. Detailed analysis along each comparison axis

### 3.1 Multi-agent coordination model

| Project | Coordination model | Detail |
|---|---|---|
| **claude-org** | **Hierarchical + P2P** | Hierarchical delegation Lead→Dispatcher→Worker + P2P over `renga-peers` MCP (same-tab scope) |
| CrewAI | Role-based coordination | Define role/backstory/goal on each Agent and coordinate as a crew. Sequential / Hierarchical processes |
| LangGraph | Graph-based | Workflows defined as nodes (agents) and edges (transitions). Supports conditional branching and loops |
| AutoGen | Conversation-based | Coordination via message passing between agents. GroupChat enables multi-agent conversation |
| Swarm | Hand-off model | Tasks are explicitly handed off between Agents. Stateless |
| Google ADK | Hierarchical | Agents composed hierarchically. Sequential / Parallel / Loop workflows + LLM dynamic routing |
| Agent Squad | Supervisor model | A SupervisorAgent coordinates specialist agents in parallel via the agent-as-tools pattern |
| Agent Teams | Team-lead model | One lead session + up to 15 teammates. Shared task list + P2P messaging |
| Ruflo | Swarm | Up to 100 agents run in parallel. Six coordination patterns. Self-learning routing |
| oh-my-claudecode | Autopilot | Auto delegation across 32 specialist agents. Up to 5 parallel workers |
| Agent Zero | Hierarchical | Higher agents spawn and delegate to lower agents. Recursive structure |
| OpenSpace | Standalone + sharing | Single Agent + integration via MCP server. Skill-sharing community |

**Similarity to claude-org**: Agent Teams is closest (P2P communication + shared task list). CrewAI's role-based design is conceptually close as well.

### 3.2 Role separation

| Project | Role model | Resident roles | Dynamic roles |
|---|---|---|---|
| **claude-org** | **Lead / Dispatcher / Curator / Worker** | **3 (Lead / Dispatcher / Curator)** | **Worker (on demand)** |
| CrewAI | User-defined roles (Manager / Researcher / etc.) | None (only at runtime) | All agents |
| LangGraph | Defined as nodes (no fixed names) | None | All nodes |
| AutoGen | UserProxy / Assistant / GroupChatManager / etc. | None | All agents |
| Swarm | User-defined (Triage / Sales / etc.) | None | All agents |
| Google ADK | Hierarchical agent definitions | None | All agents |
| Agent Squad | Supervisor + specialist agents | None | All agents |
| Agent Teams | Team Lead + Teammates | Team Lead (1) | Teammates |
| Ruflo | Orchestrator + Specialist Swarm | None (on-demand spawn) | All agents |
| oh-my-claudecode | Architect + 32 specialist agents | None | All agents |
| Agent Zero | Parent agent + child agents | Parent (1) | Child agents |
| OpenSpace | Single agent (no role separation) | — | — |

**What's distinctive about claude-org**: **the number of resident roles** (three) and **a clear organizational structure** (Lead-Dispatcher-Curator-Worker) is unmatched elsewhere. The Curator in particular — a resident process specialized in knowledge curation — is unique to claude-org.

### 3.3 State management

| Project | State persistence | Format | Crash recovery |
|---|---|---|---|
| **claude-org** | **Journal + snapshot + suspend (three layers)** | **JSONL / Markdown** | **Restoration from journal + org-resume** |
| CrewAI | Memory (short-term / long-term / entity) | Internal DB | Limited |
| LangGraph | Checkpoints (persisted) | Custom storage | Time-travel debugging supported |
| AutoGen | Session-based state management | Memory / serialization | Improved in v0.4 |
| Swarm | **None** (stateless design) | — | None |
| Google ADK | Session state | Custom | Vertex AI integration |
| Agent Squad | Context management | Memory | Limited |
| Agent Teams | Shared task list (file-based) | JSON / files | Recoverable from the task list |
| Ruflo | Neural memory (v3) | Internal DB | Pattern retention (catastrophic-forgetting prevention) |
| Agent Zero | Persistent memory | File-based | Recovery from memory |
| OpenSpace | Skill DB | File-based | Auto skill repair (FIX mode) |

**What's distinctive about claude-org**: **Markdown-based state management** is unique in that a fresh instance can grasp the situation just by reading the file. LangGraph's checkpoints are the most full-featured on the functional axis.

### 3.4 Self-improvement mechanism

| Project | Self-improvement | Mechanism | Human approval |
|---|---|---|---|
| **claude-org** | **Yes (structured loop)** | **Worker → raw learning → Curator curation → proposal → approval → skill update** | **Required (safety valve)** |
| CrewAI | Limited | Memory accumulated across tasks | None |
| LangGraph | None (external implementation possible) | — | — |
| AutoGen | Planned | Long-term agent learning (roadmap) | — |
| Swarm | None | — | — |
| Google ADK | None | — | — |
| Agent Squad | None | — | — |
| Agent Teams | None | — | — |
| Ruflo | Yes | Auto learning from task execution, pattern retention | None (autonomous) |
| oh-my-claudecode | Limited | Feedback from execution results | None |
| Agent Zero | Yes | Dynamic tool creation, learning via persistent memory | None (autonomous) |
| OpenSpace | **Yes (most advanced)** | **Three-mode evolution: FIX / DERIVED / CAPTURED. Auto skill repair, derivation, capture** | **None (autonomous)** |
| AutoAgent | Yes (meta-optimization) | Autonomously optimizes the harness itself (prompts / tools / routing) | None (autonomous) |
| SuperAGI | Yes | Per-run performance improvement | None |

**What's distinctive about claude-org**: **a self-improvement loop with human approval in the middle** is unique to claude-org. Other self-improvement projects are autonomous (no human in the loop). OpenSpace's skill-evolution mechanism is conceptually close to claude-org's skill system, but lacks the human-approval step.

### 3.5 Communication model

| Project | Communication model | Notes |
|---|---|---|
| **claude-org** | **`renga-peers` MCP (same-tab P2P, push-style) + CLAUDE.md (persistent baseline)** | **Reliability via layering. Volatile communication + persistent instructions in combination** |
| CrewAI | Shared context / delegation | context / delegation between agents |
| LangGraph | Via shared State | Data sharing through the graph's State object |
| AutoGen | Message passing | Direct messages between agents. GroupChat broadcasts |
| Swarm | Hand-off function | The conversation context is handed over wholesale |
| Google ADK | Hierarchical messages + transfer | Parent–child messages + LLM dynamic routing |
| Agent Squad | Intent routing | User input is dynamically routed to the right agent |
| Agent Teams | P2P mailbox + shared task list | File-based mailbox system |
| Ruflo | Swarm communication | Hierarchical coordination + consensus mechanism |
| Agent Zero | Parent-child messaging | Hierarchical message passing |

**What's distinctive about claude-org**: **layered instructions** (CLAUDE.md persistent instructions + `renga-peers` real-time communication) are an unmatched design. Agent Teams' mailbox system is the closest.

---

## 4. Summary comparison matrix

| Axis | claude-org | CrewAI | LangGraph | AutoGen | Agent Teams | Ruflo | OpenSpace | Agent Zero |
|---|---|---|---|---|---|---|---|---|
| Coordination model | Hierarchical + P2P | Role-based | Graph | Conversation | Team | Swarm | Single + share | Hierarchical |
| Role fixity | ◎ 4 fixed | △ Free-form | △ Free-form | △ Free-form | ○ Lead + Members | △ Free-form | × None | ○ Parent / child |
| Resident roles | ◎ 3 | × None | × None | × None | ○ 1 | × None | × None | ○ 1 |
| State persistence | ◎ 3 layers | ○ Memory | ◎ Checkpoint | ○ Session | ○ Task list | ○ Neural DB | ○ Skill DB | ○ Memory |
| Self-improvement | ◎ Structured | △ Limited | × None | × Planned | × None | ○ Auto-learning | ◎ 3-mode evolution | ○ Tool generation |
| Human approval | ◎ Required | × None | × None | × None | × None | × None | × None | × None |
| P2P communication | ◎ | × | × | ○ | ◎ | △ | × | × |
| Persistent instructions | ◎ Layered | × | × | × | △ | × | × | × |

Legend: ◎ Highly implemented / ○ Implemented / △ Limited / × None

---

## 5. Most notable similar projects (Top 3)

### 5.1 Claude Code Agent Teams (closest structurally)

- **Similar**: P2P communication, shared task list, team-lead + members structure
- **Different**: only one resident role (Lead); no Curator equivalent; no self-improvement loop; no layered instructions
- **Verdict**: the infrastructure layer (communication / task management) is close, but the organizational design and self-improvement layers are missing

### 5.2 OpenSpace (closest in self-improvement philosophy)

- **Similar**: automatic skill evolution (FIX/DERIVED/CAPTURED resembles claude-org's raw → curated → skill update); skill reuse
- **Different**: not multi-agent (single agent + MCP integration); no human-approval step; no role separation
- **Verdict**: the self-improvement mechanism may be more mature than claude-org's, but the project lacks coordination as an organization

### 5.3 CrewAI (closest in role-based design)

- **Similar**: clear roles assigned to agents (role/backstory/goal), hierarchical processes, the concept of delegation
- **Different**: no resident roles; limited state management; no self-improvement loop; not Claude-Code-specific
- **Verdict**: the role-based coordination pattern is conceptually close, but the design philosophy of being a persistent organization differs

---

## 6. claude-org's differentiators

The survey identifies the following differentiators for claude-org:

### 6.1 Features absent from existing OSS

1. **A multi-role resident organization**: an organizational structure with three resident roles (Lead / Dispatcher / Curator) is not seen elsewhere
2. **A self-improvement loop with human approval**: several frameworks have self-improvement, but only claude-org embeds human approval as a safety valve
3. **Layered instructions**: combining CLAUDE.md (persistent baseline) with `renga-peers` messages (real-time supplement) is unmatched
4. **Progressive disclosure**: the skill system as a strategy to minimize context consumption
5. **Markdown-based state management**: a design where a fresh instance can read its way into the situation (machine-readable and human-readable)

### 6.2 What we can learn from existing OSS

1. **LangGraph's checkpoints**: time-travel debugging would help strengthen state management
2. **OpenSpace's three skill-evolution modes**: the FIX/DERIVED/CAPTURED taxonomy is applicable to claude-org's knowledge curation
3. **Ruflo's self-learning routing**: a useful reference for improving automatic task assignment
4. **Agent Teams' file locking**: a conflict-prevention mechanism for simultaneous edits across multiple Workers
5. **AutoAgent's meta-optimization**: harness self-improvement is applicable to claude-org's auto skill updates

---

## 7. Conclusion

claude-org occupies a unique position: "persistent organizational operation by multiple AI instances". Most existing OSS focuses on "agent coordination during task execution"; claude-org instead aims at **continuous operation and self-improvement of the organization itself**.

Even the closest project — Claude Code Agent Teams — lacks a resident Curator and a self-improvement loop. claude-org's design philosophy fills a clear gap in the current OSS landscape.

---

## Sources

- [CrewAI](https://crewai.com/open-source)
- [LangGraph](https://www.langchain.com/langgraph)
- [Microsoft AutoGen / Agent Framework](https://github.com/microsoft/autogen)
- [OpenAI Swarm](https://github.com/openai/swarm)
- [Google ADK](https://google.github.io/adk-docs/)
- [AWS Agent Squad](https://github.com/awslabs/agent-squad)
- [Claude Code Agent Teams](https://code.claude.com/docs/en/agent-teams)
- [Ruflo](https://github.com/ruvnet/ruflo)
- [oh-my-claudecode](https://github.com/yeachan-heo/oh-my-claudecode)
- [claude-code-by-agents](https://github.com/baryhuang/claude-code-by-agents)
- [Agent Zero](https://github.com/agent0ai/agent-zero)
- [OpenSpace](https://github.com/HKUDS/OpenSpace)
- [AutoAgent](https://github.com/kevinrgu/autoagent)
- [SuperAGI](https://github.com/TransformerOptimus/SuperAGI)
- [The Best Open Source Frameworks For Building AI Agents in 2026](https://www.firecrawl.dev/blog/best-open-source-agent-frameworks)
- [Self-Evolving Agents: Open-Source Projects Redefining AI in 2026](https://evoailabs.medium.com/self-evolving-agents-open-source-projects-redefining-ai-in-2026-be2c60513e97)
