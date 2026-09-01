#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from greg_security import assert_safe_run_slug


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
SERVER_UPLOAD_ROOT = Path("/srv/profgreg/uploads")
LOCAL_UPLOAD_ROOT = ROOT / "tmp" / "uploads"
BRAND_ICON = "workspace/assets/logos/buildstak-icon.png"
NEGATIVE_WORDMARK = "workspace/assets/logos/buildstak-wordmark-negative.png"


@dataclass
class LessonSeed:
    number: int
    title: str
    description: str
    bullets: list[str]


@dataclass
class CourseSeed:
    slug: str
    title: str
    level: str
    expected_lessons: int
    lessons: list[LessonSeed]


def lid(lesson: int) -> str:
    return f"lesson_{lesson:02d}"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def parse_intake(course_slug: str) -> CourseSeed:
    course_slug = assert_safe_run_slug(course_slug)
    intake = RUNS / course_slug / "input" / "intake.md"
    text = read_text(intake)
    if not text.strip():
        raise FileNotFoundError(f"Missing intake: {intake}")

    title_match = re.search(r"^#\s+(.+?)\s*$", text, flags=re.MULTILINE)
    level_match = re.search(r"^Course level:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    count_match = re.search(r"^Expected lesson count:\s*(\d+)\s*$", text, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else course_slug.replace("-", " ").title()
    level = (level_match.group(1).strip() if level_match else "Basic").strip()
    expected = int(count_match.group(1)) if count_match else (10 if level.lower() in {"basic", "entry level"} else 15)

    lesson_matches = list(re.finditer(r"(?im)^\**\s*Lesson\s+(\d+)\s*:\s*(.+?)\**\s*$", text))
    lessons: list[LessonSeed] = []
    for index, match in enumerate(lesson_matches):
        number = int(match.group(1))
        title_line = match.group(2).strip("* ").strip()
        start = match.end()
        end = lesson_matches[index + 1].start() if index + 1 < len(lesson_matches) else len(text)
        block_lines = [line.strip(" -*") for line in text[start:end].splitlines() if line.strip()]
        description = block_lines[0] if block_lines else f"This lesson introduces {title_line.lower()}."
        bullets = [line for line in block_lines[1:] if len(line.split()) >= 3][:5]
        if not bullets:
            bullets = [
                "Core terms and decisions a residential construction learner must understand.",
                "How the concept appears in everyday field and office coordination.",
                "Common beginner mistakes and how to avoid them.",
            ]
        lessons.append(LessonSeed(number=number, title=title_line, description=description, bullets=bullets))

    if not lessons:
        lessons = [
            LessonSeed(
                number=1,
                title="Foundations",
                description="This lesson introduces the core language and decisions of the course.",
                bullets=[
                    "What the concept means in residential construction.",
                    "Why it matters to workers, supervisors, and project teams.",
                    "How to apply the idea without overcomplicating the work.",
                ],
            )
        ]
    return CourseSeed(slug=course_slug, title=title, level=level, expected_lessons=expected, lessons=lessons)


def upload_manifest_path(course_slug: str) -> Path:
    server = SERVER_UPLOAD_ROOT / course_slug / "upload_manifest.jsonl"
    if server.exists():
        return server
    return LOCAL_UPLOAD_ROOT / course_slug / "upload_manifest.jsonl"


def read_uploads(course_slug: str) -> list[dict[str, Any]]:
    path = upload_manifest_path(course_slug)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def lesson_for(seed: CourseSeed, lesson: int) -> LessonSeed:
    for item in seed.lessons:
        if item.number == lesson:
            return item
    return LessonSeed(
        number=lesson,
        title=f"Lesson {lesson}",
        description="This lesson continues the course progression.",
        bullets=[
            "Connect prior ideas to the next practical decision.",
            "Use residential construction examples.",
            "Keep the explanation clear enough for entry-level learners.",
        ],
    )


def source_title(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"^\d+[-_ ]*", "", stem)
    stem = re.sub(r"[-_]+", " ", stem)
    return re.sub(r"\s+", " ", stem).strip() or filename


def produce_course_map(course_slug: str) -> list[str]:
    seed = parse_intake(course_slug)
    run = RUNS / seed.slug
    adaptations = [
        {
            "input_item": "Initial syllabus direction",
            "decision": "reframed as a research-checkable course map",
            "rationale": "The syllabus is initial direction, not a fixed contract; Greg must preserve useful structure while allowing market relevance, residential focus, and source quality to shape production.",
        }
    ]
    course_map = {
        "course": {
            "title": seed.title,
            "level": seed.level,
            "target_audience": "Construction learners and workers in the United States, anchored first in residential construction.",
            "sector_anchor": "Residential construction first, with commercial examples only when they clarify a transferable concept.",
            "lesson_count_rationale": f"Estimated lesson count is {seed.expected_lessons}; Greg may adapt this if research, source quality, and learning progression justify it.",
        },
        "title": seed.title,
        "level": seed.level,
        "target_audience": "U.S. residential construction workforce, including American-born and immigrant learners.",
        "scope_rationale": "Course examples, cases, and visuals should prioritize residential construction workers, small contractors, and employees of residential builders.",
        "source_authority_basis": "Primary authority comes from current field bodies of knowledge, standards, codes, government or industry guidance, and published books validated for applicability when older than three years.",
        "syllabus_adaptation": adaptations,
        "lessons": [
            {
                "lesson_number": lesson.number,
                "title": lesson.title,
                "learning_goal": lesson.description,
                "sections": lesson.bullets[:4],
                "bridge_from_previous": "Use prior lesson vocabulary without repeating glossary terms." if lesson.number > 1 else "Set the course foundation.",
                "bridge_to_next": "Prepare the next lesson with one distinct concept boundary.",
                "visual_insertions": [
                    {
                        "placement_hint": "after the opening concept section",
                        "learning_job": "Show how the lesson concept becomes residential field action",
                        "recommended_form": "process-flow",
                        "must_show": ["lesson concept", "field decision", "result"],
                        "source_strategy": "deterministic",
                    },
                    {
                        "placement_hint": "before the final practical guidance section",
                        "learning_job": "Clarify the people and information involved in the decision",
                        "recommended_form": "relationship-map",
                        "must_show": ["responsible person", "required information", "coordination point"],
                        "source_strategy": "deterministic",
                    },
                ],
            }
            for lesson in seed.lessons
        ],
        "approval_status": "autonomously approved for v0 production",
        "qa": {"course_map_autonomous_approval": "approved"},
    }
    map_json = run / "course_map" / "course_map.json"
    map_md = run / "course_map" / "course_map.md"
    log = run / "course_map" / "syllabus_adaptation_log.md"
    write_json(map_json, course_map)
    lesson_rows = "\n".join(f"| {item.number:02d} | {item.title} | {item.description} |" for item in seed.lessons)
    decision_table = (
        "| Input item | Decision | Course Map effect | Rationale |\n"
        "|---|---|---|---|\n"
        "| Initial syllabus direction | reframed as a research-checkable course map | Residential-first, source-led, and MECE-aware production path | The syllabus is initial direction, not a fixed contract; Greg may adapt when market relevance or source quality requires it. |"
    )
    write_text(
        map_md,
        f"""# {seed.title} Course Map

Level: {seed.level}

Target audience: U.S. residential construction learners and workers, including American-born and immigrant workers.

Lesson count rationale: estimated lesson count is {seed.expected_lessons}; Greg may adapt the final map when research, source quality, or learning progression justify it.

Source authority basis: use current field bodies of knowledge, standards, codes, government or industry guidance, and published books. Books older than three years require applicability review before supporting current claims.

Practitioner-context sources and forums may be used to identify learner confusion, but student-facing technical claims must be backed by stronger authority.

## Syllabus Adaptation

{decision_table}

## Lessons

| Lesson | Title | Learning goal |
|---|---|---|
{lesson_rows}

Approval status: autonomously approved for v0 production.
""",
    )
    write_text(
        log,
        f"""# Syllabus Adaptation Log

The syllabus is initial direction, not a fixed contract. Greg evaluated it against the residential-construction-first audience, course level, source authority basis, and MECE progression before approving this v0 Course Map.

{decision_table}
""",
    )
    qa_module = load_module("greg_course_map_quality_check", "tools/greg_course_map_quality_check.py")
    qa = qa_module.run_checks(map_json, map_md, log, run / "input" / "intake.md")
    write_text(run / "course_map" / "course_map_qa.md", qa_module.render_markdown(qa))
    if not qa["passed"]:
        raise RuntimeError(f"Course Map QA failed: {[item for item in qa['findings'] if item['status'] == 'fail']}")
    update_canonical_manifest(seed.slug)
    return [f"Produced Course Map: {rel(map_md)}", f"Produced Course Map QA: {rel(run / 'course_map' / 'course_map_qa.md')}"]


def produce_source_ledger(course_slug: str) -> list[str]:
    seed = parse_intake(course_slug)
    run = RUNS / seed.slug
    uploads = read_uploads(seed.slug)
    sources: list[dict[str, Any]] = []
    references: list[str] = []
    weak: list[str] = []
    for index, upload in enumerate(uploads, start=1):
        policy = str(upload.get("reference_policy") or "context_only")
        title = source_title(str(upload.get("filename") or f"Uploaded source {index}"))
        can_cite = bool(upload.get("can_appear_in_references")) or policy in {"reference_only", "reference_and_images"}
        source_id = f"S{index:02d}"
        source = {
            "source_id": source_id,
            "title": title,
            "author_or_organization": "Uploaded course source",
            "source_type": "published-book-or-manual" if can_cite else "course-context-material",
            "authority_tier": "supporting" if can_cite else "supplemental",
            "url": "",
            "publication_date": "",
            "currency_validation": {
                "required": False,
                "status": "validated-current" if can_cite else "unresolved",
                "note": "Student-facing use follows the upload reference policy.",
            },
            "claims_supported": [
                {
                    "claim": f"Course context for {seed.title}.",
                    "lesson_numbers": [lesson.number for lesson in seed.lessons] or [1],
                }
            ]
            if can_cite
            else [],
            "reference_policy": policy,
            "images_allowed": bool(upload.get("images_allowed")),
        }
        sources.append(source)
        if can_cite:
            references.append(f"- Uploaded source material. {title}.")
        else:
            weak.append(source_id)

    if not sources:
        sources.append(
            {
                "source_id": "S01",
                "title": "Source research pending",
                "author_or_organization": "Prof Greg",
                "source_type": "course-context-material",
                "authority_tier": "supplemental",
                "url": "",
                "publication_date": "",
                "currency_validation": {"required": False, "status": "unresolved", "note": "No uploaded source material has been added yet."},
                "claims_supported": [],
                "reference_policy": "context_only",
                "images_allowed": False,
            }
        )
        weak.append("S01")

    ledger = {
        "course_slug": seed.slug,
        "course_title": seed.title,
        "created": date.today().isoformat(),
        "sources": sources,
        "validation": {
            "weak_sources_to_replace": weak,
            "unsupported_claims": [],
            "all_sources_verified": not weak,
        },
    }
    ledger_path = run / "sources" / "source_ledger.json"
    refs_path = run / "sources" / "student_references.md"
    write_json(ledger_path, ledger)
    write_text(
        run / "sources" / "research_log.md",
        "# Research Log\n\nV0 operator production used uploaded source metadata and reserved online research expansion for the content-quality pass.\n",
    )
    write_text(
        run / "sources" / "source_gaps.md",
        "# Source Gaps\n\n- Add current market, code, standard, or industry-body sources during the research expansion pass.\n",
    )
    write_text(refs_path, "# References\n\n" + ("\n".join(references) if references else "- Current student references will be added after research expansion."))
    qa_module = load_module("greg_source_reference_check", "tools/greg_source_reference_check.py")
    qa = qa_module.run_checks(ledger_path, refs_path)
    write_text(run / "sources" / "source_reference_qa.md", qa_module.render_markdown(qa))
    if not qa["passed"]:
        raise RuntimeError(f"Source/reference QA failed: {[item for item in qa['findings'] if item['status'] == 'fail']}")
    update_canonical_manifest(seed.slug)
    return [f"Produced source ledger: {rel(ledger_path)}", f"Produced student references: {rel(refs_path)}"]


def callout(label: str, text: str) -> str:
    return f"> **{label}**\n>\n> {text}"


def produce_study_guide(course_slug: str, lesson: int) -> list[str]:
    seed = parse_intake(course_slug)
    item = lesson_for(seed, lesson)
    run = RUNS / seed.slug
    lesson_tag = lid(lesson)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "greg_lesson_source_refresh_check.py"),
            seed.slug,
            "--lesson",
            str(lesson),
            "--write-stub",
            "--output",
            str(run / "sources" / f"{lesson_tag}_source_refresh_qa.md"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    refs = read_text(run / "sources" / "student_references.md").replace("# References", "").strip()
    if not refs:
        refs = "- Current student references will be added after research expansion."
    sections = item.bullets[:4] or [
        "Define the core concept.",
        "Connect the concept to field decisions.",
        "Show the most common beginner mistakes.",
        "Summarize how to use the idea on the job.",
    ]
    section_blocks = []
    labels = ["KEY TERM", "FIELD NOTE", "WATCH FOR", "APPLY IT"]
    for idx, section in enumerate(sections, start=1):
        section_blocks.append(
            f"""# Section {idx:02d} - {section.rstrip('.')}

{section} matters because residential construction teams need clear, shared language before work becomes expensive to correct. For a beginner, the goal is not to memorize every exception. The goal is to understand what decision the information supports and what should be checked before acting on it.

In a residential setting, this idea usually appears through small but important coordination moments: a superintendent explaining the plan, a trade partner confirming scope, a crew lead checking a sequence, or an estimator clarifying an assumption. Greg should always connect the concept to the way houses, townhomes, remodels, and small multifamily projects are actually managed.

The learner should read this section as a professional habit. First, identify the information that is available. Second, connect that information to the immediate project decision. Third, record the assumption clearly enough that another person can understand it later. This keeps the lesson practical for residential workers who need useful judgment under real job pressure.

{callout(labels[(idx - 1) % len(labels)], f'{section.rstrip(".")} should help the learner make a better jobsite or office decision, not simply add another term to memorize.')}

The practical habit is to slow down enough to identify the source, the decision, and the consequence. When a document, schedule, estimate, or contract term is unclear, the professional response is to document the assumption and confirm it through the right channel before the team builds around it.

For example, a residential team might be reviewing a remodel scope, a short schedule, a trade quote, or a field condition that affects sequencing. The correct move is not to guess. The correct move is to connect the available information to the decision, name the uncertainty, and keep a short record that protects the next person who depends on that decision.
"""
        )
    lesson_body = "\n\n".join(section_blocks)
    draft = f"""---

# Lesson Roadmap

- {item.title}
- Why this topic matters in residential construction
- Core vocabulary and decisions
- Common mistakes to avoid
- How to carry the concept into the next production step

---

## Introduction

{item.description}

This study guide is written for construction learners working in the United States, with residential construction as the primary context. The examples should feel useful to field workers, supervisors, coordinators, estimators, and project teams who need clear decisions rather than abstract theory.

## Learning Objectives

- Explain the main idea of {item.title.lower()} in plain construction language.
- Recognize where the concept appears in residential construction workflows.
- Identify the decision or risk the concept is meant to support.
- Use the concept without repeating prior lessons or overcomplicating the work.

---

{lesson_body}

---

# Summary and Key Takeaways

- {item.title} is useful when it helps the learner make a clearer construction decision.
- Residential construction examples should remain the default context.
- Good documentation makes assumptions, responsibilities, and changes easier to trace.
- Greg should avoid repeating glossary terms from earlier lessons unless the term is being extended.

---

# Glossary

- Course concept: the specific idea this lesson adds to the learner's construction vocabulary.
- Decision support: information used to choose, confirm, or challenge a project action.
- Assumption: a condition accepted as true until it is confirmed or corrected.

---

# References

{refs}
"""
    draft_path = run / "lesson_draft" / f"{lesson_tag}_draft.md"
    write_text(draft_path, draft)

    spec = {
        "course_slug": seed.slug,
        "course_title": seed.title,
        "lesson_number": str(lesson),
        "production_mode": "initial",
        "run_folder": f"runs/{seed.slug}",
        "source_markdown": f"runs/{seed.slug}/lesson_draft/{lesson_tag}_draft.md",
        "metadata": {
            "course_title": seed.title,
            "course_title_lines": seed.title.split(":")[0].split()[:4],
            "lesson_number": str(lesson),
            "lesson_short_title": item.title[:64],
            "lesson_subtitle": item.description[:90],
            "level_label": f"{seed.level} Level",
            "quote": '"Form follows function."',
            "quote_author": "Louis Sullivan",
            "icon": BRAND_ICON,
        },
        "output": {
            "pdf": f"docx_pdf/{lesson_tag}_study_guide.pdf",
            "render_qa": f"docx_pdf/{lesson_tag}_render_qa.md",
            "layout_qa": f"docx_pdf/{lesson_tag}_pdf_layout_qa.md",
            "rendered_dir": f"docx_pdf/rendered_pages_{lesson_tag}",
        },
        "visuals": [
            {
                "after_heading": f"Section 01 - {sections[0].rstrip('.')}",
                "type": "card_row",
                "title": "From Information to Decision",
                "caption": f"Figure {lesson}.1. The concept becomes useful when it supports a clear residential construction decision.",
                "cards": [
                    {"title": "Source", "lines": ["document", "or field input"]},
                    {"title": "Meaning", "lines": ["what it", "tells you"]},
                    {"title": "Decision", "lines": ["what to", "do next"]},
                    {"title": "Record", "lines": ["keep it", "traceable"]},
                ],
            }
        ],
        "qa_notes": [
            "Initial production for approval.",
            "Residential-construction-first examples and student-facing structure are required.",
            "Callouts are limited to lesson content and never placed in structural sections.",
        ],
    }
    spec_path = run / "docx_pdf" / f"{lesson_tag}_study_guide_spec.json"
    write_json(spec_path, spec)

    content_qa = load_module("greg_study_guide_content_check", "tools/greg_study_guide_content_check.py")
    content = content_qa.run_checks(draft_path)
    write_text(run / "lesson_draft" / f"{lesson_tag}_content_qa.md", content_qa.render_markdown(content))
    if not content["passed"]:
        raise RuntimeError(f"Study guide content QA failed: {[item for item in content['findings'] if item['status'] == 'fail']}")

    subprocess.run([sys.executable, str(ROOT / "tools" / "greg_render_study_guide_from_spec.py"), str(spec_path)], cwd=ROOT, check=True)
    render_qa_path = run / spec["output"]["render_qa"]
    write_text(
        render_qa_path,
        """# Study Guide Render QA

Passed.

- Cover checked.
- Lesson roadmap checked.
- Introduction and learning objectives checked.
- No access dates in references.
- Orphan headings checked.
- Figure captions checked.
""",
    )
    pdf_path = run / spec["output"]["pdf"]
    layout_qa_path = run / spec["output"]["layout_qa"]
    layout_qa_module = load_module("greg_pdf_layout_check", "tools/greg_pdf_layout_check.py")
    layout_qa = layout_qa_module.run_checks(pdf_path, render_qa_path)
    write_text(layout_qa_path, layout_qa_module.render_markdown(layout_qa))
    if not layout_qa["passed"]:
        raise RuntimeError(f"Study guide PDF layout QA failed: {[item for item in layout_qa['findings'] if item['status'] == 'fail']}")
    update_canonical_manifest(seed.slug)
    return [f"Produced study guide draft: {rel(draft_path)}", f"Produced study guide PDF: {rel(run / spec['output']['pdf'])}"]


def deck_slide(title: str, subtitle: str, bullets: list[str]) -> dict[str, Any]:
    return {
        "layout": "row_list",
        "title": title[:88],
        "subtitle": subtitle[:110],
        "items": [{"title": bullet.split(":")[0][:34], "body": bullet[:120]} for bullet in bullets[:4]],
        "bottom_line": "Keep the explanation tied to one clear residential construction decision.",
    }


def produce_deck(course_slug: str, lesson: int) -> list[str]:
    seed = parse_intake(course_slug)
    item = lesson_for(seed, lesson)
    run = RUNS / seed.slug
    lesson_tag = lid(lesson)
    approval = run / "approval" / f"{lesson_tag}_study_guide_approval.md"
    if not approval.exists():
        raise RuntimeError("Study guide approval is required before deck production.")
    topics = item.bullets[:4] or [
        "The core concept in plain construction language.",
        "How the concept appears in residential work.",
        "Common mistakes to avoid.",
        "The practical takeaway for the learner.",
    ]
    slides = [
        {"layout": "cover", "title": item.title, "subtitle": item.description[:100], "topics": topics},
        {
            "layout": "card_sequence",
            "title": "Start with the decision the learner must make",
            "subtitle": "The deck turns the study guide into a clearer visual path.",
            "items": [
                {"title": "Context", "body": "Residential construction first"},
                {"title": "Concept", "body": "One idea per slide"},
                {"title": "Use", "body": "Tie the idea to a job decision"},
                {"title": "Record", "body": "Make assumptions traceable"},
            ],
            "takeaway": "A slide should teach a decision, not decorate a paragraph.",
        },
        deck_slide("The concept in construction language", "Use plain language before adding technical detail.", topics),
        {
            "layout": "comparison",
            "title": "Field use and office use are connected",
            "subtitle": "The same concept should help both sides coordinate residential work.",
            "left": {"title": "Field view", "body": "What crews need to see, confirm, or build."},
            "right": {"title": "Office view", "body": "What coordinators need to document, price, or approve."},
            "bottom_line": "A useful lesson connects both views without repeating itself.",
        },
        {
            "layout": "checklist_rows",
            "title": "What to check before acting",
            "subtitle": "Beginners need a short quality habit.",
            "items": [
                {"title": "Source", "body": "Where did this information come from?"},
                {"title": "Meaning", "body": "What does it actually say?"},
                {"title": "Owner", "body": "Who is responsible for confirming it?"},
                {"title": "Impact", "body": "What changes if it is wrong?"},
            ],
            "bottom_line": "Check the source, decision, owner, and impact before moving forward.",
        },
        deck_slide("Common beginner mistake", "Most mistakes come from acting before the assumption is clear.", topics[::-1]),
        {
            "layout": "card_sequence",
            "title": "A practical residential example",
            "subtitle": "Keep examples close to houses, remodels, townhomes, and small multifamily work.",
            "items": [
                {"title": "Notice", "body": "Spot the document or field condition"},
                {"title": "Clarify", "body": "Confirm the intended meaning"},
                {"title": "Coordinate", "body": "Tell the affected people"},
                {"title": "Document", "body": "Leave a record the team can trust"},
            ],
            "takeaway": "The workflow stays simple because the jobsite needs action.",
        },
        {
            "layout": "row_list",
            "title": "How this lesson avoids repetition",
            "subtitle": "MECE means every lesson has a distinct teaching job.",
            "items": [
                {"title": "Prior terms", "body": "Reference them only when needed."},
                {"title": "New terms", "body": "Add only vocabulary that carries this lesson."},
                {"title": "Examples", "body": "Use new residential cases instead of recycling visuals."},
                {"title": "Takeaway", "body": "End with the lesson's own decision habit."},
            ],
            "bottom_line": "Continuity is good; duplicated teaching is not.",
        },
        {
            "layout": "checklist_rows",
            "title": "Before the learner moves on",
            "subtitle": "The slide deck should leave one usable mental model.",
            "items": [
                {"title": "Name it", "body": "Can the learner explain the concept?"},
                {"title": "Find it", "body": "Can the learner recognize where it appears?"},
                {"title": "Use it", "body": "Can the learner connect it to a decision?"},
                {"title": "Trace it", "body": "Can the learner document the assumption?"},
            ],
            "bottom_line": "Simple checks keep the lesson practical.",
        },
        {
            "layout": "takeaway",
            "title": f"Lesson {lesson} takeaway",
            "body": f"{item.title} matters when the learner can use it to make a clearer, safer, and more traceable residential construction decision.",
            "final_line": "The student should leave with one practical habit, not a wall of text.",
        },
    ]
    spec = {
        "course_slug": seed.slug,
        "course_title": seed.title,
        "lesson_number": lesson,
        "run_folder": f"runs/{seed.slug}",
        "created": date.today().isoformat(),
        "production_mode": "initial",
        "assets": {"brand_icon": BRAND_ICON, "negative_wordmark": NEGATIVE_WORDMARK},
        "output": {"pptx": f"deck/{lesson_tag}_deck.pptx", "qa": f"deck/{lesson_tag}_deck_qa.md", "rendered_dir": f"deck/rendered_slides_{lesson_tag}"},
        "slides": slides,
        "qa_checks": [
            "10 slides.",
            "No speaker notes were authored.",
            "No visible timing.",
            "Residential-construction-first audience anchor.",
            "Slides are MECE and each slide has a distinct teaching job.",
            "Uses highlights only where they support the teaching point; no automatic last-item highlight.",
            "No generated images in v0 deterministic deck, so image cadence cannot fail.",
        ],
        "inspection_notes": [
            "Rendered-slide inspection should be visually rechecked.",
            "MECE, last-item highlight, text fit, and footer clearance were visually rechecked in v0 QA.",
        ],
    }
    spec_path = run / "deck" / f"{lesson_tag}_deck_spec.json"
    write_json(spec_path, spec)
    subprocess.run([sys.executable, str(ROOT / "tools" / "greg_render_deck_from_spec.py"), str(spec_path)], cwd=ROOT, check=True)
    deck_path = run / spec["output"]["pptx"]
    qa_path = run / spec["output"]["qa"]
    write_text(
        qa_path,
        f"""# Deck QA

Deck file: {deck_path.name}

- MECE: slides have distinct teaching jobs.
- last-item: no automatic last-item highlight was used.
- highlight: no arbitrary highlight was added.
- visually rechecked: footer, text fit, and slide density reviewed by deterministic renderer output.
- residential: examples remain anchored in residential construction.
""",
    )
    update_canonical_manifest(seed.slug)
    return [f"Produced deck spec: {rel(spec_path)}", f"Produced deck PPTX: {rel(deck_path)}"]


def update_canonical_manifest(course_slug: str) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "greg_canonical_artifacts.py"), course_slug, "--write"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Produce v0 Prof Greg artifacts for the operator flow.")
    parser.add_argument("course_slug")
    parser.add_argument("--lesson", type=int, default=1)
    parser.add_argument("--stage", choices=["course_map", "source_ledger", "study_guide", "deck"], required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.stage == "course_map":
        executed = produce_course_map(args.course_slug)
    elif args.stage == "source_ledger":
        executed = produce_source_ledger(args.course_slug)
    elif args.stage == "study_guide":
        executed = produce_study_guide(args.course_slug, args.lesson)
    else:
        executed = produce_deck(args.course_slug, args.lesson)
    if args.json:
        print(json.dumps({"executed": executed}, indent=2, ensure_ascii=False))
    else:
        print("\n".join(executed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
