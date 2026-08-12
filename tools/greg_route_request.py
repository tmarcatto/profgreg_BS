#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COURSE = "blueprint-reading-crash-course-for-construction-careers"


@dataclass
class Route:
    intent: str
    stage: str
    primary_skill: str
    gate_status: str
    allowed: bool
    next_action: str
    reason: str


INTENT_PATTERNS = [
    ("approval", [r"aprovo", r"aprovad", r"approval", r"autorizo"]),
    ("deck", [r"deck", r"ppt", r"pptx", r"slide", r"apresenta[cç][aã]o"]),
    ("localization", [r"localiz", r"traduz", r"pt-br", r"portugu[eê]s", r"es-419", r"spanish", r"espanhol"]),
    ("status", [r"\bstatus\b", r"onde estamos", r"retom", r"volte", r"voltar", r"where are we"]),
    ("course_map", [r"course map", r"mapa do curso", r"mapear", r"syllabus"]),
    ("sources", [r"fonte", r"refer[eê]ncia", r"source", r"ledger", r"research", r"pesquisa"]),
    ("review", [r"revis", r"qa", r"pedagog", r"cita", r"visual", r"design"]),
    ("docx_pdf", [r"docx", r"pdf", r"render", r"format", r"vers[aã]o final"]),
    ("study_guide", [r"apostila", r"study guide", r"lesson", r"li[cç][aã]o", r"draft", r"rascunho"]),
    ("process_review", [r"process review", r"relat[oó]rio", r"o que aprendemos", r"melhorar o processo"]),
]

STAGE_BY_INTENT = {
    "status": "CURRENT",
    "intake": "INTAKE",
    "course_map": "COURSE_MAP",
    "sources": "SOURCE_LEDGER",
    "study_guide": "DRAFT",
    "review": "REVIEW",
    "docx_pdf": "DOCX_PDF",
    "approval": "HUMAN_APPROVAL",
    "deck": "DECK",
    "localization": "LOCALIZATION",
    "process_review": "REVIEW",
    "unknown": "UNKNOWN",
}

SKILL_BY_INTENT = {
    "status": "greg-operator",
    "intake": "greg-operator",
    "course_map": "course-map",
    "sources": "source-ledger",
    "study_guide": "study-guide-draft",
    "review": "reviewer skill by type",
    "docx_pdf": "docx-pdf-producer",
    "approval": "human-approval-gate",
    "deck": "deck-producer",
    "localization": "localization skill by locale",
    "process_review": "greg-operator",
    "unknown": "greg-operator",
}


def load_status(course_slug: str) -> dict:
    script = ROOT / "tools" / "greg_course_status.py"
    result = subprocess.run(
        [sys.executable, str(script), course_slug, "--json"],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode not in (0, 1):
        return {"blockers": [result.stderr.strip() or "Could not load status."]}
    return json.loads(result.stdout)


def detect_intent(text: str) -> str:
    normalized = text.strip().lower()
    if normalized in {"ok", "segue", "seguir", "continue", "continuar", "próximo", "proximo", "next"}:
        return "status"
    for intent, patterns in INTENT_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, normalized):
                return intent
    return "unknown"


def artifact_exists(status: dict, name: str) -> bool:
    return any(item["name"] == name and item["exists"] for item in status.get("artifacts", []))


def route_request(text: str, course_slug: str) -> Route:
    status = load_status(course_slug)
    intent = detect_intent(text)
    gate_status = status.get("gate_status", "Gate status unavailable.")
    blockers = status.get("blockers", [])

    if blockers:
        return Route(
            intent=intent,
            stage="BLOCKED",
            primary_skill="greg-operator",
            gate_status=gate_status,
            allowed=False,
            next_action="Resolve status blockers before routing production work.",
            reason="The current run has blockers.",
        )

    if intent == "status":
        return Route(
            intent=intent,
            stage=status.get("stage", "CURRENT"),
            primary_skill="greg-operator",
            gate_status=gate_status,
            allowed=True,
            next_action=status.get("next_recommended_action", "Show status and choose next allowed stage."),
            reason="User requested status, resume, or continuation.",
        )

    if intent == "deck" and not artifact_exists(status, "approval"):
        return Route(
            intent="approval",
            stage="HUMAN_APPROVAL",
            primary_skill="human-approval-gate",
            gate_status=gate_status,
            allowed=False,
            next_action="Capture explicit study-guide approval before deck production.",
            reason="Deck production is gated by the approval file.",
        )

    if intent == "localization" and not artifact_exists(status, "approval"):
        return Route(
            intent="approval",
            stage="HUMAN_APPROVAL",
            primary_skill="human-approval-gate",
            gate_status=gate_status,
            allowed=False,
            next_action="Capture explicit study-guide approval before localization.",
            reason="Localization depends on an approved English source artifact.",
        )

    if intent == "approval" and not artifact_exists(status, "study_guide_pdf"):
        return Route(
            intent=intent,
            stage="DOCX_PDF",
            primary_skill="docx-pdf-producer",
            gate_status=gate_status,
            allowed=False,
            next_action="Produce a final study-guide PDF before capturing approval.",
            reason="Approval requires a final study-guide artifact.",
        )

    if intent in {"study_guide", "review", "docx_pdf"} and not artifact_exists(status, "course_map"):
        return Route(
            intent="course_map",
            stage="COURSE_MAP",
            primary_skill="course-map",
            gate_status=gate_status,
            allowed=False,
            next_action="Create or approve the Course Map before lesson production.",
            reason="Lesson production depends on a Course Map.",
        )

    if intent == "unknown":
        return Route(
            intent=intent,
            stage=status.get("stage", "CURRENT"),
            primary_skill="greg-operator",
            gate_status=gate_status,
            allowed=False,
            next_action="Ask a concise clarification or show the current status with a recommended next step.",
            reason="No safe intent was detected.",
        )

    return Route(
        intent=intent,
        stage=STAGE_BY_INTENT[intent],
        primary_skill=SKILL_BY_INTENT[intent],
        gate_status=gate_status,
        allowed=True,
        next_action=f"Route to `{SKILL_BY_INTENT[intent]}` for `{STAGE_BY_INTENT[intent]}`.",
        reason="Intent detected and no blocking gate applies.",
    )


def render_markdown(route: Route) -> str:
    allowed = "yes" if route.allowed else "no"
    return "\n".join(
        [
            f"Interpreted intent: `{route.intent}`",
            f"Selected stage: `{route.stage}`",
            f"Primary skill: `{route.primary_skill}`",
            f"Allowed now: {allowed}",
            f"Gate status: {route.gate_status}",
            f"Next action: {route.next_action}",
            f"Reason: {route.reason}",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Route a Prof Greg human request to the next stage.")
    parser.add_argument("request", help="Human request text to classify.")
    parser.add_argument("--course", default=DEFAULT_COURSE, help="Course slug.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    route = route_request(args.request, args.course)
    if args.json:
        print(json.dumps(asdict(route), indent=2, ensure_ascii=False))
    else:
        print(render_markdown(route))
    return 0 if route.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
