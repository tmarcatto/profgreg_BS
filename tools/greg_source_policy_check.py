#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from greg_security import assert_safe_write_path


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Finding:
    status: str
    check: str
    note: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def has_all(text: str, required: list[str]) -> bool:
    lower = text.lower()
    return all(item.lower() in lower for item in required)


def run_checks(root: Path = ROOT) -> dict[str, Any]:
    findings: list[Finding] = []
    source_contract = read_text(root / "workspace" / "contracts" / "source-ledger-contract.md")
    source_skill = read_text(root / "workspace" / "skills" / "source-ledger" / "SKILL.md")
    model_contract = read_text(root / "workspace" / "contracts" / "model-routing-contract.md")
    routing = load_json(root / "workspace" / "config" / "model-routing.json")

    academic_terms = ["Semantic Scholar", "OpenAlex", "Crossref", "academic discovery", "not final authority"]
    if has_all(source_contract, academic_terms):
        findings.append(Finding("pass", "source_contract_academic_policy", "Source contract records academic discovery policy."))
    else:
        findings.append(Finding("fail", "source_contract_academic_policy", "Source contract must name Semantic Scholar, OpenAlex, Crossref, academic discovery, and final-authority limits."))

    skill_terms = ["Semantic Scholar", "OpenAlex", "Crossref", "academic-discovery checkpoint", "U.S. residential construction"]
    if has_all(source_skill, skill_terms):
        findings.append(Finding("pass", "source_skill_academic_workflow", "Source-ledger skill includes academic checkpoint workflow."))
    else:
        findings.append(Finding("fail", "source_skill_academic_workflow", "Source-ledger skill must include academic checkpoint workflow and residential-construction authority limits."))

    if has_all(model_contract, ["Semantic Scholar", "OpenAlex", "Crossref", "Do not require a Semantic Scholar API key"]):
        findings.append(Finding("pass", "model_contract_metadata_helpers", "Model routing contract clarifies metadata helpers."))
    else:
        findings.append(Finding("fail", "model_contract_metadata_helpers", "Model routing contract must clarify Semantic Scholar, OpenAlex, and Crossref usage."))

    providers = routing.get("providers") or {}
    semantic = providers.get("semantic_scholar") or {}
    openalex = providers.get("openalex") or {}
    crossref = providers.get("crossref") or {}
    helper_issues = []
    if semantic.get("api_key_env") is not None:
        helper_issues.append("semantic_scholar should not require api_key_env")
    if semantic.get("kind") != "academic_discovery_checkpoint":
        helper_issues.append("semantic_scholar kind should be academic_discovery_checkpoint")
    if "academic_metadata_api" != openalex.get("kind"):
        helper_issues.append("openalex kind should be academic_metadata_api")
    if "citation_metadata_api" != crossref.get("kind"):
        helper_issues.append("crossref kind should be citation_metadata_api")
    source_helpers = ((routing.get("bindings") or {}).get("source_research") or {}).get("metadata_helpers") or []
    for helper in ["openalex", "crossref", "semantic_scholar"]:
        if helper not in source_helpers:
            helper_issues.append(f"source_research metadata_helpers missing {helper}")
    if helper_issues:
        findings.append(Finding("fail", "routing_metadata_helpers", f"Metadata helper issues: {helper_issues}."))
    else:
        findings.append(Finding("pass", "routing_metadata_helpers", "Routing config treats academic helpers as discovery/metadata helpers."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"Source policy QA passed: {'yes' if data['passed'] else 'no'}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Prof Greg source policy contracts and metadata-helper routing.")
    parser.add_argument("--output", help="Optional Markdown output path.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    data = run_checks()
    markdown = render_markdown(data)
    if args.output:
        output = assert_safe_write_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2, ensure_ascii=False) if args.json else markdown)
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
