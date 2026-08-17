#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_render_study_guide_from_spec.py"
PDF_RENDERER_PATH = ROOT / "workspace" / "renderers" / "pdf" / "greg-buildstak-study-guide-renderer.py"

spec = importlib.util.spec_from_file_location("greg_render_study_guide_from_spec", MODULE_PATH)
assert spec and spec.loader
renderer = importlib.util.module_from_spec(spec)
sys.modules["greg_render_study_guide_from_spec"] = renderer
spec.loader.exec_module(renderer)

pdf_spec = importlib.util.spec_from_file_location("greg_buildstak_study_guide_renderer", PDF_RENDERER_PATH)
assert pdf_spec and pdf_spec.loader
pdf_renderer = importlib.util.module_from_spec(pdf_spec)
sys.modules["greg_buildstak_study_guide_renderer"] = pdf_renderer
try:
    pdf_spec.loader.exec_module(pdf_renderer)
except ModuleNotFoundError as error:
    if error.name != "reportlab":
        raise
    pdf_renderer = None


class RenderStudyGuideFromSpecTests(unittest.TestCase):
    def test_run_folder_from_relative_spec(self) -> None:
        path = renderer.run_folder_from_spec({"run_folder": "runs/demo"})
        self.assertEqual(path, ROOT / "runs" / "demo")

    def test_run_folder_blocks_absolute_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                renderer.run_folder_from_spec({"run_folder": tmp})

    def test_output_pdf_from_spec(self) -> None:
        spec_data = {"run_folder": "runs/demo", "output": {"pdf": "docx_pdf/lesson_01_study_guide_r02.pdf"}}
        self.assertEqual(renderer.output_pdf_from_spec(spec_data), ROOT / "runs" / "demo" / "docx_pdf" / "lesson_01_study_guide_r02.pdf")

    def test_structural_pages_are_enforced_by_heading(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        self.assertTrue(pdf_renderer.starts_structural_page("Introduction"))
        self.assertTrue(pdf_renderer.starts_structural_page("Section 01 - The First Decision"))
        self.assertTrue(pdf_renderer.starts_structural_page("Summary and Key Takeaways"))
        self.assertFalse(pdf_renderer.starts_structural_page("Section 02 - The Next Decision"))

    def test_visual_heading_matches_section_prefix(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        self.assertTrue(pdf_renderer.visual_matches_heading("Section 01", "Section 01 - The First Decision"))
        self.assertFalse(pdf_renderer.visual_matches_heading("Section 01", "Section 02 - The Next Decision"))

    def test_inline_headline_callout_keeps_short_label_and_full_body(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        blocks = pdf_renderer.parse_markdown(
            "> **Field Note: These responsibilities are one job, not six.** The duties run simultaneously."
        )
        self.assertEqual(blocks[0]["label"], "FIELD NOTE")
        self.assertEqual(
            blocks[0]["body"],
            "These responsibilities are one job, not six. The duties run simultaneously.",
        )


if __name__ == "__main__":
    unittest.main()
