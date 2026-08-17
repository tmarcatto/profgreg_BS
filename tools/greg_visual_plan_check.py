#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class Finding:
    status: str
    check: str
    note: str


GENERATED_TYPES = {"generated-conceptual-image"}
SOURCE_TYPES = {"trusted-source-image", "real-source-image"}
DIAGRAM_TYPES = {"deterministic-diagram", "chart", "process-flow", "structured-visual"}
DIAGRAM_MECHANISMS = {"process-flow", "relationship-map", "comparison-matrix", "card-sequence"}
BRAND_TYPES = {"brand-mark", "logo"}
ALLOWED_HIGHLIGHT_REASONS = {
    "exception",
    "warning",
    "decision-point",
    "risk-threshold",
    "contrast",
    "lesson-emphasis",
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return " ".join(tokens)


def visual_label(visual: dict[str, Any], index: int) -> str:
    return str(visual.get("visual_id") or visual.get("id") or f"visual_{index + 1}")


def visual_type(visual: dict[str, Any]) -> str:
    return str(visual.get("visual_type") or visual.get("type") or "").strip()


def is_generated(visual: dict[str, Any]) -> bool:
    return visual_type(visual) in GENERATED_TYPES or visual.get("generated") is True


def is_brand(visual: dict[str, Any]) -> bool:
    return visual_type(visual) in BRAND_TYPES or visual.get("role") == "brand"


def placement_number(visual: dict[str, Any], fallback: int) -> int:
    for key in ("slide", "page", "order"):
        value = visual.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    placement = str(visual.get("placement") or "")
    match = re.search(r"\b(\d+)\b", placement)
    return int(match.group(1)) if match else fallback + 1


def run_checks(plan_path: Path) -> dict[str, Any]:
    findings: list[Finding] = []
    plan = load_json(plan_path)
    visuals = plan.get("visuals") or []
    artifact_type = str(plan.get("artifact_type") or "").lower()

    if plan_path.exists():
        findings.append(Finding("pass", "visual_plan_exists", "Visual plan exists."))
    else:
        findings.append(Finding("fail", "visual_plan_exists", "Visual plan is missing."))

    if visuals:
        findings.append(Finding("pass", "visuals_present", f"Visual plan has {len(visuals)} visual items."))
    else:
        findings.append(Finding("fail", "visuals_present", "Visual plan has no visual items."))

    required_missing = []
    missing_purpose = []
    missing_learning_claim = []
    source_gaps = []
    generated_over_half = []
    generated_unknown_size = []
    generated_deck_captions = []
    highlighted_without_reason = []
    invalid_highlight_reasons = []
    text_below_diagram = []
    source_needed = []
    generated_for_real_example = []
    missing_residential_context = []
    people_representation_missing = []
    learning_claims: dict[str, list[str]] = {}
    generated_positions: list[tuple[int, str]] = []
    missing_diagram_decisions = []
    unsuitable_diagram_decisions = []
    diagram_mechanisms: dict[str, list[str]] = {}

    for index, visual in enumerate(visuals):
        label = visual_label(visual, index)
        kind = visual_type(visual)
        if not kind:
            required_missing.append((label, "visual_type"))
        if not visual.get("placement") and visual.get("slide") is None and visual.get("page") is None:
            required_missing.append((label, "placement"))

        if is_brand(visual):
            continue

        purpose = str(visual.get("purpose") or "").strip()
        if len(purpose.split()) < 4:
            missing_purpose.append(label)

        learning_claim = str(visual.get("learning_claim") or visual.get("learning_line") or "").strip()
        if len(learning_claim.split()) < 5:
            missing_learning_claim.append(label)
        else:
            learning_claims.setdefault(normalize(learning_claim), []).append(label)

        source_status = str(visual.get("source_status") or "").strip()
        if kind in SOURCE_TYPES and not (visual.get("source_id") or visual.get("source_url") or visual.get("attribution")):
            source_gaps.append(label)
        if source_status in {"source-needed", "unverified", "missing"}:
            source_needed.append(label)

        context_focus = normalize(str(visual.get("context_focus") or visual.get("setting") or visual.get("scenario_context") or ""))
        if "residential" not in context_focus and not visual.get("commercial_contrast") is True:
            missing_residential_context.append(label)

        depicts_people = visual.get("depicts_people")
        people_text = normalize(
            " ".join(
                [
                    str(visual.get("workforce_representation") or ""),
                    str(visual.get("prompt") or ""),
                    str(visual.get("alt") or ""),
                    purpose,
                ]
            )
        )
        if depicts_people is True and not (
            "immigrant" in people_text
            and ("american born" in people_text or "american" in people_text)
        ):
            people_representation_missing.append(label)

        if is_generated(visual):
            generated_positions.append((placement_number(visual, index), label))
            area = visual.get("max_area_percent", visual.get("area_percent"))
            if isinstance(area, (int, float)) and area > 50:
                generated_over_half.append((label, area))
            elif area is None:
                generated_unknown_size.append(label)
            if artifact_type == "deck" and (visual.get("caption") or visual.get("visible_subtitle") or visual.get("subtitle")):
                generated_deck_captions.append(label)
            if visual.get("core_message_depends_on_real_example") is True and source_status != "visual-curation-required":
                generated_for_real_example.append(label)

        if visual.get("highlighted") is True:
            reason = str(visual.get("highlight_reason") or "").strip()
            if not reason:
                highlighted_without_reason.append(label)
            elif reason not in ALLOWED_HIGHLIGHT_REASONS:
                invalid_highlight_reasons.append((label, reason))

        if kind in DIAGRAM_TYPES and visual.get("internal_text") is True:
            position = str(visual.get("internal_text_position") or "").strip().lower()
            if position in {"below", "bottom", "caption-area"}:
                text_below_diagram.append(label)

        if kind in DIAGRAM_TYPES:
            mechanism = str(visual.get("diagram_type") or "").strip().lower()
            rationale = str(visual.get("diagram_rationale") or "").strip()
            if mechanism not in DIAGRAM_MECHANISMS or len(rationale.split()) < 6:
                missing_diagram_decisions.append(label)
            else:
                diagram_mechanisms.setdefault(mechanism, []).append(label)
                claim_text = normalize(" ".join([purpose, learning_claim]))
                if mechanism == "comparison-matrix" and re.search(r"\b(sequence|lifecycle|workflow|process|handoff|phase)\b", claim_text):
                    unsuitable_diagram_decisions.append((label, mechanism, "sequential learning claim"))

    if required_missing:
        findings.append(Finding("fail", "required_visual_fields", f"Missing required visual fields: {required_missing}."))
    else:
        findings.append(Finding("pass", "required_visual_fields", "Each visual has a type and placement."))

    if missing_purpose:
        findings.append(Finding("fail", "visual_purpose", f"Visuals missing a clear teaching purpose: {missing_purpose}."))
    else:
        findings.append(Finding("pass", "visual_purpose", "Each non-brand visual has a clear teaching purpose."))

    if missing_learning_claim:
        findings.append(Finding("fail", "visual_learning_claim", f"Visuals missing a distinct learning claim: {missing_learning_claim}."))
    else:
        findings.append(Finding("pass", "visual_learning_claim", "Each non-brand visual has a learning claim."))

    repeated_claims = {claim: labels for claim, labels in learning_claims.items() if len(labels) > 1}
    if repeated_claims:
        findings.append(Finding("fail", "visual_mece", f"Repeated visual learning claims: {repeated_claims}."))
    else:
        findings.append(Finding("pass", "visual_mece", "Visual learning claims are distinct."))

    generated_positions.sort()
    consecutive_generated = [(a_label, b_label) for (a_pos, a_label), (b_pos, b_label) in zip(generated_positions, generated_positions[1:]) if b_pos == a_pos + 1]
    if consecutive_generated:
        findings.append(Finding("fail", "generated_image_cadence", f"Generated images appear consecutively: {consecutive_generated}."))
    else:
        findings.append(Finding("pass", "generated_image_cadence", "Generated images are not consecutive."))

    if generated_over_half:
        findings.append(Finding("fail", "generated_image_size", f"Generated images exceed half the slide/page area: {generated_over_half}."))
    elif generated_unknown_size:
        findings.append(Finding("warn", "generated_image_size", f"Generated images lack max_area_percent: {generated_unknown_size}."))
    else:
        findings.append(Finding("pass", "generated_image_size", "Generated images declare acceptable size limits."))

    if generated_deck_captions:
        findings.append(Finding("fail", "generated_deck_captions", f"Generated deck images have captions/subtitles: {generated_deck_captions}."))
    else:
        findings.append(Finding("pass", "generated_deck_captions", "Generated deck images have no captions/subtitles."))

    if source_gaps or source_needed:
        findings.append(Finding("fail", "visual_source_status", f"Visual source gaps: source attribution missing {source_gaps}; source-needed {source_needed}."))
    else:
        findings.append(Finding("pass", "visual_source_status", "Visual source status is production-ready."))

    if missing_residential_context:
        findings.append(Finding("fail", "residential_context", f"Visuals missing residential-construction context: {missing_residential_context}."))
    else:
        findings.append(Finding("pass", "residential_context", "Visuals preserve residential-construction-first context or explicit contrast."))

    if people_representation_missing:
        findings.append(Finding("fail", "workforce_representation", f"People-centered visuals do not document respectful American-born and immigrant workforce representation: {people_representation_missing}."))
    else:
        findings.append(Finding("pass", "workforce_representation", "People-centered visuals document respectful workforce representation when applicable."))

    if generated_for_real_example:
        findings.append(Finding("fail", "real_example_priority", f"Generated images used where real examples are core and curation was not requested: {generated_for_real_example}."))
    else:
        findings.append(Finding("pass", "real_example_priority", "Generated images are not replacing required real examples."))

    if highlighted_without_reason or invalid_highlight_reasons:
        findings.append(Finding("fail", "highlight_reason", f"Highlight issues: missing {highlighted_without_reason}; invalid {invalid_highlight_reasons}."))
    else:
        findings.append(Finding("pass", "highlight_reason", "Highlighted visuals have valid student-facing reasons."))

    if text_below_diagram:
        findings.append(Finding("fail", "diagram_internal_text_position", f"Diagram internal text is placed below the visual: {text_below_diagram}."))
    else:
        findings.append(Finding("pass", "diagram_internal_text_position", "Diagram internal text is not placed in the caption area."))

    if missing_diagram_decisions:
        findings.append(Finding("fail", "diagram_mechanism_decision", f"Deterministic diagrams lack an approved mechanism or pedagogical rationale: {missing_diagram_decisions}."))
    else:
        findings.append(Finding("pass", "diagram_mechanism_decision", "Each deterministic diagram declares a mechanism and pedagogical rationale."))

    if unsuitable_diagram_decisions:
        findings.append(Finding("fail", "diagram_mechanism_fit", f"Diagram mechanisms do not fit their learning jobs: {unsuitable_diagram_decisions}."))
    else:
        findings.append(Finding("pass", "diagram_mechanism_fit", "Diagram mechanisms fit their stated learning jobs."))

    diagram_count = sum(len(labels) for labels in diagram_mechanisms.values())
    if diagram_count >= 3 and len(diagram_mechanisms) == 1:
        findings.append(Finding("fail", "diagram_mechanism_variety", f"All {diagram_count} diagrams use {next(iter(diagram_mechanisms))}; re-evaluate the mechanism for each learning job."))
    else:
        findings.append(Finding("pass", "diagram_mechanism_variety", "The visual plan does not mechanically repeat one diagram mechanism."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "visual_plan": str(plan_path),
        "artifact_type": artifact_type or "unknown",
        "visual_count": len(visuals),
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"Visual plan QA passed: {'yes' if data['passed'] else 'no'}",
        f"Artifact type: {data['artifact_type']}",
        f"Visuals: {data['visual_count']}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        f"Visual plan: {data['visual_plan']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Prof Greg visual plans before rendering.")
    parser.add_argument("visual_plan", help="Path to visual_plan.json.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    data = run_checks(Path(args.visual_plan).expanduser().resolve())
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(data))
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
