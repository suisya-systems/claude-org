"""Tests for sync_classifier (Issue #189 P1)."""

from __future__ import annotations

import pytest

from sync_classifier import (
    CLASS_DIVERGENCE,
    CLASS_RUNTIME,
    CLASS_TRANSLATION,
    CLASS_UNKNOWN,
    classify_path,
    classify_paths,
    summarize,
)


@pytest.mark.parametrize(
    "path",
    [
        "tools/dispatcher_runner.py",
        "tools/sub/helper.py",
        "tools/role_configs_schema.json",
        "tools/test_check_renga_compat.py",
        "tools/migrations/2026-05-runtime.sh",
        "tools/data/fixtures/sample.yaml",
        "dashboard/app.js",
        "dashboard/server.py",
        "dashboard/index.html",
        ".claude/settings.json",
        ".claude/hooks/pre-tool-use.sh",
        ".claude/hooks/nested/dir/script.py",
        "tests/integration/test_flow.py",
        "tests/unit.py",
    ],
)
def test_runtime_paths(path: str) -> None:
    assert classify_path(path) == CLASS_RUNTIME


@pytest.mark.parametrize(
    "path",
    [
        ".claude/skills/org-curate/SKILL.md",
        ".claude/skills/foo/bar.md",
        "docs/glossary.md",
        "docs/runbook/auto-mirror-runtime.md",
        "README.md",
        "CLAUDE.md",
    ],
)
def test_translation_paths(path: str) -> None:
    assert classify_path(path) == CLASS_TRANSLATION


@pytest.mark.parametrize(
    "path",
    [
        "knowledge/curated/2026-04-29-foo.md",
        "knowledge/curated/sub/topic.md",
        "registry/projects.md",
        ".state/org-state.md",
        ".curator/queue.md",
        ".dispatcher/log.md",
    ],
)
def test_divergence_paths(path: str) -> None:
    assert classify_path(path) == CLASS_DIVERGENCE


@pytest.mark.parametrize(
    "path",
    [
        "Makefile",
        "scripts/build.sh",
        "random/file.txt",
        "tools-not-tools/foo.py",  # not under tools/
        "knowledge/raw/2026-05-01-note.md",  # raw not curated
    ],
)
def test_unknown_paths(path: str) -> None:
    assert classify_path(path) == CLASS_UNKNOWN


def test_classify_paths_batch() -> None:
    result = classify_paths(
        [
            "tools/foo.py",
            "docs/glossary.md",
            ".state/x.md",
            "Makefile",
        ]
    )
    assert result == {
        "tools/foo.py": CLASS_RUNTIME,
        "docs/glossary.md": CLASS_TRANSLATION,
        ".state/x.md": CLASS_DIVERGENCE,
        "Makefile": CLASS_UNKNOWN,
    }


def test_summarize_groups_by_class() -> None:
    out = summarize(
        {
            "tools/a.py": CLASS_RUNTIME,
            "tools/b.py": CLASS_RUNTIME,
            "Makefile": CLASS_UNKNOWN,
        }
    )
    assert out[CLASS_RUNTIME] == ["tools/a.py", "tools/b.py"]
    assert out[CLASS_UNKNOWN] == ["Makefile"]
    assert out[CLASS_TRANSLATION] == []
    assert out[CLASS_DIVERGENCE] == []


def test_normalize_handles_backslashes_and_dot_slash() -> None:
    assert classify_path("./tools/foo.py") == CLASS_RUNTIME
    assert classify_path("tools\\foo.py") == CLASS_RUNTIME
