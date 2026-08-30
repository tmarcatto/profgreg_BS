#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from greg_security import assert_safe_run_slug, assert_safe_write_path


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Finding:
    status: str
    check: str
    note: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def normalize(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"\([^)]*\)", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def lesson_id(lesson: int) -> str:
    return f"lesson_{lesson:02d}"


def extract_glossary_terms(markdown: str) -> list[str]:
    match = re.search(r"^# Glossary\s*(.*?)\n---\s*\n# References", markdown, flags=re.M | re.S)
    if not match:
        match = re.search(r"^# Glossary\s*(.*)$", markdown, flags=re.M | re.S)
    if not match:
        return []
    terms: list[str] = []
    for term in re.findall(r"^- \*\*(.+?)\*\*:", match.group(1), flags=re.M):
        normalized = normalize(term)
        if normalized:
            terms.append(normalized)
    return terms


def extract_section_headings(markdown: str) -> list[str]:
    headings: list[str] = []
    for heading in re.findall(r"^# Section\s+\d+\s+-\s+(.+)$", markdown, flags=re.M | re.I):
        normalized = normalize(heading)
        if normalized:
            headings.append(normalized)
    return headings


def visual_structure(visual: dict[str, Any]) -> str:
    visual_type = str(visual.get("type") or "")
    if visual_type == "card_row":
        cards = visual.get("cards") if isinstance(visual.get("cards"), list) else []
        return f"card_row:{len(cards)}:pill:{bool(visual.get('pill'))}"
    if visual_type == "timeline":
        return "timeline"
    if visual_type == "source_to_wbs_matrix":
        rows = visual.get("rows") if isinstance(visual.get("rows"), list) else []
        return f"source_to_wbs_matrix:{len(rows)}"
    return visual_type


def visual_title(visual: dict[str, Any]) -> str:
    return normalize(str(visual.get("title") or ""))


def previous_lessons(run: Path, lesson: int) -> list[int]:
    found: list[int] = []
    for path in (run / "lesson_draft").glob("lesson_*_draft*.md"):
        match = re.fullmatch(r"lesson_(\d+)_draft(?:_r\d+)?\.md", path.name)
        if match and int(match.group(1)) < lesson:
            found.append(int(match.group(1)))
    return sorted(found)


def lesson_paths(run: Path, lesson: int) -> tuple[Path, Path]:
    lid = lesson_id(lesson)
    drafts = sorted((run / "lesson_draft").glob(f"{lid}_draft_r*.md"))
    specs = sorted((run / "docx_pdf").glob(f"{lid}_study_guide_spec_r*.json"))
    return (drafts[-1] if drafts else run / "lesson_draft" / f"{lid}_draft.md", specs[-1] if specs else run / "docx_pdf" / f"{lid}_study_guide_spec.json")


def run_checks(course_slug: str, lesson: int) -> dict[str, Any]:
    course_slug = assert_safe_run_slug(course_slug)
    run = ROOT / "runs" / course_slug
    draft_path, spec_path = lesson_paths(run, lesson)
    findings: list[Finding] = []

    if draft_path.exists() and spec_path.exists():
        findings.append(Finding("pass", "current_artifacts", "Current lesson draft and PDF spec exist."))
    else:
        missing = [str(path) for path in (draft_path, spec_path) if not path.exists()]
        findings.append(Finding("fail", "current_artifacts", f"Missing current lesson artifacts: {missing}."))

    previous = previous_lessons(run, lesson)
    if previous:
        findings.append(Finding("pass", "previous_lessons_found", f"Compared against prior lessons: {previous}."))
    else:
        findings.append(Finding("warn", "previous_lessons_found", "No prior lesson drafts found; cross-lesson MECE is limited."))

    current_markdown = read_text(draft_path)
    current_spec = read_json(spec_path)
    current_terms = set(extract_glossary_terms(current_markdown))
    current_headings = set(extract_section_headings(current_markdown))
    current_visuals = current_spec.get("visuals") if isinstance(current_spec.get("visuals"), list) else []
    current_visual_titles = {visual_title(visual) for visual in current_visuals if visual_title(visual)}
    current_visual_structures = [visual_structure(visual) for visual in current_visuals]

    prior_terms: set[str] = set()
    prior_headings: set[str] = set()
    prior_visual_titles: set[str] = set()
    prior_visual_structures: dict[str, list[int]] = {}

    for prior_lesson in previous:
        prior_draft, prior_spec_path = lesson_paths(run, prior_lesson)
        prior_markdown = read_text(prior_draft)
        prior_spec = read_json(prior_spec_path)
        prior_terms.update(extract_glossary_terms(prior_markdown))
        prior_headings.update(extract_section_headings(prior_markdown))
        prior_visual_titles.update(
            title for title in (visual_title(visual) for visual in prior_spec.get("visuals", [])) if title
        )
        for visual in prior_spec.get("visuals", []):
            prior_visual_structures.setdefault(visual_structure(visual), []).append(prior_lesson)

    repeated_terms = sorted(current_terms & prior_terms)
    if repeated_terms:
        findings.append(Finding("fail", "glossary_mece", f"Glossary repeats prior lesson terms: {repeated_terms}."))
    else:
        findings.append(Finding("pass", "glossary_mece", "Glossary terms are new relative to prior lessons."))

    repeated_headings = sorted(current_headings & prior_headings)
    if repeated_headings:
        findings.append(Finding("fail", "section_heading_mece", f"Section headings repeat prior lessons: {repeated_headings}."))
    else:
        findings.append(Finding("pass", "section_heading_mece", "Section headings are distinct from prior lessons."))

    repeated_titles = sorted(current_visual_titles & prior_visual_titles)
    if repeated_titles:
        findings.append(Finding("fail", "visual_title_mece", f"Visual titles repeat prior lessons: {repeated_titles}."))
    else:
        findings.append(Finding("pass", "visual_title_mece", "Visual titles are distinct from prior lessons."))

    repeated_structures = sorted(
        {
            structure
            for structure in current_visual_structures
            if structure in prior_visual_structures and structure.startswith("card_row:")
        }
    )
    if repeated_structures:
        findings.append(
            Finding(
                "warn",
                "visual_structure_mece",
                "Card-row structure is reused across lessons: "
                f"{repeated_structures}. Confirm visual variety during review; structure alone does not mean the teaching scope overlaps.",
            )
        )
    else:
        findings.append(Finding("pass", "visual_structure_mece", "No repeated card-row visual structure from prior lessons."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "course_slug": course_slug,
        "lesson": lesson,
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"Cross-lesson MECE QA passed: {'yes' if data['passed'] else 'no'}",
        f"Course: {data['course_slug']}",
        f"Lesson: {data['lesson']:02d}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check cross-lesson MECE for Prof Greg lesson artifacts.")
    parser.add_argument("course_slug", help="Course/run slug under runs/.")
    parser.add_argument("--lesson", type=int, required=True, help="Current lesson number.")
    parser.add_argument("--output", help="Optional Markdown output path.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    data = run_checks(args.course_slug, args.lesson)
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
