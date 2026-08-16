#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


@dataclass
class ArtifactStatus:
    name: str
    path: str
    exists: bool
    role: str


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def artifact(run: Path, name: str, relative_path: str, role: str) -> ArtifactStatus:
    path = run / relative_path
    return ArtifactStatus(name=name, path=rel(path), exists=path.exists(), role=role)


def first_existing(run: Path, name: str, relative_paths: list[str], role: str) -> ArtifactStatus:
    for relative_path in relative_paths:
        item = artifact(run, name, relative_path, role)
        if item.exists:
            return item
    return artifact(run, name, relative_paths[0], role)


def latest_matching(run: Path, name: str, patterns: list[str], role: str) -> ArtifactStatus:
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(run.glob(pattern))
    matches = sorted(set(matches), key=lambda path: (path.stat().st_mtime if path.exists() else 0, path.name))
    if matches:
        path = matches[-1]
        return ArtifactStatus(name=name, path=rel(path), exists=True, role=role)
    return artifact(run, name, patterns[0].replace("*", "latest"), role)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def lesson_titles(run: Path) -> dict[str, str]:
    data = load_json(run / "course_map" / "course_map.json")
    titles: dict[str, str] = {}
    for index, item in enumerate(data.get("lessons") or [], start=1):
        raw_number = item.get("lesson_number") or item.get("number") or item.get("lesson") or index
        try:
            number = f"{int(raw_number):02d}"
        except (TypeError, ValueError):
            number = str(raw_number).zfill(2)
        title = item.get("title") or item.get("lesson_title")
        if title:
            titles[number] = str(title).strip()
    return titles


def read_status_field(status_text: str, label: str) -> str:
    prefix = f"{label}:"
    for line in status_text.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return ""


def infer_stage(artifacts: list[ArtifactStatus]) -> str:
    by_name = {item.name: item.exists for item in artifacts}
    if by_name.get("approval"):
        return "HUMAN_APPROVAL"
    if by_name.get("study_guide_pdf"):
        return "DOCX_PDF"
    if by_name.get("lesson_draft"):
        return "DRAFT"
    if by_name.get("source_policy") or by_name.get("source_ledger"):
        return "SOURCE_LEDGER"
    if by_name.get("course_map"):
        return "COURSE_MAP"
    return "INTAKE"


def summarize(course_slug: str) -> dict:
    run = RUNS / course_slug
    run_status = run / "process_review" / "run_status.md"
    canonical_json = run / "process_review" / "canonical_artifacts.json"
    workspace_status = ROOT / "workspace" / "STATUS.md"

    manifest = load_json(canonical_json)
    if manifest.get("artifacts"):
        artifacts = [
            ArtifactStatus(
                name=item["key"],
                path=rel(run / item["path"]),
                exists=(run / item["path"]).exists(),
                role="active" if item["status"] in {"active", "approved"} else item["status"],
            )
            for item in manifest["artifacts"]
        ]
    else:
        artifacts = [
            artifact(run, "intake", "input/intake.md", "active"),
            artifact(run, "course_map", "course_map/course_map.md", "active"),
            artifact(run, "source_policy", "sources/source_policy_v1.md", "active"),
            artifact(run, "source_ledger", "sources/source_ledger.json", "supporting"),
            latest_matching(run, "lesson_draft", ["lesson_draft/lesson_*_draft.md"], "active"),
            first_existing(run, "study_guide_pdf", ["docx_pdf/lesson_01_study_guide.pdf", "output/pdf/*.pdf"], "active"),
            first_existing(run, "study_guide_approval", ["approval/lesson_01_study_guide_approval.md"], "gate"),
            latest_matching(run, "deck", ["deck/lesson_*_deck_r*.pptx", "deck/lesson_*_deck*.pptx"], "active"),
            first_existing(run, "deck_qa", ["deck/lesson_01_deck_qa.md"], "supporting"),
            first_existing(run, "deck_approval", ["approval/lesson_01_deck_approval.md"], "gate"),
            first_existing(run, "localization_pt_br", ["localization/pt-br/lesson_01_localization_qa.md"], "supporting"),
            first_existing(run, "localization_es_419", ["localization/es-419/lesson_01_localization_qa.md"], "supporting"),
            first_existing(run, "process_review", ["process_review/full_flow_test_report.md"], "status"),
        ]

    parked = []
    run_status_text = read_text(run_status)
    run_stage = read_status_field(run_status_text, "Current stage")
    run_gate_status = read_status_field(run_status_text, "Gate status")
    run_next_action = read_status_field(run_status_text, "Next recommended action")

    next_action = "Return to the Greg operator layer: make status, routing, and canonical-artifact handling reliable."
    if run_next_action:
        next_action = run_next_action

    approval_exists = (run / "approval" / "lesson_01_study_guide_approval.md").exists()
    gate_status = run_gate_status or "No final study-guide approval record found. Deck production remains gated."
    deck_approval_exists = (run / "approval" / "lesson_01_deck_approval.md").exists()
    if deck_approval_exists:
        gate_status = "Study guide and deck approval records found."
    elif approval_exists:
        gate_status = "Final study-guide approval record found. Deck production may proceed if requested."

    blockers = []
    if not run.exists():
        blockers.append("Run folder not found.")
    if run.exists() and not (run / "input" / "intake.md").exists():
        blockers.append("Missing input/intake.md.")

    stage = run_stage or infer_stage(artifacts)

    return {
        "course_slug": course_slug,
        "run_folder": rel(run),
        "stage": stage,
        "artifacts": [asdict(item) for item in artifacts],
        "parked": parked,
        "blockers": blockers,
        "gate_status": gate_status,
        "workspace_status": rel(workspace_status) if workspace_status.exists() else None,
        "canonical_manifest": rel(canonical_json) if canonical_json.exists() else None,
        "next_recommended_action": next_action,
        "lessons": summarize_lessons(run, manifest),
    }


def summarize_lessons(run: Path, manifest: dict) -> list[dict]:
    lessons: dict[str, dict] = {}
    titles = lesson_titles(run)
    for item in manifest.get("artifacts", []):
        lesson = item.get("lesson")
        key = item.get("key", "")
        if not lesson:
            continue
        row = lessons.setdefault(
            lesson,
            {
                "lesson": lesson,
                "title": titles.get(str(lesson).zfill(2), ""),
                "study_guide": "missing",
                "deck": "missing",
                "pipeline_qa": "missing",
            },
        )
        path = run / item.get("path", "")
        exists = path.exists()
        status = item.get("status", "missing")
        if key.endswith("_study_guide_pdf"):
            row["study_guide"] = status if exists else "missing"
            row["study_guide_path"] = rel(path)
        elif key.endswith("_deck_pptx"):
            row["deck"] = status if exists else "missing"
            row["deck_path"] = rel(path)
        elif key.endswith("_pipeline_qa"):
            row["pipeline_qa"] = "present" if exists else "missing"
            row["pipeline_qa_path"] = rel(path)
    return [lessons[key] for key in sorted(lessons)]


def render_markdown(data: dict) -> str:
    lines = [
        f"Current stage: `{data['stage']}`",
    "",
        "Active artifacts:",
    ]
    for item in data["artifacts"]:
        if item["role"] in {"active", "active reference"}:
            mark = "present" if item["exists"] else "missing"
            lines.append(f"- {item['name']}: {item['path']} ({mark})")

    if data["parked"]:
        lines.extend(["", "Parked artifacts:"])
        for name in data["parked"]:
            lines.append(f"- {name}")

    lines.extend([
        "",
        f"Gate status: {data['gate_status']}",
    ])

    if data.get("canonical_manifest"):
        lines.extend(["", f"Canonical manifest: {data['canonical_manifest']}"])

    if data.get("lessons"):
        lines.extend(["", "Lesson status:", "| Lesson | Study guide | Deck | Pipeline QA |", "|---|---|---|---|"])
        for lesson in data["lessons"]:
            lines.append(
                f"| {lesson['lesson']} | {lesson['study_guide']} | {lesson['deck']} | {lesson['pipeline_qa']} |"
            )

    lines.append("")
    if data["blockers"]:
        lines.append("Blockers:")
        for blocker in data["blockers"]:
            lines.append(f"- {blocker}")
    else:
        lines.append("Blockers: none")

    lines.extend([
        "",
        f"Next recommended action: {data['next_recommended_action']}",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Show Prof Greg course/run status.")
    parser.add_argument("course_slug", nargs="?", default="blueprint-reading-crash-course-for-construction-careers")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    data = summarize(args.course_slug)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(data))
    return 1 if data["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
