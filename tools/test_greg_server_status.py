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

    def test_invalid_job_transition_fails(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            root = Path(tmp)
            job = checker.create_job(job_root=root, request_type="backup")
            with self.assertRaises(ValueError):
                checker.transition_job(root, job["job_id"], "completed")

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


if __name__ == "__main__":
    unittest.main()
