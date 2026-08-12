#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Finding:
    status: str
    check: str
    note: str


PLACEHOLDER_PATTERNS = [
    r"Paste the user-provided syllabus",
    r"List uploaded books",
    r"Course title:\s*$",
    r"Course level:\s*Basic \| Intermediate \| Advanced",
]


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def run_checks(intake_path: Path) -> dict:
    text = read_text(intake_path)
    findings: list[Finding] = []

    if intake_path.exists():
        findings.append(Finding("pass", "intake_exists", "Intake file exists."))
    else:
        findings.append(Finding("fail", "intake_exists", "Intake file is missing."))

    placeholders = [pattern for pattern in PLACEHOLDER_PATTERNS if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)]
    if placeholders:
        findings.append(Finding("fail", "placeholders_resolved", f"Intake still contains template placeholders: {placeholders}."))
    else:
        findings.append(Finding("pass", "placeholders_resolved", "No blocking intake placeholders found."))

    if re.search(r"Course level:\s*(Basic|Intermediate|Advanced|Basic / Entry Level|Entry Level)", text, flags=re.IGNORECASE):
        findings.append(Finding("pass", "course_level", "Course level is explicit."))
    else:
        findings.append(Finding("fail", "course_level", "Course level is missing or unclear."))

    if re.search(r"Lesson\s+1\s*:", text, flags=re.IGNORECASE) or re.search(r"## Syllabus / Initial Direction\s*\n\s*\S", text, flags=re.IGNORECASE):
        findings.append(Finding("pass", "syllabus_direction", "Syllabus or lesson direction is present."))
    else:
        findings.append(Finding("fail", "syllabus_direction", "No syllabus or lesson direction found."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "intake": str(intake_path),
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict) -> str:
    lines = [
        f"Intake QA passed: {'yes' if data['passed'] else 'no'}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        f"Intake: {data['intake']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether a Prof Greg intake is ready for Course Map production.")
    parser.add_argument("intake", help="Path to input/intake.md.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    data = run_checks(Path(args.intake).expanduser().resolve())
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(data))
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
