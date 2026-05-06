# Multi-Agent AI Coordination Frameworks: OSS Comparison Report

> Survey date: 2026-04-06
> Objective: comprehensively survey and compare OSS similar to the claude-org design philosophy (coordination across multiple AI instances, role separation, resident roles, a self-improvement loop, and progressive disclosure through skills)

---

## 1. claude-org Design Characteristics (Comparison Baseline)

claude-org has the following characteristics:

| Characteristic | Description |
|---|---|
| **Multi-instance coordination** | Four types of Claude Code instances coordinate: Lead, Dispatcher, Curator, and Worker |
| **Role separation** | Clear division of labor across Secretary (interaction), Dispatcher (pane management), Curator (knowledge organization), and Worker (execution) |
| **Resident roles** | Secretary/Dispatcher/Curator stay resident; Workers launch on demand |
| **State management** | Three-layer structure: journal (JSONL) + snapshot (Markdown) + suspend |
| **Self-improvement loop** | Worker → raw findings → Curator organization → improvement proposal → user approval → skill/`CLAUDE.md` update |
| **Communication model** | `renga-peers` MCP (same-tab P2P push) + `CLAUDE.md` (persistent baseline) |
| **Progressive disclosure** | The skill system loads detailed procedures only when needed |

---

## 2. OSS Compared

### 2.1 General-Purpose Multi-Agent Frameworks

| # | Project | Maintainer | GitHub Stars | License |
|---|---|---|---|---|
| 1 | [CrewAI](https://github.com/crewaiinc/crewai) | CrewAI Inc. | 44,300+ | MIT |
| 2 | [LangGraph](https://github.com/langchain-ai/langgraph) | LangChain | 24,800+ | MIT |
| 3 | [Microsoft Agent Framework (AutoGen)](https://github.com/microsoft/autogen) | Microsoft | 40,000+ | MIT |
| 4 | [OpenAI Swarm](https://github.com/openai/swarm) | OpenAI | — | MIT |
| 5 | [Google ADK](https://github.com/google/adk-python) | Google | — | Apache 2.0 |
| 6 | [AWS Agent Squad](https://github.com/awslabs/agent-squad) | AWS Labs | — | Apache 2.0 |

### 2.2 Claude Code-Focused Multi-Agent Projects

| # | Project | Maintainer | Characteristic |
|---|---|---|---|
| 7 | [Claude Code Agent Teams](https://code.claude.com/docs/en/agent-teams) | Anthropic (official) | Official multi-session coordination feature set (experimental) |
| 8 | [Ruflo](https://github.com/ruvnet/ruflo) | ruvnet | Swarm-style agent platform for Claude Code |
| 9 | [oh-my-claudecode](https://github.com/yeachan-heo/oh-my-claudecode) | Yeachan Heo | Team-oriented multi-agent orchestration |
| 10 | [claude-code-by-agents](https://github.com/baryhuang/claude-code-by-agents) | baryhuang | `@mention`-based multi-agent coordination |

### 2.3 Self-Improvement and Self-Evolution Systems

| # | Project | Maintainer | Characteristic |
|---|---|---|---|
| 11 | [Agent Zero](https://github.com/agent0ai/agent-zero) | agent0ai | Learns through autonomous tool creation and persistent memory |
| 12 | [OpenSpace](https://github.com/HKUDS/OpenSpace) | HKUDS (University of Hong Kong) | Self-evolving skill engine |
| 13 | [AutoAgent](https://github.com/kevinrgu/autoagent) | Kevin Gu / thirdlayer | Autonomous optimization of the agent harness |
| 14 | [SuperAGI](https://github.com/TransformerOptimus/SuperAGI) | TransformerOptimus | Autonomous agent framework with automatic performance improvement |

---

## 3. Detailed Analysis by Comparison Axis

### 3.1 Multi-Agent Coordination Model

| Project | Coordination model | Details |
|---|---|---|
| **claude-org** | **Hierarchical + P2P** | Hierarchical delegation from Secretary → Dispatcher → Worker, plus P2P communication over `renga-peers` MCP (same-tab scope) |
| CrewAI | Role-based coordination | Define role/backstory/goal on each agent and coordinate them as a crew. Sequential / Hierarchical processes |
| LangGraph | Graph-based | Define workflows as nodes (agents) and edges (transitions). Supports branching and loops |
| AutoGen | Conversation-based | Coordination through message passing between agents. Multi-agent conversation via GroupChat |
| Swarm | Handoff-based | Delegate tasks through explicit handoffs between agents. Stateless |
| Google ADK | Hierarchical | Compose agents hierarchically. Sequential / Parallel / Loop workflows plus LLM-driven dynamic routing |
| Agent Squad | Supervisor-based | `SupervisorAgent` coordinates specialist agents in parallel with the agent-as-tools pattern |
| Agent Teams | Team lead-based | One lead session plus up to 15 teammates. Shared task list plus P2P messaging |
| Ruflo | Swarm-based | Up to 100 agents run in parallel. Six coordination patterns. Self-learning routing |
| oh-my-claudecode | Autopilot-style | Automatic delegation across 32 specialist agents. Up to 5 concurrent workers |
| Agent Zero | Hierarchical | Higher-level agents spawn and delegate to lower-level agents. Recursive structure |
| OpenSpace | Standalone + shared | Standalone agent plus integration through an MCP server. Skill-sharing community |

**Similarity to claude-org**: Agent Teams is the closest match (P2P communication + shared task list). CrewAI’s role-based design is also conceptually close.

### 3.2 Role Separation

| Project | Role model | Resident roles | Dynamic roles |
|---|---|---|---|
| **claude-org** | **Secretary / Dispatcher / Curator / Worker** | **3 (Sec/Fore/Cur)** | **Worker (on demand)** |
| CrewAI | User-defined roles (Manager / Researcher, etc.) | None (run-time only) | All agents |
| LangGraph | Defined as nodes (no fixed names) | None | All nodes |
| AutoGen | UserProxy / Assistant / GroupChatManager, etc. | None | All agents |
| Swarm | User-defined (Triage / Sales, etc.) | None | All agents |
| Google ADK | Hierarchical agent definitions | None | All agents |
| Agent Squad | Supervisor + specialist agents | None | All agents |
| Agent Teams | Team Lead + Teammates | Team Lead (1) | Teammates |
| Ruflo | Orchestrator + Specialist Swarm | None (on-demand launch) | All agents |
| oh-my-claudecode | Architect + 32 specialist agents | None | All agents |
| Agent Zero | Parent agent + child agents | Parent (1) | Child agents |
| OpenSpace | Single agent (no role separation) | — | — |

**claude-org differentiation**: The combination of **multiple resident roles** (3 types) and a **clear organizational structure** (Secretary-Dispatcher-Curator-Worker) is unique. In particular, Curator as a resident process dedicated to knowledge organization is specific to claude-org.

### 3.3 State Management

| Project | State persistence | Format | Crash recovery |
|---|---|---|---|
| **claude-org** | **Journal + snapshot + suspend (three layers)** | **JSONL / Markdown** | **Restore from journal + `org-resume`** |
| CrewAI | Memory (short-term / long-term / entity) | Internal DB | Limited |
| LangGraph | Checkpoints (persistent) | Custom storage | Supports time-travel debugging |
| AutoGen | Session-based state management | Memory / serialization | Improved in v0.4 |
| Swarm | **None** (stateless design) | — | None |
| Google ADK | Session state | Custom | Vertex AI integration |
| Agent Squad | Context management | Memory | Limited |
| Agent Teams | Shared task list (file-based) | JSON / files | Can restore from task list |
| Ruflo | Neural memory (v3) | Internal DB | Retains patterns (prevents catastrophic forgetting) |
| Agent Zero | Persistent memory | File-based | Restore from memory |
| OpenSpace | Skill DB | File-based | Automatic skill repair (FIX mode) |

**claude-org characteristic**: **Markdown-based state management** is distinctive because a new instance can understand the situation by reading it. LangGraph’s checkpointing is the most feature-complete in this area.

### 3.4 Self-Improvement Mechanism

| Project | Self-improvement | Mechanism | Human approval |
|---|---|---|---|
| **claude-org** | **Yes (structured loop)** | **Worker → raw findings → Curator organization → proposal → approval → skill update** | **Required (safety valve)** |
| CrewAI | Limited | Memory accumulation across tasks | None |
| LangGraph | None (possible through external implementation) | — | — |
| AutoGen | Planned | Long-term agent learning (roadmap) | — |
| Swarm | None | — | — |
| Google ADK | None | — | — |
| Agent Squad | None | — | — |
| Agent Teams | None | — | — |
| Ruflo | Yes | Automatic learning from task execution, pattern retention | None (automatic) |
| oh-my-claudecode | Limited | Feedback from execution results | None |
| Agent Zero | Yes | Dynamic tool creation and learning through persistent memory | None (autonomous) |
| OpenSpace | **Yes (most advanced)** | **Three evolution modes: FIX / DERIVED / CAPTURED. Automatic repair, derivation, and acquisition of skills** | **None (autonomous)** |
| AutoAgent | Yes (meta-optimization) | Autonomously optimizes the harness itself (prompts, tools, routing) | None (autonomous) |
| SuperAGI | Yes | Improves performance on each run | None |

**claude-org differentiation**: A **self-improvement loop with human approval in the middle** is unique to claude-org. Other self-improving systems are autonomous and do not include human intervention. OpenSpace is conceptually close to the claude-org skill system, but it lacks a human approval step.

### 3.5 Communication Model

| Project | Communication model | Characteristic |
|---|---|---|
| **claude-org** | **`renga-peers` MCP (same-tab P2P push) + `CLAUDE.md` (persistent baseline)** | **Reliability through duplication. Combines ephemeral communication with persistent instructions** |
| CrewAI | Shared context and delegation | Shares context / delegation across agents |
| LangGraph | Shared state | Shares data through the graph State object |
| AutoGen | Message passing | Direct agent-to-agent messages. Broadcast via GroupChat |
| Swarm | Handoff functions | Transfers the entire conversation context |
| Google ADK | Hierarchical messaging + forwarding | Parent-child messaging plus LLM-driven dynamic routing |
| Agent Squad | Intent routing | Dynamically routes user input to the right agent |
| Agent Teams | P2P mailbox + shared task list | File-based mailbox system |
| Ruflo | Swarm communication | Hierarchical coordination plus a consensus mechanism |
| Agent Zero | Parent-child messaging | Hierarchical message passing |

**claude-org differentiation**: **Instruction duplication** (`CLAUDE.md` as persistent instruction + `renga-peers` as real-time communication) is a distinctive design. Agent Teams’ mailbox system is the closest comparable model.

---

## 4. Overall Comparison Table

| Comparison axis | claude-org | CrewAI | LangGraph | AutoGen | Agent Teams | Ruflo | OpenSpace | Agent Zero |
|---|---|---|---|---|---|---|---|---|
| Coordination model | Hierarchical + P2P | Role-based | Graph-based | Conversation-based | Team-based | Swarm-based | Standalone + shared | Hierarchical |
| Role rigidity | ◎ Four fixed roles | △ Freely defined | △ Freely defined | △ Freely defined | ○ Lead + Members | △ Freely defined | × None | ○ Parent-child |
| Resident roles | ◎ Three types | × None | × None | × None | ○ One type | × None | × None | ○ One type |
| State persistence | ◎ Three layers | ○ Memory | ◎ Checkpoints | ○ Sessions | ○ Task list | ○ Neural DB | ○ Skill DB | ○ Memory |
| Self-improvement | ◎ Structured | △ Limited | × None | × Planned | × None | ○ Automatic learning | ◎ Three-mode evolution | ○ Tool generation |
| Human approval | ◎ Required | × None | × None | × None | × None | × None | × None | × None |
| P2P communication | ◎ | × | × | ○ | ◎ | △ | × | × |
| Persistent instructions | ◎ Duplicated | × | × | × | △ | × | × | × |

Legend: ◎ Fully implemented / ○ Implemented / △ Limited / × None

---

## 5. Notable Similar Projects (Top 3)

### 5.1 Claude Code Agent Teams (closest structurally)

- **Similarities**: P2P communication, shared task list, team lead + member structure
- **Differences**: Only one resident role (Lead), no Curator equivalent, no self-improvement loop, no instruction duplication
- **Assessment**: The infrastructure layer (communication and task management) is close, but the organizational design and self-improvement layer are missing

### 5.2 OpenSpace (closest in self-improvement philosophy)

- **Similarities**: Automatic skill evolution (FIX/DERIVED/CAPTURED is similar to claude-org’s raw → curated → skill update flow), skill reuse
- **Differences**: Not a multi-agent coordination system (single agent + MCP integration), no human approval process, no role separation
- **Assessment**: Its self-improvement mechanism may be more mature than claude-org’s, but it lacks coordination as an organization

### 5.3 CrewAI (closest in role-based design)

- **Similarities**: Defines explicit agent roles (`role`/`backstory`/`goal`), hierarchical processes, and delegation
- **Differences**: No resident roles, limited state management, no self-improvement loop, not Claude Code-specific
- **Assessment**: The role-based coordination pattern is conceptually close, but the design philosophy differs from a persistent organization

---

## 6. claude-org Differentiators

The survey confirms the following differentiators in claude-org:

### 6.1 Characteristics Not Found in Existing OSS

1. **Resident multi-role organization**: No other example uses an organizational structure with three resident roles: Secretary, Dispatcher, and Curator
2. **Self-improvement loop with human approval**: Multiple frameworks support self-improvement, but only claude-org builds in human approval as a safety valve
3. **Instruction duplication**: The combination of `CLAUDE.md` (persistent baseline) and `renga-peers` messages (real-time supplement) is distinctive
4. **Progressive disclosure**: A strategy to minimize context consumption through the skill system
5. **Markdown state management**: A design that lets a new instance understand the situation by reading state directly, while remaining both machine-readable and human-readable

### 6.2 What Existing OSS Can Teach

1. **LangGraph checkpoints**: Time-travel debugging is useful for strengthening state management
2. **OpenSpace’s three-mode skill evolution**: The FIX/DERIVED/CAPTURED taxonomy could be applied to knowledge organization in claude-org
3. **Ruflo’s self-learning routing**: Relevant as a reference for improving automatic task routing
4. **Agent Teams file locking**: A collision-prevention mechanism for concurrent edits by multiple workers
5. **AutoAgent meta-optimization**: Automatic improvement of the harness itself could inform more advanced automatic skill updates in claude-org

---

## 7. Summary

claude-org occupies a distinct position: persistent organizational operation by multiple AI instances. Most existing OSS focuses on agent coordination during task execution, while claude-org aims at **continuous operation and self-improvement of the organization itself**.

Even Claude Code Agent Teams, the closest project, does not include a resident Curator or a self-growth loop. The claude-org design fills a clear gap in the current OSS landscape.

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
---
