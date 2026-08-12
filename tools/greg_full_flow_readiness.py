#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Check:
    name: str
    status: str
    path: str
    note: str


REQUIRED_FILES = [
    ("roadmap", "workspace/ROADMAP.md", "Roadmap of record exists."),
    ("workspace_status", "workspace/STATUS.md", "Development status exists."),
    ("operator_interface_contract", "workspace/contracts/operator-interface-contract.md", "Human interface contract exists."),
    ("operator_routing_contract", "workspace/contracts/operator-routing-contract.md", "Routing contract exists."),
    ("stage_execution_contract", "workspace/contracts/stage-execution-contract.md", "Stage execution contract exists."),
    ("run_folder_contract", "workspace/contracts/run-folder-contract.md", "Run folder contract exists."),
    ("canonical_artifacts_contract", "workspace/contracts/canonical-artifacts-contract.md", "Canonical artifacts contract exists."),
    ("reusable_renderer_contract", "workspace/contracts/reusable-renderer-contract.md", "Reusable renderer contract exists."),
    ("model_routing_contract", "workspace/contracts/model-routing-contract.md", "Model routing contract exists."),
    ("model_routing_config", "workspace/config/model-routing.json", "Model routing config exists."),
    ("source_ledger_contract", "workspace/contracts/source-ledger-contract.md", "Source ledger contract exists."),
    ("study_guide_contract", "workspace/contracts/study-guide-draft-contract.md", "Study guide contract exists."),
    ("review_contract", "workspace/contracts/study-guide-review-contract.md", "Review contract exists."),
    ("docx_pdf_contract", "workspace/contracts/docx-pdf-production-contract.md", "DOCX/PDF contract exists."),
    ("human_approval_contract", "workspace/contracts/human-approval-contract.md", "Human approval contract exists."),
    ("deck_contract", "workspace/contracts/deck-production-contract.md", "Deck contract exists."),
    ("localization_contract", "workspace/contracts/localization-contract.md", "Localization contract exists."),
    ("design_tokens", "workspace/design-system/tokens.json", "Design tokens exist."),
    ("design_components", "workspace/design-system/components.md", "Design components exist."),
    ("docx_rules", "workspace/design-system/docx-rules.md", "DOCX rules exist."),
    ("pptx_rules", "workspace/design-system/pptx-rules.md", "PPTX rules exist."),
    ("deck_components", "workspace/renderers/deck/buildstak-deck-components.md", "BuildStak deck component spec exists."),
    ("operator_skill", "workspace/skills/greg-operator/SKILL.md", "Operator skill exists."),
    ("full_flow_checklist", "workspace/test-packages/full-flow-v0/execution-checklist.md", "Full-flow checklist exists."),
    ("full_flow_intake_template", "workspace/test-packages/full-flow-v0/intake-template.md", "Full-flow intake template exists."),
    ("full_flow_report_template", "workspace/test-packages/full-flow-v0/full_flow_test_report_template.md", "Full-flow report template exists."),
    ("full_flow_v1_checklist", "workspace/test-packages/full-flow-v1/execution-checklist.md", "Full-flow v1 checklist exists."),
    ("full_flow_v1_intake_template", "workspace/test-packages/full-flow-v1/intake-template.md", "Full-flow v1 intake template exists."),
    ("intake_check_tool", "tools/greg_intake_check.py", "Intake checker exists."),
    ("course_status_tool", "tools/greg_course_status.py", "Course status tool exists."),
    ("lesson_operator_tool", "tools/greg_run_lesson.py", "Local lesson operator tool exists."),
    ("lesson_pipeline_qa_tool", "tools/greg_lesson_pipeline_qa.py", "Consolidated lesson pipeline QA tool exists."),
    ("request_router_tool", "tools/greg_route_request.py", "Request routing tool exists."),
    ("run_creator_tool", "tools/greg_create_run.py", "Run creator tool exists."),
    ("canonical_artifacts_tool", "tools/greg_canonical_artifacts.py", "Canonical artifacts tool exists."),
    ("course_map_quality_tool", "tools/greg_course_map_quality_check.py", "Course Map quality checker exists."),
    ("visual_plan_tool", "tools/greg_visual_plan_check.py", "Visual plan checker exists."),
    ("deck_quality_tool", "tools/greg_deck_quality_check.py", "Deck quality checker exists."),
    ("pdf_layout_tool", "tools/greg_pdf_layout_check.py", "PDF layout checker exists."),
    ("source_reference_tool", "tools/greg_source_reference_check.py", "Source/reference checker exists."),
    ("study_guide_content_tool", "tools/greg_study_guide_content_check.py", "Study guide content checker exists."),
    ("renderer_reuse_tool", "tools/greg_renderer_reuse_check.py", "Renderer reuse checker exists."),
    ("model_routing_check_tool", "tools/greg_model_routing_check.py", "Model routing checker exists."),
    ("prepare_full_flow_test_tool", "tools/greg_prepare_full_flow_test.py", "Full-flow test prep tool exists."),
    ("localized_deck_text_map_tool", "tools/greg_localized_deck_text_map_check.py", "Localized deck text-map checker exists."),
]

PRIMARY_SKILLS = [
    "greg-operator",
    "course-map",
    "source-ledger",
    "study-guide-draft",
    "pedagogy-reviewer",
    "citation-reviewer",
    "design-qa",
    "visual-qa",
    "docx-pdf-producer",
    "human-approval-gate",
    "deck-producer",
    "localize-pt-br",
    "localize-es-419",
    "localization-producer",
    "localization-reviewer",
]


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def exists_check(name: str, relative_path: str, note: str) -> Check:
    path = ROOT / relative_path
    status = "pass" if path.exists() else "fail"
    return Check(name=name, status=status, path=relative_path, note=note if status == "pass" else "Missing required file.")


def skill_check(skill: str) -> Check:
    relative = f"workspace/skills/{skill}/SKILL.md"
    path = ROOT / relative
    if not path.exists():
        return Check(name=f"skill:{skill}", status="fail", path=relative, note="Missing primary skill.")

    text = read_text(relative)
    if "workspace/contracts/" not in text:
        return Check(
            name=f"skill:{skill}",
            status="warn",
            path=relative,
            note="Skill exists but does not reference any contract.",
        )
    return Check(name=f"skill:{skill}", status="pass", path=relative, note="Skill exists and references contracts.")


def semantic_checks() -> list[Check]:
    checks = []

    operator = read_text("workspace/skills/greg-operator/SKILL.md")
    if "operator-routing-contract.md" in operator and "stage-execution-contract.md" in operator:
        checks.append(Check("operator_contract_links", "pass", "workspace/skills/greg-operator/SKILL.md", "Operator links routing and stage execution contracts."))
    else:
        checks.append(Check("operator_contract_links", "warn", "workspace/skills/greg-operator/SKILL.md", "Operator should reference routing and stage execution contracts."))

    status = read_text("workspace/STATUS.md")
    if "tools/greg_course_status.py" in status and "tools/greg_route_request.py" in status:
        checks.append(Check("status_tools_recorded", "pass", "workspace/STATUS.md", "Status records status and routing tools."))
    else:
        checks.append(Check("status_tools_recorded", "warn", "workspace/STATUS.md", "Status should record both status and routing tools."))

    return checks


def readiness() -> dict:
    checks = [exists_check(*item) for item in REQUIRED_FILES]
    checks.extend(skill_check(skill) for skill in PRIMARY_SKILLS)
    checks.extend(semantic_checks())

    failures = [check for check in checks if check.status == "fail"]
    warnings = [check for check in checks if check.status == "warn"]
    ready = not failures and not warnings
    ready_with_warnings = not failures and bool(warnings)

    if ready:
        recommendation = "Ready for Phase 3 refinement work."
    elif ready_with_warnings:
        recommendation = "Structurally ready, but resolve warnings before treating the test as clean."
    else:
        recommendation = "Not ready. Fix failed checks before starting full-flow v0."

    return {
        "ready": ready,
        "ready_with_warnings": ready_with_warnings,
        "fail_count": len(failures),
        "warn_count": len(warnings),
        "pass_count": sum(1 for check in checks if check.status == "pass"),
        "recommendation": recommendation,
        "checks": [asdict(check) for check in checks],
    }


def render_markdown(data: dict) -> str:
    lines = [
        f"Ready: {'yes' if data['ready'] else 'no'}",
        f"Ready with warnings: {'yes' if data['ready_with_warnings'] else 'no'}",
        f"Passed: {data['pass_count']}",
        f"Warnings: {data['warn_count']}",
        f"Failures: {data['fail_count']}",
        "",
        f"Recommendation: {data['recommendation']}",
    ]

    issues = [item for item in data["checks"] if item["status"] != "pass"]
    if issues:
        lines.extend(["", "Issues:"])
        for item in issues:
            lines.append(f"- {item['status'].upper()} {item['name']}: {item['path']} - {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether Prof Greg has the core files needed for the current development phase.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    data = readiness()
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(data))
    return 0 if data["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
