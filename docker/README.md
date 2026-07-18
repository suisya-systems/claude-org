# claude-org-ja Docker distribution (PoC)

Distributes the whole org (Claude Code CLI / claude-org-runtime / broker daemon / both tmux and herdr backends / the skill set / dashboard) as a pre-set-up image. The design SoT is [`docs/design/org-docker-distribution.md`](../docs/design/org-docker-distribution.md).

## ⚠️ What this image does NOT contain (pre-distribution checklist)

The following are **never baked into the image** (blocked by the two layers of [`docker/Dockerfile.dockerignore`](./Dockerfile.dockerignore) + the build-time secret scan; if even one slips in, the build fails):

- [ ] `.state/**` — state.db, worker state, broker tokens
- [ ] `CLAUDE.local.md`, `.env*`, `tmp/` — personal briefs / local secrets
- [ ] `**/settings.local.json` (including `.override` / `.bak`) — per-role local settings
- [ ] `knowledge/raw/**` — raw logs of org operation
- [ ] `.venv/`, `.worktrees/`
- [ ] `.git` (a carry-in path for secrets via reflog / stash. The repo inside the image is not a git repo but an "executable body"; ja self-edits inside the container are done via a fresh clone into workers)
- [ ] Any Claude / gh / Codex / Slack / Google credentials (they live under HOME and are structurally never part of the build context. They are generated into the volume at first boot)

## Quick start

```bash
# 1. build (repo root is the context. Single arch, local)
docker compose -f docker/compose.yaml build

# 2. start the infra (broker daemon + dashboard)
docker compose -f docker/compose.yaml up -d

# 3. first time only: auth setup (Claude /login → gh auth login → codex login →
#    org_setup_prune.py. Everything persists in the org_home volume)
docker exec -it claude-org org-shell --setup

# 4. normal path: secretary TUI (org up inside the tmux session) → /org-start
docker exec -it claude-org org-shell
```

Detach with `Ctrl-b d`, reattach with `docker exec -it claude-org org-shell`.

## Environment variables (compose)

| Variable | Default | Meaning |
|---|---|---|
| `ORG_TRANSPORT` | `broker` (fixed) | The container distribution supports broker only (renga assumes host interaction and is out of scope) |
| `ORG_BACKEND` | `tmux` | `tmux` \| `herdr`. Switch via `docker compose up -d --force-recreate` (rebuilds the daemon) |
| `ORG_MAX_WORKERS` | `3` | Worker parallelism cap. Conservative default sized for a Raspberry Pi 5 16GB. Up to 8 on a well-provisioned host |
| `ORG_DASHBOARD_EXPOSE` | `1` | Whether to expose the dashboard on the host loopback |
| `ORG_BROKER_PORT` | `48720` | The broker daemon's listen port (127.0.0.1 inside the container) |
| `ORG_UID` / `ORG_GID` | `1000` | Build args. When using host bind mounts, rebuild with `ORG_UID=$(id -u)` |

## dashboard

`http://127.0.0.1:8099` (**host loopback only**). The dashboard has no authentication, so it **must not be exposed to the LAN**. To view it remotely, use a port-forward: `ssh -L 8099:127.0.0.1:8099 <host>`.

## Terminal backends (tmux / herdr)

- The default is **tmux**. herdr is opt-in via `ORG_BACKEND=herdr` (bundled in the image; excludable with an `INSTALL_HERDR=0` build).
- herdr's false-reap (runtime #114) was fixed in runtime 0.1.33, and herdr is officially supported. tmux stays the default only because the "pure headless in container → later TUI attach" path has not been measured yet (design §9, §12 H1).
- Check the running backend: `docker exec claude-org cat .state/broker/daemon.json | jq .backend`

## Using Docker from workers (disabled by default)

The default is to **not** pass the host Docker socket. Only when needed:

```bash
docker compose -f docker/compose.yaml -f docker/compose.docker-optin.yaml up -d
```

A socket mount grants privileges equivalent to host root. Read the warning inside the overlay file before using it.

## Multi-arch build (amd64 + arm64 / Raspberry Pi 5)

```bash
docker buildx build -f docker/Dockerfile \
  --platform linux/amd64,linux/arm64 \
  --build-arg REPO_REF="$(git describe --always)" \
  -t ghcr.io/suisya-systems/claude-org-ja:$(git describe --always)-r0.1.36 \
  --push .
```

- The image tag convention is `<repo-ref>-r<runtime-version>` (design §7.7). To update the runtime, **rebuild — never upgrade at boot**. When the runtime drift warning (org-start Block C2) appears inside the container, the correct handling is "pull / rebuild a newer tag".
- **Raspberry Pi 5 caveat**: the default kernel uses a 16KB page size, and Rust binaries (herdr, the ripgrep bundled with Claude Code) crash — a known issue. If it does not boot, append `kernel=kernel8.img` to `/boot/firmware/config.txt` to switch to the 4KB kernel (design §11).

## Security boundary essentials

- All in-container processes are non-root (`org`, UID 1000 default). Root is only PID1 tini and the head of the entrypoint doing the one-time chown. `docker exec` enters as root, but the primary path `org-shell` immediately self-demotes to org.
- The compose file sets `seccomp=unconfined`. It is required for Claude Code's Bash sandbox (bubblewrap) to create user namespaces — the trade-off of "loosening the container-boundary seccomp to keep the inner bwrap sandbox alive" (verification matrix in design §7.5). In exchange, it tightens with `cap_drop: ALL` (only minimal caps restored) and `no-new-privileges`.
- The Claude Code CLI / herdr / runtime venv are all baked outside the volumes (`/opt`). **Every update is an image rebuild** (no self-update at boot).
- Do not co-locate other containers on this compose project's network (socat listens on 0.0.0.0 inside the container, so the dashboard is reachable without auth from the same network).
- No SSH daemon is bundled. Remote use is "SSH to the host → docker exec".

## Troubleshooting

| Symptom | Handling |
|---|---|
| `org-shell` says "Claude credentials not found" | Run first-time setup from `org-shell --setup` |
| broker `no_backend` | Check that the `ORG_BACKEND` value matches the backend in daemon.json. For herdr, check that `herdr --version` works inside the container |
| bwrap / sandbox errors | Check that the compose `seccomp=unconfined` is in effect, and that you are not on rootless Docker / Ubuntu 24.04 AppArmor restrictions (design §7.5) |
| Old panes visible after `docker restart` | The entrypoint reconcile discards `.state/broker` on every boot by design. If they persist, check the reconcile logs |
| herdr / ripgrep dies instantly on Pi 5 | The 16KB page size issue. Switch to the 4KB kernel (above) |
