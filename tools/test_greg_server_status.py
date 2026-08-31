from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_server_status.py"
spec = importlib.util.spec_from_file_location("greg_server_status", MODULE_PATH)
checker = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(ROOT / "tools"))
sys.modules["greg_server_status"] = checker
assert spec.loader is not None
spec.loader.exec_module(checker)


class GregServerStatusTests(unittest.TestCase):
    def test_jobs_created_in_same_second_have_unique_ids(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            with patch.object(checker, "iso_now", return_value="2026-08-25T04:16:46Z"):
                first = checker.create_job(job_root=root, request_type="backup")
                second = checker.create_job(job_root=root, request_type="backup")
            self.assertNotEqual(first["job_id"], second["job_id"])
            self.assertEqual(len(list(root.glob("job_*/job.json"))), 2)

    def test_worker_startup_recovers_interrupted_jobs(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            job = checker.create_job(job_root=root, request_type="backup")
            checker.transition_job(root, job["job_id"], "running", note="claimed")
            recovered = checker.recover_interrupted_jobs(root)
            current = checker.list_jobs(root)[0]
            self.assertEqual(recovered, [job["job_id"]])
            self.assertEqual(current["state"], "failed")
            self.assertIn("Worker restart interrupted", current["last_error"])

    def test_qa_report_passed_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deploy_qa.md"
            path.write_text("Prof Greg pre-push QA passed: yes\n", encoding="utf-8")
            self.assertTrue(checker.qa_report_passed(path))
            path.write_text("Prof Greg pre-push QA passed: no\n", encoding="utf-8")
            self.assertFalse(checker.qa_report_passed(path))

    def test_local_missing_git_fails_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = checker.run_checks(root, mode="local")
            self.assertFalse(data["passed"])
            self.assertTrue(any(item["check"] == "git_commit" for item in data["findings"]))

    def test_render_markdown_includes_commit_and_findings(self) -> None:
        data = {
            "passed": True,
            "report_type": "status",
            "mode": "local",
            "root": "/tmp/example",
            "commit": "abc123",
            "branch": "main",
            "fail_count": 0,
            "warn_count": 0,
            "findings": [{"status": "pass", "check": "sample", "note": "ok"}],
            "server_paths": [],
        }
        text = checker.render_markdown(data)
        self.assertIn("Commit: abc123", text)
        self.assertIn("PASS sample", text)

    def test_logrotate_policy_detection(self) -> None:
        text = """
/var/log/profgreg/*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
}
"""
        self.assertTrue(checker.logrotate_policy_ok(text))
        self.assertFalse(checker.logrotate_policy_ok("/var/log/profgreg/*.log { weekly }"))

    def test_backup_systemd_policy_detection(self) -> None:
        service = (ROOT / "workspace" / "ops" / "profgreg-backup.service").read_text(encoding="utf-8")
        timer = (ROOT / "workspace" / "ops" / "profgreg-backup.timer").read_text(encoding="utf-8")
        worker = (ROOT / "workspace" / "ops" / "profgreg-worker.service").read_text(encoding="utf-8")
        ui = (ROOT / "workspace" / "ops" / "profgreg-ui.service").read_text(encoding="utf-8")
        self.assertTrue(checker.backup_service_policy_ok(service))
        self.assertTrue(checker.backup_timer_policy_ok(timer))
        self.assertTrue(checker.worker_service_policy_ok(worker))
        self.assertTrue(checker.ui_service_policy_ok(ui))
        self.assertFalse(checker.backup_service_policy_ok("User=root"))
        self.assertFalse(checker.backup_timer_policy_ok("OnCalendar=weekly"))
        self.assertFalse(checker.worker_service_policy_ok("User=root"))
        self.assertFalse(checker.ui_service_policy_ok("ExecStart=python server.py --host 0.0.0.0"))

    def test_ops_only_current_repo_passes_local(self) -> None:
        data = checker.run_ops_checks(ROOT, mode="local")
        self.assertTrue(data["passed"], data["findings"])
        self.assertNotIn("Commit:", checker.render_markdown(data))

    def test_backup_root_must_stay_in_allowed_location(self) -> None:
        with self.assertRaises(ValueError):
            checker.safe_backup_root(Path("/tmp/not-profgreg"))

    def test_backup_dry_run_has_manifest_without_secret_backup(self) -> None:
        data = checker.create_backup(ROOT, backup_root=ROOT / "tmp" / "backup-test", label="unit", dry_run=True)
        self.assertTrue(data["passed"])
        self.assertFalse(data["backup_created"])
        manifest = data["manifest_data"]
        self.assertIn("/etc/profgreg", manifest["excluded_secret_paths"])
        self.assertIn("/srv/profgreg/uploads", manifest["included_roots"])
        self.assertIn("/opt/profgreg/app/runs", manifest["included_roots"])

    def test_create_and_transition_job(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            job = checker.create_job(job_root=root, request_type="backup", input_summary="manual backup")
            self.assertEqual(job["state"], "queued")
            listed = checker.list_jobs(root)
            self.assertEqual(len(listed), 1)
            running = checker.transition_job(root, job["job_id"], "running")
            self.assertEqual(running["state"], "running")
            completed = checker.transition_job(root, job["job_id"], "completed")
            self.assertEqual(completed["state"], "completed")

    def test_list_jobs_reports_active_timing_step(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            job = checker.create_job(job_root=root, request_type="backup")
            trace = root / job["job_id"] / "timing.jsonl"
            trace.write_text(
                '{"event":"activity_started","activity":"model_text:technical_content","started_at":"2026-08-26T13:00:00Z"}\n',
                encoding="utf-8",
            )
            listed = checker.list_jobs(root)
            self.assertEqual(listed[0]["progress"]["activity"], "model_text:technical_content")

    def test_worker_lanes_route_content_and_decks_separately(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            book = checker.create_job(
                job_root=root,
                request_type="production_stage",
                course_slug="demo",
                payload={"stage": "study_guide", "lessons": [3]},
            )
            deck = checker.create_job(
                job_root=root,
                request_type="production_stage",
                course_slug="demo",
                payload={"stage": "deck", "lessons": [2]},
            )
            self.assertEqual(checker.job_lane(book), "content")
            self.assertEqual(checker.job_lane(deck), "delivery")
            self.assertEqual(checker.next_queued_job(root, worker_lane="content")["job_id"], book["job_id"])
            self.assertEqual(checker.next_queued_job(root, worker_lane="delivery")["job_id"], deck["job_id"])
            claimed = checker.claim_queued_job(root, worker_lane="content")
            self.assertEqual(claimed["job_id"], book["job_id"])
            self.assertIsNone(checker.next_queued_job(root, worker_lane="content"))
            self.assertEqual(checker.next_queued_job(root, worker_lane="delivery")["job_id"], deck["job_id"])

    def test_invalid_job_transition_fails(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            job = checker.create_job(job_root=root, request_type="backup")
            with self.assertRaises(ValueError):
                checker.transition_job(root, job["job_id"], "completed")

    def test_queued_job_can_fail_before_worker_claim(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            job = checker.create_job(job_root=root, request_type="backup")
            failed = checker.transition_job(root, job["job_id"], "failed", note="claim failed")
            self.assertEqual(failed["state"], "failed")
            self.assertEqual(failed["last_error"], "claim failed")

    def test_job_root_must_be_safe(self) -> None:
        with self.assertRaises(ValueError):
            checker.safe_job_root(Path("/tmp/not-profgreg"))

    def test_main_create_job_returns_success(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            argv = ["greg_server_status.py", "--job-root", tmp, "--create-job", "backup"]
            with patch.object(sys, "argv", argv):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(checker.main(), 0)

    def test_worker_once_without_jobs_is_successful_noop(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            result = checker.process_one_worker_job(Path(tmp), backup_root=ROOT / "tmp" / "worker-backups", dry_run=True)
            self.assertFalse(result["processed"])

    def test_worker_backup_job_completes_with_artifacts(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            job = checker.create_job(job_root=root, request_type="backup", input_summary="worker unit backup")
            result = checker.process_one_worker_job(root, backup_root=ROOT / "tmp" / "worker-backups", dry_run=True)
            self.assertTrue(result["processed"])
            self.assertEqual(result["job_id"], job["job_id"])
            self.assertEqual(result["state"], "completed")
            updated = checker.list_jobs(root)[0]
            self.assertEqual(updated["state"], "completed")
            self.assertTrue(updated["artifacts"])

    def test_worker_unsupported_job_fails_without_stack_dump(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            checker.create_job(job_root=root, request_type="course_status")
            result = checker.process_one_worker_job(root, backup_root=ROOT / "tmp" / "worker-backups", dry_run=True)
            self.assertEqual(result["state"], "failed")
            updated = checker.list_jobs(root)[0]
            self.assertEqual(updated["state"], "failed")
            self.assertLessEqual(len(updated["last_error"]), 500)

    def test_worker_claim_write_failure_does_not_crash_loop(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            job = checker.create_job(job_root=root, request_type="backup")
            with patch.object(checker, "transition_job", side_effect=PermissionError("read-only job")):
                result = checker.process_one_worker_job(root, backup_root=ROOT / "tmp" / "worker-backups", dry_run=True)
            self.assertTrue(result["processed"])
            self.assertEqual(result["job_id"], job["job_id"])
            self.assertEqual(result["state"], "failed")
            self.assertFalse(result["failure_recorded"])
            self.assertIn("could not persist failed state", result["error"])

    def test_worker_lesson_lifecycle_dry_run_completes(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            job = checker.create_job(job_root=root, request_type="lesson_lifecycle", course_slug="demo-course", lesson=2)
            result = checker.process_one_worker_job(root, backup_root=ROOT / "tmp" / "worker-backups", dry_run=True)
            self.assertEqual(result["job_id"], job["job_id"])
            self.assertEqual(result["state"], "completed")
            updated = checker.list_jobs(root)[0]
            self.assertEqual(updated["artifacts"][0]["kind"], "operator_report")

    def test_worker_stage_next_dry_run_completes(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            job = checker.create_job(job_root=root, request_type="stage_next", course_slug="demo-course", lesson=1)
            result = checker.process_one_worker_job(root, backup_root=ROOT / "tmp" / "worker-backups", dry_run=True)
            self.assertEqual(result["job_id"], job["job_id"])
        self.assertEqual(result["state"], "completed")

    def test_worker_production_stage_dry_run_completes(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            job = checker.create_job(
                job_root=root,
                request_type="production_stage",
                course_slug="demo-course",
                input_summary="test production stage",
                payload={"stage": "study_guide", "lessons": [1, 3]},
            )
            result = checker.process_one_worker_job(root, dry_run=True)
            self.assertTrue(result["processed"])
            self.assertEqual(result["job_id"], job["job_id"])
            self.assertEqual(result["state"], "completed")
            updated = checker.list_jobs(root)[0]
            self.assertEqual(updated["artifacts"][0]["kind"], "operator_report")

    def test_production_stage_timeout_is_recorded_as_a_retryable_failure(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            job = checker.create_job(
                job_root=root,
                request_type="production_stage",
                course_slug="demo-course",
                payload={"stage": "translations_book", "lessons": [1]},
            )
            with patch.object(checker, "run_command", return_value=(124, "Worker safety timeout: production did not finish after 95 minutes.")) as runner:
                result = checker.process_one_worker_job(root)
            self.assertEqual(result["state"], "failed")
            self.assertIn("Worker safety timeout", checker.list_jobs(root)[0]["last_error"])
            self.assertEqual(runner.call_args.kwargs["timeout_seconds"], 95 * 60)
            self.assertEqual(job["job_id"], result["job_id"])

    def test_translation_deck_timeout_scales_with_selected_lessons(self) -> None:
        self.assertEqual(checker.production_stage_timeout_seconds("translations_deck", 2), 95 * 60)

    def test_video_job_uses_delivery_lane_and_completes_dry_run(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp, tempfile.TemporaryDirectory() as app_tmp:
            app_root = Path(app_tmp)
            deck = app_root / "runs" / "demo" / "deck" / "lesson_02.pptx"
            deck.parent.mkdir(parents=True)
            deck.write_bytes(b"approved")
            job = checker.create_job(
                job_root=Path(tmp),
                request_type="video_generation",
                course_slug="demo",
                lesson=2,
                payload={
                    "locale": "en",
                    "sourcePath": "runs/demo/deck/lesson_02.pptx",
                    "sourceSha256": checker.sha256_file(deck),
                    "title": "Scheduling",
                },
            )
            self.assertEqual("delivery", checker.job_lane(job))
            with patch.object(checker, "ROOT", app_root):
                result = checker.process_one_worker_job(Path(tmp), dry_run=True, worker_lane="delivery")
        self.assertEqual("completed", result["state"])

    def test_automatic_video_discovery_deduplicates_source_revision(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp, tempfile.TemporaryDirectory() as app_tmp:
            app_root = Path(app_tmp)
            (app_root / "runs" / "demo" / "input").mkdir(parents=True)
            (app_root / "runs" / "demo" / "input" / "intake.md").write_text("# Demo", encoding="utf-8")
            summary = {
                "lessons": [{
                    "lesson": "02",
                    "title": "Scheduling",
                    "videos": {
                        "en": {
                            "status": "ready",
                            "presentation_path": "runs/demo/deck/lesson_02.pptx",
                            "source_sha256": "abc123",
                        }
                    },
                }]
            }
            with patch.object(checker, "ROOT", app_root), patch("greg_course_status.summarize", return_value=summary):
                first = checker.enqueue_approved_video_jobs(Path(tmp))
                second = checker.enqueue_approved_video_jobs(Path(tmp))
        self.assertEqual(1, len(first))
        self.assertEqual([], second)

    def test_interrupted_video_job_is_requeued_once(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            job = checker.create_job(
                job_root=root,
                request_type="video_generation",
                course_slug="demo",
                lesson=2,
                payload={"locale": "en", "sourcePath": "deck.pptx", "sourceSha256": "abc", "recoveryCount": 0},
            )
            checker.transition_job(root, job["job_id"], "running", note="claimed")
            checker.recover_interrupted_jobs(root)
            jobs = checker.list_jobs(root)
        self.assertEqual(2, len(jobs))
        self.assertEqual(["failed", "queued"], sorted(item["state"] for item in jobs))
        queued = next(item for item in jobs if item["state"] == "queued")
        self.assertEqual(1, queued["payload"]["recoveryCount"])

    def test_content_worker_does_not_recover_running_delivery_job(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            job = checker.create_job(
                job_root=root,
                request_type="video_generation",
                course_slug="demo",
                lesson=2,
                payload={"locale": "en", "sourcePath": "deck.pptx", "sourceSha256": "abc"},
            )
            checker.transition_job(root, job["job_id"], "running", note="delivery claimed")
            recovered = checker.recover_interrupted_jobs(root, worker_lane="content")
            current = checker.list_jobs(root)[0]
        self.assertEqual([], recovered)
        self.assertEqual("running", current["state"])


if __name__ == "__main__":
    unittest.main()
