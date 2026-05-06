# claude-org — Capabilities Guide

This repository is a **system for getting work done with a team of AI assistants**.
You speak to only one "Lead." Behind the scenes, multiple specialists work in parallel.

---

## What You Can Do

### Request work

You can start work by simply stating what you want, such as "Add an article to the blog" or "Fix the product page on the ecommerce site." You do not need to use technical terms.

- The Lead understands the request and assigns the work to the appropriate specialist (Worker)
- Multiple tasks can proceed at the same time
- If the target project is unclear, the system presents options and asks

### Check status

- The Lead reports progress
- If you say "Show me the dashboard," you can review the overall state in the browser
  - Project list
  - Current work status
  - Recent events
  - Accumulated knowledge

### Pause and resume

- If you say "We're done for today," all state is saved
- The next time you start, it reports the previous state and resumes from there
- Even if you close the terminal unexpectedly, some state can be recovered

---

## Organization Roles

| Role | What it does | How it relates to you |
|---|---|---|
| **Lead (Secretary)** | Talks with you, assigns work, reports results | **The only role you speak to directly** |
| **Dispatcher** | Launches and manages specialists on your behalf | No need to think about it |
| **Curator** | Organizes learnings and proposes improvements | No need to think about it |
| **Worker** | Performs the actual work (code edits, research, file creation, etc.) | No need to think about it |

You interact only with the Lead. Everything else runs automatically behind the scenes.

---

## Basic Flow

```
1. Start Claude Code
2. Run /org-start (first time only. If previous state exists, it is reported automatically)
3. State what you want to do
4. Receive the result report
5. When finished, say "We're done for today"
```

---

## How the Organization Gets Smarter

The more you use it, the more the organization learns and improves.

1. Each time work completes, the specialist records what it learned
2. The Curator periodically organizes and merges those learnings
3. The organized knowledge is stored by theme
4. When process improvements are needed, they are proposed through the Lead
5. If you approve them, the improved process is used from the next run onward

If an improvement proposal misses the mark, you can reject it by saying "Not needed."

---

## Project Management

When you request work, the project (work target) is registered automatically. After that, it can be recognized by a short name alone.

Examples:
- "blog" -> company blog site
- "ecommerce site" -> ecommerce sales site
- "CSV aggregation tool" -> web app for CSV upload and aggregation

You can list registered projects with "Show me the dashboard."

---

## If Something Goes Wrong

- **Not sure what to ask for** -> Try asking, "What can you do?"
- **The result looks wrong** -> Tell the Lead, and it will instruct the specialist to fix it
- **Not sure about the overall state** -> Check with "Show me the dashboard"
- **Want to continue from last time** -> Start it and the previous state is shown automatically
---
