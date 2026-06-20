# claude-org

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/suisya-systems/claude-org/actions/workflows/tests.yml/badge.svg)](https://github.com/suisya-systems/claude-org/actions/workflows/tests.yml)

> This is the English-edition reference distribution. The Japanese edition is [suisya-systems/claude-org-ja](https://github.com/suisya-systems/claude-org-ja).

## What is this
A Claude Code organizational operations harness, well suited as a first step for people who are "interested in harness engineering or loop engineering but find it hard to build their own from scratch."

claude-org is a Claude Code organizational harness for running Claude Code over long sessions in a "one human-facing Secretary + many Workers behind it" configuration. You only ever talk to a single Secretary Claude Code, while task breakdown, work assignment to Workers, saving and resuming work state, and curating accumulated learnings all run automatically behind the scenes.
It also includes a feature that proposes skill fixes and new skills based on the accumulated learnings.

The design minimizes human intervention: outside of task selection, push / PR creation, and important design decisions, it delegates authority to the agents and lets them run autonomously as much as possible.

The security settings required to provide these features are built in ahead of time.

## Quick start

If the prerequisite tools (git / claude / renga / gh / jq / Node.js / Python) are installed, you can clone and set up with a single one-liner.

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/suisya-systems/claude-org/main/scripts/install.sh | bash
```

```powershell
# Windows (PowerShell 7+)
iwr -useb https://raw.githubusercontent.com/suisya-systems/claude-org/main/scripts/install.ps1 | iex
```

After cloning, run the following once on the first time.

```bash
cd claude-org
source .venv/bin/activate                                # Linux / macOS
bash scripts/install-hooks.sh                            # Secret scanner that runs right before commit
python tools/org_setup_prune.py --user-common-sandbox    # Harden personal settings (one time only)
claude-org-runtime org up                                # Launch the Secretary
```

Once the Secretary is up, run `/org-setup` (place permission settings) → `/org-start` (start the organization) in that order, but only the first time. From the second time onward, you can resume with just `claude-org-runtime org up` → `/org-start`. For prerequisites, manual steps, and troubleshooting, see [`docs/getting-started.md`](docs/getting-started.md).

## How it works

```
Human <-> Secretary (command role)
        ├─ Dispatcher (proxies Worker launch and instructions)
        ├─ Curator (curates knowledge; launched only when needed)
        └─ Worker pool (implementation work; automatically cleaned up when done)
```

- **Secretary** — the only one a human talks to. Breaks down tasks, makes decisions, and reports results.
- **Dispatcher** — takes over launching Workers and issuing instructions, reducing wait time.
- **Curator** — turns accumulated learnings into organized knowledge. Comes up only when needed.
- **Worker** — does implementation work in a per-task working area, and cleans up automatically when done.

<table>
  <tr>
    <td width="50%"><img src="docs/assets/org-start-fresh.png" alt="Right after /org-start: Secretary and Dispatcher are running"></td>
    <td width="50%"><img src="docs/assets/org-start-pane-layout.png" alt="In action: parallel Workers running in addition to Secretary and Dispatcher"></td>
  </tr>
</table>

## Key features

- **Humans only decide** — leave startup, distribution, and state management to the Secretary; humans just return a decision when called. Decision requests and blockers are always escalated to a human, preventing things from slipping through.
- **Explicit permission boundaries and defense in depth** — rather than handing out full permissions uniformly, work areas are separated per task. Sandbox, hooks, and permission boundaries apply to every task.
- **Quality-first, modestly parallel** — 3 to 5 Workers rather than a large farm. An independent review by a model separate from the implementation (`codex`, optional) can also be built into verification.
- **Suspend/resume and automatic knowledge curation** — even over long runs, work state and learnings are not lost.

The design background (safety model / a reference implementation of Loop Engineering / comparison with existing tools) is summarized in [`docs/overview-business.md`](docs/overview-business.md) and [`docs/overview-technical.md`](docs/overview-technical.md).

## Skill cheat sheet

Secretary operations are divided into three groups.

- **Organizational operations `/org-*`** — `/org-start` (startup), `/org-delegate` (delegation), `/org-suspend` / `/org-resume` (suspend / resume), `/org-retro` (retrospective), `/org-dashboard` (status), and more
- **Secretary handover `/secretary-*`** — `/secretary-handover` / `/secretary-resume` (swap only the Secretary without stopping the organization)
- **Skill-system meta-operations `/skill-*`** — `/skill-eligibility-check` / `/skill-audit` (skill creation decisions and inventory)

## Learn more

- [`docs/getting-started.md`](docs/getting-started.md) — setup, prerequisites, manual steps, troubleshooting
- [`docs/overview-business.md`](docs/overview-business.md) — a gentle, business-perspective overview
- [`docs/overview-technical.md`](docs/overview-technical.md) — architecture, four-layer stack, MCP tool details
- [`docs/non-goals.md`](docs/non-goals.md) — features intentionally not included
- [`docs/oss-comparison.md`](docs/oss-comparison.md) — comparison with related projects
- [`docs/verification.md`](docs/verification.md) — testing and safety (attack vector × defense layer)
- [`docs/operations/dispatcher-view.md`](docs/operations/dispatcher-view.md) — how to keep the dispatcher continuously visible next to the Secretary (WezTerm / tmux)
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — contribution guide

If you run into trouble, head to [Issues](https://github.com/suisya-systems/claude-org/issues).

## License

[MIT License](LICENSE) © 2026 Ryo Iwama
