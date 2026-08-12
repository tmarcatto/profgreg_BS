#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_study_guide_content_check.py"

spec = importlib.util.spec_from_file_location("greg_study_guide_content_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_study_guide_content_check"] = checker
spec.loader.exec_module(checker)


class StudyGuideContentCheckTests(unittest.TestCase):
    def test_clean_callout_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text(
                "# Intro\n\n# Section 01 - One\n\nBody text.\n\n> **KEY TERM**\n>\n> Contract: a project rule.\n\nMore text.\n\n# References\n\n- AIA. Contract Documents.\n",
                encoding="utf-8",
            )
            result = checker.run_checks(path)
            self.assertTrue(result["passed"])

    def test_callout_in_references_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text("# References\n\n> **KEY TERM**\n>\n> Bad placement.\n", encoding="utf-8")
            result = checker.run_checks(path)
            self.assertFalse(result["passed"])

    def test_activity_language_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text("# Section 01 - One\n\nClass activity: discuss this with your group.\n", encoding="utf-8")
            result = checker.run_checks(path)
            self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
