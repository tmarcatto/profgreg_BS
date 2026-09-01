#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_course_map_quality_check.py"

spec = importlib.util.spec_from_file_location("greg_course_map_quality_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_course_map_quality_check"] = checker
spec.loader.exec_module(checker)


class CourseMapQualityCheckTests(unittest.TestCase):
    def test_detects_lesson_titles_from_intake(self) -> None:
        text = "### Lesson 1: Foundations\n### Lesson 2: Takeoff\n"
        self.assertEqual(checker.lesson_titles_from_intake(text), ["Foundations", "Takeoff"])

    def test_adapted_course_map_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course_json = root / "course_map.json"
            course_md = root / "course_map.md"
            log = root / "syllabus_adaptation_log.md"
            intake = root / "intake.md"
            course_json.write_text(
                json.dumps(
                    {
            "level": "Basic",
            "visual_decision_protocol_version": 2,
                        "target_audience": "Residential construction workers in the United States",
                        "sector_anchor": "Residential construction first.",
                        "approval_status": "autonomously_approved",
                        "scope_rationale": "The 10-lesson structure is appropriate for the level and lesson count rationale.",
                        "syllabus_adaptations": [
                            {"lesson": 1, "decision": "reframed", "rationale": "The lesson needs clearer PM framing for beginner learners."}
                        ],
                        "lessons": [{"lesson_number": 1, "title": "Foundations Reframed", "visual_insertions": [
                            {"placement_hint": "after section one", "learning_job": "Show how approved information becomes field action", "pedagogical_strategy": "explain-with-diagram", "real_example_importance": "not-needed", "generation_suitability": "safe", "recommended_form": "process-flow", "must_show": ["approved input", "field action"], "source_strategy": "deterministic", "targeted_search_query": "official construction workflow visual", "evidence_considered": [{"source_type": "authoritative-web", "locator": "https://example.com/one"}], "alternatives_considered": ["conceptual image"], "selection_reason": "A flow directly explains the ordered transformation."},
                            {"placement_hint": "after section two", "learning_job": "Show who coordinates the residential project team", "pedagogical_strategy": "explain-with-diagram", "real_example_importance": "not-needed", "generation_suitability": "safe", "recommended_form": "relationship-map", "must_show": ["project manager", "trade leads"], "source_strategy": "deterministic", "targeted_search_query": "official construction coordination relationship map", "evidence_considered": [{"source_type": "authoritative-web", "locator": "https://example.com/two"}], "alternatives_considered": ["table"], "selection_reason": "A relationship map directly exposes coordination connections."},
                        ]}],
                        "qa": {"approval_status": "approved"},
                    }
                ),
                encoding="utf-8",
            )
            course_md.write_text("## 9. Source Needs by Lesson\nAIA and AGC authority. Practitioner-context source opportunities. Residential examples first.\n", encoding="utf-8")
            log.write_text(
                "The user-provided syllabus was treated as an initial direction, not as a fixed contract.\n\n"
                "| Input item | Decision | Course Map result | Rationale |\n|---|---|---|---|\n"
                "| Lesson 1 | reframed | Foundations Reframed | Clearer PM framing for beginners. |\n",
                encoding="utf-8",
            )
            intake.write_text("### Lesson 1: Foundations\n", encoding="utf-8")
            result = checker.run_checks(course_json, course_md, log, intake)
            self.assertTrue(result["passed"])

    def test_missing_adaptation_log_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course_json = root / "course_map.json"
            course_md = root / "course_map.md"
            log = root / "syllabus_adaptation_log.md"
            course_json.write_text(json.dumps({"lessons": [{"title": "A"}]}), encoding="utf-8")
            course_md.write_text("", encoding="utf-8")
            result = checker.run_checks(course_json, course_md, log)
            self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
