#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest


MODULE_PATH = "tools/greg_prepare_full_flow_test.py"

spec = importlib.util.spec_from_file_location("greg_prepare_full_flow_test", MODULE_PATH)
assert spec and spec.loader
prep = importlib.util.module_from_spec(spec)
sys.modules["greg_prepare_full_flow_test"] = prep
spec.loader.exec_module(prep)


class PrepareFullFlowTestTests(unittest.TestCase):
    def test_slugify(self) -> None:
        self.assertEqual(prep.slugify("My Course!"), "my-course")

    def test_render_markdown(self) -> None:
        data = prep.PreparedRun("demo", "runs/demo", "runs/demo/check.md", "runs/demo/intake.md", "runs/demo/status.md")
        text = prep.render_markdown(data)
        self.assertIn("demo", text)


if __name__ == "__main__":
    unittest.main()
