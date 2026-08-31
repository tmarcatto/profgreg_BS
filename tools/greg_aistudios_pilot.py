#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from greg_aistudios_api import AiStudiosClient, AiStudiosCredentials, AiStudiosError, validate_presentation


ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any], *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if private:
        temporary.chmod(0o600)
    temporary.replace(path)
    if private:
        path.chmod(0o600)


def approved_deck(course_slug: str, lesson: int, requested: Path) -> Path:
    source = validate_presentation(requested)
    approval = ROOT / "runs" / course_slug / "approval" / f"lesson_{lesson:02d}_deck_approval.md"
    if not approval.is_file():
        raise AiStudiosError("The presentation does not have a recorded deck approval.")
    approval_text = approval.read_text(encoding="utf-8")
    relative = source.relative_to(ROOT).as_posix()
    if "Status: approved" not in approval_text or f"Artifact: {relative}" not in approval_text:
        raise AiStudiosError("The selected presentation is not the approved canonical deck.")
    return source


def upload(args: argparse.Namespace) -> int:
    source = approved_deck(args.course_slug, args.lesson, Path(args.presentation))
    locale = args.locale
    lane_dir = ROOT / "runs" / args.course_slug / "video_generator"
    state_path = lane_dir / f"lesson_{args.lesson:02d}_{locale}.json"
    private_path = ROOT / "runtime" / "aistudios" / args.course_slug / f"lesson_{args.lesson:02d}_{locale}_upload.json"
    source_hash = sha256_file(source)
    stat = source.stat()
    state: dict[str, Any] = {
        "version": 1,
        "courseSlug": args.course_slug,
        "lesson": f"{args.lesson:02d}",
        "locale": locale,
        "status": "uploading",
        "sourcePath": source.relative_to(ROOT).as_posix(),
        "sourceSha256": source_hash,
        "sourceSizeBytes": stat.st_size,
        "sourceModifiedNs": stat.st_mtime_ns,
        "attemptCount": 1,
        "createdAt": utc_now(),
        "updatedAt": utc_now(),
    }
    write_json(state_path, state)
    try:
        result = AiStudiosClient(AiStudiosCredentials.from_environment()).upload_presentation(source)
        private_payload = {
            "sourceSha256": source_hash,
            "uploadedFile": result,
            "createdAt": utc_now(),
        }
        write_json(private_path, private_payload, private=True)
        state.update(
            {
                "status": "configuring",
                "uploadReferenceSha256": hashlib.sha256(result["uri"].encode("utf-8")).hexdigest(),
                "uploadedFileName": result["fileName"],
                "updatedAt": utc_now(),
            }
        )
        write_json(state_path, state)
    except Exception as error:
        state.update({"status": "failed", "errorSummary": str(error)[:240], "updatedAt": utc_now()})
        write_json(state_path, state)
        raise
    print("Approved presentation uploaded. Transcript generation has not started.")
    return 0


def validate_generated_project(project: dict[str, Any], config: dict[str, Any]) -> None:
    scenes = project.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise AiStudiosError("AI Studios generated a project without scenes.")
    expected_template = config["template"]["id"]
    actual_template = str(project.get("templateId") or "")
    if actual_template and actual_template != expected_template:
        raise AiStudiosError("AI Studios generated the project with an unexpected template.")
    expected_model = config["avatar"]["modelId"]
    expected_clothing = config["avatar"]["clothingId"]
    avatar_models: list[dict[str, Any]] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        for clip in scene.get("clips") or []:
            if isinstance(clip, dict) and clip.get("type") == "aiModel" and isinstance(clip.get("model"), dict):
                avatar_models.append(clip["model"])
    if not avatar_models:
        raise AiStudiosError("AI Studios generated the project without the approved avatar.")
    if any(str(model.get("ai_name") or "") != expected_model for model in avatar_models):
        raise AiStudiosError("AI Studios generated the project with an unexpected avatar.")
    clothing_values = {str(model.get("emotion") or "") for model in avatar_models}
    if clothing_values != {expected_clothing}:
        raise AiStudiosError("AI Studios did not apply the approved Gregory Orange variant.")


def wait_for_creation(client: AiStudiosClient, project_id: str, state: dict[str, Any], state_path: Path) -> None:
    deadline = time.monotonic() + 30 * 60
    last_progress = -1
    while time.monotonic() < deadline:
        progress = client.creation_progress(project_id)
        state_name = str(progress.get("state") or "").lower()
        try:
            percent = int(float(progress.get("progress") or 0))
        except (TypeError, ValueError):
            percent = 0
        if percent != last_progress:
            print(f"Transcript generation: {percent}%", flush=True)
            last_progress = percent
        state.update({"creationState": state_name, "creationProgress": percent, "updatedAt": utc_now()})
        write_json(state_path, state)
        if state_name in {"error", "failed", "fail"}:
            raise AiStudiosError("AI Studios reported a transcript generation failure.")
        if state_name in {"finish", "finished", "complete", "completed"} and percent >= 100:
            return
        time.sleep(10)
    raise AiStudiosError("AI Studios transcript generation did not finish within 30 minutes.")


def wait_for_export(client: AiStudiosClient, project_id: str, state: dict[str, Any], state_path: Path) -> str:
    deadline = time.monotonic() + 30 * 60
    last_progress = -1
    while time.monotonic() < deadline:
        progress = client.export_progress(project_id)
        state_name = str(progress.get("state") or "").lower()
        try:
            percent = int(float(progress.get("progress") or 0))
        except (TypeError, ValueError):
            percent = 0
        if percent != last_progress:
            print(f"Video export: {percent}%", flush=True)
            last_progress = percent
        state.update({"exportState": state_name, "exportProgress": percent, "updatedAt": utc_now()})
        write_json(state_path, state)
        if state_name in {"error", "failed", "fail"}:
            raise AiStudiosError("AI Studios reported a video export failure.")
        if percent >= 100:
            return client.completed_export_url(project_id)
        time.sleep(10)
    raise AiStudiosError("AI Studios video export did not finish within 30 minutes.")


def complete(args: argparse.Namespace) -> int:
    lane = f"lesson_{args.lesson:02d}_{args.locale}"
    state_path = ROOT / "runs" / args.course_slug / "video_generator" / f"{lane}.json"
    private_path = ROOT / "runtime" / "aistudios" / args.course_slug / f"{lane}_upload.json"
    config_path = ROOT / "workspace" / "config" / "aistudios.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    private = json.loads(private_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if state.get("status") != "configuring":
        raise AiStudiosError("The lane is not waiting for Docs-to-Video configuration.")
    if private.get("sourceSha256") != state.get("sourceSha256"):
        raise AiStudiosError("The protected upload reference does not match the approved presentation.")
    uploaded_file = dict(private.get("uploadedFile") or {})
    if not uploaded_file.get("uri"):
        raise AiStudiosError("The protected upload reference is missing.")
    uploaded_file["fileName"] = args.project_name + ".pptx"
    client = AiStudiosClient(AiStudiosCredentials.from_environment())
    try:
        project_id = client.create_docs_project(
            uploaded_file,
            locale=args.locale,
            template_id=config["template"]["id"],
            model_id=config["avatar"]["modelId"],
        )
        state.update(
            {
                "status": "generating_transcripts",
                "aiStudiosProjectId": project_id,
                "projectName": args.project_name,
                "updatedAt": utc_now(),
            }
        )
        write_json(state_path, state)
        print("Docs-to-Video project created.", flush=True)
        wait_for_creation(client, project_id, state, state_path)
        project = client.project(project_id)
        validate_generated_project(project, config)
        state.update({"status": "exporting", "validatedAt": utc_now(), "updatedAt": utc_now()})
        write_json(state_path, state)
        print("Project validated. Starting video export.", flush=True)
        export_project_id = client.export_project(project_id, workspace_id=config["workspace"]["id"])
        if export_project_id != project_id:
            state["aiStudiosExportProjectId"] = export_project_id
        download_url = wait_for_export(client, export_project_id, state, state_path)
        state.update(
            {
                "status": "video_ready",
                "downloadUrl": download_url,
                "completedAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )
        write_json(state_path, state)
    except Exception as error:
        state.update({"status": "needs_attention", "errorSummary": str(error)[:240], "updatedAt": utc_now()})
        write_json(state_path, state)
        raise
    print(download_url, flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run explicitly approved AI Studios pilot boundaries.")
    subparsers = parser.add_subparsers(dest="action", required=True)
    upload_parser = subparsers.add_parser("upload", help="Upload one approved PPTX without creating a project.")
    upload_parser.add_argument("--course-slug", required=True)
    upload_parser.add_argument("--lesson", required=True, type=int)
    upload_parser.add_argument("--locale", required=True, choices=("en", "pt", "es"))
    upload_parser.add_argument("--presentation", required=True)
    upload_parser.set_defaults(handler=upload)
    complete_parser = subparsers.add_parser("complete", help="Create, validate, export, and wait for one uploaded pilot video.")
    complete_parser.add_argument("--course-slug", required=True)
    complete_parser.add_argument("--lesson", required=True, type=int)
    complete_parser.add_argument("--locale", required=True, choices=("en", "pt", "es"))
    complete_parser.add_argument("--project-name", required=True)
    complete_parser.set_defaults(handler=complete)
    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except (AiStudiosError, OSError, ValueError) as error:
        print(f"AI Studios pilot stopped safely: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
