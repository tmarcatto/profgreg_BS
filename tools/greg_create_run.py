#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


RUN_DIRS = [
    "input",
    "course_map",
    "marketing",
    "sources",
    "lesson_draft",
    "review",
    "docx_pdf",
    "docx_pdf/assets",
    "docx_pdf/rendered_pages",
    "approval",
    "deck",
    "deck/assets",
    "deck/rendered_slides",
    "localization/pt-br",
    "localization/es-419",
    "process_review",
]


@dataclass
class RunSetup:
    course_slug: str
    run_folder: str
    created: list[str]
    existing: list[str]
    intake_path: str
    status_path: str


def slugify(text: str) -> str:
    slug = text.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "untitled-course"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def create_run(course_title: str, course_slug: str | None, level: str | None) -> RunSetup:
    slug = slugify(course_slug or course_title)
    run = RUNS / slug
    created = []
    existing = []

    for folder in RUN_DIRS:
        path = run / folder
        if path.exists():
            existing.append(rel(path))
        else:
            path.mkdir(parents=True, exist_ok=True)
            created.append(rel(path))

    intake = run / "input" / "intake.md"
    if not intake.exists():
        template = ROOT / "workspace" / "test-packages" / "full-flow-v0" / "intake-template.md"
        text = template.read_text(encoding="utf-8", errors="replace") if template.exists() else "# Intake\n"
        header = [
            f"# {course_title}",
            "",
            f"Course slug: `{slug}`",
            f"Course level: {level or '[Basic | Intermediate | Advanced]'}",
            f"Created: {date.today().isoformat()}",
            "",
            "---",
            "",
        ]
        intake.write_text("\n".join(header) + text, encoding="utf-8")
        created.append(rel(intake))
    else:
        existing.append(rel(intake))

    status = run / "process_review" / "run_status.md"
    if not status.exists():
        status.write_text(
            "\n".join(
                [
                    "# Run Status",
                    "",
                    f"Course title: {course_title}",
                    f"Course slug: {slug}",
                    f"Course level: {level or '[unknown]'}",
                    f"Created: {date.today().isoformat()}",
                    "",
                    "Current stage: INTAKE",
                    "Gate status: intake not yet approved for Course Map.",
                    "",
                    "Next recommended action: complete intake and route to Course Map.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        created.append(rel(status))
    else:
        existing.append(rel(status))

    return RunSetup(
        course_slug=slug,
        run_folder=rel(run),
        created=created,
        existing=existing,
        intake_path=rel(intake),
        status_path=rel(status),
    )


def render_markdown(setup: RunSetup) -> str:
    lines = [
        f"Course slug: `{setup.course_slug}`",
        f"Run folder: `{setup.run_folder}`",
        f"Intake: `{setup.intake_path}`",
        f"Status: `{setup.status_path}`",
        "",
        f"Created items: {len(setup.created)}",
        f"Existing items: {len(setup.existing)}",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a standardized Prof Greg run folder.")
    parser.add_argument("course_title", help="Course title.")
    parser.add_argument("--slug", help="Optional explicit course slug.")
    parser.add_argument("--level", help="Course level: Basic, Intermediate, or Advanced.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    setup = create_run(args.course_title, args.slug, args.level)
    if args.json:
        print(json.dumps(asdict(setup), indent=2, ensure_ascii=False))
    else:
        print(render_markdown(setup))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
