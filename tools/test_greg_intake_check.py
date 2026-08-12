#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = "tools/greg_intake_check.py"

spec = importlib.util.spec_from_file_location("greg_intake_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_intake_check"] = checker
spec.loader.exec_module(checker)


class IntakeCheckTests(unittest.TestCase):
    def test_placeholder_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "intake.md"
            path.write_text("Course level: Basic | Intermediate | Advanced\nPaste the user-provided syllabus here.\n", encoding="utf-8")
            result = checker.run_checks(path)
            self.assertFalse(result["passed"])

    def test_filled_intake_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "intake.md"
            path.write_text("Course level: Basic\nLesson 1: Foundations\nThis lesson starts the course.\n", encoding="utf-8")
            result = checker.run_checks(path)
            self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()
