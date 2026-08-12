#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_lesson_source_refresh_check.py"

spec = importlib.util.spec_from_file_location("greg_lesson_source_refresh_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_lesson_source_refresh_check"] = checker
spec.loader.exec_module(checker)


class LessonSourceRefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.slug = "tmp-source-refresh"
        self.run = ROOT / "runs" / self.slug
        if self.run.exists():
            shutil.rmtree(self.run)
        (self.run / "sources").mkdir(parents=True)

    def tearDown(self) -> None:
        if self.run.exists():
            shutil.rmtree(self.run)

    def write_ledger(self) -> None:
        (self.run / "sources" / "source_ledger.json").write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "source_id": "S001",
                            "claims_supported": [{"lesson_numbers": [1]}],
                        },
                        {
                            "source_id": "S002",
                            "claims_supported": [{"lesson_numbers": [2]}],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

    def test_ledger_sources_for_lesson(self) -> None:
        ledger = {"sources": [{"source_id": "S001", "claims_supported": [{"lesson_numbers": [1, 2]}]}]}
        self.assertEqual(checker.ledger_sources_for_lesson(ledger, 2), {"S001"})

    def test_missing_refresh_fails(self) -> None:
        self.write_ledger()
        result = checker.run_checks(self.slug, 1)
        self.assertFalse(result["passed"])

    def test_completed_refresh_passes(self) -> None:
        self.write_ledger()
        (self.run / "sources" / "lesson_01_source_refresh.json").write_text(
            json.dumps(
                {
                    "status": "completed",
                    "source_ids_reviewed": ["S001"],
                    "current_claim_validation": "completed",
                    "gaps": [],
                }
            ),
            encoding="utf-8",
        )
        result = checker.run_checks(self.slug, 1)
        self.assertTrue(result["passed"], result["findings"])


if __name__ == "__main__":
    unittest.main()
