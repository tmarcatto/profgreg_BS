#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_security.py"

spec = importlib.util.spec_from_file_location("greg_security", MODULE_PATH)
assert spec and spec.loader
security = importlib.util.module_from_spec(spec)
sys.modules["greg_security"] = security
spec.loader.exec_module(security)


class GregSecurityTests(unittest.TestCase):
    def test_safe_write_path_allows_runs(self) -> None:
        path = security.assert_safe_write_path("runs/demo/process_review/report.md")
        self.assertTrue(str(path).endswith("runs/demo/process_review/report.md"))

    def test_safe_write_path_blocks_escape(self) -> None:
        with self.assertRaises(ValueError):
            security.assert_safe_write_path("../outside.md")

    def test_safe_write_path_blocks_root_file(self) -> None:
        with self.assertRaises(ValueError):
            security.assert_safe_write_path(".env.local")

    def test_run_slug_blocks_traversal(self) -> None:
        with self.assertRaises(ValueError):
            security.assert_safe_run_slug("../demo")


if __name__ == "__main__":
    unittest.main()
