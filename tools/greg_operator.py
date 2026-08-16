#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from greg_security import assert_safe_run_slug
from greg_server_status import LOCAL_JOB_ROOT, SERVER_JOB_ROOT, create_job, list_jobs, safe_job_root, transition_job


ROOT = Path(__file__).resolve().parents[1]
SERVER_DEFAULT = Path("/srv/profgreg/jobs")


@dataclass
class OperatorResult:
    action: str
    allowed: bool
    message: str
    job: dict[str, Any] | None = None
    route: dict[str, Any] | None = None
    status: dict[str, Any] | None = None
    jobs: list[dict[str, Any]] | None = None


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def default_job_root() -> Path:
    return SERVER_DEFAULT if SERVER_DEFAULT.exists() else LOCAL_JOB_ROOT


def route_request_text(request: str, course_slug: str) -> dict[str, Any]:
    router = load_module("greg_route_request", "tools/greg_route_request.py")
    return asdict(router.route_request(request, course_slug))


def course_status(course_slug: str) -> dict[str, Any]:
    status = load_module("greg_course_status", "tools/greg_course_status.py")
    return status.summarize(course_slug)


def enqueue_job(
    *,
    job_root: Path,
    request_type: str,
    course_slug: str | None = None,
    lesson: int | None = None,
    requested_by: str = "operator",
    summary: str = "",
    payload: dict[str, Any] | None = None,
) -> OperatorResult:
    job = create_job(
        job_root=job_root,
        request_type=request_type,
        course_slug=course_slug,
        lesson=lesson,
        requested_by=requested_by,
        input_summary=summary,
        payload=payload,
    )
    return OperatorResult(
        action="enqueue",
        allowed=True,
        message=f"Job queued: {job['job_id']}",
        job=job,
    )


def request_to_job_type(route: dict[str, Any]) -> str | None:
    intent = route.get("intent")
    if intent == "status":
        return "course_status"
    if intent in {"study_guide", "review", "docx_pdf", "sources"}:
        return "lesson_lifecycle"
    if intent == "process_review":
        return "lesson_lifecycle"
    return None


def handle_request(request: str, *, course_slug: str, lesson: int, job_root: Path, enqueue: bool) -> OperatorResult:
    course_slug = assert_safe_run_slug(course_slug)
    route = route_request_text(request, course_slug)
    if not route.get("allowed"):
        return OperatorResult(
            action="request",
            allowed=False,
            message=route.get("next_action", "Request is blocked by a gate."),
            route=route,
        )
    job_type = request_to_job_type(route)
    if not enqueue or not job_type:
        status = course_status(course_slug)
        return OperatorResult(
            action="request",
            allowed=True,
            message=route.get("next_action", "Request interpreted."),
            route=route,
            status=status,
        )
    return enqueue_job(
        job_root=job_root,
        request_type=job_type,
        course_slug=course_slug,
        lesson=lesson,
        summary=f"operator request: {request[:220]}",
    )


def render_markdown(result: OperatorResult) -> str:
    lines = [
        f"Action: `{result.action}`",
        f"Allowed: {'yes' if result.allowed else 'no'}",
        f"Message: {result.message}",
    ]
    if result.job:
        lines.extend(
            [
                "",
                "Job:",
                f"- id: `{result.job['job_id']}`",
                f"- state: `{result.job['state']}`",
                f"- type: `{result.job['request_type']}`",
            ]
        )
        if result.job.get("course_slug"):
            lines.append(f"- course: `{result.job['course_slug']}`")
        if result.job.get("lesson"):
            lines.append(f"- lesson: {result.job['lesson']}")
    if result.route:
        lines.extend(
            [
                "",
                "Route:",
                f"- intent: `{result.route.get('intent')}`",
                f"- stage: `{result.route.get('stage')}`",
                f"- gate: {result.route.get('gate_status')}",
            ]
        )
    if result.status:
        lines.extend(
            [
                "",
                "Course:",
                f"- stage: `{result.status.get('stage')}`",
                f"- gate: {result.status.get('gate_status')}",
                f"- next: {result.status.get('next_recommended_action')}",
            ]
        )
    if result.jobs is not None:
        lines.extend(["", "Jobs:"])
        if not result.jobs:
            lines.append("- none")
        for job in result.jobs:
            lesson = f" lesson={job.get('lesson')}" if job.get("lesson") else ""
            course = f" course={job.get('course_slug')}" if job.get("course_slug") else ""
            lines.append(f"- `{job['job_id']}` {job['state']} {job.get('request_type')}{course}{lesson}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prof Greg operator interface for status, gates, and server jobs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_options(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--job-root", default=str(default_job_root()))
        subparser.add_argument("--json", action="store_true")

    status_parser = subparsers.add_parser("status", help="Show course status.")
    status_parser.add_argument("--course", required=True)
    add_common_options(status_parser)

    request_parser = subparsers.add_parser("request", help="Interpret a natural-language request.")
    request_parser.add_argument("request")
    request_parser.add_argument("--course", required=True)
    request_parser.add_argument("--lesson", type=int, default=1)
    request_parser.add_argument("--enqueue", action="store_true", help="Queue a safe job when the request maps to one.")
    add_common_options(request_parser)

    backup_parser = subparsers.add_parser("backup", help="Queue a backup job.")
    backup_parser.add_argument("--summary", default="operator backup request")
    add_common_options(backup_parser)

    lifecycle_parser = subparsers.add_parser("lesson-lifecycle", help="Queue safe lesson lifecycle QA/canonical work.")
    lifecycle_parser.add_argument("--course", required=True)
    lifecycle_parser.add_argument("--lesson", type=int, default=1)
    lifecycle_parser.add_argument("--summary", default="operator lesson lifecycle request")
    add_common_options(lifecycle_parser)

    jobs_parser = subparsers.add_parser("jobs", help="List jobs.")
    jobs_parser.add_argument("--limit", type=int, default=20)
    add_common_options(jobs_parser)

    cancel_parser = subparsers.add_parser("cancel", help="Cancel a queued/running/approval job.")
    cancel_parser.add_argument("job_id")
    cancel_parser.add_argument("--note", default="operator cancelled job")
    add_common_options(cancel_parser)
    args = parser.parse_args()
    job_root = safe_job_root(Path(args.job_root))

    if args.command == "status":
        result = OperatorResult("status", True, "Course status loaded.", status=course_status(args.course))
    elif args.command == "request":
        result = handle_request(args.request, course_slug=args.course, lesson=args.lesson, job_root=job_root, enqueue=args.enqueue)
    elif args.command == "backup":
        result = enqueue_job(job_root=job_root, request_type="backup", summary=args.summary)
    elif args.command == "lesson-lifecycle":
        result = enqueue_job(
            job_root=job_root,
            request_type="lesson_lifecycle",
            course_slug=assert_safe_run_slug(args.course),
            lesson=args.lesson,
            summary=args.summary,
        )
    elif args.command == "jobs":
        jobs = list_jobs(job_root)[-args.limit :]
        result = OperatorResult("jobs", True, f"Loaded {len(jobs)} job(s).", jobs=jobs)
    elif args.command == "cancel":
        job = transition_job(job_root, args.job_id, "cancelled", note=args.note)
        result = OperatorResult("cancel", True, f"Job cancelled: {args.job_id}", job=job)
    else:
        raise SystemExit(f"Unsupported command: {args.command}")

    data = asdict(result)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(result), end="")
    return 0 if result.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
