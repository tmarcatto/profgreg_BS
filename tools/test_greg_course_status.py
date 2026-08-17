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
    def test_operating_progress_uses_approved_artifacts_only(self) -> None:
        lessons = [
            {
                "study_guide": "approved" if index == 0 else "active",
                "deck": "approved" if index == 0 else "missing",
                "pt_br_study_guide": "approved" if index == 0 else "missing",
                "pt_br_deck": "missing",
                "es_study_guide": "missing",
                "es_deck": "missing",
            }
            for index in range(15)
        ]
        result = status.operating_progress(True, lessons)
        self.assertAlmostEqual(result["percent"], 28.75, places=2)
        self.assertAlmostEqual(result["course_books"]["points"], 1.667, places=3)
        self.assertAlmostEqual(result["presentations"]["points"], 1.667, places=3)
        self.assertAlmostEqual(result["translations"]["points"], 0.417, places=3)

    def test_operating_progress_full_course_is_100(self) -> None:
        lesson = {
            "study_guide": "approved",
            "deck": "approved",
            "pt_br_study_guide": "approved",
            "pt_br_deck": "approved",
            "es_study_guide": "approved",
            "es_deck": "approved",
        }
        self.assertEqual(status.operating_progress(True, [lesson] * 15)["percent"], 100.0)

    def test_summarize_lessons_reads_multi_lesson_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "demo"
            (run / "docx_pdf").mkdir(parents=True)
            (run / "deck").mkdir()
            (run / "process_review").mkdir()
            (run / "course_map").mkdir()
            (run / "lesson_draft").mkdir()
            (run / "sources").mkdir()
            (run / "review").mkdir()
            (run / "course_map" / "course_map.json").write_text(
                '{"lessons": [{"lesson_number": 1, "title": "The Modern Construction Project Manager"}]}',
                encoding="utf-8",
            )
            (run / "docx_pdf" / "lesson_01_study_guide.pdf").write_text("pdf", encoding="utf-8")
            (run / "deck" / "lesson_01_deck_r02.pptx").write_text("deck", encoding="utf-8")
            (run / "process_review" / "lesson_01_pipeline_qa.md").write_text("qa", encoding="utf-8")
            for name in ("pedagogy_review", "citation_review", "design_qa"):
                (run / "review" / f"lesson_01_{name}.md").write_text("## Verdict\n\nPASS\n", encoding="utf-8")
            (run / "review" / "lesson_01_visual_qa.md").write_text("Visual plan QA passed: yes\n", encoding="utf-8")
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
            self.assertEqual(lessons[0]["title"], "The Modern Construction Project Manager")
            self.assertEqual(lessons[0]["study_guide"], "approved")
            self.assertEqual(lessons[0]["deck"], "approved")
            self.assertEqual(lessons[0]["pipeline_qa"], "present")

    def test_stale_study_guide_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "demo"
            (run / "docx_pdf").mkdir(parents=True)
            (run / "lesson_draft").mkdir()
            (run / "sources").mkdir()
            (run / "course_map").mkdir()
            (run / "docx_pdf" / "lesson_01_study_guide.pdf").write_text("pdf", encoding="utf-8")
            (run / "lesson_draft" / "lesson_01_draft.md").write_text(
                "# Introduction\n\nThis study guide is written for construction learners working in the United States.\n\n# Section 01 - One\n\nBody.",
                encoding="utf-8",
            )
            (run / "sources" / "student_references.md").write_text(
                "# References\n\n- Current student references will be added after research expansion.\n",
                encoding="utf-8",
            )
            manifest = {
                "artifacts": [
                    {
                        "key": "lesson_01_study_guide_pdf",
                        "path": "docx_pdf/lesson_01_study_guide.pdf",
                        "status": "active",
                        "lesson": "01",
                    }
                ]
            }

            lessons = status.summarize_lessons(run, manifest)

            self.assertEqual(lessons[0]["study_guide"], "blocked")
            self.assertNotIn("study_guide_path", lessons[0])
            self.assertIn("study_guide_blocked_path", lessons[0])
            self.assertTrue(lessons[0]["study_guide_quality_blockers"])

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
