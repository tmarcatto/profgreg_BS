#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
OPTIONAL_MISSING_KEYS = {
    "localization_pt_br_study_sample",
    "localization_pt_br_deck_text_map",
    "localization_pt_br_deck_fit_plan",
    "localization_es_419_study_sample",
    "localization_es_419_deck_text_map",
    "localization_es_419_deck_fit_plan",
    "process_review",
}


@dataclass
class CanonicalArtifact:
    key: str
    path: str
    status: str
    stage: str
    lesson: str | None = None
    revision: str | None = None
    approval_path: str | None = None
    qa_path: str | None = None
    notes: str = ""


def rel_to_run(run: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(run))
    except ValueError:
        return str(path)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def revision_label(path: Path) -> str | None:
    match = re.search(r"_r(\d+)(?=\.)", path.name)
    if match:
        return f"r{int(match.group(1)):02d}"
    return None


def latest(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    return sorted(existing, key=lambda path: (path.stat().st_mtime, path.name))[-1]


def latest_glob(run: Path, patterns: list[str]) -> Path | None:
    revisioned: list[tuple[int, Path]] = []
    canonical: list[Path] = []
    for pattern in patterns:
        for path in run.glob(pattern):
            match = re.search(r"_r(\d+)(?=\.)", path.name)
            if match:
                revisioned.append((int(match.group(1)), path))
            else:
                canonical.append(path)
    if revisioned:
        return sorted(revisioned, key=lambda item: (item[0], item[1].stat().st_mtime, item[1].name))[-1][1]
    return latest(sorted(set(canonical)))


def lesson_numbers(run: Path) -> list[str]:
    lessons: set[str] = set()
    for pattern in [
        "lesson_draft/lesson_*_draft.md",
        "docx_pdf/lesson_*_study_guide*.pdf",
        "deck/lesson_*_deck*.pptx",
        "approval/lesson_*_study_guide_approval.md",
        "approval/lesson_*_deck_approval.md",
        "review/lesson_*_visual_plan.json",
        "review/lesson_*_image_requests.json",
    ]:
        for path in run.glob(pattern):
            match = re.search(r"lesson_(\d+)_", path.name)
            if match:
                lessons.add(match.group(1))
    return sorted(lessons)


def normalize_approval_path(run: Path, value: str) -> Path:
    value = value.strip().strip("`").strip()
    if value.startswith(str(run) + "/"):
        return Path(value)
    run_prefix = str(run.relative_to(ROOT)) + "/"
    if value.startswith(run_prefix):
        return ROOT / value
    return run / value


def artifact_from_approval(run: Path, approval: Path) -> Path | None:
    text = read_text(approval)
    patterns = [
        r"(?:Artifact approved|Approved artifact|Artifact):\s*`([^`]+)`",
        r"(?:Artifact approved|Approved artifact|Artifact):\s*([^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        path = normalize_approval_path(run, match.group(1))
        if path.exists():
            return path
    return None


def artifact(
    run: Path,
    key: str,
    path: Path | None,
    status: str,
    stage: str,
    lesson: str | None = "01",
    approval_path: Path | None = None,
    qa_path: Path | None = None,
    notes: str = "",
) -> CanonicalArtifact:
    return CanonicalArtifact(
        key=key,
        path=rel_to_run(run, path) or "",
        status=status if path and path.exists() else "missing",
        stage=stage,
        lesson=lesson,
        revision=revision_label(path) if path else None,
        approval_path=rel_to_run(run, approval_path) if approval_path and approval_path.exists() else None,
        qa_path=rel_to_run(run, qa_path) if qa_path and qa_path.exists() else None,
        notes=notes,
    )


def approved_or_default_study_guide(run: Path, lesson: str, approval: Path) -> Path | None:
    approved = artifact_from_approval(run, approval)
    if approved:
        return approved
    canonical = run / "docx_pdf" / f"lesson_{lesson}_study_guide.pdf"
    if approval.exists() and canonical.exists():
        return canonical
    revisioned = latest_glob(run, [f"docx_pdf/lesson_{lesson}_study_guide_r*.pdf"])
    if revisioned:
        return revisioned
    return None


def approved_or_default_deck(run: Path, lesson: str, approval: Path) -> Path | None:
    approved = artifact_from_approval(run, approval)
    if approved:
        return approved
    if approval.exists():
        return latest_glob(run, [f"deck/lesson_{lesson}_deck_r*.pptx", f"deck/lesson_{lesson}_deck.pptx"])
    return latest_glob(run, [f"deck/lesson_{lesson}_deck_r*.pptx"])


def infer_manifest(course_slug: str) -> dict:
    run = RUNS / course_slug
    artifacts = [
        artifact(run, "intake", run / "input" / "intake.md", "active", "INTAKE", lesson=None),
        artifact(run, "course_map_md", run / "course_map" / "course_map.md", "active", "COURSE_MAP", lesson=None),
        artifact(run, "course_map_json", run / "course_map" / "course_map.json", "supporting", "COURSE_MAP", lesson=None),
        artifact(run, "course_map_qa", run / "course_map" / "course_map_qa.md", "supporting", "COURSE_MAP", lesson=None),
        artifact(run, "source_ledger", run / "sources" / "source_ledger.json", "active", "SOURCE_LEDGER", lesson=None),
        artifact(run, "process_review", run / "process_review" / "full_flow_test_report.md", "supporting", "PROCESS_REVIEW", lesson=None),
        artifact(run, "course_registry", run / "process_review" / "course_registry.json", "supporting", "PROCESS_REVIEW", lesson=None),
        artifact(run, "course_registry_qa", run / "process_review" / "course_registry_qa.md", "supporting", "PROCESS_REVIEW", lesson=None),
        artifact(run, "renderer_reuse_qa", run / "process_review" / "renderer_reuse_qa.md", "supporting", "PROCESS_REVIEW", lesson=None),
        artifact(run, "model_routing_qa", run / "process_review" / "model_routing_qa.md", "supporting", "PROCESS_REVIEW", lesson=None),
    ]

    for lesson in lesson_numbers(run):
        study_guide_approval = run / "approval" / f"lesson_{lesson}_study_guide_approval.md"
        deck_approval = run / "approval" / f"lesson_{lesson}_deck_approval.md"
        study_pdf = approved_or_default_study_guide(run, lesson, study_guide_approval)
        deck_pptx = approved_or_default_deck(run, lesson, deck_approval)
        pt_br_book = latest_glob(run, [f"localization/pt-br/lesson_{lesson}_study_guide_pt_br_r*.pdf"])
        pt_br_deck = latest_glob(run, [f"localization/pt-br/lesson_{lesson}_deck_pt_br_r*.pptx"])
        es_book = latest_glob(run, [f"localization/es-419/lesson_{lesson}_study_guide_es_r*.pdf"])
        es_deck = latest_glob(run, [f"localization/es-419/lesson_{lesson}_deck_es_r*.pptx"])

        artifacts.extend(
            [
                artifact(run, f"lesson_{lesson}_draft", run / "lesson_draft" / f"lesson_{lesson}_draft.md", "active", "DRAFT", lesson=lesson),
                artifact(
                    run,
                    f"lesson_{lesson}_source_refresh",
                    run / "sources" / f"lesson_{lesson}_source_refresh.json",
                    "supporting",
                    "SOURCE_LEDGER",
                    lesson=lesson,
                    qa_path=run / "sources" / f"lesson_{lesson}_source_refresh_qa.md",
                    notes="Lesson-level source applicability refresh.",
                ),
                artifact(run, f"lesson_{lesson}_pedagogy_review", run / "review" / f"lesson_{lesson}_pedagogy_review.md", "supporting", "REVIEW", lesson=lesson),
                artifact(run, f"lesson_{lesson}_citation_review", run / "review" / f"lesson_{lesson}_citation_review.md", "supporting", "REVIEW", lesson=lesson),
                artifact(run, f"lesson_{lesson}_design_qa", run / "review" / f"lesson_{lesson}_design_qa.md", "supporting", "REVIEW", lesson=lesson),
                artifact(run, f"lesson_{lesson}_visual_plan", run / "review" / f"lesson_{lesson}_visual_plan.json", "supporting", "REVIEW", lesson=lesson),
                artifact(run, f"lesson_{lesson}_visual_qa", run / "review" / f"lesson_{lesson}_visual_qa.md", "supporting", "REVIEW", lesson=lesson),
                artifact(run, f"lesson_{lesson}_image_requests", run / "review" / f"lesson_{lesson}_image_requests.md", "waiting_images", "VISUAL_CURATION", lesson=lesson),
                artifact(
                    run,
                    f"lesson_{lesson}_study_guide_pdf",
                    study_pdf,
                    "approved" if study_guide_approval.exists() else "active",
                    "DOCX_PDF",
                    lesson=lesson,
                    approval_path=study_guide_approval,
                    qa_path=run / "docx_pdf" / f"lesson_{lesson}_render_qa.md",
                    notes="Human-approved English study guide." if study_guide_approval.exists() else "Latest inferred English study guide.",
                ),
                artifact(
                    run,
                    f"lesson_{lesson}_deck_pptx",
                    deck_pptx,
                    "approved" if deck_approval.exists() else "active",
                    "DECK",
                    lesson=lesson,
                    approval_path=deck_approval,
                    qa_path=run / "deck" / f"lesson_{lesson}_deck_qa.md",
                    notes="Human-approved English deck." if deck_approval.exists() else "Latest inferred English deck; no deck approval recorded.",
                ),
                artifact(
                    run,
                    f"lesson_{lesson}_deck_visual_plan",
                    run / "deck" / f"lesson_{lesson}_visual_plan.json",
                    "supporting",
                    "DECK",
                    lesson=lesson,
                    qa_path=run / "deck" / f"lesson_{lesson}_deck_qa.md",
                    notes="Machine-checkable visual plan for the lesson deck.",
                ),
                artifact(run, f"lesson_{lesson}_study_guide_pt_br_pdf", pt_br_book, "active", "LOCALIZATION", lesson=lesson, notes="Latest PT-BR course book."),
                artifact(run, f"lesson_{lesson}_deck_pt_br_pptx", pt_br_deck, "active", "LOCALIZATION", lesson=lesson, notes="Latest PT-BR presentation."),
                artifact(run, f"lesson_{lesson}_study_guide_es_pdf", es_book, "active", "LOCALIZATION", lesson=lesson, notes="Latest ES course book."),
                artifact(run, f"lesson_{lesson}_deck_es_pptx", es_deck, "active", "LOCALIZATION", lesson=lesson, notes="Latest ES presentation."),
                artifact(run, f"lesson_{lesson}_pipeline_qa", run / "process_review" / f"lesson_{lesson}_pipeline_qa.md", "supporting", "PROCESS_REVIEW", lesson=lesson),
            ]
        )

    return {
        "course_slug": course_slug,
        "run_folder": str(run.relative_to(ROOT)) if run.exists() else str(run),
        "manifest_version": 2,
        "artifacts": [asdict(item) for item in artifacts],
    }


def write_manifest(data: dict) -> tuple[Path, Path]:
    run = RUNS / data["course_slug"]
    out_json = run / "process_review" / "canonical_artifacts.json"
    out_md = run / "process_review" / "canonical_artifacts.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    out_md.write_text(render_markdown(data) + "\n", encoding="utf-8")
    return out_json, out_md


def render_markdown(data: dict) -> str:
    lines = [
        "# Canonical Artifacts",
        "",
        f"Course slug: `{data['course_slug']}`",
        f"Manifest version: {data['manifest_version']}",
        "",
        "| Key | Status | Stage | Path | Revision | Approval | QA | Notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in data["artifacts"]:
        lines.append(
            "| {key} | {status} | {stage} | `{path}` | {revision} | {approval} | {qa} | {notes} |".format(
                key=item["key"],
                status=item["status"],
                stage=item["stage"],
                path=item["path"],
                revision=item["revision"] or "",
                approval=f"`{item['approval_path']}`" if item["approval_path"] else "",
                qa=f"`{item['qa_path']}`" if item["qa_path"] else "",
                notes=item["notes"].replace("|", "/"),
            )
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Infer and write Prof Greg canonical artifact manifests.")
    parser.add_argument("course_slug", help="Run/course slug under runs/.")
    parser.add_argument("--write", action="store_true", help="Write canonical_artifacts.json and .md.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    parser.add_argument("--allow-missing", action="store_true", help="Return success even when future-stage artifacts are missing.")
    args = parser.parse_args()

    data = infer_manifest(args.course_slug)
    if args.write:
        write_manifest(data)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(data))
    missing = [
        item
        for item in data["artifacts"]
        if item["status"] == "missing" and item["key"] not in OPTIONAL_MISSING_KEYS
    ]
    return 0 if args.allow_missing else (1 if missing else 0)


if __name__ == "__main__":
    raise SystemExit(main())
