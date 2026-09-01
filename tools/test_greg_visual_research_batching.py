#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("greg_live_production", ROOT / "tools" / "greg_live_production.py")
if not spec or not spec.loader:
    raise RuntimeError("Could not load greg_live_production.py")
production = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = production
spec.loader.exec_module(production)


class GregVisualResearchBatchingTests(unittest.TestCase):
    def test_fifteen_lessons_are_split_into_bounded_batches(self) -> None:
        lessons = [{"lesson_number": number} for number in range(1, 16)]
        batches = production.visual_research_batches(lessons)
        self.assertEqual([5, 5, 5], [len(batch) for batch in batches])
        self.assertEqual([1, 6, 11], [batch[0]["lesson_number"] for batch in batches])

    def test_batch_must_return_every_requested_lesson(self) -> None:
        batch = [{"lesson_number": 1}, {"lesson_number": 2}]
        with self.assertRaisesRegex(RuntimeError, r"expected \[1, 2\]"):
            production.validate_visual_research_batch(batch, {"lessons": [{"lesson_number": 1}]})


if __name__ == "__main__":
    unittest.main()
