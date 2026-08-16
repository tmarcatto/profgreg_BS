from __future__ import annotations

import importlib.util
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
        self.assertIn("Production Status", html)
        self.assertIn("Approval Queue", html)
        self.assertIn("Activity Log", html)
        self.assertIn("Lessons", html)
        self.assertIn("Do not cite text - images allowed", html)
        self.assertIn("Can cite + images allowed", html)
        self.assertIn("Start production", html)
        self.assertIn("/api/stage-next", html)
        self.assertIn("Request edits", html)
        self.assertIn("Download", html)
        self.assertIn("blocked by QA", html)
        self.assertIn(".approval-card.blocked", html)
        self.assertIn("/artifact?path=", html)
        self.assertIn("approveArtifact", html)
        self.assertIn("/api/approve", html)
        self.assertIn("/api/request-changes", html)
        self.assertIn("demo-course", html)

    def test_json_bytes_preserves_utf8(self) -> None:
        data = ui.json_bytes({"message": "ação"})
        self.assertIn("ação".encode("utf-8"), data)

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
        upload_root = ROOT / "tmp" / "uploads"
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
        upload_root = ROOT / "tmp" / "uploads"
        result = ui.save_uploaded_file(
            upload_root=upload_root,
            course_slug="Image Only Course",
            filename="image-policy.pdf",
            data=b"image policy pdf",
            scope="course",
            reference_policy="image_only",
        )
        self.assertEqual(result["reference_policy"], "image_only")
        self.assertFalse(result["can_appear_in_references"])
        self.assertTrue(result["images_allowed"])

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

    def test_rejects_unsupported_upload_extension(self) -> None:
        with self.assertRaises(ValueError):
            ui.safe_filename("../bad.exe")

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
