from __future__ import annotations

import importlib.util
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
        self.assertIn("Prof Greg Operator", html)
        self.assertIn("Queue Backup", html)
        self.assertIn("Queue Lesson Lifecycle", html)
        self.assertIn("demo-course", html)

    def test_json_bytes_preserves_utf8(self) -> None:
        data = ui.json_bytes({"message": "ação"})
        self.assertIn("ação".encode("utf-8"), data)

    def test_build_server_rejects_unsafe_job_root(self) -> None:
        with self.assertRaises(ValueError):
            ui.build_server("127.0.0.1", 0, job_root=Path("/tmp/not-profgreg"), default_course="demo")

    def test_build_server_accepts_local_job_root(self) -> None:
        (ROOT / "tmp" / "jobs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" / "jobs") as tmp:
            class FakeServer:
                def __init__(self, *_args, **_kwargs) -> None:
                    pass

            with patch.object(ui, "ThreadingHTTPServer", FakeServer):
                server = ui.build_server("127.0.0.1", 0, job_root=Path(tmp), default_course="demo")
            self.assertEqual(server.default_course, "demo")


if __name__ == "__main__":
    unittest.main()
