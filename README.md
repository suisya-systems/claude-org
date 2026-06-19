# claude-org

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/suisya-systems/claude-org/actions/workflows/tests.yml/badge.svg)](https://github.com/suisya-systems/claude-org/actions/workflows/tests.yml)

> English-edition reference distribution. The Japanese edition is at [suisya-systems/claude-org-ja](https://github.com/suisya-systems/claude-org-ja).

## What is this

claude-org is an operations layer for running Claude Code over long sessions with a "one Secretary the human talks to + many Workers running behind the scenes" structure. You only talk to one Secretary Claude. Task breakdown, assignment to Workers, saving and restoring work state, and curating accumulated learnings all run automatically behind the scenes.

It is not for running agents end-to-end on full autopilot. It is for people who want to draw a clear line on "where human approval is required from here on" and run 3 to 5 Workers in a quality-first manner.

## Quick start

If the prerequisite tools (git / claude / renga / gh / jq / Node.js / Python) are installed, you can clone and set up with a one-liner.

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/suisya-systems/claude-org/main/scripts/install.sh | bash
```

```powershell
# Windows (PowerShell 7+)
iwr -useb https://raw.githubusercontent.com/suisya-systems/claude-org/main/scripts/install.ps1 | iex
```

After cloning, run the following only the first time.

```bash
cd claude-org
source .venv/bin/activate                                # Linux / macOS
bash scripts/install-hooks.sh                            # Pre-commit secret scanner
python tools/org_setup_prune.py --user-common-sandbox    # Harden personal settings (once only)
claude-org-runtime org up                                # Launch the Secretary
```

Once the Secretary is up, run `/org-setup` (deploy permission settings) then `/org-start` (start the organization) — first time only. From the second launch onward, just `claude-org-runtime org up` then `/org-start` is enough to resume. See [`docs/getting-started.md`](docs/getting-started.md) for prerequisites, manual steps, and troubleshooting.

## How it works

```
human <-> Secretary (command post)
              |- Dispatcher (proxies Worker launches and instructions)
              |- Curator (organizes learnings; launched only when needed)
              `- Workers (do the actual work; auto-clean when done)
```

- **Secretary** — The sole party the human talks to. Breaks down tasks, makes decisions, reports results.
- **Dispatcher** — Takes over Worker launches and instructions for the Secretary, reducing wait time.
- **Curator** — Turns accumulated learnings into organized knowledge. Spins up only when needed.
- **Worker** — Does the actual work in a per-task working directory, and auto-cleans when done.

<table>
  <tr>
    <td width="50%"><img src="docs/assets/org-start-fresh.png" alt="Right after /org-start: Secretary and Dispatcher are running"></td>
    <td width="50%"><img src="docs/assets/org-start-pane-layout.png" alt="In operation: Secretary, Dispatcher, plus parallel Workers in flight"></td>
  </tr>
</table>

## Key features

- **Humans only judge** — Launch, distribution, and state management are delegated to the Secretary; the human only responds when called. Judgment-escalations and blockers are always escalated to the human, preventing drops.
- **Explicit permission boundaries and defense in depth** — Full permissions are not handed out blanket; each task gets its own working directory. Sandboxes, hooks, and permission boundaries apply to every task.
- **Quality-first small-scale parallelism** — Not a large farm — 3 to 5 Workers. Independent review by a model separate from the implementation (`codex`, optional) can also be built into verification.
- **Suspend / resume and automatic knowledge curation** — Work state and learnings are not lost even when running over long sessions.

For design background (safety model / a reference implementation of Loop Engineering / comparison with existing tools), see [`docs/overview-business.md`](docs/overview-business.md) and [`docs/overview-technical.md`](docs/overview-technical.md).

## Skill cheat sheet

Secretary operations fall into three families.

- **Organization operations `/org-*`** — `/org-start` (launch), `/org-delegate` (delegation), `/org-suspend` / `/org-resume` (suspend / resume), `/org-retro` (retrospective), `/org-dashboard` (status), and more.
- **Secretary handover `/secretary-*`** — `/secretary-handover` / `/secretary-resume` (swap only the Secretary without stopping the organization).
- **Skill-system meta operations `/skill-*`** — `/skill-eligibility-check` / `/skill-audit` (skill generation judgment and inventory).

## Learn more

- [`docs/getting-started.md`](docs/getting-started.md) — Setup, prerequisites, manual steps, troubleshooting
- [`docs/overview-business.md`](docs/overview-business.md) — Friendly overview from a business perspective
- [`docs/overview-technical.md`](docs/overview-technical.md) — Architecture, four-layer stack, MCP tool details
- [`docs/non-goals.md`](docs/non-goals.md) — Features intentionally not included
- [`docs/oss-comparison.md`](docs/oss-comparison.md) — Comparison with related projects
- [`docs/verification.md`](docs/verification.md) — Testing and safety (attack vectors x defense layers)
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — Contribution guide

For issues, head to [Issues](https://github.com/suisya-systems/claude-org/issues).

## License

[MIT License](LICENSE) (c) 2026 Ryo Iwama
