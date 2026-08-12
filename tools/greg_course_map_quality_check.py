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


ADAPTIVE_DECISION_WORDS = {
    "renamed",
    "reframed",
    "reordered",
    "merged",
    "split",
    "added",
    "removed",
    "flagged",
    "narrowed",
    "expanded",
}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def lesson_titles_from_intake(text: str) -> list[str]:
    titles = []
    for line in text.splitlines():
        match = re.match(r"#{1,4}\s*Lesson\s+\d+\s*:\s*(.+)$", line.strip(), re.IGNORECASE)
        if match:
            titles.append(match.group(1).strip("* ").strip())
    return titles


def lesson_titles_from_json(data: dict[str, Any]) -> list[str]:
    titles = []
    for lesson in data.get("lessons") or []:
        title = lesson.get("title") or lesson.get("lesson_title")
        if title:
            titles.append(str(title).strip())
    return titles


def adaptation_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    entries = data.get("syllabus_adaptation")
    if isinstance(entries, list):
        return entries
    entries = data.get("syllabus_adaptations")
    if isinstance(entries, list):
        return entries
    return []


def decisions_from_markdown_table(text: str) -> list[tuple[str, str, str, str]]:
    entries: list[tuple[str, str, str, str]] = []
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("| Input item | Decision |"):
            in_table = True
            continue
        if in_table and stripped.startswith("|---"):
            continue
        if in_table:
            if not stripped.startswith("|"):
                if entries:
                    break
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) >= 4:
                entries.append((cells[0], cells[1], cells[2], cells[3]))
    return entries


def normalized(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def exact_title_matches(input_titles: list[str], mapped_titles: list[str]) -> int:
    mapped = {normalized(title) for title in mapped_titles}
    return sum(1 for title in input_titles if normalized(title) in mapped)


def has_adaptive_decision(decision_text: str) -> bool:
    text = decision_text.lower().replace("_", " ").replace("-", " ")
    return any(word in text for word in ADAPTIVE_DECISION_WORDS)


def run_checks(course_map_json: Path, course_map_md: Path, adaptation_log: Path, intake: Path | None = None) -> dict[str, Any]:
    findings: list[Finding] = []
    data = load_json(course_map_json)
    md_text = read_text(course_map_md)
    log_text = read_text(adaptation_log)
    intake_text = read_text(intake) if intake else ""

    for name, path in [
        ("course_map_json", course_map_json),
        ("course_map_md", course_map_md),
        ("syllabus_adaptation_log", adaptation_log),
    ]:
        if path.exists():
            findings.append(Finding("pass", f"{name}_exists", f"{name} exists."))
        else:
            findings.append(Finding("fail", f"{name}_exists", f"{name} is missing."))

    lessons = data.get("lessons") or []
    if lessons:
        findings.append(Finding("pass", "lessons_present", f"Course Map has {len(lessons)} lessons."))
    else:
        findings.append(Finding("fail", "lessons_present", "Course Map JSON has no lessons."))

    level = str(data.get("level") or (data.get("course") or {}).get("level") or "")
    audience = str(data.get("target_audience") or (data.get("course") or {}).get("target_audience") or "")
    if "basic" in level.lower() or "entry" in level.lower() or "intermediate" in level.lower() or "advanced" in level.lower():
        findings.append(Finding("pass", "level_recorded", f"Course level recorded as `{level}`."))
    else:
        findings.append(Finding("fail", "level_recorded", "Course level is missing or not one of the expected learning levels."))

    if "construction" in audience.lower() and ("united states" in audience.lower() or "u.s." in audience.lower() or "usa" in audience.lower()):
        findings.append(Finding("pass", "audience_recorded", "Audience is construction learners/workers in the U.S. market."))
    else:
        findings.append(Finding("fail", "audience_recorded", "Audience does not clearly state construction learners/workers in the U.S. market."))

    audience_context = " ".join(
        [
            audience,
            str((data.get("course") or {}).get("sector_anchor") or ""),
            str(data.get("sector_anchor") or ""),
            str(data.get("scope_rationale") or ""),
            md_text,
            log_text,
        ]
    ).lower()
    if "residential" in audience_context:
        findings.append(Finding("pass", "residential_anchor", "Course Map records the residential-construction-first learner context."))
    else:
        findings.append(Finding("fail", "residential_anchor", "Course Map does not record the residential-construction-first learner context."))

    entries_json = adaptation_entries(data)
    entries_md = decisions_from_markdown_table(md_text)
    entries_log = decisions_from_markdown_table(log_text)
    if entries_json or entries_md or entries_log:
        findings.append(Finding("pass", "adaptation_entries_present", f"Adaptation entries found: json={len(entries_json)}, map={len(entries_md)}, log={len(entries_log)}."))
    else:
        findings.append(Finding("fail", "adaptation_entries_present", "No syllabus adaptation entries found in JSON, Course Map Markdown, or adaptation log."))

    log_lower = log_text.lower()
    if "initial direction" in log_lower and re.search(r"not\s+(as\s+)?a\s+fixed\s+contract", log_lower):
        findings.append(Finding("pass", "syllabus_not_fixed_contract", "Adaptation log states syllabus is initial direction, not fixed contract."))
    else:
        findings.append(Finding("fail", "syllabus_not_fixed_contract", "Adaptation log does not state that the syllabus is initial direction, not fixed contract."))

    rationale_gaps = []
    for index, entry in enumerate(entries_json):
        rationale = str(entry.get("rationale") or "").strip()
        decision = str(entry.get("decision") or "").strip()
        if not decision or len(rationale.split()) < 3:
            rationale_gaps.append(f"json[{index}]")
    for index, row in enumerate(entries_log):
        if not row[1] or len(row[3].split()) < 3:
            rationale_gaps.append(f"log[{index}]")
    if rationale_gaps:
        findings.append(Finding("fail", "adaptation_rationale", f"Adaptation entries lack decision/rationale: {rationale_gaps}."))
    else:
        findings.append(Finding("pass", "adaptation_rationale", "Adaptation decisions include usable rationale."))

    all_decisions = [str(entry.get("decision") or "") for entry in entries_json] + [row[1] for row in entries_md] + [row[1] for row in entries_log]
    if any(has_adaptive_decision(decision) for decision in all_decisions):
        findings.append(Finding("pass", "adaptive_decision_recorded", "At least one adaptive syllabus decision is recorded."))
    else:
        preserved_rationale = "evaluated" in log_lower and any(word in log_lower for word in ["preserved", "coherent", "strong"])
        if preserved_rationale:
            findings.append(Finding("warn", "adaptive_decision_recorded", "No adaptive decision recorded, but preservation rationale is documented."))
        else:
            findings.append(Finding("fail", "adaptive_decision_recorded", "No adaptive decision or preservation rationale found."))

    input_titles = lesson_titles_from_intake(intake_text)
    mapped_titles = lesson_titles_from_json(data)
    if input_titles and mapped_titles:
        exact = exact_title_matches(input_titles, mapped_titles)
        if exact == len(input_titles) and not any(has_adaptive_decision(decision) for decision in all_decisions):
            findings.append(Finding("fail", "syllabus_mirroring", "Course Map lesson titles exactly mirror the input and no adaptation/preservation rationale is recorded."))
        else:
            findings.append(Finding("pass", "syllabus_mirroring", f"Input/title comparison is traceable: {exact}/{len(input_titles)} exact title matches."))
    else:
        findings.append(Finding("warn", "syllabus_mirroring", "Could not compare input syllabus titles to Course Map titles."))

    lesson_count_text = " ".join(
        [
            str((data.get("course") or {}).get("lesson_count_rationale") or ""),
            str(data.get("scope_rationale") or ""),
            md_text,
        ]
    ).lower()
    if "lesson count" in lesson_count_text or "10-lesson" in lesson_count_text or "estimated lesson count" in lesson_count_text:
        findings.append(Finding("pass", "lesson_count_rationale", "Lesson count rationale is documented."))
    else:
        findings.append(Finding("fail", "lesson_count_rationale", "Lesson count rationale is missing."))

    source_text = (md_text + "\n" + log_text + "\n" + json.dumps(data, ensure_ascii=False)).lower()
    if "source" in source_text and ("authority" in source_text or "aia" in source_text or "agc" in source_text or "cmaa" in source_text or "body of knowledge" in source_text):
        findings.append(Finding("pass", "source_basis", "Course Map records source/authority basis."))
    else:
        findings.append(Finding("fail", "source_basis", "Course Map does not clearly record source/authority basis."))

    if "practitioner-context" in source_text or "practitioner context" in source_text:
        findings.append(Finding("pass", "practitioner_context", "Practitioner-context source opportunities are recorded."))
    else:
        findings.append(Finding("warn", "practitioner_context", "Practitioner-context source opportunities are not explicit."))

    approval_text = " ".join([str(data.get("approval_status") or ""), json.dumps(data.get("qa") or {}), md_text, log_text]).lower()
    if "approved" in approval_text:
        findings.append(Finding("pass", "autonomous_approval_status", "Course Map autonomous approval is recorded."))
    else:
        findings.append(Finding("fail", "autonomous_approval_status", "Course Map approval status is missing."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "course_map_json": str(course_map_json),
        "course_map_md": str(course_map_md),
        "syllabus_adaptation_log": str(adaptation_log),
        "intake": str(intake) if intake else None,
        "lesson_count": len(lessons),
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"Course Map QA passed: {'yes' if data['passed'] else 'no'}",
        f"Lessons: {data['lesson_count']}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        f"Course Map JSON: {data['course_map_json']}",
        f"Course Map Markdown: {data['course_map_md']}",
        f"Adaptation log: {data['syllabus_adaptation_log']}",
    ]
    if data.get("intake"):
        lines.append(f"Intake: {data['intake']}")
    lines.extend(["", "Findings:"])
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Prof Greg Course Map adaptation and approval quality.")
    parser.add_argument("course_map_json", help="Path to course_map.json.")
    parser.add_argument("course_map_md", help="Path to course_map.md.")
    parser.add_argument("syllabus_adaptation_log", help="Path to syllabus_adaptation_log.md.")
    parser.add_argument("--intake", help="Optional path to input/intake.md for syllabus/title comparison.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    data = run_checks(
        Path(args.course_map_json).expanduser().resolve(),
        Path(args.course_map_md).expanduser().resolve(),
        Path(args.syllabus_adaptation_log).expanduser().resolve(),
        Path(args.intake).expanduser().resolve() if args.intake else None,
    )
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(data))
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
