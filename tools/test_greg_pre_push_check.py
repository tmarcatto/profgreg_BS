#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_pre_push_check.py"

spec = importlib.util.spec_from_file_location("greg_pre_push_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_pre_push_check"] = checker
spec.loader.exec_module(checker)


class GregPrePushCheckTests(unittest.TestCase):
    def test_report_shape(self) -> None:
        step = checker.Step("sample", ["true"])
        report = checker.render_report([(step, True, "ok")])
        self.assertIn("pre-push QA passed: yes", report)
        self.assertIn("PASS sample", report)


if __name__ == "__main__":
    unittest.main()
