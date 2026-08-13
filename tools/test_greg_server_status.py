from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
