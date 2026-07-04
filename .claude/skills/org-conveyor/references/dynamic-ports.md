# Dynamic port-allocation discipline (avoiding port collisions in parallel verify)

[`/org-conveyor`](../SKILL.md) runs **multiple workers in parallel, up to the number of free panes**, under backpressure. Each worker runs verify in a separate worktree, so if it stands up a **fixed-port app** (Next.js dev server `:3000` / broker server / a local HTTP service, etc.), the **ports collide** and a verify started later either dies with `EADDRINUSE` or hits another worker's process and mis-decides.

The finalized policy of Issue #637 solves this with **dynamic port allocation** (it does not adopt serializing verify into a lane, so as not to kill parallelism). In a word, the discipline is **"do not write the port as a fixed value; receive it via env"**.

## Discipline

1. **The app / server receives its listen port from env**. Do not bake a fixed port into the code.
   - The default env name is `PORT` (the convention of many frameworks). If an app has its own env, follow that (e.g. Next.js uses `PORT`, the broker server has its own port env). State the env name in the verify policy ([`.claude/skills/org-conveyor/references/scope-contract.md`](scope-contract.md)).
2. **conveyor / worker dynamically reserves a free port for each verify and passes it via env to both the app and the checking side**. Do not write a repro command with a hardcoded port number.
3. **Reflect the env-passed port in the repro command too** and transcribe it into PR `## Test plan` ([`.claude/skills/org-conveyor/references/verify-evidence.md`](verify-evidence.md)). Because the port number changes each run, **show it by env name in the Test plan and do not bake in a concrete value** (a re-tester can re-reserve one under the same discipline).

## Reserving a free port (portable)

Let the OS assign an ephemeral port (bind to `:0`, close immediately, and use the number you got). Do not depend on repo-specific tooling:

```bash
# Reserve one free port and put it in env
PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("",0));print(s.getsockname()[1]);s.close()')
# Pass the same env to both the app and the check
PORT="$PORT" tools/run.sh &          # the app listens on PORT
curl -s "localhost:$PORT/health"     # the check hits the same PORT
```

> A race where another process grabs the same port between bind→close→use is theoretically possible, but the ephemeral range is wide and at the parallelism in play (= free pane count, a few at most) real harm is unlikely. For apps that need certainty, you may switch to the "have it print the port to stdout right after startup and grab that" approach (if the framework supports it).

## How to put it into the worker brief

- For heavy-lane delegations that involve parallel verify, state clearly in the brief via [`/org-delegate`](../../org-delegate/SKILL.md)'s `--impl-guidance` etc.: "no fixed ports / receive via `PORT` env / write repro commands via env".
- Leave a one-line note of the env name and reservation method in the verify policy (scope contract), pinning down the assumption that conveyor admits multiple workers.

## Rejected option (serializing verify into a lane)

Serializing verify one at a time would avoid collisions even with fixed ports, but it **kills the belt's parallelism (backpressure)**, so Issue #637 does not adopt it. With dynamic ports you avoid collisions while staying parallel. If an app that truly requires serialization appears (an exclusive lock on a shared DB or other non-port resource contention), that is a scope edge — state it in the scope contract and seek human judgment.
