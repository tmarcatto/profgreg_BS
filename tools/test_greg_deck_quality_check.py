#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_deck_quality_check.py"

spec = importlib.util.spec_from_file_location("greg_deck_quality_check", MODULE_PATH)
assert spec and spec.loader
deck_qa = importlib.util.module_from_spec(spec)
sys.modules["greg_deck_quality_check"] = deck_qa
spec.loader.exec_module(deck_qa)


class DeckQualityCheckTests(unittest.TestCase):
    def test_similarity_flags_repeated_text(self) -> None:
        a = deck_qa.normalize_tokens("Document facts, dates, impacts, approvals, and requested action.")
        b = deck_qa.normalize_tokens("Document dates, facts, impacts, approvals, and the requested decision.")
        self.assertGreaterEqual(deck_qa.jaccard(a, b), 0.34)

    def test_similarity_allows_distinct_slides(self) -> None:
        a = deck_qa.normalize_tokens("Field requests should move through the contract process.")
        b = deck_qa.normalize_tokens("Good documentation makes decisions traceable.")
        self.assertLess(deck_qa.jaccard(a, b), 0.22)

    def test_function_classifier_distinguishes_sequence_and_trigger(self) -> None:
        sequence = deck_qa.classify_slide_function("A contract-aware PM builds five preventive habits. Read. Translate. Document.")
        trigger = deck_qa.classify_slide_function("Escalate when the issue leaves normal project control.")
        self.assertEqual(sequence, "sequence")
        self.assertEqual(trigger, "decision_trigger")

    def test_missing_inspect_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deck = Path(tmp) / "lesson_01_deck_r02.pptx"
            qa = Path(tmp) / "lesson_01_deck_qa.md"
            deck.write_bytes(b"placeholder")
            qa.write_text("MECE\nlast-item\nhighlight\nvisually rechecked\nlesson_01_deck_r02.pptx\n", encoding="utf-8")
            result = deck_qa.run_checks(deck, qa)
            self.assertFalse(result["passed"])
            self.assertGreaterEqual(result["fail_count"], 1)

    def test_bbox_intersection(self) -> None:
        self.assertTrue(deck_qa.intersects((0, 0, 100, 100), (50, 50, 100, 100)))
        self.assertFalse(deck_qa.intersects((0, 0, 20, 20), (30, 30, 20, 20)))

    def test_brand_and_background_detection(self) -> None:
        self.assertTrue(deck_qa.is_brand_or_background({"name": "footer-course"}))
        self.assertTrue(deck_qa.is_brand_or_background({"name": "left-navy"}))
        self.assertTrue(deck_qa.is_brand_or_background({"alt": "BuildStak negative wordmark"}))
        self.assertFalse(deck_qa.is_brand_or_background({"name": "content-card"}))

    def test_text_capacity_warning_flags_dense_box(self) -> None:
        warning = deck_qa.text_capacity_warning(
            {
                "slide": 4,
                "name": "tight-body",
                "text": "This is a very long line of teaching text that cannot reasonably fit inside the tiny box.",
                "bbox": [100, 100, 120, 20],
                "resolvedFontSize": 20,
            }
        )
        self.assertIsNotNone(warning)

    def test_text_capacity_warning_allows_reasonable_box(self) -> None:
        warning = deck_qa.text_capacity_warning(
            {
                "slide": 4,
                "name": "body",
                "text": "Readable teaching text.",
                "bbox": [100, 100, 420, 60],
                "resolvedFontSize": 18,
            }
        )
        self.assertIsNone(warning)

    def test_text_capacity_warning_flags_a_second_line_in_a_single_line_box(self) -> None:
        warning = deck_qa.text_capacity_warning(
            {
                "slide": 4,
                "name": "row-1-body",
                "text": "Identify the legal parties, project or property, and people authorized to approve work or changes.",
                "bbox": [432, 248, 704, 26],
                "resolvedFontSize": 19,
            }
        )
        self.assertIsNotNone(warning)

    def test_rendered_line_fit_flags_actual_wrapping_beyond_box_height(self) -> None:
        warning = deck_qa.rendered_line_fit_warning(
            {
                "slide": 8,
                "name": "bullet-1",
                "text": "Texto traduzido que ocupa três linhas.",
                "bbox": [106, 338, 524, 58],
                "textLayout": {"lineCount": 3},
                "paragraphs": [{"resolvedTextStyle": {"fontSize": 21}}],
            }
        )
        self.assertIsNotNone(warning)

    def test_rendered_line_fit_allows_two_lines_in_expanded_row(self) -> None:
        row = {
            "slide": 5,
            "name": "row-1-body",
            "text": "Texto legível em duas linhas.",
            "bbox": [432, 234, 704, 48],
            "textLayout": {"lineCount": 2},
            "paragraphs": [{"resolvedTextStyle": {"fontSize": 17}}],
        }
        warning = deck_qa.rendered_line_fit_warning(
            row,
            [row, {"slide": 5, "name": "row-1-bar", "bbox": [104, 224, 1068, 68]}],
        )
        self.assertIsNone(warning)

    def test_rendered_line_fit_flags_text_beyond_visible_row_container(self) -> None:
        row = {
            "slide": 5,
            "name": "row-1-body",
            "text": "Texto que se divide en dos líneas.",
            "bbox": [432, 248, 704, 26],
            "textLayout": {"lineCount": 2},
            "paragraphs": [{"resolvedTextStyle": {"fontSize": 19}}],
        }
        warning = deck_qa.rendered_line_fit_warning(
            row,
            [row, {"slide": 5, "name": "row-1-bar", "bbox": [104, 236, 1068, 52]}],
        )
        self.assertIsNotNone(warning)

    def test_revisioned_render_directory_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deck = Path(tmp) / "lesson_04_deck_es_r02.pptx"
            rendered = Path(tmp) / "rendered_slides_lesson_04_r02"
            rendered.mkdir()
            self.assertEqual(rendered, deck_qa.rendered_slide_dir_for(deck))

    def test_missing_fit_metadata_fails_a_rendered_deck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deck = Path(tmp) / "lesson_03_deck_r01.pptx"
            qa = Path(tmp) / "lesson_03_deck_qa_r01.md"
            deck.write_bytes(b"placeholder")
            qa.write_text("MECE\nlast-item\nhighlight\nvisually rechecked\nlesson_03_deck_r01.pptx\n", encoding="utf-8")
            inspect = deck_qa.inspect_path_for(deck)
            rows = [{"kind": "slide", "slide": number} for number in range(1, 11)]
            rows.extend(
                {"kind": "textbox", "slide": number, "name": "card-body", "text": "A sufficiently long text box without recorded fit metadata.", "bbox": [100, 100, 250, 50]}
                for number in range(1, 11)
            )
            inspect.write_text("\n".join(__import__("json").dumps(row) for row in rows) + "\n", encoding="utf-8")
            result = deck_qa.run_checks(deck, qa)
            self.assertFalse(result["passed"])
            self.assertTrue(any(item["check"] == "text_box_density" and item["status"] == "fail" for item in result["findings"]))


if __name__ == "__main__":
    unittest.main()
