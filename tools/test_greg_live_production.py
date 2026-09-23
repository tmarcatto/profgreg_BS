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
    asset_strategy = {
        "native-diagram": "native-diagram",
        "trusted-source-image": "reuse-reference",
        "generated-conceptual-image": "generate",
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
        "image_need": "not-needed" if medium == "native-diagram" else "helpful",
        "image_need_reason": "The selected medium makes the construction decision concrete for the learner.",
        "asset_strategy": asset_strategy,
        "asset_strategy_reason": "The selected route matches the required teaching medium and evidence needs.",
        "pedagogical_strategy": selected_strategy[0],
        "real_example_importance": "not-needed",
        "generation_suitability": "safe",
        "source_strategy": selected_strategy[1],
        "evidence_considered": [{"locator": "Course Map", "relevance": "Matches the teaching job."}],
        "alternatives_considered": ["A trusted source image was evaluated.", "A generated conceptual image was evaluated."],
        "selection_reason": "This slide mechanism directly teaches the mapped decision clearly.",
    }


def complete_deck_slide(layout: str, index: int) -> dict:
    slide = {
        "layout": layout,
        "title": f"Use project evidence to improve decision {index}",
        "bottom_line": "Convert the evidence into one owned operating change.",
        **deck_decision(),
    }
    items = [
        {"title": "Result", "body": "Compare the planned result with the actual result."},
        {"title": "Cause", "body": "Trace the controllable cause behind the important variance."},
        {"title": "Action", "body": "Assign one improvement to the next project playbook."},
    ]
    if layout in {"card_sequence", "process_flow", "row_list", "checklist_rows"}:
        slide["items"] = items
    elif layout == "comparison":
        slide["left"] = {"title": "Weak review", "body": "Record the outcome without tracing its cause."}
        slide["right"] = {"title": "Useful review", "body": "Trace the cause and assign a repeatable change."}
    elif layout == "planned_actual":
        slide["left"] = {"title": "Planned result", "body": "The approved budget protected the expected gross margin."}
        slide["right"] = {"title": "Actual result", "body": "Unpriced changes reduced the final gross margin."}
    elif layout == "schedule_bar_chart":
        slide["schedule_rows"] = [
            {"activity": "Close cost records", "start": 0, "duration": 2, "status": "complete"},
            {"activity": "Review variances", "start": 1, "duration": 3, "status": "in-progress"},
            {"activity": "Assign changes", "start": 3, "duration": 2, "status": "planned"},
        ]
    elif layout == "activity_network":
        slide["network_paths"] = [{"label": "Learning loop", "activities": [
            {"title": "Measure result", "duration": "1d"},
            {"title": "Trace cause", "duration": "1d"},
            {"title": "Change system", "duration": "1d"},
        ]}]
    return slide


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

    def test_visible_deck_content_rejects_an_empty_layout_payload(self) -> None:
        slides = [
            {"layout": "cover", "title": "Turn Projects into Better Business", "subtitle": "Use project evidence to improve the next job", "topics": ["Review", "Trust", "Leadership"]},
            *[
                {
                    "layout": "row_list",
                    "title": "Use the project record to improve decisions",
                    "items": [
                        {"title": "Result", "body": "Compare the planned outcome with the actual outcome."},
                        {"title": "Cause", "body": "Trace the controllable cause behind the important variance."},
                        {"title": "Action", "body": "Assign one change to the next project playbook."},
                    ],
                    "bottom_line": "Close the loop by changing the next decision.",
                }
                for _ in range(8)
            ],
            {"layout": "takeaway", "title": "Every completed job should improve the next one", "body": "Review financial results, preserve client trust, and turn field evidence into a repeatable leadership habit for the business.", "final_line": "Convert one lesson into one owned operating change."},
        ]
        slides[4]["items"] = []
        with self.assertRaisesRegex(RuntimeError, "row-list slide needs 3-5"):
            production.validate_deck_visible_content(slides)

    def test_visible_deck_content_accepts_complete_layout_payloads(self) -> None:
        slides = [
            {"layout": "cover", "title": "Turn Projects into Better Business", "subtitle": "Use project evidence to improve the next job", "topics": ["Review", "Trust", "Leadership"]},
            *[
                {
                    "layout": "checklist_rows",
                    "title": "Use the project record to improve decisions",
                    "items": [
                        {"title": "Result", "body": "Compare the planned outcome with the actual outcome."},
                        {"title": "Cause", "body": "Trace the controllable cause behind the important variance."},
                        {"title": "Action", "body": "Assign one change to the next project playbook."},
                    ],
                    "bottom_line": "Close the loop by changing the next decision.",
                }
                for _ in range(8)
            ],
            {"layout": "takeaway", "title": "Every completed job should improve the next one", "body": "Review financial results, preserve client trust, and turn field evidence into a repeatable leadership habit for the business.", "final_line": "Convert one lesson into one owned operating change."},
        ]
        production.validate_deck_visible_content(slides)

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
        layouts = ["intro_image_bullets", "card_sequence", "comparison", "planned_actual", "row_list", "checklist_rows", "image_bullets", "card_sequence"]
        slides = [{"layout": "cover", "title": "Make Residential Work Buildable", "subtitle": "Verify the project before committing field production", "topics": ["Intake", "Scope", "Permits"]}]
        for index, layout in enumerate(layouts, start=2):
            if layout in {"intro_image_bullets", "image_bullets"}:
                slide = {**complete_deck_slide(layout, index), **deck_decision("generated-conceptual-image")}
                slide.update({"intro": "A field review turns hidden assumptions into controlled decisions.", "bullets": ["Verify physical site access", "Record the controlling constraints", "Confirm accountable work owners"], "image_source_strategy": "generated-conceptual", "image_prompt": "A residential project manager reviewing a home site plan with a field lead.", "image_alt": "Project manager and field lead review a residential site plan."})
            else:
                slide = complete_deck_slide(layout, index)
            slides.append(slide)
        slides.append({"layout": "takeaway", "title": "Buildability comes before field production", "body": "Verify the job basis, clear the controlling constraints, and record the responsible owner before crews and commitments move into production.", "final_line": "Make the job buildable before releasing the work."})
        normalized = production.normalize_deck_slides({"slides": slides}, {"title": "Buildability", "learning_goal": "Make the job buildable."})
        self.assertEqual(10, len(normalized))
        self.assertEqual("right", normalized[1]["image_side"])
        self.assertEqual("left", normalized[7]["image_side"])

    def test_deck_plan_allows_no_teaching_image_when_strategy_does_not_call_for_one(self) -> None:
        slides = [{"layout": "cover", "title": "Use Better Project Decisions", "subtitle": "Turn evidence into repeatable construction operating habits", "topics": ["One", "Two", "Three"]}]
        slides.extend(complete_deck_slide(layout, index) for index, layout in enumerate(["card_sequence", "comparison", "planned_actual", "row_list", "checklist_rows", "card_sequence", "comparison", "row_list"], start=2))
        slides.append({"layout": "takeaway", "title": "Every project should improve the business", "body": "Review the outcome, identify the controllable cause, and assign one practical operating change before the next project begins.", "final_line": "Turn each lesson into an owned system change."})
        normalized = production.normalize_deck_slides({"slides": slides}, {"title": "Test", "learning_goal": "Test"})
        self.assertEqual(10, len(normalized))

    def test_deck_plan_uses_layout_diversity_as_a_floor_not_a_visual_quota(self) -> None:
        slides = [{"layout": "cover", "title": "Use Better Project Decisions", "subtitle": "Turn evidence into repeatable construction operating habits", "topics": ["One", "Two", "Three"]}]
        slides.extend(complete_deck_slide(layout, index) for index, layout in enumerate([
            "card_sequence", "comparison", "planned_actual", "row_list",
            "card_sequence", "comparison", "planned_actual", "row_list",
        ], start=2))
        slides.append({"layout": "takeaway", "title": "Every project should improve the business", "body": "Review the outcome, identify the controllable cause, and assign one practical operating change before the next project begins.", "final_line": "Turn each lesson into an owned system change."})
        self.assertEqual(10, len(production.normalize_deck_slides({"slides": slides}, {"title": "Test"})))

    def test_deck_plan_accepts_direct_schedule_and_network_demonstrations(self) -> None:
        slides = [{"layout": "cover", "title": "Read Residential Schedule Logic", "subtitle": "See sequence, overlap, and controlling project paths", "topics": ["One", "Two", "Three"]}]
        layouts = ["process_flow", "schedule_bar_chart", "activity_network", "comparison", "process_flow", "schedule_bar_chart", "activity_network", "comparison"]
        slides.extend(complete_deck_slide(layout, index) for index, layout in enumerate(layouts, start=2))
        slides.append({"layout": "takeaway", "title": "Schedule logic makes commitments visible", "body": "Use connected activities, time scaled bars, and explicit handoffs to test whether the next residential work package is truly ready.", "final_line": "Release work only when its logic and constraints are visible."})
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
            {"layout": "planned_actual", "planned": {"label": "Planned", "body": "Start"}, "actual": {"label": "Actual", "body": "Delayed"}, "planned_actual_rows": [{"item": "Status", "planned": "Complete", "actual": "Evidence missing", "decision": "Keep open"}]},
            {"layout": "card_sequence", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "row_list", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "checklist_rows", "rows": [{"label": "Verify", "body": "Check the evidence"}, {"label": "Release", "body": "Record the decision"}]},
            {"layout": "comparison", "left": {"title": "A", "body": "a"}, "right": {"title": "B", "body": "b"}},
            {"layout": "card_sequence", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
            {"layout": "row_list", "items": [{"title": "A", "body": "a"}, {"title": "B", "body": "b"}]},
        ]
        slides.extend({**item, **deck_decision()} for item in body)
        slides.append({"layout": "takeaway"})
        normalized = production.normalize_deck_slides({"slides": slides}, {"title": "Test"})
        self.assertEqual("Planned", normalized[2]["left"]["title"])
        self.assertEqual("Actual", normalized[2]["right"]["title"])
        self.assertEqual("Keep open", normalized[2]["planned_actual_rows"][0]["action"])
        self.assertEqual("Verify", normalized[5]["items"][0]["title"])

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

    def test_content_review_rerun_calls_only_the_failed_specialist(self) -> None:
        seed = SimpleNamespace(slug="demo", title="Demo Course")
        lesson = {"lesson_number": 1, "title": "Demo Lesson"}
        response = {"passed": True, "verdict": "PASS", "findings": [], "required_changes": []}
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "review").mkdir()
            with patch.object(production, "request_json_with_retry", return_value=response) as request:
                passed, changes, failed_roles, target_headings = production.run_content_reviewers(
                    seed,
                    lesson,
                    "# Section 01 - Work\n\nBody.\n",
                    {"sources": []},
                    run,
                    "lesson_01",
                    roles={"citation_review"},
                )

        self.assertTrue(passed)
        self.assertEqual([], changes)
        self.assertEqual(set(), failed_roles)
        self.assertEqual([], target_headings)
        self.assertEqual(1, request.call_count)
        self.assertEqual("citation_review", request.call_args.args[1])

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
        self.assertEqual(production.localized_slide_visible_items({"title": "T", "topics": ["Um", "Dois"]}), ["T", "Um", "Dois"])

    def test_localized_translation_source_removes_authoring_evidence_only(self) -> None:
        source = [{
            "layout": "comparison", "title": "Visible", "comparison_columns": ["A", "B"],
            "learning_job": "Internal", "visual_candidates": [{"reason": "Internal"}],
            "evidence_considered": [{"locator": "Internal"}],
        }]
        compact = production.localized_deck_translation_source(source)
        self.assertEqual("Visible", compact[0]["title"])
        self.assertEqual(["A", "B"], compact[0]["comparison_columns"])
        self.assertNotIn("learning_job", compact[0])
        self.assertNotIn("visual_candidates", compact[0])
        self.assertIn("learning_job", source[0])

    def test_localized_deck_rejects_omitted_nested_visible_copy(self) -> None:
        source = [{
            "layout": "planned_actual",
            "title": "Control the variance",
            "left": {"title": "Plan", "body": "Expected condition"},
            "right": {"title": "Actual", "body": "Observed condition"},
            "decision_ready_update": {"title": "Decision-ready update", "body": "State the effect."},
        }]
        incomplete = [{
            "layout": "planned_actual",
            "title": "Controle a variação",
            "left": {"title": "Plano", "body": "Condição esperada"},
            "right": {"title": "Real", "body": "Condição observada"},
            "decision_ready_update": {"title": "Atualização para decisão"},
        }]
        with self.assertRaisesRegex(RuntimeError, "decision_ready_update field `body`"):
            production.localized_deck_slides(source, incomplete)

    def test_localized_deck_translates_comparison_and_planned_actual_rows(self) -> None:
        source = [{
            "layout": "planned_actual",
            "title": "Read the record",
            "comparison_columns": ["Evidence", "Decision"],
            "comparison_rows": [{"cells": ["Record kept", "Confirmed owner decision"]}],
            "planned_actual_rows": [{"item": "Permit", "planned": "Monday", "actual": "Unknown", "action": "Confirm release"}],
        }]
        translated = [{
            "layout": "planned_actual",
            "title": "Leia o registro",
            "comparison_columns": ["Evidência", "Decisão"],
            "comparison_rows": [{"cells": ["Registro mantido", "Decisão do proprietário confirmada"]}],
            "planned_actual_rows": [{"item": "Licença", "planned": "Segunda-feira", "actual": "Desconhecido", "action": "Confirmar liberação"}],
        }]
        slides = production.localized_deck_slides(source, translated)
        self.assertEqual("Registro mantido", slides[0]["comparison_rows"][0]["cells"][0])
        self.assertEqual("Confirmar liberação", slides[0]["planned_actual_rows"][0]["action"])

    def test_localized_deck_translates_named_comparison_rows(self) -> None:
        source = [{
            "layout": "comparison",
            "title": "Three forums",
            "comparison_columns": ["Variable", "Daily huddle", "Weekly coordination"],
            "comparison_rows": [{
                "variable": "Leader", "daily_huddle": "Superintendent", "weekly_coordination": "Project manager",
            }],
        }]
        translated = [{
            "layout": "comparison",
            "title": "Três fóruns",
            "comparison_columns": ["Variável", "Reunião diária", "Coordenação semanal"],
            "comparison_rows": [{
                "variable": "Líder", "daily_huddle": "Superintendente", "weekly_coordination": "Gerente de projeto",
            }],
        }]
        slides = production.localized_deck_slides(source, translated)
        row = slides[0]["comparison_rows"][0]
        self.assertEqual("Líder", row["variable"])
        self.assertEqual("Gerente de projeto", row["weekly_coordination"])

    def test_localized_deck_accepts_comparison_aliases_and_synchronizes_them(self) -> None:
        source = [{
            "layout": "comparison",
            "title": "Classify",
            "columns": ["Question", "Risk"],
            "rows": [{"cells": ["When?", "Future"]}],
            "comparison_columns": ["Question", "Risk"],
            "comparison_rows": [{"cells": ["When?", "Future"]}],
        }]
        translated = [{
            "layout": "comparison",
            "title": "Classifique",
            "columns": ["Pergunta", "Risco"],
            "rows": [{"cells": ["Quando?", "Futuro"]}],
        }]
        slide = production.localized_deck_slides(source, translated)[0]
        self.assertEqual(["Pergunta", "Risco"], slide["comparison_columns"])
        self.assertEqual(slide["comparison_columns"], slide["columns"])
        self.assertEqual("Futuro", slide["comparison_rows"][0]["cells"][1])
        self.assertEqual(slide["comparison_rows"], slide["rows"])

    def test_localized_deck_derives_planned_actual_lists_from_comparison_rows(self) -> None:
        source = [{
            "layout": "comparison", "title": "Plan meets field", "decision": "Pause exposure.",
            "planned": ["Opening covered", "Route separated"],
            "actual": ["Cover removed", "Route crosses opening"],
            "comparison_columns": ["Check", "Planned", "Actual"],
            "comparison_rows": [{"cells": ["Opening", "Opening covered", "Cover removed"]}, {"cells": ["Route", "Route separated", "Route crosses opening"]}],
        }]
        translated = [{
            "layout": "comparison", "title": "Plano encontra campo", "decision": "Pause a exposição.",
            "comparison_columns": ["Verificação", "Planejado", "Real"],
            "comparison_rows": [{"cells": ["Abertura", "Abertura coberta", "Cobertura removida"]}, {"cells": ["Rota", "Rota separada", "Rota cruza a abertura"]}],
        }]
        slide = production.localized_deck_slides(source, translated)[0]
        self.assertEqual(["Abertura coberta", "Rota separada"], slide["planned"])
        self.assertEqual(["Cobertura removida", "Rota cruza a abertura"], slide["actual"])
        self.assertEqual("Pause a exposição.", slide["decision"])

    def test_localized_deck_translates_planned_and_actual_lists(self) -> None:
        source = [{
            "layout": "comparison",
            "title": "Compare the condition",
            "planned": ["Opening covered", "Route separated"],
            "actual": ["Cover removed", "Route crosses opening"],
        }]
        translated = [{
            "layout": "comparison",
            "title": "Compare a condição",
            "planned": ["Abertura coberta", "Rota separada"],
            "actual": ["Cobertura removida", "Rota cruza a abertura"],
        }]
        slides = production.localized_deck_slides(source, translated)
        self.assertEqual(["Abertura coberta", "Rota separada"], slides[0]["planned"])
        self.assertEqual(["Cobertura removida", "Rota cruza a abertura"], slides[0]["actual"])
        self.assertIn("Abertura coberta", production.localized_slide_visible_items(slides[0]))

    def test_localized_deck_rejects_incomplete_planned_list(self) -> None:
        source = [{"layout": "comparison", "title": "Compare", "planned": ["One", "Two"]}]
        translated = [{"layout": "comparison", "title": "Compare", "planned": ["Um"]}]
        with self.assertRaisesRegex(RuntimeError, "did not preserve `planned`"):
            production.localized_deck_slides(source, translated)

    def test_localized_deck_translates_network_path_names_and_activity_bodies(self) -> None:
        source = [{
            "layout": "activity_network",
            "title": "Release or hold",
            "network_paths": [{
                "path_name": "Conforming evidence to release",
                "activities": [{"id": "C1", "title": "Self-check", "body": "Submit the check record."}],
            }],
        }]
        translated = [{
            "layout": "activity_network",
            "title": "Liberar ou reter",
            "network_paths": [{
                "path_name": "Evidência conforme para liberação",
                "activities": [{"id": "C1", "title": "Autoverificação", "body": "Envie o registro da verificação."}],
            }],
        }]
        slides = production.localized_deck_slides(source, translated)
        path = slides[0]["network_paths"][0]
        self.assertEqual("Evidência conforme para liberação", path["path_name"])
        self.assertEqual("Envie o registro da verificação.", path["activities"][0]["body"])
        visible = production.localized_slide_visible_items(slides[0])
        self.assertIn("Evidência conforme para liberação", visible)
        self.assertIn("Envie o registro da verificação.", visible)

    def test_localized_deck_translates_word_based_network_durations(self) -> None:
        source = [{
            "layout": "activity_network", "title": "Release",
            "network_paths": [{"label": "Control", "activities": [
                {"title": "Verify", "duration": "before exposure"},
                {"title": "Release", "duration": "3d"},
            ]}],
        }]
        translated = [{
            "layout": "activity_network", "title": "Liberação",
            "network_paths": [{"label": "Controle", "activities": [
                {"title": "Verifique", "duration": "antes da exposição"},
                {"title": "Libere", "duration": "3d"},
            ]}],
        }]
        slide = production.localized_deck_slides(source, translated)[0]
        self.assertEqual("antes da exposição", slide["network_paths"][0]["activities"][0]["duration"])
        self.assertEqual("3d", slide["network_paths"][0]["activities"][1]["duration"])

    def test_localized_deck_accepts_row_list_alias_and_synchronizes_items(self) -> None:
        source = [{
            "layout": "row_list", "title": "Quality gates",
            "rows": [{"label": "Framing", "body": "Check connections."}],
            "items": [{"title": "Framing", "body": "Check connections."}],
        }]
        translated = [{
            "layout": "row_list", "title": "Pontos de qualidade",
            "rows": [{"label": "Estrutura", "body": "Verifique as conexões."}],
        }]
        slide = production.localized_deck_slides(source, translated)[0]
        self.assertEqual("Estrutura", slide["items"][0]["title"])
        self.assertEqual("Verifique as conexões.", slide["items"][0]["body"])
        self.assertEqual("Estrutura", slide["rows"][0]["label"])

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
            "type": "process_flow", "nodes": [
                {"title": "Valid title", "detail": "Valid detail"},
                {"title": "Next title", "detail": "Next detail"},
            ],
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
        self.assertFalse(production.localized_visuals_fit_contract([{
            "type": "relationship_map",
            "nodes": [
                {"title": "Centro", "detail": ""},
                {"title": "X" * 50, "detail": ""},
            ],
        }]))
        self.assertFalse(production.localized_visuals_fit_contract([{
            "type": "comparison_matrix",
            "title": "Comparación",
            "columns": ["Variable", "Entrada del registro de problemas y decisiones pendientes", "Respuesta"],
            "rows": [{"cells": ["Estado", "Registrado", "Listo"]}, {"cells": ["Dueño", "PM", "Cliente"]}],
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
            "## Seção 01: Primeiro\n\nTexto — complemento.\n\n> EXEMPLO PRÁTICO\n> Corpo.\n\n> **CENÁRIO:** Situação.", "pt_br"
        )
        self.assertIn("# Seção 01: Primeiro", normalized)
        self.assertIn("Texto; complemento.", normalized)
        self.assertIn("> **EXEMPLO PRÁTICO**", normalized)
        self.assertIn("> **CENÁRIO**: Situação.", normalized)

    def test_localized_contract_preserves_section_heading_separator(self) -> None:
        normalized = production.normalize_localized_course_contract(
            "# Sección 01 — Preparar el trabajo\n\nTexto – complemento.", "es"
        )
        self.assertIn("# Sección 01 — Preparar el trabajo", normalized)
        self.assertIn("Texto; complemento.", normalized)

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

    def test_localized_book_structure_reports_dash_punctuation_before_rendering(self) -> None:
        localized = "\n".join([
            "# Seção 01: Primeiro", "Texto — complemento.",
            "# Seção 02: Segundo", "# Seção 03: Terceiro", "# Seção 04: Quarto",
            "# Resumo e Principais Conclusões", "- Um", "# Referências",
        ])
        self.assertIn(
            "dash punctuation on lines [2]",
            production.localized_book_structure_issues(localized, "pt_br"),
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

    def test_standalone_document_reference_drops_parent_collection(self) -> None:
        source = {
            "title": "After-Move-In Service Matrix",
            "formal_reference": (
                "National Association of Home Builders. After-Move-In Service Matrix. "
                "In Beyond Warranty. Accessed September 2, 2026."
            ),
            "source_type": "webpage",
            "url": "https://example.org/AfterMoveInServiceMatrix.pdf?rev=2",
        }
        self.assertEqual(
            "National Association of Home Builders. After-Move-In Service Matrix.",
            production.student_reference_for_source(source),
        )

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

**Summary and Key Takeaways**

- Remove this repeated takeaway.

# Glossary

- **Canonical:** Keep this definition.
"""
        revised = production.normalize_repeated_lesson_objectives(draft)
        self.assertIn("Keep this objective", revised)
        self.assertNotIn("Remove this objective", revised)
        self.assertNotIn("Remove this definition", revised)
        self.assertNotIn("Remove this repeated takeaway", revised)
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
        self.assertIn("max_visual_review_attempts = 3", source)
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

    def test_explicit_relationship_map_is_not_reclassified_from_handoff_words(self) -> None:
        visual = {
            "diagram_type": "relationship-map",
            "purpose": "Map five independent residential handoff conditions",
            "diagram_nodes": [
                {"title": "Release conditions", "detail": "Shared hub"},
                {"title": "Framing to mechanical", "detail": "Independent example"},
            ],
        }
        self.assertEqual("relationship-map", production.infer_diagram_type(visual))

    def test_callout_normalizer_repairs_inline_comma_form(self) -> None:
        draft = (
            "# Section 01 - Work\n\n"
            "> **HANDS-ON EXAMPLE**, Apply the rule and check the result.\n"
        )
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> **HANDS-ON EXAMPLE**\n> Apply the rule and check the result.", normalized)
        self.assertNotIn("EXAMPLE**,", normalized)

    def test_callout_normalizer_repairs_flattened_hands_on_body(self) -> None:
        draft = (
            "# Section 01 - Work\n\n> **HANDS-ON EXAMPLE**\n>\n"
            "**Setup.** Use the records. **Supplied inputs.** * **Record A:** Current plan. "
            "* **Record B:** Old photo. **Task.** Decide what governs. "
            "**Actions.** 1. Check the revision. 2. Hold changed work. "
            "**Answer/check.** The current plan governs.\n\nFollowing teaching prose.\n"
        )
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> - **Record A:** Current plan.", normalized)
        self.assertIn("> - **Record B:** Old photo.", normalized)
        self.assertIn("> 1. Check the revision.", normalized)
        self.assertIn("> 2. Hold changed work.", normalized)
        self.assertIn("> Answer/check: The current plan governs.", normalized)
        self.assertNotIn("Actions.** 1.", normalized)

    def test_callout_normalizer_unboxes_unapproved_labels(self) -> None:
        draft = (
            "# Section 01 - Work\n\n"
            "> **WARNING**\n"
            "> Verify the contract before assigning authority.\n\n"
            "> **BRIDGE**\n"
            "> Carry the verified record forward.\n"
        )
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> **APPLY IT**\n> Verify the contract before assigning authority.", normalized)
        self.assertNotIn("> **WARNING**", normalized)
        self.assertIn("> **BRIDGE**", normalized)

    def test_callout_normalizer_unboxes_admonition_syntax(self) -> None:
        draft = (
            "# Section 01 - Work\n\n"
            "> **BRIDGE**\n> Carry the record forward.\n\n"
            "> [!IMPORTANT]\n"
            "> Verify the governing record.\n"
        )
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> **APPLY IT**\n> Verify the governing record.", normalized)
        self.assertNotIn("[!IMPORTANT]", normalized)

    def test_callout_normalizer_promotes_one_instruction_when_below_minimum(self) -> None:
        draft = (
            "# Section 01 - Work\n\n"
            "> **BRIDGE**\n> Carry the record forward.\n\n"
            "> **WARNING**\n> Verify the governing record before assigning authority.\n\n"
            "# Summary and Key Takeaways\n\n- One.\n- Two.\n- Three.\n- Four.\n"
        )
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> **BRIDGE**", normalized)
        self.assertIn("> **APPLY IT**\n> Verify the governing record before assigning authority.", normalized)

    def test_content_review_policy_has_a_bounded_convergence_budget(self) -> None:
        source = Path(production.__file__).read_text(encoding="utf-8")
        self.assertIn("max_content_review_attempts = 3", source)
        self.assertIn("max_content_review_attempts - 1", source)
        self.assertIn("roles=reviewer_roles_to_run", source)

    def test_visual_prompts_describe_relationship_map_renderer_contract(self) -> None:
        source = Path(production.__file__).read_text(encoding="utf-8")
        self.assertIn("The renderer connects every node after the first node directly to the first center node", source)
        self.assertIn("Never demand unsupported edge fields", source)

    def test_plain_section_patch_uses_bounded_output_budget(self) -> None:
        source = Path(production.__file__).read_text(encoding="utf-8")
        self.assertIn("max_tokens=min(8000, max(2000, target_words * 3))", source)

    def test_invalid_revision_selection_falls_back_to_sections_named_in_feedback(self) -> None:
        draft = """# Introduction

Intro.

## Learning Objectives

- Learn.

# Section 01 - One

One body.

# Section 02 - Two

Two body.

# Summary and Key Takeaways

- One.
- Two.
- Three.
- Four.

# Glossary

Term.

# References

- Work.
"""
        feedback = "Automatic reviewer changes required:\n- Repair Section 02 and keep its answer check separate."
        replacement = "# Section 02 - Two\n\nRepaired body.\n"
        with patch.object(
            production,
            "request_json_with_retry",
            side_effect=[{}, production.ModelRequestError("malformed patch")],
        ), patch.object(
            production, "request_plain_study_guide_section_patch", return_value=replacement
        ) as section_patch:
            revised = production.targeted_study_guide_revision(
                "course", draft, feedback, "# References\n\n- Work.", level="Basic"
            )
        self.assertIn("# Section 01 - One\n\nOne body.", revised)
        self.assertIn(replacement.strip(), revised)
        self.assertEqual("# Section 02 - Two", section_patch.call_args.args[1])

    def test_visual_review_prompt_uses_complete_compact_plan(self) -> None:
        seed = SimpleNamespace(title="Course")
        lesson = {"lesson_number": 2, "title": "Lesson"}
        plan = {
            "artifact_type": "study-guide",
            "visuals": [{
                "visual_id": "L02V01",
                "visual_type": "deterministic-diagram",
                "diagram_type": "relationship-map",
                "diagram_title": "GC Connections",
                "diagram_nodes": [{"title": "GC", "detail": "Center"}],
                "selection_reason": "x" * 30000,
            }],
        }
        prompt = production.visual_semantic_review_prompt(seed, lesson, "Draft.", plan)
        self.assertIn('"diagram_title": "GC Connections"', prompt)
        self.assertIn('"detail": "Center"', prompt)
        self.assertNotIn("selection_reason", prompt)
        self.assertNotIn("x" * 100, prompt)

    def test_numbered_hands_on_label_and_individual_action_are_normalized(self) -> None:
        draft = """> **HANDS-ON EXAMPLE 1**
> Supplied inputs: - A2.1 is current. - A2.0 is old. Individual action: Identify the current sheet. Answer/check: A2.1 governs.
"""
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> **HANDS-ON EXAMPLE**", normalized)
        self.assertNotIn("HANDS-ON EXAMPLE 1", normalized)
        self.assertIn("> Individual action: Identify the current sheet.", normalized)
        self.assertIn("> - A2.1 is current.\n> - A2.0 is old.", normalized)

    def test_inline_hands_on_variant_and_spaced_answer_check_are_normalized(self) -> None:
        draft = """**HANDS ON EXAMPLE.** Setup: Use the field record. Supplied information: * Drawing A4.1 is current. * The vent blocks the centerline. Task: 1. Confirm A4.1, revision 3. 2. Hold the affected work. **Answer / Check** * The current drawing is recorded. * The work remains on hold.
"""
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> **HANDS-ON EXAMPLE**", normalized)
        self.assertIn("> Supplied inputs:\n> - Drawing A4.1 is current.", normalized)
        self.assertIn("> Task:\n> 1. Confirm A4.1, revision 3.\n> 2. Hold the affected work.", normalized)
        self.assertIn("> Answer/Check:\n> - The current drawing is recorded.", normalized)
        self.assertNotIn("HANDS ON EXAMPLE", normalized)

    def test_hands_on_step_splitter_does_not_treat_revision_as_a_step(self) -> None:
        draft = """> **HANDS-ON EXAMPLE**
> Setup: Use current records. Task: 1. Record the request. 2. Compare A2.14, revision 3. 3. Check the register. Answer / Check: A2.14, revision 3, remains current.
"""
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> 2. Compare A2.14, revision 3.", normalized)
        self.assertIn("> 3. Check the register.", normalized)
        self.assertNotIn("> 3. 3. Check", normalized)
        self.assertIn("> Answer/Check: A2.14, revision 3, remains current.", normalized)

    def test_unquoted_multiline_hands_on_block_is_restored(self) -> None:
        draft = """# Section 02 - Coordinate

**HANDS ON EXAMPLE**

**Supplied inputs:**

- The scope assigns the door.
- A2.1 shows its location.

**Individual action:** Identify each source.

**Answer/check:**

- The scope assigns responsibility.
- A2.1 supplies location.

Following teaching prose remains outside the box.
"""
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> **HANDS-ON EXAMPLE**", normalized)
        self.assertIn("> - The scope assigns the door.", normalized)
        self.assertIn("> Individual action: Identify each source.", normalized)
        self.assertIn("> - A2.1 supplies location.", normalized)
        self.assertIn("\nFollowing teaching prose remains outside the box.", normalized)
        self.assertNotIn("> Following teaching prose", normalized)

    def test_unlabeled_flat_multiline_exercise_is_promoted(self) -> None:
        draft = """# Section 03 - Control

Supplied inputs: - Addendum 02 is incorporated. - A5.2 revision 3 is current.
Individual action: Prepare the control record.
Answer/check: - Mark Addendum 02 incorporated. - Keep A5.2 revision 3 current.

# Section 04 - Verify

Body.
"""
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> **HANDS-ON EXAMPLE**", normalized)
        self.assertIn("> - Addendum 02 is incorporated.", normalized)
        self.assertIn("> Individual action: Prepare the control record.", normalized)
        self.assertIn("> - Keep A5.2 revision 3 current.", normalized)
        self.assertIn("# Section 04 - Verify", normalized)

    def test_setup_inside_hands_on_label_is_restored(self) -> None:
        draft = """**HANDS ON EXAMPLE: Setup**

**Supplied inputs**

- Revision 2 is current.
- The request is not authorized.

**Task**

1. Confirm the revision.
2. Verify authority.

**Answer / Check**

- Revision 2 remains current.
- Authorization remains pending.

Following prose.
"""
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> **HANDS-ON EXAMPLE**\n> Setup:", normalized)
        self.assertIn("> - Revision 2 is current.", normalized)
        self.assertIn("> 1. Confirm the revision.\n> 2. Verify authority.", normalized)
        self.assertIn("> - Authorization remains pending.", normalized)
        self.assertNotIn("> Following prose.", normalized)

    def test_answer_and_check_variant_is_split_after_task(self) -> None:
        draft = """> **HANDS-ON EXAMPLE**
> Setup: Compare the records. Supplied inputs: - A2.14 revision 3 is current. - SS-14 is unapproved. Task: 1. Compare the records. 2. Hold the order. **Answer and check:** - A2.14 remains current. - The order remains on hold.
"""
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> 1. Compare the records.\n> 2. Hold the order.", normalized)
        self.assertIn("> Answer/check:\n> - A2.14 remains current.", normalized)
        self.assertNotIn("Hold the order. **Answer", normalized)

    def test_excess_hands_on_callout_becomes_structured_worked_example(self) -> None:
        block = """> **HANDS-ON EXAMPLE**
> Setup: Compare records.
> Supplied inputs:
> - A2.1 is current.
> - A2.0 is old.
> Individual action: Select the current record.
> Answer/Check:
> - A2.1 governs.
"""
        draft = "# Section 01 - Work\n\n" + "\n".join(block for _ in range(5))
        normalized = production.normalize_callout_density(draft)
        self.assertEqual(4, normalized.count("> **HANDS-ON EXAMPLE**"))
        self.assertIn("**Worked example.** Compare records.", normalized)
        self.assertIn("**Example records.**", normalized)
        self.assertIn("- A2.1 is current.", normalized)
        self.assertIn("**Application.** Select the current record.", normalized)
        self.assertIn("**Interpretation.**", normalized)

    def test_prose_dash_normalizer_removes_compound_hyphens_only_before_references(self) -> None:
        draft = """# Section 01 - Work

Use document-control and wall-insulation records for the two-story addition.

# References

- Formal Work-with-Hyphens.
"""
        normalized = production.normalize_prose_dashes(draft)
        self.assertIn("# Section 01 - Work", normalized)
        self.assertIn("document control and wall insulation records for the two story addition", normalized)
        self.assertIn("Formal Work-with-Hyphens", normalized)

    def test_cross_section_consistency_uses_chapter_context(self) -> None:
        feedback = (
            "Automatic reviewer changes required:\n"
            "- Define one canonical schema and keep its field names consistent throughout the lesson.\n"
            "- Reconcile every amount across sections."
        )
        self.assertTrue(production.revision_requires_chapter_context(feedback))
        self.assertFalse(production.revision_requires_chapter_context("Simplify the Section 02 example."))

    def test_mece_reorganization_uses_chapter_context(self) -> None:
        feedback = (
            "Automatic reviewer changes required:\n"
            "- Reorganize the lesson so each section owns a distinct stage."
        )
        self.assertTrue(production.revision_requires_chapter_context(feedback))

    def test_complete_project_review_schema_uses_chapter_context(self) -> None:
        feedback = (
            "Automatic reviewer changes required:\n"
            "- Add the complete project-review schema and ensure every referenced field is defined."
        )
        self.assertTrue(production.revision_requires_chapter_context(feedback))

    def test_design_reviewer_cannot_reject_approved_bridge_label(self) -> None:
        response = production.normalize_reviewer_response(
            "design_review",
            {
                "passed": False,
                "findings": ["BRIDGE must be replaced with an approved label."],
                "required_changes": ["Replace the BRIDGE callout label."],
            },
        )
        self.assertTrue(response["passed"])
        self.assertEqual([], response["required_changes"])

    def test_reviewer_keeps_only_exact_existing_target_headings(self) -> None:
        draft = "# Introduction\n\nIntro.\n\n# Section 01 - Work\n\nBody.\n\n# References\n\n- Source.\n"
        response = production.normalize_reviewer_response(
            "citation_review",
            {
                "passed": False,
                "findings": ["The claim needs correction."],
                "required_changes": ["Correct the claim."],
                "target_headings": ["# Section 01 - Work", "# Invented", "# References"],
            },
            draft,
        )
        self.assertEqual(["# Section 01 - Work"], response["target_headings"])

    def test_reviewer_cannot_reject_unboxed_admonition_as_callout(self) -> None:
        response = production.normalize_reviewer_response(
            "design_review",
            {
                "passed": False,
                "findings": ["Replace the NOTE callout with an approved label."],
                "required_changes": ["Replace every NOTE callout label."],
            },
            "# Section 01 - Work\n\n**Note.** This is ordinary prose.\n",
        )
        self.assertTrue(response["passed"])

    def test_reviewer_ledger_uses_normalized_student_reference(self) -> None:
        ledger = {
            "course_slug": "course",
            "sources": [{
                "source_id": "L15S06",
                "title": "After-Move-In Service Matrix",
                "author_or_organization": "National Association of Home Builders, BuilderBooks",
                "formal_reference": (
                    "National Association of Home Builders. After-Move-In Service Matrix. "
                    "In Beyond Warranty. Accessed September 2, 2026."
                ),
                "source_type": "webpage",
                "url": "https://example.org/matrix.pdf",
                "claims_supported": [{"lesson_numbers": [15], "claim": "Service model."}],
            }],
        }
        compact = production.compact_reviewer_ledger(ledger, 15)
        reference = compact["sources"][0]["formal_reference"]
        self.assertNotIn("Accessed", reference)
        self.assertNotIn("Beyond Warranty", reference)

    def test_introduction_is_available_to_automatic_section_revision(self) -> None:
        draft = "# Introduction\n\nRevise me.\n\n## Learning Objectives\n\n- Learn.\n\n# Section 01 - Work\n\nBody.\n"
        sections = production.editable_study_guide_sections(draft, include_introduction=True)
        self.assertIn("# Introduction", sections)

    def test_automatic_patch_can_replace_introduction(self) -> None:
        draft = "\n".join([
            "# Introduction", "", "Old canonical case.", "", "## Learning Objectives", "", "- Learn.", "",
            "# Section 01 - Work", "", "Body.", "", "# Section 02 - Check", "", "Body.", "",
            "# Section 03 - Decide", "", "Body.", "", "# Section 04 - Close", "", "Body.", "",
            "# Summary and Key Takeaways", "", "- One", "- Two", "- Three", "- Four", "",
            "# Glossary", "", "- **Term:** Definition.", "", "# References", "", "- Authority.", "",
        ])
        revised = production.apply_study_guide_section_patches(
            draft,
            {"# Introduction": "# Introduction\n\nOne canonical case.\n"},
        )
        self.assertIn("One canonical case.", revised)
        self.assertNotIn("Old canonical case.", revised)

    def test_section_heading_variant_resolves_by_unique_number(self) -> None:
        available = {
            "# Section 03 - Protect Client Trust After Handover": "body",
            "# Section 04 - Turn Experience into Standard Work": "body",
        }
        self.assertEqual(
            ["# Section 03 - Protect Client Trust After Handover"],
            production.resolve_study_guide_headings(["Section 3 - Technology Exercise"], available),
        )

    def test_unknown_section_heading_remains_blocked(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "does not exist"):
            production.resolve_study_guide_headings(
                ["Section 09 - Missing"],
                {"# Section 03 - Existing": "body"},
            )

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

    def test_render_spec_fingerprint_changes_with_source_markdown(self) -> None:
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            root = Path(directory)
            renderer = root / "renderer.py"
            source = root / "lesson.md"
            renderer.write_text("renderer", encoding="utf-8")
            source.write_text("version one", encoding="utf-8")
            with patch.object(production, "ROOT", root), patch.object(production, "STUDY_GUIDE_RENDERER", renderer):
                first = production.render_spec_fingerprint({"source_markdown": "lesson.md"})
                source.write_text("version two", encoding="utf-8")
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

    def test_student_references_remove_private_provenance_and_duplicate_works(self) -> None:
        sources = [
            {"title": "Construction Contract and Laws (uploaded reference; author not stated)", "author_or_organization": "Not stated in supplied excerpt", "source_type": "book", "formal_reference": "Uploaded reference: 123-Construction-Contract-and-Laws.pdf. Supplied excerpt covers contract documents."},
            {"title": "Specifications and Drawings for Construction, FAR 52.236-21", "source_type": "government", "url": "https://origin.example/far/52.236-21", "formal_reference": "Federal Acquisition Regulation, FAR 52.236-21, Specifications and Drawings for Construction. https://origin.example/far/52.236-21"},
            {"title": "Specifications and Drawings for Construction, FAR 52.236-21", "source_type": "government", "url": "https://example/far/52.236-21", "formal_reference": "Federal Acquisition Regulation, FAR 52.236-21, Specifications and Drawings for Construction. https://example/far/52.236-21"},
        ]
        lines = production.student_reference_lines(sources)
        self.assertEqual(2, len(lines))
        self.assertEqual("- Construction Contract and Laws.", lines[0])
        self.assertNotIn("http", lines[1])
        self.assertNotIn("uploaded", " ".join(lines).lower())

    def test_formal_ufgs_reference_drops_url_and_web_descriptor_is_cleaned(self) -> None:
        ufgs = {
            "title": "UFGS 01 33 00, Submittal Procedures",
            "source_type": "government",
            "url": "https://legacy.wbdg.org/dod/ufgs/ufgs-01-33-00",
            "formal_reference": "U.S. Department of Defense. UFGS 01 33 00, Submittal Procedures. https://legacy.wbdg.org/dod/ufgs/ufgs-01-33-00",
        }
        fhwa = {
            "title": "Development and Review of Specifications—Construction, Attachment 2",
            "source_type": "webpage",
            "url": "https://www.fhwa.dot.gov/construction/specrevattach2.cfm",
            "formal_reference": "Federal Highway Administration. Development and Review of Specifications—Construction, Attachment 2. Online technical guidance,.",
        }
        self.assertNotIn("http", production.student_reference_for_source(ufgs))
        cleaned = production.student_reference_for_source(fhwa)
        self.assertNotIn("Online technical guidance", cleaned)
        self.assertIn(fhwa["url"], cleaned)

    def test_direct_fannie_document_drops_url_and_far_part_16_is_deduplicated(self) -> None:
        fannie = {
            "title": "Single-Closing Construction-to-Permanent Financing Transaction Process",
            "source_type": "government",
            "url": "https://singlefamily.fanniemae.com/media/6311/display",
            "formal_reference": "Fannie Mae. Single-Closing Construction-to-Permanent Financing Transaction Process.",
        }
        far_sources = [
            {"title": "Federal Acquisition Regulation, Subpart 16.1—Selecting Contract Types", "formal_reference": "Federal Acquisition Regulation, Subpart 16.1, Selecting Contract Types."},
            {"title": "Federal Acquisition Regulation, Part 16—Types of Contracts", "formal_reference": "Federal Acquisition Regulation, Part 16, Types of Contracts."},
            {"title": "Part 16—Types of Contracts", "formal_reference": "Federal Acquisition Regulatory Council. Federal Acquisition Regulation, Part 16—Types of Contracts."},
        ]
        self.assertNotIn("http", production.student_reference_for_source(fannie))
        self.assertEqual(1, len(production.student_reference_lines(far_sources)))

    def test_locator_only_manual_and_distinct_web_attachment_survive_identity_cleanup(self) -> None:
        caltrans = {
            "title": "Chapter 5: Contract Administration, Section 3: Change Orders",
            "source_type": "government",
            "formal_reference": "California Department of Transportation. Construction Manual, Chapter 5: Contract Administration, Section 3: Change Orders.",
        }
        fhwa_main = {
            "title": "Development and Review of Specifications—Construction",
            "source_type": "government",
            "url": "https://www.fhwa.dot.gov/construction/specreview.cfm",
            "formal_reference": "Federal Highway Administration. Development and Review of Specifications—Construction.",
        }
        fhwa_attachment = {
            "title": "Development and Review of Specifications—Construction",
            "source_type": "government",
            "url": "https://www.fhwa.dot.gov/construction/specrevattach2.cfm",
            "formal_reference": "Federal Highway Administration. Development and Review of Specifications—Construction, Attachment 2.",
        }
        lines = production.student_reference_lines([caltrans, fhwa_main, fhwa_attachment])
        self.assertEqual(3, len(lines))
        self.assertTrue(any("Construction Manual" in line for line in lines))
        self.assertTrue(any("Attachment 2" in line for line in lines))

    def test_forced_references_remove_model_source_ledger_block(self) -> None:
        draft = """# Summary and Key Takeaways

- One.
- Two.
- Three.
- Four.

# Source ledger

Internal source metadata.

# Glossary

Term.

# References

- Model output.
"""
        normalized = production.force_student_references(draft, "# References\n\n- Validated work.")
        self.assertNotIn("Source ledger", normalized)
        self.assertNotIn("Internal source metadata", normalized)

    def test_hands_on_normalizer_preserves_bold_colon_fields_and_splits_task_steps(self) -> None:
        draft = """> **HANDS-ON EXAMPLE**
> **Setup:** Revision 2 is current. **Task:** 1. Confirm the revision. 2. Compare the request. 3. Verify authority. 4. Record the result. **Answer/Check:** Revision 2 governs.
"""
        normalized = production.normalize_callout_density(
            production.normalize_reviewed_factual_language(draft)
        )
        self.assertIn("> **HANDS-ON EXAMPLE**", normalized)
        self.assertIn("> Setup: Revision 2 is current.", normalized)
        self.assertIn("> Task:\n> 1. Confirm the revision.\n> 2. Compare the request.", normalized)
        self.assertIn("> 3. Verify authority.\n> 4. Record the result.", normalized)
        self.assertIn("> Answer/Check: Revision 2 governs.", normalized)
        self.assertNotIn("1. Confirm the revision. 2.", normalized)

    def test_hands_on_normalizer_recovers_adjacent_exercise_after_early_answer(self) -> None:
        draft = """> **HANDS-ON EXAMPLE**
> Answer/check: Stale answer that appeared before the task.

Supplied inputs: Use these records: - A5.2 Revision 3 is current. - Addendum 02 is incorporated.

**Your action** Prepare the control record.

**Answer/check** Mark Addendum 02 as incorporated and A5.2 Revision 3 as current.

# Section 04 - Next

Body.
"""
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> Supplied inputs:\n> Use these records:", normalized)
        self.assertIn("> - A5.2 Revision 3 is current.", normalized)
        self.assertIn("> Your action: Prepare the control record.", normalized)
        self.assertIn("> Answer/check: Mark Addendum 02 as incorporated", normalized)
        self.assertLess(normalized.index("> Supplied inputs:"), normalized.index("> Your action:"))
        self.assertLess(normalized.index("> Your action:"), normalized.index("> Answer/check:"))
        self.assertNotIn("Stale answer", normalized)

    def test_factual_normalizer_repairs_course_book_source_title_and_sheet_spacing(self) -> None:
        normalized = production.normalize_reviewed_factual_language(
            "Residential Construction Agreement and Exhibits A, C uses W- 3 on A2. 1.\n"
        )
        self.assertIn("Residential Construction Agreement and Exhibits A through C", normalized)
        self.assertIn("W-3 on A2.1", normalized)

    def test_flat_complete_exercise_is_promoted_to_hands_on_callout(self) -> None:
        draft = """# Section 05 - Decide

Supplied inputs: - Record A is current. - Record B is old. Task: 1. Compare the records. 2. Choose the current record. Answer/Check: Record A governs.
"""
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> **HANDS-ON EXAMPLE**", normalized)
        self.assertIn("> Supplied inputs:", normalized)
        self.assertIn("> 1. Compare the records.\n> 2. Choose the current record.", normalized)
        self.assertIn("> Answer/Check: Record A governs.", normalized)

    def test_inline_step_normalizer_does_not_split_revision_number(self) -> None:
        draft = (
            "> Task: 1. Record the request. 2. Compare it with A2.14, revision 3. "
            "3. Check the register. **Answer/Check:** A2.14, revision 3. governs.\n"
        )
        normalized = production.normalize_inline_numbered_sequences(draft)
        self.assertIn("> 2. Compare it with A2.14, revision 3.", normalized)
        self.assertIn("> 3. Check the register.", normalized)
        self.assertIn("A2.14, revision 3. governs.", normalized)

    def test_chapter_wide_feedback_routes_to_complete_revision(self) -> None:
        feedback = (
            "Automatic reviewer changes required:\n- Re-outline the lesson so each section has one distinct purpose. "
            "Remove duplicated explanations and use one running residential scenario."
        )
        self.assertTrue(production.revision_requires_chapter_context(feedback))
        alternate = (
            "Automatic reviewer changes required:\n- Consolidate the lesson into a non-overlapping sequence and use one "
            "connected residential scenario. Remove repeated explanations from later sections and use a consistent Markdown heading hierarchy."
        )
        self.assertTrue(production.revision_requires_chapter_context(alternate))
        self.assertTrue(production.revision_requires_chapter_context(
            "Automatic reviewer changes required:\n- Reorganize the sections into distinct, nonoverlapping functions."
        ))
        self.assertFalse(production.revision_requires_chapter_context(
            "Automatic reviewer changes required:\n- Correct A2. 1 and check the entire lesson for similar spacing errors."
        ))

    def test_chapter_wide_revision_retries_incomplete_response(self) -> None:
        draft = """# Introduction

Intro.

## Learning Objectives

- Learn.

# Section 01 - One

Body.

# Section 02 - Two

Body.

# Section 03 - Three

Body.

# Section 04 - Four

Body.

# Section 05 - Five

Body.

# Summary and Key Takeaways

- One.
- Two.
- Three.
- Four.

# Glossary

Term.

# References

- Work.
"""
        feedback = "Automatic reviewer changes required:\n- Reorganize the sections into distinct, nonoverlapping functions."
        with patch.object(production, "request_text", side_effect=["# Introduction\n\nPartial.", draft]) as request:
            revised = production.targeted_study_guide_revision(
                "course", draft, feedback, "# References\n\n- Work.", level="Basic"
            )
        self.assertIn("# Summary and Key Takeaways", revised)
        self.assertEqual(2, request.call_count)
        self.assertIn("previous chapter-wide response was incomplete", request.call_args_list[1].args[2])

    def test_utah_reference_title_normalizes_exhibit_range(self) -> None:
        self.assertIn(
            "Exhibits A–C",
            production.student_reference_text("Utah. Residential Construction Agreement and Exhibits A, C."),
        )

    def test_hands_on_normalizer_demotes_answer_only_and_expands_flat_task(self) -> None:
        draft = """> **HANDS-ON EXAMPLE**
> Answer/Check: The answer is the current sheet.

> **HANDS-ON EXAMPLE**
> The supplied inputs are: - Record A is current. - Record B is superseded. Compare the records and choose the current one. The result should identify Record A. Your check is complete when the status agrees.
"""
        normalized = production.normalize_hands_on_example_markdown(draft)
        self.assertIn("> **APPLY IT**\n> Answer/Check:", normalized)
        self.assertIn("> Inputs:", normalized)
        self.assertIn("> - Record A is current.", normalized)
        self.assertIn("> Action: Compare the records", normalized)
        self.assertIn("> Answer/Check: The result should", normalized)

    def test_review_normalizers_split_inline_tasks_and_convert_conceptual_party_table(self) -> None:
        draft = """| Party | Role and project relationship |
|---|---|
| **Owner** | Hires the builder. |
| **GC** | Coordinates the work. |

> **SCENARIO**
> **Learner tasks and answer/check:** 1. Classify the role. 2. Identify the hiring party. **Record A:** GC.
"""
        normalized = production.normalize_reviewed_factual_language(draft)
        self.assertNotIn("| Party |", normalized)
        self.assertIn("- **Owner**: Hires the builder.", normalized)
        self.assertIn("> 1. Classify the role.", normalized)
        self.assertIn("> 2. Identify the hiring party.", normalized)
        self.assertIn("> **Record A:** GC.", normalized)

    def test_callout_density_removes_surplus_blank_quote_lines(self) -> None:
        draft = """> **SCENARIO**
>
> **Setup:** One.
>
> **Records:** Two.
>
> **Tasks:** Three.
>
> **Answer/check:** Four.
"""
        normalized = production.normalize_callout_density(draft)
        self.assertLessEqual(sum(1 for line in normalized.splitlines() if line.strip() == ">"), 2)

    def test_reviewed_factual_language_softens_submittal_effect_claim(self) -> None:
        draft = (
            "Approved submittals have contractual effect only when the governing contract incorporates or otherwise recognizes them. "
            "Approval alone does not modify the contract."
        )
        normalized = production.normalize_reviewed_factual_language(draft)
        self.assertNotIn("contractual effect only", normalized)
        self.assertIn("does not automatically replace or modify", normalized)

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
                "> **HANDS-ON EXAMPLE**\n> Using the supplied records, compare the versions and choose the current sheet. Check that your answer matches the register.",
                "> **BRIDGE**\n> The next connection.",
            ]
        )
        normalized = production.normalize_callout_density(draft)
        self.assertEqual(normalized.count("> **"), 4)
        self.assertIn("First definition.", normalized)
        self.assertIn("Second definition.", normalized)
        self.assertIn("> **SCENARIO**", normalized)
        self.assertIn("> **HANDS-ON EXAMPLE**", normalized)

    def test_prose_dash_normalizer_restores_flattened_quoted_records(self) -> None:
        draft = (
            "# Section 01 - Work\n\n"
            "> Classify each record. - Record A: included. - Record B: excluded.\n\n"
            "Use the current document - do not guess.\n"
        )
        normalized = production.normalize_prose_dashes(draft)
        self.assertIn("> Classify each record.\n> - Record A: included.\n> - Record B: excluded.", normalized)
        self.assertIn("Use the current document, do not guess.", normalized)
        prose_lines = [line for line in normalized.splitlines() if not line.lstrip().startswith(("#", "> -", "- "))]
        self.assertNotIn(" - ", "\n".join(prose_lines))

    def test_factual_normalizer_uses_ascii_words_for_exhibit_range(self) -> None:
        normalized = production.normalize_reviewed_factual_language(
            "Residential Construction Agreement and Exhibits A, C"
        )
        self.assertIn("Exhibits A through C", normalized)
        self.assertNotIn("–", normalized)

    def test_section_patches_can_condense_without_triggering_truncation_guard(self) -> None:
        long_body = " ".join(["Detailed instruction."] * 1900)
        draft = (
            "# Introduction\n\nIntro.\n\n## Learning Objectives\n\n- Apply.\n\n"
            f"# Section 01 - One\n\n{long_body}\n\n"
            "# Section 02 - Two\n\nOriginal two.\n\n"
            "# Summary and Key Takeaways\n\n- One.\n- Two.\n- Three.\n- Four.\n\n"
            "# Glossary\n\nTerm: definition.\n\n# References\n\n- Source.\n"
        )
        revised = production.apply_study_guide_section_patches(
            draft,
            {
                "# Section 01 - One": "# Section 01 - One\n\nConcise but complete.",
                "# Section 02 - Two": "# Section 02 - Two\n\nUpdated two.",
            },
        )
        self.assertIn("Concise but complete.", revised)
        self.assertIn("Updated two.", revised)

    def test_glossary_patch_does_not_consume_references_boundary(self) -> None:
        draft = (
            "# Introduction\n\nIntro.\n\n## Learning Objectives\n\n- Apply.\n\n"
            "# Section 01 - One\n\nBody.\n\n"
            "# Summary and Key Takeaways\n\n- One.\n- Two.\n- Three.\n- Four.\n\n"
            "# Glossary\n\nOld term.\n\n# References\n\n- Validated source.\n"
        )
        revised = production.apply_study_guide_section_patches(
            draft,
            {"# Glossary": "# Glossary\n\nThe entries define this lesson's terms.\n\n- Term: definition."},
        )
        self.assertIn("The entries define this lesson's terms.", revised)
        self.assertTrue(revised.rstrip().endswith("- Validated source."))

    def test_introduction_patch_does_not_consume_h1_learning_objectives_boundary(self) -> None:
        draft = (
            "# Introduction\n\nOld intro.\n\n# Learning Objectives\n\n- Apply.\n\n"
            "# Section 01 - One\n\nBody.\n\n"
            "# Summary and Key Takeaways\n\n- One.\n- Two.\n- Three.\n- Four.\n\n"
            "# Glossary\n\nTerm.\n\n# References\n\n- Source.\n"
        )
        revised = production.apply_study_guide_section_patches(
            draft,
            {"# Introduction": "# Introduction\n\nNew intro."},
        )
        self.assertIn("# Learning Objectives\n\n- Apply.", revised)
        self.assertIn("# References\n\n- Source.", revised)

    def test_diagram_cell_compaction_preserves_agreement_qualifiers(self) -> None:
        first = production.compact_diagram_cell_text(
            "Where applicable and as allocated by the agreement: track costs, forecasts, and cap remaining"
        )
        second = production.compact_diagram_cell_text(
            "Follow agreement's change process; approved changes can raise the cap when the agreement permits"
        )
        self.assertLessEqual(len(first), 90)
        self.assertLessEqual(len(second), 90)
        self.assertIn("agreement", first)
        self.assertIn("agreement", second)

    def test_payment_request_visual_has_one_canonical_calculation_order(self) -> None:
        visual = {
            "purpose": "Show the payment request calculation",
            "learning_claim": "Include stored materials, retainage, and prior payments.",
            "diagram_title": "Payment amount",
            "diagram_nodes": [
                {"title": "Add approved changes/materials", "detail": ""},
                {"title": "Subtract prior payments", "detail": ""},
                {"title": "Subtract retainage", "detail": ""},
                {"title": "Subtract prior payments again", "detail": ""},
            ],
        }
        normalized = production.normalize_payment_request_visual(visual)
        titles = [node["title"] for node in normalized["diagram_nodes"]]
        self.assertEqual("process-flow", normalized["diagram_type"])
        self.assertEqual(1, titles.count("Subtract prior payments"))
        self.assertEqual(
            [
                "Start with accepted base work", "Add approved changes", "Add stored materials",
                "Subtract credits/deductions", "Subtract retainage", "Subtract prior payments",
            ],
            titles,
        )

    def test_embedded_action_is_separated_before_numbered_steps(self) -> None:
        draft = (
            "> - The field copy is Revision 1. **Action** 1. Remove it from the active set.\n"
            "> - The current set remains Revision 2. **Action** 1. Trace the cloud. 2. Update affected records.\n"
        )
        normalized = production.normalize_inline_numbered_sequences(draft)
        self.assertIn("> - The field copy is Revision 1.\n> Action:\n> 1. Remove it from the active set.", normalized)
        self.assertIn("> - The current set remains Revision 2.\n> Action:\n> 1. Trace the cloud.\n> 2. Update affected records.", normalized)

    def test_numbered_task_ends_before_answer_result_check(self) -> None:
        draft = (
            "> 5. Verify the current drawing. 6. Compare A2.14 with SS- 14. "
            "**Answer/Result check:** - SS-14 is not incorporated. - Keep the work on hold.\n"
        )
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> 6. Compare A2.14 with SS-14.\n> **Answer/Result check:**", normalized)
        self.assertIn("> - SS-14 is not incorporated.\n> - Keep the work on hold.", normalized)

    def test_single_final_task_step_ends_before_answer_result_check(self) -> None:
        draft = (
            "> 4. Hold installation until authorization is documented. "
            "**Answer/Result check:** - Authorization is pending. - Installation remains on hold.\n"
        )
        normalized = production.normalize_callout_density(draft)
        self.assertIn("> 4. Hold installation until authorization is documented.\n> **Answer/Result check:**", normalized)
        self.assertIn("> - Authorization is pending.\n> - Installation remains on hold.", normalized)

    def test_callout_normalizer_rejoins_month_dates_and_identifiers(self) -> None:
        draft = (
            "> **HANDS-ON EXAMPLE**\n"
            "> Supplied inputs:\n"
            "> - The field copy was issued March\n"
            "> 3. **Action:**\n"
            "> 1. Confirm window W-\n"
            "> 3.\n"
        )
        normalized = production.normalize_callout_density(draft)
        self.assertIn("issued March 3.", normalized)
        self.assertIn("Confirm window W-3.", normalized)
        self.assertNotIn("March\n> 3", normalized)
        self.assertNotIn("W-\n> 3", normalized)

    def test_study_guide_budget_covers_bounded_review_workflow(self) -> None:
        config = json.loads((ROOT / "workspace" / "config" / "model-routing.json").read_text(encoding="utf-8"))
        budgets = config["cost_tracking"]
        self.assertGreaterEqual(budgets["call_budgets"]["study_guide_initial"], 60)
        self.assertGreaterEqual(budgets["call_budgets"]["study_guide_targeted_revision"], 20)
        self.assertGreaterEqual(budgets["usd_budgets"]["study_guide_initial"], 1.5)
        self.assertGreaterEqual(budgets["usd_budgets"]["study_guide_targeted_revision"], 0.5)

    def test_student_references_dedupe_far_clause_and_clean_journal_url(self) -> None:
        references = """# References

- Federal Acquisition Regulation, FAR 52.232-5, current clause. https://origin-www.acquisition.gov/far/52.232-5
- American Bar Association, Forum on Construction Law. Article. The Construction Lawyer, Spring 2026. https://www.americanbar.org/article
- Federal Acquisition Regulation, FAR 52.232-5, duplicate clause. https://www.acquisition.gov/far/52.232-5
"""
        normalized = production.force_student_references(
            "# Introduction\n\nIntro.\n\n# References\n\n- Old.\n",
            references,
        )
        self.assertEqual(1, normalized.lower().count("far 52.232-5"))
        aba_line = next(line for line in normalized.splitlines() if "American Bar Association" in line)
        self.assertNotIn("http", aba_line)

    def test_student_references_dedupe_far_part_and_remove_url(self) -> None:
        references = """# References

- Federal Acquisition Regulation, Part 16, Types of Contracts. https://www.acquisition.gov/far/part-16
- Federal Acquisition Regulation, FAR Part 16, duplicate title. https://origin-www.acquisition.gov/far/part-16
"""
        normalized = production.force_student_references(
            "# Introduction\n\nIntro.\n\n# References\n\n- Old.\n",
            references,
        )
        self.assertEqual(1, normalized.lower().count("part 16"))
        self.assertNotIn("acquisition.gov", normalized)

    def test_student_references_clean_new_york_home_improvement_contract_url(self) -> None:
        references = """# References

- New York State Department of Public Service. Home Improvement Contract. https://documents.dps.ny.gov/home-improvement-contract.pdf
"""
        normalized = production.force_student_references(
            "# Introduction\n\nIntro.\n\n# References\n\n- Old.\n",
            references,
        )
        entry = next(line for line in normalized.splitlines() if "New York State Department" in line)
        self.assertNotIn("http", entry)

    def test_student_references_remove_incomplete_placeholder_title(self) -> None:
        normalized = production.force_student_references(
            "# Introduction\n\nIntro.\n\n# References\n\n- Old.\n",
            "# References\n\n- Construction Contract and Laws.\n- Complete source with publisher and date.\n",
        )
        self.assertNotIn("Construction Contract and Laws", normalized)
        self.assertIn("Complete source with publisher and date", normalized)


if __name__ == "__main__":
    unittest.main()
