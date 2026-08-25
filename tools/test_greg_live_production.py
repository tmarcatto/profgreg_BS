#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_live_production.py"
spec = importlib.util.spec_from_file_location("greg_live_production", MODULE_PATH)
production = importlib.util.module_from_spec(spec)
sys.modules["greg_live_production"] = production
assert spec and spec.loader
spec.loader.exec_module(production)


class GregLiveProductionTests(unittest.TestCase):
    def test_study_guide_revision_is_shared_across_draft_and_pdf(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "lesson_draft").mkdir()
            (run / "docx_pdf").mkdir()
            (run / "lesson_draft" / "lesson_01_draft_r01.md").write_text("x")
            (run / "docx_pdf" / "lesson_01_study_guide_r03.pdf").write_bytes(b"pdf")
            self.assertEqual(4, production.next_study_guide_revision(run, "lesson_01"))

    def test_revision_prompt_edits_existing_draft_instead_of_starting_over(self) -> None:
        prompt = production.study_guide_revision_prompt(
            "# Existing\nKeep this.", "Fix one phrase.", "# References\n- Source", attempt=2
        )
        self.assertIn("Preserve all compliant content", prompt)
        self.assertIn("# Existing\nKeep this.", prompt)
        self.assertIn("Fix one phrase.", prompt)
        self.assertIn("Revision attempt: 2", prompt)
        self.assertIn("must not exceed 5,400 words", prompt)

        advanced = production.study_guide_revision_prompt(
            "# Existing", "Complete the ending.", "# References", attempt=1, level="Advanced"
        )
        self.assertIn("must not exceed 6,200 words", advanced)

    def test_lesson_source_refresh_requires_full_technical_authority(self) -> None:
        weak = {
            "source_gaps": [],
            "sources": [
                {"content_depth": "supporting-summary", "claims_supported": [{}], "currency_validation": {"status": "validated-current"}}
                for _ in range(3)
            ],
        }
        strong = {
            **weak,
            "sources": [
                *weak["sources"],
                {"content_depth": "formal-publication", "claims_supported": [{"claim": "x"}], "currency_validation": {"status": "validated-current"}},
            ],
        }
        self.assertFalse(production.lesson_sources_are_adequate(weak))
        self.assertTrue(production.lesson_sources_are_adequate(strong))

    def test_student_reference_removes_chapter_and_page_locators(self) -> None:
        source = {
            "formal_reference": (
                "International Code Council. 2024 International Residential Code for One- and Two-Family "
                "Dwellings, Chapter 1: Scope and Administration. International Code Council, 2024."
            ),
            "source_type": "code",
            "url": "",
        }
        reference = production.student_reference_for_source(source)
        self.assertEqual(
            "International Code Council. 2024 International Residential Code for One- and Two-Family Dwellings. International Code Council, 2024.",
            reference,
        )

    def test_visual_plan_prompt_requires_highlight_reason(self) -> None:
        seed = type("Seed", (), {"title": "Course"})()
        lesson = {"lesson_number": 1, "title": "Lesson"}
        prompt = production.visual_plan_prompt(seed, lesson, "# Section 01 - Start", [])
        self.assertIn('"highlight_reason"', prompt)
        self.assertIn("lesson-emphasis", prompt)
        self.assertIn("process-flow: 2-6 nodes", prompt)
        self.assertIn("must agree exactly", prompt)

    def test_visual_semantic_review_checks_visible_omissions(self) -> None:
        seed = type("Seed", (), {"title": "Course"})()
        lesson = {"lesson_number": 1, "title": "Lesson"}
        prompt = production.visual_semantic_review_prompt(seed, lesson, "# Section 01 - Start", {"visuals": []})
        self.assertIn("promised lifecycle endpoint", prompt)
        self.assertIn("hidden extra nodes or rows", prompt)
        self.assertIn("material learner-visible error", prompt)
        self.assertIn("minor editorial preferences are non-blocking", prompt)

    def test_render_spec_fingerprint_changes_with_visuals(self) -> None:
        base = {"source_markdown": "lesson.md", "visuals": [{"title": "One"}]}
        changed = {"source_markdown": "lesson.md", "visuals": [{"title": "Two"}]}
        self.assertEqual(production.render_spec_fingerprint(base), production.render_spec_fingerprint(dict(base)))
        self.assertNotEqual(production.render_spec_fingerprint(base), production.render_spec_fingerprint(changed))

    def test_render_spec_fingerprint_changes_with_renderer(self) -> None:
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            renderer = Path(directory) / "renderer.py"
            renderer.write_text("version one", encoding="utf-8")
            with patch.object(production, "STUDY_GUIDE_RENDERER", renderer):
                first = production.render_spec_fingerprint({"source_markdown": "lesson.md"})
                renderer.write_text("version two", encoding="utf-8")
                second = production.render_spec_fingerprint({"source_markdown": "lesson.md"})
        self.assertNotEqual(first, second)

    def test_citation_review_separates_prose_from_bibliography(self) -> None:
        seed = type("Seed", (), {"title": "Course"})()
        lesson = {"lesson_number": 1, "title": "Lesson"}
        prompt = production.reviewer_prompt("citation_review", seed, lesson, "# References\n- Work.", {"sources": []})
        self.assertIn("after the final `# References` heading", prompt)
        self.assertIn("teaching prose is not a bibliography defect", prompt)

    def test_visual_retry_reuses_frozen_passed_content_review(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "review").mkdir()
            (run / "review" / "lesson_01_visual_qa.md").write_text("Visual plan QA passed: no\n")
            for suffix in ("pedagogy_review", "citation_review", "design_qa"):
                (run / "review" / f"lesson_01_{suffix}_r01.md").write_text("## Verdict\n\nPASS\n")
            self.assertTrue(production.reviewed_draft_can_resume_visuals(run, "lesson_01", 1))
            (run / "review" / "lesson_01_visual_qa.md").write_text("Visual plan QA passed: yes\n")
            self.assertTrue(production.reviewed_draft_can_resume_visuals(run, "lesson_01", 1))

    def test_student_reference_text_removes_access_dates(self) -> None:
        text = production.student_reference_text(
            "Occupational Safety and Health Administration. Safety and Health Regulations for Construction. Current online edition accessed August 16, 2026."
        )
        self.assertNotIn("accessed", text.lower())
        self.assertIn("Current online edition.", text)

    def test_forced_references_keep_summary_bullet_only_and_normalize_osha_title(self) -> None:
        draft = "# Summary and Key Takeaways\n\nReview this first.\n\n- Keep this point.\n\n# Glossary\n\nTerm"
        references = "# References\n\n- Occupational Safety and Health Administration. (2016). Construction (OSHA Publication 3886)."
        normalized = production.force_student_references(draft, references)
        self.assertNotIn("Review this first.", normalized)
        self.assertIn("- Keep this point.", normalized)
        self.assertIn("Recommended Practices for Safety and Health Programs in Construction", normalized)

    def test_forced_references_replace_localized_reference_section_without_duplicate(self) -> None:
        draft = "# Resumo e Principais Conclusões\n\n- Um.\n- Dois.\n- Três.\n- Quatro.\n\n# Referências\n\n- Saída do modelo."
        normalized = production.force_student_references(draft, "# References\n\n- Fonte validada.", "pt_br")
        self.assertEqual(1, normalized.count("# Referências"))
        self.assertNotIn("# References", normalized)
        self.assertNotIn("Saída do modelo", normalized)
        self.assertIn("Fonte validada", normalized)

    def test_visual_cards_are_lesson_specific(self) -> None:
        cards = production.visual_cards_from_lesson(
            {"sections": ["Project lifecycle phases", "PM responsibilities vs field leadership", "Stakeholder expectations", "Jobsite vocabulary"]}
        )
        titles = [card["title"] for card in cards]
        self.assertIn("Project lifecycle phases", titles)
        self.assertIn("PM responsibilities vs field leadership", titles)
        self.assertNotIn("Identify", titles)

    def test_role_document_is_not_escalated_to_operator(self) -> None:
        visual = {
            "visual_type": "trusted-source-image",
            "purpose": "show a real residential superintendent job description",
            "learning_claim": "The PM role includes repeatable coordination duties",
            "core_message_depends_on_real_example": True,
            "technical_fidelity_required": True,
        }
        normalized = production.normalize_visual_strategy(visual)
        self.assertEqual(normalized["visual_type"], "deterministic-diagram")
        self.assertFalse(production.technical_visual_requires_operator(normalized))

    def test_actual_floor_plan_can_require_operator_source(self) -> None:
        visual = {
            "visual_type": "trusted-source-image",
            "purpose": "inspect an actual residential floor plan",
            "learning_claim": "A floor plan communicates walls openings and dimensions",
            "technical_object_type": "floor plan",
            "core_message_depends_on_real_example": True,
            "technical_fidelity_required": True,
        }
        self.assertTrue(production.technical_visual_requires_operator(visual))
        self.assertEqual(production.normalize_visual_strategy(visual)["visual_type"], "trusted-source-image")

    def test_callout_normalization_keeps_four_and_preserves_excess_body(self) -> None:
        draft = "\n\n".join(
            [
                "> **KEY TERM**\n> First definition.",
                "> **KEY TERM**\n> Second definition.",
                "> **KEY TERM**\n> Third definition.",
                "> **SCENARIO**\n> A field situation.",
                "> **HANDS-ON EXAMPLE**\n> A worked example.",
                "> **BRIDGE**\n> The next connection.",
            ]
        )
        normalized = production.normalize_callout_density(draft)
        self.assertEqual(normalized.count("> **"), 4)
        self.assertIn("First definition.", normalized)
        self.assertIn("Second definition.", normalized)
        self.assertIn("> **SCENARIO**", normalized)
        self.assertIn("> **HANDS-ON EXAMPLE**", normalized)


if __name__ == "__main__":
    unittest.main()
