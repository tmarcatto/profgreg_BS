#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_study_guide_content_check.py"

spec = importlib.util.spec_from_file_location("greg_study_guide_content_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_study_guide_content_check"] = checker
spec.loader.exec_module(checker)


class StudyGuideContentCheckTests(unittest.TestCase):
    def test_clean_callout_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text(
                "# Intro\n\n# Section 01 - One\n\nBody text.\n\n> **KEY TERM**\n>\n> Contract: a project rule.\n\nMore text.\n\n> **SCENARIO**\n>\n> A residential example.\n\n# Section 02 - Two\n\nBody text.\n\n# Section 03 - Three\n\nBody text.\n\n# Section 04 - Four\n\nBody text.\n\n# Summary and Key Takeaways\n\n- First takeaway.\n- Second takeaway.\n- Third takeaway.\n- Fourth takeaway.\n\n# References\n\n- American Institute of Architects. AIA Contract Documents.\n",
                encoding="utf-8",
            )
            result = checker.run_checks(path)
            self.assertTrue(result["passed"])

    def test_callout_in_references_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text("# References\n\n> **KEY TERM**\n>\n> Bad placement.\n", encoding="utf-8")
            result = checker.run_checks(path)
            self.assertFalse(result["passed"])

    def test_summary_paragraphs_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text(
                "# Summary and Key Takeaways\n\nThis is a paragraph summary.\n\n# References\n\n- A formal source.\n",
                encoding="utf-8",
            )
            result = checker.run_checks(path)
            finding = next(item for item in result["findings"] if item["check"] == "summary_bullet_structure")
            self.assertEqual(finding["status"], "fail")

    def test_summary_bullets_pass_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text(
                "# Summary and Key Takeaways\n\n- One.\n- Two.\n- Three.\n- Four.\n\n# References\n\n- A formal source.\n",
                encoding="utf-8",
            )
            result = checker.run_checks(path)
            finding = next(item for item in result["findings"] if item["check"] == "summary_bullet_structure")
            self.assertEqual(finding["status"], "pass")

    def test_activity_language_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text("# Section 01 - One\n\nClass activity: discuss this with your group.\n", encoding="utf-8")
            result = checker.run_checks(path)
            self.assertFalse(result["passed"])

    def test_professional_use_of_exercise_is_not_a_learner_activity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text(
                "# Introduction\n\nCourse orientation.\n\n# Section 01 - One\n\n"
                "Design professionals exercise only the authority assigned by contract.\n\n"
                "> **KEY TERM**\n> Contract authority is assigned.\n\n"
                "> **SCENARIO**\n> A designer reviews a substitution.\n\n"
                "# Section 02 - Two\n\nBody.\n\n# Section 03 - Three\n\nBody.\n\n"
                "# Section 04 - Four\n\nBody.\n\n# References\n\n- A formal book.\n",
                encoding="utf-8",
            )
            result = checker.run_checks(path)
            self.assertFalse(any(item["check"] == "no_activities" for item in result["findings"] if item["status"] == "fail"))

    def test_unapproved_callout_heading_and_dash_punctuation_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text("# Introduction\n\nCourse orientation.\n\n# Section 01 - One\n\n### Subheading\n\nText — more text.\n\n> **FIELD NOTE**\n>\n> Not approved.\n\n# References\n\n- A formal book.\n", encoding="utf-8")
            result = checker.run_checks(path)
            failed = {item["check"] for item in result["findings"] if item["status"] == "fail"}
            self.assertTrue({"no_deep_markdown_headings", "no_dash_punctuation", "fixed_callout_vocabulary"}.issubset(failed))

    def test_plain_unapproved_callout_and_fenced_visual_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text(
                "# Introduction\n\nCourse orientation.\n\n# Section 01 - One\n\n> PRACTICAL NOTE: Invented box.\n\n```\n[A] -> [B]\n```\n\n# References\n\n- A formal book.\n",
                encoding="utf-8",
            )
            result = checker.run_checks(path)
            failed = {item["check"] for item in result["findings"] if item["status"] == "fail"}
            self.assertTrue({"fixed_callout_vocabulary", "no_fenced_visual_source"}.issubset(failed))

    def test_intro_target_user_boilerplate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text(
                "# Introduction\n\nThis study guide is written for construction learners working in the United States.\n\n# Section 01 - One\n\nBody text.\n\n# References\n\n- AIA. Contract Documents.\n",
                encoding="utf-8",
            )
            result = checker.run_checks(path)
            self.assertFalse(result["passed"])
            self.assertTrue(any(item["check"] == "course_focused_introduction" for item in result["findings"] if item["status"] == "fail"))

    def test_intermediate_underwritten_draft_fails_depth_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text(
                "# Lesson Roadmap\n\n- One\n- Two\n- Three\n- Four\n\n"
                "## Introduction\n\nCourse intro.\n\n## Learning Objectives\n\n- One\n- Two\n- Three\n- Four\n\n"
                "# Section 01 - One\n\nShort body.\n\n# Section 02 - Two\n\nShort body.\n\n"
                "# Section 03 - Three\n\nShort body.\n\n# Section 04 - Four\n\nShort body.\n\n"
                "# Summary and Key Takeaways\n\n- One\n\n# Glossary\n\n- Term: definition.\n\n"
                "# References\n\n- National Association of Home Builders. Residential Construction Performance Guidelines.\n",
                encoding="utf-8",
            )
            result = checker.run_checks(path, "Intermediate")
            self.assertFalse(result["passed"])
            self.assertTrue(any(item["check"] == "level_depth" for item in result["findings"] if item["status"] == "fail"))


if __name__ == "__main__":
    unittest.main()
