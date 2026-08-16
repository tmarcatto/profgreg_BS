#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from greg_security import assert_safe_write_path


@dataclass
class Finding:
    status: str
    check: str
    note: str


STRUCTURAL_HEADINGS = {
    "lesson roadmap",
    "summary",
    "summary and key takeaways",
    "key takeaways",
    "glossary",
    "references",
}

ACTIVITY_PATTERNS = [
    r"\b(class|student|group|individual|practice|hands-on|interactive)\s+activit(?:y|ies)\b",
    r"\bactivit(?:y|ies)\s+(for|where)\s+(students|learners|the class)\b",
    r"\bexercise\b",
    r"\bquiz\b",
    r"\bquestionnaire\b",
    r"\bdiscussion prompt\b",
    r"\breflection prompt\b",
    r"\bgroup work\b",
    r"\bQ&A session\b",
]

INTERNAL_PATTERNS = [
    r"\btarget audience\b",
    r"\bprerequisites?\b",
    r"\bunit policy\b",
    r"\bsource policy\b",
    r"\binternal(?:ly)?\b",
    r"\bAI workflow\b",
]

INTRO_BOILERPLATE_PATTERNS = [
    r"\bthis study guide is written for\b",
    r"\bconstruction learners working in the united states\b",
    r"\btarget user\b",
    r"\btarget learner\b",
]

REFERENCE_PLACEHOLDER_PATTERNS = [
    r"\bCurrent student references will be added after research expansion\b",
    r"\bReferences?\s+pending\b",
    r"\bSource research pending\b",
]


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text))


def heading_name(line: str) -> str | None:
    match = re.match(r"^#{1,3}\s+(.+?)\s*$", line)
    if not match:
        return None
    return re.sub(r"[*_`]", "", match.group(1)).strip().lower()


def is_callout_label(line: str) -> str | None:
    stripped = line.strip()
    match = re.match(r"^>\s*\*\*([A-Z][A-Z ?&/-]{2,})\*\*\s*$", stripped)
    if match:
        return match.group(1).strip()
    return None


def callout_blocks(lines: list[str]) -> list[dict]:
    blocks = []
    current_section = ""
    index = 0
    while index < len(lines):
        heading = heading_name(lines[index])
        if heading:
            current_section = heading
        label = is_callout_label(lines[index])
        if not label:
            index += 1
            continue
        start = index + 1
        index += 1
        body_lines = []
        while index < len(lines):
            if heading_name(lines[index]) or is_callout_label(lines[index]):
                break
            if lines[index].startswith(">"):
                body_lines.append(lines[index])
            elif lines[index].strip():
                break
            index += 1
        body_text = "\n".join(line.lstrip("> ").strip() for line in body_lines)
        paragraphs = [para for para in re.split(r"\n\s*>\s*\n|\n\s*\n", body_text) if para.strip()]
        blocks.append(
            {
                "label": label,
                "section": current_section,
                "line": start,
                "paragraph_count": len(paragraphs),
            }
        )
    return blocks


def run_checks(draft_path: Path) -> dict:
    findings: list[Finding] = []
    text = read_text(draft_path)
    lines = text.splitlines()

    if draft_path.exists():
        findings.append(Finding("pass", "draft_exists", "Study guide draft exists."))
    else:
        findings.append(Finding("fail", "draft_exists", "Study guide draft is missing."))

    forbidden_activity = []
    for pattern in ACTIVITY_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            forbidden_activity.append(pattern)
    if forbidden_activity:
        findings.append(Finding("fail", "no_activities", f"Activity/quiz language found: {forbidden_activity}."))
    else:
        findings.append(Finding("pass", "no_activities", "No activity, quiz, or reflection-prompt language found."))

    intro_text = text.split("# Section 01", 1)[0]
    internal_found = []
    for pattern in INTERNAL_PATTERNS:
        if re.search(pattern, intro_text, flags=re.IGNORECASE):
            internal_found.append(pattern)
    if internal_found:
        findings.append(Finding("fail", "student_facing_intro_metadata", f"Internal metadata language before lesson body: {internal_found}."))
    else:
        findings.append(Finding("pass", "student_facing_intro_metadata", "No obvious internal metadata in student-facing intro area."))

    intro_boilerplate = []
    for pattern in INTRO_BOILERPLATE_PATTERNS:
        if re.search(pattern, intro_text, flags=re.IGNORECASE):
            intro_boilerplate.append(pattern)
    if intro_boilerplate:
        findings.append(Finding("fail", "course_focused_introduction", f"Introduction contains operator/audience boilerplate instead of course-facing orientation: {intro_boilerplate}."))
    else:
        findings.append(Finding("pass", "course_focused_introduction", "Introduction does not explain the target user as metadata."))

    blocks = callout_blocks(lines)
    if blocks:
        findings.append(Finding("pass", "callouts_present", f"Found {len(blocks)} callout blocks."))
    else:
        findings.append(Finding("warn", "callouts_present", "No callout blocks found."))

    structural_callouts = [f"{block['label']} line {block['line']} in {block['section']}" for block in blocks if block["section"] in STRUCTURAL_HEADINGS]
    if structural_callouts:
        findings.append(Finding("fail", "callouts_not_structural", f"Callouts appear in structural sections: {structural_callouts}."))
    else:
        findings.append(Finding("pass", "callouts_not_structural", "No callouts found in roadmap, summary, glossary, or references."))

    long_callouts = [f"{block['label']} line {block['line']} ({block['paragraph_count']} paragraphs)" for block in blocks if block["paragraph_count"] > 3]
    if long_callouts:
        findings.append(Finding("fail", "callout_length", f"Callouts exceed 3 paragraphs: {long_callouts}."))
    else:
        findings.append(Finding("pass", "callout_length", "Callouts are 3 paragraphs or fewer."))

    consecutive = []
    for first, second in zip(blocks, blocks[1:]):
        between = "\n".join(lines[first["line"] : second["line"] - 1])
        body_between = [line for line in between.splitlines() if line.strip() and not line.strip().startswith(">") and not heading_name(line)]
        if not body_between:
            consecutive.append((first["label"], second["label"], second["line"]))
    if consecutive:
        findings.append(Finding("fail", "callout_spacing", f"Back-to-back callouts without body text: {consecutive}."))
    else:
        findings.append(Finding("pass", "callout_spacing", "No back-to-back callouts found."))

    if re.search(r"\blearning line\b", text, flags=re.IGNORECASE):
        findings.append(Finding("fail", "no_learning_line_visible", "Visible `learning line` language found."))
    else:
        findings.append(Finding("pass", "no_learning_line_visible", "No visible `learning line` language found."))

    if re.search(r"\bAccessed\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b", text):
        findings.append(Finding("fail", "no_access_dates", "Visible reference access date found."))
    else:
        findings.append(Finding("pass", "no_access_dates", "No visible reference access dates found."))

    references_match = re.search(r"(?ims)^#\s+References\s*$([\s\S]+)$", text)
    references_text = references_match.group(1).strip() if references_match else ""
    if not references_match:
        findings.append(Finding("fail", "references_present", "References section is missing."))
    elif word_count(references_text) < 6:
        findings.append(Finding("fail", "references_present", "References section has no usable source entries."))
    else:
        findings.append(Finding("pass", "references_present", "References section has usable source entries."))

    placeholder_refs = []
    for pattern in REFERENCE_PLACEHOLDER_PATTERNS:
        if re.search(pattern, references_text, flags=re.IGNORECASE):
            placeholder_refs.append(pattern)
    if placeholder_refs:
        findings.append(Finding("fail", "no_reference_placeholders", f"Placeholder reference language found: {placeholder_refs}."))
    else:
        findings.append(Finding("pass", "no_reference_placeholders", "No placeholder reference language found."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "draft": str(draft_path),
        "callout_count": len(blocks),
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict) -> str:
    lines = [
        f"Study guide content QA passed: {'yes' if data['passed'] else 'no'}",
        f"Callouts: {data['callout_count']}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        f"Draft: {data['draft']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Prof Greg study guide draft content rules before rendering.")
    parser.add_argument("draft", help="Path to lesson draft Markdown.")
    parser.add_argument("--output", help="Optional path to write the Markdown report.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    data = run_checks(Path(args.draft).expanduser().resolve())
    markdown = render_markdown(data)
    if args.output:
        output = assert_safe_write_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown + "\n", encoding="utf-8")
    if args.json:
        import json

        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(markdown)
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
