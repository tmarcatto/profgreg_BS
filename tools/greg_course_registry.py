#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from greg_security import assert_safe_run_slug, assert_safe_write_path


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


@dataclass
class Finding:
    status: str
    check: str
    note: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"\([^)]*\)", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def lesson_numbers(run: Path) -> list[str]:
    found: set[str] = set()
    for pattern in ["lesson_draft/lesson_*_draft*.md", "docx_pdf/lesson_*_study_guide_spec*.json", "review/lesson_*_visual_plan.json", "deck/lesson_*_visual_plan.json"]:
        for path in run.glob(pattern):
            match = re.search(r"lesson_(\d+)_", path.name)
            if match:
                found.add(f"{int(match.group(1)):02d}")
    return sorted(found)


def latest_path(folder: Path, pattern: str) -> Path | None:
    matches = sorted(folder.glob(pattern), key=lambda item: (item.stat().st_mtime, item.name))
    return matches[-1] if matches else None


def extract_glossary(markdown: str) -> list[dict[str, str]]:
    match = re.search(r"^# Glossary\s*(.*?)\n---\s*\n# References", markdown, flags=re.M | re.S)
    if not match:
        match = re.search(r"^# Glossary\s*(.*)$", markdown, flags=re.M | re.S)
    if not match:
        return []
    terms: list[dict[str, str]] = []
    for term, definition in re.findall(r"^- \*\*(.+?)\*\*:\s*(.+)$", match.group(1), flags=re.M):
        normalized = normalize(term)
        if normalized:
            terms.append({"term": term.strip(), "normalized": normalized, "definition": definition.strip()})
    return terms


def visual_structure(visual: dict[str, Any]) -> str:
    visual_type = str(visual.get("visual_type") or visual.get("type") or "")
    if visual_type in {"deterministic-diagram", "chart", "process-flow", "structured-visual"}:
        mechanism = str(visual.get("diagram_type") or "").strip()
        return f"native:{mechanism or 'unspecified'}"
    if visual_type == "card_row":
        cards = visual.get("cards") if isinstance(visual.get("cards"), list) else []
        return f"card_row:{len(cards)}:pill:{bool(visual.get('pill'))}"
    if visual_type == "source_to_wbs_matrix":
        rows = visual.get("rows") if isinstance(visual.get("rows"), list) else []
        return f"source_to_wbs_matrix:{len(rows)}"
    if visual_type in {"generated-conceptual-image", "trusted-source-image", "real-source-image"}:
        return visual_type
    return visual_type or "unknown"


def collect_study_visuals(run: Path, lesson: str) -> list[dict[str, Any]]:
    spec_path = latest_path(run / "docx_pdf", f"lesson_{lesson}_study_guide_spec_r*.json") or latest_path(run / "docx_pdf", f"lesson_{lesson}_study_guide_spec.json")
    spec = read_json(spec_path) if spec_path else {}
    visuals = []
    for index, visual in enumerate(spec.get("visuals") or [], start=1):
        title = str(visual.get("title") or "").strip()
        caption = str(visual.get("caption") or "").strip()
        visuals.append(
            {
                "visual_id": f"lesson_{lesson}_study_{index:02d}",
                "lesson": lesson,
                "artifact": "study_guide",
                "type": str(visual.get("type") or ""),
                "title": title,
                "normalized_title": normalize(title),
                "caption": caption,
                "structure": visual_structure(visual),
                "structure_justification": str(visual.get("structure_justification") or ""),
                "learning_claim": normalize(caption),
            }
        )
    return visuals


def collect_deck_visuals(run: Path, lesson: str) -> list[dict[str, Any]]:
    plan_path = latest_path(run / "deck", f"lesson_{lesson}_visual_plan*.json") or latest_path(run / "review", f"lesson_{lesson}_visual_plan*.json")
    plan = read_json(plan_path) if plan_path else {}
    visuals = []
    for index, visual in enumerate(plan.get("visuals") or [], start=1):
        if visual.get("role") == "brand" or visual.get("visual_type") in {"brand-mark", "logo"}:
            continue
        title = str(visual.get("visual_id") or f"deck_visual_{index:02d}")
        learning_claim = str(visual.get("learning_claim") or "")
        visuals.append(
            {
                "visual_id": title,
                "lesson": lesson,
                "artifact": "deck",
                "type": str(visual.get("visual_type") or ""),
                "title": title,
                "normalized_title": normalize(title),
                "caption": "",
                "structure": visual_structure(visual),
                "structure_justification": str(visual.get("structure_justification") or visual.get("purpose") or ""),
                "learning_claim": normalize(learning_claim),
            }
        )
    return visuals


def build_registry(course_slug: str) -> dict[str, Any]:
    course_slug = assert_safe_run_slug(course_slug)
    run = RUNS / course_slug
    lessons = []
    glossary_terms = []
    visuals = []
    for lesson in lesson_numbers(run):
        draft_path = latest_path(run / "lesson_draft", f"lesson_{lesson}_draft_r*.md") or run / "lesson_draft" / f"lesson_{lesson}_draft.md"
        terms = extract_glossary(read_text(draft_path))
        lesson_study_visuals = collect_study_visuals(run, lesson)
        lesson_deck_visuals = collect_deck_visuals(run, lesson)
        for term in terms:
            glossary_terms.append({"lesson": lesson, **term})
        visuals.extend(lesson_study_visuals)
        visuals.extend(lesson_deck_visuals)
        lessons.append(
            {
                "lesson": lesson,
                "draft": str(draft_path.relative_to(run)) if draft_path.exists() else "",
                "glossary_count": len(terms),
                "study_visual_count": len(lesson_study_visuals),
                "deck_visual_count": len(lesson_deck_visuals),
            }
        )

    return {
        "course_slug": course_slug,
        "registry_version": 1,
        "lessons": lessons,
        "glossary_terms": glossary_terms,
        "visuals": visuals,
    }


def duplicate_groups(rows: list[dict[str, Any]], key: str) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        value = str(row.get(key) or "")
        if value:
            grouped[value].append(f"L{row.get('lesson')}:{row.get('term') or row.get('visual_id')}")
    return {value: labels for value, labels in grouped.items() if len(labels) > 1}


def run_checks(course_slug: str, registry_path: Path | None = None) -> dict[str, Any]:
    course_slug = assert_safe_run_slug(course_slug)
    run = RUNS / course_slug
    registry_path = registry_path or run / "process_review" / "course_registry.json"
    registry = read_json(registry_path) if registry_path.exists() else build_registry(course_slug)
    findings: list[Finding] = []

    if registry.get("lessons"):
        findings.append(Finding("pass", "lessons_present", f"Registry covers {len(registry['lessons'])} lessons."))
    else:
        findings.append(Finding("fail", "lessons_present", "Registry has no lessons."))

    term_duplicates = duplicate_groups(registry.get("glossary_terms") or [], "normalized")
    if term_duplicates:
        findings.append(Finding("fail", "glossary_home_lesson", f"Repeated glossary home terms: {term_duplicates}."))
    else:
        findings.append(Finding("pass", "glossary_home_lesson", "Each glossary term has one home lesson."))

    title_duplicates = duplicate_groups(registry.get("visuals") or [], "normalized_title")
    if title_duplicates:
        findings.append(Finding("fail", "visual_title_registry", f"Repeated visual titles/IDs: {title_duplicates}."))
    else:
        findings.append(Finding("pass", "visual_title_registry", "Visual titles/IDs are unique across the course registry."))

    structured_rows = [
        row for row in registry.get("visuals") or []
        if str(row.get("structure", "")).startswith(("card_row:", "native:"))
    ]
    raw_structure_duplicates = duplicate_groups(structured_rows, "structure")
    structure_duplicates = {}
    for structure, labels in raw_structure_duplicates.items():
        rows = [row for row in structured_rows if row.get("structure") == structure]
        if all(str(row.get("structure_justification") or "").strip() for row in rows):
            continue
        structure_duplicates[structure] = labels
    if structure_duplicates:
        findings.append(Finding("warn", "visual_structure_registry", f"Repeated visual structures need explicit content-specific justification: {structure_duplicates}."))
    else:
        findings.append(Finding("pass", "visual_structure_registry", "Repeated native visual structures, if any, have content-specific justification."))

    claim_duplicates = duplicate_groups([row for row in registry.get("visuals") or [] if row.get("learning_claim")], "learning_claim")
    if claim_duplicates:
        findings.append(Finding("fail", "visual_claim_registry", f"Repeated visual learning claims: {claim_duplicates}."))
    else:
        findings.append(Finding("pass", "visual_claim_registry", "Visual learning claims are unique across the course registry."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "course_slug": course_slug,
        "registry": str(registry_path),
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown_registry(registry: dict[str, Any]) -> str:
    lines = [
        "# Course Registry",
        "",
        f"Course slug: `{registry['course_slug']}`",
        f"Registry version: {registry['registry_version']}",
        "",
        "## Lessons",
        "",
        "| Lesson | Glossary Terms | Study Visuals | Deck Visuals |",
        "|---|---:|---:|---:|",
    ]
    for lesson in registry["lessons"]:
        lines.append(f"| {lesson['lesson']} | {lesson['glossary_count']} | {lesson['study_visual_count']} | {lesson['deck_visual_count']} |")
    lines.extend(["", "## Glossary Home Lessons", ""])
    for row in registry["glossary_terms"]:
        lines.append(f"- L{row['lesson']}: {row['term']}")
    lines.extend(["", "## Visual Registry", ""])
    for row in registry["visuals"]:
        lines.append(f"- L{row['lesson']} {row['artifact']}: {row['title']} [{row['type']} / {row['structure']}]")
    return "\n".join(lines)


def render_markdown_check(data: dict[str, Any]) -> str:
    lines = [
        f"Course registry QA passed: {'yes' if data['passed'] else 'no'}",
        f"Course: {data['course_slug']}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        f"Registry: {data['registry']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def write_registry(course_slug: str) -> tuple[Path, Path]:
    run = RUNS / course_slug
    registry = build_registry(course_slug)
    out_json = run / "process_review" / "course_registry.json"
    out_md = run / "process_review" / "course_registry.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    out_md.write_text(render_markdown_registry(registry) + "\n", encoding="utf-8")
    return out_json, out_md


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and validate Prof Greg course glossary/visual registry.")
    parser.add_argument("course_slug")
    parser.add_argument("--write", action="store_true", help="Write process_review/course_registry.json and .md before checking.")
    parser.add_argument("--json", action="store_true", help="Print QA result as JSON.")
    parser.add_argument("--output", help="Optional Markdown QA output path.")
    args = parser.parse_args()

    if args.write:
        write_registry(args.course_slug)
    data = run_checks(args.course_slug)
    markdown = render_markdown_check(data)
    if args.output:
        output = assert_safe_write_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2, ensure_ascii=False) if args.json else markdown)
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
