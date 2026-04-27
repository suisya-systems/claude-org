# claude-org — What You Can Do

This repository is **a system for getting work done with a team of AI assistants**.
You only ever talk to one role: the **Lead**. Behind the scenes, several specialized roles run in parallel.

---

## What it can do for you

### Hand off work

Say what you want done in plain language — "add a new post to the blog", "fix the product page on the storefront" — and the work begins. You don't need to use technical vocabulary.

- The Lead understands the request and routes it to the right role (a Worker)
- Several pieces of work can run at the same time
- If it's unclear which project you mean, the Lead asks with a short list of choices

### Check on what's happening

- The Lead reports progress back to you
- Say "show me the dashboard" and you'll get a browser view of:
  - The list of projects
  - Currently running work
  - A recent activity timeline
  - Knowledge accumulated so far

### Suspend and resume

- Say "we're done for today" and the full state is saved
- Next time you start, the Lead reports the previous state and you pick up where you left off
- Even if the terminal is closed abruptly, most of the state can still be recovered

---

## The roles in the organization

| Role | What it does | Your interaction |
|---|---|---|
| **Lead** | Talks with you, assigns work, reports results | **The only role you speak to directly** |
| **Dispatcher** | Spawns and manages Workers on the Lead's behalf | None needed |
| **Curator** | Organizes accumulated knowledge, suggests improvements | None needed |
| **Worker** | Does the actual work — code edits, investigation, file authoring, etc. | None needed |

You only deal with the Lead. The rest run automatically in the background.

---

## How a session flows

```
1. Start Claude Code
2. Run /org-start (only the first time per session — prior state is reported automatically)
3. Tell the Lead what you want done
4. Receive the report when it's finished
5. Say "we're done for today" when you're stopping
```

---

## How the organization gets smarter over time

The more you use it, the more the organization learns and improves.

1. Each time work completes, the responsible role records what was learned
2. The Curator periodically organizes and consolidates those notes
3. Curated knowledge is filed by topic
4. When a process change would help, the Lead surfaces a proposal
5. If you approve, future sessions run with the improvement in place

If a proposal misses the mark, just say "skip that" and it's discarded.

---

## Project management

When you ask for work, the project (the thing being worked on) is registered automatically. After that, you can refer to it by a short nickname.

Examples:
- "the blog" → company blog site
- "the storefront" → e-commerce site
- "the CSV tool" → CSV upload + aggregation web app

To see what's registered, say "show me the dashboard".

---

## When you're stuck

- **Not sure what to ask for** → Try "what can you do?"
- **The result looks wrong** → Tell the Lead; corrections are dispatched to a Worker
- **Want a sense of the whole picture** → "Show me the dashboard"
- **Want to continue from last time** → Just start the session — the previous state is reported automatically
