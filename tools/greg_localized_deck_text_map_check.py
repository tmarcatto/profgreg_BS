#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Finding:
    status: str
    check: str
    note: str


@dataclass
class SlideEntry:
    slide: int
    original_title: str
    localized_title: str
    visible_items: list[str]
    preserved_terms: str
    length_risk: str
    layout_note: str


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def parse_metadata(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z][A-Za-z ]+):\s*(.+)$", line.strip())
        if match:
            key = match.group(1).strip().lower().replace(" ", "_")
            value = match.group(2).strip().strip("`")
            metadata[key] = value
    return metadata


def parse_slides(text: str) -> list[SlideEntry]:
    parts = re.split(r"(?=^## Slide\s+\d+)", text, flags=re.MULTILINE)
    slides: list[SlideEntry] = []
    for part in parts:
        header = re.search(r"^## Slide\s+(\d+)", part, flags=re.MULTILINE)
        if not header:
            continue
        slide = int(header.group(1))
        original = field(part, "Original title")
        localized = field(part, "Localized title")
        preserved = field(part, "Preserved terms")
        risk = field(part, "Length risk").lower()
        note = field(part, "Layout note")
        visible = visible_items(part)
        slides.append(
            SlideEntry(
                slide=slide,
                original_title=original,
                localized_title=localized,
                visible_items=visible,
                preserved_terms=preserved,
                length_risk=risk,
                layout_note=note,
            )
        )
    return slides


def field(text: str, name: str) -> str:
    pattern = rf"^-\s+{re.escape(name)}:\s*(.+)$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def visible_items(text: str) -> list[str]:
    match = re.search(r"^-\s+Localized visible text:\s*\n(?P<body>(?:\s+-\s+.+\n?)+)", text, flags=re.MULTILINE)
    if not match:
        return []
    return [line.strip()[2:].strip() for line in match.group("body").splitlines() if line.strip().startswith("- ")]


def expansion_ratio(original: str, localized: str) -> float:
    if not original:
        return 0.0
    return len(localized) / max(1, len(original))


def compact_rewrite_needed(slide: SlideEntry) -> bool:
    text_blob = " ".join([slide.localized_title, *slide.visible_items])
    longest = max([len(item) for item in [slide.localized_title, *slide.visible_items]] or [0])
    return (
        slide.length_risk == "high"
        or expansion_ratio(slide.original_title, slide.localized_title) >= 1.35
        or longest >= 115
    )


def note_has_rewrite_plan(note: str) -> bool:
    return bool(re.search(r"rewrite|shorten|shorter|concise|compact|fit|layout|rewritten|reescrit|encurt|resum", note, re.IGNORECASE))


def run_checks(map_path: Path, qa_path: Path | None = None) -> dict:
    qa_path = qa_path or map_path.with_name(map_path.name.replace("_text_map_", "_localization_qa_"))
    text = read_text(map_path)
    qa_text = read_text(qa_path)
    findings: list[Finding] = []

    if map_path.exists():
        findings.append(Finding("pass", "map_exists", "Deck text map exists."))
    else:
        findings.append(Finding("fail", "map_exists", "Deck text map is missing."))

    metadata = parse_metadata(text)
    slides = parse_slides(text)

    required_meta = ["course_slug", "lesson", "source_deck", "target_locale", "scope", "status"]
    missing_meta = [key for key in required_meta if key not in metadata]
    if missing_meta:
        findings.append(Finding("fail", "metadata", f"Missing metadata fields: {missing_meta}."))
    else:
        findings.append(Finding("pass", "metadata", "Required metadata fields found."))

    if "smoke_test" in metadata.get("scope", ""):
        findings.append(Finding("pass", "scope_label", "Deck text map is clearly labeled as smoke test."))
    elif metadata.get("scope") == "deck_text_map":
        findings.append(Finding("pass", "scope_label", "Deck text map scope is explicit."))
    else:
        findings.append(Finding("warn", "scope_label", f"Unexpected scope `{metadata.get('scope', '')}`."))

    if slides:
        findings.append(Finding("pass", "slide_entries", f"Found {len(slides)} slide entries."))
    else:
        findings.append(Finding("fail", "slide_entries", "No slide entries found."))

    allowed_risks = {"low", "medium", "high"}
    bad_risks = [(slide.slide, slide.length_risk) for slide in slides if slide.length_risk not in allowed_risks]
    if bad_risks:
        findings.append(Finding("fail", "length_risk_values", f"Invalid length-risk values: {bad_risks}."))
    else:
        findings.append(Finding("pass", "length_risk_values", "All length-risk values are valid."))

    missing_fields = []
    for slide in slides:
        if not slide.original_title:
            missing_fields.append((slide.slide, "original_title"))
        if not slide.localized_title:
            missing_fields.append((slide.slide, "localized_title"))
        if not slide.visible_items:
            missing_fields.append((slide.slide, "localized_visible_text"))
        if not slide.preserved_terms:
            missing_fields.append((slide.slide, "preserved_terms"))
        if not slide.layout_note:
            missing_fields.append((slide.slide, "layout_note"))
    if missing_fields:
        findings.append(Finding("fail", "slide_required_fields", f"Missing slide fields: {missing_fields}."))
    else:
        findings.append(Finding("pass", "slide_required_fields", "All slide entries include required fields."))

    high_risk = [slide.slide for slide in slides if slide.length_risk == "high"]
    if high_risk:
        findings.append(Finding("warn", "high_length_risk", f"High length risk on slides: {high_risk}. Localized PPTX requires compact rewrite before rendering."))
    else:
        findings.append(Finding("pass", "high_length_risk", "No high length-risk slides."))

    no_plan = [slide.slide for slide in slides if compact_rewrite_needed(slide) and not note_has_rewrite_plan(slide.layout_note)]
    if no_plan:
        findings.append(Finding("fail", "compact_rewrite_plan", f"Slides need compact rewrite but layout note lacks a fit/rewrite plan: {no_plan}."))
    else:
        findings.append(Finding("pass", "compact_rewrite_plan", "Every high-expansion slide has a fit/rewrite layout note."))

    too_long_items = []
    for slide in slides:
        for item in [slide.localized_title, *slide.visible_items]:
            if len(item) > 150:
                too_long_items.append((slide.slide, len(item), item[:70] + "..."))
    if too_long_items:
        findings.append(Finding("warn", "very_long_visible_text", f"Very long localized visible text items: {too_long_items}."))
    else:
        findings.append(Finding("pass", "very_long_visible_text", "No very long localized visible text items found."))

    forbidden = [
        ("footer_numbers", r"\bfooter number\b|\bpage number\b|\bnúmero da página\b|\bnúmero de página\b"),
        ("speaker_notes", r"\bspeaker notes\b|\bnotas del presentador\b|\bnotas do apresentador\b"),
        ("activities", r"\bquiz\b|\bactivity\b|\batividade\b|\bactividad\b"),
    ]
    for check, pattern in forbidden:
        if re.search(pattern, text, flags=re.IGNORECASE):
            findings.append(Finding("fail", check, f"Forbidden deck-localization concept found: `{pattern}`."))
        else:
            findings.append(Finding("pass", check, "Forbidden localization concept not found."))

    qa_requirements = ["U.S. market", "Fit", "No new claims"]
    for needle in qa_requirements:
        if needle.lower() in qa_text.lower():
            findings.append(Finding("pass", f"qa_{needle.lower().replace(' ', '_')}", f"QA mentions `{needle}`."))
        else:
            findings.append(Finding("warn", f"qa_{needle.lower().replace(' ', '_')}", f"QA does not mention `{needle}`."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "map": str(map_path),
        "qa": str(qa_path),
        "target_locale": metadata.get("target_locale", ""),
        "scope": metadata.get("scope", ""),
        "slide_count": len(slides),
        "high_risk_slides": high_risk,
        "passed": fail_count == 0,
        "ready_for_pptx_rendering": fail_count == 0 and not high_risk,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict) -> str:
    lines = [
        f"Localized deck text-map QA passed: {'yes' if data['passed'] else 'no'}",
        f"Ready for localized PPTX rendering: {'yes' if data['ready_for_pptx_rendering'] else 'no'}",
        f"Locale: {data['target_locale']}",
        f"Scope: {data['scope']}",
        f"Slides mapped: {data['slide_count']}",
        f"High-risk slides: {data['high_risk_slides']}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        f"Map: {data['map']}",
        f"QA: {data['qa']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Prof Greg localized deck text maps before localized PPTX rendering.")
    parser.add_argument("map", help="Path to localized deck text map Markdown.")
    parser.add_argument("--qa", help="Path to localization QA Markdown.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    map_path = Path(args.map).expanduser().resolve()
    qa_path = Path(args.qa).expanduser().resolve() if args.qa else None
    data = run_checks(map_path, qa_path)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(data))
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
