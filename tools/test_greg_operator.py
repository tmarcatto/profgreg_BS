from __future__ import annotations

import importlib.util
import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
MODULE_PATH = ROOT / "tools" / "greg_operator.py"
spec = importlib.util.spec_from_file_location("greg_operator", MODULE_PATH)
operator = importlib.util.module_from_spec(spec)
sys.modules["greg_operator"] = operator
assert spec and spec.loader
spec.loader.exec_module(operator)


class GregOperatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.slug = "tmp-operator-course"
        self.run = ROOT / "runs" / self.slug
        if self.run.exists():
            shutil.rmtree(self.run)
        (self.run / "input").mkdir(parents=True)
        (self.run / "input" / "intake.md").write_text("Course level: Basic\nLesson 1: Foundations\n", encoding="utf-8")

    def tearDown(self) -> None:
        if self.run.exists():
            shutil.rmtree(self.run)

    def test_backup_enqueue_creates_job(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            result = operator.enqueue_job(job_root=Path(tmp), request_type="backup", summary="unit backup")
            self.assertTrue(result.allowed)
            self.assertEqual(result.job["request_type"], "backup")
            self.assertEqual(result.job["state"], "queued")

    def test_status_request_does_not_require_enqueue(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            result = operator.handle_request("mostre o status", course_slug=self.slug, lesson=1, job_root=Path(tmp), enqueue=False)
            self.assertTrue(result.allowed)
            self.assertEqual(result.route["intent"], "status")
            self.assertIsNotNone(result.status)

    def test_blocked_deck_request_does_not_enqueue(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            result = operator.handle_request("gera o deck", course_slug=self.slug, lesson=1, job_root=Path(tmp), enqueue=True)
            self.assertFalse(result.allowed)
            self.assertIsNone(result.job)

    def test_job_root_can_be_passed_after_subcommand(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            argv = ["greg_operator.py", "jobs", "--job-root", tmp]
            with patch.object(sys, "argv", argv):
                with redirect_stdout(io.StringIO()) as stdout:
                    self.assertEqual(operator.main(), 0)
            self.assertIn("Jobs:", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
