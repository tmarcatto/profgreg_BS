#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_cross_lesson_mece_check.py"

spec = importlib.util.spec_from_file_location("greg_cross_lesson_mece_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_cross_lesson_mece_check"] = checker
spec.loader.exec_module(checker)


class CrossLessonMECETests(unittest.TestCase):
    def setUp(self) -> None:
        self.slug = "tmp-cross-lesson-mece"
        self.run = ROOT / "runs" / self.slug
        if self.run.exists():
            shutil.rmtree(self.run)
        (self.run / "lesson_draft").mkdir(parents=True)
        (self.run / "docx_pdf").mkdir(parents=True)

    def tearDown(self) -> None:
        if self.run.exists():
            shutil.rmtree(self.run)

    def write_lesson(self, number: int, markdown: str, visuals: list[dict]) -> None:
        lid = f"lesson_{number:02d}"
        (self.run / "lesson_draft" / f"{lid}_draft.md").write_text(markdown, encoding="utf-8")
        (self.run / "docx_pdf" / f"{lid}_study_guide_spec.json").write_text(
            json.dumps({"visuals": visuals}),
            encoding="utf-8",
        )

    def lesson_markdown(self, section: str, terms: list[str]) -> str:
        glossary = "\n".join(f"- **{term}**: definition." for term in terms)
        return f"# Section 01 - {section}\n\nBody.\n\n---\n\n# Glossary\n\n{glossary}\n\n---\n\n# References\n\n- Source."

    def test_repeated_glossary_term_fails(self) -> None:
        self.write_lesson(1, self.lesson_markdown("Baseline Basics", ["Activity"]), [])
        self.write_lesson(2, self.lesson_markdown("Schedule Logic", ["Activity"]), [])
        data = checker.run_checks(self.slug, 2)
        checks = {item["check"]: item["status"] for item in data["findings"]}
        self.assertEqual(checks["glossary_mece"], "fail")

    def test_repeated_card_row_structure_fails(self) -> None:
        visual = {"type": "card_row", "title": "Five Step Loop", "pill": "Plan", "cards": [{}, {}, {}, {}, {}]}
        self.write_lesson(1, self.lesson_markdown("Baseline Basics", ["Activity"]), [visual])
        self.write_lesson(2, self.lesson_markdown("Schedule Logic", ["Dependency"]), [visual | {"title": "Different Labels"}])
        data = checker.run_checks(self.slug, 2)
        checks = {item["check"]: item["status"] for item in data["findings"]}
        self.assertEqual(checks["visual_structure_mece"], "fail")

    def test_distinct_matrix_and_new_terms_pass(self) -> None:
        self.write_lesson(
            1,
            self.lesson_markdown("Baseline Basics", ["Activity"]),
            [{"type": "card_row", "title": "Five Step Loop", "pill": "Plan", "cards": [{}, {}, {}, {}, {}]}],
        )
        self.write_lesson(
            2,
            self.lesson_markdown("Schedule Logic", ["Dependency"]),
            [{"type": "source_to_wbs_matrix", "title": "Document Decisions", "rows": [{}, {}, {}, {}, {}]}],
        )
        data = checker.run_checks(self.slug, 2)
        self.assertTrue(data["passed"], data["findings"])


if __name__ == "__main__":
    unittest.main()
