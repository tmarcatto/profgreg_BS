#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_pdf_layout_check.py"

spec = importlib.util.spec_from_file_location("greg_pdf_layout_check", MODULE_PATH)
assert spec and spec.loader
pdf_qa = importlib.util.module_from_spec(spec)
sys.modules["greg_pdf_layout_check"] = pdf_qa
spec.loader.exec_module(pdf_qa)


class PdfLayoutCheckUnitTests(unittest.TestCase):
    def test_figure_numbers_accept_english_portuguese_and_spanish_labels(self) -> None:
        self.assertEqual(["1.1", "1.2", "1.3"], pdf_qa.figure_numbers("Figure 1.1 Figura 1.2 Figura 1.3"))

    def test_find_page(self) -> None:
        pages = ["Cover", "Lesson Roadmap", "Introduction\nLearning Objectives", "Section 01 - Start"]
        self.assertEqual(pdf_qa.find_page(pages, r"Lesson Roadmap"), 2)
        self.assertEqual(pdf_qa.find_page(pages, r"Section\s+01\s+-"), 4)

    def test_heading_only_does_not_match_prose_that_starts_with_heading_word(self) -> None:
        pages = [
            "Cover",
            "Introduction",
            "References are most useful when they concern comparable work.",
            "References",
        ]
        self.assertEqual(pdf_qa.find_page(pages, r"References", min_page=3, heading_only=True), 4)

    def test_forbidden_patterns(self) -> None:
        self.assertTrue(pdf_qa.contains("References Accessed August 9, 2026", r"\bAccessed\s+August\b"))
        self.assertTrue(pdf_qa.contains("/Users/name/file.pdf", r"/Users/"))
        self.assertFalse(pdf_qa.contains("References AIA Contract Documents", r"/Users/"))
        self.assertFalse(pdf_qa.contains("reliability of working commitments", r"source reliability"))

    def test_norm(self) -> None:
        self.assertEqual(pdf_qa.norm("A\n  B\tC"), "A B C")
        self.assertEqual(pdf_qa.norm("Pre-\nConstruction Plan"), "Pre-Construction Plan")

    def test_missing_pdf_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = pdf_qa.run_checks(Path(tmp) / "missing.pdf", Path(tmp) / "missing_qa.md")
            self.assertFalse(result["passed"])
            self.assertGreaterEqual(result["fail_count"], 1)

    def test_meaningful_lines_ignores_footer_noise(self) -> None:
        lines = pdf_qa.meaningful_lines("Construction Schedule Management\n4\nSection 01 - Start\nBody")
        self.assertEqual(lines, ["Section 01 - Start", "Body"])

    def test_heading_detection_is_conservative(self) -> None:
        self.assertTrue(pdf_qa.is_heading_line("Section 02 - Schedule Logic"))
        self.assertTrue(pdf_qa.is_heading_line("KEY TERM"))
        self.assertFalse(pdf_qa.is_heading_line("Path B is procurement:"))
        self.assertFalse(pdf_qa.is_heading_line("turned over clean.'"))

    def test_figure_numbers(self) -> None:
        self.assertEqual(pdf_qa.figure_numbers("Figure 2.1. Text\nFigure 2.3. More"), ["2.1", "2.3"])

    def test_expected_visible_visual_text_tracks_renderer_content(self) -> None:
        spec = {
            "visuals": [
                {"type": "process_flow", "title": "Flow", "nodes": [{"title": "Gate", "detail": "Decision evidence"}]},
                {"type": "source_to_wbs_matrix", "title": "Matrix", "left_header": "Concept", "right_header": "Meaning", "rows": [{"left": "Daily", "right": "Facts recorded"}]},
                {"type": "relationship_map", "title": "Map", "nodes": [{"title": "Owner", "detail": "Not visibly rendered"}]},
            ]
        }
        visible = pdf_qa.expected_visible_visual_text(spec)
        self.assertIn("Decision evidence", visible)
        self.assertIn("Facts recorded", visible)
        self.assertIn("Owner", visible)
        self.assertNotIn("Not visibly rendered", visible)

    def test_localized_visual_parity_rejects_missing_visuals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "runs" / "course"
            english = run / "docx_pdf"
            localized = run / "localization" / "es-419"
            english.mkdir(parents=True)
            localized.mkdir(parents=True)
            (english / "lesson_04_study_guide_spec_r01.json").write_text(
                '{"visuals":[{"visual_id":"L04V01","type":"process_flow","caption":"Figure 4.1."}]}', encoding="utf-8"
            )
            issues = pdf_qa.localized_visual_parity_issues(
                localized / "lesson_04_study_guide_es_r01.pdf", {"locale": "es", "visuals": []}
            )
            self.assertTrue(issues)

    def test_localized_visual_placement_rejects_a_figure_after_its_next_section(self) -> None:
        pages = [
            "Seção 01: Primeiro\nTexto.",
            "Seção 02: Segundo\nTexto.\nFigura 2.1: Diagrama localizado.",
        ]
        issues = pdf_qa.localized_visual_placement_issues(
            pages,
            {
                "locale": "pt_br",
                "visuals": [
                    {
                        "visual_id": "L02V01",
                        "after_heading": "Seção 01: Primeiro",
                        "caption": "Figura 2.1: Diagrama localizado.",
                    }
                ],
            },
        )
        self.assertTrue(issues)

    def test_content_page_range(self) -> None:
        sequence = {"section_01": 4, "summary": 10}
        self.assertEqual(list(pdf_qa.content_page_range(sequence, 12)), [4, 5, 6, 7, 8, 9])

    def test_markdown_marker_detection_is_literal(self) -> None:
        self.assertTrue(pdf_qa.has_unrendered_markdown("Field Note: headline.** Body"))
        self.assertTrue(pdf_qa.has_unrendered_markdown("| Item | Amount |\n|---|---:|"))
        self.assertFalse(pdf_qa.has_unrendered_markdown("Field Note headline. Body"))

    def test_broken_currency_wrap_is_rejected(self) -> None:
        self.assertEqual([(1, "$12,0 / 00")], pdf_qa.broken_currency_wraps(["Valor\n$12,0\n00\nInclusões"]))
        self.assertEqual([], pdf_qa.broken_currency_wraps(["Markup $17.713,50\n10% da base"]))

    def test_single_table_row_before_page_break_is_orphaned(self) -> None:
        markdown = (
            "| Item | Valor |\n|---|---:|\n"
            "| Supervisão e coordenação do local | $12,000 |\n"
            "| Proteção temporária e utilidades | $3,800 |\n"
            "| Mobilização e entregas | $2,700 |\n"
        )
        pages = [
            "Item Valor\nSupervisão e coordenação do local $12,000",
            "Item Valor\nProteção temporária e utilidades $3,800\nMobilização e entregas $2,700",
        ]
        self.assertEqual(
            ["table 1 leaves one body row on page 1"],
            pdf_qa.table_orphan_row_issues(pages, markdown),
        )


if __name__ == "__main__":
    unittest.main()
