#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_visual_plan_check.py"

spec = importlib.util.spec_from_file_location("greg_visual_plan_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_visual_plan_check"] = checker
spec.loader.exec_module(checker)


class VisualPlanCheckTests(unittest.TestCase):
    def test_clean_deck_plan_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "visual_plan.json"
            path.write_text(
                json.dumps(
                    {
                        "artifact_type": "deck",
                        "visuals": [
                            {
                                "visual_id": "V01",
                                "visual_type": "generated-conceptual-image",
                                "slide": 2,
                                "purpose": "Shows a real-world contract review setting without pretending to be a sourced project.",
                                "learning_claim": "Contracts become useful when project teams connect the document to daily field decisions.",
                                "source_status": "generated-fallback",
                                "generated": True,
                                "max_area_percent": 45,
                                "context_focus": "U.S. residential construction",
                                "depicts_people": True,
                                "workforce_representation": "Respectfully represents American-born and immigrant construction workers.",
                                "pedagogical_strategy": "orient-with-conceptual-image",
                                "real_example_importance": "not-needed",
                                "generation_suitability": "safe",
                                "evidence_considered": [{"source_type": "course-map", "locator": "Lesson 1 visual strategy"}],
                                "alternatives_considered": ["trusted source photo"],
                                "selection_reason": "A conceptual scene safely establishes the decision context.",
                            },
                            {
                                "visual_id": "V02",
                                "visual_type": "deterministic-diagram",
                                "slide": 4,
                                "purpose": "Compares the responsibilities of project management and contract management.",
                                "learning_claim": "Project management coordinates work while contract management controls rights obligations and records.",
                                "source_status": "not-required",
                                "diagram_type": "comparison-matrix",
                                "diagram_rationale": "A comparison matrix directly contrasts the two responsibility systems.",
                                "context_focus": "U.S. residential construction",
                                "internal_text": True,
                                "internal_text_position": "inside",
                                "pedagogical_strategy": "explain-with-diagram",
                                "real_example_importance": "not-needed",
                                "generation_suitability": "safe",
                                "evidence_considered": [{"source_type": "course-map", "locator": "Lesson 1 visual strategy"}],
                                "alternatives_considered": ["two-column prose"],
                                "selection_reason": "The shared attributes require a direct visual comparison.",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = checker.run_checks(path)
            self.assertTrue(result["passed"])

    def test_repeated_learning_claim_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "visual_plan.json"
            claim = "The same project can need different estimates as information matures."
            path.write_text(
                json.dumps(
                    {
                        "artifact_type": "study-guide",
                        "visuals": [
                            {"visual_id": "A", "visual_type": "deterministic-diagram", "placement": "section 1", "purpose": "Shows estimate maturity across phases.", "learning_claim": claim, "source_status": "not-required", "context_focus": "U.S. residential construction", "diagram_type": "process-flow", "diagram_rationale": "A process flow shows how estimate information matures across phases."},
                            {"visual_id": "B", "visual_type": "deterministic-diagram", "placement": "section 2", "purpose": "Repeats estimate maturity across phases.", "learning_claim": claim, "source_status": "not-required", "context_focus": "U.S. residential construction", "diagram_type": "process-flow", "diagram_rationale": "A process flow shows the repeated sequence across project phases."},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = checker.run_checks(path)
            self.assertFalse(result["passed"])
            self.assertTrue(any(item["check"] == "visual_mece" and item["status"] == "fail" for item in result["findings"]))

    def test_comparison_matrix_fails_for_lifecycle_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "visual_plan.json"
            path.write_text(json.dumps({"artifact_type":"study-guide","visuals":[{"visual_id":"V1","visual_type":"deterministic-diagram","placement":"Section 01","purpose":"Shows the lifecycle sequence from preconstruction to closeout.","learning_claim":"Residential project phases follow a connected handoff sequence.","source_status":"not-required","context_focus":"U.S. residential construction","diagram_type":"comparison-matrix","diagram_rationale":"This mechanism was selected to display the project phases clearly."}]}), encoding="utf-8")
            result = checker.run_checks(path)
            self.assertFalse(result["passed"])
            self.assertTrue(any(item["check"] == "diagram_mechanism_fit" and item["status"] == "fail" for item in result["findings"]))

    def test_generated_deck_caption_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "visual_plan.json"
            path.write_text(
                json.dumps(
                    {
                        "artifact_type": "deck",
                        "visuals": [
                            {
                                "visual_id": "G",
                                "visual_type": "generated-conceptual-image",
                                "slide": 2,
                                "purpose": "Adds context to the construction office scenario.",
                                "learning_claim": "Estimating work depends on interpreting project information before pricing.",
                                "source_status": "generated-fallback",
                                "generated": True,
                                "max_area_percent": 40,
                                "context_focus": "U.S. residential construction",
                                "caption": "Generated image of an estimating desk.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = checker.run_checks(path)
            self.assertFalse(result["passed"])

    def test_diagram_visible_capacity_fails_before_renderer_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "visual_plan.json"
            path.write_text(
                json.dumps(
                    {
                        "artifact_type": "study-guide",
                        "visuals": [
                            {
                                "visual_id": "V1",
                                "visual_type": "deterministic-diagram",
                                "placement": "Section 01",
                                "purpose": "Shows the complete residential project lifecycle.",
                                "learning_claim": "Six visible phases carry the project from lead through warranty.",
                                "source_status": "not-required",
                                "context_focus": "U.S. residential construction",
                                "diagram_type": "process-flow",
                                "diagram_rationale": "A process flow shows the ordered lifecycle and its handoffs.",
                                "diagram_nodes": [{"title": f"Phase {number}", "detail": "Short detail"} for number in range(1, 8)],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = checker.run_checks(path)
            self.assertFalse(result["passed"])
            self.assertTrue(any(item["check"] == "diagram_visible_capacity" and item["status"] == "fail" for item in result["findings"]))

    def test_deck_renderer_mechanisms_are_accepted_by_visual_qa(self) -> None:
        for mechanism in ("planned-actual", "paired-record-rows", "verification-checklist"):
            with self.subTest(mechanism=mechanism), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "visual_plan.json"
                path.write_text(
                    json.dumps(
                        {
                            "artifact_type": "deck",
                            "visuals": [
                                {
                                    "visual_id": "V1",
                                    "visual_type": "deterministic-diagram",
                                    "placement": "slide 2",
                                    "purpose": "Teaches a distinct residential field decision clearly.",
                                    "learning_claim": "Learners connect documented conditions to the correct field response.",
                                    "source_status": "not-required",
                                    "context_focus": "U.S. residential construction",
                                    "diagram_type": mechanism,
                                    "diagram_rationale": "This renderer mechanism directly supports the stated field decision.",
                                    "pedagogical_strategy": "explain-with-diagram",
                                    "real_example_importance": "not-needed",
                                    "generation_suitability": "safe",
                                    "evidence_considered": [{"source_type": "course-map", "locator": "Lesson visual strategy"}],
                                    "alternatives_considered": ["A photograph would hide the decision relationship."],
                                    "selection_reason": "The structured visual makes the decision relationship explicit.",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                result = checker.run_checks(path)
                self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()
