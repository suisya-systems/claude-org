"""Restore the EN-canonical installer clone URL after an auto-mirror copy.

Issue #523: scripts/install.sh and scripts/install.ps1 are runtime-class,
so the ja->en auto-mirror copies them verbatim from ja at the merge SHA.
Their clone-URL assignment, however, is EN-owned: ja points the installer
at claude-org-ja.git while EN smoke (install-scripts.yml) asserts
claude-org.git, so every ja PR touching those lines turned EN smoke
deterministically red (established pattern: EN #506 -> #511).

Called by .github/workflows/auto-mirror-runtime.yml as a post-copy step.
Rewrites ONLY the clone-URL assignment lines back to the EN-canonical URL,
per the established minimal-adaptation policy: clone URL only;
banner / comments / TARGET_DIR stay ja.

Usage:
    python tools/restore_en_clone_url.py [path ...]

With no arguments, processes DEFAULT_TARGETS relative to the current
working directory. Exits 0 when every file was handled (whether or not a
rewrite was needed); exits 2 when a file is missing, has no recognizable
clone-URL assignment line, or has an extension the tool does not know.
The no-assignment case is a hard error on purpose: silently skipping
would ship a mirror PR that deterministically fails EN smoke.
"""

from __future__ import annotations

import argparse
import re
import sys

EN_CLONE_URL = "https://github.com/suisya-systems/claude-org.git"

DEFAULT_TARGETS: tuple[str, ...] = (
    "scripts/install.sh",
    "scripts/install.ps1",
)

# One pattern per installer flavor. Group 1 / group 2 bracket the URL so
# the substitution keeps everything else on the line (including a CRLF
# ending) untouched. The URL character class excludes quotes and line
# breaks so a match can never spill across lines.
_PATTERNS: dict[str, re.Pattern[str]] = {
    # REPO_URL="https://..."  (top-level assignment in install.sh)
    "sh": re.compile(r'^(REPO_URL=")[^"\r\n]*(")', re.MULTILINE),
    # $RepoUrl = 'https://...'  (top-level assignment in install.ps1)
    "ps1": re.compile(r"^(\$RepoUrl = ')[^'\r\n]*(')", re.MULTILINE),
}


class RestoreError(Exception):
    """Raised when a target file cannot be safely restored."""


def kind_for_path(path: str) -> str:
    """Map a file path to a pattern kind by extension."""
    lower = path.lower()
    if lower.endswith(".sh"):
        return "sh"
    if lower.endswith(".ps1"):
        return "ps1"
    raise RestoreError(f"unsupported file type (expected .sh or .ps1): {path}")


def restore_text(text: str, kind: str) -> tuple[str, int]:
    """Rewrite clone-URL assignment lines in ``text`` to EN_CLONE_URL.

    Returns ``(new_text, matched)`` where ``matched`` is the number of
    assignment lines found (regardless of whether they needed rewriting).
    Any URL value is normalized to EN_CLONE_URL -- the EN repo's clone
    target is EN-canonical no matter what ja changes theirs to.
    """
    pattern = _PATTERNS[kind]
    new_text, matched = pattern.subn(rf"\g<1>{EN_CLONE_URL}\g<2>", text)
    return new_text, matched


def restore_file(path: str) -> bool:
    """Restore one file in place. Returns True if the file was modified."""
    kind = kind_for_path(path)
    try:
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
    except FileNotFoundError:
        raise RestoreError(f"file not found: {path}") from None
    new_text, matched = restore_text(text, kind)
    if matched == 0:
        raise RestoreError(
            f"no clone-URL assignment line found in {path}; "
            "refusing to continue (the mirror copy would fail EN smoke)"
        )
    if new_text == text:
        return False
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Restore the EN-canonical clone URL in installer scripts "
            "after an auto-mirror copy from ja (Issue #523)."
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=list(DEFAULT_TARGETS),
        help="installer scripts to restore (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    status = 0
    for path in args.paths:
        try:
            changed = restore_file(path)
        except RestoreError as exc:
            print(f"error: {exc}", file=sys.stderr)
            status = 2
            continue
        print(f"{'restored' if changed else 'unchanged'}: {path}")
    return status


if __name__ == "__main__":
    sys.exit(main())
