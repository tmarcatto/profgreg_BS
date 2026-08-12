#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from greg_security import assert_safe_run_slug


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


@dataclass
class StageStatus:
    stage: str
    gate_status: str
    next_action: str
    next_command: str
    blockers: list[str]


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
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def lid(lesson: int) -> str:
    return f"lesson_{lesson:02d}"


def exists(run: Path, relative_path: str) -> bool:
    return (run / relative_path).exists()


def intake_ready(run: Path) -> bool:
    checker = load_module("greg_intake_check", "tools/greg_intake_check.py")
    return bool(checker.run_checks(run / "input" / "intake.md").get("passed"))


def artifact_list(run: Path) -> list[dict[str, Any]]:
    manifest = read_json(run / "process_review" / "canonical_artifacts.json")
    if manifest.get("artifacts"):
        return [
            {
                "key": item.get("key"),
                "path": rel(run / item.get("path", "")),
                "exists": (run / item.get("path", "")).exists(),
                "status": item.get("status"),
                "stage": item.get("stage"),
            }
            for item in manifest["artifacts"]
        ]

    candidates = [
        ("intake", "input/intake.md", "active", "INTAKE"),
        ("course_map_md", "course_map/course_map.md", "active", "COURSE_MAP"),
        ("course_map_json", "course_map/course_map.json", "supporting", "COURSE_MAP"),
        ("course_map_qa", "course_map/course_map_qa.md", "supporting", "COURSE_MAP"),
        ("source_ledger", "sources/source_ledger.json", "active", "SOURCE_LEDGER"),
        ("student_references", "sources/student_references.md", "supporting", "SOURCE_LEDGER"),
        ("lesson_draft", "lesson_draft/lesson_01_draft.md", "active", "DRAFT"),
        ("study_guide_pdf", "docx_pdf/lesson_01_study_guide.pdf", "active", "DOCX_PDF"),
        ("study_guide_approval", "approval/lesson_01_study_guide_approval.md", "gate", "HUMAN_APPROVAL"),
        ("deck_pptx", "deck/lesson_01_deck.pptx", "active", "DECK"),
        ("deck_approval", "approval/lesson_01_deck_approval.md", "gate", "DECK"),
        ("lesson_pipeline_qa", "process_review/lesson_01_pipeline_qa.md", "supporting", "PROCESS_REVIEW"),
    ]
    return [
        {
            "key": key,
            "path": rel(run / path),
            "exists": (run / path).exists(),
            "status": status,
            "stage": stage,
        }
        for key, path, status, stage in candidates
    ]


def infer_stage(run: Path, lesson: int) -> StageStatus:
    lesson_tag = lid(lesson)
    blockers: list[str] = []

    if not run.exists():
        return StageStatus(
            stage="MISSING_RUN",
            gate_status="Run folder does not exist.",
            next_action="Create the run folder before production can start.",
            next_command="python3 tools/greg_create_run.py \"[Course Title]\" --slug [course-slug] --level Basic",
            blockers=["Run folder not found."],
        )

    if not exists(run, "input/intake.md"):
        return StageStatus(
            stage="INTAKE",
            gate_status="Missing intake.",
            next_action="Create or complete the intake.",
            next_command="Fill runs/[course-slug]/input/intake.md",
            blockers=["Missing input/intake.md."],
        )

    if not intake_ready(run):
        return StageStatus(
            stage="INTAKE",
            gate_status="Intake exists but is not complete enough for Course Map.",
            next_action="Complete the intake with real course level, syllabus direction, and source-material notes.",
            next_command=f"python3 tools/greg_intake_check.py runs/{run.name}/input/intake.md",
            blockers=[],
        )

    if not (exists(run, "course_map/course_map.md") and exists(run, "course_map/course_map.json") and exists(run, "course_map/course_map_qa.md")):
        return StageStatus(
            stage="COURSE_MAP",
            gate_status="Course Map not complete or not QA-approved.",
            next_action="Produce Course Map, adaptation log, and Course Map QA.",
            next_command=f"python3 tools/greg_course_map_quality_check.py runs/{run.name}/course_map/course_map.json runs/{run.name}/course_map/course_map.md runs/{run.name}/course_map/syllabus_adaptation_log.md --intake runs/{run.name}/input/intake.md",
            blockers=[],
        )

    if not (exists(run, "sources/source_ledger.json") and exists(run, "sources/student_references.md")):
        return StageStatus(
            stage="SOURCE_LEDGER",
            gate_status="Source ledger or student references missing.",
            next_action="Build source ledger, research log, source gaps, and student references.",
            next_command=f"python3 tools/greg_source_reference_check.py runs/{run.name}/sources/source_ledger.json runs/{run.name}/sources/student_references.md",
            blockers=[],
        )

    if not exists(run, f"lesson_draft/{lesson_tag}_draft.md"):
        return StageStatus(
            stage="DRAFT",
            gate_status="Lesson draft missing.",
            next_action="Draft the study guide lesson from the approved Course Map and sources.",
            next_command=f"python3 tools/greg_study_guide_content_check.py runs/{run.name}/lesson_draft/{lesson_tag}_draft.md",
            blockers=[],
        )

    if not exists(run, f"docx_pdf/{lesson_tag}_study_guide.pdf"):
        return StageStatus(
            stage="DOCX_PDF",
            gate_status="Final study guide PDF missing.",
            next_action="Run review gates and produce the final study guide PDF.",
            next_command=f"python3 tools/greg_study_guide_content_check.py runs/{run.name}/lesson_draft/{lesson_tag}_draft.md",
            blockers=[],
        )

    if not exists(run, f"approval/{lesson_tag}_study_guide_approval.md"):
        return StageStatus(
            stage="HUMAN_APPROVAL",
            gate_status="Study guide awaits human approval.",
            next_action="Ask for explicit approval of the final study guide before deck production.",
            next_command=f"Create runs/{run.name}/approval/{lesson_tag}_study_guide_approval.md after approval.",
            blockers=["Deck generation is blocked until study guide approval exists."],
        )

    approved_deck = exists(run, f"approval/{lesson_tag}_deck_approval.md")
    deck_exists = bool(list((run / "deck").glob(f"{lesson_tag}_deck*.pptx")))
    if not deck_exists:
        return StageStatus(
            stage="DECK",
            gate_status="Study guide approved; deck may be produced.",
            next_action="Produce the English PPTX deck and deck QA.",
            next_command=f"python3 tools/greg_lesson_pipeline_qa.py {run.name} --lesson {lesson}",
            blockers=[],
        )

    if deck_exists and not approved_deck:
        return StageStatus(
            stage="DECK_APPROVAL",
            gate_status="Deck exists but approval record is missing.",
            next_action="Run deck QA, present the deck, and capture approval or revision notes.",
            next_command=f"python3 tools/greg_lesson_pipeline_qa.py {run.name} --lesson {lesson}",
            blockers=[],
        )

    if not exists(run, f"process_review/{lesson_tag}_pipeline_qa.md"):
        return StageStatus(
            stage="PROCESS_REVIEW",
            gate_status="Study guide and deck approvals found; consolidated pipeline QA missing.",
            next_action="Run and save the consolidated lesson pipeline QA.",
            next_command=f"python3 tools/greg_lesson_pipeline_qa.py {run.name} --lesson {lesson} --include-localization --output runs/{run.name}/process_review/{lesson_tag}_pipeline_qa.md",
            blockers=[],
        )

    return StageStatus(
        stage="FULL_FLOW_CONFIRMATION_COMPLETE",
        gate_status="Study guide, deck, approvals, canonical manifest, and consolidated QA are present.",
        next_action="Continue Phase 3A by reducing manual production steps or start a new full-flow test run.",
        next_command=f"python3 tools/greg_lesson_pipeline_qa.py {run.name} --lesson {lesson} --include-localization",
        blockers=[],
    )


def run_pipeline_qa(course_slug: str, lesson: int, include_localization: bool) -> dict[str, Any]:
    course_slug = assert_safe_run_slug(course_slug)
    module = load_module("greg_lesson_pipeline_qa", "tools/greg_lesson_pipeline_qa.py")
    return module.run_pipeline(course_slug, lesson=lesson, include_localization=include_localization)


def save_pipeline_qa(course_slug: str, lesson: int, include_localization: bool) -> Path:
    course_slug = assert_safe_run_slug(course_slug)
    run = RUNS / course_slug
    out = run / "process_review" / f"{lid(lesson)}_pipeline_qa.md"
    command = [
        sys.executable,
        str(ROOT / "tools" / "greg_lesson_pipeline_qa.py"),
        course_slug,
        "--lesson",
        str(lesson),
        "--output",
        str(out),
    ]
    if include_localization:
        command.append("--include-localization")
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    return out


def refresh_lesson_sources(course_slug: str, lesson: int) -> Path:
    course_slug = assert_safe_run_slug(course_slug)
    run = RUNS / course_slug
    out = run / "sources" / f"{lid(lesson)}_source_refresh_qa.md"
    command = [
        sys.executable,
        str(ROOT / "tools" / "greg_lesson_source_refresh_check.py"),
        course_slug,
        "--lesson",
        str(lesson),
        "--write-stub",
        "--output",
        str(out),
    ]
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    return out


def update_canonical_manifest(course_slug: str) -> None:
    course_slug = assert_safe_run_slug(course_slug)
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "greg_canonical_artifacts.py"), course_slug, "--write"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def execute_safe_action(course_slug: str, lesson: int, action: str, include_localization: bool) -> list[str]:
    course_slug = assert_safe_run_slug(course_slug)
    run = RUNS / course_slug
    stage = infer_stage(run, lesson)
    executed: list[str] = []

    if action == "status":
        return executed

    if action == "refresh":
        out = refresh_lesson_sources(course_slug, lesson)
        executed.append(f"Saved lesson source refresh QA to {rel(out)}.")
        update_canonical_manifest(course_slug)
        executed.append("Updated canonical artifact manifest.")
        return executed

    if action == "qa":
        out = save_pipeline_qa(course_slug, lesson, include_localization)
        executed.append(f"Saved consolidated QA to {rel(out)}.")
        update_canonical_manifest(course_slug)
        executed.append("Updated canonical artifact manifest.")
        return executed

    if action == "lifecycle":
        source_out = refresh_lesson_sources(course_slug, lesson)
        executed.append(f"Saved lesson source refresh QA to {rel(source_out)}.")
        qa_out = save_pipeline_qa(course_slug, lesson, include_localization)
        executed.append(f"Saved consolidated QA to {rel(qa_out)}.")
        update_canonical_manifest(course_slug)
        executed.append("Updated canonical artifact manifest.")
        return executed

    if action == "next":
        if stage.stage in {"FULL_FLOW_CONFIRMATION_COMPLETE", "PROCESS_REVIEW", "DECK_APPROVAL", "DECK"}:
            out = save_pipeline_qa(course_slug, lesson, include_localization)
            executed.append(f"Saved consolidated QA to {rel(out)}.")
            update_canonical_manifest(course_slug)
            executed.append("Updated canonical artifact manifest.")
            return executed
        if stage.stage == "COURSE_MAP":
            executed.append("Next safe automatic action is not available yet: Course Map generation remains a controlled production step.")
            return executed
        if stage.stage == "SOURCE_LEDGER":
            executed.append("Next safe automatic action is not available yet: source research/ledger generation remains a controlled production step.")
            return executed
        if stage.stage in {"DRAFT", "DOCX_PDF", "HUMAN_APPROVAL"}:
            executed.append(f"Next safe automatic action is blocked by stage `{stage.stage}`.")
            return executed
        return executed

    raise ValueError(f"Unsupported action: {action}")


def maybe_write_status(
    run: Path,
    lesson: int,
    stage: StageStatus,
    qa: dict[str, Any] | None,
    action: str = "status",
    executed: list[str] | None = None,
) -> Path:
    out = run / "process_review" / f"{lid(lesson)}_operator_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_markdown(build_report(run.name, lesson, stage, artifact_list(run), qa, action=action, executed=executed)) + "\n",
        encoding="utf-8",
    )
    return out


def build_report(
    course_slug: str,
    lesson: int,
    stage: StageStatus,
    artifacts: list[dict[str, Any]],
    qa: dict[str, Any] | None,
    action: str = "status",
    executed: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "course_slug": course_slug,
        "lesson": lesson,
        "action": action,
        "executed": executed or [],
        "stage": asdict(stage),
        "artifacts": artifacts,
        "pipeline_qa": qa,
    }


def render_markdown(data: dict[str, Any]) -> str:
    stage = data["stage"]
    lines = [
        "# Greg Lesson Operator Report",
        "",
        f"Course: `{data['course_slug']}`",
        f"Lesson: {data['lesson']:02d}",
        f"Action: `{data.get('action', 'status')}`",
        f"Current stage: `{stage['stage']}`",
        f"Gate status: {stage['gate_status']}",
        "",
        f"Next action: {stage['next_action']}",
        f"Suggested command: `{stage['next_command']}`",
    ]

    if stage["blockers"]:
        lines.extend(["", "Blockers:"])
        for blocker in stage["blockers"]:
            lines.append(f"- {blocker}")
    else:
        lines.extend(["", "Blockers: none"])

    if data.get("executed"):
        lines.extend(["", "Executed:"])
        for item in data["executed"]:
            lines.append(f"- {item}")

    qa = data.get("pipeline_qa")
    if qa:
        lines.extend(
            [
                "",
                "Pipeline QA:",
                f"- passed: {'yes' if qa.get('passed') else 'no'}",
                f"- failures: {qa.get('fail_count', 0)}",
                f"- warnings: {qa.get('warn_count', 0)}",
            ]
        )
        blocked = qa.get("blocked_gates") or []
        if blocked:
            lines.append(f"- blocked gates: {', '.join(blocked)}")

    active = [item for item in data["artifacts"] if item["exists"] and item["status"] in {"active", "approved", "gate"}]
    if active:
        lines.extend(["", "Active Artifacts:"])
        for item in active:
            lines.append(f"- {item['key']}: `{item['path']}`")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Prof Greg lesson operator: status, gate, and next action.")
    parser.add_argument("course_slug", help="Course/run slug under runs/.")
    parser.add_argument("--lesson", type=int, default=1, help="Lesson number. Defaults to 1.")
    parser.add_argument(
        "--action",
        choices=["status", "refresh", "qa", "lifecycle", "next"],
        default="status",
        help="Safe operator action. Defaults to status.",
    )
    parser.add_argument("--qa", action="store_true", help="Run consolidated lesson pipeline QA when possible.")
    parser.add_argument("--include-localization", action="store_true", help="Include localization gates when running QA.")
    parser.add_argument("--write-report", action="store_true", help="Write process_review/lesson_XX_operator_report.md.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    run = RUNS / args.course_slug
    stage = infer_stage(run, args.lesson)
    executed: list[str] = []
    if run.exists() and not stage.blockers and args.action in {"refresh", "qa", "lifecycle", "next"}:
        executed = execute_safe_action(args.course_slug, args.lesson, args.action, args.include_localization)
        stage = infer_stage(run, args.lesson)
    qa = None
    if (args.qa or args.action == "qa") and run.exists() and not stage.blockers:
        qa = run_pipeline_qa(args.course_slug, args.lesson, args.include_localization)
    report = build_report(args.course_slug, args.lesson, stage, artifact_list(run), qa, args.action, executed)
    if args.write_report and run.exists():
        maybe_write_status(run, args.lesson, stage, qa, action=args.action, executed=executed)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(report))
    return 1 if stage.blockers or (qa and not qa.get("passed")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
