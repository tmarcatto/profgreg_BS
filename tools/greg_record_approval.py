#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from greg_security import assert_safe_run_slug


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


@dataclass
class ApprovalRecord:
    course_slug: str
    lesson: int
    artifact_type: str
    artifact_path: Path
    status: str
    approver: str
    approved_on: str
    approval_mode: str
    note: str


def load_canonical_module():
    path = ROOT / "tools" / "greg_canonical_artifacts.py"
    spec = importlib.util.spec_from_file_location("greg_canonical_artifacts", path)
    if not spec or not spec.loader:
        raise RuntimeError("Could not load canonical artifact module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules["greg_canonical_artifacts"] = module
    spec.loader.exec_module(module)
    return module


def normalize_artifact_path(course_slug: str, artifact: str) -> Path:
    course_slug = assert_safe_run_slug(course_slug)
    path = Path(artifact).expanduser()
    if path.is_absolute():
        return path
    if str(path).startswith("runs/"):
        return ROOT / path
    return RUNS / course_slug / path


def approval_path(course_slug: str, lesson: int, artifact_type: str) -> Path:
    course_slug = assert_safe_run_slug(course_slug)
    return RUNS / course_slug / "approval" / f"lesson_{lesson:02d}_{artifact_type}_approval.md"


def render_approval(record: ApprovalRecord) -> str:
    title = "Study Guide" if record.artifact_type == "study_guide" else "Deck"
    rel_artifact = record.artifact_path
    try:
        artifact_text = str(rel_artifact.relative_to(ROOT))
    except ValueError:
        artifact_text = str(rel_artifact)
    return "\n".join(
        [
            f"# Lesson {record.lesson:02d} {title} Approval",
            "",
            f"- Course slug: {record.course_slug}",
            f"- Lesson: {record.lesson:02d}",
            f"- Artifact: {artifact_text}",
            f"- Status: {record.status}",
            f"- Approved by: {record.approver}",
            f"- Approved on: {record.approved_on}",
            f"- Approval mode: {record.approval_mode}",
            "",
            "Notes:",
            f"- {record.note or 'Approved.'}",
            "",
        ]
    )


def record_approval(
    course_slug: str,
    lesson: int,
    artifact_type: str,
    artifact: str,
    status: str = "approved",
    approver: str = "user",
    approved_on: str | None = None,
    approval_mode: str = "v0_process",
    note: str = "Approved.",
    write_canonical: bool = True,
    force: bool = False,
) -> dict:
    course_slug = assert_safe_run_slug(course_slug)
    artifact_path = normalize_artifact_path(course_slug, artifact)
    if not artifact_path.exists():
        raise FileNotFoundError(f"Approved artifact does not exist: {artifact_path}")
    record = ApprovalRecord(
        course_slug=course_slug,
        lesson=lesson,
        artifact_type=artifact_type,
        artifact_path=artifact_path,
        status=status,
        approver=approver,
        approved_on=approved_on or date.today().isoformat(),
        approval_mode=approval_mode,
        note=note,
    )
    out = approval_path(course_slug, lesson, artifact_type)
    if out.exists() and not force:
        raise FileExistsError(f"Approval already exists. Re-run with --force to replace it: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_approval(record), encoding="utf-8")

    # A revision stays visible to the operator until it is explicitly approved.
    # Once approved, this exact file becomes the sole current artifact; prior
    # versions remain archival only and cannot be selected as the active file.
    state_path = RUNS / course_slug / "operator_feedback" / f"lesson_{lesson:02d}_{artifact_type}_revision_state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
        state.update({"state": "approved", "approved_artifact": str(artifact_path.relative_to(RUNS / course_slug))})
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    canonical_paths: tuple[Path, Path] | None = None
    if write_canonical:
        canonical = load_canonical_module()
        canonical_paths = canonical.write_manifest(canonical.infer_manifest(course_slug))

    return {
        "course_slug": course_slug,
        "lesson": lesson,
        "artifact_type": artifact_type,
        "artifact": str(artifact_path),
        "approval": str(out),
        "canonical_updated": bool(canonical_paths),
        "canonical_paths": [str(path) for path in canonical_paths] if canonical_paths else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Record Prof Greg lesson approval and update canonical artifacts.")
    parser.add_argument("course_slug")
    parser.add_argument("--lesson", type=int, required=True)
    parser.add_argument("--artifact-type", choices=["study_guide", "deck", "pt_br_study_guide", "pt_br_deck", "es_study_guide", "es_deck"], required=True)
    parser.add_argument("--artifact", required=True, help="Approved artifact path, relative to run folder, repo root, or absolute.")
    parser.add_argument("--status", default="approved")
    parser.add_argument("--approver", default="user")
    parser.add_argument("--approved-on")
    parser.add_argument("--approval-mode", default="v0_process")
    parser.add_argument("--note", default="Approved.")
    parser.add_argument("--no-canonical", action="store_true")
    parser.add_argument("--force", action="store_true", help="Replace an existing approval record.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    data = record_approval(
        args.course_slug,
        args.lesson,
        args.artifact_type,
        args.artifact,
        status=args.status,
        approver=args.approver,
        approved_on=args.approved_on,
        approval_mode=args.approval_mode,
        note=args.note,
        write_canonical=not args.no_canonical,
        force=args.force,
    )
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Approval recorded: {data['approval']}")
        if data["canonical_updated"]:
            print("Canonical artifact manifest updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
