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
    def test_source_with_paragraph_summary_is_blocked_before_rendering(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as tmp:
            draft = Path(tmp) / "draft.md"
            draft.write_text(
                "# Introduction\n\nCourse orientation.\n\n"
                "# Section 01 - One\n\nBody text.\n\n"
                "# Section 02 - Two\n\nBody text.\n\n"
                "# Section 03 - Three\n\nBody text.\n\n"
                "# Section 04 - Four\n\nBody text.\n\n"
                "# Summary and Key Takeaways\n\nThis must be bullets, not a paragraph.\n\n"
                "# References\n\n- A formal source.\n",
                encoding="utf-8",
            )
            relative = str(draft.relative_to(ROOT))
            with self.assertRaisesRegex(RuntimeError, "Summary must contain only 4 to 6 bullet points"):
                renderer.validate_source_markdown({"source_markdown": relative})

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

    def test_approved_inline_callout_keeps_short_label_and_full_body(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        blocks = pdf_renderer.parse_markdown(
            "> **Scenario: These responsibilities are one job, not six.** The duties run simultaneously."
        )
        self.assertEqual(blocks[0]["label"], "SCENARIO")
        self.assertEqual(
            blocks[0]["body"],
            "These responsibilities are one job, not six. The duties run simultaneously.",
        )

    def test_unapproved_callout_label_is_not_rendered_as_box(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        blocks = pdf_renderer.parse_markdown("> **A Clever New Box:** This must remain ordinary prose.")
        self.assertEqual(blocks[0]["type"], "paragraph")

    def test_plain_canonical_callout_syntax_is_rendered_as_box(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        blocks = pdf_renderer.parse_markdown("> KEY TERM: Scope is the agreed work.")
        self.assertEqual(blocks[0], {"type": "callout", "label": "KEY TERM", "body": "Scope is the agreed work."})

    def test_fenced_ascii_visual_is_not_rendered_as_prose(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        blocks = pdf_renderer.parse_markdown("Body before.\n\n```\n[A] -> [B]\n```\n\nBody after.")
        self.assertEqual([block["text"] for block in blocks if block["type"] == "paragraph"], ["Body before.", "Body after."])

    def test_long_cover_title_fits_three_lines_without_dropping_words(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        title = "The Complete Construction Project Manager From Pre-Construction to Closeout"
        lines, font_size = pdf_renderer.fit_cover_title(title, 360)
        self.assertLessEqual(len(lines), 3)
        self.assertGreaterEqual(font_size, 18)
        self.assertEqual(" ".join(lines), title)


if __name__ == "__main__":
    unittest.main()
