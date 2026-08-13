from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_source_policy_check.py"
spec = importlib.util.spec_from_file_location("greg_source_policy_check", MODULE_PATH)
checker = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(ROOT / "tools"))
sys.modules["greg_source_policy_check"] = checker
assert spec.loader is not None
spec.loader.exec_module(checker)


class SourcePolicyCheckTest(unittest.TestCase):
    def test_current_repo_policy_passes(self) -> None:
        data = checker.run_checks(ROOT)
        self.assertTrue(data["passed"], data["findings"])

    def test_semantic_scholar_api_key_requirement_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "workspace" / "contracts").mkdir(parents=True)
            (root / "workspace" / "skills" / "source-ledger").mkdir(parents=True)
            (root / "workspace" / "config").mkdir(parents=True)
            policy = "Semantic Scholar OpenAlex Crossref academic discovery not final authority Do not require a Semantic Scholar API key U.S. residential construction academic-discovery checkpoint"
            (root / "workspace" / "contracts" / "source-ledger-contract.md").write_text(policy, encoding="utf-8")
            (root / "workspace" / "skills" / "source-ledger" / "SKILL.md").write_text(policy, encoding="utf-8")
            (root / "workspace" / "contracts" / "model-routing-contract.md").write_text(policy, encoding="utf-8")
            (root / "workspace" / "config" / "model-routing.json").write_text(
                """{
  "providers": {
    "semantic_scholar": {"kind": "academic_discovery_checkpoint", "api_key_env": "SEMANTIC_SCHOLAR_API_KEY"},
    "openalex": {"kind": "academic_metadata_api"},
    "crossref": {"kind": "citation_metadata_api"}
  },
  "bindings": {"source_research": {"metadata_helpers": ["openalex", "crossref", "semantic_scholar"]}}
}""",
                encoding="utf-8",
            )

            data = checker.run_checks(root)
            self.assertFalse(data["passed"])
            self.assertTrue(any(item["check"] == "routing_metadata_helpers" for item in data["findings"] if item["status"] == "fail"))


if __name__ == "__main__":
    unittest.main()
