#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import shutil
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
MODULE_PATH = ROOT / "tools" / "greg_v0_production.py"
spec = importlib.util.spec_from_file_location("greg_v0_production", MODULE_PATH)
producer = importlib.util.module_from_spec(spec)
sys.modules["greg_v0_production"] = producer
assert spec and spec.loader
spec.loader.exec_module(producer)


class GregV0ProductionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.slug = "tmp-v0-production-test"
        self.run = ROOT / "runs" / self.slug
        if self.run.exists():
            shutil.rmtree(self.run)
        (self.run / "input").mkdir(parents=True)
        (self.run / "input" / "intake.md").write_text(
            "\n".join(
                [
                    "# Tmp V0 Production Test",
                    "",
                    "Course level: Intermediate",
                    "Expected lesson count: 15",
                    "Audience: U.S. residential construction workforce.",
                    "",
                    "## Initial Syllabus Direction",
                    "",
                    "Lesson 1: Production Foundation",
                    "This lesson validates the production path.",
                    "Build the map.",
                    "Render the guide.",
                ]
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        if self.run.exists():
            shutil.rmtree(self.run)

    def test_course_map_and_source_ledger_are_created(self) -> None:
        course_map = producer.produce_course_map(self.slug)
        source_ledger = producer.produce_source_ledger(self.slug)
        self.assertTrue((self.run / "course_map" / "course_map.json").exists())
        self.assertTrue((self.run / "course_map" / "course_map_qa.md").exists())
        self.assertTrue((self.run / "sources" / "source_ledger.json").exists())
        self.assertTrue((self.run / "sources" / "student_references.md").exists())
        self.assertTrue(any("Course Map" in item for item in course_map))
        self.assertTrue(any("source ledger" in item for item in source_ledger))


if __name__ == "__main__":
    unittest.main()
