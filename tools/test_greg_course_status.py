#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_course_status.py"

spec = importlib.util.spec_from_file_location("greg_course_status", MODULE_PATH)
assert spec and spec.loader
status = importlib.util.module_from_spec(spec)
sys.modules["greg_course_status"] = status
spec.loader.exec_module(status)


class CourseStatusTests(unittest.TestCase):
    def test_operating_progress_uses_approved_artifacts_only(self) -> None:
        lessons = [
            {
                "study_guide": "approved" if index == 0 else "active",
                "deck": "approved" if index == 0 else "missing",
                "pt_br_study_guide": "approved" if index == 0 else "missing",
                "pt_br_deck": "missing",
                "es_study_guide": "missing",
                "es_deck": "missing",
            }
            for index in range(15)
        ]
        result = status.operating_progress(True, lessons)
        self.assertAlmostEqual(result["percent"], 28.75, places=2)
        self.assertAlmostEqual(result["course_books"]["points"], 1.667, places=3)
        self.assertAlmostEqual(result["presentations"]["points"], 1.667, places=3)
        self.assertAlmostEqual(result["translations"]["points"], 0.417, places=3)

    def test_operating_progress_full_course_is_100(self) -> None:
        lesson = {
            "study_guide": "approved",
            "deck": "approved",
            "pt_br_study_guide": "approved",
            "pt_br_deck": "approved",
            "es_study_guide": "approved",
            "es_deck": "approved",
        }
        self.assertEqual(status.operating_progress(True, [lesson] * 15)["percent"], 100.0)

    def test_summarize_lessons_reads_multi_lesson_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "demo"
            (run / "docx_pdf").mkdir(parents=True)
            (run / "deck").mkdir()
            (run / "process_review").mkdir()
            (run / "course_map").mkdir()
            (run / "lesson_draft").mkdir()
            (run / "sources").mkdir()
            (run / "review").mkdir()
            (run / "course_map" / "course_map.json").write_text(
                '{"lessons": [{"lesson_number": 1, "title": "The Modern Construction Project Manager"}]}',
                encoding="utf-8",
            )
            (run / "docx_pdf" / "lesson_01_study_guide.pdf").write_text("pdf", encoding="utf-8")
            (run / "deck" / "lesson_01_deck_r02.pptx").write_text("deck", encoding="utf-8")
            (run / "process_review" / "lesson_01_pipeline_qa.md").write_text("qa", encoding="utf-8")
            for name in ("pedagogy_review", "citation_review", "design_qa"):
                (run / "review" / f"lesson_01_{name}.md").write_text("## Verdict\n\nPASS\n", encoding="utf-8")
            (run / "review" / "lesson_01_visual_qa.md").write_text("Visual plan QA passed: yes\n", encoding="utf-8")
            manifest = {
                "artifacts": [
                    {
                        "key": "lesson_01_study_guide_pdf",
                        "path": "docx_pdf/lesson_01_study_guide.pdf",
                        "status": "approved",
                        "lesson": "01",
                    },
                    {
                        "key": "lesson_01_deck_pptx",
                        "path": "deck/lesson_01_deck_r02.pptx",
                        "status": "approved",
                        "lesson": "01",
                    },
                    {
                        "key": "lesson_01_pipeline_qa",
                        "path": "process_review/lesson_01_pipeline_qa.md",
                        "status": "supporting",
                        "lesson": "01",
                    },
                ]
            }

            lessons = status.summarize_lessons(run, manifest)

            self.assertEqual(lessons[0]["lesson"], "01")
            self.assertEqual(lessons[0]["title"], "The Modern Construction Project Manager")
            self.assertEqual(lessons[0]["study_guide"], "approved")
            self.assertEqual(lessons[0]["deck"], "approved")
            self.assertEqual(lessons[0]["pipeline_qa"], "present")

    def test_stale_study_guide_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "demo"
            (run / "docx_pdf").mkdir(parents=True)
            (run / "lesson_draft").mkdir()
            (run / "sources").mkdir()
            (run / "course_map").mkdir()
            (run / "docx_pdf" / "lesson_01_study_guide.pdf").write_text("pdf", encoding="utf-8")
            (run / "lesson_draft" / "lesson_01_draft.md").write_text(
                "# Introduction\n\nThis study guide is written for construction learners working in the United States.\n\n# Section 01 - One\n\nBody.",
                encoding="utf-8",
            )
            (run / "sources" / "student_references.md").write_text(
                "# References\n\n- Current student references will be added after research expansion.\n",
                encoding="utf-8",
            )
            manifest = {
                "artifacts": [
                    {
                        "key": "lesson_01_study_guide_pdf",
                        "path": "docx_pdf/lesson_01_study_guide.pdf",
                        "status": "active",
                        "lesson": "01",
                    }
                ]
            }

            lessons = status.summarize_lessons(run, manifest)

            self.assertEqual(lessons[0]["study_guide"], "blocked")
            self.assertNotIn("study_guide_path", lessons[0])
            self.assertIn("study_guide_blocked_path", lessons[0])
            self.assertTrue(lessons[0]["study_guide_quality_blockers"])
            self.assertEqual(lessons[0]["visual_status"], "not_planned")

    def test_operator_approved_study_guide_is_not_retroactively_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "runs" / "demo"
            for folder in ("docx_pdf", "lesson_draft", "sources", "course_map", "approval", "review"):
                (run / folder).mkdir(parents=True, exist_ok=True)
            (run / "docx_pdf" / "lesson_01_study_guide.pdf").write_text("pdf", encoding="utf-8")
            (run / "lesson_draft" / "lesson_01_draft.md").write_text("# Introduction\n\nThis study guide is written for construction learners working in the United States.", encoding="utf-8")
            (run / "sources" / "student_references.md").write_text("References pending", encoding="utf-8")
            (run / "approval" / "lesson_01_study_guide_approval.md").write_text("Approval status: approved", encoding="utf-8")
            (run / "review" / "lesson_01_image_requests.json").write_text('{"requests": [{"visual_id": "v1"}]}', encoding="utf-8")
            lessons = status.summarize_lessons(run, {"artifacts": [{"key": "lesson_01_study_guide_pdf", "path": "docx_pdf/lesson_01_study_guide.pdf", "status": "active", "lesson": "01"}]})
            self.assertEqual(lessons[0]["study_guide"], "approved")
            self.assertEqual(lessons[0]["visual_status"], "not_planned")
            self.assertIn("study_guide_path", lessons[0])

    def test_legacy_course_map_stays_available_after_operator_book_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original_runs = status.RUNS
            try:
                status.RUNS = Path(tmp) / "runs"
                run = status.RUNS / "legacy-course"
                for folder in ("input", "course_map", "approval"):
                    (run / folder).mkdir(parents=True, exist_ok=True)
                (run / "input" / "intake.md").write_text("# Legacy course", encoding="utf-8")
                (run / "course_map" / "course_map.json").write_text('{"lessons": [{"lesson_number": 1, "title": "Approved lesson"}]}', encoding="utf-8")
                (run / "approval" / "lesson_01_study_guide_approval.md").write_text("Approval status: approved", encoding="utf-8")
                result = status.summarize("legacy-course")
            finally:
                status.RUNS = original_runs
            self.assertTrue(result["course_map_ready"])
            self.assertEqual(result["stage"], "LESSON_PRODUCTION")
            self.assertIn("operator-approved course book", result["gate_status"])

    def test_render_markdown_includes_lesson_table(self) -> None:
        text = status.render_markdown(
            {
                "stage": "TECHNICAL_PAUSE",
                "artifacts": [],
                "parked": [],
                "gate_status": "ok",
                "canonical_manifest": "runs/demo/process_review/canonical_artifacts.json",
                "blockers": [],
                "next_recommended_action": "continue",
                "lessons": [
                    {
                        "lesson": "01",
                        "study_guide": "approved",
                        "deck": "approved",
                        "pipeline_qa": "present",
                    }
                ],
            }
        )

        self.assertIn("Lesson status:", text)
        self.assertIn("| 01 | approved | approved | present |", text)

    def test_video_lane_requires_an_approved_presentation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            result = status.video_generation_status(run, "02", {"deck": "active", "deck_path": ""})
        self.assertEqual("waiting_approved_presentation", result["en"]["status"])

    def test_ready_video_lane_includes_source_hash_for_automatic_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            deck = run / "deck" / "lesson_02_deck.pptx"
            deck.parent.mkdir()
            deck.write_bytes(b"approved deck")
            result = status.video_generation_status(
                run,
                "02",
                {"deck": "approved", "deck_path": str(deck)},
            )
            expected_hash = status.file_sha256(deck)
        self.assertEqual("ready", result["en"]["status"])
        self.assertEqual(expected_hash, result["en"]["source_sha256"])

    def test_video_lane_detects_a_new_approved_revision_by_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            deck = run / "deck" / "lesson_02_deck_r02.pptx"
            deck.parent.mkdir()
            deck.write_bytes(b"new approved deck")
            state_dir = run / "video_generator"
            state_dir.mkdir()
            (state_dir / "lesson_02_en.json").write_text(
                '{"status":"video_ready","source_sha256":"old-hash","project_url":"https://app.aistudios.com/project/old","download_url":"https://cdn.aistudios.com/video/old.mp4"}',
                encoding="utf-8",
            )
            result = status.video_generation_status(
                run,
                "02",
                {"deck": "approved", "deck_path": str(deck)},
            )
        self.assertEqual("ready_new_revision", result["en"]["status"])
        self.assertEqual("https://app.aistudios.com/project/old", result["en"]["previous_project_url"])
        self.assertEqual("https://cdn.aistudios.com/video/old.mp4", result["en"]["previous_download_url"])

    def test_video_lane_blocks_a_presentation_over_twenty_mb(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            deck = run / "deck" / "lesson_02_deck.pptx"
            deck.parent.mkdir()
            with deck.open("wb") as handle:
                handle.seek(status.VIDEO_SOURCE_MAX_BYTES)
                handle.write(b"x")
            result = status.video_generation_status(
                run,
                "02",
                {"deck": "approved", "deck_path": str(deck)},
            )
        self.assertEqual("presentation_too_large", result["en"]["status"])

    def test_video_lane_reads_completed_worker_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            deck = run / "deck" / "lesson_02_deck_r03.pptx"
            deck.parent.mkdir()
            deck.write_bytes(b"approved deck")
            deck_stat = deck.stat()
            state_dir = run / "video_generator"
            state_dir.mkdir()
            source_hash = status.file_sha256(deck)
            (state_dir / "lesson_02_en.json").write_text(
                json.dumps(
                    {
                        "status": "video_ready",
                        "sourcePath": str(deck),
                        "sourceSha256": source_hash,
                        "sourceSizeBytes": deck_stat.st_size,
                        "sourceModifiedNs": deck_stat.st_mtime_ns,
                        "attemptCount": 1,
                        "downloadUrl": "https://media.aistudios.com/export/video.completed.mp4",
                        "updatedAt": "2026-08-31T21:10:26Z",
                    }
                ),
                encoding="utf-8",
            )
            result = status.video_generation_status(
                run,
                "02",
                {"deck": "approved", "deck_path": str(deck)},
            )
        self.assertEqual("video_ready", result["en"]["status"])
        self.assertEqual(1, result["en"]["attempts"])
        self.assertEqual(
            "https://media.aistudios.com/export/video.completed.mp4",
            result["en"]["download_url"],
        )


if __name__ == "__main__":
    unittest.main()
