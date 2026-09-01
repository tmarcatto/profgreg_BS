#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
MODULE_PATH = ROOT / "tools" / "greg_live_production.py"

spec = importlib.util.spec_from_file_location("greg_live_production_approved_source_test", MODULE_PATH)
assert spec and spec.loader
production = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = production
spec.loader.exec_module(production)


class ApprovedDeckSourceTests(unittest.TestCase):
    def test_localization_translates_schedule_and_network_labels(self) -> None:
        source = [{
            "layout": "schedule_bar_chart",
            "title": "Plan",
            "schedule_rows": [{"activity": "Framing", "start": 0, "duration": 4, "status": "planned"}],
            "network_paths": [{
                "label": "Controlling path",
                "critical": True,
                "activities": [{"title": "Foundation", "duration": "4d"}],
            }],
        }]
        translated = [{
            "layout": "schedule_bar_chart",
            "title": "Plano",
            "schedule_rows": [{"activity": "Estrutura"}],
            "network_paths": [{"label": "Caminho controlador", "activities": [{"title": "Fundação"}]}],
        }]
        slides = production.localized_deck_slides(source, translated)
        self.assertEqual("Estrutura", slides[0]["schedule_rows"][0]["activity"])
        self.assertEqual(4, slides[0]["schedule_rows"][0]["duration"])
        self.assertEqual("Caminho controlador", slides[0]["network_paths"][0]["label"])
        self.assertEqual("Fundação", slides[0]["network_paths"][0]["activities"][0]["title"])
        self.assertEqual("4d", slides[0]["network_paths"][0]["activities"][0]["duration"])

    def test_uses_spec_for_exact_approved_deck_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "deck").mkdir()
            approved = run / "deck" / "lesson_05_deck_r02.pptx"
            approved.write_bytes(b"approved")
            (run / "deck" / "lesson_05_deck_r03.pptx").write_bytes(b"newer but unapproved")
            (run / "deck" / "lesson_05_deck_spec_r02.json").write_text(
                '{"output":{"pptx":"deck/lesson_05_deck_r02.pptx"}}', encoding="utf-8"
            )
            (run / "deck" / "lesson_05_deck_spec_r03.json").write_text(
                '{"output":{"pptx":"deck/lesson_05_deck_r03.pptx"}}', encoding="utf-8"
            )
            with patch.object(production, "approved_deck_baseline", return_value=approved):
                source_deck, source_spec = production.approved_deck_source_spec(run, "lesson_05")
            self.assertEqual(approved, source_deck)
            self.assertEqual("lesson_05_deck_spec_r02.json", source_spec.name)

    def test_stops_when_approved_deck_spec_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            approved = run / "deck" / "lesson_05_deck_r02.pptx"
            approved.parent.mkdir()
            approved.write_bytes(b"approved")
            with patch.object(production, "approved_deck_baseline", return_value=approved):
                with self.assertRaisesRegex(RuntimeError, "no matching deck spec"):
                    production.approved_deck_source_spec(run, "lesson_05")


if __name__ == "__main__":
    unittest.main()
