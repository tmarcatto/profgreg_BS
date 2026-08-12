#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_security_check.py"

spec = importlib.util.spec_from_file_location("greg_security_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_security_check"] = checker
spec.loader.exec_module(checker)


class GregSecurityCheckTests(unittest.TestCase):
    def test_security_check_shape(self) -> None:
        data = checker.run_checks()
        self.assertIn("passed", data)
        self.assertIn("findings", data)


if __name__ == "__main__":
    unittest.main()
