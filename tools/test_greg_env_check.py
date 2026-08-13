#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_env_check.py"

spec = importlib.util.spec_from_file_location("greg_env_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_env_check"] = checker
spec.loader.exec_module(checker)


class GregEnvCheckTests(unittest.TestCase):
    def test_missing_required_keys_fails_without_secret_values(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch.object(checker, "load_env_file", lambda path: None):
            data = checker.run_checks()
        self.assertFalse(data["passed"])
        self.assertIn("OPENAI_API_KEY", data["missing_required"])

    def test_set_required_keys_passes_and_reports_length_only(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "abc", "ANTHROPIC_API_KEY": "defgh"}, clear=True):
            data = checker.run_checks()
            report = checker.render_markdown(data)
        self.assertTrue(data["passed"])
        self.assertIn("OPENAI_API_KEY: set length=3", report)
        self.assertNotIn("abc", report)
