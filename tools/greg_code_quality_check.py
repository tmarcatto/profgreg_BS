#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from greg_security import assert_safe_write_path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DIRS = [ROOT / "tools", ROOT / "workspace" / "renderers", ROOT / "workspace" / "adapters"]
IGNORED_PARTS = {"legacy", "__pycache__", ".cache", ".git"}
SELF_AUDIT_FILES = {"tools/greg_code_quality_check.py", "tools/greg_security_check.py", "tools/greg_renderer_reuse_check.py"}
MAX_ACTIVE_TOOL_FILES = 70
MAX_NON_TEST_TOOL_FILES = 35
MAX_LONG_FILE_LINES = 900


@dataclass
class Finding:
    status: str
    check: str
    note: str


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def active_files() -> list[Path]:
    paths: list[Path] = []
    for folder in ACTIVE_DIRS:
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            if any(part in IGNORED_PARTS for part in path.parts):
                continue
            if path.suffix not in {".py", ".mjs", ".md", ".json"}:
                continue
            paths.append(path)
    return sorted(paths)


def tool_files() -> list[Path]:
    return sorted(path for path in (ROOT / "tools").glob("*") if path.is_file())


def run_checks() -> dict[str, Any]:
    findings: list[Finding] = []
    tools = tool_files()
    non_test_tools = [path for path in tools if not path.name.startswith("test_")]
    files = active_files()

    if len(tools) <= MAX_ACTIVE_TOOL_FILES:
        findings.append(Finding("pass", "tool_file_count", f"Tool file count is manageable for v0: {len(tools)}."))
    else:
        findings.append(Finding("warn", "tool_file_count", f"Tool file count is high: {len(tools)}; consider grouping commands by domain."))

    if len(non_test_tools) <= MAX_NON_TEST_TOOL_FILES:
        findings.append(Finding("pass", "non_test_tool_file_count", f"Active non-test tool count is acceptable: {len(non_test_tools)}."))
    else:
        findings.append(Finding("warn", "non_test_tool_file_count", f"Active non-test tool count is high: {len(non_test_tools)}; consolidation would help."))

    legacy_active = [rel(path) for path in tools if "legacy" not in path.parts and re.search(r"(blueprint|cost_estimating|contract_essentials|lesson1|lesson_01).*build", path.name)]
    if legacy_active:
        findings.append(Finding("warn", "course_specific_active_tools", f"Course-specific active tool names found: {legacy_active}."))
    else:
        findings.append(Finding("pass", "course_specific_active_tools", "No obvious course-specific build scripts remain in active tools."))

    long_files = []
    for path in files:
        lines = read_text(path).splitlines()
        if len(lines) > MAX_LONG_FILE_LINES:
            long_files.append((rel(path), len(lines)))
    if long_files:
        findings.append(Finding("warn", "large_files", f"Large active files found: {long_files}."))
    else:
        findings.append(Finding("pass", "large_files", "No active file exceeds the maintainability line threshold."))

    root_constants = []
    for path in non_test_tools:
        text = read_text(path)
        if "Path(__file__).resolve().parents[1]" in text:
            root_constants.append(rel(path))
    if len(root_constants) <= len(non_test_tools):
        findings.append(Finding("pass", "root_constants", f"ROOT constants are consistent across {len(root_constants)} tools."))
    else:
        findings.append(Finding("warn", "root_constants", "ROOT constant usage needs review."))

    unsafe_patterns = []
    for path in files:
        relative = rel(path)
        if relative in SELF_AUDIT_FILES:
            continue
        text = read_text(path)
        if "shell=True" in text:
            unsafe_patterns.append((relative, "shell=True"))
        if re.search(r"\b(eval|exec)\s*\(", text) and path.name != "greg_code_quality_check.py":
            unsafe_patterns.append((relative, "eval/exec"))
    if unsafe_patterns:
        findings.append(Finding("fail", "unsafe_runtime_patterns", f"Unsafe runtime patterns found: {unsafe_patterns}."))
    else:
        findings.append(Finding("pass", "unsafe_runtime_patterns", "No shell=True or eval/exec patterns found in active code."))

    hardcoded_home_paths = []
    for path in files:
        relative = rel(path)
        if relative.startswith("tools/test_") or relative in SELF_AUDIT_FILES:
            continue
        text = read_text(path)
        if "/Users/tmarcato" in text:
            hardcoded_home_paths.append(relative)
    if hardcoded_home_paths:
        findings.append(Finding("fail", "hardcoded_home_paths", f"Hardcoded local user paths found: {hardcoded_home_paths}."))
    else:
        findings.append(Finding("pass", "hardcoded_home_paths", "No hardcoded local user paths found in active code."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "metrics": {
            "tool_files": len(tools),
            "non_test_tool_files": len(non_test_tools),
            "active_files_scanned": len(files),
        },
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"Prof Greg code quality QA passed: {'yes' if data['passed'] else 'no'}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        "Metrics:",
    ]
    for key, value in data.get("metrics", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "Findings:"])
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Prof Greg active code structure and maintainability.")
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
