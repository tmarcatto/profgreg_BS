#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_course_status.py"

spec = importlib.util.spec_from_file_location("greg_course_status", MODULE_PATH)
assert spec and spec.loader
status = importlib.util.module_from_spec(spec)
sys.modules["greg_course_status"] = status
spec.loader.exec_module(status)


class CourseStatusTests(unittest.TestCase):
    def test_summarize_lessons_reads_multi_lesson_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "demo"
            (run / "docx_pdf").mkdir(parents=True)
            (run / "deck").mkdir()
            (run / "process_review").mkdir()
            (run / "docx_pdf" / "lesson_01_study_guide.pdf").write_text("pdf", encoding="utf-8")
            (run / "deck" / "lesson_01_deck_r02.pptx").write_text("deck", encoding="utf-8")
            (run / "process_review" / "lesson_01_pipeline_qa.md").write_text("qa", encoding="utf-8")
            manifest = {
                "artifacts": [
                    {
                        "key": "lesson_01_study_guide_pdf",
                        "path": "docx_pdf/lesson_01_study_guide.pdf",
                        "status": "approved",
                        "lesson": "01",
                    },
                    {
                        "key": "lesson_01_deck_pptx",
                        "path": "deck/lesson_01_deck_r02.pptx",
                        "status": "approved",
                        "lesson": "01",
                    },
                    {
                        "key": "lesson_01_pipeline_qa",
                        "path": "process_review/lesson_01_pipeline_qa.md",
                        "status": "supporting",
                        "lesson": "01",
                    },
                ]
            }

            lessons = status.summarize_lessons(run, manifest)

            self.assertEqual(lessons[0]["lesson"], "01")
            self.assertEqual(lessons[0]["study_guide"], "approved")
            self.assertEqual(lessons[0]["deck"], "approved")
            self.assertEqual(lessons[0]["pipeline_qa"], "present")

    def test_render_markdown_includes_lesson_table(self) -> None:
        text = status.render_markdown(
            {
                "stage": "TECHNICAL_PAUSE",
                "artifacts": [],
                "parked": [],
                "gate_status": "ok",
                "canonical_manifest": "runs/demo/process_review/canonical_artifacts.json",
                "blockers": [],
                "next_recommended_action": "continue",
                "lessons": [
                    {
                        "lesson": "01",
                        "study_guide": "approved",
                        "deck": "approved",
                        "pipeline_qa": "present",
                    }
                ],
            }
        )

        self.assertIn("Lesson status:", text)
        self.assertIn("| 01 | approved | approved | present |", text)


if __name__ == "__main__":
    unittest.main()
