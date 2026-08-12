#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_source_reference_check.py"

spec = importlib.util.spec_from_file_location("greg_source_reference_check", MODULE_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules["greg_source_reference_check"] = checker
spec.loader.exec_module(checker)


class SourceReferenceCheckTests(unittest.TestCase):
    def test_old_source_detection(self) -> None:
        source = {"publication_date": "2017"}
        self.assertTrue(checker.is_more_than_three_years_old(source, 2026))

    def test_student_reference_forbidden_patterns(self) -> None:
        self.assertTrue(checker.title_in_references({"title": "Contract Administration Guidelines", "author_or_organization": "CMAA"}, "CMAA. Contract Administration Guidelines."))
        self.assertFalse(checker.title_in_references({"title": "Internal Notes", "author_or_organization": "Prof Greg"}, "AIA Contract Documents."))

    def test_formal_publication_reference_cannot_use_webpage_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ledger = tmp_path / "ledger.json"
            refs = tmp_path / "refs.md"
            ledger.write_text(
                """
{
  "sources": [
    {
      "source_id": "S001",
      "title": "Practice Standard for Scheduling--Second Edition",
      "author_or_organization": "Project Management Institute",
      "source_type": "published-book-or-standard",
      "authority_tier": "supporting-formal",
      "publication_date": "2011",
      "currency_validation": {"required": true, "status": "validated-applicable"},
      "claims_supported": [{"claim_id": "C001", "claim_summary": "A baseline supports comparison."}]
    }
  ],
  "validation": {"all_sources_verified": true, "unsupported_claims": []}
}
""",
                encoding="utf-8",
            )
            refs.write_text(
                "- Project Management Institute. Practice Standard for Scheduling--Second Edition. https://www.pmi.org/learning/library/abstract\n",
                encoding="utf-8",
            )
            result = checker.run_checks(ledger, refs, date(2026, 8, 10))
            self.assertFalse(result["passed"])
            self.assertTrue(any(item["check"] == "formal_publications_not_linked_as_webpages" for item in result["findings"] if item["status"] == "fail"))

    def test_missing_files_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = checker.run_checks(Path(tmp) / "missing.json", Path(tmp) / "missing.md", date(2026, 8, 10))
            self.assertFalse(result["passed"])
            self.assertGreaterEqual(result["fail_count"], 1)


if __name__ == "__main__":
    unittest.main()
