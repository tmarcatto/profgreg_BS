#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_aistudios_pilot.py"
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("greg_aistudios_pilot", MODULE_PATH)
pilot = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(pilot)


class AiStudiosPilotTests(unittest.TestCase):
    def test_private_json_is_mode_0600(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "upload.json"
            pilot.write_json(path, {"uploadedFile": {"uri": "private"}}, private=True)
            self.assertEqual(0o600, path.stat().st_mode & 0o777)

    def test_sha256_file_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "deck.pptx"
            path.write_bytes(b"approved")
            self.assertEqual(
                "2687f86ed6784b8a5fca36e6c468e12aa44dc3c7e8137e3160d1a95079bdcd02",
                pilot.sha256_file(path),
            )

    def test_generated_project_requires_exact_avatar_and_clothing(self) -> None:
        config = {
            "template": {"id": "template-1"},
            "avatar": {"modelId": "M0001", "clothingId": "BG-orange"},
        }
        project = {
            "_id": "project-1",
            "templateId": "template-1",
            "scenes": [{"clips": [{"type": "aiModel", "model": {"ai_name": "M0001", "emotion": "BG-orange"}}]}],
        }
        pilot.validate_generated_project(project, config)
        project["scenes"][0]["clips"][0]["model"]["emotion"] = "BG-black"
        with self.assertRaisesRegex(pilot.AiStudiosError, "Gregory Orange"):
            pilot.validate_generated_project(project, config)


if __name__ == "__main__":
    unittest.main()
