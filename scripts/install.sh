#!/usr/bin/env bash
# One-liner installer for claude-org (Linux / macOS).
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/suisya-systems/claude-org/main/scripts/install.sh | bash
#   bash scripts/install.sh [--dir <path>] [--dry-run] [--skip-mcp]
#
# This script:
#   1. Checks for required commands (git, claude, renga, gh) and prints
#      installation hints when something is missing.
#   2. Clones suisya-systems/claude-org (asks before reusing an
#      existing directory).
#   3. Runs `renga mcp install` (user-scope) so the renga-peers MCP
#      server is registered with Claude Code.
#   4. Prints next steps.
#
# It never auto-installs missing tools and never bypasses Claude Code's
# permission prompts.
set -euo pipefail

REPO_URL="https://github.com/suisya-systems/claude-org.git"
TARGET_DIR="claude-org"
DRY_RUN=0
SKIP_MCP=0
# CLAUDE_ORG_REF pins the clone to a specific branch or tag for
# reproducibility. Default `main` keeps the latest-features behaviour
# unchanged for users who do not set it.
REF="${CLAUDE_ORG_REF:-main}"

usage() {
  cat <<'USAGE'
Usage: install.sh [--dir <path>] [--dry-run] [--skip-mcp] [--help]

Options:
  --dir <path>   Target directory for the clone (default: ./claude-org).
  --dry-run      Print the commands that would run without executing them.
  --skip-mcp     Skip `renga mcp install` (use when already registered).
  -h, --help     Show this help and exit.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      [[ $# -ge 2 ]] || { echo "install.sh: --dir requires an argument" >&2; exit 2; }
      TARGET_DIR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --skip-mcp) SKIP_MCP=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "install.sh: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# Detect interactive input. When piped from curl, stdin is the pipe; the
# only reliable prompt path is /dev/tty, and only if it can actually be
# opened for both read and write. Probe once and cache the result so
# `set -e` doesn't kill the script on a failed write later.
HAS_TTY=0
if [[ -t 0 ]]; then
  HAS_TTY=1
elif { : > /dev/tty; } 2>/dev/null && { : < /dev/tty; } 2>/dev/null; then
  HAS_TTY=1
fi

prompt_yes_no() {
  # $1 = prompt, $2 = default (Y or N). Returns 0 for yes, 1 for no.
  local prompt="$1" default="$2" reply=""
  local hint
  if [[ "$default" == "Y" ]]; then hint="[Y/n]"; else hint="[y/N]"; fi
  if [[ "$HAS_TTY" != "1" ]]; then
    echo "install.sh: non-interactive shell; assuming '$default' for: $prompt" >&2
    [[ "$default" == "Y" ]] && return 0 || return 1
  fi
  if [[ -t 0 ]]; then
    read -r -p "$prompt $hint " reply || reply=""
  else
    # Use /dev/tty for both prompt and response. Guard with `|| true` so
    # `set -e` doesn't terminate on a transient write failure.
    printf "%s %s " "$prompt" "$hint" > /dev/tty 2>/dev/null || true
    read -r reply < /dev/tty || reply=""
  fi
  reply="${reply:-$default}"
  case "$reply" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

run() {
  # Echo + execute, or just echo when --dry-run is set.
  echo "+ $*"
  if [[ "$DRY_RUN" != "1" ]]; then
    "$@"
  fi
}

# Detect a Windows-style POSIX shell (Git Bash / MSYS2 / Cygwin). WSL
# reports OSTYPE=linux-gnu and is intentionally excluded — there the
# Linux PATH conventions apply, so the extra fallbacks would just slow
# things down without fixing anything.
#
# OSTYPE is the cheap probe; `uname -s` is a fallback for shells that
# don't export OSTYPE (some minimal POSIX shims). Either matching is
# enough.
IS_WINDOWS_SHELL=0
case "${OSTYPE:-}" in
  msys*|cygwin*|win32*) IS_WINDOWS_SHELL=1 ;;
esac
if [[ "$IS_WINDOWS_SHELL" != "1" ]] && command -v uname >/dev/null 2>&1; then
  case "$(uname -s 2>/dev/null || true)" in
    MINGW*|MSYS*|CYGWIN*) IS_WINDOWS_SHELL=1 ;;
  esac
fi

resolve_command() {
  # Echoes the resolved path of a command, or returns non-zero when not
  # found. On Git Bash / MSYS, `command -v claude` does NOT auto-append
  # PATHEXT (`.exe` / `.cmd` / `.bat`) the way the exec layer does at
  # actual invocation time, so a tool installed as `claude.cmd` shows
  # up as missing here even though `claude foo` would have worked.
  # That trips the prerequisite gate for users who run
  # `curl ... | bash` from PowerShell, where claude / renga are
  # installed via npm or cargo and end up at `<name>.cmd` /
  # `<name>.exe` rather than as bare-name shims.
  #
  # The fallback ladder mirrors install.ps1's `py -3` candidate-list
  # philosophy: try the cheap thing first, then explicit extensions,
  # then a small set of common Windows install locations under $HOME.
  local cmd="$1" found="" ext cand
  if found=$(command -v "$cmd" 2>/dev/null); then
    printf '%s\n' "$found"
    return 0
  fi
  if [[ "$IS_WINDOWS_SHELL" != "1" ]]; then
    return 1
  fi
  for ext in .exe .cmd .bat; do
    if found=$(command -v "${cmd}${ext}" 2>/dev/null); then
      printf '%s\n' "$found"
      return 0
    fi
  done
  # Common Windows install locations that aren't always on PATH when
  # bash is launched from PowerShell. Order: language-package managers
  # (npm / cargo) first, since claude / renga ship through them; then
  # POSIX-style $HOME bin dirs; then scoop shims for users on that
  # package manager.
  for cand in \
    "$HOME/AppData/Roaming/npm/${cmd}.cmd" \
    "$HOME/AppData/Roaming/npm/${cmd}.exe" \
    "$HOME/AppData/Roaming/npm/${cmd}" \
    "$HOME/.cargo/bin/${cmd}.exe" \
    "$HOME/.cargo/bin/${cmd}" \
    "$HOME/.local/bin/${cmd}.exe" \
    "$HOME/.local/bin/${cmd}" \
    "$HOME/AppData/Local/Programs/${cmd}/${cmd}.exe" \
    "$HOME/scoop/shims/${cmd}.exe" \
    "$HOME/scoop/shims/${cmd}.cmd"; do
    # Use -f, not -x: npm-installed `.cmd` shims on Windows ship
    # without the POSIX execute bit (they're invoked by cmd.exe, not
    # by /bin/sh), but Windows can still launch them and Git Bash
    # forwards the call. -f keeps `.exe` and bare POSIX shims working
    # too.
    if [[ -f "$cand" ]]; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  return 1
}

require_or_warn() {
  # $1 = command name, $2 = install hint URL/text.
  local cmd="$1" hint="$2" path dir
  if path=$(resolve_command "$cmd"); then
    echo "  [ok]   $cmd: $path"
    # When resolve_command found the tool via a Windows-only fallback,
    # its parent dir may not be on PATH yet. Prepend it so later steps
    # that invoke the tool through PATH (`.exe` invocations, bare
    # POSIX shims) keep working. NOTE: this is NOT enough on its own
    # for `.cmd` / `.bat` shims — Git Bash / MSYS bash's exec layer
    # auto-appends `.exe` for bare-name invocations but does NOT try
    # `.cmd` / `.bat`. So tools resolved as `<name>.cmd` (renga is the
    # canonical case — `npm install -g @suisya-systems/renga` lays
    # down `renga.cmd`) must be invoked via the absolute path captured
    # by the caller. See RENGA_BIN below.
    dir=$(dirname "$path")
    case ":$PATH:" in
      *":$dir:"*) ;;
      *) PATH="$dir:$PATH" ;;
    esac
    return 0
  fi
  echo "  [miss] $cmd not found. Install hint: $hint"
  if [[ "$IS_WINDOWS_SHELL" == "1" ]]; then
    echo "         (Probed .exe/.cmd/.bat on PATH and common install dirs"
    echo "          under \$HOME — npm / cargo / scoop / .local. None matched.)"
  fi
  return 1
}

echo "== claude-org installer =="
echo

echo "Checking prerequisites..."
missing=0
require_or_warn git    "https://git-scm.com/downloads" || missing=1
require_or_warn claude "https://claude.ai/code (Claude Code CLI)" || missing=1
require_or_warn renga  "npm install -g @suisya-systems/renga@0.18.0" || missing=1
require_or_warn gh     "https://cli.github.com/" || missing=1
echo

# Capture renga's absolute path for the later `renga mcp install` step.
# Git Bash / MSYS bash auto-appends `.exe` on bare-name invocations
# but not `.cmd` / `.bat`, and `npm install -g @suisya-systems/renga`
# lays down `renga.cmd` on Windows — so a bare `run renga mcp install`
# would exit 127 (command not found) for npm-installed users even
# though require_or_warn just printed [ok] for it. Prefer the
# explicit absolute path on Windows; fall back to the bare name (so
# POSIX users still see the same `+ renga mcp install` echo line they
# always have, and so the dry-run smoke regex stays happy).
RENGA_BIN=""
if [[ "$IS_WINDOWS_SHELL" == "1" ]]; then
  RENGA_BIN=$(resolve_command renga 2>/dev/null || true)
fi

if [[ "$missing" == "1" ]]; then
  cat <<'MSG' >&2
install.sh: one or more prerequisites are missing.
Install the listed tools, then re-run this installer.
(This script intentionally does not auto-install dependencies.)
MSG
  exit 1
fi

# --- Clone -----------------------------------------------------------------

if [[ -e "$TARGET_DIR" ]]; then
  # `.git` may be a directory (normal clone) or a file (worktree / submodule).
  if [[ -e "$TARGET_DIR/.git" ]]; then
    # Verify it's actually our repo, not some unrelated git checkout that
    # happens to share the directory name. Without this check, a curl|bash
    # invocation would silently run later steps against the wrong tree.
    existing_url=$(git -C "$TARGET_DIR" remote get-url origin 2>/dev/null || true)
    if [[ "$existing_url" != "$REPO_URL" ]]; then
      echo "install.sh: '$TARGET_DIR' is a git repo, but its 'origin' is:" >&2
      echo "  ${existing_url:-<unset>}" >&2
      echo "  expected: $REPO_URL" >&2
      echo "install.sh: refusing to reuse. Move/rename the directory or pass --dir <other>." >&2
      exit 1
    fi
    echo "install.sh: '$TARGET_DIR' already exists and points at $REPO_URL."
    # Fail-closed in non-interactive mode: the curl|bash flow cannot get a
    # meaningful Y/N answer, so we don't silently fall through to the
    # later steps on a pre-existing checkout.
    if [[ "$HAS_TTY" != "1" ]]; then
      echo "install.sh: non-interactive shell; refusing to reuse without confirmation." >&2
      echo "install.sh: re-run interactively, or move/rename the directory and re-run." >&2
      exit 1
    fi
    if prompt_yes_no "Skip clone and reuse existing directory?" "Y"; then
      echo "Reusing existing $TARGET_DIR (no clone)."
    else
      echo "install.sh: aborting so you can move or rename '$TARGET_DIR' first." >&2
      exit 1
    fi
  else
    echo "install.sh: '$TARGET_DIR' exists but is not a git repository." >&2
    echo "install.sh: refusing to overwrite. Move or rename it and re-run." >&2
    exit 1
  fi
else
  # `git clone --branch` accepts either a branch or a tag; an unknown ref
  # exits non-zero with "Remote branch <ref> not found", which `set -e`
  # propagates. Wrap it so the user sees a friendlier abort message
  # naming the ref they asked for.
  if [[ "$DRY_RUN" != "1" ]]; then
    echo "+ git clone --branch $REF $REPO_URL $TARGET_DIR"
    if ! git clone --branch "$REF" "$REPO_URL" "$TARGET_DIR"; then
      echo "install.sh: failed to clone ref '$REF' from $REPO_URL." >&2
      echo "install.sh: check that CLAUDE_ORG_REF names an existing branch or tag." >&2
      echo "install.sh: branches and tags are accepted; see https://github.com/suisya-systems/claude-org/releases for stable tags." >&2
      exit 1
    fi
  else
    echo "+ git clone --branch $REF $REPO_URL $TARGET_DIR"
  fi
fi

# --- renga mcp install -----------------------------------------------------

if [[ "$SKIP_MCP" == "1" ]]; then
  echo "Skipping 'renga mcp install' (--skip-mcp)."
else
  echo
  echo "Registering renga-peers MCP with Claude Code (user-scope)..."
  echo "Note: Claude Code may show a permission prompt; approve it to continue."
  run "${RENGA_BIN:-renga}" mcp install
fi

# --- Python deps (core-harness pin) ----------------------------------------

# Step B (Issue #128) made tools/check_role_configs.py and
# tools/generate_worker_settings.py thin shims over the core-harness
# package; Phase 4 (Issue #129) then moved the dispatcher runner and
# the worker settings generator out of tools/ into the
# claude-org-runtime package. Phase 5c (Issue #130) moved the install
# path from `requirements.txt` to `pyproject.toml`; we prefer the
# editable install so the dep set comes from the canonical source.
# PY is a single-token interpreter command for POSIX (`python3` or
# `python`). On Git Bash / MSYS, neither name is on PATH by default;
# only the `py.exe` launcher is present. Git Bash users have hit this
# enough times that the install.ps1 sibling already has a `py -3`
# candidate for it. Mirror that here so `bash <(curl ...)` from
# PowerShell doesn't dead-end the Python deps step on stock Windows.
#
# PY_LAUNCHER carries the optional `-3` flag so the call site can pin
# the launcher to a Python 3 interpreter without hard-coding a major
# version into every invocation. It is empty for the POSIX-friendly
# names so they continue to invoke as `python3 -m pip ...`.
PY=""
PY_LAUNCHER=""
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
elif [[ "$IS_WINDOWS_SHELL" == "1" ]] && command -v py >/dev/null 2>&1; then
  # Probe with --version so we don't accidentally pick up a launcher
  # whose configured Python 3 is broken or removed; same defensive
  # check install.ps1 does for the Microsoft Store stub.
  if py -3 --version >/dev/null 2>&1; then
    PY=py
    PY_LAUNCHER="-3"
  fi
fi
PYPROJECT_FILE="$TARGET_DIR/pyproject.toml"
REQ_FILE="$TARGET_DIR/requirements.txt"
if [[ -f "$PYPROJECT_FILE" && -n "$PY" ]]; then
  echo
  echo "Installing Python deps via pyproject.toml (editable) ..."
  run $PY $PY_LAUNCHER -m pip install --user -e "$TARGET_DIR"
elif [[ -f "$REQ_FILE" && -n "$PY" ]]; then
  # Backward-compat path for refs that predate Phase 5c (no
  # pyproject.toml) but post-date Step B (have requirements.txt).
  echo
  echo "Installing Python deps (core-harness pin, requirements.txt) ..."
  run $PY $PY_LAUNCHER -m pip install --user -r "$REQ_FILE"
elif [[ ! -f "$PYPROJECT_FILE" && ! -f "$REQ_FILE" ]]; then
  # Older refs / fixtures predate Step B and ship neither file.
  # The shim CLIs only exist on Step-B-or-later commits, so skipping
  # here keeps the installer backward compatible.
  echo "Skipping Python deps (no pyproject.toml or requirements.txt)."
else
  echo "WARN: python not found; tools/check_role_configs.py will fail until you 'pip install -e .'."
fi

# --- Done ------------------------------------------------------------------

cat <<MSG

Done. Next steps:

  cd $TARGET_DIR
  bash scripts/install-hooks.sh   # enable pre-commit secret scanner
  renga --layout ops              # launch the Secretary pane

Inside the Secretary's Claude Code pane, run:

  /org-setup    # first time only: place per-role permissions and hooks
  /org-start    # bring dispatcher + curator online

For details see docs/getting-started.md.
MSG
