#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_lesson_pipeline_qa.py"

spec = importlib.util.spec_from_file_location("greg_lesson_pipeline_qa", MODULE_PATH)
assert spec and spec.loader
pipeline = importlib.util.module_from_spec(spec)
sys.modules["greg_lesson_pipeline_qa"] = pipeline
spec.loader.exec_module(pipeline)


class LessonPipelineQATests(unittest.TestCase):
    def test_lesson_id(self) -> None:
        self.assertEqual(pipeline.lesson_id(1), "lesson_01")
        self.assertEqual(pipeline.lesson_id(12), "lesson_12")

    def test_render_markdown_contains_gate_table(self) -> None:
        data = {
            "passed": True,
            "course_slug": "demo",
            "lesson": 1,
            "fail_count": 0,
            "warn_count": 0,
            "gates": [
                {
                    "gate": "course_map",
                    "status": "pass",
                    "fail_count": 0,
                    "warn_count": 0,
                    "path": "runs/demo/course_map/course_map.json",
                    "note": "",
                    "findings": [],
                }
            ],
        }
        text = pipeline.render_markdown(data)
        self.assertIn("Lesson pipeline QA passed: yes", text)
        self.assertIn("| course_map | pass |", text)

    def test_manifest_artifact_filters_wrong_lesson(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            process_review = run / "process_review"
            process_review.mkdir()
            (process_review / "canonical_artifacts.json").write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {
                                "key": "study_guide_pdf",
                                "path": "docx_pdf/lesson_01_study_guide.pdf",
                                "lesson": "01",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.assertIsNone(pipeline.manifest_artifact(run, "study_guide_pdf", 2))
            self.assertEqual(
                pipeline.manifest_artifact(run, "study_guide_pdf", 1),
                run / "docx_pdf" / "lesson_01_study_guide.pdf",
            )


if __name__ == "__main__":
    unittest.main()
