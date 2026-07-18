"""Tests for restore_en_clone_url (Issue #523).

Uses stdlib unittest so the existing `tests.yml` CI
(`python -m unittest discover -s tools -p 'test_*.py'`) picks it up
without adding new test-runner dependencies.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from restore_en_clone_url import (
    DEFAULT_TARGETS,
    EN_CLONE_URL,
    RestoreError,
    kind_for_path,
    main,
    restore_file,
    restore_text,
)

JA_CLONE_URL = "https://github.com/suisya-systems/claude-org-ja.git"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SH_SAMPLE = f"""#!/usr/bin/env bash
# One-liner installer for claude-org-ja (Linux / macOS).
#
#   curl -fsSL https://raw.githubusercontent.com/suisya-systems/claude-org-ja/main/scripts/install.sh | bash
set -euo pipefail

REPO_URL="{JA_CLONE_URL}"
TARGET_DIR="claude-org-ja"
"""

PS1_SAMPLE = f"""# One-liner installer for claude-org-ja (Windows / PowerShell 7+).
#
#   iwr -useb https://raw.githubusercontent.com/suisya-systems/claude-org-ja/main/scripts/install.ps1 | iex

$RepoUrl = '{JA_CLONE_URL}'
$dir = 'claude-org-ja'
"""


class KindForPathTests(unittest.TestCase):
    def test_extensions(self) -> None:
        self.assertEqual(kind_for_path("scripts/install.sh"), "sh")
        self.assertEqual(kind_for_path("scripts/install.ps1"), "ps1")
        self.assertEqual(kind_for_path("SCRIPTS/INSTALL.PS1"), "ps1")

    def test_unknown_extension_raises(self) -> None:
        with self.assertRaises(RestoreError):
            kind_for_path("scripts/install.bat")


class RestoreTextTests(unittest.TestCase):
    def test_sh_ja_url_is_restored(self) -> None:
        new_text, matched = restore_text(SH_SAMPLE, "sh")
        self.assertEqual(matched, 1)
        self.assertIn(f'REPO_URL="{EN_CLONE_URL}"', new_text)
        self.assertNotIn(f'REPO_URL="{JA_CLONE_URL}"', new_text)

    def test_ps1_ja_url_is_restored(self) -> None:
        new_text, matched = restore_text(PS1_SAMPLE, "ps1")
        self.assertEqual(matched, 1)
        self.assertIn(f"$RepoUrl = '{EN_CLONE_URL}'", new_text)
        self.assertNotIn(f"$RepoUrl = '{JA_CLONE_URL}'", new_text)

    def test_only_assignment_line_is_touched(self) -> None:
        """Minimal-adaptation policy: banner / comments / TARGET_DIR stay ja."""
        new_text, _ = restore_text(SH_SAMPLE, "sh")
        self.assertIn(
            "raw.githubusercontent.com/suisya-systems/claude-org-ja/main", new_text
        )
        self.assertIn('TARGET_DIR="claude-org-ja"', new_text)
        self.assertIn("installer for claude-org-ja", new_text)

        new_text, _ = restore_text(PS1_SAMPLE, "ps1")
        self.assertIn(
            "raw.githubusercontent.com/suisya-systems/claude-org-ja/main", new_text
        )
        self.assertIn("$dir = 'claude-org-ja'", new_text)

    def test_en_url_is_unchanged(self) -> None:
        already_en = SH_SAMPLE.replace(JA_CLONE_URL, EN_CLONE_URL)
        new_text, matched = restore_text(already_en, "sh")
        self.assertEqual(matched, 1)
        self.assertEqual(new_text, already_en)

    def test_any_other_url_is_normalized_to_en(self) -> None:
        """EN's clone target is EN-canonical no matter what ja moves to."""
        moved = SH_SAMPLE.replace(
            JA_CLONE_URL, "https://github.com/elsewhere/claude-org-ja.git"
        )
        new_text, matched = restore_text(moved, "sh")
        self.assertEqual(matched, 1)
        self.assertIn(f'REPO_URL="{EN_CLONE_URL}"', new_text)

    def test_no_assignment_returns_zero_matches(self) -> None:
        new_text, matched = restore_text("echo no assignment here\n", "sh")
        self.assertEqual(matched, 0)
        self.assertEqual(new_text, "echo no assignment here\n")

    def test_indented_lookalike_is_not_an_assignment(self) -> None:
        text = f'  REPO_URL="{JA_CLONE_URL}"\n'
        _, matched = restore_text(text, "sh")
        self.assertEqual(matched, 0)

    def test_crlf_line_endings_are_preserved(self) -> None:
        crlf = PS1_SAMPLE.replace("\n", "\r\n")
        new_text, matched = restore_text(crlf, "ps1")
        self.assertEqual(matched, 1)
        self.assertIn(f"$RepoUrl = '{EN_CLONE_URL}'\r\n", new_text)
        self.assertNotIn(
            "\n$RepoUrl", new_text.replace("\r\n", "|")
        )  # no bare-LF lines introduced


class RealRepoFileTests(unittest.TestCase):
    """Bind the patterns to the actual installer scripts in this repo.

    If either script's assignment line drifts to a shape the pattern no
    longer recognizes, this fails locally / in tests.yml before the
    mirror workflow can silently stop restoring.
    """

    def _read(self, rel: str) -> str:
        with open(os.path.join(REPO_ROOT, rel), encoding="utf-8", newline="") as f:
            return f.read()

    def test_default_targets_match_and_are_already_en(self) -> None:
        for rel in DEFAULT_TARGETS:
            with self.subTest(path=rel):
                text = self._read(rel)
                new_text, matched = restore_text(text, kind_for_path(rel))
                self.assertEqual(matched, 1)
                self.assertEqual(new_text, text)

    def test_simulated_mirror_copy_round_trips(self) -> None:
        """ja-URL clobber (what the mirror copy does) restores to HEAD."""
        for rel in DEFAULT_TARGETS:
            with self.subTest(path=rel):
                text = self._read(rel)
                clobbered = text.replace(EN_CLONE_URL, JA_CLONE_URL)
                self.assertNotEqual(clobbered, text)
                new_text, matched = restore_text(clobbered, kind_for_path(rel))
                self.assertEqual(matched, 1)
                # Only the assignment line comes back; other ja-URL
                # occurrences (if any) stay clobbered, hence compare the
                # assignment line specifically.
                self.assertIn(EN_CLONE_URL, new_text)
                if rel.endswith(".sh"):
                    self.assertIn(f'REPO_URL="{EN_CLONE_URL}"', new_text)
                else:
                    self.assertIn(f"$RepoUrl = '{EN_CLONE_URL}'", new_text)


class RestoreFileAndCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name: str, content: str) -> str:
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return path

    def _read(self, path: str) -> str:
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()

    def test_restore_file_rewrites_and_reports_change(self) -> None:
        path = self._write("install.sh", SH_SAMPLE)
        self.assertTrue(restore_file(path))
        self.assertIn(f'REPO_URL="{EN_CLONE_URL}"', self._read(path))
        # Second run is a no-op (idempotent).
        self.assertFalse(restore_file(path))

    def test_restore_file_missing_file_raises(self) -> None:
        with self.assertRaises(RestoreError):
            restore_file(os.path.join(self.tmp.name, "absent.sh"))

    def test_restore_file_without_assignment_raises(self) -> None:
        path = self._write("install.sh", "echo hello\n")
        with self.assertRaises(RestoreError):
            restore_file(path)

    def test_main_success_exit_code(self) -> None:
        sh = self._write("install.sh", SH_SAMPLE)
        ps1 = self._write("install.ps1", PS1_SAMPLE)
        self.assertEqual(main([sh, ps1]), 0)
        self.assertIn(EN_CLONE_URL, self._read(sh))
        self.assertIn(EN_CLONE_URL, self._read(ps1))

    def test_main_error_exit_code_and_keeps_processing(self) -> None:
        bad = os.path.join(self.tmp.name, "absent.sh")
        good = self._write("install.sh", SH_SAMPLE)
        self.assertEqual(main([bad, good]), 2)
        # The good file is still restored even though an earlier one failed.
        self.assertIn(EN_CLONE_URL, self._read(good))


if __name__ == "__main__":
    unittest.main()
