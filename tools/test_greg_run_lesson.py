#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_run_lesson.py"

spec = importlib.util.spec_from_file_location("greg_run_lesson", MODULE_PATH)
assert spec and spec.loader
operator = importlib.util.module_from_spec(spec)
sys.modules["greg_run_lesson"] = operator
spec.loader.exec_module(operator)


class GregRunLessonTests(unittest.TestCase):
    def test_missing_run_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stage = operator.infer_stage(Path(tmp) / "missing", 1)
            self.assertEqual(stage.stage, "MISSING_RUN")
            self.assertTrue(stage.blockers)

    def test_intake_routes_to_course_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "demo"
            (run / "input").mkdir(parents=True)
            (run / "input" / "intake.md").write_text("Course level: Basic\nLesson 1: Foundations\n", encoding="utf-8")
            stage = operator.infer_stage(run, 1)
            self.assertEqual(stage.stage, "COURSE_MAP")
            self.assertFalse(stage.blockers)

    def test_complete_run_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "demo"
            for folder in ["input", "course_map", "sources", "lesson_draft", "docx_pdf", "approval", "deck", "process_review"]:
                (run / folder).mkdir(parents=True)
            for relative in [
                "course_map/course_map.md",
                "course_map/course_map.json",
                "course_map/course_map_qa.md",
                "sources/source_ledger.json",
                "sources/student_references.md",
                "lesson_draft/lesson_01_draft.md",
                "docx_pdf/lesson_01_study_guide.pdf",
                "approval/lesson_01_study_guide_approval.md",
                "approval/lesson_01_deck_approval.md",
                "deck/lesson_01_deck.pptx",
                "process_review/lesson_01_pipeline_qa.md",
            ]:
                (run / relative).write_text("x", encoding="utf-8")
            (run / "input" / "intake.md").write_text("Course level: Basic\nLesson 1: Foundations\n", encoding="utf-8")
            stage = operator.infer_stage(run, 1)
            self.assertEqual(stage.stage, "FULL_FLOW_CONFIRMATION_COMPLETE")

    def test_render_report_includes_action_and_executed(self) -> None:
        stage = operator.StageStatus(
            stage="PROCESS_REVIEW",
            gate_status="Ready for QA.",
            next_action="Run QA.",
            next_command="python3 tools/greg_lesson_pipeline_qa.py demo",
            blockers=[],
        )
        report = operator.build_report(
            "demo",
            1,
            stage,
            [],
            None,
            action="qa",
            executed=["Saved consolidated QA."],
        )
        text = operator.render_markdown(report)
        self.assertIn("Action: `qa`", text)
        self.assertIn("Saved consolidated QA.", text)

    def test_maybe_write_status_preserves_action_and_executed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "demo"
            (run / "process_review").mkdir(parents=True)
            stage = operator.StageStatus(
                stage="PROCESS_REVIEW",
                gate_status="Ready for QA.",
                next_action="Run QA.",
                next_command="python3 tools/greg_lesson_pipeline_qa.py demo",
                blockers=[],
            )
            out = operator.maybe_write_status(
                run,
                1,
                stage,
                None,
                action="lifecycle",
                executed=["Saved lesson source refresh QA."],
            )
            text = out.read_text(encoding="utf-8")
            self.assertIn("Action: `lifecycle`", text)
            self.assertIn("Saved lesson source refresh QA.", text)


if __name__ == "__main__":
    unittest.main()
