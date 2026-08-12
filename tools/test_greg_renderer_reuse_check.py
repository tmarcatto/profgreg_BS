#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest


MODULE_PATH = "tools/greg_renderer_reuse_check.py"

spec = importlib.util.spec_from_file_location("greg_renderer_reuse_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_renderer_reuse_check"] = checker
spec.loader.exec_module(checker)


class RendererReuseCheckTests(unittest.TestCase):
    def test_run_checks_returns_findings(self) -> None:
        result = checker.run_checks()
        self.assertIn("findings", result)
        self.assertGreaterEqual(len(result["findings"]), 1)

    def test_render_markdown(self) -> None:
        text = checker.render_markdown({"passed": True, "fail_count": 0, "warn_count": 0, "findings": []})
        self.assertIn("Renderer reuse QA passed: yes", text)


if __name__ == "__main__":
    unittest.main()
