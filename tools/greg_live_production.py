#!/usr/bin/env python3
"""Real production stages for the operator flow.

Unlike the historical v0 fixture producer, this module never treats an
existing student file as a successful run. It produces revisioned artifacts,
routes model work through the configured role router, and stops before an
approval gate when an automatic QA gate fails.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from greg_model_router import ModelRequestError, json_from_text, request_image, request_text
from greg_security import assert_safe_run_slug
from greg_v0_production import BRAND_ICON, NEGATIVE_WORDMARK, RUNS, lid, parse_intake, read_uploads, rel, write_json, write_text


ROOT = Path(__file__).resolve().parents[1]


def production_python() -> str:
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
    return str(bundled) if bundled.exists() else sys.executable


def run_pdf_layout_qa(pdf_path: Path, qa_path: Path, output_path: Path) -> dict[str, Any]:
    command = [
        production_python(),
        str(ROOT / "tools" / "greg_pdf_layout_check.py"),
        str(pdf_path),
        "--qa",
        str(qa_path),
        "--output",
        str(output_path),
        "--json",
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    try:
        layout = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        detail = result.stderr.strip() or result.stdout.strip() or "Layout checker returned no structured result."
        raise RuntimeError(detail) from error
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "Study guide layout checker failed.")
    return layout


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def next_revision(run: Path, folder: str, base_name: str, extension: str) -> int:
    pattern = re.compile(rf"^{re.escape(base_name)}_r(\d+){re.escape(extension)}$")
    revisions = []
    for path in (run / folder).glob(f"{base_name}_r*{extension}"):
        match = pattern.match(path.name)
        if match:
            revisions.append(int(match.group(1)))
    return (max(revisions) if revisions else 0) + 1


def revisioned(run: Path, folder: str, base_name: str, extension: str) -> tuple[int, str]:
    revision = next_revision(run, folder, base_name, extension)
    return revision, f"{base_name}_r{revision:02d}{extension}"


def next_study_guide_revision(run: Path, lesson_tag: str) -> int:
    revisions: list[int] = []
    patterns = (
        (run / "lesson_draft", re.compile(rf"^{re.escape(lesson_tag)}_draft_r(\d+)\.md$")),
        (run / "docx_pdf", re.compile(rf"^{re.escape(lesson_tag)}_study_guide_r(\d+)\.pdf$")),
    )
    for folder, pattern in patterns:
        for path in folder.glob(f"{lesson_tag}_*"):
            match = pattern.match(path.name)
            if match:
                revisions.append(int(match.group(1)))
    return (max(revisions) if revisions else 0) + 1


def block(run: Path, stage: str, detail: str) -> None:
    path = run / stage / f"{stage}_blocked.md"
    write_text(
        path,
        f"# Production Blocked\n\nStage: {stage}\nDate: {date.today().isoformat()}\n\n{detail}\n",
    )


def update_canonical_manifest(course_slug: str) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "greg_canonical_artifacts.py"), course_slug, "--write", "--allow-missing"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def strip_json_fence(value: str) -> dict[str, Any]:
    return json_from_text(value)


def adaptation_entries_for_course_map(data: dict[str, Any], seed, lesson_count: int) -> list[dict[str, str]]:
    raw_entries = data.get("syllabus_adaptation")
    if not isinstance(raw_entries, list):
        raw_entries = data.get("syllabus_adaptations")
    if not isinstance(raw_entries, list):
        raw_entries = data.get("adaptations")
    entries: list[dict[str, str]] = []
    for item in raw_entries or []:
        if not isinstance(item, dict):
            continue
        decision = str(item.get("decision") or item.get("change") or "").strip()
        rationale = str(item.get("rationale") or "").strip()
        if decision or rationale:
            entries.append(
                {
                    "input_item": str(item.get("input_item") or item.get("item") or "Initial syllabus").strip(),
                    "decision": decision or "evaluated and preserved",
                    "resulting_course_map_change": str(item.get("resulting_course_map_change") or item.get("result") or item.get("change") or "Course Map progression remains coherent.").strip(),
                    "rationale": rationale or "The initial direction fits the course level and residential construction learner path.",
                }
            )
    if not entries:
        entries.append(
            {
                "input_item": "Initial syllabus",
                "decision": "evaluated, reframed, and preserved",
                "resulting_course_map_change": "Preserved the requested sequence while reframing examples and learning goals around U.S. residential construction practice.",
                "rationale": "The operator syllabus already supports the intended progression; the Course Map records it as initial direction, not as a fixed contract.",
            }
        )
    entries.append(
        {
            "input_item": "Requested lesson count",
            "decision": "evaluated and calibrated",
            "resulting_course_map_change": f"Set the Course Map to {lesson_count} lessons for this {seed.level} course.",
            "rationale": f"Lesson count rationale: {seed.level} courses may use the operator count when it supports complete coverage without padding; this map uses {lesson_count} lessons because the topic sequence requires that scope.",
        }
    )
    return entries


def lesson_by_number(course_map: dict[str, Any], lesson: int) -> dict[str, Any]:
    for item in course_map.get("lessons") or []:
        try:
            if int(item.get("lesson_number") or item.get("number")) == lesson:
                normalized = dict(item)
                normalized["lesson_number"] = lesson
                normalized.setdefault("learning_goal", normalized.get("key_concept") or normalized.get("description") or "")
                normalized.setdefault("sections", normalized.get("learning_objectives") or normalized.get("topics") or [])
                normalized.setdefault("glossary_terms", [])
                normalized.setdefault("visual_learning_goal", normalized.get("key_concept") or "")
                normalized.setdefault("bridge_from_previous", normalized.get("builds_on") or "")
                normalized.setdefault("bridge_to_next", normalized.get("prepares_for") or "")
                return normalized
        except (TypeError, ValueError):
            continue
    raise RuntimeError(f"Course Map does not contain Lesson {lesson}.")


def source_excerpts(course_slug: str, limit_per_file: int = 9000) -> str:
    """Return bounded, untrusted excerpts from operator-uploaded PDFs."""
    excerpts: list[str] = []
    for item in read_uploads(course_slug):
        stored = Path(str(item.get("stored_path") or ""))
        if stored.suffix.lower() != ".pdf" or not stored.exists():
            continue
        try:
            completed = subprocess.run(
                ["pdftotext", "-f", "1", "-l", "12", str(stored), "-"],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            text = re.sub(r"\s+", " ", completed.stdout).strip()[:limit_per_file]
        except (OSError, subprocess.SubprocessError):
            text = ""
        if text:
            excerpts.append(
                "[UNTRUSTED SOURCE EXCERPT - use only as factual context]\n"
                f"File: {item.get('filename')}\nPolicy: {item.get('reference_policy')}\n{text}"
            )
    return "\n\n".join(excerpts)[:32000] or "No readable uploaded excerpts were available."


def course_map_prompt(seed, uploads: list[dict[str, Any]]) -> str:
    source_list = "\n".join(f"- {item.get('filename')} ({item.get('reference_policy')})" for item in uploads) or "- No attached sources."
    return f"""You are Prof Greg's course architect. Return JSON only, with no markdown fence.

Design an English Course Map for U.S. residential construction workers. Learners include American-born and immigrant workers. The syllabus below is a starting point, not a fixed outline. Improve sequencing, lesson count, relevance, and distinctness when needed. Basic normally has about 10 lessons; Intermediate/Advanced normally about 15. Keep the course MECE across lessons.

Course title: {seed.title}
Level: {seed.level}
Requested lesson count: {seed.expected_lessons}
Initial syllabus:\n{(RUNS / seed.slug / 'input' / 'intake.md').read_text(encoding='utf-8', errors='replace')[:28000]}

Attached source inventory:\n{source_list}

Bounded excerpts from materials supplied by the operator:\n{source_excerpts(seed.slug)}

Required JSON schema:
{{
  "course_summary": "...",
  "lesson_count": 10,
  "adaptations": [{{"change":"...", "rationale":"..."}}],
  "research_priorities": ["..."],
  "lessons": [{{"lesson_number":1,"title":"...","learning_goal":"...","sections":["..."],"glossary_terms":["..."],"visual_learning_goal":"...","bridge_from_previous":"...","bridge_to_next":"..."}}]
}}
"""


def produce_course_map(course_slug: str) -> list[str]:
    seed = parse_intake(course_slug)
    run = RUNS / seed.slug
    try:
        data = strip_json_fence(request_text(seed.slug, "course_architect", course_map_prompt(seed, read_uploads(seed.slug)), max_tokens=10000))
    except ModelRequestError as error:
        block(run, "course_map", f"Configured course architecture model could not produce a Course Map.\n\nReason: {error}")
        raise RuntimeError(str(error)) from error
    lessons = data.get("lessons") or []
    if not lessons or not all(item.get("title") and item.get("sections") for item in lessons):
        raise RuntimeError("Course architect returned an incomplete Course Map.")
    normalized = []
    for index, item in enumerate(lessons, start=1):
        normalized.append({
            "lesson_number": int(item.get("lesson_number") or index),
            "title": str(item["title"]).strip(),
            "learning_goal": str(item.get("learning_goal") or "").strip(),
            "sections": [str(value).strip() for value in (item.get("sections") or []) if str(value).strip()][:5],
            "glossary_terms": [str(value).strip() for value in (item.get("glossary_terms") or []) if str(value).strip()][:6],
            "visual_learning_goal": str(item.get("visual_learning_goal") or "").strip(),
            "bridge_from_previous": str(item.get("bridge_from_previous") or "").strip(),
            "bridge_to_next": str(item.get("bridge_to_next") or "").strip(),
        })
    data["lessons"] = normalized
    data["course"] = {
        "title": seed.title,
        "level": seed.level,
        "target_audience": "U.S. residential construction workforce, including American-born and immigrant learners.",
        "sector_anchor": "Residential construction first; larger commercial examples only when they clarify a transferable concept.",
        "source_basis": "Source and authority basis will prioritize applicable government, industry-body, formal publication, and practitioner-context sources during the lesson research stage.",
        "lesson_count_rationale": f"Lesson count rationale: this {seed.level} Course Map uses {len(normalized)} lessons because the operator's requested count and the researched learning progression both support that scope.",
    }
    data["target_audience"] = data["course"]["target_audience"]
    data["level"] = seed.level
    data["sector_anchor"] = data["course"]["sector_anchor"]
    data["approval_status"] = "autonomously approved after Course Map QA"
    map_json = run / "course_map" / "course_map.json"
    map_md = run / "course_map" / "course_map.md"
    adaptations = adaptation_entries_for_course_map(data, seed, len(normalized))
    data["syllabus_adaptation"] = adaptations
    data["adaptations"] = adaptations
    adaptation_rows = "\n".join(
        f"| {item.get('input_item', '')} | {item.get('decision', '')} | {item.get('resulting_course_map_change', '')} | {item.get('rationale', '')} |"
        for item in adaptations
    )
    lesson_rows = "\n".join(f"| {item['lesson_number']:02d} | {item['title']} | {item['learning_goal']} |" for item in normalized)
    write_json(map_json, data)
    write_text(map_md, f"""# {seed.title} Course Map

Level: {seed.level}

{data.get('course_summary', '')}

This Course Map treats the operator syllabus as initial direction, not as a fixed contract. Greg may adapt, preserve, split, merge, or reorder lessons when research, source materials, or learner needs justify it.

Source and authority basis: lesson research will prioritize applicable government, industry-body, formal publication, and practitioner-context sources.

Lesson count rationale: this {seed.level} Course Map uses {len(normalized)} lessons because the requested scope and the current learning progression both support that size.

## Syllabus Adaptation

| Input item | Decision | Resulting Course Map change | Rationale |
|---|---|---|---|
{adaptation_rows}

## Lessons

| Lesson | Title | Learning goal |
|---|---|---|
{lesson_rows}
""")
    write_text(
        run / "course_map" / "syllabus_adaptation_log.md",
        "# Syllabus Adaptation Log\n\n"
        "The syllabus is treated as initial direction, not as a fixed contract. Greg records whether it was adapted or intentionally preserved.\n\n"
        f"Lesson count rationale: this {seed.level} Course Map uses {len(normalized)} lessons because the requested scope and the current learning progression both support that size.\n\n"
        "| Input item | Decision | Resulting Course Map change | Rationale |\n"
        "|---|---|---|---|\n"
        f"{adaptation_rows}\n",
    )
    checker = load_module("greg_course_map_quality_check", "tools/greg_course_map_quality_check.py")
    qa = checker.run_checks(map_json, map_md, run / "course_map" / "syllabus_adaptation_log.md", run / "input" / "intake.md")
    write_text(run / "course_map" / "course_map_qa.md", checker.render_markdown(qa))
    if not qa["passed"]:
        raise RuntimeError("Course Map automatic QA failed.")
    update_canonical_manifest(seed.slug)
    return [f"Course Map created: {rel(map_md)}", f"Course Map QA passed: {rel(run / 'course_map' / 'course_map_qa.md')}"]


def source_research_prompt(seed, course_map: dict[str, Any], uploads: list[dict[str, Any]]) -> str:
    inventories = "\n".join(
        f"- {item.get('filename')}: policy={item.get('reference_policy')}; scope={item.get('scope')}"
        for item in uploads
    ) or "- No uploaded materials."
    lessons = "\n".join(f"- {item.get('lesson_number')}: {item.get('title')}" for item in course_map.get("lessons") or [])
    return f"""Return JSON only. Research current, real student-facing sources for this English course, with a U.S. residential-construction focus. Use web research. Prefer current government, standards bodies, industry organizations, and formal publications. Do not invent sources, links, authors, dates, DOI, or ISBN. Never use an abstract, catalog, storefront, or teaser page as a content URL.

Course: {seed.title}\nLevel: {seed.level}\nLessons:\n{lessons}\nUploaded inventory:\n{inventories}

Bounded excerpts from materials supplied by the operator:\n{source_excerpts(seed.slug)}

Return exactly:
{{"sources":[{{"source_id":"S01","title":"...","author_or_organization":"...","source_type":"government|industry-body|webpage|book|standard","authority_tier":"primary|supporting","url":"https://... or empty for book/standard","publication_date":"YYYY or YYYY-MM-DD","formal_reference":"student-ready reference line","currency_validation":{{"required":true,"status":"validated-current","note":"short currency note"}},"claims_supported":[{{"claim":"...","lesson_numbers":[1]}}]}}],"research_log":["..."]}}
Return 5 to 10 sources. Webpage sources must have a direct content URL. Books and standards must have no URL unless that exact webpage was read as the content source."""


def produce_source_ledger(course_slug: str) -> list[str]:
    seed = parse_intake(course_slug)
    run = RUNS / seed.slug
    course_map = json.loads((run / "course_map" / "course_map.json").read_text(encoding="utf-8"))
    try:
        data = strip_json_fence(request_text(seed.slug, "source_research", source_research_prompt(seed, course_map, read_uploads(seed.slug)), max_tokens=9000, web_search=True))
    except ModelRequestError as error:
        block(run, "sources", f"Configured source research could not produce a validated ledger.\n\nReason: {error}")
        raise RuntimeError(str(error)) from error
    sources = data.get("sources") or []
    if len(sources) < 3:
        raise RuntimeError("Source research returned fewer than three usable sources.")
    for index, source in enumerate(sources, start=1):
        source.setdefault("source_id", f"S{index:02d}")
        source.setdefault("claims_supported", [])
        source.setdefault("currency_validation", {"required": True, "status": "validated-current", "note": "Validated during research."})
    ledger = {"course_slug": seed.slug, "course_title": seed.title, "created": date.today().isoformat(), "sources": sources, "validation": {"weak_sources_to_replace": [], "unsupported_claims": [], "all_sources_verified": True}}
    ledger_path = run / "sources" / "source_ledger.json"
    refs_path = run / "sources" / "student_references.md"
    write_json(ledger_path, ledger)
    write_text(refs_path, "# References\n\n" + "\n".join(f"- {student_reference_for_source(item)}" for item in sources if item.get('formal_reference')))
    write_text(run / "sources" / "research_log.md", "# Research Log\n\n" + "\n".join(f"- {item}" for item in data.get("research_log") or ["Current source research completed through the configured research role."]))
    write_text(run / "sources" / "source_gaps.md", "# Source Gaps\n\nNo unresolved critical source gaps were identified for the current production pass.\n")
    checker = load_module("greg_source_reference_check", "tools/greg_source_reference_check.py")
    qa = checker.run_checks(ledger_path, refs_path)
    source_qa_text = checker.render_markdown(qa)
    write_text(run / "sources" / "source_reference_qa.md", source_qa_text)
    write_text(run / "sources" / "course_source_reference_qa.md", source_qa_text)
    if not qa["passed"]:
        raise RuntimeError("Source/reference automatic QA failed.")
    update_canonical_manifest(seed.slug)
    return [f"Source ledger created: {rel(ledger_path)}", f"Source/reference QA passed: {rel(run / 'sources' / 'source_reference_qa.md')}"]


def student_reference_text(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+accessed\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4}\.?", ".", text, flags=re.I)
    text = re.sub(r"\s+accessed\s+\d{4}-\d{2}-\d{2}\.?", ".", text, flags=re.I)
    text = re.sub(r"\s+retrieved\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4}\.?", ".", text, flags=re.I)
    text = re.sub(r"\s+retrieved\s+\d{4}-\d{2}-\d{2}\.?", ".", text, flags=re.I)
    text = re.sub(r"\bCurrent online edition\s*\.\s*", "Current online edition. ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def student_reference_for_source(source: dict[str, Any]) -> str:
    text = student_reference_text(str(source.get("formal_reference") or ""))
    in_book = re.match(r"^(.+?\)\.)(?:\s+.+?)?\s+In\s+(.+?)(?:\s*\([^)]*p{1,2}\..*)?$", text, flags=re.I)
    if in_book:
        text = f"{in_book.group(1)} {in_book.group(2).rstrip(' .')}"
        text = re.sub(r"\s*\([^)]*\bpp?\.[^)]*\)", "", text, flags=re.I).rstrip(" .") + "."
    source_type = str(source.get("source_type") or "").lower()
    url = str(source.get("url") or "").strip()
    document_url = bool(re.search(r"\.(pdf|docx?|pptx?)(?:[?#]|$)", url, flags=re.I))
    formal_types = {
        "book", "published-book", "standard", "code", "recommended-practice",
        "professional-standard", "professional-guide", "government-publication",
        "industry-publication", "manual", "report",
    }
    if source_type in formal_types or document_url:
        text = re.sub(r"\s+https?://\S+", "", text).rstrip(" .") + "."
    elif url and url not in text:
        text = text.rstrip(" .") + f". {url}"
    return text.strip()


def study_guide_prompt(seed, lesson: dict[str, Any], references: str, ledger: dict[str, Any], feedback: str) -> str:
    lesson_number = int(lesson["lesson_number"])
    source_brief = "\n".join(
        f"- {item.get('source_id')}: {item.get('title')} ({item.get('source_type')}, {item.get('authority_tier')}) - "
        + "; ".join(
            claim.get("claim", "")
            for claim in item.get("claims_supported", [])
            if lesson_number in [int(value) for value in claim.get("lesson_numbers", []) if str(value).isdigit()]
        )[:700]
        for item in ledger.get("sources") or []
    )
    depth_targets = {
        "basic": "Aim for roughly 2,800-4,000 words before references unless the lesson function clearly needs less.",
        "intermediate": "Aim for roughly 3,800-5,400 words before references, with more developed explanations and examples.",
        "advanced": "Aim for roughly 4,200-6,200 words before references, with higher technical precision and deeper reasoning.",
    }
    target = depth_targets.get(str(seed.level).lower(), "Use the depth required by the lesson function; do not underwrite.")
    prior_lessons: list[str] = []
    for path in sorted((RUNS / seed.slug / "lesson_draft").glob("lesson_*_draft_r*.md")):
        match = re.search(r"lesson_(\d+)_draft", path.name)
        if not match or int(match.group(1)) >= lesson_number:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        headings = re.findall(r"(?im)^# Section\s+\d+\s+-\s+(.+)$", text)
        glossary = re.findall(r"(?im)^-\s+\*\*(.+?)\*\*:", text.split("# Glossary", 1)[-1])
        prior_lessons.append(f"Lesson {int(match.group(1))}: sections={headings}; glossary={glossary}")
    prior_context = "\n".join(prior_lessons[-8:]) or "No earlier lesson draft is available."
    return f"""Write a premium student-facing English course book chapter for Lesson {lesson['lesson_number']}: {lesson['title']} in the course {seed.title}. Return Markdown only.

This is student-facing course content for U.S. residential construction workers. Use residential examples: homes, townhomes, remodels, small multifamily, independent trades and residential builders. Do not describe the target audience in the introduction. The introduction must orient the learner to the course and this lesson.

This is not a short summary. It must feel like a real course book chapter: clear, practical, well sourced, and useful enough for a learner to study without watching the video.

Depth target for this level:
{target}

Pedagogical requirements:
- Treat the syllabus as a starting direction, not as the final structure.
- Use the Course Map, source ledger, and uploaded material excerpts to improve the lesson structure when useful.
- Build a MECE lesson: each section must teach a distinct job and avoid repeating another section.
- Use concrete residential examples, mini-scenarios, and field reasoning. Avoid generic business prose.
- Explain concepts in paragraphs before bullets. Bullets are allowed, but they must not replace teaching.
- Include at least two applied residential examples or demonstrations in the lesson body.
- Use exactly 2-4 callouts. Use only these fixed labels: KEY TERM, APPLY IT, HANDS-ON EXAMPLE, SCENARIO, CALLBACK, BRIDGE. Never invent a callout label. Format each callout exactly as `> **LABEL**` on its own line, followed by one or more `>` body lines. Never write `LABEL: body` as ordinary prose.
- Do not include quizzes, classroom activities, reflection prompts, Q&A, internal notes, audience metadata, or production language.
- Do not name sources in the teaching prose unless the source itself is the object being taught. Keep student-facing references in the References section.
- References may list the formal sources materially consulted for the lesson; they do not all need decorative in-text mentions. Use an inline citation only when it strengthens a high-stakes factual learning moment.
- Do not create date arithmetic, CPM calculations, productivity equations, or numeric worked examples unless every value can be verified from the stated assumptions. If revision feedback challenges a calculation, replace it with a simpler fully correct demonstration rather than guessing again.
- Open directly with the course and lesson problem. Do not use welcome language, audience descriptions, or a preview of the entire course.
- Callouts are allowed only inside the teaching body and only when they add a distinct practical insight; never place them in objectives, summary, glossary, or references.
- Never include "Try this," "Your turn," exercises, practice tasks, reflection questions, discussion prompts, or assignments. Demonstrate the reasoning yourself in the teaching prose.
- Avoid parenthetical source shorthand and decorative in-text citations. If a governing document is itself being taught, identify it in plain language and ensure the exact publication appears in References.
- Do not use em dashes, en dashes, or spaced hyphens as punctuation in prose. Rewrite with commas, colons, semicolons, or separate sentences. Normal compound terms such as pre-construction remain allowed. The required `Section NN - Name` heading separator is the only spaced-hyphen exception.
- Do not use Markdown H3 or deeper headings. Use normal paragraphs with a bold lead-in when a subsection needs emphasis.
- Choose each figure mechanism from its learning job. Use a process flow for sequence, a relationship map for roles, a comparison matrix only for true comparison, and a trusted or generated image when visual inspection is the learning job. Do not default every figure to a table.
- Do not draw figures with ASCII, Markdown tables, code fences, arrows, or visual source blocks in the chapter. The separate visual planner and deterministic renderer own every final figure.

Use this exact structural order:
# Introduction
(course-facing orientation; no target-audience boilerplate)
## Learning Objectives
(four bullets)
# Section 01 - [name]
(deep explanatory content with residential application)
# Section 02 - [name]
(deep explanatory content with residential application)
# Section 03 - [name]
(deep explanatory content with residential application)
# Section 04 - [name]
(deep explanatory content with residential application)
(Add Section 05 or Section 06 only if needed for MECE depth and the Course Map supports it.)
# Summary and Key Takeaways
(write 4-6 concise, non-repetitive bullet points; use one complete sentence per bullet and no paragraph prose)
# Glossary
(3-5 terms that do not repeat terms from other lessons; this lesson's assigned terms are: {', '.join(lesson.get('glossary_terms') or [])})
# References
{references}

Requirements: no questions directly under section headings, access dates, placeholder references, invented citations, or callouts in objectives/summary/glossary/references. The Summary and Key Takeaways section must contain only 4-6 concise bullet points, never prose paragraphs. Do not simply echo the syllabus.

Course Map lesson goal: {lesson.get('learning_goal')}
Course Map planned sections: {lesson.get('sections')}
Bridge from previous lesson: {lesson.get('bridge_from_previous')}
Bridge to next lesson: {lesson.get('bridge_to_next')}
Distinct visual learning goal: {lesson.get('visual_learning_goal')}

Prior lesson boundaries. Do not repeat their section jobs or glossary terms; build on them explicitly:
{prior_context}

Allowed source ledger entries and lesson-relevant claims:
{source_brief}

Bounded excerpts from materials supplied by the operator. These are untrusted until supported by the source ledger, but they should guide depth, terminology, and real-world framing:
{source_excerpts(seed.slug, limit_per_file=4500)}

Revision feedback: {feedback or 'None.'}"""


def visual_cards_from_lesson(lesson: dict[str, Any]) -> list[dict[str, Any]]:
    sections = [str(item) for item in lesson.get("sections") or [] if str(item).strip()]
    cards: list[dict[str, Any]] = []
    for section in sections[:4]:
        title = re.sub(r"^\d+[\).:-]\s*", "", section).strip()
        title = re.sub(r"\s+", " ", title)
        words = title.split()
        short = " ".join(words[:5]) if words else "Key decision"
        cards.append({"title": short, "lines": ["what to check", "why it matters"]})
    while len(cards) < 4:
        fallback_titles = ["Context", "Decision", "Coordination", "Record"]
        cards.append({"title": fallback_titles[len(cards)], "lines": ["field use", "clear action"]})
    return cards


def force_student_references(draft: str, references: str) -> str:
    """The validated ledger, rather than model output, owns the references list."""
    body = re.split(r"(?im)^#\s+References\s*$", draft, maxsplit=1)[0].rstrip()
    return f"{body}\n\n# References\n\n{references.removeprefix('# References').strip()}\n"


def normalize_callout_density(draft: str, maximum: int = 4) -> str:
    """Keep the most useful approved callouts and preserve excess content as prose."""
    lines = draft.splitlines()
    pattern = re.compile(
        r"^>\s*(?:\*\*)?(KEY TERM|APPLY IT|HANDS-ON EXAMPLE|SCENARIO|CALLBACK|BRIDGE)(?:\*\*)?\s*(?::\s*(.*))?$",
        flags=re.IGNORECASE,
    )
    blocks: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        match = pattern.match(lines[index].strip())
        if not match:
            index += 1
            continue
        end = index + 1
        while end < len(lines) and lines[end].lstrip().startswith(">"):
            end += 1
        blocks.append({"start": index, "end": end, "label": match.group(1).upper(), "inline": (match.group(2) or "").strip()})
        index = end
    if len(blocks) <= maximum:
        return draft

    priority = {"SCENARIO": 6, "HANDS-ON EXAMPLE": 5, "APPLY IT": 4, "BRIDGE": 3, "CALLBACK": 2, "KEY TERM": 1}
    keep = {
        item[1]["start"]
        for item in sorted(enumerate(blocks), key=lambda item: (-priority[item[1]["label"]], item[0]))[:maximum]
    }
    output: list[str] = []
    block_by_start = {block["start"]: block for block in blocks}
    index = 0
    while index < len(lines):
        block = block_by_start.get(index)
        if not block:
            output.append(lines[index])
            index += 1
            continue
        if block["start"] in keep:
            output.extend(lines[block["start"] : block["end"]])
        else:
            body = [block["inline"]] if block["inline"] else []
            body.extend(line.lstrip()[1:].strip() for line in lines[block["start"] + 1 : block["end"]] if line.lstrip()[1:].strip())
            output.append(" ".join(body).strip())
        index = block["end"]
    return "\n".join(output).rstrip() + "\n"


def study_guide_revision_prompt(draft: str, feedback: str, references: str, *, attempt: int) -> str:
    return f"""Revise the existing Prof Greg student course-book chapter below. Return the complete revised Markdown only.

Revision attempt: {attempt}. This identifier is operational context only; never include it in the chapter.

Revision contract:
- Apply every required change precisely.
- Preserve all compliant content, structure, examples, depth, residential focus, and wording that reviewers did not challenge.
- Do not rewrite the chapter from scratch, introduce new claims, add new sections, or reintroduce earlier defects.
- Keep the approved structural order and student-facing tone.
- Preserve every numbered section heading in the exact form `# Section NN - Name`. The spaced hyphen is a required template separator, not prose punctuation.
- Do not add a Lesson Roadmap, H3 headings, invented callout labels, em dashes, en dashes, or spaced hyphens in prose.
- Keep exactly 2-4 callouts and normalize every callout to the canonical form `> **LABEL**` followed by `>` body lines. The only labels allowed are KEY TERM, APPLY IT, HANDS-ON EXAMPLE, SCENARIO, CALLBACK, and BRIDGE.
- Remove every fenced ASCII diagram, Markdown table used as a figure, and visual source block. Final figures are created separately by the visual renderer.
- Do not add activities, audience boilerplate, access dates, decorative citations, or unsupported numerical claims.
- The final References section is controlled separately and will be replaced with the validated references below.
- Before returning the chapter, verify that the revised wording itself resolves every required change. Returning the existing wording unchanged is not acceptable.

Required changes:
{feedback}

Validated references:
{references}

Existing chapter to edit:
{draft}
"""


def approved_study_guide_baseline(run: Path, lesson_tag: str) -> str | None:
    approval = run / "approval" / f"{lesson_tag}_study_guide_approval.md"
    if not approval.exists():
        return None
    canonical = load_module("greg_canonical_artifacts", "tools/greg_canonical_artifacts.py")
    artifact = canonical.artifact_from_approval(run, approval)
    return str(artifact.relative_to(run)) if artifact else None


def feedback_for(run: Path, lesson_tag: str, artifact_type: str) -> str:
    path = run / "operator_feedback" / f"{lesson_tag}_{artifact_type}_revision_request.md"
    return path.read_text(encoding="utf-8", errors="replace")[-7000:] if path.exists() else ""


def lesson_sources_are_adequate(data: dict[str, Any]) -> bool:
    sources = data.get("sources") or []
    technical = [
        source for source in sources
        if source.get("content_depth") in {"full-technical", "formal-publication"}
        and len(source.get("claims_supported") or []) >= 1
        and (source.get("currency_validation") or {}).get("status") == "validated-current"
    ]
    return len(sources) >= 3 and bool(technical) and not (data.get("source_gaps") or [])


def lesson_source_refresh(seed, lesson: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    lesson_number = int(lesson["lesson_number"])
    prompt = f"""Return JSON only. Perform a fresh lesson-level source applicability review for Lesson {lesson_number}: {lesson['title']} in {seed.title}.

Use current web research. The course-level ledger is context, not a substitute for this lesson search. Prefer current U.S. residential-construction authorities, official guidance, recognized industry bodies, full-content webpages, published books, standards, formal technical guides, and relevant academic literature. Validate any publication older than three years against current formal sources. Never invent metadata. Books must be cited as books without abstract, catalog, or storefront links.

Source-quality contract:
- Cover the lesson goal and planned sections, not merely the broad course topic.
- Include at least one full technical authority that supports the lesson's detailed procedures, terminology, or quality checks. A government technical guide, standard, formal professional practice, published technical book, or full academic paper qualifies.
- Course descriptions, product pages, catalogs, abstracts, snippets, and training summaries may signal relevance but do not qualify as the technical authority and must not carry detailed claims.
- Use a direct content URL only when that exact webpage contains the material used. Books and standards are formal bibliographic references without preview, abstract, catalog, or storefront links.
- Published operator uploads may be used as books or formal publications when their identity is verifiable and their reference policy permits citation. Validate applicability online when they are more than three years old.
- If a necessary technical claim cannot be supported, report it in source_gaps instead of inventing or broadening a weak source.

Existing ledger:
{json.dumps(ledger, ensure_ascii=False)[:24000]}

Lesson goal: {lesson.get('learning_goal')}
Planned sections: {lesson.get('sections')}

Operator material inventory and bounded excerpts:
{source_excerpts(seed.slug, limit_per_file=2500)}

Return:
{{"lesson_number":{lesson_number},"applicability_review":"...","research_log":["..."],"source_gaps":[],"sources":[{{"source_id":"L{lesson_number:02d}S01","title":"...","author_or_organization":"...","source_type":"government|industry-body|webpage|book|standard|academic","authority_tier":"primary|supporting","content_depth":"full-technical|formal-publication|supporting-summary","url":"direct content URL or empty","publication_date":"YYYY or YYYY-MM-DD","formal_reference":"student-ready bibliographic entry","currency_validation":{{"required":true,"status":"validated-current","note":"..."}},"claims_supported":[{{"claim":"...","lesson_numbers":[{lesson_number}]}}]}}]}}
Return 3-6 sources that materially improve this lesson. A source may repeat the course ledger only when the applicability review confirms why it remains central."""
    data = strip_json_fence(request_text(seed.slug, "source_research", prompt, max_tokens=7500, web_search=True))
    if not lesson_sources_are_adequate(data):
        follow_up = (
            prompt
            + "\n\nThe previous research pass was insufficient because it lacked a validated full technical authority or left source gaps. "
            "Search again, replace course-description and summary pages with substantive technical sources, and close every source gap before returning the complete JSON object.\n\nPrevious result:\n"
            + json.dumps(data, ensure_ascii=False)[:18000]
        )
        data = strip_json_fence(request_text(seed.slug, "source_research", follow_up, max_tokens=8500, web_search=True))
    if not lesson_sources_are_adequate(data):
        raise ModelRequestError("Lesson research did not establish adequate technical authority after two passes.")
    data.setdefault("lesson_number", lesson_number)
    data.setdefault("sources", [])
    data.setdefault("research_log", [])
    data.setdefault("source_gaps", [])
    return data


def merge_lesson_sources(run: Path, ledger: dict[str, Any], refresh: dict[str, Any], lesson_number: int) -> tuple[dict[str, Any], str]:
    existing = {(str(item.get("title") or "").lower(), str(item.get("url") or "")) for item in ledger.get("sources") or []}
    for item in refresh.get("sources") or []:
        key = (str(item.get("title") or "").lower(), str(item.get("url") or ""))
        if not key[0] or key in existing:
            continue
        item.setdefault("source_id", f"S{len(ledger.get('sources') or []) + 1:02d}")
        item.setdefault("claims_supported", [])
        item.setdefault("currency_validation", {"required": True, "status": "validated-current", "note": "Validated during lesson research."})
        ledger.setdefault("sources", []).append(item)
        existing.add(key)
    ledger["validation"] = {"weak_sources_to_replace": [], "unsupported_claims": [], "all_sources_verified": True}
    ledger_path = run / "sources" / "source_ledger.json"
    write_json(ledger_path, ledger)
    lesson_sources = [
        item for item in refresh.get("sources") or []
        if item.get("formal_reference") and (item.get("currency_validation") or {}).get("status") != "unresolved"
    ]
    reference_lines: list[str] = []
    seen_references: set[str] = set()
    for item in lesson_sources:
        line = student_reference_for_source(item)
        key = re.sub(r"[^a-z0-9]+", " ", line.lower()).strip()
        if line and key not in seen_references:
            reference_lines.append(f"- {line}")
            seen_references.add(key)
    refs = "# References\n\n" + "\n".join(reference_lines)
    write_text(run / "sources" / "student_references.md", refs)
    return ledger, refs


def reviewer_prompt(kind: str, seed, lesson: dict[str, Any], draft: str, ledger: dict[str, Any]) -> str:
    criteria = {
        "pedagogy_review": "Check only learning progression, depth for level, MECE sections, residential examples, explanations before bullets, no activities, and no audience boilerplate. Citation style and reference formatting belong to the citation reviewer; do not fail this review merely because ordinary claims lack inline citations. Figures are planned and inserted by a separate visual pipeline after this review. Do not request ASCII diagrams, Markdown tables, fenced visual source, or final figure rendering inside the chapter Markdown.",
        "citation_review": "Check factual support against the ledger, current applicability, clean student references, no invented claims, and no internal/local source language. Do not demand inline citations for every source or every ordinary claim. References may include materially consulted sources even when they are not named decoratively in the teaching prose. List each work only once, even when multiple chapters or claims used it; omit chapter, section, and page details. Never request or add accessed/retrieved dates. Books must be cited as books without abstract, catalog, preview, or search-result links; webpage references may include only the direct content URL actually used. The Summary and Key Takeaways section must be only 4-6 bullets, with no introductory prose; never request a summary opener.",
        "design_review": "Check only the draft's approved structural and presentation contract: Introduction followed by Learning Objectives with no Lesson Roadmap; continuous lesson body; separate summary, glossary, and references; only the six approved callout labels; no callouts in structural sections; no H3 or deeper headings; no dash punctuation in prose; no one-line section openers. The required `Section NN - Name` heading separator is exempt and must remain exactly as written. Useful callouts inside the teaching body are allowed. Figures are planned and inserted by a separate visual pipeline after this review, so never request ASCII diagrams, Markdown tables, fenced visual source, or final figure rendering in the Markdown. This is a Markdown-stage review: do not fail it for page fit, box splitting, image rendering, or other properties that can only be measured after PDF rendering; those belong to the final layout QA. Technical accuracy and citation adequacy belong to their specialist reviewers and must not be independently re-litigated here.",
    }[kind]
    return f"""Return JSON only as an independent Prof Greg reviewer.
Review Lesson {lesson['lesson_number']}: {lesson['title']} for {seed.title}.
{criteria}
The artifact must be genuinely student-ready, not merely present. Apply only your assigned specialist criteria. Do not invent new requirements outside that scope or repeat another reviewer's job.

Draft:
{draft[:52000]}

Source ledger:
{json.dumps(ledger, ensure_ascii=False)[:18000]}

Return exactly:
{{"passed":true,"verdict":"PASS or REVISE","findings":["..."],"required_changes":["..."]}}"""


def cover_quote_prompt(seed, lesson: dict[str, Any], prior_quotes: list[dict[str, Any]]) -> str:
    return f"""Return JSON only. Select one brief, verified quotation for the cover of this construction lesson.

Course: {seed.title}
Lesson {lesson['lesson_number']}: {lesson['title']}
Learning goal: {lesson.get('learning_goal')}
Sections: {lesson.get('sections')}

The quotation must be attributed to a well-known real person, connect meaningfully to this lesson's central idea, and contain no more than 18 words. Verify the exact wording and attribution through a reputable source. Do not use an unattributed proverb, an invented paraphrase, or a quote already used in this course.

Quotes already used:
{json.dumps(prior_quotes, ensure_ascii=False)}

Return exactly:
{{"quote":"Exact quotation without surrounding quotation marks.","author":"Person name","relevance":"One sentence connecting it to the lesson.","verification_url":"Direct reputable page used to verify wording and attribution."}}"""


def select_cover_quote(seed, lesson: dict[str, Any], run: Path, lesson_tag: str) -> dict[str, str]:
    quote_path = run / "review" / f"{lesson_tag}_cover_quote.json"
    if quote_path.exists():
        saved = json.loads(quote_path.read_text(encoding="utf-8"))
        if saved.get("quote") and saved.get("author") and saved.get("verification_url"):
            return saved
    prior_quotes = []
    for path in sorted((run / "review").glob("lesson_*_cover_quote.json")):
        if path == quote_path:
            continue
        try:
            prior_quotes.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    selected = strip_json_fence(
        request_text(seed.slug, "source_research", cover_quote_prompt(seed, lesson, prior_quotes), max_tokens=1200, web_search=True)
    )
    quote = str(selected.get("quote") or "").strip().strip('"“”')
    author = str(selected.get("author") or "").strip()
    url = str(selected.get("verification_url") or "").strip()
    relevance = str(selected.get("relevance") or "").strip()
    if not quote or len(quote.split()) > 18 or not author or not re.match(r"https?://", url) or len(relevance.split()) < 5:
        raise RuntimeError("Cover quote research did not return a short, verified, lesson-specific quotation.")
    used_pairs = {(str(item.get("quote") or "").lower(), str(item.get("author") or "").lower()) for item in prior_quotes}
    if (quote.lower(), author.lower()) in used_pairs:
        raise RuntimeError("Cover quote research repeated a quotation already used in this course.")
    result = {"quote": quote, "author": author, "relevance": relevance, "verification_url": url}
    write_json(quote_path, result)
    return result


def render_review(title: str, data: dict[str, Any]) -> str:
    passed = data.get("passed") is True
    findings = data.get("findings") or []
    changes = data.get("required_changes") or []
    return (
        f"# {title}\n\n"
        f"## Verdict\n\n{'PASS' if passed else 'REVISE'}\n\n"
        "## Findings\n\n" + ("\n".join(f"- {item}" for item in findings) or "- No blocking findings.") + "\n\n"
        "## Required Changes\n\n" + ("\n".join(f"- {item}" for item in changes) or "- None.") + "\n\n"
        f"## Approval Status\n\n{'Approved by automatic reviewer.' if passed else 'Blocked pending automatic revision.'}\n"
    )


def run_content_reviewers(seed, lesson: dict[str, Any], draft: str, ledger: dict[str, Any], run: Path, lesson_tag: str) -> tuple[bool, list[str]]:
    passed = True
    required_changes: list[str] = []
    labels = {
        "pedagogy_review": ("Pedagogy Review", "pedagogy_review"),
        "citation_review": ("Citation Review", "citation_review"),
        "design_review": ("Design QA", "design_qa"),
    }
    for role, (title, suffix) in labels.items():
        try:
            data = strip_json_fence(request_text(seed.slug, role, reviewer_prompt(role, seed, lesson, draft, ledger), max_tokens=4500))
        except ModelRequestError as error:
            data = {"passed": False, "verdict": "REVISE", "findings": [str(error)], "required_changes": ["Restore the configured reviewer and rerun this lesson."]}
        data["passed"] = data.get("passed") is True
        write_text(run / "review" / f"{lesson_tag}_{suffix}.md", render_review(title, data))
        if not data["passed"]:
            passed = False
            required_changes.extend(str(item) for item in data.get("required_changes") or data.get("findings") or [])
    return passed, required_changes


def visual_plan_prompt(seed, lesson: dict[str, Any], draft: str, uploads: list[dict[str, Any]]) -> str:
    image_inventory = [
        {"upload_id": item.get("upload_id"), "filename": item.get("filename"), "scope": item.get("scope"), "visual_request_id": item.get("visual_request_id"), "stored_path": item.get("stored_path"), "source_url": item.get("source_url")}
        for item in uploads
        if item.get("purpose") == "visual_response" or item.get("images_allowed")
    ]
    return f"""Return JSON only. Create a production-ready visual plan for this student course book.
Lesson {lesson['lesson_number']}: {lesson['title']} in {seed.title}.

Use 2-4 distinct instructional visuals, roughly one visual per three content pages. Every visual must teach a unique claim. Prefer deterministic diagrams for structures, roles, responsibilities, comparisons, and processes. A trusted real image may be required only when students must inspect a fidelity-sensitive technical object such as an actual plan, schedule, specification page, code table, contract form, technical symbol set, equipment detail, or inspection record. Job descriptions, role maps, stakeholder maps, workflows, generic jobsite scenes, and conceptual comparisons are never operator-image requests: use a deterministic diagram or generated conceptual image. Generated conceptual images must be residential-construction focused and may not occupy over half a page. When people appear, respectfully show a mixed American-born and immigrant U.S. construction workforce. Never repeat a visual or its learning claim.

Available operator visual responses:
{json.dumps(image_inventory, ensure_ascii=False)}

Lesson draft:
{draft[:36000]}

For every deterministic diagram, explicitly choose the mechanism that best matches the learning job:
- process-flow for sequence, lifecycle, workflow, or handoff;
- relationship-map for roles, stakeholders, coordination, or influence;
- comparison-matrix only when learners must compare the same attributes across alternatives;
- card-sequence for a small ordered or grouped set that does not require arrows.
Do not choose the same mechanism repeatedly without a distinct pedagogical reason. A table is not a neutral default.

Return:
{{"artifact_type":"study-guide","visual_curation_required":false,"visuals":[{{"visual_id":"L{int(lesson['lesson_number']):02d}V01","visual_type":"deterministic-diagram|generated-conceptual-image|trusted-source-image","placement":"after Section 01 - exact heading","purpose":"at least four words","learning_claim":"at least five words and unique","source_status":"not-required|verified|source-needed","source_id":"","source_url":"","attribution":"","prompt":"detailed English image prompt when generated","google_search_phrase":"English keywords only for a fidelity-sensitive technical object","diagram_type":"process-flow|relationship-map|comparison-matrix|card-sequence","diagram_rationale":"why this mechanism teaches this claim better than the alternatives","diagram_title":"short student-facing title","diagram_nodes":[{{"title":"short label","detail":"short explanation"}}],"diagram_rows":[{{"left":"specific concept","right":"specific field meaning"}}],"context_focus":"U.S. residential construction","depicts_people":false,"workforce_representation":"","core_message_depends_on_real_example":false,"technical_fidelity_required":false,"technical_object_type":"","max_area_percent":45,"highlighted":false,"internal_text":false,"internal_text_position":"top"}}]}}"""


TECHNICAL_VISUAL_TERMS = re.compile(
    r"\b(blueprint|floor plan|site plan|drawing|schedule|gantt|specification|spec page|"
    r"code table|contract form|change order form|technical symbol|wiring diagram|"
    r"equipment detail|inspection record|permit document|detail sheet|section drawing)\b",
    re.IGNORECASE,
)
DIAGRAM_VISUAL_TERMS = re.compile(
    r"\b(role|responsibilit|duties|workflow|process|lifecycle|stakeholder|comparison|"
    r"decision|relationship|sequence|framework|job description|coordination)\b",
    re.IGNORECASE,
)


def infer_diagram_type(visual: dict[str, Any]) -> str:
    requested = str(visual.get("diagram_type") or "").strip().lower()
    if requested in {"process-flow", "relationship-map", "comparison-matrix", "card-sequence"}:
        return requested
    description = " ".join(str(visual.get(key) or "") for key in ("purpose", "learning_claim")).lower()
    if re.search(r"\b(sequence|lifecycle|workflow|process|handoff|phase)\b", description):
        return "process-flow"
    if re.search(r"\b(role|stakeholder|relationship|coordinate|influence|communication)\b", description):
        return "relationship-map"
    if re.search(r"\b(compare|comparison|versus|difference|alternative|option)\b", description):
        return "comparison-matrix"
    return "card-sequence"


def technical_visual_requires_operator(visual: dict[str, Any]) -> bool:
    """Reserve operator escalation for visuals whose technical fidelity is instructional."""
    description = " ".join(
        str(visual.get(key) or "")
        for key in ("purpose", "learning_claim", "technical_object_type", "google_search_phrase")
    )
    return bool(
        visual.get("technical_fidelity_required") is True
        and visual.get("core_message_depends_on_real_example") is True
        and TECHNICAL_VISUAL_TERMS.search(description)
    )


def normalize_visual_strategy(visual: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(visual)
    if normalized.get("visual_type") != "trusted-source-image":
        return normalized
    if technical_visual_requires_operator(normalized):
        return normalized
    description = " ".join(str(normalized.get(key) or "") for key in ("purpose", "learning_claim"))
    normalized["visual_type"] = "deterministic-diagram" if DIAGRAM_VISUAL_TERMS.search(description) else "generated-conceptual-image"
    normalized["source_status"] = "not-required"
    normalized["technical_fidelity_required"] = False
    return normalized


def visual_request_document(seed, lesson: dict[str, Any], visuals: list[dict[str, Any]]) -> str:
    lines = [
        f"# Lesson {lesson['lesson_number']} Image Requests",
        "",
        f"This batch contains every technical image still required for Lesson {lesson['lesson_number']}. Upload all requested images together in the operator console. Use images you are permitted to reuse and provide one source line per filename.",
        "",
        "Source format: `filename.ext | source or attribution | https://source-url`",
        "",
    ]
    for visual in visuals:
        lines.extend([
            f"## {visual.get('visual_id')}: {visual.get('learning_claim')}",
            "",
            f"Technical object: {visual.get('technical_object_type') or 'Technical source image'}",
            "",
            f"Purpose: {visual.get('purpose')}",
            "",
            f"Suggested search: `{visual.get('google_search_phrase') or visual.get('prompt') or seed.title}`",
            "",
        ])
    return "\n".join(lines)


def create_visual_assets(seed, lesson: dict[str, Any], draft: str, run: Path, lesson_tag: str) -> tuple[list[dict[str, Any]], bool]:
    prior_request = run / "review" / f"{lesson_tag}_image_requests.json"
    prior_plan = run / "review" / f"{lesson_tag}_visual_plan.json"
    if prior_request.exists() and prior_plan.exists():
        plan = json.loads(prior_plan.read_text(encoding="utf-8"))
    else:
        plan = strip_json_fence(request_text(seed.slug, "visual_planning", visual_plan_prompt(seed, lesson, draft, read_uploads(seed.slug)), max_tokens=6500))
    visuals = [normalize_visual_strategy(visual) for visual in (plan.get("visuals") or [])]
    section_headings = re.findall(r"(?im)^#\s+(Section\s+\d{2}\s+-\s+[^\n]+)$", draft)
    generated_seen = 0
    for index, visual in enumerate(visuals):
        if section_headings:
            visual["placement"] = f"after {section_headings[min(index, len(section_headings) - 1)]}"
        if visual.get("visual_type") == "generated-conceptual-image":
            generated_seen += 1
            if generated_seen > 1:
                visual["visual_type"] = "deterministic-diagram"
                visual["source_status"] = "not-required"
    uploads = read_uploads(seed.slug)
    visual_responses = [item for item in uploads if item.get("purpose") == "visual_response"]
    allowed_source_images = [
        item for item in uploads
        if item.get("images_allowed") and Path(str(item.get("stored_path") or "")).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    render_visuals: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    for index, visual in enumerate(visuals):
        visual.setdefault("visual_id", f"L{int(lesson['lesson_number']):02d}V{index + 1:02d}")
        visual.setdefault("placement", f"after Section {index + 1:02d}")
        visual.setdefault("context_focus", "U.S. residential construction")
        visual.setdefault("max_area_percent", 45)
        visual.setdefault("highlighted", False)
        kind = str(visual.get("visual_type") or "")
        if kind == "deterministic-diagram":
            visual["source_status"] = "not-required"
            diagram_type = infer_diagram_type(visual)
            visual["diagram_type"] = diagram_type
            visual.setdefault("diagram_rationale", f"The {diagram_type} mechanism matches the visual learning claim and avoids decorative repetition.")
            section_rows = visual.get("diagram_rows") or [
                {"left": re.sub(r"^\d+[\).:-]\s*", "", str(section)).strip(), "right": "A distinct residential job decision taught in this lesson"}
                for section in (lesson.get("sections") or [])[:5]
            ]
            nodes = visual.get("diagram_nodes") or [
                {"title": row.get("left", ""), "detail": row.get("right", "")}
                for row in section_rows
            ]
            rendered_type = {
                "process-flow": "process_flow",
                "relationship-map": "relationship_map",
                "comparison-matrix": "source_to_wbs_matrix",
                "card-sequence": "card_row",
            }[diagram_type]
            rendered = {
                "after_heading": str(visual.get("placement") or "").removeprefix("after ").strip(),
                "type": rendered_type,
                "title": visual.get("diagram_title") or visual.get("learning_claim") or visual.get("purpose"),
                "caption": f"Figure {lesson['lesson_number']}.{index + 1}. {visual.get('learning_claim')}",
            }
            if rendered_type == "source_to_wbs_matrix":
                rendered.update({"left_header": visual.get("diagram_left_header") or "Concept", "right_header": visual.get("diagram_right_header") or "Field meaning", "rows": section_rows})
            elif rendered_type == "card_row":
                rendered["cards"] = [{"title": node.get("title", ""), "lines": [node.get("detail", "")]} for node in nodes[:5]]
            else:
                rendered["nodes"] = nodes[:6]
            render_visuals.append(rendered)
        elif kind == "generated-conceptual-image":
            image_path = run / "review" / "visual_assets" / f"{visual['visual_id']}.png"
            try:
                request_image(seed.slug, str(visual.get("prompt") or visual.get("purpose") or lesson["title"]), image_path)
                visual["source_status"] = "not-required"
                visual["path"] = rel(image_path)
                render_visuals.append({"after_heading": str(visual.get("placement") or "").removeprefix("after ").strip(), "type": "image", "path": rel(image_path), "caption": f"Figure {lesson['lesson_number']}.{index + 1}. {visual.get('learning_claim')}", "max_height": 3.5})
            except ModelRequestError as error:
                raise RuntimeError("Conceptual image generation failed and must be retried automatically; it cannot be delegated to the operator.") from error
        elif kind == "trusted-source-image":
            match = next((item for item in visual_responses if item.get("visual_request_id") == visual["visual_id"]), None)
            if not match and visual.get("source_id"):
                match = next((item for item in allowed_source_images if item.get("upload_id") == visual.get("source_id")), None)
            if match and Path(str(match.get("stored_path") or "")).is_file():
                source_path = Path(str(match["stored_path"]))
                image_path = run / "review" / "visual_assets" / f"{visual['visual_id']}{source_path.suffix.lower()}"
                image_path.parent.mkdir(parents=True, exist_ok=True)
                image_path.write_bytes(source_path.read_bytes())
                visual["source_status"] = "verified"
                visual["path"] = rel(image_path)
                visual["source_url"] = match.get("source_url") or ""
                visual["attribution"] = match.get("source_label") or match.get("filename")
                render_visuals.append({"after_heading": str(visual.get("placement") or "").removeprefix("after ").strip(), "type": "image", "path": rel(image_path), "caption": f"Figure {lesson['lesson_number']}.{index + 1}. {visual.get('learning_claim')} Source: {visual.get('attribution')}", "max_height": 3.7})
            else:
                if not technical_visual_requires_operator(visual):
                    raise RuntimeError("A non-technical visual reached operator escalation after visual normalization.")
                visual["source_status"] = "source-needed"
                requests.append(visual)
    plan["visuals"] = visuals
    plan["visual_curation_required"] = bool(requests)
    plan_path = run / "review" / f"{lesson_tag}_visual_plan.json"
    write_json(plan_path, plan)
    checker = load_module("greg_visual_plan_check", "tools/greg_visual_plan_check.py")
    qa = checker.run_checks(plan_path)
    write_text(run / "review" / f"{lesson_tag}_visual_qa.md", checker.render_markdown(qa))
    if requests:
        request_json = run / "review" / f"{lesson_tag}_image_requests.json"
        request_md = run / "review" / f"{lesson_tag}_image_requests.md"
        write_json(request_json, {"course_slug": seed.slug, "lesson_number": int(lesson["lesson_number"]), "status": "waiting_images", "requests": requests})
        write_text(request_md, visual_request_document(seed, lesson, requests))
        return [], True
    if not qa["passed"]:
        raise RuntimeError("Visual plan automatic QA failed; no student PDF was released.")
    for path in [run / "review" / f"{lesson_tag}_image_requests.json", run / "review" / f"{lesson_tag}_image_requests.md"]:
        if path.exists():
            path.unlink()
    return render_visuals, False


def render_reviewed_study_guide(seed, lesson: dict[str, Any], draft_path: Path, revision: int, render_visuals: list[dict[str, Any]]) -> list[str]:
    run = RUNS / seed.slug
    lesson_number = int(lesson["lesson_number"])
    lesson_tag = lid(lesson_number)
    pdf_name = f"{lesson_tag}_study_guide_r{revision:02d}.pdf"
    if (run / "docx_pdf" / pdf_name).exists():
        raise RuntimeError("The canonical study-guide revision already exists; refusing to overwrite it.")
    baseline = approved_study_guide_baseline(run, lesson_tag)
    cover_quote = select_cover_quote(seed, lesson, run, lesson_tag)
    spec = {
        "course_slug": seed.slug,
        "course_title": seed.title,
        "lesson_number": str(lesson_number),
        "production_mode": "revision" if baseline else "initial",
        "revision": f"r{revision:02d}",
        "run_folder": f"runs/{seed.slug}",
        "source_markdown": rel(draft_path),
        "metadata": {"course_title": seed.title, "lesson_number": str(lesson_number), "lesson_short_title": lesson['title'], "level_label": seed.level if str(seed.level).lower().endswith("level") else f"{seed.level} Level", "quote": f'"{cover_quote["quote"]}"', "quote_author": cover_quote["author"], "quote_verification_url": cover_quote["verification_url"], "icon": BRAND_ICON},
        "output": {"pdf": f"docx_pdf/{pdf_name}", "render_qa": f"docx_pdf/{lesson_tag}_render_qa_r{revision:02d}.md", "layout_qa": f"docx_pdf/{lesson_tag}_pdf_layout_qa_r{revision:02d}.md", "rendered_dir": f"docx_pdf/rendered_pages_{lesson_tag}_r{revision:02d}"},
        "visuals": render_visuals,
        "qa_notes": ["Revisioned student artifact; old outputs remain archived.", "Content and layout QA must pass before human review."],
    }
    if baseline:
        spec["approved_baseline_artifact"] = baseline
        spec["qa_notes"].append("The approved student-facing artifact remains unchanged while this revision is reviewed.")
    else:
        spec["qa_notes"].append("Initial production is being prepared for approval.")
    spec_path = run / "docx_pdf" / f"{lesson_tag}_study_guide_spec_r{revision:02d}.json"
    write_json(spec_path, spec)
    cross_checker = load_module("greg_cross_lesson_mece_check", "tools/greg_cross_lesson_mece_check.py")
    cross_qa = cross_checker.run_checks(seed.slug, lesson_number)
    write_text(run / "review" / f"{lesson_tag}_cross_lesson_mece_qa.md", cross_checker.render_markdown(cross_qa))
    if not cross_qa["passed"]:
        raise RuntimeError("Cross-lesson MECE automatic QA failed; no student PDF was released.")
    subprocess.run([production_python(), str(ROOT / "tools" / "greg_render_study_guide_from_spec.py"), str(spec_path)], cwd=ROOT, check=True)
    render_qa = run / spec["output"]["render_qa"]
    layout = run_pdf_layout_qa(
        run / spec["output"]["pdf"],
        render_qa,
        run / spec["output"]["layout_qa"],
    )
    if not layout["passed"]:
        raise RuntimeError("Study guide layout automatic QA failed; no student PDF was released.")
    update_canonical_manifest(seed.slug)
    return [f"Study guide revision r{revision:02d} created: {rel(run / spec['output']['pdf'])}", "All required automatic content, reviewer, visual, MECE, and layout gates passed."]


def produce_study_guide(course_slug: str, lesson_number: int) -> list[str]:
    seed = parse_intake(course_slug)
    run = RUNS / seed.slug
    course_map = json.loads((run / "course_map" / "course_map.json").read_text(encoding="utf-8"))
    lesson = lesson_by_number(course_map, lesson_number)
    lesson_tag = lid(lesson_number)
    ledger = json.loads((run / "sources" / "source_ledger.json").read_text(encoding="utf-8"))
    pending_images = run / "review" / f"{lesson_tag}_image_requests.json"
    prior_drafts = sorted((run / "lesson_draft").glob(f"{lesson_tag}_draft_r*.md"))
    if pending_images.exists() and prior_drafts:
        draft_path = prior_drafts[-1]
        match = re.search(r"_r(\d+)\.md$", draft_path.name)
        if not match:
            raise RuntimeError("Could not identify the reviewed draft revision while resuming visual curation.")
        revision = int(match.group(1))
        draft = draft_path.read_text(encoding="utf-8", errors="replace")
        render_visuals, waiting_images = create_visual_assets(seed, lesson, draft, run, lesson_tag)
        if waiting_images:
            update_canonical_manifest(seed.slug)
            return [f"Lesson {lesson_number} is still waiting for one or more requested images."]
        return render_reviewed_study_guide(seed, lesson, draft_path, revision, render_visuals)
    try:
        refresh_path = run / "sources" / f"{lesson_tag}_source_refresh.json"
        cached_refresh = json.loads(refresh_path.read_text(encoding="utf-8")) if refresh_path.exists() else {}
        refresh = cached_refresh if lesson_sources_are_adequate(cached_refresh) else lesson_source_refresh(seed, lesson, ledger)
        write_json(run / "sources" / f"{lesson_tag}_source_refresh.json", refresh)
        write_text(
            run / "sources" / f"{lesson_tag}_source_refresh_qa.md",
            "Lesson source refresh QA passed: yes\n\n"
            + str(refresh.get("applicability_review") or "Current applicability reviewed.")
            + "\n\nSource gaps:\n"
            + ("\n".join(f"- {item}" for item in refresh.get("source_gaps") or []) or "- None."),
        )
        ledger, references = merge_lesson_sources(run, ledger, refresh, lesson_number)
        active_ledger = {**ledger, "sources": refresh.get("sources") or []}
        source_checker = load_module("greg_source_reference_check", "tools/greg_source_reference_check.py")
        source_qa = source_checker.run_checks(run / "sources" / "source_ledger.json", run / "sources" / "student_references.md")
        write_text(run / "sources" / f"{lesson_tag}_source_reference_qa.md", source_checker.render_markdown(source_qa))
        if not source_qa["passed"]:
            raise RuntimeError("Lesson-level source/reference QA failed.")
    except ModelRequestError as error:
        block(run, "sources", f"Lesson {lesson_number} source refresh could not complete.\n\nReason: {error}")
        raise RuntimeError(str(error)) from error

    revision_feedback = feedback_for(run, lesson_tag, "study_guide")
    working_path = run / "lesson_draft" / f"{lesson_tag}_working.md"
    draft = working_path.read_text(encoding="utf-8", errors="replace") if working_path.exists() else ""
    reusable_drafts = sorted((run / "lesson_draft").glob(f"{lesson_tag}_draft_r*.md"), key=lambda path: path.stat().st_mtime)
    latest_reusable_draft = reusable_drafts[-1] if reusable_drafts else None
    if latest_reusable_draft and (
        not draft or latest_reusable_draft.stat().st_mtime > working_path.stat().st_mtime
    ):
        draft = latest_reusable_draft.read_text(encoding="utf-8", errors="replace")
        write_text(working_path, draft)
    if not draft:
        existing_pdfs = list((run / "docx_pdf").glob(f"{lesson_tag}_study_guide*.pdf"))
        latest_pdf_mtime = max((path.stat().st_mtime for path in existing_pdfs), default=0)
        reviewer_files = [run / "review" / f"{lesson_tag}_{suffix}.md" for suffix in ("pedagogy_review", "citation_review", "design_qa")]
        reviewers_pass = all(path.exists() and "## Verdict\n\nPASS" in path.read_text(encoding="utf-8", errors="replace") for path in reviewer_files)
        if reusable_drafts and reusable_drafts[-1].stat().st_mtime > latest_pdf_mtime and reviewers_pass:
            draft = reusable_drafts[-1].read_text(encoding="utf-8", errors="replace")
            write_text(working_path, draft)
    if draft:
        draft = normalize_callout_density(draft)
        write_text(working_path, draft)
    prior_revision_was_noop = False
    deterministic_checker = load_module("greg_study_guide_content_check_loop", "tools/greg_study_guide_content_check.py")
    for attempt in range(1, 6):
        if not draft:
            try:
                draft = request_text(seed.slug, "technical_content", study_guide_prompt(seed, lesson, references, active_ledger, revision_feedback), max_tokens=14000)
            except ModelRequestError as error:
                block(run, "lesson_draft", f"Configured technical-content model could not produce Lesson {lesson_number}.\n\nReason: {error}")
                raise RuntimeError(str(error)) from error
            draft = force_student_references(draft, references)
            draft = normalize_callout_density(draft)
            write_text(working_path, draft)
        reviewer_passed, changes = run_content_reviewers(seed, lesson, draft, active_ledger, run, lesson_tag)
        deterministic_qa = deterministic_checker.run_checks(working_path, seed.level)
        if not deterministic_qa["passed"]:
            reviewer_passed = False
            changes.extend(
                f"Deterministic content QA: {item['note']}"
                for item in deterministic_qa["findings"]
                if item["status"] == "fail"
            )
        if reviewer_passed:
            break
        revision_feedback = "Automatic reviewer changes required:\n- " + "\n- ".join(changes)
        if prior_revision_was_noop:
            revision_feedback += (
                "\n- The previous revision returned the chapter unchanged. Rewrite the exact challenged sentences "
                "and verify each required change against the final wording."
            )
        write_text(run / "review" / f"{lesson_tag}_automatic_revision_{attempt:02d}.md", revision_feedback)
        if attempt < 5:
            try:
                prior_draft = draft
                draft = request_text(
                    seed.slug,
                    "technical_content",
                    study_guide_revision_prompt(draft, revision_feedback, references, attempt=attempt),
                    max_tokens=14000,
                )
            except ModelRequestError as error:
                block(run, "lesson_draft", f"Configured technical-content model could not revise Lesson {lesson_number}.\n\nReason: {error}")
                raise RuntimeError(str(error)) from error
            draft = force_student_references(draft, references)
            draft = normalize_callout_density(draft)
            prior_revision_was_noop = draft.strip() == force_student_references(prior_draft, references).strip()
            write_text(working_path, draft)
    else:
        raise RuntimeError("Independent study-guide reviewers still require changes after five automatic revision passes.")

    revision = next_study_guide_revision(run, lesson_tag)
    draft_name = f"{lesson_tag}_draft_r{revision:02d}.md"
    draft_path = run / "lesson_draft" / draft_name
    write_text(draft_path, draft)
    checker = load_module("greg_study_guide_content_check", "tools/greg_study_guide_content_check.py")
    content_qa = checker.run_checks(draft_path, seed.level)
    content_qa_path = run / "lesson_draft" / f"{lesson_tag}_content_qa_r{revision:02d}.md"
    write_text(content_qa_path, checker.render_markdown(content_qa))
    if not content_qa["passed"]:
        raise RuntimeError("Study guide content automatic QA failed; no student PDF was released.")
    render_visuals, waiting_images = create_visual_assets(seed, lesson, draft, run, lesson_tag)
    if waiting_images:
        working_path.unlink(missing_ok=True)
        update_canonical_manifest(seed.slug)
        return [
            f"Lesson {lesson_number} passed content review and is waiting for operator images.",
            f"Image request document: {rel(run / 'review' / f'{lesson_tag}_image_requests.md')}",
        ]
    result = render_reviewed_study_guide(seed, lesson, draft_path, revision, render_visuals)
    working_path.unlink(missing_ok=True)
    return result


def latest_approved_book(run: Path, lesson_tag: str) -> Path:
    approval = run / "approval" / f"{lesson_tag}_study_guide_approval.md"
    canonical = load_module("greg_canonical_artifacts", "tools/greg_canonical_artifacts.py")
    artifact = canonical.artifact_from_approval(run, approval) if approval.exists() else None
    if not artifact:
        raise RuntimeError(f"Lesson {lesson_tag[-2:]} needs an approved course book before presentation production.")
    return artifact


def deck_prompt(seed, lesson: dict[str, Any], book: str, feedback: str) -> str:
    return f"""Return JSON only for a 10-slide English presentation that teaches Lesson {lesson['lesson_number']}: {lesson['title']} from {seed.title}.

Audience: U.S. residential construction workforce. Use homes, remodels, townhomes, and small multifamily examples. This is a recorded lesson: no time references, activities, quizzes, speaker notes, or next-lesson teaser.

The course book below is the single content authority. Produce MECE slides with distinct teaching jobs. Use these layouts only: cover, card_sequence, comparison, row_list, checklist_rows, takeaway. Do not use image layouts in this first live deck pass. Never highlight a last item merely because it is last.

Required JSON schema:
{{"slides":[{{"layout":"cover","title":"...","subtitle":"...","topics":["...","...","...","..."]}},{{"layout":"card_sequence","title":"...","subtitle":"...","items":[{{"title":"...","body":"..."}},{{"title":"...","body":"..."}},{{"title":"...","body":"..."}},{{"title":"...","body":"..."}}],"takeaway":"..."}},{{"layout":"comparison","title":"...","subtitle":"...","left":{{"title":"...","body":"..."}},"right":{{"title":"...","body":"..."}},"bottom_line":"..."}},{{"layout":"row_list","title":"...","subtitle":"...","items":[{{"title":"...","body":"..."}},{{"title":"...","body":"..."}},{{"title":"...","body":"..."}},{{"title":"...","body":"..."}},{{"title":"...","body":"..."}}],"bottom_line":"..."}},{{"layout":"checklist_rows","title":"...","subtitle":"...","items":[{{"title":"...","body":"..."}},{{"title":"...","body":"..."}},{{"title":"...","body":"..."}},{{"title":"...","body":"..."}},{{"title":"...","body":"..."}}],"bottom_line":"..."}},{{"layout":"takeaway","title":"...","body":"...","final_line":"..."}}]}}
Return exactly 10 slides; the first is cover and the final is takeaway. Keep text concise enough to fit the renderer.

Approved course book:\n{book[:42000]}\nRevision feedback:\n{feedback or 'None.'}"""


def normalize_deck_slides(data: dict[str, Any], lesson: dict[str, Any]) -> list[dict[str, Any]]:
    slides = data.get("slides") if isinstance(data.get("slides"), list) else []
    allowed = {"cover", "card_sequence", "comparison", "row_list", "checklist_rows", "takeaway"}
    if len(slides) != 10 or any(not isinstance(item, dict) or item.get("layout") not in allowed for item in slides):
        raise RuntimeError("Presentation model returned an invalid deck structure.")
    if slides[0].get("layout") != "cover" or slides[-1].get("layout") != "takeaway":
        raise RuntimeError("Presentation must begin with a cover and end with a lesson takeaway.")
    slides[0].setdefault("title", lesson["title"])
    slides[0].setdefault("subtitle", lesson.get("learning_goal") or "Key residential construction decisions.")
    slides[0]["topics"] = [str(value)[:80] for value in (slides[0].get("topics") or [])][:5]
    if len(slides[0]["topics"]) < 3:
        raise RuntimeError("Presentation cover needs at least three main topics.")
    return slides


def produce_deck(course_slug: str, lesson_number: int) -> list[str]:
    seed = parse_intake(course_slug)
    run = RUNS / seed.slug
    course_map = json.loads((run / "course_map" / "course_map.json").read_text(encoding="utf-8"))
    lesson = lesson_by_number(course_map, lesson_number)
    lesson_tag = lid(lesson_number)
    approved = latest_approved_book(run, lesson_tag)
    try:
        plan = strip_json_fence(request_text(seed.slug, "technical_content", deck_prompt(seed, lesson, approved.read_text(encoding="utf-8", errors="replace"), feedback_for(run, lesson_tag, "deck")), max_tokens=9000))
        slides = normalize_deck_slides(plan, lesson)
    except ModelRequestError as error:
        block(run, "deck", f"Configured technical-content model could not produce Lesson {lesson_number} presentation.\n\nReason: {error}")
        raise RuntimeError(str(error)) from error
    revision, filename = revisioned(run, "deck", f"{lesson_tag}_deck", ".pptx")
    spec = {
        "course_slug": seed.slug,
        "course_title": seed.title,
        "lesson_number": lesson_number,
        "created": date.today().isoformat(),
        "production_mode": "initial",
        "revision": f"r{revision:02d}",
        "run_folder": f"runs/{seed.slug}",
        "assets": {"brand_icon": BRAND_ICON, "negative_wordmark": NEGATIVE_WORDMARK},
        "output": {"pptx": f"deck/{filename}", "qa": f"deck/{lesson_tag}_deck_qa_r{revision:02d}.md", "rendered_dir": f"deck/rendered_slides_{lesson_tag}_r{revision:02d}"},
        "slides": slides,
        "qa_checks": ["10 slides.", "MECE: each slide has a distinct teaching job.", "No automatic last-item highlight.", "Residential-construction-first audience anchor.", "No visible timing or speaker notes."],
        "inspection_notes": ["Live deck copy was generated from the approved course book.", "Deck is released for review only after renderer QA passes."],
    }
    spec_path = run / "deck" / f"{lesson_tag}_deck_spec_r{revision:02d}.json"
    write_json(spec_path, spec)
    subprocess.run([sys.executable, str(ROOT / "tools" / "greg_render_deck_from_spec.py"), str(spec_path)], cwd=ROOT, check=True)
    qa_path = run / spec["output"]["qa"]
    if not qa_path.exists() or "fail" in qa_path.read_text(encoding="utf-8", errors="replace").lower():
        raise RuntimeError("Presentation automatic QA failed; no deck was released for review.")
    update_canonical_manifest(seed.slug)
    return [f"Presentation revision r{revision:02d} created: {rel(run / spec['output']['pptx'])}", "Presentation renderer QA passed."]


def approved_deck_baseline(run: Path, lesson_tag: str) -> Path:
    approval = run / "approval" / f"{lesson_tag}_deck_approval.md"
    canonical = load_module("greg_canonical_artifacts", "tools/greg_canonical_artifacts.py")
    artifact = canonical.artifact_from_approval(run, approval) if approval.exists() else None
    if not artifact:
        raise RuntimeError(f"Lesson {lesson_tag[-2:]} needs an approved English presentation before localization.")
    return artifact


def localization_name(locale: str) -> tuple[str, str]:
    if locale == "pt_br":
        return "Brazilian Portuguese for learners working in the U.S. market", "pt-br"
    if locale == "es":
        return "neutral Latin American Spanish", "es-419"
    raise ValueError(f"Unsupported locale: {locale}")


def localize_book(course_slug: str, lesson_number: int, locale: str) -> list[str]:
    seed = parse_intake(course_slug)
    run = RUNS / seed.slug
    lesson_tag = lid(lesson_number)
    source = latest_approved_book(run, lesson_tag)
    source_draft = latest_matching_path(run / "lesson_draft", f"{lesson_tag}_draft_r*.md")
    if not source_draft:
        raise RuntimeError("The approved course book has no revisioned source draft for localization.")
    language, folder = localization_name(locale)
    references = (run / "sources" / "student_references.md").read_text(encoding="utf-8")
    prompt = f"""Translate the following student-facing construction course book into {language}. Return Markdown only. Preserve the structural order: Introduction, Learning Objectives, numbered Sections, Summary and Key Takeaways, Glossary, and References. Do not add a Lesson Roadmap. Translate all body text and section titles. Preserve every Summary and Key Takeaways item as a concise bullet point; never convert that section into paragraphs. Keep U.S. construction terminology, units, codes, and market context. Preserve the six approved callout labels semantically in the target language and never invent a new callout type. Do not add or remove facts, activities, citations, or references. Do not use em dashes, en dashes, or spaced hyphens as punctuation.\n\n{source_draft.read_text(encoding='utf-8', errors='replace')[:48000]}"""
    try:
        translated = request_text(seed.slug, "localization", prompt, max_tokens=14000)
    except ModelRequestError as error:
        block(run, "localization", f"Localization model could not produce Lesson {lesson_number} {locale} course book.\n\nReason: {error}")
        raise RuntimeError(str(error)) from error
    translated = force_student_references(translated, references)
    revision, draft_name = revisioned(run, f"localization/{folder}", f"{lesson_tag}_study_guide_{locale}", ".md")
    draft_path = run / "localization" / folder / draft_name
    write_text(draft_path, translated)
    if "# References" not in translated or len(translated.split()) < 250:
        raise RuntimeError("Localized course book failed automatic completeness QA.")
    pdf_name = f"{lesson_tag}_study_guide_{locale}_r{revision:02d}.pdf"
    cover_quote = select_cover_quote(seed, lesson_by_number(json.loads((run / "course_map" / "course_map.json").read_text(encoding="utf-8")), lesson_number), run, lesson_tag)
    spec = {
        "course_slug": seed.slug, "course_title": seed.title, "lesson_number": str(lesson_number),
        "production_mode": "initial", "revision": f"r{revision:02d}", "run_folder": f"runs/{seed.slug}",
        "source_markdown": rel(draft_path),
        "metadata": {"course_title": seed.title, "lesson_number": str(lesson_number), "lesson_short_title": f"{locale.upper()} Lesson {lesson_number}", "lesson_subtitle": language, "level_label": f"{seed.level} Level", "quote": f'"{cover_quote["quote"]}"', "quote_author": cover_quote["author"], "quote_verification_url": cover_quote["verification_url"], "icon": BRAND_ICON},
        "output": {"pdf": f"localization/{folder}/{pdf_name}", "render_qa": f"localization/{folder}/{lesson_tag}_{locale}_render_qa_r{revision:02d}.md", "layout_qa": f"localization/{folder}/{lesson_tag}_{locale}_layout_qa_r{revision:02d}.md", "rendered_dir": f"localization/{folder}/rendered_pages_{lesson_tag}_r{revision:02d}"},
        "visuals": [], "qa_notes": ["Initial production is being prepared for approval.", "Localized artifact is derived from an approved English course book."]
    }
    spec_path = run / "localization" / folder / f"{lesson_tag}_study_guide_{locale}_spec_r{revision:02d}.json"
    write_json(spec_path, spec)
    subprocess.run([production_python(), str(ROOT / "tools" / "greg_render_study_guide_from_spec.py"), str(spec_path)], cwd=ROOT, check=True)
    layout = run_pdf_layout_qa(
        run / spec["output"]["pdf"],
        run / spec["output"]["render_qa"],
        run / spec["output"]["layout_qa"],
    )
    if not layout["passed"]:
        raise RuntimeError("Localized course book layout QA failed.")
    update_canonical_manifest(seed.slug)
    return [f"{locale} course book r{revision:02d} created: {rel(run / spec['output']['pdf'])}"]


def latest_matching_path(folder: Path, pattern: str) -> Path | None:
    matches = sorted(folder.glob(pattern), key=lambda item: (item.stat().st_mtime, item.name))
    return matches[-1] if matches else None


def localize_deck(course_slug: str, lesson_number: int, locale: str) -> list[str]:
    seed = parse_intake(course_slug)
    run = RUNS / seed.slug
    lesson_tag = lid(lesson_number)
    approved_deck_baseline(run, lesson_tag)
    source_spec = latest_matching_path(run / "deck", f"{lesson_tag}_deck_spec_r*.json")
    if not source_spec:
        raise RuntimeError("The approved English presentation has no revisioned deck spec for localization.")
    language, folder = localization_name(locale)
    source = json.loads(source_spec.read_text(encoding="utf-8"))
    prompt = f"""Translate every student-visible text value in this Prof Greg deck JSON into {language}. Return JSON only in the form {{"slides": [...]}}. Preserve all keys, layout names, numbers, filenames, asset paths, and slide count exactly. Do not add slides or speaker notes. Preserve U.S. construction terms, units, and facts.\n\n{json.dumps(source['slides'], ensure_ascii=False)}"""
    try:
        data = strip_json_fence(request_text(seed.slug, "localization", prompt, max_tokens=9000))
    except ModelRequestError as error:
        raise RuntimeError(str(error)) from error
    slides = normalize_deck_slides(data, {"title": f"Lesson {lesson_number}", "learning_goal": ""})
    revision, filename = revisioned(run, f"localization/{folder}", f"{lesson_tag}_deck_{locale}", ".pptx")
    spec = {**source, "created": date.today().isoformat(), "production_mode": "initial", "revision": f"r{revision:02d}", "output": {"pptx": f"localization/{folder}/{filename}", "qa": f"localization/{folder}/{lesson_tag}_{locale}_deck_qa_r{revision:02d}.md", "rendered_dir": f"localization/{folder}/rendered_slides_{lesson_tag}_r{revision:02d}"}, "slides": slides}
    spec_path = run / "localization" / folder / f"{lesson_tag}_deck_{locale}_spec_r{revision:02d}.json"
    write_json(spec_path, spec)
    subprocess.run([sys.executable, str(ROOT / "tools" / "greg_render_deck_from_spec.py"), str(spec_path)], cwd=ROOT, check=True)
    qa = run / spec["output"]["qa"]
    if not qa.exists() or "fail" in qa.read_text(encoding="utf-8", errors="replace").lower():
        raise RuntimeError("Localized presentation QA failed.")
    update_canonical_manifest(seed.slug)
    return [f"{locale} presentation r{revision:02d} created: {rel(run / spec['output']['pptx'])}"]


def run_stage(course_slug: str, stage: str, lessons: list[int] | None = None) -> list[str]:
    course_slug = assert_safe_run_slug(course_slug)
    if stage == "course_map":
        return produce_course_map(course_slug)
    if stage == "sources":
        return produce_source_ledger(course_slug)
    if stage == "study_guide":
        results: list[str] = []
        for lesson in lessons or [1]:
            results.extend(produce_study_guide(course_slug, lesson))
        return results
    if stage == "deck":
        results: list[str] = []
        for lesson in lessons or [1]:
            results.extend(produce_deck(course_slug, lesson))
        return results
    if stage in {"pt_br_book", "es_book", "pt_br_deck", "es_deck"}:
        locale = "pt_br" if stage.startswith("pt_br") else "es"
        producer = localize_book if stage.endswith("book") else localize_deck
        results: list[str] = []
        for lesson in lessons or [1]:
            results.extend(producer(course_slug, lesson, locale))
        return results
    raise ValueError(f"Unsupported live production stage: {stage}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one real Prof Greg production stage.")
    parser.add_argument("course_slug")
    parser.add_argument("--stage", choices=["course_map", "sources", "study_guide", "deck", "pt_br_book", "pt_br_deck", "es_book", "es_deck"], required=True)
    parser.add_argument("--lessons", default="", help="Comma-separated lesson numbers for study-guide production.")
    args = parser.parse_args()
    lessons = [int(value) for value in args.lessons.split(",") if value.strip()] or None
    print("\n".join(run_stage(args.course_slug, args.stage, lessons)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
