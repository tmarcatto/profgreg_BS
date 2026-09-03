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
DIAGRAM_MECHANISMS = {
    "process-flow", "relationship-map", "comparison-matrix", "card-sequence", "cost-stack",
    "schedule-bar-chart", "activity-network", "planned-actual", "paired-record-rows",
    "verification-checklist",
}
DECK_TEACHING_STRATEGIES = {
    "activate-prior-knowledge", "anchor-with-scenario", "worked-example", "compare-and-contrast",
    "trace-a-process", "inspect-evidence", "diagnose-and-decide", "synthesize-and-recall",
}
DECK_VISUAL_MEDIA = {"native-diagram", "trusted-source-image", "generated-conceptual-image"}
IMAGE_NEEDS = {"required", "helpful", "not-needed"}
ASSET_STRATEGIES = {"native-diagram", "reuse-reference", "search-online", "generate", "operator-request"}
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


ALIGNMENT_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "with", "from", "by",
    "shows", "show", "diagram", "visual", "project", "residential", "construction", "step", "steps",
}


def expected_diagram_mechanism(text: str, numbered_items: int = 0) -> str | None:
    normalized = normalize(text)
    if re.search(r"\b(gantt|schedule bar|time scaled|planned timing|overlap|status by period)\b", normalized):
        return "schedule-bar-chart"
    if re.search(r"\b(predecessor|successor|parallel path|critical path|controlling path|network logic)\b", normalized):
        return "activity-network"
    if re.search(r"\b(cumulative|additive|cost stack|price layers|allowance layers|sum to|builds to a total)\b", normalized):
        return "cost-stack"
    if numbered_items >= 2 or re.search(r"\b(step|steps|sequence|order|workflow|process|handoff|phase|first|next|then|finally)\b", normalized):
        return "process-flow"
    if re.search(r"\b(planned versus actual|planned vs actual|plan actual|variance|drift|baseline gap)\b", normalized):
        return "planned-actual"
    if re.search(r"\b(record field|record fields|paired record|prompt to field|document mapping)\b", normalized):
        return "paired-record-rows"
    if re.search(r"\b(field verification|verification checklist|verify before|inspection checklist)\b", normalized):
        return "verification-checklist"
    if re.search(r"\b(compare|comparison|versus|difference|differences|alternative|alternatives|same attributes)\b", normalized):
        return "comparison-matrix"
    if re.search(r"\b(role|roles|stakeholder|stakeholders|relationship|relationships|influence|responsibility map)\b", normalized):
        return "relationship-map"
    return None


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
    diagram_capacity_violations = []
    cost_stack_total_layers = []
    visual_decision_evidence_gaps = []
    forbidden_generated_real_examples = []
    diagram_mechanisms: dict[str, list[str]] = {}
    deck_decision_protocol_gaps = []
    diagram_explanation_gaps = []
    comparison_matrix_structure_gaps = []
    image_need_gaps = []
    asset_strategy_gaps = []
    operator_request_box_gaps = []
    unresolved_online_searches = []

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
        asset_strategy = str(visual.get("asset_strategy") or "").strip()
        image_need = str(visual.get("image_need") or "").strip()
        image_need_reason = str(visual.get("image_need_reason") or "").strip()
        asset_strategy_reason = str(visual.get("asset_strategy_reason") or "").strip()
        if image_need not in IMAGE_NEEDS or len(image_need_reason.split()) < 5:
            image_need_gaps.append(label)
        expected_asset_strategies = {
            "deterministic-diagram": {"native-diagram"},
            "chart": {"native-diagram"},
            "process-flow": {"native-diagram"},
            "structured-visual": {"native-diagram"},
            "generated-conceptual-image": {"generate"},
            "trusted-source-image": {"reuse-reference", "search-online", "operator-request"},
            "real-source-image": {"reuse-reference", "search-online", "operator-request"},
        }.get(kind, ASSET_STRATEGIES)
        if asset_strategy not in expected_asset_strategies or len(asset_strategy_reason.split()) < 5:
            asset_strategy_gaps.append(label)
        if kind in SOURCE_TYPES and asset_strategy != "operator-request" and not (visual.get("source_id") or visual.get("source_url") or visual.get("attribution")):
            source_gaps.append(label)
        if source_status in {"source-needed", "unverified", "missing"} and asset_strategy != "operator-request":
            source_needed.append(label)
        if asset_strategy == "search-online" and not (visual.get("source_url") and visual.get("attribution")):
            unresolved_online_searches.append(label)
        if asset_strategy == "operator-request":
            request_box = visual.get("request_box") or {}
            if (
                not isinstance(request_box, dict)
                or len(str(request_box.get("image_description") or "").split()) < 5
                or len(str(request_box.get("pedagogical_reason") or "").split()) < 5
                or len(str(request_box.get("search_phrase") or "").split()) < 3
                or source_status not in {"source-needed", "visual-curation-required"}
            ):
                operator_request_box_gaps.append(label)

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
            if visual.get("real_example_importance") == "required" or visual.get("generation_suitability") == "unsafe":
                forbidden_generated_real_examples.append(label)

        if (
            visual.get("pedagogical_strategy") not in {"inspect-real-example", "explain-with-diagram", "orient-with-conceptual-image"}
            or visual.get("real_example_importance") not in {"required", "preferred", "not-needed"}
            or visual.get("generation_suitability") not in {"safe", "unsafe"}
            or not (visual.get("evidence_considered") or [])
            or not (visual.get("alternatives_considered") or [])
            or len(str(visual.get("selection_reason") or "").split()) < 6
        ):
            visual_decision_evidence_gaps.append(label)

        if artifact_type == "deck":
            candidates = visual.get("visual_candidates")
            candidate_media = [
                str(candidate.get("medium") or "")
                for candidate in candidates or []
                if isinstance(candidate, dict)
            ]
            selected_media = [
                str(candidate.get("medium") or "")
                for candidate in candidates or []
                if isinstance(candidate, dict) and candidate.get("decision") == "selected"
            ]
            medium = str(visual.get("visual_medium") or "")
            expected_type = {
                "native-diagram": "deterministic-diagram",
                "trusted-source-image": "trusted-source-image",
                "generated-conceptual-image": "generated-conceptual-image",
            }.get(medium)
            if (
                visual.get("teaching_strategy") not in DECK_TEACHING_STRATEGIES
                or set(candidate_media) != DECK_VISUAL_MEDIA
                or len(candidate_media) != len(DECK_VISUAL_MEDIA)
                or selected_media != [medium]
                or expected_type != kind
                or any(len(str(candidate.get("reason") or "").split()) < 4 for candidate in candidates or [] if isinstance(candidate, dict))
                or len(str(visual.get("text_role") or "").split()) < 4
            ):
                deck_decision_protocol_gaps.append(label)

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
                claim_text = normalize(" ".join([
                    purpose,
                    learning_claim,
                    str(visual.get("diagram_title") or ""),
                ]))
                nodes = visual.get("diagram_nodes") or []
                numbered_nodes = sum(
                    bool(re.match(r"^\s*\d+[.)]\s+", str(node.get("title") or "")))
                    for node in nodes
                )
                rows = visual.get("diagram_rows") or []
                expected_mechanism = expected_diagram_mechanism(claim_text, numbered_nodes)
                if expected_mechanism and mechanism != expected_mechanism:
                    unsuitable_diagram_decisions.append((label, mechanism, f"content logic requires {expected_mechanism}"))
                visible_text = " ".join(
                    [
                        f"{node.get('title') or ''} {node.get('detail') or ''}"
                        for node in nodes
                    ]
                    + [
                        " ".join(str(cell) for cell in (row.get("cells") or []))
                        or f"{row.get('left') or ''} {row.get('right') or ''}"
                        for row in rows
                    ]
                )
                claim_tokens = set(normalize(" ".join([learning_claim, str(visual.get("diagram_title") or "")])).split()) - ALIGNMENT_STOPWORDS
                visible_tokens = set(normalize(visible_text).split()) - ALIGNMENT_STOPWORDS
                if visible_tokens and claim_tokens and not (claim_tokens & visible_tokens):
                    diagram_explanation_gaps.append(label)
                if artifact_type != "study-guide":
                    continue
                if mechanism == "process-flow":
                    if not 2 <= len(nodes) <= 6:
                        diagram_capacity_violations.append((label, "process-flow requires 2-6 visible nodes"))
                    for node in nodes:
                        if len(str(node.get("title") or "")) > 30 or len(str(node.get("detail") or "")) > 36:
                            diagram_capacity_violations.append((label, "process-flow title/detail exceeds 30/36 characters"))
                            break
                elif mechanism == "relationship-map" and not 2 <= len(nodes) <= 6:
                    diagram_capacity_violations.append((label, "relationship-map requires 2-6 visible nodes"))
                elif mechanism == "comparison-matrix":
                    columns = [str(column).strip() for column in (visual.get("diagram_columns") or [])]
                    if not 3 <= len(columns) <= 4:
                        comparison_matrix_structure_gaps.append((label, "requires one variable column and 2-3 entity columns"))
                    if not 2 <= len(rows) <= 5:
                        diagram_capacity_violations.append((label, "comparison-matrix requires 2-5 visible rows"))
                    entity_tokens = list(dict.fromkeys(normalize(column).split()[0] for column in columns[1:] if normalize(column)))
                    for row in rows:
                        cells = [str(cell) for cell in (row.get("cells") or [])]
                        if len(cells) != len(columns):
                            comparison_matrix_structure_gaps.append((label, "every row requires one cell per visible column"))
                            break
                        if any(len(cell) > (45 if index == 0 else 90) for index, cell in enumerate(cells)):
                            diagram_capacity_violations.append((label, "comparison-matrix criterion/entity cell exceeds 45/90 characters"))
                            break
                        for cell in cells[1:]:
                            mentioned_entities = sum(bool(re.search(rf"\b{re.escape(token)}\b", normalize(cell))) for token in entity_tokens)
                            if mentioned_entities >= 2:
                                comparison_matrix_structure_gaps.append((label, "multiple compared entities are packed into one narrative cell"))
                                break
                elif mechanism in {"card-sequence", "cost-stack"} and not 2 <= len(nodes) <= 8:
                    diagram_capacity_violations.append((label, f"{mechanism} requires 2-8 visible cards"))
                elif mechanism == "schedule-bar-chart":
                    schedule_rows = visual.get("schedule_rows") or []
                    if not 3 <= len(schedule_rows) <= 8:
                        diagram_capacity_violations.append((label, "schedule-bar-chart requires 3-8 visible rows"))
                    for row in schedule_rows:
                        if not str(row.get("activity") or "").strip() or not isinstance(row.get("start"), int) or not isinstance(row.get("duration"), int) or row.get("start", -1) < 0 or row.get("duration", 0) <= 0:
                            diagram_capacity_violations.append((label, "schedule-bar-chart rows require activity, nonnegative integer start, and positive integer duration"))
                            break
                elif mechanism == "activity-network":
                    network_paths = visual.get("network_paths") or []
                    if not 1 <= len(network_paths) <= 2 or any(not 2 <= len(path.get("activities") or []) <= 4 for path in network_paths):
                        diagram_capacity_violations.append((label, "activity-network requires 1-2 visible paths with 2-4 activities each"))
                if mechanism == "cost-stack":
                    if any(re.search(r"\b(proposal price|final total|total price)\b", str(node.get("title") or ""), re.I) for node in nodes):
                        cost_stack_total_layers.append(label)
                    if not str(visual.get("diagram_total") or "").strip():
                        cost_stack_total_layers.append(label)

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

    if image_need_gaps:
        findings.append(Finding("fail", "image_need_decision", f"Visuals do not state whether an image improves learning and why: {image_need_gaps}."))
    else:
        findings.append(Finding("pass", "image_need_decision", "Every visual records an explicit image-need decision and pedagogical reason."))

    if asset_strategy_gaps:
        findings.append(Finding("fail", "asset_acquisition_strategy", f"Visuals lack a compatible, justified acquisition strategy: {asset_strategy_gaps}."))
    else:
        findings.append(Finding("pass", "asset_acquisition_strategy", "Every visual selects a compatible asset-acquisition route."))

    if unresolved_online_searches:
        findings.append(Finding("fail", "online_image_resolution", f"Online searches have no verified asset and attribution: {unresolved_online_searches}."))
    else:
        findings.append(Finding("pass", "online_image_resolution", "Every online-search selection resolves to a verified attributable asset."))

    if operator_request_box_gaps:
        findings.append(Finding("fail", "operator_request_box", f"Operator image requests lack a complete red-box payload: {operator_request_box_gaps}."))
    else:
        findings.append(Finding("pass", "operator_request_box", "Every operator request contains an image description, pedagogical reason, and search phrase."))

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

    if visual_decision_evidence_gaps:
        findings.append(Finding("fail", "visual_decision_evidence", f"Visuals lack an auditable pedagogical/source decision: {visual_decision_evidence_gaps}."))
    else:
        findings.append(Finding("pass", "visual_decision_evidence", "Every visual records strategy, real-example importance, evidence, alternatives, and selection reason."))

    if deck_decision_protocol_gaps:
        findings.append(Finding("fail", "deck_visual_decision_protocol", f"Deck visuals did not choose a teaching strategy, compare all three media, select one matching medium, and define the text role: {deck_decision_protocol_gaps}."))
    else:
        findings.append(Finding("pass", "deck_visual_decision_protocol", "Every deck visual chooses pedagogy first, compares all three media, and defines how text supports the selected visual."))

    if forbidden_generated_real_examples:
        findings.append(Finding("fail", "generated_real_example_forbidden", f"Generated imagery was selected where a real example is required or generation is unsafe: {forbidden_generated_real_examples}."))
    else:
        findings.append(Finding("pass", "generated_real_example_forbidden", "No generated image substitutes for a required real example."))

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

    if diagram_explanation_gaps:
        findings.append(Finding("fail", "diagram_explanation_alignment", f"Diagram titles/captions share no specific learner-facing terms with their visible labels: {diagram_explanation_gaps}."))
    else:
        findings.append(Finding("pass", "diagram_explanation_alignment", "Diagram titles/captions are anchored to their visible labels."))

    if comparison_matrix_structure_gaps:
        findings.append(Finding("fail", "comparison_matrix_structure", f"Comparison matrices do not separate variables and compared entities: {comparison_matrix_structure_gaps}."))
    else:
        findings.append(Finding("pass", "comparison_matrix_structure", "Comparison matrices use one variable column and one dedicated column per compared entity."))

    if diagram_capacity_violations:
        findings.append(Finding("fail", "diagram_visible_capacity", f"Diagram content would be omitted or clipped by the renderer: {diagram_capacity_violations}."))
    else:
        findings.append(Finding("pass", "diagram_visible_capacity", "Every deterministic diagram fits its visible renderer capacity."))

    if cost_stack_total_layers:
        findings.append(Finding("fail", "cost_stack_total_semantics", f"Cost stacks must present the final total separately from additive layers: {cost_stack_total_layers}."))
    else:
        findings.append(Finding("pass", "cost_stack_total_semantics", "Cost-stack totals are presented as calculated results, not layers."))

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
