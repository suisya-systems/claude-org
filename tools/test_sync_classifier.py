"""Tests for sync_classifier (Issue #189 P1).

Uses stdlib unittest so the existing `tests.yml` CI
(`python -m unittest discover -s tools -p 'test_*.py'`) picks it up
without adding new test-runner dependencies.
"""

from __future__ import annotations

import unittest

from sync_classifier import (
    CLASS_DIVERGENCE,
    CLASS_RUNTIME,
    CLASS_TRANSLATION,
    CLASS_UNKNOWN,
    classify_path,
    classify_paths,
    summarize,
)


RUNTIME_PATHS = [
    "tools/dispatcher_runner.py",
    "tools/sub/helper.py",
    "tools/role_configs_schema.json",
    "tools/test_check_renga_compat.py",
    "tools/migrations/2026-05-runtime.sh",
    "tools/data/fixtures/sample.yaml",
    # Templates dir mechanics (loader scripts / JSON schemas) stay runtime;
    # only the prose .md / .toml templates fall through to translation.
    "tools/templates/loader.py",
    "tools/templates/schema.json",
    "dashboard/app.js",
    "dashboard/server.py",
    "dashboard/index.html",
    "dashboard/org_state_converter.py",
    "dashboard/style.css",
    ".claude/settings.json",
    ".hooks/block-dangerous-git.sh",
    ".hooks/lib/segment-split.sh",
    "tests/integration/test_flow.py",
    "tests/unit.py",
    # Issue #159: documented installer entry points are runtime.
    "scripts/install.sh",
    "scripts/install.ps1",
]

TRANSLATION_PATHS = [
    ".claude/skills/org-curate/SKILL.md",
    ".claude/skills/foo/bar.md",
    "docs/glossary.md",
    "docs/runbook/auto-mirror-runtime.md",
    "README.md",
    "CLAUDE.md",
    # Worker brief templates: prose rendered into Worker prompts. Must reach
    # en harness in English via the translation pipeline.
    "tools/templates/worker_brief_self_edit.md",
    "tools/templates/worker_brief_normal.md",
    "tools/templates/worker_brief.example.toml",
]

DIVERGENCE_PATHS = [
    "knowledge/curated/2026-04-29-foo.md",
    "knowledge/curated/sub/topic.md",
    "registry/projects.md",
    ".state/org-state.md",
    ".curator/queue.md",
    ".dispatcher/log.md",
]

UNKNOWN_PATHS = [
    "Makefile",
    "scripts/build.sh",
    # The install rule is narrow — sibling scripts under scripts/ stay unknown
    # so they get manual triage rather than silently mirroring.
    "scripts/install-hooks.sh",
    "scripts/install.bat",
    "random/file.txt",
    "tools-not-tools/foo.py",
    "knowledge/raw/2026-05-01-note.md",
]


class ClassifyPathTests(unittest.TestCase):
    def test_runtime_paths(self) -> None:
        for p in RUNTIME_PATHS:
            with self.subTest(path=p):
                self.assertEqual(classify_path(p), CLASS_RUNTIME)

    def test_translation_paths(self) -> None:
        for p in TRANSLATION_PATHS:
            with self.subTest(path=p):
                self.assertEqual(classify_path(p), CLASS_TRANSLATION)

    def test_divergence_paths(self) -> None:
        for p in DIVERGENCE_PATHS:
            with self.subTest(path=p):
                self.assertEqual(classify_path(p), CLASS_DIVERGENCE)

    def test_unknown_paths(self) -> None:
        for p in UNKNOWN_PATHS:
            with self.subTest(path=p):
                self.assertEqual(classify_path(p), CLASS_UNKNOWN)

    def test_normalize_handles_backslashes_and_dot_slash(self) -> None:
        self.assertEqual(classify_path("./tools/foo.py"), CLASS_RUNTIME)
        self.assertEqual(classify_path("tools\\foo.py"), CLASS_RUNTIME)


class BatchTests(unittest.TestCase):
    def test_classify_paths_batch(self) -> None:
        result = classify_paths(
            [
                "tools/foo.py",
                "docs/glossary.md",
                ".state/x.md",
                "Makefile",
            ]
        )
        self.assertEqual(
            result,
            {
                "tools/foo.py": CLASS_RUNTIME,
                "docs/glossary.md": CLASS_TRANSLATION,
                ".state/x.md": CLASS_DIVERGENCE,
                "Makefile": CLASS_UNKNOWN,
            },
        )

    def test_summarize_groups_by_class(self) -> None:
        out = summarize(
            {
                "tools/a.py": CLASS_RUNTIME,
                "tools/b.py": CLASS_RUNTIME,
                "Makefile": CLASS_UNKNOWN,
            }
        )
        self.assertEqual(out[CLASS_RUNTIME], ["tools/a.py", "tools/b.py"])
        self.assertEqual(out[CLASS_UNKNOWN], ["Makefile"])
        self.assertEqual(out[CLASS_TRANSLATION], [])
        self.assertEqual(out[CLASS_DIVERGENCE], [])


if __name__ == "__main__":
    unittest.main()
