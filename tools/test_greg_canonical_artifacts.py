#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_canonical_artifacts.py"

spec = importlib.util.spec_from_file_location("greg_canonical_artifacts", MODULE_PATH)
assert spec and spec.loader
canonical = importlib.util.module_from_spec(spec)
sys.modules["greg_canonical_artifacts"] = canonical
spec.loader.exec_module(canonical)


class CanonicalArtifactsTests(unittest.TestCase):
    def test_revision_label(self) -> None:
        self.assertEqual(canonical.revision_label(Path("lesson_01_deck_r03.pptx")), "r03")
        self.assertIsNone(canonical.revision_label(Path("lesson_01_deck.pptx")))

    def test_render_markdown_contains_table(self) -> None:
        data = {
            "course_slug": "demo",
            "manifest_version": 1,
            "artifacts": [
                {
                    "key": "deck_pptx",
                    "path": "deck/lesson_01_deck_r02.pptx",
                    "status": "approved",
                    "stage": "DECK",
                    "lesson": "01",
                    "revision": "r02",
                    "approval_path": "approval/lesson_01_deck_approval.md",
                    "qa_path": "deck/lesson_01_deck_qa.md",
                    "notes": "Approved.",
                }
            ],
        }
        text = canonical.render_markdown(data)
        self.assertIn("deck_pptx", text)
        self.assertIn("r02", text)

    def test_latest_glob_prefers_revisioned_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deck_dir = root / "deck"
            deck_dir.mkdir()
            canonical_path = deck_dir / "lesson_01_deck.pptx"
            revision_path = deck_dir / "lesson_01_deck_r03.pptx"
            revision_path.write_text("r03", encoding="utf-8")
            canonical_path.write_text("canonical", encoding="utf-8")
            selected = canonical.latest_glob(root, ["deck/lesson_01_deck_r*.pptx", "deck/lesson_01_deck.pptx"])
            self.assertEqual(selected, revision_path)

    def test_approval_without_artifact_prefers_canonical_study_guide(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docx_pdf").mkdir()
            (root / "approval").mkdir()
            canonical_pdf = root / "docx_pdf" / "lesson_01_study_guide.pdf"
            validation_pdf = root / "docx_pdf" / "lesson_01_study_guide_r02.pdf"
            canonical_pdf.write_text("approved", encoding="utf-8")
            validation_pdf.write_text("technical validation", encoding="utf-8")
            approval = root / "approval" / "lesson_01_study_guide_approval.md"
            approval.write_text("# Approval\n\nApproved by user.\n", encoding="utf-8")

            selected = canonical.approved_or_default_study_guide(root, "01", approval)

            self.assertEqual(selected, canonical_pdf)

    def test_approval_artifact_path_can_include_run_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original_root = canonical.ROOT
            canonical.ROOT = Path(tmp)
            try:
                run = canonical.ROOT / "runs" / "demo"
                deck = run / "deck" / "lesson_03_deck_r02.pptx"
                approval = run / "approval" / "lesson_03_deck_approval.md"
                deck.parent.mkdir(parents=True)
                approval.parent.mkdir(parents=True)
                deck.write_text("deck", encoding="utf-8")
                approval.write_text(
                    "- Artifact: runs/demo/deck/lesson_03_deck_r02.pptx\n",
                    encoding="utf-8",
                )

                self.assertEqual(canonical.artifact_from_approval(run, approval), deck)
            finally:
                canonical.ROOT = original_root

    def test_ready_revision_candidate_with_run_prefix_is_downloadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original_root = canonical.ROOT
            canonical.ROOT = Path(tmp)
            try:
                run = canonical.ROOT / "runs" / "demo"
                pdf = run / "docx_pdf" / "lesson_03_study_guide_r06.pdf"
                state = run / "operator_feedback" / "lesson_03_study_guide_revision_state.json"
                pdf.parent.mkdir(parents=True)
                state.parent.mkdir(parents=True)
                pdf.write_bytes(b"pdf")
                state.write_text(
                    '{"state":"ready_for_review","candidate_artifact":"runs/demo/docx_pdf/lesson_03_study_guide_r06.pdf"}',
                    encoding="utf-8",
                )
                self.assertEqual(canonical.revision_candidate(run, "03", "study_guide"), pdf)
            finally:
                canonical.ROOT = original_root

    def test_optional_missing_keys_do_not_include_approved_core(self) -> None:
        self.assertIn("localization_pt_br_deck_text_map", canonical.OPTIONAL_MISSING_KEYS)
        self.assertNotIn("deck_pptx", canonical.OPTIONAL_MISSING_KEYS)


if __name__ == "__main__":
    unittest.main()
