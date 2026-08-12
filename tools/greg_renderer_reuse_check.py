#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from greg_security import assert_safe_write_path


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Finding:
    status: str
    check: str
    note: str


SCRIPT_PATTERNS = ["tools/*.py", "tools/*.mjs", "workspace/renderers/deck/*.mjs", "workspace/renderers/pdf/*.py"]
REUSABLE_TARGETS = [
    "tools/greg_run_lesson.py",
    "tools/greg_lesson_pipeline_qa.py",
    "tools/greg_artifact_spec_check.py",
    "tools/greg_pdf_layout_check.py",
    "tools/greg_deck_quality_check.py",
    "workspace/renderers/deck/greg-buildstak-deck-renderer.mjs",
    "workspace/renderers/pdf/greg-buildstak-study-guide-renderer.py",
]


def iter_script_paths(patterns: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(ROOT.glob(pattern))
    return sorted(path for path in set(paths) if path.is_file() and "__pycache__" not in str(path))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def run_checks() -> dict:
    findings: list[Finding] = []
    paths = iter_script_paths(SCRIPT_PATTERNS)

    if paths:
        findings.append(Finding("pass", "scripts_found", f"Scanned {len(paths)} renderer/tool scripts."))
    else:
        findings.append(Finding("fail", "scripts_found", "No scripts found to audit."))

    missing_targets = [target for target in REUSABLE_TARGETS if not (ROOT / target).exists()]
    if missing_targets:
        findings.append(Finding("fail", "reusable_targets_present", f"Missing reusable targets: {missing_targets}."))
    else:
        findings.append(Finding("pass", "reusable_targets_present", "Core reusable operator/QA targets exist."))

    absolute_paths = []
    course_tied = []
    lesson_tied = []
    one_off_builders = []
    hardcoded_outputs = []

    for path in paths:
        text = read_text(path)
        relative = rel(path)
        if relative.startswith("tools/test_") or relative == "tools/greg_renderer_reuse_check.py":
            continue
        if re.search(r"/Users/tmarcato/|/private/var/|/var/folders/", text):
            absolute_paths.append(relative)
        if re.search(r"runs/[a-z0-9-]+", text) and not relative.startswith("tools/greg_"):
            course_tied.append(relative)
        if re.search(r"lesson_01|Lesson 1|LESSON 1", text) and not (relative.startswith("tools/greg_") or relative.startswith("workspace/renderers/")):
            lesson_tied.append(relative)
        if re.search(r"build_.*lesson|lesson1|blueprint|cost_estimating|construction-contract", path.name, re.IGNORECASE):
            one_off_builders.append(relative)
        if re.search(r"(FINAL_PPTX|PDF_OUT|OUTPUT|QA_PATH)\s*=", text):
            hardcoded_outputs.append(relative)

    if absolute_paths:
        findings.append(Finding("warn", "absolute_paths", f"Scripts with hardcoded local paths: {sorted(set(absolute_paths))}."))
    else:
        findings.append(Finding("pass", "absolute_paths", "No hardcoded local absolute paths found."))

    if course_tied:
        findings.append(Finding("warn", "course_tied_scripts", f"Scripts tied to specific run/course folders: {sorted(set(course_tied))}."))
    else:
        findings.append(Finding("pass", "course_tied_scripts", "No course-tied scripts found outside Greg tools."))

    if lesson_tied:
        findings.append(Finding("warn", "lesson_tied_scripts", f"Scripts tied to Lesson 1 conventions: {sorted(set(lesson_tied))}."))
    else:
        findings.append(Finding("pass", "lesson_tied_scripts", "No lesson-tied scripts found."))

    if one_off_builders:
        findings.append(Finding("warn", "one_off_builders", f"Likely one-off build scripts: {sorted(set(one_off_builders))}."))
    else:
        findings.append(Finding("pass", "one_off_builders", "No obvious one-off build scripts found."))

    if hardcoded_outputs:
        findings.append(Finding("warn", "hardcoded_outputs", f"Scripts with hardcoded output constants: {sorted(set(hardcoded_outputs))}."))
    else:
        findings.append(Finding("pass", "hardcoded_outputs", "No hardcoded output constants found."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict) -> str:
    lines = [
        f"Renderer reuse QA passed: {'yes' if data['passed'] else 'no'}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Prof Greg renderer scripts for reuse readiness.")
    parser.add_argument("--output", help="Optional path to write the Markdown report.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    data = run_checks()
    markdown = render_markdown(data)
    if args.output:
        output = assert_safe_write_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(markdown)
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
