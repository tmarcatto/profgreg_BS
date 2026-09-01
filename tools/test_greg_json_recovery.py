#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_live_production.py"

spec = importlib.util.spec_from_file_location("greg_live_production_json_recovery", MODULE_PATH)
assert spec and spec.loader
production = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = production
spec.loader.exec_module(production)


class JsonRecoveryTests(unittest.TestCase):
    def test_malformed_json_is_repaired_with_the_original_output(self) -> None:
        responses = ['{"sources":[{"title":"A"} {"title":"B"}]}', '{"sources":[{"title":"A"},{"title":"B"}]}']
        with patch.object(production, "request_text", side_effect=responses) as request:
            result = production.request_json_with_retry("course", "source_research", "Research sources", max_tokens=2000, web_search=True)

        self.assertEqual(["A", "B"], [item["title"] for item in result["sources"]])
        self.assertEqual(2, request.call_count)
        repair_prompt = request.call_args_list[1].args[2]
        self.assertIn("Repair the malformed JSON object", repair_prompt)
        self.assertIn(responses[0], repair_prompt)
        self.assertFalse(request.call_args_list[1].kwargs["web_search"])

    def test_recovery_regenerates_after_a_failed_repair(self) -> None:
        responses = ['{"a":1 "b":2}', '{"a":1 "b":2}', '{"a":1,"b":2}']
        with patch.object(production, "request_text", side_effect=responses) as request:
            result = production.request_json_with_retry("course", "source_research", "Original task", max_tokens=2000)

        self.assertEqual({"a": 1, "b": 2}, result)
        self.assertEqual(3, request.call_count)
        self.assertIn("Regenerate the complete result", request.call_args_list[2].args[2])

    def test_missing_json_object_uses_the_same_recovery_path(self) -> None:
        responses = ["I could not complete the structured response.", '{"sources":[]}']
        with patch.object(production, "request_text", side_effect=responses) as request:
            result = production.request_json_with_retry("course", "source_research", "Research sources", max_tokens=2000)

        self.assertEqual({"sources": []}, result)
        self.assertEqual(2, request.call_count)
        self.assertIn("Repair the malformed JSON object", request.call_args_list[1].args[2])

    def test_provider_response_without_final_text_regenerates_without_web_search(self) -> None:
        responses = [
            production.ModelRequestError("OpenAI returned no text content (status='completed')."),
            '{"sources":[]}',
        ]
        with patch.object(production, "request_text", side_effect=responses) as request:
            result = production.request_json_with_retry(
                "course", "source_research", "Research sources", max_tokens=2000, web_search=True
            )

        self.assertEqual({"sources": []}, result)
        self.assertEqual(2, request.call_count)
        self.assertFalse(request.call_args_list[1].kwargs["web_search"])


class VisualDecisionEvidenceTests(unittest.TestCase):
    def test_old_visual_plan_requires_conscious_reaudit(self) -> None:
        old_plan = {"visuals": [{"visual_id": "L07V01", "visual_type": "deterministic-diagram"}]}
        self.assertFalse(production.visual_plan_has_decision_evidence(old_plan))

    def test_complete_visual_decision_record_is_reusable(self) -> None:
        current_plan = {"visuals": [{
            "visual_id": "L07V01",
            "pedagogical_strategy": "explain-with-diagram",
            "real_example_importance": "not-needed",
            "generation_suitability": "safe",
            "evidence_considered": [{"locator": "course map", "relevance": "Shows the dependency."}],
            "alternatives_considered": ["comparison matrix"],
            "selection_reason": "A process diagram makes the required dependency visible to learners.",
        }]}
        self.assertTrue(production.visual_plan_has_decision_evidence(current_plan))


class TargetedRevisionRecoveryTests(unittest.TestCase):
    DRAFT = """# Introduction

Intro stays fixed.

## Learning Objectives

- Original objective.

# Section 01 - Communicate

Original section.

# Summary and Key Takeaways

Original summary.

# Glossary

- Term: definition.

# References

- Source.
"""

    def test_learning_objectives_are_an_editable_named_section(self) -> None:
        sections = production.editable_study_guide_sections(self.DRAFT)
        self.assertIn("## Learning Objectives", sections)
        self.assertNotIn("# Introduction", sections)
        self.assertNotIn("# References", sections)

    def test_targeted_revision_retries_an_out_of_scope_patch_set(self) -> None:
        responses = [
            {"headings": ["## Learning Objectives"]},
            {"patches": [{"heading": "# Introduction", "markdown": "# Introduction\n\nChanged."}]},
            {"patches": [{"heading": "## Learning Objectives", "markdown": "## Learning Objectives\n\nA short orientation.\n\n- Revised objective."}]},
        ]
        with patch.object(production, "request_json_with_retry", side_effect=responses) as request:
            revised = production.targeted_study_guide_revision(
                "course", self.DRAFT, "Add an orientation sentence.", "", level="intermediate"
            )

        self.assertEqual(3, request.call_count)
        self.assertIn("A short orientation.", revised)
        self.assertIn("Intro stays fixed.", revised)

    def test_targeted_revision_falls_back_to_plain_markdown_for_large_invalid_json(self) -> None:
        responses = [
            {"headings": ["# Section 01 - Communicate"]},
            production.ModelRequestError("The model returned invalid JSON after recovery"),
        ]
        replacement = "# Section 01 - Communicate\n\nA concise corrected section."
        with (
            patch.object(production, "request_json_with_retry", side_effect=responses),
            patch.object(production, "request_text", return_value=replacement) as request,
        ):
            revised = production.targeted_study_guide_revision(
                "course", self.DRAFT, "Make the section concise.", "", level="intermediate"
            )

        self.assertEqual(1, request.call_count)
        self.assertIn("A concise corrected section.", revised)
        self.assertIn("Intro stays fixed.", revised)

    def test_large_selected_source_uses_plain_markdown_without_json_patch_attempt(self) -> None:
        large_draft = self.DRAFT.replace("Original section.", "Field detail. " * 1200)
        replacement = "# Section 01 - Communicate\n\nA concise corrected section."
        with (
            patch.object(
                production,
                "request_json_with_retry",
                return_value={"headings": ["# Section 01 - Communicate"]},
            ) as request_json,
            patch.object(production, "request_text", return_value=replacement) as request_text,
        ):
            revised = production.targeted_study_guide_revision(
                "course", large_draft, "Make the section concise.", "", level="intermediate"
            )

        self.assertEqual(1, request_json.call_count)
        self.assertEqual(1, request_text.call_count)
        self.assertIn("A concise corrected section.", revised)


class LessonSourceMergeTests(unittest.TestCase):
    def test_research_passes_merge_distinct_authorities_and_use_later_gap_state(self) -> None:
        earlier = {
            "sources": [
                {"source_id": "L09S01", "title": "Government Guide", "url": "https://example.gov/guide"},
                {"source_id": "L09S02", "title": "Industry Practice", "url": "https://example.org/practice"},
            ],
            "research_log": ["First search"],
            "source_gaps": ["Need a formal technical authority"],
        }
        later = {
            "sources": [
                {"source_id": "L09S01", "title": "Formal Standard", "formal_reference": "Formal Standard 2026"},
            ],
            "research_log": ["Focused authority search"],
            "source_gaps": [],
        }

        merged = production.merge_lesson_source_research(earlier, later, 9)

        self.assertEqual(3, len(merged["sources"]))
        self.assertEqual(["L09S01", "L09S02", "L09S03"], [source["source_id"] for source in merged["sources"]])
        self.assertEqual([], merged["source_gaps"])
        self.assertEqual(["First search", "Focused authority search"], merged["research_log"])


if __name__ == "__main__":
    unittest.main()
