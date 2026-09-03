from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import greg_marketing as marketing


class GregMarketingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.course_map = {
            "course": {"title": "Construction AI Essentials", "target_audience": "U.S. construction professionals."},
            "lessons": [
                {
                    "lesson_number": index,
                    "title": f"Lesson topic {index}",
                    "learning_goal": f"Apply topic {index}.",
                    "sections": [f"Plan topic {index}", f"Practice topic {index}", f"Review topic {index}"],
                }
                for index in range(1, 11)
            ],
        }
        self.marketing = {
            "course_title": "AI for Construction Professionals",
            "short_description": "Use AI to reduce routine work. Make stronger project decisions with practical workflows.",
            "full_description": "Construction teams are managing more information across projects. This course turns the approved learning journey into practical, responsible workflows that support better day-to-day performance and readiness for broader responsibilities.",
            "skills": ["Construction AI", "Prompt Design", "Workflow Automation"],
            "what_you_will_learn": [f"Apply practical workflow {index}." for index in range(1, 6)],
            "requirements": ["Basic construction project experience", "A computer with internet access"],
            "audience": "Project engineers, coordinators, superintendents, estimators, and construction managers.",
            "value_proposition": "Turn AI into a practical construction advantage without losing professional judgment.",
            "career_outcomes": ["Take on more structured project reporting.", "Support stronger coordination across teams.", "Demonstrate readiness for broader digital responsibilities."],
            "market_highlights": ["Construction employers continue to seek digital and analytical capability."],
            "market_sources": [{"organization": "U.S. Bureau of Labor Statistics", "title": "Construction Managers", "url": "https://www.bls.gov/ooh/management/construction-managers.htm", "published": "2026", "claim": "Employment outlook."}],
            "course_journey": [f"Lesson topic {index}" for index in range(1, 11)],
            "call_to_action": "Build a smarter way to work.",
            "landing_page_url": "https://learn.buildstak.com/courses/ai-4-construction-professionals",
        }

    def test_normalize_requires_exactly_three_skills_and_five_outcomes(self) -> None:
        normalized = marketing.normalize_marketing(self.marketing, self.course_map)
        self.assertEqual(3, len(normalized["skills"]))
        self.assertEqual(5, len(normalized["what_you_will_learn"]))
        self.assertEqual(5, len(normalized["how_you_will_learn"]))
        self.assertEqual(10, len(normalized["lesson_details"]))
        self.assertTrue(all(len(item["bullets"]) == 2 for item in normalized["lesson_details"]))
        invalid = {**self.marketing, "skills": ["one", "two"]}
        with self.assertRaisesRegex(ValueError, "exactly 3 skills"):
            marketing.normalize_marketing(invalid, self.course_map)
        invalid_description = {**self.marketing, "short_description": "Only one sentence."}
        with self.assertRaisesRegex(ValueError, "exactly 2 sentences"):
            marketing.normalize_marketing(invalid_description, self.course_map)

    def test_non_https_market_sources_are_not_saved(self) -> None:
        data = {**self.marketing, "market_sources": [{"url": "http://example.com", "claim": "Unsafe"}]}
        normalized = marketing.normalize_marketing(data, self.course_map)
        self.assertEqual([], normalized["market_sources"])

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "pypdf is required for PDF integration checks")
    def test_save_and_render_create_a_five_page_brochure(self) -> None:
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            course = runs / "demo-course"
            (course / "course_map").mkdir(parents=True)
            (course / "course_map" / "course_map.json").write_text(json.dumps(self.course_map), encoding="utf-8")
            with patch.object(marketing, "RUNS", runs):
                saved = marketing.save_marketing("demo-course", self.marketing)
                status = marketing.marketing_status("demo-course")
                pages = PdfReader(str(marketing.brochure_path("demo-course"))).pages
                page_text = [page.extract_text() or "" for page in pages]
                page_five_links = [
                    annotation.get_object()
                    for annotation in (pages[4].get("/Annots") or [])
                    if annotation.get_object().get("/Subtype") == "/Link"
                ]
        self.assertEqual(self.marketing["course_title"], saved["course_title"])
        self.assertTrue(status["brochure_ready"])
        self.assertEqual(5, len(pages))
        self.assertTrue(all(skill in page_text[0] for skill in self.marketing["skills"]))
        self.assertIn("HOW YOU WILL LEARN", page_text[2])
        self.assertIn("Plan topic 1", page_text[3])
        self.assertIn("Practice topic 1", page_text[3])
        self.assertNotIn("Review topic 1", page_text[3])
        self.assertIn("HOW THIS CAN SUPPORT YOUR CAREER", page_text[4])
        self.assertIn("Start the course today", page_text[4])
        self.assertNotIn(self.marketing["landing_page_url"], page_text[4])
        self.assertTrue(any(link.get("/A", {}).get("/URI") == self.marketing["landing_page_url"] for link in page_five_links))


if __name__ == "__main__":
    unittest.main()
