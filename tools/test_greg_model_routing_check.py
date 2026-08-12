#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest


MODULE_PATH = "tools/greg_model_routing_check.py"

spec = importlib.util.spec_from_file_location("greg_model_routing_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_model_routing_check"] = checker
spec.loader.exec_module(checker)


class ModelRoutingCheckTests(unittest.TestCase):
    def test_provider_refs(self) -> None:
        refs = checker.provider_refs(
            {
                "primary": {"provider": "a"},
                "fallbacks": [{"provider": "b"}],
                "metadata_helpers": ["c"],
                "premium_escalation": {"provider": "d"},
            }
        )
        self.assertEqual(refs, ["a", "b", "c", "d"])

    def test_current_config_passes(self) -> None:
        result = checker.run_checks()
        self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()
