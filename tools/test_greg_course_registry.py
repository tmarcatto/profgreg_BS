#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_course_registry.py"

spec = importlib.util.spec_from_file_location("greg_course_registry", MODULE_PATH)
assert spec and spec.loader
registry = importlib.util.module_from_spec(spec)
sys.modules["greg_course_registry"] = registry
spec.loader.exec_module(registry)


class CourseRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.slug = "tmp-course-registry"
        self.run = ROOT / "runs" / self.slug
        if self.run.exists():
            shutil.rmtree(self.run)
        (self.run / "lesson_draft").mkdir(parents=True)
        (self.run / "docx_pdf").mkdir()
        (self.run / "deck").mkdir()

    def tearDown(self) -> None:
        if self.run.exists():
            shutil.rmtree(self.run)

    def write_lesson(self, lesson: int, term: str, visual_title: str) -> None:
        lid = f"lesson_{lesson:02d}"
        (self.run / "lesson_draft" / f"{lid}_draft.md").write_text(
            f"# Lesson\n\n# Glossary\n\n- **{term}**: definition.\n\n---\n\n# References\n\n- Source.\n",
            encoding="utf-8",
        )
        (self.run / "docx_pdf" / f"{lid}_study_guide_spec.json").write_text(
            json.dumps({"visuals": [{"type": "card_row", "title": visual_title, "caption": f"Figure {lesson}.1. {visual_title} teaches a distinct idea.", "cards": [{}, {}]}]}),
            encoding="utf-8",
        )
        (self.run / "deck" / f"{lid}_visual_plan.json").write_text(json.dumps({"visuals": []}), encoding="utf-8")

    def test_build_registry_collects_terms_and_visuals(self) -> None:
        self.write_lesson(1, "Baseline schedule", "Baseline Plan")
        data = registry.build_registry(self.slug)
        self.assertEqual(data["lessons"][0]["glossary_count"], 1)
        self.assertEqual(data["glossary_terms"][0]["normalized"], "baseline schedule")
        self.assertEqual(data["visuals"][0]["normalized_title"], "baseline plan")

    def test_repeated_glossary_term_fails(self) -> None:
        self.write_lesson(1, "Activity", "Activity Flow")
        self.write_lesson(2, "Activity", "Different Flow")
        data = registry.run_checks(self.slug)
        checks = {item["check"]: item["status"] for item in data["findings"]}
        self.assertEqual(checks["glossary_home_lesson"], "fail")

    def test_unique_terms_and_visual_claims_pass(self) -> None:
        self.write_lesson(1, "Activity", "Baseline Flow")
        self.write_lesson(2, "Dependency", "Logic Flow")
        data = registry.run_checks(self.slug)
        self.assertTrue(data["passed"], data["findings"])


if __name__ == "__main__":
    unittest.main()
