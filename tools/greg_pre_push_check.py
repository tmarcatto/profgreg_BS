#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from greg_security import assert_safe_write_path


ROOT = Path(__file__).resolve().parents[1]
REPORT = "runs/_system/pre_push_qa.md"


@dataclass
class Step:
    name: str
    command: list[str]


STEPS = [
    Step("security QA", [sys.executable, "tools/greg_security_check.py", "--output", "runs/_system/security_qa.md"]),
    Step("code quality QA", [sys.executable, "tools/greg_code_quality_check.py", "--output", "runs/_system/code_quality_qa.md"]),
    Step("model routing QA", [sys.executable, "tools/greg_model_routing_check.py", "--output", "runs/_system/model_routing_security_qa.md"]),
    Step("renderer reuse QA", [sys.executable, "tools/greg_renderer_reuse_check.py", "--output", "runs/_system/renderer_reuse_security_qa.md"]),
    Step(
        "unit tests",
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tools",
            "-p",
            "test_greg_*.py",
        ],
    ),
]


def run_step(step: Step) -> tuple[bool, str]:
    result = subprocess.run(step.command, cwd=ROOT, text=True, capture_output=True, check=False)
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    return result.returncode == 0, output


def without_output_args(command: list[str]) -> list[str]:
    cleaned: list[str] = []
    skip_next = False
    for value in command:
        if skip_next:
            skip_next = False
            continue
        if value == "--output":
            skip_next = True
            continue
        cleaned.append(value)
    return cleaned


def step_for_mode(step: Step, *, update_reports: bool) -> Step:
    if update_reports:
        return step
    return Step(step.name, without_output_args(step.command))


def render_report(results: list[tuple[Step, bool, str]]) -> str:
    passed = all(ok for _, ok, _ in results)
    lines = [
        f"Prof Greg pre-push QA passed: {'yes' if passed else 'no'}",
        f"Failures: {sum(1 for _, ok, _ in results if not ok)}",
        "",
        "Steps:",
    ]
    for step, ok, output in results:
        lines.append(f"- {'PASS' if ok else 'FAIL'} {step.name}")
        if output:
            snippet = output.splitlines()[:12]
            lines.extend(f"  {line}" for line in snippet)
            if len(output.splitlines()) > len(snippet):
                lines.append("  ...")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Prof Greg checks expected before pushing to GitHub.")
    parser.add_argument("--output", default=REPORT, help="Markdown report path.")
    parser.add_argument("--no-update-reports", action="store_true", help="Run checks without updating tracked QA report files.")
    args = parser.parse_args()

    steps = [step_for_mode(step, update_reports=not args.no_update_reports) for step in STEPS]
    results = [(step, *run_step(step)) for step in steps]
    report = render_report(results)
    output = assert_safe_write_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(report, end="")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
