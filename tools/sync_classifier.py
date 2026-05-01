"""Path classifier for ja->en auto-mirror runtime sync (Issue #189).

Classifies file paths into one of four classes:
- runtime: auto-mirrored from ja main to en main
- translation: handled by translation pipeline (TRANSLATION-PENDING issue)
- divergence-allowed: intentionally divergent per docs/sync-policy.md
- unknown: not matched; requires manual triage
"""

from __future__ import annotations

import fnmatch
from typing import Iterable


RUNTIME_GLOBS: tuple[str, ...] = (
    "tools/*.py",
    "tools/**/*.py",
    "tools/*.json",
    "tools/**/*.json",
    "dashboard/app.js",
    "dashboard/server.py",
    "dashboard/index.html",
    ".claude/settings.json",
    ".claude/hooks/*",
    ".claude/hooks/**/*",
    "tests/*",
    "tests/**/*",
)

TRANSLATION_GLOBS: tuple[str, ...] = (
    ".claude/skills/*",
    ".claude/skills/**/*",
    "docs/*",
    "docs/**/*",
    "README.md",
    "CLAUDE.md",
)

DIVERGENCE_GLOBS: tuple[str, ...] = (
    "knowledge/curated/*",
    "knowledge/curated/**/*",
    "registry/projects.md",
    ".state/*",
    ".state/**/*",
    ".curator/*",
    ".curator/**/*",
    ".dispatcher/*",
    ".dispatcher/**/*",
)


CLASS_RUNTIME = "runtime"
CLASS_TRANSLATION = "translation"
CLASS_DIVERGENCE = "divergence-allowed"
CLASS_UNKNOWN = "unknown"


def _normalize(path: str) -> str:
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _matches_any(path: str, globs: Iterable[str]) -> bool:
    for pat in globs:
        if fnmatch.fnmatchcase(path, pat):
            return True
        # fnmatch ** does not span directories; emulate by stripping the prefix
        if "**" in pat:
            prefix, _, suffix = pat.partition("**")
            prefix = prefix.rstrip("/")
            suffix = suffix.lstrip("/")
            if prefix and not path.startswith(prefix + "/"):
                continue
            tail = path[len(prefix) + 1 :] if prefix else path
            if not suffix:
                return True
            if fnmatch.fnmatchcase(tail, suffix) or fnmatch.fnmatchcase(
                tail, "*/" + suffix
            ):
                return True
            # allow nested directories
            parts = tail.split("/")
            for i in range(len(parts)):
                cand = "/".join(parts[i:])
                if fnmatch.fnmatchcase(cand, suffix):
                    return True
    return False


def classify_path(path: str) -> str:
    """Return the class of a single path.

    Order matters: runtime > divergence-allowed > translation > unknown.
    Runtime wins because some runtime files (e.g., tools/test_*.py) live under
    paths that could otherwise match by extension; explicit runtime globs take
    precedence. Divergence is checked before translation because divergence-
    allowed paths under .state/ etc. should never be queued for translation.
    """
    p = _normalize(path)
    if _matches_any(p, RUNTIME_GLOBS):
        return CLASS_RUNTIME
    if _matches_any(p, DIVERGENCE_GLOBS):
        return CLASS_DIVERGENCE
    if _matches_any(p, TRANSLATION_GLOBS):
        return CLASS_TRANSLATION
    return CLASS_UNKNOWN


def classify_paths(paths: Iterable[str]) -> dict[str, str]:
    """Classify a batch of paths. Returns {path: class}."""
    return {p: classify_path(p) for p in paths}


def summarize(classifications: dict[str, str]) -> dict[str, list[str]]:
    """Group paths by class for reporting."""
    out: dict[str, list[str]] = {
        CLASS_RUNTIME: [],
        CLASS_TRANSLATION: [],
        CLASS_DIVERGENCE: [],
        CLASS_UNKNOWN: [],
    }
    for path, klass in classifications.items():
        out.setdefault(klass, []).append(path)
    for k in out:
        out[k].sort()
    return out


if __name__ == "__main__":
    import json
    import sys

    paths = [line.strip() for line in sys.stdin if line.strip()]
    result = classify_paths(paths)
    json.dump(
        {"by_path": result, "by_class": summarize(result)},
        sys.stdout,
        indent=2,
        sort_keys=True,
    )
    sys.stdout.write("\n")
