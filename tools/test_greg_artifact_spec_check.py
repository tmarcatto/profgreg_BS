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
MODULE_PATH = ROOT / "tools" / "greg_artifact_spec_check.py"

spec = importlib.util.spec_from_file_location("greg_artifact_spec_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_artifact_spec_check"] = checker
spec.loader.exec_module(checker)


class ArtifactSpecCheckTests(unittest.TestCase):
    fixture_run = ROOT / "runs" / "tmp-artifact-spec-test"

    def setUp(self) -> None:
        self.fixture_run.mkdir(parents=True, exist_ok=True)
        (self.fixture_run / "lesson_draft").mkdir(parents=True, exist_ok=True)
        (self.fixture_run / "docx_pdf").mkdir(parents=True, exist_ok=True)
        (self.fixture_run / "deck").mkdir(parents=True, exist_ok=True)
        (self.fixture_run / "lesson_draft" / "lesson_01_draft.md").write_text("# Lesson draft\n", encoding="utf-8")
        (self.fixture_run / "docx_pdf" / "lesson_01_study_guide.pdf").write_bytes(b"%PDF-1.4\n")
        (self.fixture_run / "deck" / "lesson_01_deck_r03.pptx").write_bytes(b"pptx")

    def tearDown(self) -> None:
        shutil.rmtree(self.fixture_run, ignore_errors=True)

    def write_spec(self, data: dict) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        with tmp:
            json.dump(data, tmp)
        return Path(tmp.name)

    def base_pdf_spec(self) -> dict:
        return {
            "course_slug": "tmp-artifact-spec-test",
            "course_title": "Temporary Artifact Spec Test",
            "lesson_number": "1",
            "production_mode": "revision",
            "revision": "r02",
            "run_folder": "runs/tmp-artifact-spec-test",
            "source_markdown": "runs/tmp-artifact-spec-test/lesson_draft/lesson_01_draft.md",
            "approved_baseline_artifact": "docx_pdf/lesson_01_study_guide.pdf",
            "metadata": {
                "course_title": "Temporary Artifact Spec Test",
                "lesson_number": "1",
                "lesson_short_title": "Mastering the Baseline",
                "level_label": "Basic Level",
                "icon": "workspace/assets/logos/buildstak-icon.png",
            },
            "output": {
                "pdf": "docx_pdf/lesson_01_study_guide_r02.pdf",
                "render_qa": "docx_pdf/lesson_01_render_qa_r02.md",
                "layout_qa": "docx_pdf/lesson_01_pdf_layout_qa_r02.md",
                "rendered_dir": "docx_pdf/rendered_pages_r02",
            },
            "visuals": [
                {
                    "after_heading": "A Baseline Is More Than Dates",
                    "type": "card_row",
                    "title": "Baseline as the Plan of Record",
                    "caption": "Figure 1.1. A baseline connects the plan.",
                    "cards": [{"title": "Scope", "lines": ["work included"]}],
                }
            ],
            "qa_notes": ["Approved student-facing artifact remains docx_pdf/lesson_01_study_guide.pdf."],
        }

    def test_pdf_spec_passes(self) -> None:
        data = checker.run_checks(self.write_spec(self.base_pdf_spec()), "study_guide_pdf")
        self.assertTrue(data["passed"], data["findings"])

    def test_pdf_spec_blocks_overwriting_baseline(self) -> None:
        spec_data = self.base_pdf_spec()
        spec_data["output"]["pdf"] = "docx_pdf/lesson_01_study_guide.pdf"
        data = checker.run_checks(self.write_spec(spec_data), "study_guide_pdf")
        checks = {item["check"]: item["status"] for item in data["findings"]}
        self.assertEqual(checks["baseline_not_overwritten"], "fail")

    def test_absolute_path_fails(self) -> None:
        spec_data = self.base_pdf_spec()
        spec_data["source_markdown"] = str(ROOT / "runs" / "demo.md")
        data = checker.run_checks(self.write_spec(spec_data), "study_guide_pdf")
        checks = {item["check"]: item["status"] for item in data["findings"]}
        self.assertEqual(checks["relative_paths"], "fail")

    def test_unknown_deck_layout_fails(self) -> None:
        spec_data = {
            "course_slug": "tmp-artifact-spec-test",
            "course_title": "Temporary Artifact Spec Test",
            "lesson_number": 1,
            "production_mode": "revision",
            "revision": "r04",
            "run_folder": "runs/tmp-artifact-spec-test",
            "approved_baseline_artifact": "deck/lesson_01_deck_r03.pptx",
            "assets": {"brand_icon": "workspace/assets/logos/buildstak-icon.png"},
            "output": {"pptx": "deck/lesson_01_deck_r04.pptx", "qa": "deck/lesson_01_deck_qa.md", "rendered_dir": "deck/rendered_slides"},
            "slides": [{"layout": "unknown"} for _ in range(10)],
            "qa_checks": ["MECE", "no automatic last-item highlight", "residential"],
        }
        data = checker.run_checks(self.write_spec(spec_data), "deck")
        checks = {item["check"]: item["status"] for item in data["findings"]}
        self.assertEqual(checks["deck_layouts"], "fail")

    def test_diverse_deck_with_teaching_image_passes_new_visual_gates(self) -> None:
        body = [
            "intro_image_bullets", "card_sequence", "comparison", "planned_actual",
            "row_list", "checklist_rows", "image_bullets", "card_sequence",
        ]
        slides = [{"layout": "cover", "topics": ["One", "Two", "Three"]}]
        for index, layout in enumerate(body, start=2):
            slide = {"layout": layout}
            if layout in {"intro_image_bullets", "image_bullets"}:
                slide["image"] = {"path": f"deck/assets/lesson_01_teaching_image_{index:02d}.png", "alt": "Residential construction teaching image"}
            slides.append(slide)
        slides.append({"layout": "takeaway"})
        spec_data = {
            "course_slug": "tmp-artifact-spec-test",
            "course_title": "Temporary Artifact Spec Test",
            "lesson_number": 1,
            "production_mode": "revision",
            "revision": "r04",
            "run_folder": "runs/tmp-artifact-spec-test",
            "approved_baseline_artifact": "deck/lesson_01_deck_r03.pptx",
            "assets": {"brand_icon": "workspace/assets/logos/buildstak-icon.png"},
            "output": {"pptx": "deck/lesson_01_deck_r04.pptx", "qa": "deck/lesson_01_deck_qa.md", "rendered_dir": "deck/rendered_slides"},
            "slides": slides,
            "qa_checks": ["MECE", "no automatic last-item highlight", "residential"],
        }
        data = checker.run_checks(self.write_spec(spec_data), "deck")
        checks = {item["check"]: item["status"] for item in data["findings"]}
        self.assertTrue(data["passed"], data["findings"])
        self.assertEqual(checks["deck_required_teaching_image"], "pass")
        self.assertEqual(checks["deck_layout_diversity"], "pass")

    def test_initial_pdf_spec_does_not_require_baseline_or_revisioned_output(self) -> None:
        spec_data = self.base_pdf_spec()
        spec_data["production_mode"] = "initial"
        spec_data.pop("revision")
        spec_data.pop("approved_baseline_artifact")
        spec_data["output"]["pdf"] = "docx_pdf/lesson_02_study_guide.pdf"
        spec_data["qa_notes"] = ["Initial production for human approval."]
        data = checker.run_checks(self.write_spec(spec_data), "study_guide_pdf")
        checks = {item["check"]: item["status"] for item in data["findings"]}
        self.assertTrue(data["passed"], data["findings"])
        self.assertEqual(checks["baseline_exists"], "pass")
        self.assertEqual(checks["revisioned_primary_output"], "pass")


if __name__ == "__main__":
    unittest.main()
