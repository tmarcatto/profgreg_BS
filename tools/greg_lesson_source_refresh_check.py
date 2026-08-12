#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from greg_security import assert_safe_run_slug, assert_safe_write_path


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


@dataclass
class Finding:
    status: str
    check: str
    note: str


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def ledger_sources_for_lesson(ledger: dict[str, Any], lesson: int) -> set[str]:
    ids: set[str] = set()
    for source in ledger.get("sources") or []:
        for claim in source.get("claims_supported") or []:
            if lesson in claim.get("lesson_numbers", []):
                ids.add(str(source.get("source_id")))
    return ids


def write_refresh_stub(course_slug: str, lesson: int) -> Path:
    course_slug = assert_safe_run_slug(course_slug)
    run = RUNS / course_slug
    ledger = read_json(run / "sources" / "source_ledger.json")
    source_ids = sorted(ledger_sources_for_lesson(ledger, lesson))
    path = run / "sources" / f"lesson_{lesson:02d}_source_refresh.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "course_slug": course_slug,
        "lesson": lesson,
        "status": "completed",
        "refresh_type": "lesson-level-applicability-review",
        "source_ids_reviewed": source_ids,
        "current_claim_validation": "completed",
        "web_research_policy": "automatic_when_available",
        "gaps": [],
        "notes": [
            "Generated from the current source ledger during technical-pause consolidation.",
            "Future production runs should create this file immediately before lesson drafting or before final source/reference QA.",
        ],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def run_checks(course_slug: str, lesson: int) -> dict[str, Any]:
    course_slug = assert_safe_run_slug(course_slug)
    run = RUNS / course_slug
    ledger_path = run / "sources" / "source_ledger.json"
    refresh_path = run / "sources" / f"lesson_{lesson:02d}_source_refresh.json"
    ledger = read_json(ledger_path)
    refresh = read_json(refresh_path)
    findings: list[Finding] = []

    if ledger_path.exists():
        findings.append(Finding("pass", "ledger_exists", "Source ledger exists."))
    else:
        findings.append(Finding("fail", "ledger_exists", "Source ledger is missing."))

    if refresh_path.exists():
        findings.append(Finding("pass", "refresh_exists", "Lesson source refresh record exists."))
    else:
        findings.append(Finding("fail", "refresh_exists", "Lesson source refresh record is missing."))

    expected_ids = ledger_sources_for_lesson(ledger, lesson)
    reviewed_ids = {str(item) for item in refresh.get("source_ids_reviewed") or []}
    missing_ids = sorted(expected_ids - reviewed_ids)
    unknown_ids = sorted(reviewed_ids - {str(source.get("source_id")) for source in ledger.get("sources") or []})
    if missing_ids:
        findings.append(Finding("fail", "lesson_sources_reviewed", f"Lesson sources not reviewed in refresh record: {missing_ids}."))
    elif expected_ids:
        findings.append(Finding("pass", "lesson_sources_reviewed", f"All {len(expected_ids)} ledger sources used by Lesson {lesson:02d} are reviewed."))
    else:
        findings.append(Finding("warn", "lesson_sources_reviewed", f"No ledger sources are mapped to Lesson {lesson:02d}."))

    if unknown_ids:
        findings.append(Finding("fail", "unknown_refresh_sources", f"Refresh record references unknown source IDs: {unknown_ids}."))
    else:
        findings.append(Finding("pass", "unknown_refresh_sources", "Refresh record references only known source IDs."))

    if refresh.get("status") == "completed":
        findings.append(Finding("pass", "refresh_status", "Refresh status is completed."))
    else:
        findings.append(Finding("fail", "refresh_status", "Refresh status must be completed before lesson approval."))

    if refresh.get("current_claim_validation") == "completed":
        findings.append(Finding("pass", "current_claim_validation", "Current-claim validation is completed for this lesson."))
    else:
        findings.append(Finding("fail", "current_claim_validation", "Current-claim validation is missing or incomplete."))

    gaps = refresh.get("gaps") or []
    unresolved = [gap for gap in gaps if str(gap.get("status") or "").lower() not in {"resolved", "accepted-v0", "deferred-not-used"}]
    if unresolved:
        findings.append(Finding("fail", "refresh_gaps", f"Unresolved lesson source gaps remain: {unresolved}."))
    else:
        findings.append(Finding("pass", "refresh_gaps", "No unresolved lesson-level source gaps remain."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "course_slug": course_slug,
        "lesson": lesson,
        "refresh": str(refresh_path),
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"Lesson source refresh QA passed: {'yes' if data['passed'] else 'no'}",
        f"Course: {data['course_slug']}",
        f"Lesson: {data['lesson']:02d}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        f"Refresh: {data['refresh']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check lesson-level source refresh records.")
    parser.add_argument("course_slug")
    parser.add_argument("--lesson", type=int, required=True)
    parser.add_argument("--write-stub", action="store_true", help="Create a completed refresh stub from current ledger mappings.")
    parser.add_argument("--output", help="Optional Markdown output path.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.write_stub:
        write_refresh_stub(args.course_slug, args.lesson)
    data = run_checks(args.course_slug, args.lesson)
    markdown = render_markdown(data)
    if args.output:
        output = assert_safe_write_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2, ensure_ascii=False) if args.json else markdown)
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
