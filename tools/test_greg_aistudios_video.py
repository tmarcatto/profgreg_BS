from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
MODULE_PATH = ROOT / "tools" / "greg_aistudios_video.py"
spec = importlib.util.spec_from_file_location("greg_aistudios_video", MODULE_PATH)
video = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(video)


class AiStudiosVideoTests(unittest.TestCase):
    def test_project_name_uses_contract_locale_suffixes(self) -> None:
        self.assertEqual("Lesson 02 - Scheduling - EN", video.project_name(2, "Scheduling", "en"))
        self.assertEqual("Lesson 02 - Scheduling - PT-BR", video.project_name(2, "Scheduling", "pt"))
        self.assertEqual("Lesson 02 - Scheduling - ES", video.project_name(2, "Scheduling", "es"))

    def test_new_revision_preserves_prior_delivery_history(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as temporary:
            source = Path(temporary) / "lesson.pptx"
            source.write_bytes(b"new")
            state = video.initial_state(
                course_slug="demo",
                lesson=2,
                locale="en",
                source=source,
                source_hash="new-hash",
                title="Scheduling",
                previous={
                    "sourceSha256": "old-hash",
                    "aiStudiosProjectId": "old-project",
                    "downloadUrl": "https://media.aistudios.com/old.mp4",
                    "completedAt": "2026-08-31T00:00:00Z",
                },
            )
        self.assertEqual("old-project", state["history"][0]["aiStudiosProjectId"])
        self.assertEqual("https://media.aistudios.com/old.mp4", state["history"][0]["downloadUrl"])

    def test_validation_mismatch_requires_attention(self) -> None:
        self.assertTrue(video.needs_attention(video.AiStudiosError("unexpected avatar")))
        self.assertFalse(video.needs_attention(video.AiStudiosError("AI Studios could not be reached.")))


if __name__ == "__main__":
    unittest.main()
