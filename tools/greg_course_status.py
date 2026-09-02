#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path

from greg_localized_deck_guard import LocalizedDeckIntegrityError, validate_localized_deck


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
VIDEO_SOURCE_MAX_BYTES = 20 * 1024 * 1024
VIDEO_LOCALES = {
    "en": ("deck", "deck_path"),
    "pt": ("pt_br_deck", "pt_br_deck_path"),
    "es": ("es_deck", "es_deck_path"),
}


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


def revision_candidate_path(run: Path, value: object) -> Path | None:
    """Resolve both run-relative and repository-relative revision candidates."""
    raw = str(value or "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    run_prefix = Path("runs") / run.name
    try:
        return run / candidate.relative_to(run_prefix)
    except ValueError:
        return run / candidate


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def video_state_value(saved: dict, snake_case: str, camel_case: str, default=None):
    """Read both the original UI schema and the AI Studios worker schema."""
    if snake_case in saved:
        return saved[snake_case]
    if camel_case in saved:
        return saved[camel_case]
    return default


def video_generation_status(run: Path, lesson: str, row: dict) -> dict[str, dict]:
    """Describe one independent video lane per approved presentation locale."""
    result: dict[str, dict] = {}
    for locale, (approval_field, path_field) in VIDEO_LOCALES.items():
        source_relative = str(row.get(path_field) or "")
        source_path = ROOT / source_relative if source_relative else None
        state_path = run / "video_generator" / f"lesson_{lesson}_{locale}.json"
        saved = load_json(state_path)
        lane = {
            "locale": locale,
            "status": "waiting_approved_presentation",
            "presentation_path": source_relative,
            "source_sha256": "",
            "project_url": "",
            "download_url": "",
            "attempts": 0,
        }
        if row.get(approval_field) != "approved" or not source_path or not source_path.is_file():
            result[locale] = lane
            continue
        source_stat = source_path.stat()
        lane["source_size_bytes"] = source_stat.st_size
        lane["source_mtime_ns"] = source_stat.st_mtime_ns
        if source_stat.st_size > VIDEO_SOURCE_MAX_BYTES:
            lane["status"] = "presentation_too_large"
            result[locale] = lane
            continue
        if saved:
            saved_source_path = video_state_value(saved, "presentation_path", "sourcePath", "")
            saved_source_size = video_state_value(saved, "source_size_bytes", "sourceSizeBytes")
            saved_source_mtime = video_state_value(saved, "source_mtime_ns", "sourceModifiedNs")
            saved_source_sha256 = str(video_state_value(saved, "source_sha256", "sourceSha256", "") or "")
            unchanged_metadata = (
                saved_source_path == source_relative
                and saved_source_size == source_stat.st_size
                and saved_source_mtime == source_stat.st_mtime_ns
                and bool(saved_source_sha256)
            )
            lane["source_sha256"] = saved_source_sha256 if unchanged_metadata else file_sha256(source_path)
        else:
            saved_source_sha256 = ""
            lane["source_sha256"] = file_sha256(source_path)
        if lane["source_sha256"] and saved_source_sha256 == lane["source_sha256"]:
            field_names = {
                "status": ("status", "status"),
                "project_url": ("project_url", "projectUrl"),
                "download_url": ("download_url", "downloadUrl"),
                "attempts": ("attempts", "attemptCount"),
                "updated_at": ("updated_at", "updatedAt"),
                "last_error": ("last_error", "errorSummary"),
            }
            for target, (snake_case, camel_case) in field_names.items():
                value = video_state_value(saved, snake_case, camel_case)
                if value is not None:
                    lane[target] = value
        elif saved:
            lane["status"] = "ready_new_revision"
            lane["previous_project_url"] = str(video_state_value(saved, "project_url", "projectUrl", "") or "")
            lane["previous_download_url"] = str(video_state_value(saved, "download_url", "downloadUrl", "") or "")
        else:
            lane["status"] = "ready"
        result[locale] = lane
    return result


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


def study_guide_quality_blockers(run: Path, lesson: str, artifact_path: Path | None = None) -> list[str]:
    revision_match = re.search(r"_r(\d+)\.pdf$", artifact_path.name) if artifact_path else None
    revision = revision_match.group(1) if revision_match else ""
    suffix = f"_r{revision}" if revision else ""
    draft = read_text(run / "lesson_draft" / f"lesson_{lesson}_draft{suffix}.md")
    references = read_text(run / "sources" / "student_references.md")
    content_qa = read_text(run / "lesson_draft" / f"lesson_{lesson}_content_qa{suffix}.md")
    layout_qa = read_text(run / "docx_pdf" / f"lesson_{lesson}_pdf_layout_qa{suffix}.md")
    source_qa = read_text(run / "sources" / f"lesson_{lesson}_source_reference_qa.md") or read_text(run / "sources" / "source_reference_qa.md")
    blockers: list[str] = []
    intro_area = draft.split("# Section 01", 1)[0]
    if re.search(r"\bthis study guide is written for\b|\bconstruction learners working in the united states\b", intro_area, flags=re.I):
        blockers.append("Introduction contains audience/operator boilerplate instead of course-facing orientation.")
    if re.search(r"\bCurrent student references will be added after research expansion\b|\bReferences?\s+pending\b|\bSource research pending\b", references, flags=re.I):
        blockers.append("References contain placeholder text instead of real student-facing sources.")
    if "Study guide content QA passed: no" in content_qa:
        blockers.append("Content QA report is failing.")
    if "PDF layout QA passed: no" in layout_qa:
        blockers.append("PDF layout QA report is failing.")
    if re.search(r"Source/reference QA passed:\s*no", source_qa, flags=re.I):
        blockers.append("Source/reference QA report is failing.")
    def revision_review_path(suffix_name: str) -> Path:
        archived = run / "review" / f"lesson_{lesson}_{suffix_name}{suffix}.md"
        return archived if archived.exists() else run / "review" / f"lesson_{lesson}_{suffix_name}.md"

    required_reviews = {
        "pedagogy": revision_review_path("pedagogy_review"),
        "citation": revision_review_path("citation_review"),
        "design": revision_review_path("design_qa"),
        "visual": revision_review_path("visual_qa"),
    }
    for label, path in required_reviews.items():
        text = read_text(path)
        if label == "visual":
            passed = bool(re.search(r"Visual plan QA passed:\s*yes", text, flags=re.I))
        else:
            passed = bool(re.search(r"(?im)^PASS\s*$", text))
        if not passed:
            blockers.append(f"Required {label} review is missing or has not passed.")
    return blockers


def read_status_field(status_text: str, label: str) -> str:
    prefix = f"{label}:"
    for line in status_text.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return ""


def report_passed(path: Path, label: str) -> bool | None:
    text = read_text(path)
    if not text:
        return None
    match = re.search(rf"{re.escape(label)}\s*:\s*(yes|no)", text, flags=re.I)
    if not match:
        return None
    return match.group(1).lower() == "yes"


def approved_artifact_count(lessons: list[dict], fields: tuple[str, ...]) -> int:
    return sum(1 for lesson in lessons for field in fields if lesson.get(field) == "approved")


def operating_progress(course_map_ready: bool, lessons: list[dict]) -> dict:
    """Return weighted progress based only on approved deliverables."""
    lesson_count = len(lessons)
    books = approved_artifact_count(lessons, ("study_guide",))
    decks = approved_artifact_count(lessons, ("deck",))
    translations = approved_artifact_count(
        lessons,
        ("pt_br_study_guide", "pt_br_deck", "es_study_guide", "es_deck"),
    )
    map_points = 25.0 if course_map_ready else 0.0
    book_points = 25.0 * books / lesson_count if lesson_count else 0.0
    deck_points = 25.0 * decks / lesson_count if lesson_count else 0.0
    translation_total = lesson_count * 4
    translation_points = 25.0 * translations / translation_total if translation_total else 0.0
    return {
        "percent": round(min(100.0, map_points + book_points + deck_points + translation_points), 3),
        "course_map": {"approved": bool(course_map_ready), "points": map_points},
        "course_books": {"approved": books, "total": lesson_count, "points": round(book_points, 3)},
        "presentations": {"approved": decks, "total": lesson_count, "points": round(deck_points, 3)},
        "translations": {"approved": translations, "total": translation_total, "points": round(translation_points, 3)},
    }


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
    course_map_passed = report_passed(run / "course_map" / "course_map_qa.md", "Course Map QA passed")
    if course_map_passed is False:
        stage = "COURSE_MAP_QA_BLOCKED"
        gate_status = "Course Map is blocked by automatic QA. Greg must revise the Course Map before lesson production."
        next_action = "re-run Course Map production; automatic QA must pass before lesson selection."
    course_source_qa_path = run / "sources" / "course_source_reference_qa.md"
    if not course_source_qa_path.exists():
        course_source_qa_path = run / "sources" / "source_reference_qa.md"
    source_reference_passed = report_passed(course_source_qa_path, "Source/reference QA passed")
    course_map_exists = (run / "course_map" / "course_map.md").exists() or (run / "course_map" / "course_map.json").exists()
    has_operator_approved_lesson = any(
        (run / "approval").glob("lesson_*_study_guide_approval.md")
    )
    course_map_ready = bool(
        course_map_passed is True
        and course_map_exists
        and (run / "sources" / "source_ledger.json").exists()
        and source_reference_passed is True
    )
    if course_map_passed is True and source_reference_passed is False and not has_operator_approved_lesson:
        stage = "SOURCE_QA_BLOCKED"
        gate_status = "Course Map source review requires an automatic correction before release."
        next_action = "re-run Course Map and source research; the operator file remains unavailable until QA passes."
    elif course_map_ready:
        stage = "LESSON_PRODUCTION"
        gate_status = "Course Map and source ledger are ready. Select lesson(s) for course book production."
        next_action = "select one, several, or all lessons and generate course books."
    elif course_map_exists and has_operator_approved_lesson:
        # Legacy courses may predate the current Course Map/source-QA records.
        # A subsequent explicit course-book approval proves that the operator
        # accepted the map used to produce it, so keep the map available.
        course_map_ready = True
        stage = "LESSON_PRODUCTION"
        gate_status = "Course Map remains available because an operator-approved course book exists."
        next_action = "select one, several, or all lessons and continue production."
    elif course_map_passed is True:
        stage = "SOURCE_LEDGER"
        gate_status = "Course Map is ready. Source research is next."
        next_action = "run source research before lesson production."

    lessons_summary = summarize_lessons(run, manifest)
    waiting_images = [item for item in lessons_summary if item.get("visual_status") == "waiting_images"]
    if waiting_images:
        stage = "WAITING_IMAGES"
        numbers = ", ".join(str(int(item["lesson"])) for item in waiting_images)
        gate_status = f"Waiting for operator-provided images for Lesson(s) {numbers}. No student PDF is released until visual QA passes."
        next_action = "download the image request, upload the requested images with attribution, and resume course book production."

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
        "lessons": lessons_summary,
        "course_map_ready": course_map_ready,
        "progress": operating_progress(course_map_ready, lessons_summary),
    }


def summarize_lessons(run: Path, manifest: dict) -> list[dict]:
    lessons: dict[str, dict] = {
        lesson: {
            "lesson": lesson,
            "title": title,
            "study_guide": "missing",
            "deck": "missing",
            "pt_br_study_guide": "missing",
            "pt_br_deck": "missing",
            "es_study_guide": "missing",
            "es_deck": "missing",
            "pipeline_qa": "missing",
            "visual_status": "not_planned",
        }
        for lesson, title in lesson_titles(run).items()
    }
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
                "pt_br_study_guide": "missing",
                "pt_br_deck": "missing",
                "es_study_guide": "missing",
                "es_deck": "missing",
                "pipeline_qa": "missing",
                "visual_status": "not_planned",
            },
        )
        item_path = str(item.get("path") or "")
        path = run / item_path
        exists = bool(item_path) and path.exists() and path.is_file()
        status = item.get("status", "missing")
        if key.endswith("_study_guide_pdf"):
            approval_exists = (run / "approval" / f"lesson_{str(lesson).zfill(2)}_study_guide_approval.md").exists()
            blockers = study_guide_quality_blockers(run, str(lesson).zfill(2), path) if exists else []
            # An explicit operator approval is the final decision for that artifact.
            # Do not retroactively block it when new automatic checks are introduced.
            if blockers and not approval_exists:
                row["study_guide"] = "blocked"
                row["study_guide_blocked_path"] = rel(path)
                row["study_guide_quality_blockers"] = blockers
            else:
                row["study_guide"] = "approved" if approval_exists else (status if exists else "missing")
                if exists:
                    row["study_guide_path"] = rel(path)
        elif key.endswith("_deck_pptx"):
            if row.get("study_guide") == "blocked":
                row["deck"] = "blocked"
                row["deck_blocked_path"] = rel(path) if exists and path.is_file() else ""
                row["deck_quality_blockers"] = ["Course book is blocked; presentation review is gated until the course book is regenerated and passes QA."]
            else:
                row["deck"] = status if exists else "missing"
                if exists:
                    row["deck_path"] = rel(path)
        elif key.endswith("_study_guide_pt_br_pdf"):
            row["pt_br_study_guide"] = "approved" if (run / "approval" / f"lesson_{str(lesson).zfill(2)}_pt_br_study_guide_approval.md").exists() else (status if exists else "missing")
            if exists:
                row["pt_br_study_guide_path"] = rel(path)
        elif key.endswith("_deck_pt_br_pptx"):
            if exists:
                try:
                    validate_localized_deck(run, f"lesson_{str(lesson).zfill(2)}", path)
                except LocalizedDeckIntegrityError as error:
                    row["pt_br_deck"] = "blocked"
                    row["pt_br_deck_quality_blockers"] = [str(error)]
                else:
                    row["pt_br_deck"] = "approved" if (run / "approval" / f"lesson_{str(lesson).zfill(2)}_pt_br_deck_approval.md").exists() else status
                    row["pt_br_deck_path"] = rel(path)
            else:
                row["pt_br_deck"] = "missing"
        elif key.endswith("_study_guide_es_pdf"):
            row["es_study_guide"] = "approved" if (run / "approval" / f"lesson_{str(lesson).zfill(2)}_es_study_guide_approval.md").exists() else (status if exists else "missing")
            if exists:
                row["es_study_guide_path"] = rel(path)
        elif key.endswith("_deck_es_pptx"):
            if exists:
                try:
                    validate_localized_deck(run, f"lesson_{str(lesson).zfill(2)}", path)
                except LocalizedDeckIntegrityError as error:
                    row["es_deck"] = "blocked"
                    row["es_deck_quality_blockers"] = [str(error)]
                else:
                    row["es_deck"] = "approved" if (run / "approval" / f"lesson_{str(lesson).zfill(2)}_es_deck_approval.md").exists() else status
                    row["es_deck_path"] = rel(path)
            else:
                row["es_deck"] = "missing"
        elif key.endswith("_pipeline_qa"):
            row["pipeline_qa"] = "present" if exists else "missing"
            row["pipeline_qa_path"] = rel(path)
    for lesson, row in lessons.items():
        request_json = run / "review" / f"lesson_{lesson}_image_requests.json"
        request_md = run / "review" / f"lesson_{lesson}_image_requests.md"
        visual_plan = run / "review" / f"lesson_{lesson}_visual_plan.json"
        visual_qa = run / "review" / f"lesson_{lesson}_visual_qa.md"
        approval_exists = (run / "approval" / f"lesson_{lesson}_study_guide_approval.md").exists()
        if request_json.exists() and not approval_exists:
            row["visual_status"] = "waiting_images"
            row["image_request_path"] = rel(request_md if request_md.exists() else request_json)
            row["image_requests"] = (load_json(request_json).get("requests") or [])
            row["study_guide"] = "waiting_images"
            row.pop("study_guide_path", None)
        elif visual_plan.exists() and report_passed(visual_qa, "Visual plan QA passed") is not False:
            # A visual plan is created only after the course-book Markdown has passed
            # content QA. It is not a standalone deliverable: the visual and the PDF
            # remain one connected production item until the book is rendered.
            row["visual_status"] = "included" if row.get("study_guide") in {"active", "approved"} else "content_ready"
        # A request is a first-class state. Keep the approved baseline
        # downloadable, but never make the operator guess whether the change
        # request was accepted by the system.
        for artifact_type, field in (
            ("study_guide", "study_guide"), ("deck", "deck"),
            ("pt_br_study_guide", "pt_br_study_guide"), ("pt_br_deck", "pt_br_deck"),
            ("es_study_guide", "es_study_guide"), ("es_deck", "es_deck"),
        ):
            state_path = run / "operator_feedback" / f"lesson_{lesson}_{artifact_type}_revision_state.json"
            state = load_json(state_path) if state_path.exists() else {}
            if state:
                candidate = revision_candidate_path(run, state.get("candidate_artifact"))
                state_requests = [item for item in (state.get("requests") or []) if isinstance(item, dict)]
                if not state_requests and str(state.get("note") or "").strip():
                    state_requests = [{"id": "1", "note": str(state.get("note"))}]
                public_state = {
                    "state": str(state.get("state") or ""),
                    "request_count": int(state.get("request_count") or len(state_requests)),
                    "requests": [
                        {"id": str(item.get("id") or ""), "note": str(item.get("note") or "")}
                        for item in state_requests
                    ],
                    "accepted_at": str(state.get("accepted_at") or ""),
                    "completed_at": str(state.get("completed_at") or ""),
                    "approved_at": str(state.get("approved_at") or ""),
                }
                if candidate and candidate.exists() and candidate.is_file():
                    public_state["candidate_artifact"] = rel(candidate)
                row[f"{field}_revision"] = public_state
            if state.get("state") == "revision_requested":
                row[field] = "revision_requested"
            elif state.get("state") == "ready_for_review":
                row[field] = "ready_for_review"
                if candidate and candidate.exists() and candidate.is_file():
                    row[f"{field}_path"] = rel(candidate)
            elif state.get("state") == "approved":
                row[field] = "approved"
                if candidate and candidate.exists() and candidate.is_file():
                    row[f"{field}_path"] = rel(candidate)
        row["videos"] = video_generation_status(run, lesson, row)
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
