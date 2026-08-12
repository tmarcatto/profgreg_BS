#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from greg_security import assert_safe_run_slug, assert_safe_write_path

ROOT = Path(__file__).resolve().parents[1]
BUNDLED_PYTHON = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "python" / "bin" / "python3"


@dataclass
class GateResult:
    gate: str
    status: str
    passed: bool
    fail_count: int
    warn_count: int
    path: str
    note: str
    findings: list[dict[str, Any]]


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def lesson_id(lesson: int) -> str:
    return f"lesson_{lesson:02d}"


def manifest_artifact(run: Path, key: str, lesson: int | None = None) -> Path | None:
    manifest = read_json(run / "process_review" / "canonical_artifacts.json")
    expected_lesson = f"{lesson:02d}" if lesson is not None else None
    candidate_keys = [key]
    if expected_lesson is not None:
        candidate_keys.insert(0, f"lesson_{expected_lesson}_{key}")
    for item in manifest.get("artifacts") or []:
        if item.get("key") in candidate_keys and item.get("path"):
            item_lesson = item.get("lesson")
            if expected_lesson is not None and item_lesson not in {None, expected_lesson}:
                continue
            return run / item["path"]
    return None


def latest_glob(run: Path, patterns: list[str]) -> Path | None:
    revisioned: list[tuple[int, Path]] = []
    canonical: list[Path] = []
    for pattern in patterns:
        for path in run.glob(pattern):
            match = re.search(r"_r(\d+)\.pptx$", path.name)
            if match:
                revisioned.append((int(match.group(1)), path))
            else:
                canonical.append(path)
    if revisioned:
        return sorted(revisioned, key=lambda item: (item[0], item[1].stat().st_mtime, item[1].name))[-1][1]
    matches = sorted(set(canonical), key=lambda path: (path.stat().st_mtime, path.name))
    return matches[-1] if matches else None


def stage_result_from_data(gate: str, path: Path, data: dict[str, Any], note: str = "") -> GateResult:
    return GateResult(
        gate=gate,
        status="pass" if data.get("passed") else "fail",
        passed=bool(data.get("passed")),
        fail_count=int(data.get("fail_count") or 0),
        warn_count=int(data.get("warn_count") or 0),
        path=rel(path),
        note=note,
        findings=data.get("findings") or [],
    )


def skipped(gate: str, path: Path, note: str) -> GateResult:
    return GateResult(
        gate=gate,
        status="skipped",
        passed=True,
        fail_count=0,
        warn_count=0,
        path=rel(path),
        note=note,
        findings=[],
    )


def failed_exception(gate: str, path: Path, exc: BaseException) -> GateResult:
    return GateResult(
        gate=gate,
        status="fail",
        passed=False,
        fail_count=1,
        warn_count=0,
        path=rel(path),
        note=f"Checker could not run: {exc}",
        findings=[{"status": "fail", "check": "checker_exception", "note": str(exc)}],
    )


def run_gate(gate: str, path: Path, callback: Callable[[], dict[str, Any]], note: str = "") -> GateResult:
    try:
        return stage_result_from_data(gate, path, callback(), note)
    except BaseException as exc:  # keep the consolidated report useful even if one checker crashes
        return failed_exception(gate, path, exc)


def run_pdf_layout_with_fallback(pdf_path: Path, qa_path: Path, pdf_checker) -> dict[str, Any]:
    try:
        return pdf_checker.run_checks(pdf_path, qa_path)
    except SystemExit as exc:
        if "Missing pypdf" not in str(exc) or not BUNDLED_PYTHON.exists():
            raise
        completed = subprocess.run(
            [
                str(BUNDLED_PYTHON),
                str(ROOT / "tools" / "greg_pdf_layout_check.py"),
                str(pdf_path),
                "--qa",
                str(qa_path),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if not completed.stdout.strip():
            raise RuntimeError(completed.stderr.strip() or "Bundled PDF checker returned no output.")
        return json.loads(completed.stdout)


def run_pipeline(course_slug: str, lesson: int = 1, production_date: date | None = None, include_localization: bool = False) -> dict[str, Any]:
    course_slug = assert_safe_run_slug(course_slug)
    production_date = production_date or date.today()
    run = ROOT / "runs" / course_slug
    lid = lesson_id(lesson)

    course_map_checker = load_module("greg_course_map_quality_check", "tools/greg_course_map_quality_check.py")
    source_checker = load_module("greg_source_reference_check", "tools/greg_source_reference_check.py")
    lesson_source_refresh_checker = load_module("greg_lesson_source_refresh_check", "tools/greg_lesson_source_refresh_check.py")
    draft_checker = load_module("greg_study_guide_content_check", "tools/greg_study_guide_content_check.py")
    cross_lesson_checker = load_module("greg_cross_lesson_mece_check", "tools/greg_cross_lesson_mece_check.py")
    registry_checker = load_module("greg_course_registry", "tools/greg_course_registry.py")
    visual_checker = load_module("greg_visual_plan_check", "tools/greg_visual_plan_check.py")
    pdf_checker = load_module("greg_pdf_layout_check", "tools/greg_pdf_layout_check.py")
    deck_checker = load_module("greg_deck_quality_check", "tools/greg_deck_quality_check.py")
    localized_checker = load_module("greg_localized_deck_text_map_check", "tools/greg_localized_deck_text_map_check.py")

    results: list[GateResult] = []

    course_map_json = run / "course_map" / "course_map.json"
    course_map_md = run / "course_map" / "course_map.md"
    adaptation_log = run / "course_map" / "syllabus_adaptation_log.md"
    intake = run / "input" / "intake.md"
    results.append(
        run_gate(
            "course_map",
            course_map_json,
            lambda: course_map_checker.run_checks(course_map_json, course_map_md, adaptation_log, intake),
        )
    )

    source_ledger = run / "sources" / "source_ledger.json"
    student_refs = run / "sources" / "student_references.md"
    results.append(
        run_gate(
            "sources_references",
            source_ledger,
            lambda: source_checker.run_checks(source_ledger, student_refs, production_date),
        )
    )

    lesson_source_refresh = run / "sources" / f"{lid}_source_refresh.json"
    results.append(
        run_gate(
            "lesson_source_refresh",
            lesson_source_refresh,
            lambda: lesson_source_refresh_checker.run_checks(course_slug, lesson),
        )
    )

    draft = run / "lesson_draft" / f"{lid}_draft.md"
    results.append(
        run_gate(
            "study_guide_content",
            draft,
            lambda: draft_checker.run_checks(draft),
        )
    )

    cross_lesson_report = run / "review" / f"{lid}_cross_lesson_mece_qa.md"
    results.append(
        run_gate(
            "cross_lesson_mece",
            cross_lesson_report,
            lambda: cross_lesson_checker.run_checks(course_slug, lesson),
        )
    )

    registry_report = run / "process_review" / "course_registry_qa.md"
    results.append(
        run_gate(
            "course_registry",
            registry_report,
            lambda: registry_checker.run_checks(course_slug),
        )
    )

    visual_plan = (
        manifest_artifact(run, "deck_visual_plan", lesson)
        or run / "deck" / f"{lid}_visual_plan.json"
        or run / "review" / f"{lid}_visual_plan.json"
    )
    if visual_plan.exists():
        results.append(
            run_gate(
                "visual_plan",
                visual_plan,
                lambda: visual_checker.run_checks(visual_plan),
            )
        )
    else:
        results.append(skipped("visual_plan", visual_plan, "No visual plan found for this lesson/run."))

    study_pdf = manifest_artifact(run, "study_guide_pdf", lesson) or run / "docx_pdf" / f"{lid}_study_guide.pdf"
    if study_pdf.exists():
        render_qa = run / "docx_pdf" / f"{lid}_render_qa.md"
        results.append(
            run_gate(
                "pdf_layout",
                study_pdf,
                lambda: run_pdf_layout_with_fallback(study_pdf, render_qa, pdf_checker),
            )
        )
    else:
        results.append(skipped("pdf_layout", study_pdf, "No study guide PDF found yet."))

    deck = manifest_artifact(run, "deck_pptx", lesson) or latest_glob(run, [f"deck/{lid}_deck_r*.pptx", f"deck/{lid}_deck.pptx"])
    if deck and deck.exists():
        deck_qa = run / "deck" / f"{lid}_deck_qa.md"
        results.append(
            run_gate(
                "deck",
                deck,
                lambda: deck_checker.run_checks(deck, deck_qa),
            )
        )
    else:
        results.append(skipped("deck", run / "deck" / f"{lid}_deck.pptx", "No deck found yet."))

    if include_localization:
        for locale in ("pt-br", "es-419"):
            text_map = run / "localization" / locale / f"{lid}_deck_text_map_{locale}.md"
            qa_path = run / "localization" / locale / f"{lid}_deck_localization_qa.md"
            if text_map.exists():
                results.append(
                    run_gate(
                        f"localization_{locale}_deck_text_map",
                        text_map,
                        lambda text_map=text_map, qa_path=qa_path: localized_checker.run_checks(text_map, qa_path),
                    )
                )
            else:
                results.append(skipped(f"localization_{locale}_deck_text_map", text_map, "No localized deck text map found."))

    fail_count = sum(item.fail_count for item in results)
    warn_count = sum(item.warn_count for item in results)
    blocked_gates = [item.gate for item in results if item.status == "fail"]
    passed = fail_count == 0

    return {
        "course_slug": course_slug,
        "run_folder": rel(run),
        "lesson": lesson,
        "production_date": production_date.isoformat(),
        "passed": passed,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "blocked_gates": blocked_gates,
        "gates": [asdict(item) for item in results],
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"Lesson pipeline QA passed: {'yes' if data['passed'] else 'no'}",
        f"Course: {data['course_slug']}",
        f"Lesson: {data['lesson']:02d}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        "| Gate | Status | Failures | Warnings | Artifact | Note |",
        "|---|---|---:|---:|---|---|",
    ]
    for gate in data["gates"]:
        note = (gate["note"] or "").replace("|", "/")
        lines.append(
            f"| {gate['gate']} | {gate['status']} | {gate['fail_count']} | {gate['warn_count']} | `{gate['path']}` | {note} |"
        )

    issue_gates = [gate for gate in data["gates"] if gate["status"] == "fail" or gate["warn_count"]]
    if issue_gates:
        lines.extend(["", "Issues:"])
        for gate in issue_gates:
            lines.append(f"- {gate['gate']}:")
            for finding in gate["findings"]:
                if finding.get("status") != "pass":
                    lines.append(f"  - {finding.get('status', '').upper()} {finding.get('check')}: {finding.get('note')}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run consolidated Prof Greg QA for one lesson/run.")
    parser.add_argument("course_slug", help="Course/run slug under runs/.")
    parser.add_argument("--lesson", type=int, default=1, help="Lesson number. Defaults to 1.")
    parser.add_argument("--production-date", help="Production date YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--include-localization", action="store_true", help="Include localized deck text-map QA.")
    parser.add_argument("--output", help="Optional path to write the Markdown report.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    production_date = date.fromisoformat(args.production_date) if args.production_date else None
    data = run_pipeline(args.course_slug, args.lesson, production_date, args.include_localization)
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
