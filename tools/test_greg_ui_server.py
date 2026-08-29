from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
MODULE_PATH = ROOT / "tools" / "greg_ui_server.py"
spec = importlib.util.spec_from_file_location("greg_ui_server", MODULE_PATH)
ui = importlib.util.module_from_spec(spec)
sys.modules["greg_ui_server"] = ui
assert spec and spec.loader
spec.loader.exec_module(ui)


class GregUiServerTests(unittest.TestCase):
    def test_ui_shell_contains_operator_controls(self) -> None:
        html = ui.ui_shell("demo-course")
        self.assertIn("BuildStak Course Agent", html)
        self.assertIn("Course Brief", html)
        self.assertIn("Source Materials", html)
        self.assertIn("Current activity", html)
        self.assertIn("Operating progress", html)
        self.assertIn("Course Map", html)
        self.assertIn("Lesson Production", html)
        self.assertIn("Operator Action", html)
        self.assertIn("Lessons", html)
        self.assertIn("AI Costs", html)
        self.assertIn("/api/costs?course=", html)
        self.assertIn("Course production remains available", html)
        self.assertIn("renderCosts(null)", html)
        self.assertLess(html.index('id="approvals"'), html.index('id="costs"'))
        self.assertIn("Total estimated investment", html)
        self.assertIn("Do not cite text - images allowed", html)
        self.assertIn("Can cite + images allowed", html)
        self.assertIn("Start Course Map with current brief and sources", html)
        self.assertIn("Regenerate Course Map with current brief and sources", html)
        self.assertIn("startButton.disabled = activeCourseMap", html)
        self.assertIn("Download Course Map", html)
        self.assertIn("waiting for images", html)
        self.assertIn("Image Requests.md", html)
        self.assertIn("uploadVisualBatch", html)
        self.assertIn("operatorImageFiles", html)
        self.assertIn("multiple accept", html)
        self.assertIn("/api/start-course", html)
        self.assertIn("/api/produce", html)
        self.assertIn("Generate course books", html)
        self.assertIn("Translate course books (PT + ES)", html)
        self.assertIn("Translate presentations (PT + ES)", html)
        self.assertIn("produceSelected('translations_book')", html)
        self.assertIn("produceSelected('translations_deck')", html)
        self.assertNotIn("Generate PT-BR books", html)
        self.assertNotIn("Generate ES books", html)
        self.assertIn("lesson-table", html)
        self.assertIn("/api/jobs?course=", html)
        self.assertIn("documentCell", html)
        self.assertIn("not generated", html)
        self.assertIn("ready for review", html)
        self.assertNotIn("Activity Log", html)
        self.assertNotIn("pipeline-strip", html)
        self.assertIn("Request edits", html)
        self.assertIn("Download", html)
        self.assertIn("operatorTarget", html)
        self.assertIn("operatorLesson", html)
        self.assertIn("Choose a lesson first", html)
        self.assertIn("function renderOperatorTargetsForLesson", html)
        self.assertIn('id="operatorResult"', html)
        self.assertIn("showOperatorResult", html)
        self.assertIn("Attach requested images", html)
        self.assertIn("Supporting files or images", html)
        self.assertIn("operatorRevisionRequests", html)
        self.assertIn("revision-sources", html)
        self.assertNotIn("visualCurationPanel", html)
        self.assertNotIn("Download blocked file", html)
        self.assertIn("/artifact?path=", html)
        self.assertIn("approveArtifact", html)
        self.assertIn("/api/approve", html)
        self.assertIn("/api/request-changes", html)
        self.assertIn("New course workspace", html)
        self.assertIn("function resetWorkspace", html)
        self.assertIn("Saved unfinished courses", html)
        self.assertIn("function restoreSavedCourse", html)
        self.assertIn("/api/courses", html)
        self.assertIn('id="newCourse"', html)
        self.assertIn('id="restartWorkspace"', html)
        self.assertIn('id="deleteCourse"', html)
        self.assertIn("/api/delete-course", html)
        self.assertNotIn('id="targetLesson"', html)
        self.assertIn("uploadQueue = [];", html)
        self.assertIn("document.getElementById('files').value = '';", html)
        self.assertIn("function ensureCourseIntake", html)
        self.assertIn("function renderUploadQueue", html)
        self.assertIn("request.upload.onprogress", html)
        self.assertIn("Start Course Map with current brief and sources", html)
        self.assertIn("Regenerate Course Map with current brief and sources", html)
        self.assertIn("The Course Book reviewers found unresolved content issues", html)
        self.assertIn("course book content ready", html)
        self.assertIn("New course workspace ready.", html)
        self.assertIn("if (!course.value.trim()) {\n        return;", html)
        self.assertIn("function operatorFormIsBeingEdited", html)
        self.assertIn("function refreshWorkspaceIfIdle", html)
        self.assertIn("setInterval(refreshWorkspaceIfIdle, 10000)", html)
        self.assertIn("operatorActionInFlight", html)
        self.assertNotIn('value="demo-course"', html)

    def test_json_bytes_preserves_utf8(self) -> None:
        data = ui.json_bytes({"message": "ação"})
        self.assertIn("ação".encode("utf-8"), data)

    def test_cost_report_is_scoped_to_one_course_and_keeps_providers_separate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            log = run_root / "course-a" / "ops" / "model_usage_log.jsonl"
            log.parent.mkdir(parents=True)
            log.write_text(
                '{"at":"2026-08-28T10:00:00Z","role":"technical_content","provider":"openai","model":"gpt-a","outcome":"completed","cost":{"status":"estimated","estimated_usd":0.12}}\n'
                '{"at":"2026-08-28T10:01:00Z","role":"citation_review","provider":"anthropic","model":"claude-b","outcome":"completed","cost":{"status":"estimated","estimated_usd":0.08}}\n',
                encoding="utf-8",
            )
            with patch.object(ui, "SESSION_RUN_ROOT", run_root):
                report = ui.course_cost_report("course-a")
        self.assertEqual(0.2, report["total_estimated_usd"])
        self.assertEqual(2, len(report["providers"]))
        self.assertEqual(2, report["request_count"])

    def test_cost_report_keeps_complete_math_but_only_returns_ten_recent_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            log = run_root / "course-a" / "ops" / "model_usage_log.jsonl"
            log.parent.mkdir(parents=True)
            rows = [
                {"at": f"2026-08-28T10:{index:02d}:00Z", "role": "technical_content", "provider": "openai", "model": "gpt-a", "outcome": "completed", "usage": {"input_tokens": 1, "output_tokens": 1}, "cost": {"status": "estimated", "estimated_usd": 0.01, "components": {"input_usd": 0.005, "output_usd": 0.005}}}
                for index in range(12)
            ]
            log.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            with patch.object(ui, "SESSION_RUN_ROOT", run_root), patch("greg_model_router.cost_estimate", side_effect=lambda binding, usage: {"status": "estimated", "estimated_usd": 0.01, "components": {"input_usd": 0.005, "output_usd": 0.005}}):
                report = ui.course_cost_report("course-a")
        self.assertEqual(12, report["request_count"])
        self.assertEqual(10, len(report["recent_requests"]))
        self.assertEqual(0.12, report["math"][0]["estimated_usd"])

    def test_unfinished_workspaces_are_listed_before_completed_ones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            for index, (slug, title) in enumerate((("active-course", "Active course"), ("complete-course", "Completed course"))):
                run = run_root / slug
                run.mkdir()
                intake = run / "input" / "intake.md" if index else run / "intake.md"
                intake.parent.mkdir(parents=True, exist_ok=True)
                intake.write_text(f"# {title}\n", encoding="utf-8")
            with patch.object(ui, "SESSION_RUN_ROOT", run_root):
                ui.write_course_session("complete-course", "completed")
                workspaces = ui.list_course_workspaces()
        self.assertEqual([item["course_slug"] for item in workspaces], ["active-course", "complete-course"])
        self.assertEqual(workspaces[0]["status"], "active")
        self.assertEqual(workspaces[1]["status"], "completed")

    def test_delete_course_workspace_removes_only_selected_course_data(self) -> None:
        uploads_base = ROOT / "tmp" / "uploads"
        jobs_base = ROOT / "tmp" / "jobs"
        uploads_base.mkdir(parents=True, exist_ok=True)
        jobs_base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as runs_tmp, tempfile.TemporaryDirectory(dir=uploads_base) as uploads_tmp, tempfile.TemporaryDirectory(dir=jobs_base) as jobs_tmp:
            runs_root = Path(runs_tmp)
            selected = runs_root / "remove-me" / "input"
            preserved = runs_root / "keep-me" / "input"
            selected.mkdir(parents=True)
            preserved.mkdir(parents=True)
            (selected / "intake.md").write_text("# Remove me\n", encoding="utf-8")
            (preserved / "intake.md").write_text("# Keep me\n", encoding="utf-8")
            upload_dir = Path(uploads_tmp) / "remove-me"
            upload_dir.mkdir()
            (upload_dir / "source.pdf").write_bytes(b"pdf")

            with patch.object(ui, "SESSION_RUN_ROOT", runs_root):
                result = ui.delete_course_workspace(
                    course_slug="remove-me",
                    job_root=Path(jobs_tmp),
                    upload_root=Path(uploads_tmp),
                )

            self.assertEqual(result["course_slug"], "remove-me")
            self.assertFalse((runs_root / "remove-me").exists())
            self.assertFalse(upload_dir.exists())
            self.assertTrue((runs_root / "keep-me").exists())

    def test_safe_artifact_path_allows_runs_file(self) -> None:
        target = ROOT / "runs" / "tmp-ui-artifact" / "docx_pdf" / "sample.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"pdf")
        try:
            self.assertEqual(ui.safe_artifact_path("runs/tmp-ui-artifact/docx_pdf/sample.pdf"), target.resolve())
        finally:
            shutil.rmtree(ROOT / "runs" / "tmp-ui-artifact")

    def test_safe_artifact_path_blocks_path_traversal(self) -> None:
        with self.assertRaises(ValueError):
            ui.safe_artifact_path("../../secrets/.env.local")

    def test_safe_download_filename_sanitizes_operator_names(self) -> None:
        name = ui.safe_download_filename("Lesson 01: PM / Closeout?.pdf", "fallback.pdf")
        self.assertEqual(name, "Lesson 01- PM - Closeout-.pdf")

    def test_build_server_rejects_unsafe_job_root(self) -> None:
        with self.assertRaises(ValueError):
            ui.build_server("127.0.0.1", 0, job_root=Path("/tmp/not-profgreg"), upload_root=ROOT / "tmp" / "uploads", default_course="demo")

    def test_build_server_accepts_local_job_root(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            class FakeServer:
                def __init__(self, *_args, **_kwargs) -> None:
                    pass

            with patch.object(ui, "ThreadingHTTPServer", FakeServer):
                server = ui.build_server("127.0.0.1", 0, job_root=Path(tmp), upload_root=ROOT / "tmp" / "uploads", default_course="demo")
            self.assertEqual(server.default_course, "demo")

    def test_save_uploaded_file_records_manifest(self) -> None:
        base = ROOT / "tmp" / "uploads"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            upload_root = Path(tmp)
            result = ui.save_uploaded_file(
                upload_root=upload_root,
                course_slug="Demo Course",
                filename="sample.pdf",
                data=b"pdf bytes",
                scope="course",
                reference_policy="reference_and_images",
            )
            self.assertEqual(result["filename"], "sample.pdf")
            self.assertEqual(result["reference_policy"], "reference_and_images")
            self.assertTrue(result["can_appear_in_references"])
            self.assertTrue(result["images_allowed"])
            uploads = ui.list_uploads(upload_root, "demo-course")
            self.assertTrue(uploads)

    def test_image_only_policy_allows_images_without_references(self) -> None:
        base = ROOT / "tmp" / "uploads"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            result = ui.save_uploaded_file(
                upload_root=Path(tmp),
                course_slug="Image Only Course",
                filename="image-policy.pdf",
                data=b"image policy pdf",
                scope="course",
                reference_policy="image_only",
            )
            self.assertEqual(result["reference_policy"], "image_only")
            self.assertFalse(result["can_appear_in_references"])
            self.assertTrue(result["images_allowed"])

    def test_visual_response_records_request_and_attribution(self) -> None:
        base = ROOT / "tmp" / "uploads"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            result = ui.save_uploaded_file(
                upload_root=Path(tmp),
                course_slug="Visual Response Course",
                filename="field-photo.png",
                data=b"\x89PNG\r\n\x1a\nminimal-test-payload",
                scope="lesson",
                lesson=2,
                reference_policy="image_only",
                purpose="visual_response",
                visual_request_id="L02V01",
                source_label="Operator supplied field photo",
                source_url="https://example.com/photo",
            )
            self.assertEqual(result["purpose"], "visual_response")
            self.assertEqual(result["visual_request_id"], "L02V01")
            self.assertEqual(result["scope"], "lesson_02")

    def test_revision_material_is_preserved_and_recorded_with_feedback(self) -> None:
        base = ROOT / "tmp" / "uploads"
        base.mkdir(parents=True, exist_ok=True)
        run = ROOT / "runs" / "revision-material-test"
        if run.exists():
            shutil.rmtree(run)
        try:
            with tempfile.TemporaryDirectory(dir=base) as tmp:
                attachment = ui.save_uploaded_file(
                    upload_root=Path(tmp),
                    course_slug="Revision Material Test",
                    filename="field-photo.png",
                    data=b"\x89PNG\r\n\x1a\nminimal-test-payload",
                    scope="lesson",
                    lesson=1,
                    reference_policy="image_only",
                    purpose="revision_material",
                    revision_artifact_type="study_guide",
                    source_label="Operator field photo",
                    source_url="https://example.com/field-photo",
                )
                self.assertEqual(attachment["purpose"], "revision_material")
                self.assertEqual(attachment["revision_artifact_type"], "study_guide")
                feedback = ui.record_revision_request(
                    course_slug="Revision Material Test",
                    lesson=1,
                    artifact_type="study_guide",
                    note="Use the attached field photo in the visual revision.",
                    attachments=[attachment],
                )
            text = (ROOT / feedback["feedback_path"]).read_text(encoding="utf-8")
            state = json.loads((ROOT / feedback["state_path"]).read_text(encoding="utf-8"))
            self.assertIn("Supporting materials:", text)
            self.assertIn("field-photo.png", text)
            self.assertIn("https://example.com/field-photo", text)
            self.assertEqual("revision_requested", state["state"])
        finally:
            if run.exists():
                shutil.rmtree(run)

    def test_revision_evidence_is_preserved_without_becoming_revision_material(self) -> None:
        base = ROOT / "tmp" / "uploads"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            attachment = ui.save_uploaded_file(
                upload_root=Path(tmp), course_slug="Revision Evidence Test", filename="issue.png",
                data=b"\x89PNG\r\n\x1a\nminimal-test-payload", scope="lesson", lesson=3,
                reference_policy="context_only", purpose="revision_evidence", revision_artifact_type="study_guide",
            )
        self.assertEqual(attachment["purpose"], "revision_evidence")
        self.assertFalse(attachment["images_allowed"])

    def test_revision_requests_accumulate_instead_of_replacing_each_other(self) -> None:
        run = ROOT / "runs" / "revision-queue-test"
        if run.exists():
            shutil.rmtree(run)
        try:
            ui.record_revision_request(course_slug="Revision Queue Test", lesson=3, artifact_type="study_guide", note="First requested change.")
            result = ui.record_revision_request(course_slug="Revision Queue Test", lesson=3, artifact_type="study_guide", note="Second requested change.")
            state = json.loads((ROOT / result["state_path"]).read_text(encoding="utf-8"))
            text = (ROOT / result["feedback_path"]).read_text(encoding="utf-8")
            self.assertEqual(2, state["request_count"])
            self.assertIn("First requested change.", text)
            self.assertIn("Second requested change.", text)
        finally:
            if run.exists():
                shutil.rmtree(run)

    def test_visual_batch_maps_ids_by_filename_then_order(self) -> None:
        files = [{"filename": "L01V02-plan.png"}, {"filename": "field-photo.jpg"}]
        mapped = ui.map_visual_batch(files, ["L01V01", "L01V02"])
        self.assertEqual([item[1] for item in mapped], ["L01V02", "L01V01"])

    def test_visual_batch_rejects_incomplete_batch(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires 2 image"):
            ui.map_visual_batch([{"filename": "one.png"}], ["L01V01", "L01V02"])

    def test_visual_source_manifest_supports_filename_source_and_url(self) -> None:
        parsed = ui.parse_visual_source_manifest("plan.png | City permit set | https://example.com/plan\n")
        self.assertEqual(parsed["plan.png"]["source_label"], "City permit set")
        self.assertEqual(parsed["plan.png"]["source_url"], "https://example.com/plan")

    def test_update_and_delete_upload_manifest_entry(self) -> None:
        (ROOT / "tmp" / "uploads").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "uploads") as tmp:
            upload_root = Path(tmp)
            result = ui.save_uploaded_file(
                upload_root=upload_root,
                course_slug="Editable Course",
                filename="editable.pdf",
                data=b"editable pdf",
                scope="course",
                reference_policy="context_only",
            )
            updated = ui.update_upload_metadata(
                upload_root=upload_root,
                course_slug="editable-course",
                upload_id=result["upload_id"],
                scope="lesson",
                lesson=3,
                reference_policy="reference_only",
            )
            self.assertEqual(updated["scope"], "lesson_03")
            self.assertEqual(updated["reference_policy"], "reference_only")
            self.assertTrue(updated["can_appear_in_references"])
            self.assertFalse(updated["images_allowed"])
            deleted = ui.delete_uploaded_file(upload_root=upload_root, course_slug="editable-course", upload_id=result["upload_id"])
            self.assertEqual(deleted["filename"], "editable.pdf")
            self.assertEqual(ui.list_uploads(upload_root, "editable-course"), [])

    def test_expected_lesson_count_by_level(self) -> None:
        self.assertEqual(ui.expected_lesson_count("Basic"), 10)
        self.assertEqual(ui.expected_lesson_count("Intermediate"), 15)
        self.assertEqual(ui.expected_lesson_count("Advanced"), 15)
        self.assertEqual(ui.expected_lesson_count("Advanced", 18), 18)

    def test_operator_visible_jobs_hides_superseded_failures(self) -> None:
        jobs = [
            {
                "job_id": "job_old_failed",
                "course_slug": "demo",
                "request_type": "course_start",
                "state": "failed",
                "updated_at": "2026-08-16T10:00:00Z",
            },
            {
                "job_id": "job_new_success",
                "course_slug": "demo",
                "request_type": "course_start",
                "state": "completed",
                "updated_at": "2026-08-16T11:00:00Z",
            },
            {
                "job_id": "job_current_failed",
                "course_slug": "demo",
                "request_type": "study_guide",
                "state": "failed",
                "updated_at": "2026-08-16T12:00:00Z",
            },
        ]
        visible = ui.operator_visible_jobs(jobs)
        self.assertEqual([job["job_id"] for job in visible], ["job_new_success", "job_current_failed"])

    def test_rejects_unsupported_upload_extension(self) -> None:
        with self.assertRaises(ValueError):
            ui.safe_filename("../bad.exe")

    def test_rejects_image_with_mismatched_signature(self) -> None:
        with self.assertRaises(ValueError):
            ui.save_uploaded_file(
                upload_root=ROOT / "tmp" / "uploads",
                course_slug="Bad Image",
                filename="not-really.png",
                data=b"not an image",
            )

    def test_parse_multipart_form(self) -> None:
        boundary = "----prof-greg-test"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="course"\r\n\r\n'
            "demo-course\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="files"; filename="sample.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
            "pdf bytes\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        fields, files = ui.parse_multipart_form(f"multipart/form-data; boundary={boundary}", body)
        self.assertEqual(fields["course"], "demo-course")
        self.assertEqual(files[0]["filename"], "sample.pdf")
        self.assertEqual(files[0]["data"], b"pdf bytes")

    def test_parse_multipart_form_multiple_files_and_policy(self) -> None:
        boundary = "----prof-greg-multi"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="reference_policy"\r\n\r\n'
            "reference_and_images\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="files"; filename="one.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
            "one\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="files"; filename="two.docx"\r\n'
            "Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n"
            "two\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        fields, files = ui.parse_multipart_form(f"multipart/form-data; boundary={boundary}", body)
        self.assertEqual(fields["reference_policy"], "reference_and_images")
        self.assertEqual([file["filename"] for file in files], ["one.pdf", "two.docx"])

    def test_create_course_intake_writes_syllabus(self) -> None:
        run = ROOT / "runs" / "tmp-ui-course"
        if run.exists():
            shutil.rmtree(run)
        try:
            result = ui.create_course_intake(title="Tmp UI Course", level="Intermediate", syllabus="Lesson 1: Intro", course_slug="tmp-ui-course")
            intake = ROOT / result["intake_path"]
            self.assertTrue(intake.exists())
            text = intake.read_text(encoding="utf-8")
            self.assertIn("Lesson 1: Intro", text)
            self.assertIn("Expected lesson count: 15", text)
        finally:
            if run.exists():
                shutil.rmtree(run)


if __name__ == "__main__":
    unittest.main()
