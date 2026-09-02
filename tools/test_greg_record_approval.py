#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_record_approval.py"

spec = importlib.util.spec_from_file_location("greg_record_approval", MODULE_PATH)
assert spec and spec.loader
approval = importlib.util.module_from_spec(spec)
sys.modules["greg_record_approval"] = approval
spec.loader.exec_module(approval)


class GregRecordApprovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.slug = "tmp-record-approval"
        self.run = ROOT / "runs" / self.slug
        if self.run.exists():
            shutil.rmtree(self.run)
        (self.run / "docx_pdf").mkdir(parents=True)
        (self.run / "approval").mkdir(parents=True)

    def tearDown(self) -> None:
        if self.run.exists():
            shutil.rmtree(self.run)

    def test_records_approval_file(self) -> None:
        artifact = self.run / "docx_pdf" / "lesson_01_study_guide.pdf"
        artifact.write_text("pdf", encoding="utf-8")

        result = approval.record_approval(
            self.slug,
            1,
            "study_guide",
            "docx_pdf/lesson_01_study_guide.pdf",
            approved_on="2026-08-11",
            write_canonical=False,
        )

        path = Path(result["approval"])
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")
        self.assertIn("Artifact: runs/tmp-record-approval/docx_pdf/lesson_01_study_guide.pdf", text)
        self.assertIn("Status: approved", text)

    def test_missing_artifact_fails(self) -> None:
        with self.assertRaises(FileNotFoundError):
            approval.record_approval(self.slug, 1, "deck", "deck/missing.pptx", write_canonical=False)

    def test_localized_deck_cannot_be_approved_without_source_integrity(self) -> None:
        artifact = self.run / "localization" / "pt-br" / "lesson_01_deck_pt_br_r01.pptx"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"wrong presentation")

        with patch.object(approval, "validate_localized_deck", side_effect=RuntimeError("wrong approved source")):
            with self.assertRaisesRegex(RuntimeError, "wrong approved source"):
                approval.record_approval(
                    self.slug,
                    1,
                    "pt_br_deck",
                    "localization/pt-br/lesson_01_deck_pt_br_r01.pptx",
                    write_canonical=False,
                )

    def test_existing_approval_requires_force(self) -> None:
        artifact = self.run / "docx_pdf" / "lesson_01_study_guide.pdf"
        artifact.write_text("pdf", encoding="utf-8")
        approval.record_approval(
            self.slug,
            1,
            "study_guide",
            "docx_pdf/lesson_01_study_guide.pdf",
            write_canonical=False,
        )

        with self.assertRaises(FileExistsError):
            approval.record_approval(
                self.slug,
                1,
                "study_guide",
                "docx_pdf/lesson_01_study_guide.pdf",
                write_canonical=False,
            )


if __name__ == "__main__":
    unittest.main()
