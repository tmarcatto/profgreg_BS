#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
TEMPLATE = ROOT / "workspace" / "test-packages" / "full-flow-v1" / "intake-template.md"


@dataclass
class PreparedRun:
    course_slug: str
    run_folder: str
    checklist: str
    intake: str
    status: str


def slugify(text: str) -> str:
    import re

    slug = text.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "full-flow-v1-test"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def prepare(course_title: str, course_slug: str | None, level: str) -> PreparedRun:
    slug = slugify(course_slug or course_title)
    run = RUNS / slug
    for folder in [
        "input",
        "course_map",
        "sources",
        "lesson_draft",
        "review",
        "docx_pdf",
        "docx_pdf/rendered_pages",
        "approval",
        "deck",
        "deck/assets",
        "deck/rendered_slides",
        "localization/pt-br",
        "localization/es-419",
        "process_review",
    ]:
        (run / folder).mkdir(parents=True, exist_ok=True)

    intake = run / "input" / "intake.md"
    if not intake.exists():
        template = TEMPLATE.read_text(encoding="utf-8", errors="replace")
        intake.write_text(
            "\n".join(
                [
                    f"# {course_title}",
                    "",
                    f"Course slug: `{slug}`",
                    f"Course level: {level}",
                    f"Created: {date.today().isoformat()}",
                    "",
                    template,
                ]
            ),
            encoding="utf-8",
        )

    checklist_src = ROOT / "workspace" / "test-packages" / "full-flow-v1" / "execution-checklist.md"
    checklist_dst = run / "process_review" / "full_flow_v1_execution_checklist.md"
    if not checklist_dst.exists():
        shutil.copyfile(checklist_src, checklist_dst)

    status = run / "process_review" / "run_status.md"
    if not status.exists():
        status.write_text(
            "\n".join(
                [
                    "# Run Status",
                    "",
                    f"Course title: {course_title}",
                    f"Course slug: {slug}",
                    f"Course level: {level}",
                    f"Created: {date.today().isoformat()}",
                    "",
                    "Current stage: INTAKE",
                    "Gate status: full-flow v1 intake pending.",
                    "Next recommended action: complete intake, then run the local lesson operator.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    return PreparedRun(slug, rel(run), rel(checklist_dst), rel(intake), rel(status))


def render_markdown(data: PreparedRun) -> str:
    return "\n".join(
        [
            f"Course slug: `{data.course_slug}`",
            f"Run folder: `{data.run_folder}`",
            f"Intake: `{data.intake}`",
            f"Checklist: `{data.checklist}`",
            f"Status: `{data.status}`",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a Prof Greg full-flow v1 test run.")
    parser.add_argument("course_title", help="Course title or test bench name.")
    parser.add_argument("--slug", help="Optional explicit slug.")
    parser.add_argument("--level", default="Basic", help="Course level.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    data = prepare(args.course_title, args.slug, args.level)
    if args.json:
        import json

        print(json.dumps(asdict(data), indent=2, ensure_ascii=False))
    else:
        print(render_markdown(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
