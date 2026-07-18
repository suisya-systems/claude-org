# Distributable Docker image for the whole org — design

> Status: **design + PoC skeleton** (task org-docker-image-design-001). All findings of the pre-implementation Codex design review (Blocker 4 / Major 7 / Minor 3 / Nit 3) are incorporated. The PoC artifacts live under [`docker/`](../../docker/) (Dockerfile / compose.yaml / entrypoint.sh / Dockerfile.dockerignore / README.md and others).
>
> **EN mirror note**: the `docker/` PoC artifacts are mirrored into this repository as-is from the ja repository at the ja#732 merge SHA (manual-triage decision on tracking issues #513 / #520: scripts imported mechanically, only `docker/README.md` hand-translated). The scripts therefore carry ja-language comments, following the same ride-along policy as runtime docstrings (`docs/canonical-ownership.md`).
>
> Audience: humans who build and operate the image, and workers who maintain docker/.
>
> Primary inputs:
> - The full pre-implementation Codex design review (knowledge-side `tmp/codex-review-org-docker-image-design-001.md`, outside the ja repo)
> - [`.claude/skills/org-start/SKILL.md`](../../.claude/skills/org-start/SKILL.md) (startup contract) / [`.claude/skills/org-setup/SKILL.md`](../../.claude/skills/org-setup/SKILL.md) (settings placement)
> - [`docs/contracts/backend-interface-contract.md`](../contracts/backend-interface-contract.md) Surface 8 (broker auth & delivery / push primary)
> - knowledge/curated/broker.md, herdr.md (on the ja operational repo side), runtime CHANGELOG 0.1.33–0.1.36

---

## 1. Purpose and scope

**Purpose**: make the whole claude-org-ja organization (Claude Code CLI, claude-org-runtime venv, broker daemon, both tmux / herdr terminal backends, the skill set, and the dashboard) distributable as a pre-set-up Docker image. Targets are x86_64 plus **ARM64 (Raspberry Pi 5 16GB)** multi-arch.

**In scope**:
- Fixing the boundary of what is baked into the image and what is not (§3, §6)
- Contract for in-container process supervision (§5)
- Persistence boundary (volume design, §6)
- First-boot path (auth is separated from the image; a human completes it interactively the first time. §10)
- Multi-arch build (§11)
- PoC: a skeleton that can be built and boot-checked locally (§12)

**Out of scope**:
- Full automation of authentication (issuing tokens for Claude / gh / Codex / Slack / Google MCP presupposes human interaction)
- Implementing an auth mechanism for the dashboard (only the exposure-boundary policy is decided. §7.4)
- Support for orchestrators other than Docker Compose, such as Kubernetes
- Automatic image publish in CI (tag operation design only. §7.7)

## 2. Established facts (confirmed by investigation)

Facts confirmed by investigation that ground the design decisions.

1. **Startup contract**: `/org-start` proceeds in the order (0) `ORG_TRANSPORT` detection → MCP connectivity → identity verification → workers_dir check → parallel Block A (dispatcher spawn) / B (state.db) / C (dashboard) / C2 (runtime drift) / C3 (queue watcher) → Block D join ([`.claude/skills/org-start/SKILL.md`](../../.claude/skills/org-start/SKILL.md)). Dispatcher / worker spawn happens as panes started by the broker daemon (tmux detached session / herdr pane), and the two-step approval prompts (folder-trust and dev-channel) are machine-approved by the orchestrator via `send_keys(enter=true)`.
2. **Settings placement**: org-setup places `~/.claude/settings.json` (user-common) and per-role `settings.local.json` (`.claude/` / `.dispatcher/.claude/` / `.curator/.claude/`; workers get theirs generated dynamically in the worker directory). Claude Code only reads the `.claude/` of its launch directory.
3. **workers_dir**: `workers_dir: ../workers` in `registry/org-config.md` (relative to the repo). Placing the repo at `/workspace/claude-org-ja` makes it resolve naturally to `/workspace/workers`.
4. **Persistent / volatile split of .state/**: persistent = `state.db` (the sole SoT), `workers/`, `pending_decisions.json`, `notes/`, `attention.json`, dispatcher cursors. Volatile = `dashboard.pid` / `dashboard.log`, `broker/` (daemon.json pid/port, admin.token, queue.jsonl, secretary-mcp.json, herdr_*), `pr-watch-*.log`, pid sidecars.
5. **broker daemon**: `claude-org-runtime broker serve --port (default 48720) --host (default 127.0.0.1) --state-dir --backend {wezterm,tmux,herdr}`. The higher-level command `claude-org-runtime org up` secures the daemon (reuses it when healthy) + starts the secretary TUI. The tmux backend uses the dedicated socket `claude-org-broker` (overridable via `ORG_BROKER_SOCKET`). The channel sidecar is `python -m claude_org_runtime.broker.channel_sidecar` (env-driven; the generated mcp-config such as secretary-mcp.json is injected).
6. **Current state of herdr**: false-reap (runtime #114) was **fixed in runtime 0.1.33 (2026-07-03)** (PR #115: spawn-then-move + `pane.get` authoritative liveness). 0.1.34 added the workspace layout policy, and 0.1.36 completed `delegate-plan` support for herdr pane ids (`w<N>:p<N>`). With the current pin 0.1.36 + herdr 0.7.3 there is no known Blocker preventing real org runs on the herdr backend (a real daemon has a track record running with `--backend herdr`). herdr is a Rust static-pie single binary with distributions for both x86_64 / aarch64 targets (https://herdr.dev, update manifest `latest.json`).
7. **Claude Code CLI**: native installer, not npm (`~/.local/bin/claude` → symlink into a versions directory). Skipping authentication requires persisting **both** `~/.claude/.credentials.json` **and** `~/.claude.json` (directly under HOME).
8. **Anthropic official devcontainer**: precedent configuration with a non-root user, a named volume for `/home/node/.claude`, and `--cap-add NET_ADMIN/NET_RAW` (for the egress firewall).
9. **bubblewrap inside containers**: Claude Code's Bash sandbox (bwrap) uses user-namespace creation, which is blocked by Docker's default seccomp profile. In practice `--security-opt seccomp=unconfined` (or a custom profile allowing unshare/clone) is required. Known failure patterns: Ubuntu 24.04+ AppArmor userns restriction and hosts with `kernel.unprivileged_userns_clone=0`.
10. **Raspberry Pi 5**: the default kernel uses a 16KB page size, and jemalloc-family binaries (Rust-built, etc.) crash with "unsupported system page size" — a known issue. The workaround is switching to `kernel=kernel8.img` (4KB).

## 3. What is NOT included in the image (checklist)

Listed first to prevent distribution accidents (the same checklist is also placed at the top of [`docker/README.md`](../../docker/README.md)).

| Category | Target | Blocking mechanism |
|---|---|---|
| Org operational state | `.state/**` (state.db, workers, broker tokens) | `.dockerignore` + secret-scan stage (§7.3) |
| Personal briefs | `CLAUDE.local.md`, `.env*`, `tmp/` | Same as above |
| Per-role local settings | `**/settings.local.json` (including `.override`, `.bak`) | Same as above |
| Raw knowledge | `knowledge/raw/**` (curated is git-tracked, so baking it in is fine) | Same as above |
| Local venv / worktrees | `.venv/`, `.worktrees/` | Same as above |
| Claude auth | `~/.claude/.credentials.json`, `~/.claude.json` | Outside the build context (HOME is not part of the context) + generated into the volume by the first-boot path |
| gh / Codex / Google auth | `~/.config/gh/`, `~/.codex/`, `~/.config/gogcli/` | Same as above |
| Slack MCP OAuth | Inside Claude Code's credential store | Same as above |

## 4. Overall architecture

The whole org fits into a **single container** (one `org` service). Dispatchers / workers are not "containers" but **in-container panes** managed by the broker daemon (tmux detached sessions or herdr panes), so there is no necessity to split containers — splitting would break the tmux socket / broker HTTP / spawn ritual across container boundaries.

```text
tini (PID1)
 └─ entrypoint.sh (root → ownership repair → gosu org)
     ├─ [reconcile] leftover cleanup (§7.1)
     ├─ broker daemon: claude-org-runtime broker serve --backend ${ORG_BACKEND} ... (resident)
     ├─ dashboard: python3 dashboard/server.py (resident, §7.4)
     └─ wait loop (SIGTERM trap → sequential shutdown)

docker exec -it claude-org org-shell   ← primary human path (interactive surface)
 └─ inside the tmux session: claude-org-runtime org up (daemon reuse) → secretary TUI
     └─ /org-start (dispatcher spawn; folder-trust approval appears on the exec'ing human's TTY)
```

- **The transport defaults to a fixed `ORG_TRANSPORT=broker`**, and the README / compose / Dockerfile `ENV` are kept consistent (Minor fix. renga is a host-interactive tool and out of scope for container distribution; users who need to switch back return to host operation).
- **No SSH daemon is bundled** (not "disabled by default" but **not bundled**). The primary path is `docker exec` + `tmux attach`. Remote use is covered by the two hops "SSH to the host → docker exec"; an in-container sshd only adds attack surface for key management and port exposure (Minor fix).

## 5. Blocker 1: contract for in-container process supervision

Fix **who starts what, in which order**.

| Stage | Actor | What it starts | On failure |
|---|---|---|---|
| 1 | tini (PID1) | entrypoint.sh | Container exits |
| 2 | entrypoint (root) | One-time volume ownership repair (§8) | fail-fast (explicit error) |
| 3 | entrypoint (gosu org) | Leftover reconciliation (§7.1) → if `.state/state.db` is absent, `python -m tools.state_db.importer --rebuild --no-strict` | fail-fast |
| 4 | entrypoint (org) | broker daemon (`broker serve --backend ${ORG_BACKEND} --state-dir .state/broker --port ${ORG_BROKER_PORT}`) | fail-fast (the org cannot exist without the daemon) |
| 5 | entrypoint (org) | dashboard (`python3 dashboard/server.py`) | Warn and continue (loss of observability, not loss of function) |
| 6 | Human (`docker exec`) | `org-shell` → inside tmux, `claude-org-runtime org up` (reuses the healthy daemon, starts only the secretary TUI) → `/org-start` | Resolve interactively |
| 7 | secretary / dispatcher | dispatcher / worker pane spawn (via broker, as before) | Conventional error branches (`no_backend`, etc.) |

Key design points:

- **Daemon first, TUI later**. The folder-trust / dev-channel approval prompts are only needed by Claude Code sessions (secretary, dispatcher, worker), and all of these appear either on "the TTY a human is exec'ed into" or in "panes the orchestrator machine-approves via send_keys". Because the (non-interactive) entrypoint never starts Claude Code, it is **structurally guaranteed that the first-boot path never stalls at `docker exec` time** (no prompt is ever shown where nobody can answer it).
- **The entrypoint does not start the channel sidecar or the tmux server** (explicit contract). The channel sidecar (`org-broker-channel`) is contained within each pane's spawn ritual (the daemon-generated mcp-config is loaded as Claude Code's dev-channel and starts as a per-session child process, machine-approved). The tmux server is implicitly started by the broker daemon on the first pane spawn, on the dedicated socket (`claude-org-broker`). Likewise the herdr server, for the herdr backend, is the daemon's responsibility. What the supervisor (entrypoint) starts directly is only the daemon and the dashboard, per the §5 table.
- The `ORG_TRANSPORT` decision is made by `/org-start` Step 0 as before. The image only provides `ENV ORG_TRANSPORT=broker` and does not touch the decision logic itself.
- **No pre-relaxation of folder-trust**. Injecting settings such as `hasTrustDialogAccepted` depends on Claude Code internals and is fragile, and the existing machine-approval path (spawn-flow 3-2/3-3b) works as-is inside the container, so it is unnecessary.
- Shutdown contract: the entrypoint traps SIGTERM and folds down in the order (a) stop the dashboard → (b) stop the broker daemon (equivalent to `org down`, including pane reap) → (c) kill the tmux server. tini reaps zombies within the grace period before SIGKILL.

## 6. Blocker 2: persistence boundary (volume design)

Named volumes — **purpose carved into the name** — are composed of 3 volumes + a bundle of symlinks inside the repo.

| Volume name | Mount point | Contents | Category |
|---|---|---|---|
| `org_home` | `/home/org` | `~/.claude` (auth + user-common settings), `~/.claude.json`, `~/.config/gh`, `~/.codex`, `~/.config/gogcli`, shell history | **Auth + user settings** |
| `org_state` | `/workspace/claude-org-ja/.state` | state.db, workers/, pending_decisions.json, notes/, attention.json, **role-config/ (the actual per-role settings.local.json files, §6.1)** | **Org operational state** |
| `org_workers` | `/workspace/workers` | Worker worktrees / deliverables | **Work products** |

**Separation policy between the auth volume and the settings volume (explicit)**: authentication (`~/.claude/.credentials.json` etc.) and user-common settings (`~/.claude/settings.json`) **live together in the same volume (`org_home`)**. Two reasons. (1) `~/.claude.json` must sit directly under HOME; volume-izing only `~/.claude` makes Claude Code treat it as a fresh install and demand login every time (investigated fact §2-7). Per-file mounts or symlink separation break easily across Claude Code updates. (2) `~/.claude/settings.json` is a file org-setup additively merges — one that "cohabits with personal settings" — and baking it into the image separately from auth invites contamination by personal settings (the reverse-direction accident Codex pointed out). Meanwhile, **per-role settings.local.json goes on the org_state side** (§6.1) — that is the separation line between "auth" and "org settings".

### 6.1 Persisting per-role settings.local.json

Per-role settings (`.claude/settings.local.json`, `.dispatcher/.claude/settings.local.json`, `.curator/.claude/settings.local.json`) are gitignored, hence never baked into the image, and if placed raw in the repo directory (image layer + container ephemeral layer) they **disappear on container re-creation**. As a countermeasure the entrypoint creates these symlinks:

```text
.claude/settings.local.json            → .state/role-config/secretary.settings.local.json
.dispatcher/.claude/settings.local.json → .state/role-config/dispatcher.settings.local.json
.curator/.claude/settings.local.json    → .state/role-config/curator.settings.local.json
```

The actual files live in `role-config/` inside the `org_state` volume and survive re-creation. If the actual files are missing at first boot, the entrypoint prompts for generation equivalent to `python tools/org_setup_prune.py --all` (it does not auto-generate; this is one step of the first-boot path §10 — org-setup includes interactive confirmation). Worker settings.local.json files are dynamically generated by org-delegate inside the `org_workers` volume, so no extra handling is needed.

### 6.2 Persistent / volatile separation inside .state (Major fix)

Even inside the `org_state` volume, **anything tied to process lifetime is discarded by the entrypoint on every boot** (§7.1). Persistent: `state.db`, `workers/`, `pending_decisions.json`, `notes/`, `attention.json`, `role-config/`, dispatcher cursors. Discarded: `broker/` (daemon.json pid/port inevitably goes stale; admin.token / secretary-mcp.json / queue.jsonl are regenerated by the daemon), `dashboard.pid`, `*.log`, pid sidecars such as `attention_pane.json`.

Discarding queue.jsonl means "loss of undelivered messages across a container restart", but a container restart = death of all panes (senders and receivers), so the messages' destination sessions themselves are gone; no delivery guarantee is lost (after restart, re-briefing from `/org-start` is the correct path).

## 7. Responses to Codex findings (Blockers 3–4 / all Majors)

### 7.1 Major 1: reconciliation of tmux socket / broker state leftovers

Run at every boot, in entrypoint stage 3:

1. Delete `.state/broker/` wholesale (sweeping stale daemon.json pid/port, expired admin.token, old secretary-mcp.json, herdr_generation / herdr_sweep.lock). This is also the root fix for the real past dogfood case where disposable state-dirs piled up in `.state/` (in the container the state-dir is fixed to `.state/broker`; only explicit override via `ORG_BROKER_STATE_DIR` is allowed).
2. Delete leftover tmux sockets (`/tmp/tmux-*/claude-org-broker`) and herdr socket / server logs. `/tmp` is assumed tmpfs, but `docker restart` (same-container restart) keeps `/tmp`, so explicit deletion is needed.
3. Delete `.state/dashboard.pid`, `*.log`, and pid sidecars.
4. If `state.db` is absent (fresh volume), rebuild via the importer.

### 7.2 Major 3: fixed container path for workers_dir

By placing the repo at `/workspace/claude-org-ja`, `workers_dir: ../workers` in `registry/org-config.md` **resolves naturally to `/workspace/workers`**. No config rewriting; the "absolute placement of the repo" is fixed as the image's contract (stated in a LABEL and the README). The `org_workers` volume is mounted there.

### 7.3 Blocker 3: preventing secrets from entering the build context

Blocked in three layers:

1. **`.dockerignore`** ([`docker/Dockerfile.dockerignore`](../../docker/Dockerfile.dockerignore); BuildKit's per-Dockerfile ignore mechanism applies it automatically for `docker build -f docker/Dockerfile`): excludes every item of the §3 checklist + `.git`.
2. **Secret-scan build stage (fail-fast)**: the Dockerfile's first stage receives the build context and **fails the build** on detecting either (a) forbidden paths (`.git`, `.state`, `CLAUDE.local.md`, `settings.local.json*`, `.env*`, real files under `knowledge/raw`, `.worktrees`, `.venv`, `tmp`, etc. — **a second layer maintained in tandem with the ignore exclusion set**), or (b) a grep for high-signal token patterns (`sk-ant-`, `ghp_`, `github_pat_`, `xox[bp]-`, `BEGIN ... PRIVATE KEY`). The grep runs with `-l` (file names only) so that **the blocking mechanism itself does not secondarily leak token bodies into the build log**. The runtime stage COPYs from the scanned stage, so content that does not pass the scan never enters the image.
3. **HOME not included**: all credentials live under HOME, which is structurally never part of the build context (the repo root).

**`.git` is not included in the image**. Git history (reflog / stash / dangling objects) is a carry-in path for secrets ever committed locally even once, and cannot practically be inspected by pattern grep, so it is blocked by both the ignore (first layer) and the forbidden-path check (second layer). Consequence: the repo inside the image is an "executable body", not a git repo — **ja self-edit tasks inside the container are done via a fresh clone into the workers directory, like any other project** (the org already supports base-clone placement for new URL projects).

### 7.4 Major 4: dashboard exposure boundary

- `dashboard/server.py` hardcodes a `localhost` bind (invisible from outside the container). **This bind is not changed** (no modification that would point an auth-less server outward by changing the bind).
- Exposure is done via **opt-in socat forwarding**: when `ORG_DASHBOARD_EXPOSE=1` (compose default), the entrypoint starts `socat TCP-LISTEN:18099,bind=0.0.0.0,fork → 127.0.0.1:8099`, and compose publishes it with `127.0.0.1:8099:18099` — **to the host's loopback only**. server.py falls back to 8100/8101 when 8099 is taken, but inside a fresh container 8099 always frees up first, so the forward target is fixed at 8099 (if the fallback ever fires, the forward misses — dashboard loss is warn-only per the §5 contract and the org continues).
- **Auth-less LAN exposure is forbidden**, stated in the README. Users who want LAN exposure must front an authenticated reverse proxy at their own responsibility (out of scope for this design).
- Since socat listens on `0.0.0.0` inside the container, **other containers on the same Docker network can reach it without auth**. The compose comments and README state that no services other than org must cohabit the compose project network.

### 7.5 Major 5: itemized verification of the Claude Code sandbox (bubblewrap)

In-container bwrap is turned into verification items — not "does it work" but the following matrix (not run in the PoC; recorded in the §12 verification checklist):

| # | Verification item | Expectation |
|---|---|---|
| S1 | Run bwrap with Docker default seccomp + default capabilities | Confirm it **fails** (userns creation blocked by seccomp) and that the error is explicitly diagnosed as "sandbox unavailable" |
| S2 | Run bwrap with `security_opt: [seccomp=unconfined]` (compose default) | Succeeds |
| S3 | S2 on a rootless Docker host | Nested userns depends on host kernel settings. Record outcome and diagnostics |
| S4 | S2 on an Ubuntu 24.04+ host (AppArmor userns restriction) | Record whether `apparmor=unconfined` is needed |
| S5 | Combination with `--cap-drop ALL` | Confirm bwrap works without added caps (it assumes unprivileged userns) |
| S6 | Fallback in sandbox-unavailable environments | Confirm Claude Code degrades safely with the sandbox disabled (does not silently gain full power) |

The compose default **does include** `seccomp=unconfined` (Claude Code's Bash sandbox is part of the org's defense layers, and a default that kills it thins the container boundary to a single layer. The unconfined weakening is the trade-off "loosen the container-boundary seccomp to keep the inner bwrap alive", stated explicitly in the README. Replacing it with a custom seccomp profile — allowing only unshare/clone — is a follow-up item).

### 7.6 Major 6: Docker for workers is disabled by default

- The image bundles neither the Docker CLI nor dind. The `/var/run/docker.sock` mount is **not written** in the main compose file.
- Only users who need it explicitly apply [`docker/compose.docker-optin.yaml`](../../docker/compose.docker-optin.yaml) as an `-f` overlay (a warning comment inside the file notes that a host socket mount is effectively host root). DinD is heavy for Pi 5 storage / memory and is not adopted.

### 7.7 Major 7: runtime pin and image rebuild operations

- **No pip upgrade at boot**. The venv is baked at build time with `claude-org-runtime==<pin>`.
- **The Claude Code CLI is baked outside the volume (`/opt/claude-home`)**. The native installer puts the binaries under `$HOME/.local`, so installing naively as the org user swallows the CLI into the `org_home` volume, which means (a) the old CLI in an existing volume permanently masks a new image after rebuild, and (b) a host bind mount for `/home/org` erases the CLI itself. Installing at build time with `HOME=/opt/claude-home` and resolving via PATH puts the CLI onto the same "update = rebuild" contract (this section) as herdr / runtime. `DISABLE_AUTOUPDATER=1` also stops self-update at boot.
- Image tag convention: `<repo-ref>-r<runtime-version>` (arch is carried by the multi-arch manifest and not included in the tag; only single-arch builds append `-<arch>`). Example: `ghcr.io/suisya-systems/claude-org-ja:v2026.07.17-r0.1.36`. The same content is stamped into OCI LABELs (`org.claude-org.repo-ref` / `org.claude-org.runtime-version`).
- When the in-container `check_runtime_version.py` drift detection (org-start Block C2) returns exit 2/3, the guidance wording is reinterpreted from "pip upgrade" to "**rebuild / pull a newer image tag**" (PyPI reachability cannot be expected inside the container. This reinterpretation is documented in the README; amending the skill prose is a follow-up item).

### 7.8 Blocker 4 and Nits are handled in §8 (UID/GID), per-file comments, and [`docker/README.md`](../../docker/README.md)

Where the Nit fixes live: volume names = purpose-suffixed (§6 table). tini = §5 table stage 1 + explicit `ENTRYPOINT ["tini","--"]` in the Dockerfile. README top-of-file checklist = identical to §3.

## 8. Blocker 4: UID/GID and volume ownership

- The image creates a **fixed app user `org` (UID/GID from build ARGs `ORG_UID`/`ORG_GID`, default 1000:1000)**. The image USER stays root (needed for the entrypoint's one-time chown), and the primary `docker exec` path `org-shell` self-demotes via `gosu org` at its start, so **the human's interactive surface always runs as org** (the README notes that a raw `docker exec` can obtain a root shell; normal operation uses nothing but org-shell).
- Only the entrypoint starts as root and performs **one-time ownership repair**: for each volume mount point (`/home/org`, `.state`, `/workspace/workers`), if the marker file `.org-owned` is absent, `chown -R org:org` and place the marker (recursive chown every boot would slow startup once state.db grows, hence one-time). It then demotes via `gosu org` and starts all subsequent processes as org.
- For users of host bind mounts, the README documents the path of matching the host UID at build time with `--build-arg ORG_UID=$(id -u)` (unnecessary with named volumes).
- **Zero** processes stay resident as root (only tini and the waiting entrypoint shell are root; broker / tmux / herdr / dashboard / Claude Code all run as org).

## 9. Terminal backends: both tmux and herdr

- The backend switches **only via the `--backend` flag at daemon start** (the runtime has no dynamic env-based switching). In the container the entrypoint reads `ORG_BACKEND` (`tmux` | `herdr`, **default `tmux`**) and passes it to the daemon start arguments. Switching is operated as "change the compose environment variable and `docker compose up -d --force-recreate`" = rebuilding the daemon (the runtime rejects a `--backend` mismatch with an existing daemon, so re-creation is the correct path).
- **herdr is officially supported and bundled**. false-reap (runtime #114) was fixed in runtime 0.1.33, and 0.1.36 completed the surrounding pieces (pane id / venv inheritance), so the original premise "experimental until fixed" has **expired** (§2-6).
- **Rationale for still defaulting the container to tmux** (not false-reap): (a) herdr's headless operation (no TUI client attached) generates startup workspaces differently from TUI-attached operation, and the path "pure headless in container → later `docker exec` TUI attach" has not been measured (§12 verification item H1). (b) tmux is stably supplied by apt on all arches and has the longest real org runtime. herdr can be opted into with the single variable `ORG_BACKEND=herdr`.
- The herdr binary is fetched at build time **from a pinned GitHub release URL and verified against measured sha256 values baked into the repository** before bundling ([`docker/install-herdr.sh`](../../docker/install-herdr.sh); default pin: v0.7.4, both amd64/arm64 sha256 measured 2026-07-17). The update manifest (https://herdr.dev/latest.json) was measured to return only URL strings in `assets["linux-<arch>"]` and provides no checksums, so the pin approach is adopted instead of manifest tracking. Self-update (`herdr update`) violates image immutability and is not used; updates happen via pin update + image rebuild (same operation as §7.7). A no-herdr build is possible with `INSTALL_HERDR=0`.

## 10. First-boot path (authentication handbook)

The image ships with zero credentials; a human completes the following exactly once at first boot (everything persists in the `org_home` volume, and no re-authentication is needed across subsequent container re-creations):

1. `docker compose up -d` — the infra (daemon / dashboard) comes up.
2. `docker exec -it claude-org org-shell --setup` — first-boot setup mode. In order:
   - Run `claude` once → `/login` (Claude OAuth. `~/.claude/.credentials.json` + `~/.claude.json` are generated into the volume)
   - `gh auth login` (`~/.config/gh/`)
   - `codex login` (optional. `~/.codex/`. Skippable when not operating the Codex gate)
   - Connect Slack / Google MCP (optional. Claude Code credential store / `~/.config/gogcli/`)
   - `python tools/org_setup_prune.py --all --claude-org-path /workspace/claude-org-ja` + `--user-common-sandbox` to generate the per-role settings (the actual files land at the §6.1 symlink targets. `--claude-org-path` must be explicit because in a fresh container the dispatcher role's `{claude_org_path}` cannot be inferred and fails — confirmed by the 2026-07-17 B3 measurement)
3. `docker exec -it claude-org org-shell` — normal path. Inside the tmux session, `org up` reuses the healthy daemon and starts the secretary TUI → `/org-start`.

## 11. Multi-arch build (linux/amd64 + linux/arm64)

- `docker buildx build --platform linux/amd64,linux/arm64` is the correct path. Multi-arch artifacts cannot be loaded into the local daemon, so `--push` is assumed (local PoC builds single-arch with `--load`).
- Arch-dependent items and their sources: Claude Code native installer (supports arm64 Linux), gh (official apt repo, multi-arch), tmux / python3 / tini / gosu / socat (debian multi-arch), herdr (per-arch assets from the manifest, §9), runtime venv (pure Python, no wheel differences).
- For CI, avoid QEMU emulation slowness (several times to 10x+) and prefer an arm64 native runner + manifest merge (design only, out of scope).
- **Pi 5 16KB page size**: Rust binaries (herdr, the ripgrep bundled with Claude Code) can crash on the 16KB kernel — a known issue — so the README troubleshooting documents switching to `kernel=kernel8.img` (4KB), tracked as §12 verification item A1.
- **Default parallelism for Pi 5**: `ORG_MAX_WORKERS` (default **3**). A conservative value back-calculated from 16GB: measured several-hundred-MB-to-1GB per Claude Code session + the resident secretary/dispatcher share. The entrypoint rewrites `max_concurrent_workers` in `registry/org-config.md` with the env value at boot (a PoC stopgap; the root fix is an env-override mechanism for the config on the runtime / repo side, a follow-up item).

## 12. PoC scope and verification checklist

The PoC ([`docker/`](../../docker/)) goes as far as "a skeleton that can be built and boot-checked locally". Steps that require authentication are substituted by the §10 handbook.

**Included in the PoC**: Dockerfile (secret-scan stage + runtime stage, multi-arch-ready description) / compose.yaml / entrypoint.sh / org-shell.sh / install-herdr.sh / Dockerfile.dockerignore / compose.docker-optin.yaml / README.md.

**Verification checklist** (the definition of image completion; includes items not yet run at PoC time):

| # | Item | PoC status |
|---|---|---|
| B1 | `docker build` (amd64 alone) passes, and the secret-scan stage fails when forbidden paths are mixed in | **Done** (measured 2026-07-17: the scan correctly failed on a test fixture's dummy token → build succeeded after exclusion adjustment. Bundling confirmed: herdr 0.7.4 / Claude Code 2.1.204 / runtime 0.1.36) |
| B2 | `docker compose up -d` brings up daemon + dashboard, and after `docker restart` the §7.1 reconcile sweeps leftovers | **Done** (measured 2026-07-17: chown → reconcile → state.db rebuild → broker daemon (tmux backend) listening; dashboard reachable from host loopback via socat; reconcile re-fired after restart, daemon.json regenerated; all resident processes run as the org user) |
| B3 | The first-boot path (§10) works as written, and no re-authentication after container re-creation | **Done** (measured 2026-07-17 / Claude Code 2.1.204, gh 2.96.0, runtime 0.1.36. With auth absent, `org-shell up` fail-fasts with guidance → following the 6 `--setup` guide steps, `claude /login` + `gh auth login` (codex skipped, not bundled in the image) generated `~/.claude/.credentials.json` + `~/.claude.json` + `~/.config/gh/` into the org_home volume. `org_setup_prune.py --all` fails in a fresh container because the dispatcher role's `{claude_org_path}` cannot be inferred, so `--claude-org-path /workspace/claude-org-ja` is passed explicitly (step 5 of `docker/org-shell.sh` fixed accordingly) → the 3 role-configs are materialized into `role-config/` in the org_state volume and the repo resolves them via symlinks. After a **full re-creation** — `docker compose down` (volumes kept) → `up -d` — the auth files survive byte-identical with the same inodes, **no re-authentication**, gh login retained, role-config symlinks re-created. Host port 8099 in use (host org dashboard running alongside) was avoided via the `ORG_DASHBOARD_HOST_PORT` remap, as designed) |
| B4 | Full cycle: `/org-start` → dispatcher spawn → worker dispatch → completion report | **Done** (measured 2026-07-17 / broker tmux backend. In-container secretary TUI (org up) → `/org-start`: transport=broker decision, MCP connectivity, identity verification → dispatcher pane spawn (id=%0; peer registration, folder-trust + dev-channel auto-approval, identity written to state.db), dashboard, queue watcher started. `/org-delegate` dispatched a tiny task to a Pattern C ephemeral worker → dispatcher spawned the worker pane (id=%1) → the worker received the brief via the push channel (org-broker-channel) → created `b4-verify.txt`, committed (a67b132) → completion report → secretary ack → REVIEW transition, events recorded → completion-received notice to the dispatcher; the whole message flow confirmed in the measured queue.jsonl. Only the runtime drift detection was PyPI-unverified due to packaging not bundled = exactly the §7.7 "rebuild" expectation) |
| S1–S6 | Sandbox verification matrix (§7.5) | Not run |
| H1 | herdr headless boot → TUI attach path from `docker exec` | Not run |
| H2 | herdr distribution path confirmation (manifest schema, arm64 asset existence, sha256 measurement) | **Done** (the manifest provides no checksums → pin approach finalized, §9) |
| A1 | Boot on real Pi 5 (both 16KB / 4KB kernels) | Not run |
| A2 | buildx `--platform linux/arm64` build (QEMU) succeeds | Not run |

## 13. Open items (follow-up)

1. Env-override mechanism for `registry/org-config.md` (root fix for the §11 sed stopgap).
2. Making the dashboard bind address configurable, or authenticated exposure (§7.4 works around it with socat + loopback-only).
3. Creating and distributing a custom seccomp profile (narrower than unconfined; allows only unshare/clone) (§7.5).
4. Container-context support for `check_runtime_version.py` / org-start skill prose (the "rebuild" wording, §7.7).
5. Real-version verification of whether `CLAUDE_CONFIG_DIR` can remove the HOME-direct dependency of `~/.claude.json` (if it holds, the §6 volume granularity can be split further into auth / settings).
6. Automatic multi-arch build / publish in CI (arm64 native runner, §11).
