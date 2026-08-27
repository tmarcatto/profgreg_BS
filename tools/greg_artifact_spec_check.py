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

DECK_LAYOUTS = {
    "cover",
    "intro_image_bullets",
    "image_bullets",
    "card_sequence",
    "comparison",
    "planned_actual",
    "row_list",
    "checklist_rows",
    "takeaway",
}
PDF_VISUAL_TYPES = {"card_row", "cpm_network", "source_to_wbs_matrix", "timeline", "process_flow", "relationship_map", "image"}
PATH_KEYS = {"run_folder", "source_markdown", "approved_baseline_artifact", "pptx", "pdf", "qa", "render_qa", "layout_qa", "rendered_dir"}


@dataclass
class Finding:
    status: str
    check: str
    note: str


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def rel_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def is_safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and not value.startswith(("~", "file://"))


def path_exists_from_root(value: Any) -> bool:
    return isinstance(value, str) and (ROOT / value).exists()


def collect_path_values(data: Any, parent_key: str = "") -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key in PATH_KEYS:
                found.append((key, value))
            found.extend(collect_path_values(value, key))
    elif isinstance(data, list):
        for item in data:
            found.extend(collect_path_values(item, parent_key))
    return found


def detect_kind(spec_path: Path, spec: dict[str, Any], explicit: str | None) -> str:
    if explicit:
        return explicit
    output = spec.get("output", {})
    if "pptx" in output or spec_path.name.endswith("_deck_spec.json"):
        return "deck"
    if "pdf" in output or spec_path.name.endswith("_study_guide_spec.json"):
        return "study_guide_pdf"
    return "unknown"


def required_root_checks(spec_path: Path, spec: dict[str, Any], kind: str) -> list[Finding]:
    findings: list[Finding] = []
    production_mode = str(spec.get("production_mode") or "revision")
    required = ["course_slug", "course_title", "lesson_number", "production_mode", "run_folder", "output"]
    if production_mode != "initial":
        required += ["revision", "approved_baseline_artifact"]
    if kind == "study_guide_pdf":
        required += ["source_markdown", "metadata"]
    if kind == "deck":
        required += ["slides", "assets"]
    missing = [field for field in required if field not in spec or spec.get(field) in ("", None, [], {})]
    if missing:
        findings.append(Finding("fail", "required_fields", f"Missing required fields: {missing}."))
    else:
        findings.append(Finding("pass", "required_fields", "Required root fields are present."))

    revision = str(spec.get("revision") or "")
    if production_mode == "initial" and not revision:
        findings.append(Finding("pass", "revision_format", "Initial production does not require a revision suffix."))
    elif re.fullmatch(r"r\d{2,}", revision):
        findings.append(Finding("pass", "revision_format", f"Revision `{revision}` is cache-safe."))
    else:
        findings.append(Finding("fail", "revision_format", f"Revision `{revision}` must use format rNN, such as r02."))

    if production_mode in {"initial", "revision"}:
        findings.append(Finding("pass", "production_mode", f"Production mode is `{production_mode}`."))
    else:
        findings.append(Finding("fail", "production_mode", f"Unsupported production mode `{production_mode}`."))

    return findings


def path_checks(spec: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    path_values = collect_path_values(spec)
    unsafe = [(key, value) for key, value in path_values if not is_safe_relative(value)]
    if unsafe:
        findings.append(Finding("fail", "relative_paths", f"Unsafe or absolute paths found: {unsafe}."))
    else:
        findings.append(Finding("pass", "relative_paths", "All declared spec paths are relative and workspace-safe."))

    run_folder = spec.get("run_folder")
    if path_exists_from_root(run_folder):
        findings.append(Finding("pass", "run_folder_exists", f"Run folder exists: {run_folder}."))
    else:
        findings.append(Finding("fail", "run_folder_exists", f"Run folder does not exist: {run_folder}."))

    production_mode = str(spec.get("production_mode") or "revision")
    baseline = spec.get("approved_baseline_artifact")
    if production_mode == "initial":
        findings.append(Finding("pass", "baseline_exists", "Initial production has no prior approved baseline artifact."))
    elif isinstance(run_folder, str) and isinstance(baseline, str) and (ROOT / run_folder / baseline).exists():
        findings.append(Finding("pass", "baseline_exists", "Approved baseline artifact exists."))
    else:
        findings.append(Finding("fail", "baseline_exists", f"Approved baseline artifact is missing: {baseline}."))

    return findings


def revision_output_checks(spec: dict[str, Any], kind: str) -> list[Finding]:
    findings: list[Finding] = []
    production_mode = str(spec.get("production_mode") or "revision")
    revision = str(spec.get("revision") or "")
    output = spec.get("output", {})
    primary_key = "pptx" if kind == "deck" else "pdf"
    primary = str(output.get(primary_key) or "")
    baseline = str(spec.get("approved_baseline_artifact") or "")
    if production_mode == "initial":
        if "_r" not in Path(primary).stem:
            findings.append(Finding("pass", "revisioned_primary_output", "Initial production uses canonical output naming."))
        else:
            findings.append(Finding("warn", "revisioned_primary_output", f"Initial production output `{primary}` is revisioned; confirm this is intentional."))
        findings.append(Finding("pass", "baseline_not_overwritten", "Initial production has no approved baseline to overwrite."))
        return findings
    if revision and revision in primary:
        findings.append(Finding("pass", "revisioned_primary_output", f"Primary output includes revision `{revision}`."))
    else:
        findings.append(Finding("fail", "revisioned_primary_output", f"Primary output `{primary}` must include revision `{revision}`."))
    if primary and primary != baseline:
        findings.append(Finding("pass", "baseline_not_overwritten", "Revision output does not overwrite approved baseline artifact."))
    else:
        findings.append(Finding("fail", "baseline_not_overwritten", "Spec would overwrite the approved baseline artifact."))
    return findings


def deck_checks(spec: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    slides = spec.get("slides") if isinstance(spec.get("slides"), list) else []
    if len(slides) == 10:
        findings.append(Finding("pass", "deck_slide_count", "Deck spec has 10 slides."))
    else:
        findings.append(Finding("fail", "deck_slide_count", f"Deck spec has {len(slides)} slides; expected 10."))

    unknown_layouts = sorted({str(slide.get("layout") or "") for slide in slides} - DECK_LAYOUTS)
    if unknown_layouts:
        findings.append(Finding("fail", "deck_layouts", f"Unknown deck layouts: {unknown_layouts}."))
    else:
        findings.append(Finding("pass", "deck_layouts", "All deck layouts are supported by the reusable renderer."))

    if slides and slides[0].get("layout") == "cover" and slides[0].get("topics"):
        findings.append(Finding("pass", "deck_cover_topics", "Cover slide includes main topics."))
    else:
        findings.append(Finding("fail", "deck_cover_topics", "Cover slide must include main topics."))

    image_slides = [index + 1 for index, slide in enumerate(slides) if slide.get("image")]
    image_layout_slides = [index + 1 for index, slide in enumerate(slides) if slide.get("layout") in {"intro_image_bullets", "image_bullets"}]
    consecutive = [(a, b) for a, b in zip(image_slides, image_slides[1:]) if b == a + 1]
    if consecutive:
        findings.append(Finding("fail", "deck_image_cadence", f"Image slides are consecutive: {consecutive}."))
    else:
        findings.append(Finding("pass", "deck_image_cadence", "Image slides are not consecutive."))

    if image_layout_slides and all(isinstance(slides[index - 1].get("image"), dict) for index in image_layout_slides):
        findings.append(Finding("pass", "deck_required_teaching_image", f"Deck includes half-slide teaching image layout(s): {image_layout_slides}."))
    else:
        findings.append(Finding("fail", "deck_required_teaching_image", "Deck needs at least one image-plus-teaching-bullets slide with a declared image asset."))

    body_layouts = [str(slide.get("layout") or "") for slide in slides[1:-1]]
    if len(set(body_layouts)) >= 6:
        findings.append(Finding("pass", "deck_layout_diversity", f"Deck uses {len(set(body_layouts))} distinct body layouts."))
    else:
        findings.append(Finding("fail", "deck_layout_diversity", "Deck needs at least six distinct body layouts across slides 2-9."))
    if any(left == right for left, right in zip(body_layouts, body_layouts[1:])):
        findings.append(Finding("fail", "deck_adjacent_layout_repeat", "Adjacent body slides repeat the same layout."))
    else:
        findings.append(Finding("pass", "deck_adjacent_layout_repeat", "No adjacent body slides repeat a layout."))

    missing_image_fields = []
    for index, slide in enumerate(slides, start=1):
        image = slide.get("image")
        if isinstance(image, dict):
            for field in ("path", "alt"):
                if not image.get(field):
                    missing_image_fields.append((index, field))
            if image.get("caption") or image.get("subtitle"):
                missing_image_fields.append((index, "no visible image caption/subtitle"))
    if missing_image_fields:
        findings.append(Finding("fail", "deck_image_fields", f"Image field issues: {missing_image_fields}."))
    else:
        findings.append(Finding("pass", "deck_image_fields", "Deck image declarations have path/alt and no captions."))

    qa_checks = " ".join(str(item) for item in spec.get("qa_checks", []))
    for needle, label in [("MECE", "qa_mece"), ("no automatic last-item highlight", "qa_no_last_item_highlight"), ("residential", "qa_residential")]:
        if needle.lower() in qa_checks.lower():
            findings.append(Finding("pass", label, f"QA checks mention `{needle}`."))
        else:
            findings.append(Finding("fail", label, f"QA checks must mention `{needle}`."))
    return findings


def pdf_checks(spec: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    production_mode = str(spec.get("production_mode") or "revision")
    source = spec.get("source_markdown")
    if path_exists_from_root(source):
        findings.append(Finding("pass", "pdf_source_markdown_exists", "Source markdown exists."))
    else:
        findings.append(Finding("fail", "pdf_source_markdown_exists", f"Source markdown is missing: {source}."))

    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    required_metadata = ["course_title", "lesson_number", "lesson_short_title", "level_label", "icon"]
    missing_metadata = [field for field in required_metadata if not metadata.get(field)]
    if missing_metadata:
        findings.append(Finding("fail", "pdf_metadata", f"Missing metadata fields: {missing_metadata}."))
    else:
        findings.append(Finding("pass", "pdf_metadata", "Required PDF metadata is present."))

    icon = metadata.get("icon")
    if path_exists_from_root(icon):
        findings.append(Finding("pass", "pdf_icon_exists", "BuildStak icon exists."))
    else:
        findings.append(Finding("fail", "pdf_icon_exists", f"BuildStak icon is missing: {icon}."))

    visuals = spec.get("visuals") if isinstance(spec.get("visuals"), list) else []
    unknown_visuals = sorted({str(visual.get("type") or "") for visual in visuals} - PDF_VISUAL_TYPES)
    if unknown_visuals:
        findings.append(Finding("fail", "pdf_visual_types", f"Unknown PDF visual types: {unknown_visuals}."))
    else:
        findings.append(Finding("pass", "pdf_visual_types", "All PDF visuals use supported deterministic renderer types."))

    missing_visual_fields = []
    for index, visual in enumerate(visuals, start=1):
        for field in ("after_heading", "title", "caption"):
            if not visual.get(field):
                missing_visual_fields.append((index, field))
        if visual.get("type") == "card_row" and not visual.get("cards"):
            missing_visual_fields.append((index, "cards"))
        if visual.get("type") == "source_to_wbs_matrix":
            for field in ("left_header", "right_header", "rows"):
                if not visual.get(field):
                    missing_visual_fields.append((index, field))
        if visual.get("type") == "cpm_network" and not visual.get("paths"):
            missing_visual_fields.append((index, "paths"))
        if visual.get("type") in {"process_flow", "relationship_map"} and not visual.get("nodes"):
            missing_visual_fields.append((index, "nodes"))
    if missing_visual_fields:
        findings.append(Finding("fail", "pdf_visual_fields", f"Visual field issues: {missing_visual_fields}."))
    else:
        findings.append(Finding("pass", "pdf_visual_fields", "PDF visual declarations include placement, title, caption, and data."))

    qa_notes = " ".join(str(item) for item in spec.get("qa_notes", []))
    if production_mode == "initial" and ("initial production" in qa_notes.lower() or "for approval" in qa_notes.lower()):
        findings.append(Finding("pass", "pdf_technical_revision_note", "Spec states that this is initial production for approval."))
    elif "approved student-facing artifact remains" in qa_notes.lower():
        findings.append(Finding("pass", "pdf_technical_revision_note", "Spec states that the approved artifact remains unchanged."))
    else:
        findings.append(Finding("fail", "pdf_technical_revision_note", "Spec must state whether this is initial production or a technical revision that does not replace the approved artifact."))
    return findings


def run_checks(spec_path: Path, kind_override: str | None = None) -> dict[str, Any]:
    findings: list[Finding] = []
    spec = read_json(spec_path)
    kind = detect_kind(spec_path, spec, kind_override)

    if spec_path.exists():
        findings.append(Finding("pass", "spec_exists", f"Spec exists: {rel_path(spec_path)}."))
    else:
        findings.append(Finding("fail", "spec_exists", f"Spec is missing: {spec_path}."))

    if kind in {"deck", "study_guide_pdf"}:
        findings.append(Finding("pass", "spec_kind", f"Spec kind detected as `{kind}`."))
    else:
        findings.append(Finding("fail", "spec_kind", "Could not detect spec kind."))

    findings.extend(required_root_checks(spec_path, spec, kind))
    findings.extend(path_checks(spec))
    if kind in {"deck", "study_guide_pdf"}:
        findings.extend(revision_output_checks(spec, kind))
    if kind == "deck":
        findings.extend(deck_checks(spec))
    elif kind == "study_guide_pdf":
        findings.extend(pdf_checks(spec))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "spec": str(spec_path),
        "kind": kind,
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"Artifact spec QA passed: {'yes' if data['passed'] else 'no'}",
        f"Kind: {data['kind']}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        f"Spec: {data['spec']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Prof Greg artifact renderer specs before rendering.")
    parser.add_argument("spec", help="Path to deck or study-guide PDF spec JSON.")
    parser.add_argument("--kind", choices=["deck", "study_guide_pdf"], help="Override detected spec kind.")
    parser.add_argument("--output", help="Optional path to write the Markdown report.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    data = run_checks(Path(args.spec).expanduser().resolve(), args.kind)
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
