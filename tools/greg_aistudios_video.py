#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from greg_aistudios_api import AiStudiosClient, AiStudiosCredentials, AiStudiosError, validate_presentation
from greg_aistudios_pilot import sha256_file, utc_now, validate_generated_project, wait_for_creation, wait_for_export, write_json


ROOT = Path(__file__).resolve().parents[1]
MAX_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 15
LOCALE_SUFFIX = {"en": "EN", "pt": "PT-BR", "es": "ES"}
ATTENTION_ERRORS = (
    "unexpected template",
    "unexpected avatar",
    "without scenes",
    "approved gregory orange",
    "valid https download url",
)


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise AiStudiosError(f"Invalid Video Generator state: {path.name}.") from error
    return value if isinstance(value, dict) else {}


def project_name(lesson: int, title: str, locale: str) -> str:
    clean_title = " ".join(str(title or f"Lesson {lesson:02d}").split())
    return f"Lesson {lesson:02d} - {clean_title} - {LOCALE_SUFFIX[locale]}"


def lane_paths(course_slug: str, lesson: int, locale: str) -> tuple[Path, Path]:
    lane = f"lesson_{lesson:02d}_{locale}"
    return (
        ROOT / "runs" / course_slug / "video_generator" / f"{lane}.json",
        ROOT / "runtime" / "aistudios" / course_slug / f"{lane}_upload.json",
    )


def initial_state(
    *, course_slug: str, lesson: int, locale: str, source: Path, source_hash: str, title: str, previous: dict[str, Any]
) -> dict[str, Any]:
    stat = source.stat()
    history = list(previous.get("history") or [])
    previous_hash = str(previous.get("sourceSha256") or "")
    if previous_hash and previous_hash != source_hash:
        history.append(
            {
                "sourceSha256": previous_hash,
                "aiStudiosProjectId": str(previous.get("aiStudiosProjectId") or ""),
                "downloadUrl": str(previous.get("downloadUrl") or ""),
                "completedAt": str(previous.get("completedAt") or previous.get("updatedAt") or ""),
            }
        )
    return {
        "version": 1,
        "courseSlug": course_slug,
        "lesson": f"{lesson:02d}",
        "locale": locale,
        "status": "queued",
        "sourcePath": source.relative_to(ROOT).as_posix(),
        "sourceSha256": source_hash,
        "sourceSizeBytes": stat.st_size,
        "sourceModifiedNs": stat.st_mtime_ns,
        "projectName": project_name(lesson, title, locale),
        "attemptCount": 0,
        "history": history[-10:],
        "createdAt": utc_now(),
        "updatedAt": utc_now(),
    }


def needs_attention(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in ATTENTION_ERRORS)


def run_video(
    *, course_slug: str, lesson: int, locale: str, presentation: Path, title: str, sleep=time.sleep
) -> dict[str, Any]:
    source = validate_presentation(presentation)
    try:
        source.relative_to(ROOT)
    except ValueError as error:
        raise AiStudiosError("Approved presentation must stay inside the Prof Greg run workspace.") from error
    source_hash = sha256_file(source)
    state_path, private_path = lane_paths(course_slug, lesson, locale)
    config = load_json(ROOT / "workspace" / "config" / "aistudios.json")
    if not config.get("workspace") or not config.get("template") or not config.get("avatar"):
        raise AiStudiosError("AI Studios approved workspace, template, or avatar configuration is missing.")
    previous = load_json(state_path)
    same_source = str(previous.get("sourceSha256") or "") == source_hash
    if same_source and previous.get("status") == "video_ready" and previous.get("downloadUrl"):
        return previous
    state = previous if same_source else initial_state(
        course_slug=course_slug,
        lesson=lesson,
        locale=locale,
        source=source,
        source_hash=source_hash,
        title=title,
        previous=previous,
    )
    client = AiStudiosClient(AiStudiosCredentials.from_environment())
    last_error: Exception | None = None
    start_attempt = min(int(state.get("attemptCount") or 0), MAX_ATTEMPTS - 1)
    for attempt in range(start_attempt + 1, MAX_ATTEMPTS + 1):
        state.update({"attemptCount": attempt, "errorSummary": "", "updatedAt": utc_now()})
        write_json(state_path, state)
        try:
            project_id = str(state.get("aiStudiosProjectId") or "")
            if not project_id:
                state.update({"status": "uploading", "updatedAt": utc_now()})
                write_json(state_path, state)
                uploaded = client.upload_presentation(source)
                write_json(
                    private_path,
                    {"sourceSha256": source_hash, "uploadedFile": uploaded, "createdAt": utc_now()},
                    private=True,
                )
                state.update({"status": "configuring", "uploadedFileName": uploaded["fileName"], "updatedAt": utc_now()})
                write_json(state_path, state)
                uploaded["fileName"] = str(state["projectName"]) + ".pptx"
                project_id = client.create_docs_project(
                    uploaded,
                    locale=locale,
                    template_id=str(config["template"]["id"]),
                    model_id=str(config["avatar"]["modelId"]),
                )
                state.update({"status": "generating_transcripts", "aiStudiosProjectId": project_id, "updatedAt": utc_now()})
                write_json(state_path, state)
            if int(state.get("creationProgress") or 0) < 100:
                wait_for_creation(client, project_id, state, state_path)
            project = client.project(project_id)
            validate_generated_project(project, config)
            state.update({"status": "exporting", "validatedAt": utc_now(), "updatedAt": utc_now()})
            write_json(state_path, state)
            export_id = str(state.get("aiStudiosExportProjectId") or "")
            if not export_id:
                export_id = client.export_project(project_id, workspace_id=str(config["workspace"]["id"]))
                state["aiStudiosExportProjectId"] = export_id
                write_json(state_path, state)
            download_url = wait_for_export(client, export_id, state, state_path)
            state.update({"status": "video_ready", "downloadUrl": download_url, "completedAt": utc_now(), "updatedAt": utc_now()})
            write_json(state_path, state)
            return state
        except Exception as error:
            last_error = error
            attention = needs_attention(error)
            state.update(
                {
                    "status": "needs_attention" if attention else "failed",
                    "errorSummary": str(error)[:240],
                    "updatedAt": utc_now(),
                }
            )
            write_json(state_path, state)
            if attention or attempt >= MAX_ATTEMPTS:
                break
            sleep(RETRY_BACKOFF_SECONDS)
    raise AiStudiosError(str(last_error or "AI Studios video generation failed."))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate one approved Prof Greg presentation video through AI Studios.")
    parser.add_argument("--course-slug", required=True)
    parser.add_argument("--lesson", required=True, type=int)
    parser.add_argument("--locale", required=True, choices=sorted(LOCALE_SUFFIX))
    parser.add_argument("--presentation", required=True)
    parser.add_argument("--title", required=True)
    args = parser.parse_args()
    try:
        state = run_video(
            course_slug=args.course_slug,
            lesson=args.lesson,
            locale=args.locale,
            presentation=Path(args.presentation),
            title=args.title,
        )
    except (AiStudiosError, OSError, ValueError) as error:
        print(f"AI Studios video generation stopped safely: {error}", file=sys.stderr)
        return 1
    print(str(state.get("downloadUrl") or ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
