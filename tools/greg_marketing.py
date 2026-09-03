#!/usr/bin/env python3
"""Generate, edit, and render course marketing kits from an approved Course Map."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from greg_create_run import slugify
from greg_live_production import request_json_with_retry


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
WORDMARK = ROOT / "workspace" / "assets" / "logos" / "buildstak-wordmark.png"
WORDMARK_NEGATIVE = ROOT / "workspace" / "assets" / "logos" / "buildstak-wordmark-negative.png"


def marketing_dir(course_slug: str) -> Path:
    return RUNS / slugify(course_slug) / "marketing"


def marketing_json_path(course_slug: str) -> Path:
    return marketing_dir(course_slug) / "marketing.json"


def brochure_path(course_slug: str) -> Path:
    return marketing_dir(course_slug) / f"{slugify(course_slug)}-course-brochure.pdf"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def course_map_for(course_slug: str) -> dict[str, Any]:
    path = RUNS / slugify(course_slug) / "course_map" / "course_map.json"
    data = read_json(path)
    if not data or not data.get("lessons"):
        raise ValueError("Generate and approve the Course Map before creating marketing content.")
    return data


def _text(value: Any, maximum: int = 12000) -> str:
    return str(value or "").strip()[:maximum]


def _text_list(value: Any, count: int, maximum: int = 260) -> list[str]:
    if isinstance(value, str):
        values = [line.strip(" -\t") for line in value.splitlines() if line.strip()]
    elif isinstance(value, list):
        values = [_text(item, maximum) for item in value]
    else:
        values = []
    return [item for item in values if item][:count]


def sentence_count(value: str) -> int:
    protected = re.sub(r"\b(?:U\.S|e\.g|i\.e)\.", lambda match: match.group(0).replace(".", ""), value, flags=re.I)
    return len(re.findall(r"[.!?](?:[\"')\]]+)?(?:\s|$)", protected.strip()))


def normalize_marketing(data: dict[str, Any], course_map: dict[str, Any]) -> dict[str, Any]:
    course = course_map.get("course") or {}
    lessons = course_map.get("lessons") or []
    title = _text(data.get("course_title") or course.get("title") or "New BuildStak Course", 180)
    requirements = _text_list(data.get("requirements"), 8)
    if not requirements:
        requirements = ["No prior specialist software experience is required.", "Bring a current or recent construction project to use in the exercises."]
    sources = []
    for item in data.get("market_sources") or []:
        if not isinstance(item, dict):
            continue
        url = _text(item.get("url"), 1000)
        if url and not re.match(r"^https://", url, flags=re.I):
            continue
        sources.append({
            "organization": _text(item.get("organization"), 160),
            "title": _text(item.get("title"), 260),
            "url": url,
            "published": _text(item.get("published"), 80),
            "claim": _text(item.get("claim"), 500),
        })
    journey = _text_list(data.get("course_journey"), 15, 180)
    if not journey:
        journey = [_text(item.get("title"), 180) for item in lessons if isinstance(item, dict) and item.get("title")]
    normalized = {
        "course_title": title,
        "short_description": _text(data.get("short_description"), 650),
        "full_description": _text(data.get("full_description"), 5000),
        "skills": _text_list(data.get("skills"), 3, 80),
        "what_you_will_learn": _text_list(data.get("what_you_will_learn"), 5, 260),
        "requirements": requirements,
        "audience": _text(data.get("audience") or course.get("target_audience"), 1000),
        "value_proposition": _text(data.get("value_proposition"), 450),
        "career_outcomes": _text_list(data.get("career_outcomes"), 5, 260),
        "market_highlights": _text_list(data.get("market_highlights"), 4, 340),
        "market_sources": sources[:8],
        "course_journey": journey,
        "call_to_action": _text(data.get("call_to_action") or "Build practical skills you can use on your next project.", 240),
        "landing_page_url": _text(data.get("landing_page_url") or "https://learn.buildstak.com/courses", 1000),
        "status": "ready",
        "schema_version": 1,
    }
    if len(normalized["skills"]) != 3:
        raise ValueError("Marketing content must include exactly 3 skills.")
    if len(normalized["what_you_will_learn"]) != 5:
        raise ValueError("Marketing content must include exactly 5 learning outcomes.")
    if sentence_count(normalized["short_description"]) != 2:
        raise ValueError("Short description must contain exactly 2 sentences.")
    for field in ("short_description", "full_description", "value_proposition"):
        if not normalized[field]:
            raise ValueError(f"Marketing content is missing {field.replace('_', ' ')}.")
    return normalized


def marketing_prompt(course_map: dict[str, Any]) -> str:
    compact_map = {
        "course": course_map.get("course") or {},
        "course_summary": course_map.get("course_summary"),
        "lessons": [
            {
                "lesson_number": item.get("lesson_number"),
                "title": item.get("title"),
                "learning_goal": item.get("learning_goal"),
                "sections": item.get("sections"),
            }
            for item in (course_map.get("lessons") or [])
            if isinstance(item, dict)
        ],
    }
    return f"""Return JSON only. Create a conversion-focused English marketing kit for the BuildStak course described by the approved Course Map below.

Use current web research for the U.S. construction market and career context. Prefer BLS, Census, government agencies, recognized construction associations, and reputable industry research. Every number or market assertion must be traceable to a direct HTTPS source in market_sources. Do not invent statistics, job titles, salaries, promotions, sources, dates, or URLs. If reliable quantitative evidence is not available, use a careful qualitative claim.

Audience: construction professionals and workers in the United States. Voice: practical, credible, direct, optimistic, construction-native. Avoid academic filler, hype, guarantees, and claims that completing one course automatically causes a promotion or job offer. Explain how the learning can support advancement, stronger performance, or readiness for expanded responsibilities.

Required JSON schema:
{{
  "course_title":"clear market-facing course title",
  "short_description":"exactly 2 concise sentences suitable for a course-card or hero section",
  "full_description":"2-4 concise paragraphs connecting the learner problem, current market context, practical course value, and career relevance",
  "skills":["exactly 3 short searchable tags"],
  "what_you_will_learn":["exactly 5 specific outcome statements beginning with action verbs"],
  "requirements":["2-5 honest prerequisites or preparation notes"],
  "audience":"who this course is for",
  "value_proposition":"one strong brochure-cover promise without unsupported guarantees",
  "career_outcomes":["3-5 ways the learning may support stronger performance or advancement"],
  "market_highlights":["2-4 concise evidence-backed market observations; include the relevant number and year when supported"],
  "market_sources":[{{"organization":"...","title":"...","url":"https://direct-source","published":"date or year","claim":"the exact claim supported"}}],
  "course_journey":["one concise label per lesson, in Course Map order"],
  "call_to_action":"short enrollment-oriented next step",
  "landing_page_url":"https://learn.buildstak.com/courses"
}}

Approved Course Map:
{json.dumps(compact_map, ensure_ascii=False)}"""


def generate_marketing(course_slug: str) -> dict[str, Any]:
    slug = slugify(course_slug)
    course_map = course_map_for(slug)
    data = request_json_with_retry(slug, "source_research", marketing_prompt(course_map), max_tokens=7000, web_search=True)
    normalized = normalize_marketing(data, course_map)
    target = marketing_json_path(slug)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    render_brochure(slug, normalized)
    return normalized


def save_marketing(course_slug: str, data: dict[str, Any], *, render: bool = True) -> dict[str, Any]:
    slug = slugify(course_slug)
    normalized = normalize_marketing(data, course_map_for(slug))
    target = marketing_json_path(slug)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if render:
        render_brochure(slug, normalized)
    return normalized


def marketing_status(course_slug: str) -> dict[str, Any]:
    slug = slugify(course_slug)
    data = read_json(marketing_json_path(slug))
    brochure = brochure_path(slug)
    return {
        "course_slug": slug,
        "ready": bool(data),
        "marketing": data,
        "brochure_ready": brochure.exists(),
        "brochure_path": (
            str(brochure.relative_to(ROOT))
            if brochure.exists() and (brochure == ROOT or ROOT in brochure.parents)
            else (str(brochure) if brochure.exists() else "")
        ),
    }


def _wrap(canvas: Any, text: str, x: float, y: float, width: float, *, font: str = "Helvetica", size: float = 10.5, leading: float = 14, color: Any = None, max_lines: int | None = None) -> float:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    canvas.setFont(font, size)
    if color is not None:
        canvas.setFillColor(color)
    words = str(text or "").split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if stringWidth(candidate, font, size) <= width or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and stringWidth(lines[-1] + "...", font, size) > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "..."
    for item in lines:
        canvas.drawString(x, y, item)
        y -= leading
    return y


def render_brochure(course_slug: str, data: dict[str, Any] | None = None) -> Path:
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    slug = slugify(course_slug)
    marketing = data or read_json(marketing_json_path(slug))
    if not marketing:
        raise ValueError("Generate or save marketing content before creating the brochure.")
    target = brochure_path(slug)
    target.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(target), pagesize=letter)
    c.setTitle(f"{marketing.get('course_title', 'BuildStak Course')} - Course Brochure")
    c.setAuthor("BuildStak")
    c.setSubject("BuildStak course overview and enrollment marketing brochure")
    width, height = letter
    navy, orange, ink, muted, soft = map(HexColor, ["#2C4363", "#F37021", "#303846", "#687486", "#F5F7FA"])

    def logo(negative: bool = False, x: float = 38, y: float = 674, w: float = 138) -> None:
        path = WORDMARK_NEGATIVE if negative else WORDMARK
        if path.exists():
            c.drawImage(str(path), x, y, width=w, height=w, preserveAspectRatio=True, mask="auto", anchor="w")
        else:
            c.setFillColor(white if negative else navy)
            c.setFont("Helvetica-Bold", 18)
            c.drawString(x, y + 8, "BUILDSTAK")

    def footer(page: int, inverse: bool = False) -> None:
        c.setFillColor(white if inverse else muted)
        c.setFont("Helvetica", 8)
        c.drawString(44, 24, "BUILDSTAK  |  PRACTICAL LEARNING FOR CONSTRUCTION")
        c.drawRightString(width - 44, 24, f"{page} / 5")

    def section_label(value: str, y: float) -> None:
        c.setFillColor(orange)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(44, y, value.upper())

    # 1. Cover
    c.setFillColor(navy)
    c.rect(0, 0, width, height, fill=1, stroke=0)
    c.setFillColor(orange)
    c.rect(0, 0, 18, height, fill=1, stroke=0)
    logo(True)
    c.setFillColor(orange)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(44, 618, "BUILD THE SKILLS. LEAD THE WORK.")
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 32)
    y = _wrap(c, marketing["course_title"], 44, 570, 500, font="Helvetica-Bold", size=32, leading=37, color=white, max_lines=4)
    c.setStrokeColor(orange)
    c.setLineWidth(4)
    c.line(44, y - 12, 156, y - 12)
    _wrap(c, marketing.get("value_proposition", ""), 44, y - 52, 470, font="Helvetica", size=16, leading=22, color=white, max_lines=5)
    chips = marketing.get("skills") or []
    chip_x = 44
    for skill in chips:
        chip_w = min(150, max(78, len(skill) * 7 + 24))
        c.setFillColor(HexColor("#405A7C"))
        c.roundRect(chip_x, 116, chip_w, 28, 8, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(chip_x + chip_w / 2, 126, skill[:24])
        chip_x += chip_w + 10
    footer(1, True)
    c.showPage()

    # 2. Market opportunity
    logo()
    section_label("Why this course, why now", 682)
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 25)
    c.drawString(44, 646, "Turn market change into practical advantage")
    y = _wrap(c, marketing.get("full_description", ""), 44, 612, 524, size=10.5, leading=15, color=ink, max_lines=14)
    highlights = marketing.get("market_highlights") or []
    top = min(y - 18, 390)
    card_h = 70
    for index, item in enumerate(highlights[:4]):
        cy = top - index * (card_h + 10)
        c.setFillColor(soft)
        c.roundRect(44, cy - card_h, 524, card_h, 7, fill=1, stroke=0)
        c.setFillColor(orange)
        c.circle(64, cy - 21, 9, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(64, cy - 24, str(index + 1))
        _wrap(c, item, 84, cy - 18, 464, font="Helvetica-Bold", size=9.5, leading=13, color=navy, max_lines=4)
    sources = marketing.get("market_sources") or []
    c.setFillColor(muted)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(44, 72, "MARKET SOURCES")
    sy = 60
    for index, source in enumerate(sources[:3], start=1):
        label = f"{index}. {source.get('organization')}: {source.get('title')} ({source.get('published')})"
        c.setFillColor(muted)
        c.setFont("Helvetica", 7)
        c.drawString(44, sy, label[:116])
        url = source.get("url") or ""
        if url:
            c.linkURL(url, (44, sy - 2, 568, sy + 8), relative=0)
        sy -= 11
    footer(2)
    c.showPage()

    # 3. Outcomes and skills
    logo()
    section_label("What you will learn", 682)
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 25)
    c.drawString(44, 646, "Capabilities you can take back to the job")
    y = 598
    for index, outcome in enumerate(marketing.get("what_you_will_learn") or [], start=1):
        c.setFillColor(orange)
        c.circle(64, y - 3, 15, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(64, y - 7, str(index))
        _wrap(c, outcome, 92, y + 4, 450, font="Helvetica-Bold", size=12, leading=16, color=navy, max_lines=3)
        y -= 78
    c.setFillColor(soft)
    c.roundRect(44, 100, 524, 82, 8, fill=1, stroke=0)
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(62, 158, "SKILLS YOU CAN SIGNAL")
    chip_x = 62
    for skill in marketing.get("skills") or []:
        chip_w = min(145, max(88, len(skill) * 7 + 28))
        c.setFillColor(white)
        c.roundRect(chip_x, 118, chip_w, 28, 7, fill=1, stroke=0)
        c.setFillColor(navy)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(chip_x + chip_w / 2, 128, skill[:24])
        chip_x += chip_w + 10
    footer(3)
    c.showPage()

    # 4. Course journey
    logo()
    section_label("The course journey", 682)
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 25)
    c.drawString(44, 646, "A practical path from insight to action")
    journey = marketing.get("course_journey") or []
    columns = 2
    rows = max(1, (len(journey) + columns - 1) // columns)
    start_y = 590
    row_gap = min(66, 430 / max(rows, 1))
    for index, item in enumerate(journey):
        col = index // rows
        row = index % rows
        x = 44 + col * 270
        y = start_y - row * row_gap
        c.setFillColor(orange)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, f"{index + 1:02d}")
        c.setFillColor(navy)
        c.setFont("Helvetica-Bold", 10.5)
        _wrap(c, item, x + 28, y + 1, 218, font="Helvetica-Bold", size=10.5, leading=13, color=navy, max_lines=3)
        c.setStrokeColor(HexColor("#DCE3EB"))
        c.line(x + 28, y - 34, x + 240, y - 34)
    footer(4)
    c.showPage()

    # 5. Audience, requirements, next step
    c.setFillColor(soft)
    c.rect(0, 0, width, height, fill=1, stroke=0)
    logo()
    section_label("Ready when you are", 682)
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(44, 646, "Bring the learning to your next project")
    c.setFillColor(white)
    c.roundRect(44, 410, 524, 196, 10, fill=1, stroke=0)
    c.setFillColor(orange)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(64, 574, "WHO THIS IS FOR")
    _wrap(c, marketing.get("audience", ""), 64, 550, 484, size=10.5, leading=15, color=ink, max_lines=6)
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(64, 474, "HOW THIS CAN SUPPORT YOUR CAREER")
    y = 454
    for item in (marketing.get("career_outcomes") or [])[:3]:
        c.setFillColor(orange)
        c.circle(68, y + 2, 3, fill=1, stroke=0)
        y = _wrap(c, item, 80, y + 5, 458, size=9.3, leading=12, color=ink, max_lines=2) - 5
    c.setFillColor(white)
    c.roundRect(44, 205, 524, 175, 10, fill=1, stroke=0)
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(64, 350, "REQUIREMENTS")
    y = 328
    for item in marketing.get("requirements") or []:
        c.setFillColor(orange)
        c.circle(68, y + 2, 3, fill=1, stroke=0)
        y = _wrap(c, item, 80, y + 5, 458, size=9.5, leading=13, color=ink, max_lines=2) - 6
    c.setFillColor(orange)
    c.roundRect(44, 92, 524, 76, 9, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(64, 136, marketing.get("call_to_action", "Start learning with BuildStak.")[:66])
    c.setFont("Helvetica", 10)
    c.drawString(64, 113, marketing.get("landing_page_url", "https://learn.buildstak.com/courses")[:88])
    url = marketing.get("landing_page_url") or "https://learn.buildstak.com/courses"
    if re.match(r"^https://", url, flags=re.I):
        c.linkURL(url, (44, 92, 568, 168), relative=0)
    footer(5)
    c.save()
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or render BuildStak course marketing materials.")
    parser.add_argument("course_slug")
    parser.add_argument("--action", choices=["generate", "render", "status"], default="generate")
    args = parser.parse_args()
    if args.action == "generate":
        result = generate_marketing(args.course_slug)
    elif args.action == "render":
        result = {"brochure_path": str(render_brochure(args.course_slug).relative_to(ROOT))}
    else:
        result = marketing_status(args.course_slug)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
