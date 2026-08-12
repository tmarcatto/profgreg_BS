#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_localized_deck_text_map_check.py"

spec = importlib.util.spec_from_file_location("greg_localized_deck_text_map_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_localized_deck_text_map_check"] = checker
spec.loader.exec_module(checker)


SAMPLE = """# Deck Text Map

Course slug: `demo`
Lesson: 01
Source deck: `deck/lesson_01_deck_r02.pptx`
Target locale: PT-BR
Scope: deck_text_map_smoke_test
Status: complete

## Slide 01

- Original title: Short title
- Localized title: Título localizado mais comprido
- Localized visible text:
  - Item curto
- Preserved terms: PM
- Length risk: high
- Layout note: needs shorter rewrite for fit.
"""


class LocalizedDeckTextMapCheckTests(unittest.TestCase):
    def test_parse_slides(self) -> None:
        slides = checker.parse_slides(SAMPLE)
        self.assertEqual(len(slides), 1)
        self.assertEqual(slides[0].slide, 1)
        self.assertEqual(slides[0].length_risk, "high")

    def test_high_risk_requires_rewrite_plan(self) -> None:
        slide = checker.parse_slides(SAMPLE)[0]
        self.assertTrue(checker.compact_rewrite_needed(slide))
        self.assertTrue(checker.note_has_rewrite_plan(slide.layout_note))

    def test_missing_map_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = checker.run_checks(Path(tmp) / "missing.md", Path(tmp) / "missing_qa.md")
            self.assertFalse(result["passed"])
            self.assertGreaterEqual(result["fail_count"], 1)


if __name__ == "__main__":
    unittest.main()
