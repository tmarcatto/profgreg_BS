#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_live_production.py"
spec = importlib.util.spec_from_file_location("greg_live_production", MODULE_PATH)
production = importlib.util.module_from_spec(spec)
sys.modules["greg_live_production"] = production
assert spec and spec.loader
spec.loader.exec_module(production)


def deck_decision(medium: str = "native-diagram") -> dict:
    selected_strategy = {
        "native-diagram": ("explain-with-diagram", "deterministic"),
        "trusted-source-image": ("inspect-real-example", "trusted-source"),
        "generated-conceptual-image": ("orient-with-conceptual-image", "generated-fallback"),
    }[medium]
    return {
        "learning_job": "Learners can apply this distinct construction decision correctly.",
        "teaching_strategy": "diagnose-and-decide",
        "visual_medium": medium,
        "visual_candidates": [
            {"medium": candidate, "decision": "selected" if candidate == medium else "rejected", "reason": f"This medium has a specific instructional fit for {candidate}."}
            for candidate in ["native-diagram", "trusted-source-image", "generated-conceptual-image"]
        ],
        "text_role": "Text directs attention to the decision rule.",
        "pedagogical_strategy": selected_strategy[0],
        "real_example_importance": "not-needed",
        "generation_suitability": "safe",
        "source_strategy": selected_strategy[1],
        "evidence_considered": [{"locator": "Course Map", "relevance": "Matches the teaching job."}],
        "alternatives_considered": ["A trusted source image was evaluated.", "A generated conceptual image was evaluated."],
        "selection_reason": "This slide mechanism directly teaches the mapped decision clearly.",
    }


class GregLiveProductionTests(unittest.TestCase):
    def test_json_request_retries_incomplete_output_with_compaction_instruction(self) -> None:
        responses = [
            production.ModelRequestError(
                "OpenAI returned incomplete text content (reason={'reason': 'max_output_tokens'})."
            ),
            '{"slides": []}',
        ]
        with patch.object(production, "request_text", side_effect=responses) as request:
            result = production.request_json_with_retry(
                "demo", "technical_content", "Return a deck.", max_tokens=12000
            )

        self.assertEqual([], result["slides"])
        self.assertEqual(2, request.call_count)
        self.assertIn("substantially shorter string values", request.call_args_list[1].args[2])

    def test_video_compatible_deck_rejects_more_than_twenty_mb(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            deck = Path(directory) / "too-large.pptx"
            with deck.open("wb") as handle:
                handle.seek(production.VIDEO_SOURCE_MAX_BYTES)
                handle.write(b"x")
            with self.assertRaisesRegex(RuntimeError, "at most 20 MB"):
                production.require_video_compatible_deck(deck)

    def test_video_compatible_deck_accepts_twenty_mb_or_less(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            deck = Path(directory) / "accepted.pptx"
            deck.write_bytes(b"pptx")
            production.require_video_compatible_deck(deck)

    def test_combined_translation_stages_produce_pt_and_es_for_each_lesson(self) -> None:
        with patch.object(production, "localize_book", side_effect=lambda course, lesson, locale: [f"{lesson}:{locale}"]) as localize_book:
            self.assertEqual(["1:pt_br", "1:es", "2:pt_br", "2:es"], production.run_stage("demo", "translations_book", [1, 2]))
        self.assertEqual(
            [("demo", 1, "pt_br"), ("demo", 1, "es"), ("demo", 2, "pt_br"), ("demo", 2, "es")],
            [item.args for item in localize_book.call_args_list],
        )

    def test_resumed_study_guide_uses_a_new_revision_after_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "lesson_draft").mkdir()
            (run / "docx_pdf").mkdir()
            draft = run / "lesson_draft" / "lesson_02_draft_r03.md"
            draft.write_text("# Saved reviewed draft\n", encoding="utf-8")
            (run / "docx_pdf" / "lesson_02_study_guide_r03.pdf").write_bytes(b"approved")
            with patch.object(production, "approved_study_guide_baseline", return_value="docx_pdf/lesson_02_study_guide_r03.pdf"):
                target, revision = production.revisioned_resumed_study_guide_draft(run, "lesson_02", draft)
            self.assertEqual(4, revision)
            self.assertEqual("lesson_02_draft_r04.md", target.name)
            self.assertEqual(draft.read_text(encoding="utf-8"), target.read_text(encoding="utf-8"))

    def test_deck_image_assets_are_reused_with_run_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            asset = run / "deck" / "assets" / "lesson_02_teaching_image_01.png"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"already-generated")
            slides = [{
                "layout": "image_bullets",
                "image_source_strategy": "generated-conceptual",
                "image_prompt": "A residential field verification scene.",
                "image_alt": "Residential field verification.",
                "image_name": "teaching-image-1",
            }]
            with patch.object(production, "request_image") as request_image:
                production.create_deck_visual_assets(SimpleNamespace(slug="demo"), {}, slides, run, "lesson_02")
            request_image.assert_not_called()
            self.assertEqual("deck/assets/lesson_02_teaching_image_01.png", slides[0]["image"]["path"])

    def test_failed_deck_spec_is_detected_as_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            deck = run / "deck"
            deck.mkdir()
            spec = deck / "lesson_02_deck_spec_r03.json"
            spec.write_text('{"slides": []}', encoding="utf-8")
            self.assertTrue(spec.exists() and not (deck / "lesson_02_deck_r03.pptx").exists())

    def test_rendered_unapproved_deck_can_resume_without_new_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            deck_dir = run / "deck"
            deck_dir.mkdir()
            output = deck_dir / "lesson_02_deck_r03.pptx"
            qa = deck_dir / "lesson_02_deck_qa_r03.md"
            output.write_bytes(b"pptx")
            qa.write_text("QA", encoding="utf-8")
            (deck_dir / "lesson_02_deck_spec_r03.json").write_text(
                json.dumps({"revision": "r03", "output": {"pptx": "deck/lesson_02_deck_r03.pptx", "qa": "deck/lesson_02_deck_qa_r03.md"}}),
                encoding="utf-8",
            )
            with patch.object(production, "load_module", return_value=SimpleNamespace(run_checks=lambda *_: {"passed": True})):
                result = production.ready_rendered_deck_spec(run, "lesson_02")
            self.assertIsNotNone(result)
            self.assertEqual(output, result[1])

    def test_deck_plan_validates_visual_decisions_and_layout_diversity(self) -> None:
        decision = deck_decision()
        slides = [
            {"layout": "cover", "title": "Buildable Work", "subtitle": "Make the job ready.", "topics": ["Intake", "Scope", "Permits"]},
            {"layout": "intro_image_bullets", "title": "Start with the site", "intro": "A field visit turns assumptions into decisions.", "bullets": ["Verify access", "Record constraints", "Confirm owners"], "image_source_strategy": "generated-conceptual", "image_prompt": "A residential project manager reviewing a home site plan with a field lead.", "image_alt": "Project manager and field lead review a residential site plan.", **deck_decision("generated-conceptual-image")},
            {"layout": "card_sequence", "title": "Move facts into action", "items": [], "takeaway": "Sequence creates control."},
            {"layout": "comparison", "title": "Separate the request from the scope", "left": {"title": "Request", "body": "Starting point"}, "right": {"title": "Scope", "body": "Verified commitment"}, "bottom_line": "Clarify first."},
            {"layout": "planned_actual", "title": "Test the gap", "left": {"title": "Planned", "body": "What was assumed"}, "right": {"title": "Actual", "body": "What the site allows"}, "bottom_line": "Price the real job."},
            {"layout": "row_list", "title": "Capture the critical record", "items": [], "bottom_line": "Record what drives decisions."},
            {"layout": "checklist_rows", "title": "Verify before commitment", "items": [], "bottom_line": "Close the gaps."},
            {"layout": "image_bullets", "title": "Permit readiness protects the start", "intro": "Authority and scope must match.", "bullets": ["Identify authority", "Assemble package", "Track response"], "bottom_line": "Release only a complete package.", "image_prompt": "A residential permit package organized on a clean desk beside house plans, no readable text.", "image_alt": "Residential permit package and house plans prepared for submittal."},
            {"layout": "card_sequence", "title": "Keep the handoff visible", "items": [], "takeaway": "A clear handoff prevents rework."},
            {"layout": "takeaway", "title": "Buildability comes before production", "body": "Verify the job before committing the work.", "final_line": "Make the job buildable first."},
        ]
        for slide in slides[2:-1]:
            slide.update(decision)
        slides[7]["image_source_strategy"] = "generated-conceptual"
        slides[7].update(deck_decision("generated-conceptual-image"))
        normalized = production.normalize_deck_slides({"slides": slides}, {"title": "Buildability", "learning_goal": "Make the job buildable."})
        self.assertEqual(10, len(normalized))
        self.assertEqual("right", normalized[1]["image_side"])
        self.assertEqual("left", normalized[7]["image_side"])

    def test_deck_plan_allows_no_teaching_image_when_strategy_does_not_call_for_one(self) -> None:
        decision = deck_decision()
        slides = [{"layout": "cover", "title": "A", "subtitle": "B", "topics": ["One", "Two", "Three"]}]
        slides.extend({"layout": layout, **decision} for layout in ["card_sequence", "comparison", "planned_actual", "row_list", "checklist_rows", "card_sequence", "comparison", "row_list"])
        slides.append({"layout": "takeaway"})
        normalized = production.normalize_deck_slides({"slides": slides}, {"title": "Test", "learning_goal": "Test"})
        self.assertEqual(10, len(normalized))

    def test_deck_plan_uses_layout_diversity_as_a_floor_not_a_visual_quota(self) -> None:
        slides = [{"layout": "cover", "title": "A", "subtitle": "B", "topics": ["One", "Two", "Three"]}]
        slides.extend({"layout": layout, **deck_decision()} for layout in [
            "card_sequence", "comparison", "planned_actual", "row_list",
            "card_sequence", "comparison", "planned_actual", "row_list",
        ])
        slides.append({"layout": "takeaway"})
        self.assertEqual(10, len(production.normalize_deck_slides({"slides": slides}, {"title": "Test"})))

    def test_deck_plan_accepts_direct_schedule_and_network_demonstrations(self) -> None:
        slides = [{"layout": "cover", "title": "A", "subtitle": "B", "topics": ["One", "Two", "Three"]}]
        slides.extend([
            {"layout": "process_flow", "items": [{"title": "Plan", "body": "Set the sequence"}, {"title": "Release", "body": "Start ready work"}], **deck_decision()},
            {"layout": "schedule_bar_chart", "schedule_rows": [
                {"activity": "Layout", "start": 0, "duration": 2, "status": "complete"},
                {"activity": "Framing", "start": 2, "duration": 4, "status": "in-progress"},
                {"activity": "Rough-ins", "start": 4, "duration": 3, "status": "planned"},
            ], **deck_decision()},
            {"layout": "activity_network", "network_paths": [{"label": "Controlling path", "critical": True, "activities": [
                {"title": "Excavate", "duration": "2d"}, {"title": "Form", "duration": "3d"}, {"title": "Pour", "duration": "1d"},
            ]}], **deck_decision()},
            {"layout": "comparison", **deck_decision()},
            {"layout": "process_flow", "items": [{"title": "Find", "body": "See the constraint"}, {"title": "Own", "body": "Assign action"}], **deck_decision()},
            {"layout": "schedule_bar_chart", "schedule_rows": [
                {"activity": "A", "start": 0, "duration": 1, "status": "complete"},
                {"activity": "B", "start": 1, "duration": 2, "status": "planned"},
                {"activity": "C", "start": 2, "duration": 2, "status": "delayed"},
            ], **deck_decision()},
            {"layout": "activity_network", "network_paths": [{"label": "Path", "critical": False, "activities": [{"title": "A", "duration": "1d"}, {"title": "B", "duration": "2d"}]}], **deck_decision()},
            {"layout": "comparison", **deck_decision()},
        ])
        slides.append({"layout": "takeaway"})
        normalized = production.normalize_deck_slides({"slides": slides}, {"title": "Test"})
        self.assertEqual("schedule_bar_chart", normalized[2]["layout"])
        self.assertEqual("activity_network", normalized[3]["layout"])

    def test_initial_deck_structure_failure_uses_bounded_revision_recovery(self) -> None:
        malformed = {
            "slides": [
                {"layout": "cover", "title": "A", "subtitle": "B", "topics": ["One", "Two", "Three"]},
                {"layout": "process_flow", "items": [], **deck_decision()},
            ]
        }
        repaired = [{"layout": "cover"}, {"layout": "takeaway"}]
        with (
            patch.object(production, "request_json_with_retry", return_value=malformed),
            patch.object(production, "request_normalized_deck_revision", return_value=repaired) as revise,
        ):
            result = production.request_normalized_initial_deck(
                "demo",
                {"title": "Test", "learning_goal": "Test"},
                "Create a deck.",
            )
        self.assertEqual(repaired, result)
        self.assertIn("invalid presentation structure", revise.call_args.args[3])
        self.assertIn("Presentation model returned an invalid deck structure", revise.call_args.args[3])

    def test_deck_normalizer_accepts_matrix_comparison_and_named_planned_actual(self) -> None:
        slides = [{"layout": "cover", "title": "A", "subtitle": "B", "topics": ["One", "Two", "Three"]}]
        body = [
            {"layout": "comparison", "comparison_columns": ["Variable", "A", "B"], "comparison_rows": [{"variable": "Owner", "a": "PM", "b": "Super"}, {"variable": "Record", "a": "Log", "b": "Report"}]},
            {"layout": "planned_actual", "planned": {"label": "Planned", "body": "Start"}, "actual": {"label": "Actual", "body": "Delayed"}},
            {"layout": "card_sequence", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "row_list", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "checklist_rows", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "comparison", "left": {"title": "A", "body": "a"}, "right": {"title": "B", "body": "b"}},
            {"layout": "card_sequence", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "row_list", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
        ]
        slides.extend({**item, **deck_decision()} for item in body)
        slides.append({"layout": "takeaway"})
        normalized = production.normalize_deck_slides({"slides": slides}, {"title": "Test"})
        self.assertEqual("Planned", normalized[2]["left"]["title"])
        self.assertEqual("Actual", normalized[2]["right"]["title"])

    def test_deck_normalizer_accepts_columns_rows_and_planned_actual_row_variants(self) -> None:
        slides = [{"layout": "cover", "title": "A", "subtitle": "B", "topics": ["One", "Two", "Three"]}]
        body = [
            {"layout": "comparison", "columns": ["Question", "Risk", "Issue"], "rows": [
                {"cells": ["When", "Future", "Now"]}, {"cells": ["Record", "Register", "Log"]},
            ]},
            {"layout": "planned_actual", "items": [
                {"title": "Access", "body": "Planned: Clear drive. Actual: Spoil blocks it. Decision: Clear before dispatch."},
                {"title": "Storage", "body": "Planned: Dry zone. Actual: Zone occupied. Decision: Reassign it."},
            ]},
            {"layout": "card_sequence", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "row_list", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "checklist_rows", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "comparison", "left": {"title": "A", "body": "a"}, "right": {"title": "B", "body": "b"}},
            {"layout": "card_sequence", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "row_list", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
        ]
        slides.extend({**slide, **deck_decision()} for slide in body)
        slides.append({"layout": "takeaway"})

        normalized = production.normalize_deck_slides({"slides": slides}, {"title": "Test"})

        self.assertEqual(["Question", "Risk", "Issue"], normalized[1]["comparison_columns"])
        self.assertEqual(["When", "Future", "Now"], normalized[1]["comparison_rows"][0]["cells"])
        self.assertEqual("Clear drive", normalized[2]["planned_actual_rows"][0]["planned"])
        self.assertEqual("Clear before dispatch", normalized[2]["planned_actual_rows"][0]["action"])

    def test_deck_normalizer_maps_record_rows_and_value_detail_variance(self) -> None:
        slides = [{"layout": "cover", "title": "A", "subtitle": "B", "topics": ["One", "Two", "Three"]}]
        body = [
            {"layout": "row_list", "rows": [{"label": "Notice", "record": "Dated correspondence"}]},
            {"layout": "planned_actual", "planned": {"label": "Budget", "value": "$40k", "detail": "Authorized"}, "actual": {"label": "Forecast", "value": "$42k", "detail": "At completion"}, "variance": {"label": "Decision", "value": "Find cause", "detail": "Act before spend"}},
            {"layout": "card_sequence", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "comparison", "left": {"title": "A", "body": "a"}, "right": {"title": "B", "body": "b"}},
            {"layout": "checklist_rows", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "row_list", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "card_sequence", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "comparison", "left": {"title": "A", "body": "a"}, "right": {"title": "B", "body": "b"}},
        ]
        slides.extend({**slide, **deck_decision()} for slide in body)
        slides.append({"layout": "takeaway"})

        normalized = production.normalize_deck_slides({"slides": slides}, {"title": "Test"})

        self.assertEqual({"title": "Notice", "body": "Dated correspondence"}, normalized[1]["items"][0])
        self.assertEqual("$40k — Authorized", normalized[2]["left"]["body"])
        self.assertEqual("$42k — At completion", normalized[2]["right"]["body"])
        self.assertEqual("Find cause — Act before spend", normalized[2]["decision_ready_update"]["body"])

    def test_deck_plan_rejects_layout_selected_before_visual_medium(self) -> None:
        slides = [{"layout": "cover", "title": "A", "subtitle": "B", "topics": ["One", "Two", "Three"]}]
        layouts = ["card_sequence", "comparison", "planned_actual", "row_list", "checklist_rows", "card_sequence", "comparison", "row_list"]
        slides.extend({"layout": layout, **deck_decision()} for layout in layouts)
        slides[3]["visual_medium"] = "generated-conceptual-image"
        slides.append({"layout": "takeaway"})
        with self.assertRaisesRegex(RuntimeError, "selected visual medium|visual candidate"):
            production.normalize_deck_slides({"slides": slides}, {"title": "Test", "learning_goal": "Test"})

    def test_deck_visual_plan_records_pedagogy_media_and_text_role(self) -> None:
        slides = [{"layout": "cover"}]
        slides.extend(
            {
                "layout": "card_sequence",
                "title": f"Decision {index}",
                "items": [{"title": "Observe", "body": "Check the work"}],
                **deck_decision(),
            }
            for index in range(2, 10)
        )
        slides.append({"layout": "takeaway"})
        plan = production.deck_visual_plan_from_slides(slides, {"lesson_number": 4})
        self.assertEqual("deck", plan["artifact_type"])
        self.assertEqual("diagnose-and-decide", plan["visuals"][0]["teaching_strategy"])
        self.assertEqual("native-diagram", plan["visuals"][0]["visual_medium"])
        self.assertIn("decision rule", plan["visuals"][0]["text_role"])
        self.assertEqual("card-sequence", plan["visuals"][0]["diagram_type"])
        self.assertEqual(
            [{"title": "Observe", "detail": "Check the work"}],
            plan["visuals"][0]["diagram_nodes"],
        )

    def test_deck_prompt_chooses_pedagogy_before_comparing_three_media(self) -> None:
        prompt = production.deck_prompt(
            SimpleNamespace(title="Demo Course"),
            {"lesson_number": 1, "title": "Demo Lesson", "visual_insertions": []},
            "Approved course book text.",
            {"visuals": []},
            "",
        )
        self.assertLess(prompt.index("Choose one `teaching_strategy`"), prompt.index("Evaluate all three `visual_candidates`"))
        for medium in ["native-diagram", "trusted-source-image", "generated-conceptual-image"]:
            self.assertIn(medium, prompt)

    def test_deck_revision_prompt_upgrades_internal_visual_metadata_without_rewriting(self) -> None:
        prompt = production.deck_revision_prompt([{"layout": "cover"}], "Shorten slide 3.")
        self.assertIn("Adding missing internal planning metadata is not a student-visible change", prompt)
        self.assertIn("all three `visual_candidates`", prompt)

    def test_image_only_upload_text_is_never_extracted_for_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "visual-only.pdf"
            pdf.write_bytes(b"not a real PDF")
            uploads = [{
                "filename": pdf.name,
                "stored_path": str(pdf),
                "purpose": "source_material",
                "reference_policy": "image_only",
            }]
            with patch.object(production, "read_uploads", return_value=uploads), patch.object(production.subprocess, "run") as run:
                excerpts = production.source_excerpts("demo")
            run.assert_not_called()
            self.assertEqual("No readable uploaded excerpts were available.", excerpts)

    def test_context_only_upload_text_can_guide_content_without_becoming_mandatory_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "context.pdf"
            pdf.write_bytes(b"not a real PDF")
            uploads = [{
                "filename": pdf.name,
                "stored_path": str(pdf),
                "purpose": "source_material",
                "reference_policy": "context_only",
            }]
            completed = type("Completed", (), {"stdout": "Useful internal terminology."})()
            with patch.object(production, "read_uploads", return_value=uploads), patch.object(production.subprocess, "run", return_value=completed):
                excerpts = production.source_excerpts("demo")
            self.assertIn("Useful internal terminology.", excerpts)

    def test_revision_text_is_limited_to_the_matching_lesson_and_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            material = Path(directory) / "revision-note.txt"
            material.write_text("Use the supplied photo after the inspection section.", encoding="utf-8")
            uploads = [{
                "filename": material.name,
                "stored_path": str(material),
                "purpose": "revision_material",
                "revision_artifact_type": "study_guide",
                "scope": "lesson_01",
                "reference_policy": "context_only",
            }]
            with patch.object(production, "read_uploads", return_value=uploads):
                matching = production.source_excerpts("demo", lesson=1, artifact_type="study_guide")
                wrong_lesson = production.source_excerpts("demo", lesson=2, artifact_type="study_guide")
                wrong_artifact = production.source_excerpts("demo", lesson=1, artifact_type="deck")
            self.assertIn("supplied photo", matching)
            self.assertEqual("No readable uploaded excerpts were available.", wrong_lesson)
            self.assertEqual("No readable uploaded excerpts were available.", wrong_artifact)

    def test_revision_evidence_never_guides_drafting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "issue.txt"
            evidence.write_text("This is only evidence of a display error.", encoding="utf-8")
            uploads = [{"filename": evidence.name, "stored_path": str(evidence), "purpose": "revision_evidence", "scope": "lesson_01", "reference_policy": "context_only"}]
            with patch.object(production, "read_uploads", return_value=uploads):
                self.assertEqual("No readable uploaded excerpts were available.", production.source_excerpts("demo", lesson=1, artifact_type="study_guide"))

    def test_truncated_revision_restores_the_approved_tail(self) -> None:
        baseline = "# Introduction\n\nStart.\n\n# Section 01 - Cost\n\nChanged area.\n\n# Section 04 - Bid\n\nComplete bid lesson.\n\n# Summary and Key Takeaways\n\n- One.\n\n# Glossary\n\nTerm.\n\n# References\n\nSource.\n"
        partial = "# Introduction\n\nStart.\n\n# Section 01 - Cost\n\nChanged area.\n"
        restored = production.restore_truncated_revision(partial, baseline)
        self.assertIn("# Section 04 - Bid", restored)
        self.assertIn("# Summary and Key Takeaways", restored)

    def test_section_patch_preserves_every_unrequested_section_verbatim(self) -> None:
        draft = (
            "# Introduction\n\nKeep this introduction.\n\n## Learning Objectives\n\n- Learn.\n\n"
            "# Section 01 - Scope\n\nKeep this scope text.\n\n"
            "# Section 03 - Cost Stack\n\nOld stack explanation.\n\n"
            "# Section 04 - Bid\n\nKeep this bid text.\n\n"
            "# Summary and Key Takeaways\n\n- Keep this recap.\n\n"
            "# Glossary\n\nTerm.\n\n# References\n\nSource.\n"
        )
        revised = production.apply_study_guide_section_patches(
            draft,
            {"# Section 03 - Cost Stack": "# Section 03 - Cost Stack\n\nNew additive stack explanation.\n"},
        )
        self.assertIn("New additive stack explanation.", revised)
        self.assertIn("# Section 01 - Scope\n\nKeep this scope text.", revised)
        self.assertIn("# Section 04 - Bid\n\nKeep this bid text.", revised)
        self.assertIn("# Summary and Key Takeaways\n\n- Keep this recap.", revised)

    def test_section_patch_rejects_an_unselected_section(self) -> None:
        draft = (
            "# Introduction\n\nStart.\n\n## Learning Objectives\n\n- Learn.\n\n# Section 01 - Scope\n\nScope.\n\n"
            "# Summary and Key Takeaways\n\n- One.\n\n# Glossary\n\nTerm.\n\n# References\n\nSource.\n"
        )
        with self.assertRaisesRegex(RuntimeError, "outside the approved revision scope"):
            production.apply_study_guide_section_patches(
                draft,
                {"# Section 99 - Other": "# Section 99 - Other\n\nNo.\n"},
            )

    def test_required_upload_binding_marks_every_citable_attachment_mandatory(self) -> None:
        uploads = [
            {"filename": "Construction Project Management Handbook.pdf", "upload_id": "u1", "reference_policy": "reference_only"},
            {"filename": "Integrated Approach.pdf", "upload_id": "u2", "reference_policy": "reference_and_images"},
        ]
        sources = [
            {"title": "Construction Project Management Handbook", "formal_reference": "Handbook."},
            {"title": "Integrated Approach", "formal_reference": "Integrated Approach."},
        ]
        self.assertEqual([], production.bind_required_upload_sources(sources, uploads))
        self.assertTrue(all(source["mandatory_use"] for source in sources))
        self.assertEqual(["operator_upload", "operator_upload"], [source["origin"] for source in sources])

    def test_required_upload_binding_reports_an_omitted_attachment(self) -> None:
        uploads = [{"filename": "Required Book.pdf", "upload_id": "u1", "reference_policy": "reference_only"}]
        self.assertEqual(["Required Book.pdf"], production.bind_required_upload_sources([], uploads))

    def test_lesson_reference_merge_preserves_attached_and_researched_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "sources").mkdir()
            ledger = {"sources": [{
                "source_id": "S01",
                "title": "Attached Construction Handbook",
                "formal_reference": "Publisher. Attached Construction Handbook.",
                "source_type": "book",
                "origin": "operator_upload",
                "mandatory_use": True,
                "currency_validation": {"status": "validated-current"},
                "claims_supported": [{"claim": "Attached guidance", "lesson_numbers": [1]}],
            }]}
            refresh = {"sources": [{
                "source_id": "L01S01",
                "title": "Current External Guidance",
                "formal_reference": "Authority. Current External Guidance.",
                "source_type": "government",
                "currency_validation": {"status": "validated-current"},
                "claims_supported": [{"claim": "Current rule", "lesson_numbers": [1]}],
            }]}
            _, references = production.merge_lesson_sources(run, ledger, refresh, 1)
            self.assertIn("Attached Construction Handbook", references)
            self.assertIn("Current External Guidance", references)

    def test_lesson_reference_merge_uses_the_ledgered_duplicate_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "sources").mkdir()
            ledger = {"sources": [{
                "source_id": "S01", "title": "Estimate Guidance", "url": "https://example.com/estimate.pdf",
                "formal_reference": "Authority. Old title.", "source_type": "standard",
                "currency_validation": {"status": "validated-current"}, "claims_supported": [],
            }]}
            refresh = {"sources": [{
                "source_id": "L03S02", "title": "Estimate Guidance", "url": "https://example.com/estimate.pdf",
                "formal_reference": "Authority. Cost Estimate Classification: Building Construction.", "source_type": "standard",
                "currency_validation": {"status": "validated-current"}, "claims_supported": [{"lesson_numbers": [3]}],
            }]}
            merged, references = production.merge_lesson_sources(run, ledger, refresh, 3)
            self.assertEqual(1, len(merged["sources"]))
            self.assertIn("Cost Estimate Classification: Building Construction.", references)

    def test_lesson_reference_merge_excludes_unrelated_refresh_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "sources").mkdir()
            ledger = {"sources": [{
                "source_id": "S01", "title": "General handbook", "formal_reference": "Authority. General handbook.",
                "currency_validation": {"status": "validated-current"}, "claims_supported": [{"lesson_numbers": [1]}],
            }]}
            refresh = {"sources": [{
                "source_id": "S01", "title": "General handbook", "formal_reference": "Authority. General handbook.",
                "currency_validation": {"status": "validated-current"}, "claims_supported": [{"lesson_numbers": [1]}],
            }]}
            _, references = production.merge_lesson_sources(run, ledger, refresh, 3)
            self.assertEqual("# References\n\n", references)

    def test_cached_draft_is_invalid_when_a_mandatory_attachment_is_missing(self) -> None:
        ledger = {"sources": [{
            "title": "Attached Construction Handbook",
            "formal_reference": "Publisher. Attached Construction Handbook.",
            "origin": "operator_upload",
            "mandatory_use": True,
        }]}
        stale = "# Introduction\n\nText.\n\n# References\n\n- A current external source.\n"
        current = "# Introduction\n\nText.\n\n# References\n\n- Publisher. Attached Construction Handbook.\n"
        self.assertFalse(production.draft_has_all_mandatory_upload_references(stale, ledger))
        self.assertTrue(production.draft_has_all_mandatory_upload_references(current, ledger))

    def test_reviewer_ledger_keeps_all_lesson_sources_without_unrelated_bulk(self) -> None:
        ledger = {"course_slug": "demo", "sources": [
            {"source_id": "A", "title": "Used", "formal_reference": "Used reference", "claims_supported": [{"claim": "Supported", "lesson_numbers": [1]}], "unused_bulk": "x" * 1000},
            {"source_id": "B", "title": "Other", "claims_supported": [{"claim": "Other", "lesson_numbers": [2]}]},
        ]}
        compact = production.compact_reviewer_ledger(ledger, 1)
        self.assertEqual([item["source_id"] for item in compact["sources"]], ["A"])
        self.assertNotIn("unused_bulk", compact["sources"][0])

    def test_reviewer_ledger_keeps_mandatory_uploaded_source_without_lesson_claim(self) -> None:
        ledger = {"course_slug": "demo", "sources": [{
            "source_id": "S01", "title": "Uploaded handbook", "formal_reference": "Authority. Uploaded handbook.",
            "origin": "operator_upload", "mandatory_use": True, "claims_supported": [{"lesson_numbers": [1]}],
        }]}
        compact = production.compact_reviewer_ledger(ledger, 3)
        self.assertEqual(["S01"], [item["source_id"] for item in compact["sources"]])
        self.assertEqual(["Mandatory operator-provided course source."], compact["sources"][0]["claims_supported"])

    def test_localized_deck_removes_dash_punctuation_recursively(self) -> None:
        value = {"topics": ["planejar–acompanhar–ajustar", "Escopo — não tarefas"]}
        cleaned = production.normalize_localized_dash_punctuation(value)
        self.assertEqual(cleaned, {"topics": ["planejar, acompanhar, ajustar", "Escopo; não tarefas"]})

    def test_localized_deck_keeps_approved_teaching_image_metadata(self) -> None:
        source = [{
            "layout": "image_bullets",
            "title": "Verify the site",
            "bullets": ["Confirm access", "Record constraints"],
            "image_prompt": "A realistic residential site visit.",
            "image_alt": "A project manager reviewing a home site.",
            "image": {"path": "deck/assets/lesson_01_teaching_image_01.png", "alt": "A project manager reviewing a home site."},
        }]
        translated = [{
            "layout": "image_bullets",
            "title": "Verifique o local",
            "bullets": ["Confirme o acesso", "Registre as restrições"],
        }]
        slides = production.localized_deck_slides(source, translated)
        self.assertEqual("Verifique o local", slides[0]["title"])
        self.assertEqual("deck/assets/lesson_01_teaching_image_01.png", slides[0]["image"]["path"])
        self.assertEqual("A realistic residential site visit.", slides[0]["image_prompt"])

    def test_localized_slide_visible_items_never_returns_empty(self) -> None:
        self.assertEqual(production.localized_slide_visible_items({"title": "Título"}), ["Título"])
        self.assertEqual(production.localized_slide_visible_items({"title": "T", "topics": ["Um", "Dois"]}), ["Um", "Dois"])

    def test_localized_book_removes_unjustified_inline_bold(self) -> None:
        source = "**El gerente completo** comienza el trabajo.\n\n# Introducción"
        self.assertEqual(
            "El gerente completo comienza el trabajo.\n\n# Introducción",
            production.remove_unnecessary_localized_emphasis(source),
        )

    def test_localized_callout_count_uses_target_language_labels(self) -> None:
        pt = "> TERMO-CHAVE  \n> Definição.\n\n> **CENÁRIO**\n> Situação."
        es = "> **TÉRMINO CLAVE**\n> Definición.\n\n> **ESCENARIO**\n> Situación."
        self.assertEqual(2, production.localized_callout_count(pt, "pt_br"))
        self.assertEqual(2, production.localized_callout_count(es, "es"))

    def test_cached_localized_visuals_must_still_fit_renderer_contract(self) -> None:
        self.assertTrue(production.localized_visuals_fit_contract([{
            "type": "process_flow", "nodes": [{"title": "Valid title", "detail": "Valid detail"}],
        }]))
        self.assertFalse(production.localized_visuals_fit_contract([{
            "type": "process_flow", "nodes": [{"title": "X" * 31, "detail": "Valid detail"}],
        }]))
        self.assertFalse(production.localized_visuals_fit_contract([{
            "type": "process_flow", "nodes": [{"title": "Valid title", "detail": "X" * 37}],
        }]))
        self.assertFalse(production.localized_visuals_fit_contract([{
            "type": "source_to_wbs_matrix", "rows": [{"left": "X" * 41, "right": "Valid detail"}],
        }]))

    def test_localized_book_visuals_translates_the_lesson_in_one_batch(self) -> None:
        source_visuals = [
            {"visual_id": "L01V01", "type": "card_row", "after_heading": "Section 01 - Start", "title": "Start"},
            {"visual_id": "L01V02", "type": "card_row", "after_heading": "Section 02 - Finish", "title": "Finish"},
        ]
        translated_visuals = [
            {"visual_id": "L01V01", "type": "card_row", "after_heading": "ignored", "title": "Começar"},
            {"visual_id": "L01V02", "type": "card_row", "after_heading": "ignored", "title": "Concluir"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            spec = run / "docx_pdf" / "lesson_01_study_guide_spec_r01.json"
            spec.parent.mkdir()
            spec.write_text(production.json.dumps({"visuals": source_visuals}), encoding="utf-8")
            translated = "# Seção 01 - Começar\n\n# Seção 02 - Concluir\n"
            with (
                patch.object(production, "request_json_with_retry", return_value={"visuals": translated_visuals}) as request,
                patch.object(production, "localized_visual_contract_error", return_value=""),
            ):
                result = production.localized_book_visuals(
                    SimpleNamespace(slug="demo"), run, "lesson_01", "pt_br", "Brazilian Portuguese", translated
                )

        self.assertEqual(1, request.call_count)
        self.assertEqual(["Seção 01 - Começar", "Seção 02 - Concluir"], [item["after_heading"] for item in result])
        self.assertIn('"visual_id": "L01V01"', request.call_args.args[2])
        self.assertIn('"visual_id": "L01V02"', request.call_args.args[2])

    def test_localized_book_structure_requires_english_heading_hierarchy(self) -> None:
        complete = "\n".join([
            "# Seção 1 — Primeiro", "# Seção 2: Segundo", "# Seção 03 - Terceiro", "# Seção 4 – Quarto",
            "# Resumo e Principais Conclusões", "- Um", "# Referências",
        ])
        self.assertEqual([], production.localized_book_structure_issues(complete, "pt_br"))

    def test_localized_contract_normalizes_section_levels_and_callout_markup(self) -> None:
        normalized = production.normalize_localized_course_contract(
            "## Seção 01: Primeiro\n\n> EXEMPLO PRÁTICO\n> Corpo.\n\n> **CENÁRIO:** Situação.", "pt_br"
        )
        self.assertIn("# Seção 01: Primeiro", normalized)
        self.assertIn("> **EXEMPLO PRÁTICO**", normalized)
        self.assertIn("> **CENÁRIO**: Situação.", normalized)

    def test_localized_book_parity_rejects_lost_box_and_table_row(self) -> None:
        source = (
            "# Introduction\n# Section 01 - One\n> **HANDS-ON EXAMPLE**\n> Body.\n"
            "| Item | Amount |\n|---|---:|\n| One | $1,000 |\n| Two | $2,000 |\n"
            "# Summary and Key Takeaways\n- One\n- Two\n- Three\n- Four\n"
        )
        localized = (
            "# Introdução\n# Seção 01: Um\nEXEMPLO PRÁTICO Corpo.\n"
            "| Item | Valor |\n|---|---:|\n| Um | $1.000 |\n"
            "# Resumo e Principais Conclusões\nUm parágrafo inválido.\n"
        )
        issues = production.localized_book_parity_issues(source, localized, "pt_br")
        self.assertTrue(any("callout boxes" in issue for issue in issues))
        self.assertTrue(any("table 1" in issue for issue in issues))
        self.assertTrue(any("summary bullet items" in issue for issue in issues))

    def test_localized_book_structure_reports_truncated_translation(self) -> None:
        partial = "# Seção 01: Primeiro\n\nTexto.\n\n# Referências\n"
        self.assertEqual(
            ["missing `Resumo e Principais Conclusões`", "fewer than four numbered sections"],
            production.localized_book_structure_issues(partial, "pt_br"),
        )

    def test_localized_retry_ignores_newer_incomplete_revision(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            folder = Path(directory)
            complete = folder / "lesson_01_study_guide_es_r01.md"
            incomplete = folder / "lesson_01_study_guide_es_r02.md"
            complete.write_text(
                "\n".join([f"# Sección {number:02d}: Título" for number in range(1, 5)])
                + "\n# Resumen y Conclusiones Clave\n- Uno\n- Dos\n- Tres\n- Cuatro\n",
                encoding="utf-8",
            )
            incomplete.write_text("## Sección 01: Incompleta\n# Resumen y Conclusiones Clave\n", encoding="utf-8")
            self.assertEqual(complete, production.latest_complete_localized_draft(folder, "lesson_01", "es"))

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

    def test_deck_revision_prompt_preserves_unmentioned_slides(self) -> None:
        prompt = production.deck_revision_prompt(
            [{"layout": "cover", "title": "Existing"}],
            "Fix one diagram.",
            [{"request_id": "7", "request": "Fix one diagram.", "target_slide_number": 1}],
        )
        self.assertIn("Apply only the requested changes", prompt)
        self.assertIn("Do not rebuild the presentation", prompt)
        self.assertIn("Fix one diagram.", prompt)
        self.assertIn("revision_resolutions", prompt)
        self.assertIn("target_slide_number", prompt)

        advanced = production.study_guide_revision_prompt(
            "# Existing", "Complete the ending.", "# References", attempt=1, level="Advanced"
        )
        self.assertIn("must not exceed 6,200 words", advanced)

    def test_deck_revision_resolution_rejects_wrong_slide_and_empty_regions(self) -> None:
        baseline = [
            {"layout": "cover", "title": "Cover"},
            {"layout": "process_flow", "title": "Flow", "items": [{"title": "A", "body": ""}, {"title": "B", "body": ""}]},
        ]
        candidate = [
            baseline[0],
            {"layout": "process_flow", "title": "Flow", "items": [{"title": "A1", "body": ""}, {"title": "B", "body": ""}]},
        ]
        requests = [{"id": "1", "note": "What is the blank space?"}]
        response = {"revision_resolutions": [{"request_id": "1", "slide_number": 2, "problem": "The boxes were empty.", "change": "Changed the first visible label only."}]}
        context = [{"request_id": "1", "target_slide_number": 2}]
        with self.assertRaisesRegex(RuntimeError, "empty diagram regions remain"):
            production.validate_deck_revision_resolutions(baseline, candidate, requests, response, context)

        with self.assertRaisesRegex(RuntimeError, "belongs to slide 2"):
            production.validate_deck_revision_resolutions(
                baseline,
                candidate,
                requests,
                {"revision_resolutions": [{"request_id": "1", "slide_number": 1, "problem": "Wrong slide selected.", "change": "Changed an unrelated cover slide."}]},
                context,
            )

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

    def test_lesson_source_refresh_audit_covers_all_lesson_sources(self) -> None:
        refresh = {"source_gaps": [], "sources": [{"source_id": "L01S01"}]}
        ledger = {
            "sources": [
                {"source_id": "S01", "claims_supported": [{"lesson_numbers": [1]}]},
                {"source_id": "L01S01", "claims_supported": [{"lesson_numbers": [1]}]},
                {"source_id": "S02", "claims_supported": [{"lesson_numbers": [2]}]},
            ]
        }
        normalized = production.normalize_lesson_source_refresh(refresh, ledger, 1)
        self.assertEqual(["L01S01", "S01"], normalized["source_ids_reviewed"])
        self.assertEqual("completed", normalized["status"])
        self.assertEqual("completed", normalized["current_claim_validation"])
        self.assertEqual([], normalized["gaps"])

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

    def test_student_reference_removes_trailing_chapter_locator_after_period(self) -> None:
        source = {
            "formal_reference": "International Code Council. (2024). 2024 International Residential Code. Chapter RE 1, Scope and Administration.",
            "source_type": "standard",
            "url": "https://codes.example.test/chapter-re-1",
        }
        self.assertEqual(
            "International Code Council. (2024). 2024 International Residential Code.",
            production.student_reference_for_source(source),
        )

    def test_student_reference_consolidates_part_1926_sections(self) -> None:
        entries = [
            production.student_reference_for_source({"formal_reference": "Occupational Safety and Health Administration. 29 C.F.R. § 1926.20, General safety and health provisions. Current OSHA online text.", "source_type": "standard"}),
            production.student_reference_for_source({"formal_reference": "Occupational Safety and Health Administration. 29 C.F.R. Part 1926, Safety and Health Regulations for Construction. Current OSHA online text.", "source_type": "standard"}),
        ]
        self.assertEqual(entries[0], entries[1])
        self.assertEqual(
            "Occupational Safety and Health Administration. Safety and Health Regulations for Construction, 29 C.F.R. Part 1926. U.S. Department of Labor.",
            entries[0],
        )

    def test_force_references_removes_embedded_reference_list(self) -> None:
        draft = "# Introduction\n\nIntro.\n\n# Section 01 - One\n\nBody.\n\n**References**\n\n- Embedded source.\n\n# Summary and Key Takeaways\n\n- One.\n\n# References\n\n- Model source.\n"
        revised = production.force_student_references(draft, "# References\n\n- Validated source.")
        self.assertNotIn("Embedded source", revised)
        self.assertNotIn("Model source", revised)
        self.assertIn("Validated source", revised)

    def test_verification_requirements_reference_omits_document_url(self) -> None:
        source = {
            "formal_reference": "U.S. Environmental Protection Agency. (2024). Indoor AirPlus Verification Requirements, Version 2.",
            "source_type": "government",
            "url": "https://example.gov/verification-requirements.txt",
        }
        reference = production.student_reference_for_source(source)
        self.assertNotIn("https://", reference)

    def test_government_guidance_document_reference_omits_page_url(self) -> None:
        source = {
            "formal_reference": "Occupational Safety and Health Administration. Fall Protection in Residential Construction: OSHA Guidance Document.",
            "source_type": "government",
            "url": "https://www.osha.gov/residential-fall-protection/guidance",
        }
        reference = production.student_reference_for_source(source)
        self.assertNotIn("https://", reference)

    def test_government_quick_start_guide_reference_omits_download_url(self) -> None:
        source = {
            "formal_reference": "National Institute of Standards and Technology. (2024). NIST Cybersecurity Framework 2.0: Small Business Quick Start Guide.",
            "source_type": "government",
            "url": "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=957322",
        }
        reference = production.student_reference_for_source(source)
        self.assertNotIn("https://", reference)

    def test_repeated_structural_blocks_are_removed_from_numbered_sections(self) -> None:
        draft = """## Learning Objectives

- Keep this objective.

# Section 01 - Lead

**Learning Objectives**

- Remove this objective.

Teaching body.

**Glossary**

Use these terms to distinguish roles.

- **Duplicate:** Remove this definition.

# Glossary

- **Canonical:** Keep this definition.
"""
        revised = production.normalize_repeated_lesson_objectives(draft)
        self.assertIn("Keep this objective", revised)
        self.assertNotIn("Remove this objective", revised)
        self.assertNotIn("Remove this definition", revised)
        self.assertIn("Keep this definition", revised)

    def test_student_reference_does_not_strip_title_containing_applied_in(self) -> None:
        source = {
            "formal_reference": (
                "AACE International. (2020, August 7). Recommended Practice No. 56R-08: Cost Estimate "
                "Classification System; As Applied in Engineering, Procurement, and Construction for the Building "
                "and General Construction Industries."
            ),
            "source_type": "standard",
            "url": "https://web.aacei.org/docs/default-source/toc/toc_56r-08.pdf",
        }
        self.assertIn("Recommended Practice No. 56R-08", production.student_reference_for_source(source))
        self.assertIn("Cost Estimate Classification System", production.student_reference_for_source(source))

    def test_reviewed_factual_language_is_corrected_without_new_claims(self) -> None:
        draft = "After award, these decisions become enforceable responsibilities, payment terms, and procurement commitments, the focus of the next lesson."
        corrected = production.normalize_reviewed_factual_language(draft)
        self.assertIn("An estimate is not itself a binding project obligation", corrected)

    def test_incomplete_revision_cannot_replace_complete_chapter(self) -> None:
        complete = "\n".join([
            "# Introduction", "Full introduction.", "# Learning Objectives", "- Learn.",
            "# Section 01 - One", "Body.", "# Section 02 - Two", "Body.",
            "# Section 03 - Three", "Body.", "# Section 04 - Four", "Body.",
            "# Summary and Key Takeaways", "- One", "- Two", "- Three", "- Four",
            "# Glossary", "- **Term:** Definition.", "# References", "- Authority.",
        ])
        partial = "# Introduction\n\nPartial text.\n\n# Learning Objectives\n\n- Learn.\n\n# Section 01 - One\n\nBody."
        self.assertFalse(production.preserves_complete_study_guide_structure(partial, complete))

    def test_complete_structure_accepts_template_learning_objectives_heading(self) -> None:
        complete = "\n".join([
            "# Introduction", "Full introduction.", "## Learning Objectives", "- Learn.",
            "# Section 01 - One", "Body.", "# Section 02 - Two", "Body.",
            "# Section 03 - Three", "Body.", "# Section 04 - Four", "Body.",
            "# Summary and Key Takeaways", "- One", "- Two", "- Three", "- Four",
            "# Glossary", "- **Term:** Definition.", "# References", "- Authority.",
        ])
        self.assertTrue(production.preserves_complete_study_guide_structure(complete, ""))

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

    def test_visual_retry_policy_uses_literal_reviewer_replacements(self) -> None:
        source = Path(production.__file__).read_text(encoding="utf-8")
        self.assertIn("copy those replacements exactly", source)
        self.assertIn("max_visual_review_attempts = 6", source)
        self.assertNotIn("after two review passes", source)

    def test_structured_visual_recovers_dropped_visual_type(self) -> None:
        visual = {
            "visual_id": "L13V01",
            "diagram_type": "relationship-map",
            "diagram_nodes": [{"title": "Hub", "detail": "Controlled system"}],
        }
        restored = production.restore_structured_visual_type(visual)
        self.assertEqual("deterministic-diagram", restored["visual_type"])
        self.assertNotIn("visual_type", visual)

    def test_content_review_policy_allows_focused_capstone_convergence(self) -> None:
        source = Path(production.__file__).read_text(encoding="utf-8")
        self.assertIn("max_content_review_attempts = 6", source)
        self.assertIn("max_content_review_attempts - 1", source)

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

    def test_design_review_allows_bold_teaching_lead_ins(self) -> None:
        seed = type("Seed", (), {"title": "Course"})()
        lesson = {"lesson_number": 1, "title": "Lesson"}
        prompt = production.reviewer_prompt("design_review", seed, lesson, "# Section 01 - Work\n\n**Plan the work.** Teaching prose.", {"sources": []})
        self.assertIn("Bold lead-ins used to introduce a teaching paragraph or list are explicitly allowed", prompt)
        self.assertIn("entire section body contains only one line", prompt)

    def test_targeted_revision_review_does_not_reopen_unrelated_baseline_issues(self) -> None:
        seed = type("Seed", (), {"title": "Course"})()
        lesson = {"lesson_number": 6, "title": "Control the Money"}
        baseline = "# Section 01 - Controls\n\nOld box text.\n\n# Section 02 - Forecasting\n\nUnchanged material."
        candidate = "# Section 01 - Controls\n\nSimplified box text.\n\n# Section 02 - Forecasting\n\nUnchanged material."

        prompt = production.reviewer_prompt(
            "pedagogy_review",
            seed,
            lesson,
            candidate,
            {"sources": []},
            approved_baseline=baseline,
            operator_revision_request="Simplify the box text.",
            operator_allowed_headings={"# Section 01 - Controls"},
        )

        self.assertIn("targeted revision of an operator-approved baseline", prompt)
        self.assertIn("Do not reopen or fail a condition already present", prompt)
        self.assertIn("only the following section headings may change", prompt)
        self.assertIn("# Section 01 - Controls", prompt)
        self.assertIn("-Old box text.", prompt)
        self.assertIn("+Simplified box text.", prompt)

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
        draft = "# Resumo e Principais Conclusões\n\n* Um.\n* Dois.\n* Três.\n* Quatro.\n\n# Referências\n\n- Saída do modelo."
        normalized = production.force_student_references(draft, "# References\n\n- Fonte validada.", "pt_br")
        self.assertEqual(1, normalized.count("# Referências"))
        self.assertNotIn("# References", normalized)
        self.assertNotIn("Saída do modelo", normalized)
        self.assertIn("Fonte validada", normalized)
        self.assertIn("* Um.", normalized)

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
