#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
MODULE_PATH = ROOT / "tools" / "greg_live_production.py"

spec = importlib.util.spec_from_file_location("greg_live_production_revision_test", MODULE_PATH)
assert spec and spec.loader
production = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = production
spec.loader.exec_module(production)


class LocalizedDeckRevisionTests(unittest.TestCase):
    def test_revision_discards_model_layout_drift(self) -> None:
        source = [{"layout": "row_list", "title": "Antes", "items": [{"title": "A", "body": "B"}]}]
        translated = [{"layout": "comparison", "title": "Depois", "items": [{"title": "A", "body": "Curto"}]}]
        slides = production.localized_deck_slides(source, translated, preserve_layout_on_drift=True)
        self.assertEqual("row_list", slides[0]["layout"])
        self.assertEqual("Depois", slides[0]["title"])


if __name__ == "__main__":
    unittest.main()
