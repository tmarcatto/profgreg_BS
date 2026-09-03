#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import mimetypes
import os
import re
import shutil
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from greg_operator import course_status, default_job_root, enqueue_job, handle_request
from greg_record_approval import record_approval
from greg_server_status import list_jobs, pause_worker_lane, resume_worker_lane, safe_job_root, worker_control_status
from greg_create_run import create_run, slugify
from greg_localized_deck_guard import LocalizedDeckIntegrityError, localized_deck_context, validate_localized_deck
from greg_marketing import marketing_status, save_marketing
from greg_revision_history import append_interaction, read_state, utc_now


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_COURSE = "construction-schedule-management"
ROOT = Path(__file__).resolve().parents[1]
SERVER_UPLOAD_ROOT = Path("/srv/profgreg/uploads")
LOCAL_UPLOAD_ROOT = ROOT / "tmp" / "uploads"
SESSION_RUN_ROOT = ROOT / "runs"
COURSE_SESSION_FILE = "ops/course_session.json"
MAX_UPLOAD_FILE_BYTES = 200 * 1024 * 1024
MAX_UPLOAD_REQUEST_BYTES = 500 * 1024 * 1024
MAX_IMAGE_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp"}
REFERENCE_POLICIES = {
    "context_only": "Use as production context only; do not cite in student references and do not reuse images.",
    "image_only": "Do not cite text in student references; images may be reused when properly referenced.",
    "reference_only": "May appear in student references; do not reuse images.",
    "reference_and_images": "May appear in student references and images may be reused when properly referenced.",
}
DEFAULT_LESSON_COUNT_BY_LEVEL = {"Basic": 10, "Intermediate": 15, "Advanced": 15}
UPLOAD_PURPOSES = {"source_material", "visual_response", "revision_material", "revision_evidence"}


def job_visibility_key(job: dict[str, object]) -> tuple[str, str, int, str]:
    """Identify the exact production attempt that a later success supersedes."""
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    lesson = int(job.get("lesson") or (payload.get("lessons") or [0])[0] or 0)
    stage = str(payload.get("stage") or payload.get("locale") or "")
    return (
        str(job.get("course_slug") or ""),
        str(job.get("request_type") or ""),
        lesson,
        stage,
    )


def operator_visible_jobs(jobs: list[dict[str, object]], *, limit: int = 200) -> list[dict[str, object]]:
    """Hide failed attempts that were superseded by a later successful retry."""
    latest_completed_by_type: dict[tuple[str, str, int, str], str] = {}
    for job in jobs:
        if job.get("state") != "completed":
            continue
        key = job_visibility_key(job)
        timestamp = str(job.get("updated_at") or job.get("created_at") or "")
        if timestamp > latest_completed_by_type.get(key, ""):
            latest_completed_by_type[key] = timestamp

    visible: list[dict[str, object]] = []
    for job in jobs:
        key = job_visibility_key(job)
        timestamp = str(job.get("updated_at") or job.get("created_at") or "")
        if job.get("state") == "failed" and latest_completed_by_type.get(key, "") > timestamp:
            continue
        visible.append(job)
    return visible[-limit:]


def recent_worker_errors(jobs: list[dict[str, object]], *, limit: int = 10) -> list[dict[str, object]]:
    """Return the latest failed worker jobs without hiding superseded attempts."""
    failed = [
        job for job in jobs
        if job.get("state") == "failed" and str(job.get("lane") or "") in {"content", "delivery", "video"}
    ]
    failed.sort(
        key=lambda job: str(job.get("updated_at") or job.get("created_at") or ""),
        reverse=True,
    )
    return failed[:limit]


def enqueue_production_lesson_jobs(
    *,
    job_root: Path,
    course: str,
    stage: str,
    lessons: list[int],
) -> list[dict[str, object]]:
    """Queue each lesson and locale independently so one failure cannot consume a batch."""
    jobs: list[dict[str, object]] = []
    stages = {
        "translations_book": ("pt_br_book", "es_book"),
        "translations_deck": ("pt_br_deck", "es_deck"),
    }.get(stage, (stage,))
    for lesson in lessons:
        for queued_stage in stages:
            result = enqueue_job(
                job_root=job_root,
                request_type="production_stage",
                course_slug=course,
                lesson=lesson,
                summary=f"operator requested {queued_stage} for lesson {lesson}",
                payload={"stage": queued_stage, "lessons": [lesson]},
            )
            if result.job:
                jobs.append(result.job)
    return jobs


def json_bytes(data: object) -> bytes:
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")


def read_request_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(min(length, 1024 * 1024))
    return json.loads(raw.decode("utf-8") or "{}")


def parse_content_disposition(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in value.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        key, raw = part.split("=", 1)
        result[key.strip().lower()] = raw.strip().strip('"')
    return result


def parse_multipart_form(content_type: str, body: bytes) -> tuple[dict[str, str], list[dict[str, object]]]:
    match = re.search(r"boundary=(?P<boundary>[^;]+)", content_type)
    if not match:
        raise ValueError("Missing multipart boundary.")
    boundary = ("--" + match.group("boundary").strip().strip('"')).encode("utf-8")
    fields: dict[str, str] = {}
    files: list[dict[str, object]] = []
    for raw_part in body.split(boundary):
        part = raw_part.strip()
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].strip()
        header_blob, separator, content = part.partition(b"\r\n\r\n")
        if not separator:
            continue
        headers = header_blob.decode("utf-8", errors="replace").split("\r\n")
        disposition = ""
        for header in headers:
            if header.lower().startswith("content-disposition:"):
                disposition = header.split(":", 1)[1].strip()
                break
        data = parse_content_disposition(disposition)
        name = data.get("name")
        if not name:
            continue
        content = content.rstrip(b"\r\n")
        filename = data.get("filename")
        if filename:
            files.append({"name": name, "filename": filename, "data": content})
        else:
            fields[name] = content.decode("utf-8", errors="replace")
    return fields, files


def safe_upload_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    local = LOCAL_UPLOAD_ROOT.resolve()
    server = SERVER_UPLOAD_ROOT.resolve()
    if resolved == local or local in resolved.parents:
        return resolved
    if resolved == server or server in resolved.parents:
        return resolved
    raise ValueError(f"Upload root must stay under {server} or {local}: {path}")


def course_session_path(course_slug: str) -> Path:
    return SESSION_RUN_ROOT / slugify(course_slug) / COURSE_SESSION_FILE


def read_course_session(course_slug: str) -> dict:
    path = course_session_path(course_slug)
    if not path.exists():
        return {"status": "active"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "active"}
    return data if isinstance(data, dict) else {"status": "active"}


def write_course_session(course_slug: str, status: str) -> None:
    path = course_session_path(course_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"status": status, "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}, indent=2) + "\n", encoding="utf-8")


def workspace_intake_path(run: Path) -> Path | None:
    """Return the intake marker used by either the current or earlier run layouts."""
    for path in (run / "intake.md", run / "input" / "intake.md"):
        if path.exists():
            return path
    return None


def list_course_workspaces() -> list[dict]:
    workspaces: list[dict] = []
    if not SESSION_RUN_ROOT.exists():
        return workspaces
    for run in SESSION_RUN_ROOT.iterdir():
        if not run.is_dir() or run.name.startswith("_"):
            continue
        intake = workspace_intake_path(run)
        if intake is None:
            continue
        title = next((line[2:].strip() for line in intake.read_text(encoding="utf-8", errors="replace").splitlines() if line.startswith("# ")), run.name)
        session = read_course_session(run.name)
        workspaces.append({
            "course_slug": run.name,
            "title": title,
            "status": "completed" if session.get("status") == "completed" else "active",
            "updated_at": datetime.fromtimestamp(run.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    workspaces.sort(key=lambda item: item["updated_at"], reverse=True)
    workspaces.sort(key=lambda item: item["status"] == "completed")
    return workspaces


def model_usage_path(course_slug: str) -> Path:
    return SESSION_RUN_ROOT / slugify(course_slug) / "ops" / "model_usage_log.jsonl"


def course_cost_report(course_slug: str) -> dict:
    """Return request-level AI spend for one workspace only."""
    path = model_usage_path(course_slug)
    rows: list[dict] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                # Older logs predate the cost field. Recalculate them from the
                # current versioned rate card so historic course spend is not
                # silently omitted from the workspace total.
                if item.get("outcome") == "completed" and item.get("usage") and not item.get("cost"):
                    try:
                        from greg_model_router import cost_estimate
                        item["cost"] = cost_estimate(
                            {"provider": item.get("provider"), "model": item.get("model")},
                            item["usage"],
                        )
                    except Exception:
                        item["cost"] = {"currency": "USD", "status": "unpriced"}
                rows.append(item)
    rows.sort(key=lambda item: str(item.get("at") or ""), reverse=True)
    completed = [item for item in rows if item.get("outcome") == "completed"]
    # Recalculate every completed request using the active, versioned rate card.
    # This also enriches older cost entries with their component math.
    for item in completed:
        if not item.get("usage"):
            continue
        try:
            from greg_model_router import cost_estimate
            item["cost"] = cost_estimate(
                {"provider": item.get("provider"), "model": item.get("model")}, item["usage"]
            )
        except Exception:
            item["cost"] = {"currency": "USD", "status": "unpriced"}
    priced = [item for item in completed if isinstance(item.get("cost"), dict) and item["cost"].get("status") == "estimated"]
    total = sum(float(item["cost"].get("estimated_usd") or 0) for item in priced)
    provider_totals: dict[tuple[str, str], float] = {}
    math: dict[tuple[str, str], dict] = {}
    for item in priced:
        key = (str(item.get("provider") or "Unknown"), str(item.get("model") or "Unknown"))
        provider_totals[key] = provider_totals.get(key, 0) + float(item["cost"].get("estimated_usd") or 0)
        usage = item.get("usage") or {}
        row = math.setdefault(key, {"provider": key[0], "model": key[1], "calls": 0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "images": 0, "web_search_runs": 0, "components": {}})
        row["calls"] += 1
        row["input_tokens"] += int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
        row["cached_tokens"] += int(usage.get("cache_read_input_tokens") or (details.get("cached_tokens") if isinstance(details, dict) else 0) or 0)
        row["output_tokens"] += int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        row["images"] += int(usage.get("images") or 0)
        row["web_search_runs"] += int(usage.get("web_search_runs") or 0)
        for name, value in (item["cost"].get("components") or {}).items():
            row["components"][name] = round(float(row["components"].get(name) or 0) + float(value or 0), 8)
    return {
        "course_slug": slugify(course_slug), "currency": "USD", "total_estimated_usd": round(total, 8),
        "request_count": len(rows), "completed_count": len(completed), "unpriced_completed_count": len(completed) - len(priced),
        "providers": [{"provider": provider, "model": model, "estimated_usd": round(value, 8)} for (provider, model), value in sorted(provider_totals.items())],
        "math": [{**item, "estimated_usd": round(provider_totals[key], 8)} for key, item in sorted(math.items())],
        "recent_requests": rows[:10],
    }


def safe_filename(value: str) -> str:
    name = Path(value or "uploaded-file").name
    clean = re.sub(r"[^a-zA-Z0-9._ -]+", "-", name).strip(" .-_")
    if not clean:
        clean = "uploaded-file"
    suffix = Path(clean).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError(f"Unsupported upload type: {suffix or '[none]'}")
    return clean[:120]


def validate_image_upload(filename: str, data: bytes) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        return
    if len(data) > MAX_IMAGE_UPLOAD_BYTES:
        raise ValueError(f"Image is too large. Maximum image size is {MAX_IMAGE_UPLOAD_BYTES // (1024 * 1024)} MB.")
    valid = {
        ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": data.startswith(b"\xff\xd8\xff"),
        ".jpeg": data.startswith(b"\xff\xd8\xff"),
        ".webp": len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }[suffix]
    if not valid:
        raise ValueError("The selected image extension does not match the file contents.")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upload_course_dir(upload_root: Path, course_slug: str) -> Path:
    return safe_upload_root(upload_root) / slugify(course_slug)


def upload_manifest_path(upload_root: Path, course_slug: str) -> Path:
    return upload_course_dir(upload_root, course_slug) / "upload_manifest.jsonl"


def safe_artifact_path(value: str) -> Path:
    raw = unquote(value or "").strip()
    if not raw:
        raise ValueError("Missing artifact path.")
    path = Path(raw)
    if path.is_absolute():
        resolved = path.resolve()
    else:
        resolved = (ROOT / path).resolve()
    runs_root = (ROOT / "runs").resolve()
    if resolved != runs_root and runs_root not in resolved.parents:
        raise ValueError("Artifact download must stay inside the runs folder.")
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"Artifact not found: {raw}")
    localized_context = localized_deck_context(resolved, runs_root)
    if localized_context:
        run, lesson_tag = localized_context
        validate_localized_deck(run, lesson_tag, resolved)
    return resolved


def safe_download_filename(value: str, fallback: str) -> str:
    raw = unquote(value or "").strip() or fallback
    name = re.sub(r"[^\w .()\-]+", "-", raw, flags=re.UNICODE).strip(" .-")
    return name or fallback


def blocked_localized_deck_page() -> bytes:
    return """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tradução bloqueada</title>
  <style>
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f5f7fa; color: #1f2937; font-family: Inter, system-ui, sans-serif; }
    main { width: min(640px, calc(100% - 40px)); padding: 36px; border: 1px solid #d8e0ea; border-radius: 16px; background: white; box-shadow: 0 8px 24px rgba(16, 24, 40, .08); }
    h1 { margin-top: 0; color: #1e3a5f; }
    p { line-height: 1.55; }
    a { display: inline-block; margin-top: 12px; padding: 11px 16px; border-radius: 8px; background: #f07800; color: white; font-weight: 700; text-decoration: none; }
  </style>
</head>
<body>
  <main>
    <h1>Esta tradução precisa ser gerada novamente</h1>
    <p>O arquivo anterior foi bloqueado porque não corresponde à apresentação em inglês aprovada. Isso impede que uma versão errada seja baixada.</p>
    <p>Volte ao Prof Greg, atualize a página e gere novamente as apresentações traduzidas. O novo arquivo será produzido somente a partir da versão aprovada.</p>
    <a href="/">Voltar ao Prof Greg</a>
  </main>
</body>
</html>""".encode("utf-8")


def upload_identifier(meta: dict) -> str:
    stable = f"{meta.get('stored_path', '')}|{meta.get('sha256', '')}|{meta.get('filename', '')}"
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]


def normalize_reference_policy(policy: str) -> str:
    return policy if policy in REFERENCE_POLICIES else "context_only"


def apply_reference_policy(meta: dict, policy: str) -> dict:
    normalized = normalize_reference_policy(policy)
    meta["reference_policy"] = normalized
    meta["reference_policy_label"] = REFERENCE_POLICIES[normalized]
    meta["can_appear_in_references"] = normalized in {"reference_only", "reference_and_images"}
    meta["images_allowed"] = normalized in {"image_only", "reference_and_images"}
    return meta


def normalize_upload_meta(meta: dict) -> dict:
    meta = dict(meta)
    meta["upload_id"] = str(meta.get("upload_id") or upload_identifier(meta))
    apply_reference_policy(meta, str(meta.get("reference_policy") or "context_only"))
    purpose = str(meta.get("purpose") or "source_material")
    meta["purpose"] = purpose if purpose in UPLOAD_PURPOSES else "source_material"
    meta["visual_request_id"] = str(meta.get("visual_request_id") or "")
    meta["revision_artifact_type"] = str(meta.get("revision_artifact_type") or "")
    meta["source_label"] = str(meta.get("source_label") or "")
    meta["source_url"] = str(meta.get("source_url") or "")
    return meta


def parse_visual_source_manifest(value: str) -> dict[str, dict[str, str]]:
    """Parse one `filename | attribution | URL` line per uploaded image."""
    result: dict[str, dict[str, str]] = {}
    for line in (value or "").splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split("|", 2)]
        filename = safe_filename(parts[0])
        if not filename:
            continue
        result[filename.casefold()] = {
            "source_label": parts[1] if len(parts) > 1 else "Operator supplied technical image",
            "source_url": parts[2] if len(parts) > 2 else "",
        }
    return result


def map_visual_batch(files: list[dict[str, object]], request_ids: list[str]) -> list[tuple[dict[str, object], str]]:
    """Map a complete lesson batch by visual ID in filenames, then displayed order."""
    if len(files) != len(request_ids):
        raise ValueError(f"This lesson requires {len(request_ids)} image(s), but {len(files)} file(s) were selected.")
    remaining = list(request_ids)
    mapped: list[tuple[dict[str, object], str]] = []
    for field in files:
        filename = str(field.get("filename") or "")
        explicit = next((request_id for request_id in remaining if request_id.casefold() in filename.casefold()), None)
        request_id = explicit or remaining[0]
        remaining.remove(request_id)
        mapped.append((field, request_id))
    return mapped


def read_upload_manifest(upload_root: Path, course_slug: str) -> list[dict]:
    manifest = upload_manifest_path(upload_root, course_slug)
    if not manifest.exists():
        return []
    return [
        normalize_upload_meta(json.loads(line))
        for line in manifest.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]


def write_upload_manifest(upload_root: Path, course_slug: str, uploads: list[dict]) -> None:
    manifest = upload_manifest_path(upload_root, course_slug)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(normalize_upload_meta(item), ensure_ascii=False) for item in uploads)
    manifest.write_text((text + "\n") if text else "", encoding="utf-8")


def scope_name_from_input(scope: str, lesson: int | None = None) -> str:
    return "course" if scope != "lesson" else f"lesson_{int(lesson or 1):02d}"


def parse_scope_name(scope_name: str) -> tuple[str, int]:
    match = re.fullmatch(r"lesson_(\d{1,2})", scope_name or "")
    if match:
        return "lesson", int(match.group(1))
    return "course", 1


def save_uploaded_file(
    *,
    upload_root: Path,
    course_slug: str,
    filename: str,
    data: bytes,
    scope: str = "course",
    lesson: int | None = None,
    reference_policy: str = "context_only",
    purpose: str = "source_material",
    visual_request_id: str = "",
    revision_artifact_type: str = "",
    source_label: str = "",
    source_url: str = "",
) -> dict:
    if len(data) > MAX_UPLOAD_FILE_BYTES:
        raise ValueError(f"Upload is too large. Maximum per file is {MAX_UPLOAD_FILE_BYTES // (1024 * 1024)} MB.")
    clean_name = safe_filename(filename)
    validate_image_upload(clean_name, data)
    scope_name = scope_name_from_input(scope, lesson)
    policy = normalize_reference_policy(reference_policy)
    target_dir = upload_course_dir(upload_root, course_slug) / scope_name
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / clean_name
    if target.exists():
        target = target_dir / f"{target.stem[:80]}-{hashlib.sha256(data).hexdigest()[:8]}{target.suffix}"
    target.write_bytes(data)
    meta = {
        "course_slug": slugify(course_slug),
        "filename": clean_name,
        "stored_path": str(target),
        "scope": scope_name,
        "reference_policy": policy,
        "reference_policy_label": REFERENCE_POLICIES[policy],
        "can_appear_in_references": policy in {"reference_only", "reference_and_images"},
        "images_allowed": policy in {"image_only", "reference_and_images"},
        "size_bytes": len(data),
        "sha256": file_sha256(target),
        "purpose": purpose if purpose in UPLOAD_PURPOSES else "source_material",
        "visual_request_id": visual_request_id.strip()[:80],
        "revision_artifact_type": revision_artifact_type.strip()[:80],
        "source_label": source_label.strip()[:300],
        "source_url": source_url.strip()[:1000],
    }
    meta["upload_id"] = upload_identifier(meta)
    manifest = upload_manifest_path(upload_root, course_slug)
    with manifest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(meta, ensure_ascii=False) + "\n")
    return meta


def list_uploads(upload_root: Path, course_slug: str) -> list[dict]:
    return read_upload_manifest(upload_root, course_slug)[-100:]


def update_upload_metadata(
    *,
    upload_root: Path,
    course_slug: str,
    upload_id: str,
    scope: str,
    lesson: int | None,
    reference_policy: str,
) -> dict:
    uploads = read_upload_manifest(upload_root, course_slug)
    for item in uploads:
        if item["upload_id"] != upload_id:
            continue
        item["scope"] = scope_name_from_input(scope, lesson)
        apply_reference_policy(item, reference_policy)
        write_upload_manifest(upload_root, course_slug, uploads)
        return normalize_upload_meta(item)
    raise ValueError("Upload not found.")


def delete_uploaded_file(*, upload_root: Path, course_slug: str, upload_id: str) -> dict:
    root = safe_upload_root(upload_root)
    uploads = read_upload_manifest(upload_root, course_slug)
    kept: list[dict] = []
    deleted: dict | None = None
    for item in uploads:
        if item["upload_id"] == upload_id and deleted is None:
            deleted = item
            continue
        kept.append(item)
    if deleted is None:
        raise ValueError("Upload not found.")
    stored = Path(str(deleted.get("stored_path") or "")).expanduser().resolve()
    if stored == root or root in stored.parents:
        try:
            if stored.exists() and stored.is_file():
                stored.unlink()
        except OSError:
            pass
    write_upload_manifest(upload_root, course_slug, kept)
    return deleted


def expected_lesson_count(level: str, requested: int | None = None) -> int:
    if requested and requested > 0:
        return min(requested, 30)
    return DEFAULT_LESSON_COUNT_BY_LEVEL.get(level or "Basic", 10)


def create_course_intake(
    *,
    title: str,
    level: str,
    syllabus: str,
    course_slug: str | None = None,
    expected_lessons: int | None = None,
) -> dict:
    if not title.strip():
        raise ValueError("Course title is required.")
    setup = create_run(title.strip(), course_slug, level or "Basic")
    lesson_count = expected_lesson_count(level or "Basic", expected_lessons)
    intake = ROOT / setup.intake_path
    intake.write_text(
        "\n".join(
            [
                f"# {title.strip()}",
                "",
                f"Course slug: `{setup.course_slug}`",
                f"Course level: {level or 'Basic'}",
                f"Expected lesson count: {lesson_count}",
                "Base language: English",
                "Audience: U.S. residential construction workforce.",
                "Lesson-count rule: Basic courses normally start around 10 lessons; Intermediate and Advanced courses normally start around 15 lessons, with Greg allowed to adapt the final Course Map when research and learning progression justify it.",
                "",
                "## Initial Syllabus Direction",
                "",
                syllabus.strip() or "[Add syllabus direction here.]",
                "",
                "## Uploaded Source Materials",
                "",
                "Uploaded files are stored outside Git under the server upload root and tracked in the upload manifest.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    write_course_session(setup.course_slug, "active")
    return {**setup.__dict__, "message": f"Course intake created: {setup.course_slug}"}


def delete_course_workspace(*, course_slug: str, job_root: Path, upload_root: Path) -> dict:
    """Permanently remove one inactive course and only its associated records."""
    slug = slugify(course_slug)
    runs_root = SESSION_RUN_ROOT.resolve()
    run = (runs_root / slug).resolve()
    if run.parent != runs_root or workspace_intake_path(run) is None:
        raise ValueError("Choose an existing course workspace.")

    jobs_root = safe_job_root(job_root)
    course_jobs = [job for job in list_jobs(jobs_root) if str(job.get("course_slug") or "") == slug]
    active_states = {"queued", "running", "needs_approval"}
    if any(job.get("state") in active_states for job in course_jobs):
        raise ValueError("This course has active work. Wait for it to finish or cancel it before deleting the course.")

    uploads_root = safe_upload_root(upload_root)
    uploads = upload_course_dir(uploads_root, slug).resolve()
    if uploads.parent != uploads_root.resolve():
        raise ValueError("Unsafe course upload path.")

    shutil.rmtree(run)
    if uploads.exists():
        shutil.rmtree(uploads)

    deleted_jobs = 0
    for job in course_jobs:
        job_id = str(job.get("job_id") or "")
        job_dir = (jobs_root / job_id).resolve()
        if job_dir.parent != jobs_root.resolve() or not job_dir.is_dir():
            continue
        shutil.rmtree(job_dir)
        deleted_jobs += 1
    return {"course_slug": slug, "deleted_jobs": deleted_jobs}


def approval_artifact_path(course_slug: str, lesson: int, artifact_type: str) -> str:
    lesson_tag = f"lesson_{lesson:02d}"
    if artifact_type == "study_guide":
        return f"docx_pdf/{lesson_tag}_study_guide.pdf"
    if artifact_type == "deck":
        return f"deck/{lesson_tag}_deck.pptx"
    raise ValueError("Unsupported approval artifact type.")


def record_ui_approval(*, course_slug: str, lesson: int, artifact_type: str, note: str) -> dict:
    artifact = approval_artifact_path(course_slug, lesson, artifact_type)
    return record_approval(
        course_slug,
        lesson,
        artifact_type,
        artifact,
        approver="operator-ui",
        approval_mode="operator_ui_v0",
        note=note or "Approved in Prof Greg Operator.",
        force=True,
    )


def record_ui_artifact_approval(*, course_slug: str, lesson: int, artifact_type: str, artifact: str, note: str) -> dict:
    result = record_approval(
        course_slug,
        lesson,
        artifact_type,
        artifact,
        approver="operator-ui",
        approval_mode="operator_ui_v0",
        note=note or "Approved in Prof Greg Operator.",
        force=True,
    )
    run = ROOT / "runs" / slugify(course_slug)
    lesson_tag = f"lesson_{lesson:02d}"
    state_path = run / "operator_feedback" / f"{lesson_tag}_{artifact_type}_revision_state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
        candidate = str(state.get("candidate_artifact") or "")
        if state.get("state") == "ready_for_review" and candidate and Path(candidate).name == Path(artifact).name:
            state.update({
                "state": "approved",
                "approved_artifact": artifact,
                "approved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            append_interaction(
                state_path,
                "approved",
                message=note or "Operator approved the corrected artifact.",
            )
    return result


def record_revision_request(
    *, course_slug: str, lesson: int, artifact_type: str, note: str, artifact_path: str = "", attachments: list[dict] | None = None,
    requests: list[dict] | None = None,
) -> dict:
    course_slug = slugify(course_slug)
    lesson_tag = f"lesson_{lesson:02d}"
    target = ROOT / "runs" / course_slug / "operator_feedback" / f"{lesson_tag}_{artifact_type}_revision_request.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    attachments = attachments or []
    requests = requests or [{"id": "0", "note": note, "attachments": attachments}]
    prior_requests: list[dict] = []
    prior_state: dict = {}
    state_path = target.with_name(f"{lesson_tag}_{artifact_type}_revision_state.json")
    if state_path.exists():
        try:
            prior_state = read_state(state_path)
            prior_requests = list(prior_state.get("requests") or [])
        except json.JSONDecodeError:
            prior_requests = []
    normalized_requests = []
    requested_at = utc_now()
    used_ids = {str(item.get("id") or "") for item in prior_requests}
    next_id = len(prior_requests) + 1
    for item in requests:
        request_id = str(item.get("id") or "")
        if not request_id or request_id in used_ids:
            while str(next_id) in used_ids:
                next_id += 1
            request_id = str(next_id)
            next_id += 1
        used_ids.add(request_id)
        item_attachments = item.get("attachments") or []
        normalized_requests.append({
            "id": request_id,
            "note": str(item.get("note") or "").strip(),
            "attachments": item_attachments,
            "requested_at": requested_at,
        })
    all_requests = [*prior_requests, *normalized_requests]
    lines = [f"# {lesson_tag} {artifact_type} Revision Requests", "", f"- Course slug: {course_slug}", f"- Lesson: {lesson:02d}", f"- Artifact type: {artifact_type}", ""]
    for number, request in enumerate(all_requests, start=1):
        lines.extend([f"## Request {number}", "", request["note"] or "Revision requested from Prof Greg Operator.", "", "Supporting materials:"])
        if request["attachments"]:
            lines.extend(
                f"- {item.get('filename')} ({item.get('reference_policy')}; {item.get('purpose')})"
                + (f" — {item.get('source_label')}" if item.get("source_label") else "")
                + (f" — {item.get('source_url')}" if item.get("source_url") else "")
                for item in request["attachments"]
            )
        else:
            lines.append("- None.")
        lines.append("")
    target.write_text("\n".join(lines), encoding="utf-8")
    first_accepted_at = str(prior_state.get("accepted_at") or requested_at)
    interactions = list(prior_state.get("interactions") or [])
    interactions.append({
        "type": "request",
        "at": requested_at,
        "requests": [{"id": item["id"], "note": item["note"]} for item in normalized_requests],
    })
    state_path.write_text(
        json.dumps({
            "state": "revision_requested",
            "course_slug": course_slug,
            "lesson": lesson,
            "artifact_type": artifact_type,
            "baseline_artifact": artifact_path,
            "feedback_path": str(target.relative_to(ROOT)),
            "requests": all_requests,
            "request_count": len(all_requests),
            "accepted_at": first_accepted_at,
            "latest_requested_at": requested_at,
            "interactions": interactions,
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"feedback_path": str(target.relative_to(ROOT)), "state_path": str(state_path.relative_to(ROOT)), "attachments": attachments}


def ui_shell(default_course: str) -> str:
    course = html.escape(default_course)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BuildStak Course Agent</title>
  <style>
    :root {{
      --navy: #1E3A5F;
      --navy-2: #27486f;
      --orange: #F07800;
      --orange-soft: #fff3e8;
      --ink: #1f2937;
      --muted: #667085;
      --line: #d8e0ea;
      --soft: #f5f7fa;
      --panel: #ffffff;
      --ok: #157347;
      --warn: #a15c00;
      --bad: #b42318;
      --shadow: 0 1px 2px rgba(16, 24, 40, .06), 0 8px 24px rgba(16, 24, 40, .05);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--soft);
    }}
    header.app {{
      position: sticky;
      top: 0;
      z-index: 10;
      background: var(--navy);
      color: #fff;
      box-shadow: var(--shadow);
    }}
    .topbar {{
      max-width: 1360px;
      margin: 0 auto;
      min-height: 72px;
      padding: 14px 28px 10px;
      display: grid;
      grid-template-columns: minmax(240px, 1fr) auto;
      gap: 24px;
      align-items: center;
    }}
    .brand {{ display: flex; align-items: center; gap: 12px; font-weight: 760; font-size: 18px; }}
    .mark {{
      width: 34px; height: 34px; border: 2px solid var(--orange); border-radius: 8px;
      display: grid; place-items: center; font-size: 15px; color: #fff; font-weight: 800;
      background: rgba(255,255,255,.06);
    }}
    .brand small {{ display: block; color: rgba(255,255,255,.72); font-size: 12px; font-weight: 600; margin-top: 2px; }}
    .top-actions {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }}
    .nav {{
      max-width: 1360px;
      margin: 0 auto;
      padding: 0 28px 12px;
      display: flex;
      gap: 8px;
      overflow-x: auto;
    }}
    .nav a {{
      color: rgba(255,255,255,.82);
      text-decoration: none;
      font-size: 13px;
      font-weight: 720;
      padding: 8px 10px;
      border-radius: 6px;
      white-space: nowrap;
    }}
    .nav a:hover {{ background: rgba(255,255,255,.1); color: #fff; }}
    .nav a.active {{ background: var(--orange); color: #fff; }}
    main {{ padding: 24px 28px 44px; display: grid; gap: 18px; max-width: 1360px; margin: 0 auto; }}
    .console-page {{ display: none; gap: 18px; }}
    .console-page.active {{ display: grid; }}
    input, textarea, button, select {{
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
    }}
    input, textarea, select {{ padding: 10px 12px; color: var(--ink); background: #fff; min-width: 0; max-width: 100%; }}
    textarea {{ width: 100%; resize: vertical; }}
    button {{
      padding: 10px 14px;
      background: #fff;
      color: var(--navy);
      font-weight: 760;
      cursor: pointer;
      border-color: #cbd6e3;
    }}
    button.primary {{ background: var(--orange); border-color: var(--orange); color: #fff; }}
    button.ghost {{ background: rgba(255,255,255,.14); color: #fff; border-color: rgba(255,255,255,.24); }}
    button.subtle {{ background: var(--soft); }}
    button.danger {{ color: var(--bad); border-color: #f4b0aa; background: #fff; }}
    button:disabled {{ opacity: .55; cursor: not-allowed; }}
    section.card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .section-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      background: #fff;
    }}
    .title-row {{ display: flex; align-items: flex-start; gap: 12px; }}
    .step-num {{
      width: 24px;
      height: 24px;
      border-radius: 999px;
      background: #e8f0f8;
      color: var(--navy);
      display: grid;
      place-items: center;
      font-size: 12px;
      font-weight: 800;
      flex: 0 0 auto;
    }}
    h2 {{ margin: 0; color: var(--navy); font-size: 16px; letter-spacing: .01em; text-transform: uppercase; }}
    .hint {{ color: var(--muted); font-size: 13px; margin-top: 3px; line-height: 1.35; }}
    .body {{ padding: 18px; }}
    .workspace-bar {{
      display: grid;
      grid-template-columns: minmax(220px, 1fr) minmax(220px, 1fr) auto;
      gap: 12px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      box-shadow: var(--shadow);
      padding: 14px 16px;
    }}
    .workspace-field label {{ margin-bottom: 5px; }}
    .workspace-actions {{ display: flex; gap: 8px; justify-content: flex-end; align-items: end; }}
    .activity-now {{
      border-left: 4px solid var(--orange);
      background: #fff8f1;
      border-radius: 8px;
      padding: 12px 14px;
      color: var(--ink);
      box-shadow: var(--shadow);
    }}
    .activity-now strong {{ display: block; color: var(--navy); margin-bottom: 3px; }}
    .worker-lanes {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 12px 0; }}
    .worker-lane {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fff; box-shadow: var(--shadow); }}
    .worker-lane strong {{ display: block; color: var(--navy); margin-bottom: 4px; }}
    .worker-lane .lane-note {{ color: var(--muted); font-size: 12px; margin-bottom: 7px; }}
    .worker-control {{ width: 100%; margin-top: 8px; }}
    .worker-tasks {{ margin: 10px 0 0; padding: 9px 0 0 18px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; line-height: 1.4; }}
    .worker-tasks li + li {{ margin-top: 5px; }}
    .progress-card {{
      border: 1px solid #fed7aa;
      border-radius: 8px;
      background: #fffaf5;
      box-shadow: var(--shadow);
      padding: 14px 16px;
    }}
    .progress-top {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 10px; }}
    .progress-track {{ height: 10px; border-radius: 999px; background: #ffe7cf; overflow: hidden; }}
    .progress-fill {{ width: 0; height: 100%; background: var(--orange); transition: width .2s ease; }}
    .progress-steps {{
      display: grid;
      grid-template-columns: repeat(4, minmax(140px, 1fr));
      gap: 10px;
      margin-top: 12px;
    }}
    .progress-step {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      background: #fff;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.35;
    }}
    .progress-step.done {{ border-color: #b8dec8; background: #f4fbf6; color: var(--ok); }}
    .progress-step.active {{ border-color: var(--orange); background: #fff8f1; color: var(--navy); }}
    .progress-step strong {{ display: block; color: var(--navy); font-size: 14px; margin-bottom: 2px; }}
    .brief-actions {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
    }}
    .brief-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      align-items: start;
    }}
    .marketing-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; align-items: start; }}
    .marketing-column {{ display: grid; gap: 14px; }}
    .marketing-column-title {{ color: var(--navy); font-size: 14px; font-weight: 800; padding-bottom: 8px; border-bottom: 2px solid var(--line); }}
    .marketing-field textarea {{ min-height: 112px; }}
    .marketing-field textarea.tall {{ min-height: 220px; }}
    .marketing-field .field-note {{ color: var(--muted); font-size: 12px; margin-top: 5px; }}
    .marketing-actions {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 18px; padding-top: 16px; border-top: 1px solid var(--line); }}
    .marketing-status {{ border-left: 4px solid var(--navy); background: #f7f9fc; padding: 12px 14px; border-radius: 5px; line-height: 1.45; }}
    .marketing-status.ready {{ border-left-color: var(--ok); background: #f4fbf6; }}
    .field-grid {{
      display: grid;
      grid-template-columns: 1fr 160px 160px;
      gap: 10px;
      margin-bottom: 12px;
    }}
    label {{ display: block; font-size: 13px; font-weight: 760; color: #344054; margin-bottom: 6px; }}
    .required::after {{ content: " *"; color: var(--orange); }}
    .segmented {{ display: grid; grid-template-columns: repeat(3, 1fr); border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }}
    .segmented button {{ border: 0; border-right: 1px solid var(--line); border-radius: 0; padding: 10px; background: #fff; }}
    .segmented button:last-child {{ border-right: 0; }}
    .segmented button.active {{ background: var(--navy); color: #fff; }}
    .dropzone {{
      border: 1.5px dashed #cbd6e3;
      border-radius: 8px;
      background: #fbfcfe;
      padding: 24px;
      text-align: center;
      display: grid;
      gap: 10px;
      justify-items: center;
    }}
    .dropzone strong {{ color: var(--navy); }}
    .upload-controls {{
      margin-top: 14px;
      display: grid;
      grid-template-columns: 220px minmax(260px, 1fr) 110px auto;
      gap: 10px;
      align-items: center;
    }}
    .upload-queue {{ display: grid; gap: 8px; margin-top: 14px; }}
    .upload-queue:empty {{ display: none; }}
    .upload-queue-item {{ border: 1px solid var(--line); border-radius: 7px; padding: 9px 11px; background: #fbfcfe; }}
    .upload-queue-meta {{ display: flex; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 13px; }}
    .upload-queue-item strong {{ color: var(--navy); overflow-wrap: anywhere; }}
    .upload-queue-item.error {{ border-color: #f4b5ae; background: #fff8f7; }}
    .upload-queue-item.done {{ border-color: #b8dec8; background: #f4fbf6; }}
    .upload-bar {{ height: 5px; border-radius: 999px; background: #e6ebf1; margin-top: 8px; overflow: hidden; }}
    .upload-bar span {{ display: block; height: 100%; background: var(--orange); transition: width .15s ease; }}
    .upload-queue-item.done .upload-bar span {{ background: var(--ok); }}
    .upload-queue-item.error .upload-bar span {{ background: #d92d20; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; margin-top: 16px; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 760px; }}
    th, td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 12px 10px; vertical-align: top; font-size: 14px; }}
    tr:last-child td {{ border-bottom: 0; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; background: #f7f9fc; }}
    .operator-tool {{
      display: grid;
      grid-template-columns: minmax(180px, .6fr) minmax(260px, 1.25fr) minmax(220px, .75fr);
      gap: 14px;
      align-items: end;
    }}
    .operator-tool-details {{ grid-column: 1 / -1; display: grid; gap: 10px; }}
    .operator-tool-actions {{ display: flex; justify-content: flex-end; gap: 10px; }}
    .operator-result {{ grid-column: 1 / -1; min-height: 20px; color: var(--muted); font-size: 14px; }}
    .operator-result.error {{ color: var(--bad); }}
    .operator-result.success {{ color: var(--ok); }}
    .download-link {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 42px;
      padding: 10px 14px;
      border: 1px solid #cbd6e3;
      border-radius: 6px;
      background: #fff;
      color: var(--navy);
      text-decoration: none;
      font-weight: 760;
    }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; align-items: center; }}
    .lesson-table-wrap {{ overflow-x: hidden; border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
    .lesson-table {{ min-width: 0; table-layout: fixed; }}
    .lesson-select-col {{ width: 44px; }}
    .lesson-name-col {{ width: 190px; }}
    .lesson-visuals-col {{ width: 70px; }}
    .lesson-table th, .lesson-table td {{ font-size: 13px; vertical-align: middle; }}
    .lesson-action-row th {{ padding: 8px 5px; background: #fff; border-bottom: 0; vertical-align: stretch; }}
    .lesson-action-row button {{ width: 100%; min-height: 58px; padding: 7px 5px; font-size: 12px; line-height: 1.15; }}
    .lesson-combined-actions {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
    .lesson-column-headings th {{ border-top: 1px solid var(--line); }}
    .lesson-column-headings th:first-child, .lesson-table tbody td:first-child {{ padding-left: 8px; padding-right: 4px; text-align: center; }}
    .lesson-column-headings th:nth-child(2), .lesson-table tbody td:nth-child(2) {{ padding-left: 8px; }}
    .lesson-column-headings th:nth-child(3), .lesson-table tbody td:nth-child(3) {{ padding-left: 4px; padding-right: 4px; text-align: center; }}
    .lesson-title-cell {{ max-width: 190px; font-weight: 760; color: var(--navy); line-height: 1.25; }}
    .visual-present {{ display: inline-flex; align-items: center; justify-content: center; color: var(--ok); font-size: 22px; font-weight: 820; }}
    .doc-cell {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
    .doc-link {{ color: var(--navy); font-weight: 760; text-decoration: none; border-bottom: 1px solid rgba(30,58,95,.35); }}
    .course-map-actions {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
    .status-pill {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 72px;
      padding: 4px 8px;
      border-radius: 999px;
      background: #eef2f7;
      color: #475467;
      font-size: 12px;
      font-weight: 760;
      text-transform: capitalize;
    }}
    .status-pill.approved, .status-pill.active, .status-pill.revision-approved {{ background: #e7f6ec; color: var(--ok); }}
    .status-pill.blocked {{ background: #fff1f0; color: var(--bad); }}
    .status-pill.missing {{ background: #f2f4f7; color: #667085; }}
    .status-pill.pending {{ background: #fff6e8; color: var(--warn); }}
    .status-pill.ready-for-review, .status-pill.revision-corrected-ready-for-review {{ background: #fff6e8; color: var(--warn); }}
    .status-pill.not-generated {{ background: #f2f4f7; color: #667085; }}
    .status-pill.not-approved {{ background: #fff6e8; color: var(--warn); }}
    .status-pill.revision-needs-attention, .status-pill.revision-failed, .status-pill.generation-failed {{ background: #fff1f0; color: var(--bad); }}
    .status-pill.revision-in-progress, .status-pill.revision-pending {{ background: #fff6e8; color: var(--warn); }}
    .status-pill.video-available {{ background: #e7f6ec; color: var(--ok); }}
    .status-pill.waiting-for-approved-presentation {{ background: #f2f4f7; color: #667085; }}
    .status-pill.ready-for-video-generation, .status-pill.new-approved-revision-ready, .status-pill.generating,
    .status-pill.queued, .status-pill.uploading, .status-pill.configuring,
    .status-pill.generating-transcripts, .status-pill.exporting, .status-pill.rendering {{ background: #fff6e8; color: var(--warn); }}
    .status-pill.presentation-exceeds-20-mb, .status-pill.needs-attention, .status-pill.failed {{ background: #fff1f0; color: var(--bad); }}
    .status-summary {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
    .metric {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fff; }}
    .metric .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; font-weight: 760; }}
    .metric .value {{ margin-top: 5px; font-weight: 820; color: var(--ink); line-height: 1.25; }}
    .notice {{ border-left: 4px solid var(--orange); background: #fff8f1; padding: 12px; border-radius: 4px; margin-top: 12px; color: var(--ink); }}
    .state {{ font-weight: 760; }}
    .completed {{ color: var(--ok); }}
    .queued, .running {{ color: var(--warn); }}
    .failed, .cancelled {{ color: var(--bad); }}
    .muted {{ color: var(--muted); }}
    .mini {{ padding: 7px 8px; font-size: 13px; border-radius: 5px; }}
    .upload-edit {{ display: grid; grid-template-columns: 130px 70px; gap: 6px; }}
    .upload-actions {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .log-tools {{ display: grid; grid-template-columns: minmax(240px, 1fr) 180px 180px; gap: 10px; }}
    .cost-provider-list {{ margin: 12px 0 0; color: var(--muted); font-size: 13px; }}
    .cost-math {{ display: grid; gap: 8px; margin-top: 14px; }}
    .cost-math-row {{ border: 1px solid var(--line); border-radius: 7px; padding: 10px 12px; background: #fbfcfe; font-size: 13px; line-height: 1.45; }}
    .worker-error-action {{ color: var(--navy); font-weight: 760; }}
    .worker-error-explanation {{ min-width: 360px; line-height: 1.45; }}
    .hidden {{ display: none !important; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }}
    @media (max-width: 980px) {{
      .topbar, .workspace-bar, .brief-grid, .marketing-grid, .field-grid, .progress-steps, .status-summary, .upload-controls, .log-tools, .operator-tool {{ grid-template-columns: 1fr; }}
      .field-grid {{ grid-template-columns: 1fr !important; }}
      .operator-tool-details {{ grid-column: 1; }}
      .segmented {{ grid-template-columns: 1fr; }}
      .segmented button {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      .segmented button:last-child {{ border-bottom: 0; }}
      .dropzone {{ padding: 18px 12px; overflow: hidden; }}
      .dropzone input {{ width: 100%; }}
      .body {{ padding: 14px; }}
      .section-head {{ align-items: flex-start; }}
      .workspace-actions, .operator-tool-actions {{ justify-content: stretch; }}
      .workspace-actions button, .operator-tool-actions button, .course-map-actions button {{ width: 100%; }}
      .top-actions {{ justify-content: flex-start; }}
      main {{ padding: 18px 14px 36px; }}
      .nav {{ padding-left: 14px; padding-right: 14px; }}
    }}
  </style>
</head>
<body>
  <header class="app">
    <div class="topbar">
      <div class="brand">
        <div class="mark">BS</div>
        <div>BuildStak Course Agent<small>Prof Greg operator console</small></div>
      </div>
      <div class="top-actions">
        <button class="ghost" id="refreshTop">Refresh</button>
      </div>
    </div>
    <nav class="nav" aria-label="Console sections">
      <a href="#dashboard" data-page-link="dashboard">Dashboard</a>
      <a href="#sections-1-2" data-page-link="sections-1-2">Course Intake</a>
      <a href="#sections-3-4" data-page-link="sections-3-4">Lesson Management</a>
      <a href="#section-5" data-page-link="section-5">Lesson Fixes</a>
      <a href="#section-6" data-page-link="section-6">Video Generator</a>
    </nav>
  </header>
  <main>
    <div class="console-page active" data-page="dashboard">
    <div class="workspace-bar">
      <div class="workspace-field">
        <label for="course">Active course workspace</label>
        <input id="course" value="" placeholder="New course workspace" aria-label="Course slug" readonly>
      </div>
      <div class="workspace-field">
        <label for="coursePicker">Saved unfinished courses</label>
        <select id="coursePicker" aria-label="Saved unfinished courses"><option value="">Loading saved courses…</option></select>
      </div>
      <div class="workspace-actions">
        <button id="newCourse" class="primary">New course</button>
        <button id="refreshWorkspace">Refresh</button>
        <button id="restartWorkspace" class="subtle">Restart</button>
        <button id="deleteCourse" class="danger">Delete</button>
      </div>
    </div>
    <div class="activity-now">
      <strong>Current activity</strong>
      <span id="currentActivity">Idle.</span>
    </div>
    <div class="worker-lanes" aria-label="Production worker lanes">
      <div class="worker-lane"><strong>Content worker</strong><div class="lane-note">Course maps, marketing kits, course books, and book translations</div><span id="contentLaneStatus" class="muted">Checking…</span><ul id="contentLaneTasks" class="worker-tasks"><li>Checking task list…</li></ul><button type="button" class="danger worker-control" id="contentLaneControl" onclick="controlWorker('content')">Stop &amp; clear queue</button></div>
      <div class="worker-lane"><strong>Delivery worker</strong><div class="lane-note">Presentations, deck translations, and operational tasks</div><span id="deliveryLaneStatus" class="muted">Checking…</span><ul id="deliveryLaneTasks" class="worker-tasks"><li>Checking task list…</li></ul><button type="button" class="danger worker-control" id="deliveryLaneControl" onclick="controlWorker('delivery')">Stop &amp; clear queue</button></div>
      <div class="worker-lane"><strong>Video worker</strong><div class="lane-note">AI Studios video requests, independent of material production</div><span id="videoLaneStatus" class="muted">Checking…</span><ul id="videoLaneTasks" class="worker-tasks"><li>Checking task list…</li></ul><button type="button" class="danger worker-control" id="videoLaneControl" onclick="controlWorker('video')">Stop &amp; clear queue</button></div>
    </div>
    <div class="progress-card">
      <div class="progress-top">
        <strong style="color:var(--navy)">Operating progress</strong>
        <span class="muted" id="progressPercent">0%</span>
      </div>
      <div class="progress-track"><div class="progress-fill" id="progressFill"></div></div>
      <div class="progress-steps" id="progressSteps"></div>
    </div>

    <section id="costs" class="card">
      <div class="section-head"><div class="title-row"><div class="step-num">8</div><div><h2>AI Costs</h2><div class="hint">Every provider call made for this course workspace is listed separately. Totals use the configured API rate card.</div></div></div></div>
      <div class="body">
        <div class="status-summary" id="costSummary"><div class="metric"><div class="label">Total estimated investment</div><div class="value">Loading…</div></div></div>
        <div class="cost-provider-list">Complete calculation for this course</div>
        <div class="table-wrap"><table><thead><tr><th>Provider</th><th>Model</th><th>API calls</th><th>Cost (USD)</th></tr></thead><tbody id="costMath"><tr><td colspan="4" class="muted">No cost calculation available yet.</td></tr></tbody></table></div>
        <div class="cost-provider-list" id="costRecentLabel">Latest API requests</div>
        <div class="table-wrap"><table><thead><tr><th>Date / time</th><th>Artifact / stage</th><th>Provider</th><th>Model</th><th>Usage</th><th>Cost (USD)</th><th>Status</th></tr></thead><tbody id="costRows"><tr><td colspan="7" class="muted">No AI calls recorded for this workspace.</td></tr></tbody></table></div>
      </div>
    </section>

    <section id="worker-errors" class="card">
      <div class="section-head"><div class="title-row"><div class="step-num">!</div><div><h2>Latest worker errors</h2><div class="hint">The 10 most recent failed worker actions for this course, including failures later resolved by a retry.</div></div></div></div>
      <div class="body">
        <div class="table-wrap"><table><thead><tr><th>Date / time</th><th>Worker</th><th>Action that failed</th><th>Explanation / next step</th></tr></thead><tbody id="workerErrorRows"><tr><td colspan="4" class="muted">No worker errors recorded for this workspace.</td></tr></tbody></table></div>
      </div>
    </section>
    </div>

    <div class="console-page" data-page="sections-1-2">
    <section id="brief" class="card">
      <div class="section-head">
        <div class="title-row">
          <div class="step-num">1</div>
          <div><h2>Course Brief</h2><div class="hint">Define the course Greg will produce. The syllabus is a starting direction, not a fixed contract.</div></div>
        </div>
      </div>
      <div class="body brief-grid">
        <div>
          <label class="required" for="courseTitle">Course name</label>
          <input id="courseTitle" placeholder="e.g. Construction Project Management Essentials">
          <div style="height:12px"></div>
          <label class="required">Study level</label>
          <div class="segmented" role="group" aria-label="Study level">
            <button type="button" data-level="Basic" class="active">Basic</button>
            <button type="button" data-level="Intermediate">Intermediate</button>
            <button type="button" data-level="Advanced">Advanced</button>
          </div>
          <div style="height:12px"></div>
          <div class="field-grid" style="grid-template-columns: 160px 1fr;">
            <div>
              <label class="required" for="expectedLessons">Lessons</label>
              <input id="expectedLessons" type="number" min="1" max="30" value="10">
            </div>
            <div>
              <label for="courseSlug">Optional slug</label>
              <input id="courseSlug" placeholder="generated automatically if empty">
            </div>
          </div>
        </div>
        <div>
          <label class="required" for="syllabus">Syllabus</label>
          <textarea id="syllabus" style="min-height:260px" placeholder="Lesson 1: ...&#10;Lesson 2: ...&#10;Learning outcomes, topics, and notes"></textarea>
        </div>
      </div>
    </section>

    <section id="materials" class="card">
      <div class="section-head">
        <div class="title-row">
          <div class="step-num">2</div>
          <div><h2>Source Materials</h2><div class="hint">Attach books, PDFs, manuals, references, and documents. Each file can be edited after upload.</div></div>
        </div>
      </div>
      <div class="body">
        <div class="dropzone" id="dropzone">
          <strong>Drop source materials here</strong>
          <span class="muted">PDF, DOCX, TXT, Markdown, PNG, JPG, or WebP. Multiple files are supported.</span>
          <input id="files" type="file" multiple accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp">
        </div>
        <div class="upload-controls">
          <select id="uploadScope">
            <option value="course">Course-level source</option>
            <option value="lesson">Lesson-specific source</option>
          </select>
          <select id="referencePolicy">
            <option value="context_only">Context only - do not cite</option>
            <option value="image_only">Do not cite text - images allowed</option>
            <option value="reference_only">Can cite - no images</option>
            <option value="reference_and_images">Can cite + images allowed</option>
          </select>
          <input id="uploadLesson" type="number" min="1" value="1" aria-label="Lesson number">
          <button class="primary" id="upload">Upload selected files</button>
        </div>
        <div id="uploadQueue" class="upload-queue" aria-live="polite"></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>File</th><th>Scope</th><th>Use</th><th>Reference policy</th><th>Size</th><th>Actions</th></tr></thead>
            <tbody id="uploads"><tr><td colspan="6" class="muted">No uploads loaded.</td></tr></tbody>
          </table>
        </div>
      </div>
    </section>

    <section id="marketing" class="card">
      <div class="section-head">
        <div class="title-row">
          <div class="step-num">3</div>
          <div><h2>Marketing</h2><div class="hint">Turn the approved Course Map into website copy and a five-page BuildStak brochure. Market claims include traceable sources and remain editable.</div></div>
        </div>
      </div>
      <div class="body">
        <div id="marketingStatus" class="marketing-status">Generate and approve the Course Map first. Marketing uses the final learning journey, not the draft syllabus.</div>
        <div id="marketingSources" class="field-note" style="margin-top:8px"></div>
        <div class="marketing-grid" style="margin-top:16px">
          <div class="marketing-column">
            <div class="marketing-column-title">Brochure fields</div>
            <div class="marketing-field"><label for="marketingPositioning">Brochure positioning</label><textarea id="marketingPositioning" placeholder="One strong, credible cover promise."></textarea></div>
            <div class="marketing-field"><label for="marketingHighlights">Market highlights</label><textarea id="marketingHighlights" placeholder="One evidence-backed market observation per line."></textarea></div>
            <div class="marketing-field"><label for="marketingAudience">Who this is for</label><textarea id="marketingAudience"></textarea></div>
            <div class="marketing-field"><label for="marketingCareer">Career relevance</label><textarea id="marketingCareer" placeholder="One careful, non-guaranteed outcome per line."></textarea></div>
            <div class="marketing-field"><label for="marketingCta">Call to action</label><input id="marketingCta" placeholder="Short enrollment-oriented next step"></div>
            <div class="marketing-field"><label for="marketingUrl">Course page URL</label><input id="marketingUrl" type="url" placeholder="https://learn.buildstak.com/courses/..."></div>
          </div>
          <div class="marketing-column">
            <div class="marketing-column-title">Website fields</div>
            <div class="marketing-field"><label class="required" for="marketingTitle">Course title</label><input id="marketingTitle" placeholder="Market-facing course title"></div>
            <div class="marketing-field"><label class="required" for="marketingShort">Short description</label><textarea id="marketingShort" placeholder="Exactly two sentences for the course hero or card."></textarea><div class="field-note">Two sentences, ready for the website.</div></div>
            <div class="marketing-field"><label class="required" for="marketingFull">Full description</label><textarea id="marketingFull" class="tall" placeholder="Market context, learner problem, practical value, and career relevance."></textarea></div>
            <div class="marketing-field"><label class="required" for="marketingLearn">What you will learn</label><textarea id="marketingLearn" placeholder="One outcome per line; exactly five."></textarea></div>
            <div class="marketing-field"><label class="required" for="marketingSkills">Skills / tags</label><textarea id="marketingSkills" placeholder="One tag per line; exactly three."></textarea></div>
            <div class="marketing-field"><label for="marketingRequirements">Requirements</label><textarea id="marketingRequirements" placeholder="One requirement per line."></textarea></div>
          </div>
        </div>
        <div class="marketing-actions">
          <button class="primary" id="generateMarketing">Generate website copy + brochure</button>
          <button id="saveMarketing">Save edits + update brochure</button>
          <a id="downloadBrochure" class="download-link hidden" target="_blank" rel="noopener">Download 5-page brochure</a>
          <span class="muted">Brochure format: US Letter PDF, using the BuildStak brand system.</span>
        </div>
      </div>
    </section>
    </div>

    <div class="console-page" data-page="sections-3-4">
    <section id="course-map" class="card">
      <div class="section-head">
        <div class="title-row">
          <div class="step-num">4</div>
          <div><h2>Course Map</h2><div class="hint">When the course brief is ready and you have added any optional source materials, choose when to start the Course Map. It appears here for review and download.</div></div>
        </div>
      </div>
      <div class="body">
        <div class="course-map-actions">
          <button class="primary" id="startProduction">Start Course Map with current brief and sources</button>
          <span class="muted">This is your confirmation that Section 1 is complete and any optional materials from Section 2 have been added.</span>
        </div>
        <div id="courseMapPanel" class="notice">Course Map has not been generated for this course yet.</div>
      </div>
    </section>

    <section id="pipeline" class="card">
      <div class="section-head">
        <div class="title-row">
          <div class="step-num">5</div>
          <div><h2>Lesson Production</h2><div class="hint">Select one, several, or all lessons. Produced files appear in this table when they are ready to review.</div></div>
        </div>
        <div class="muted" id="approvalCount">0 approvals</div>
      </div>
      <div class="body">
        <div class="notice hidden" id="message">Ready.</div>
        <div>
          <div class="lesson-table-wrap">
            <table class="lesson-table">
              <colgroup>
                <col class="lesson-select-col">
                <col class="lesson-name-col">
                <col class="lesson-visuals-col">
                <col span="6">
              </colgroup>
              <thead>
                <tr class="lesson-action-row">
                  <th colspan="3">
                    <div class="lesson-combined-actions">
                      <button id="produceTranslatedBooks">Translate course books (PT + ES)</button>
                      <button id="produceTranslatedDecks">Translate presentations (PT + ES)</button>
                    </div>
                  </th>
                  <th><button class="primary" id="produceBooks">Generate course books</button></th>
                  <th><button id="produceDecks">Generate presentations</button></th>
                  <th><button id="producePtBrBooks">Translate PT-BR course book</button></th>
                  <th><button id="producePtBrDecks">Translate PT-BR presentation</button></th>
                  <th><button id="produceEsBooks">Translate ES course book</button></th>
                  <th><button id="produceEsDecks">Translate ES presentation</button></th>
                </tr>
                <tr class="lesson-column-headings">
                  <th><input id="selectAllLessons" type="checkbox" aria-label="Select all lessons"></th>
                  <th>Lesson</th>
                  <th>Visuals</th>
                  <th>Course book</th>
                  <th>Presentation</th>
                  <th>PT-BR book</th>
                  <th>PT-BR deck</th>
                  <th>ES book</th>
                  <th>ES deck</th>
                </tr>
              </thead>
              <tbody id="lessonSelection"><tr><td colspan="9" class="muted">Generate the Course Map first to choose lessons.</td></tr></tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
    </div>

    <div class="console-page" data-page="section-5">
    <section id="approvals" class="card">
      <div class="section-head">
        <div class="title-row">
          <div class="step-num">6</div>
          <div><h2>Operator Action</h2><div class="hint">Choose a lesson first, then select its file or image request to approve it, request edits, or attach requested images. Files remain managed in the lesson table.</div></div>
        </div>
      </div>
      <div class="body">
        <div class="operator-tool">
          <div><label for="operatorLesson">Lesson</label><select id="operatorLesson"></select></div>
          <div><label for="operatorTarget">File or image request</label><select id="operatorTarget"></select></div>
          <div><label for="operatorAction">Action</label><select id="operatorAction"><option value="approve">Approve</option><option value="request_edits">Request edits</option></select></div>
          <div class="operator-tool-details" id="operatorToolDetails"></div>
          <div class="operator-result" id="operatorResult" role="status" aria-live="polite"></div>
          <div class="operator-tool-actions"><button class="primary" id="applyOperatorAction">Apply action</button></div>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Editing material</th><th>Scope</th><th>Use</th><th>Reference policy</th><th>Size</th><th>Actions</th></tr></thead>
            <tbody id="revisionUploads"><tr><td colspan="6" class="muted">No editing materials attached yet.</td></tr></tbody>
          </table>
        </div>
      </div>
    </section>
    </div>

    <div class="console-page" data-page="section-6">
    <section id="video-generator" class="card">
      <div class="section-head">
        <div class="title-row">
          <div class="step-num">7</div>
          <div><h2>Video Generator</h2><div class="hint">Each approved presentation enters its own English, Portuguese, or Spanish video lane. A revised approved PPTX always creates a new video record. Completed exports provide a direct video download URL.</div></div>
        </div>
      </div>
      <div class="body">
        <div class="status-summary" id="videoGeneratorSummary"><div class="metric"><div class="label">Videos available</div><div class="value">0</div></div><div class="metric"><div class="label">In production</div><div class="value">0</div></div><div class="metric"><div class="label">Waiting for presentation</div><div class="value">0</div></div></div>
        <div class="notice">AI Studios integration validated. Each approved presentation is handled independently, one video at a time. Completed videos appear below with a direct download link.</div>
        <div class="lesson-table-wrap">
          <table class="lesson-table">
            <thead><tr><th>Lesson</th><th>English video</th><th>Portuguese video</th><th>Spanish video</th></tr></thead>
            <tbody id="videoGeneratorRows"><tr><td colspan="4" class="muted">Generate and approve a presentation to prepare its video.</td></tr></tbody>
          </table>
        </div>
      </div>
    </section>
    </div>

  </main>
  <script>
    const course = document.getElementById('course');
    const msg = document.getElementById('message');
    const expectedLessonsByLevel = {{ Basic: 10, Intermediate: 15, Advanced: 15 }};
    let currentStatus = null;
    let currentJobs = [];
    let currentWorkerControls = {{content: false, delivery: false, video: false}};
    const workerControlInFlight = new Set();
    let currentMarketing = null;
    let operatorTargetMap = {{}};
    let operatorTargetsByLesson = {{}};
    let workspaceLoadInFlight = false;
    let operatorActionInFlight = false;
    let uploadQueue = [];
    let revisionRequestCount = 0;
    const consolePages = new Set(['dashboard', 'sections-1-2', 'sections-3-4', 'section-5', 'section-6']);
    function showConsolePage(requestedPage, updateHash = false) {{
      const page = consolePages.has(requestedPage) ? requestedPage : 'dashboard';
      document.querySelectorAll('[data-page]').forEach(item => item.classList.toggle('active', item.dataset.page === page));
      document.querySelectorAll('[data-page-link]').forEach(item => item.classList.toggle('active', item.dataset.pageLink === page));
      if (updateHash && location.hash !== `#${{page}}`) history.pushState(null, '', `#${{page}}`);
      window.scrollTo({{top: 0, behavior: 'smooth'}});
    }}
    const progressSteps = [
      ['course_map', 'Course Map', 'Map and source research'],
      ['book', 'Course books', 'English PDFs by lesson'],
      ['deck', 'Presentations', 'PPTX after book approval'],
      ['translation', 'Translations', 'PT-BR and ES artifacts']
    ];
    const approvalGroups = [
      {{
        key: 'study_guide',
        title: 'Course book',
        description: 'Approve the English course book to release presentation production.',
        artifactType: 'study_guide',
        artifactNames: lesson => [`lesson_${{lesson}}_study_guide_pdf`, 'study_guide_pdf'],
        approvalField: 'study_guide'
      }},
      {{
        key: 'deck',
        title: 'Presentation',
        description: 'Approve the English presentation after reviewing the PPTX.',
        artifactType: 'deck',
        artifactNames: lesson => [`lesson_${{lesson}}_deck_pptx`, 'deck_pptx'],
        approvalField: 'deck'
      }},
      {{
        key: 'pt_br_study_guide',
        title: 'PT-BR translation - course book',
        description: 'Review the Portuguese version for Brazilian learners working in the U.S. market.',
        artifactType: 'pt_br_study_guide',
        artifactNames: lesson => [`lesson_${{lesson}}_study_guide_pt_br_pdf`, `lesson_${{lesson}}_pt_br_study_guide_pdf`, 'localization_pt_br'],
        approvalField: 'pt_br_study_guide'
      }},
      {{
        key: 'pt_br_deck',
        title: 'PT-BR translation - presentation',
        description: 'Review the Portuguese presentation after the English deck is approved.',
        artifactType: 'pt_br_deck',
        artifactNames: lesson => [`lesson_${{lesson}}_deck_pt_br_pptx`, `lesson_${{lesson}}_pt_br_deck_pptx`, 'localization_pt_br_deck'],
        approvalField: 'pt_br_deck'
      }},
      {{
        key: 'es_study_guide',
        title: 'ES translation - course book',
        description: 'Review the neutral Spanish course book version.',
        artifactType: 'es_study_guide',
        artifactNames: lesson => [`lesson_${{lesson}}_study_guide_es_pdf`, `lesson_${{lesson}}_es_study_guide_pdf`, 'localization_es_419'],
        approvalField: 'es_study_guide'
      }},
      {{
        key: 'es_deck',
        title: 'ES translation - presentation',
        description: 'Review the neutral Spanish presentation version.',
        artifactType: 'es_deck',
        artifactNames: lesson => [`lesson_${{lesson}}_deck_es_pptx`, `lesson_${{lesson}}_es_deck_pptx`, 'localization_es_419_deck'],
        approvalField: 'es_deck'
      }}
    ];
    function esc(value) {{
      return String(value ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    }}
    function normalizedStage(key) {{
      if (key === 'DRAFT') return 'DOCX_PDF';
      if (key === 'LESSON_PRODUCTION') return 'SOURCE_LEDGER';
      if (key === 'COURSE_MAP_QA_BLOCKED') return 'COURSE_MAP';
      if (key === 'PROCESS_REVIEW' || key === 'FULL_FLOW_CONFIRMATION_COMPLETE') return 'FINAL_REVIEW';
      return key || 'INTAKE';
    }}
    function artifactExists(names) {{
      const artifacts = currentStatus?.artifacts || [];
      return artifacts.some(item => names.includes(item.name) && item.exists);
    }}
    function artifactByNames(names) {{
      const artifacts = currentStatus?.artifacts || [];
      return artifacts.find(item => names.includes(item.name) && item.exists && isDownloadablePath(item.path)) || null;
    }}
    function isDownloadablePath(path) {{
      return /\\.(pdf|pptx|docx|md)$/i.test(String(path || ''));
    }}
    function fileExtension(path) {{
      const match = String(path || '').match(/\\.[a-z0-9]+$/i);
      return match ? match[0].toLowerCase() : '';
    }}
    function cleanFilenamePart(value) {{
      return String(value || '').replace(/[\\\\/:*?"<>|]+/g, '-').replace(/\\s+/g, ' ').trim();
    }}
    function downloadFilename(group, artifactPath, lesson) {{
      const ext = fileExtension(artifactPath) || (group.key.includes('deck') || group.key === 'deck' ? '.pptx' : '.pdf');
      const lessonNumber = Number(lesson?.lesson || lesson || 1);
      const lessonPart = `Lesson ${{String(Math.max(1, lessonNumber)).padStart(2, '0')}}`;
      const titlePart = cleanFilenamePart(lesson?.title || 'Course lesson');
      const suffix = group.key.includes('deck') || group.key === 'deck' ? 'Presentation' : 'Course Book';
      return `${{lessonPart}} - ${{titlePart}} - ${{suffix}}${{ext}}`;
    }}
    function renderPipeline() {{
      const progress = currentStatus?.progress || {{percent: 0}};
      const phases = [progress.course_map, progress.course_books, progress.presentations, progress.translations];
      const activeIndex = phases.findIndex((phase, index) => index === 0 ? !phase?.approved : (phase?.approved || 0) < (phase?.total || 0));
      const percent = Number(progress.percent || 0);
      const shownPercent = Number.isInteger(percent) ? percent.toFixed(0) : percent.toFixed(1);
      document.getElementById('progressPercent').textContent = `${{shownPercent}}%`;
      document.getElementById('progressFill').style.width = `${{percent}}%`;
      document.getElementById('progressSteps').innerHTML = progressSteps.map((step, index) => {{
        const phase = phases[index] || {{}};
        const complete = index === 0 ? phase.approved : phase.total > 0 && phase.approved === phase.total;
        const state = complete ? 'done' : index === (activeIndex < 0 ? 3 : activeIndex) ? 'active' : '';
        const detail = index === 0
          ? `${{phase.approved ? 'Approved' : 'Not approved'}} · ${{Number(phase.points || 0).toFixed(0)}}/25%`
          : `${{phase.approved || 0}}/${{phase.total || 0}} approved · ${{Number(phase.points || 0).toFixed(1)}}/25%`;
        return `<div class="progress-step ${{state}}"><strong>${{index + 1}}. ${{esc(step[1])}}</strong>${{esc(detail)}}</div>`;
      }}).join('');
      const approved = (currentStatus?.lessons || []).reduce((count, lesson) => count + approvalGroups.filter(group => lesson[group.approvalField] === 'approved').length, 0);
      document.getElementById('approvalCount').textContent = `${{approved}} approvals`;
      renderCourseMapPanel();
      renderOperatorTool();
    }}
    function formatUsd(value) {{
      return new Intl.NumberFormat('en-US', {{style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 6}}).format(Number(value || 0));
    }}
    function usageLabel(usage) {{
      if (!usage) return '—';
      if (usage.images) return `${{usage.images}} image${{Number(usage.images) === 1 ? '' : 's'}} · ${{esc(usage.size || '')}}`;
      const input = usage.input_tokens ?? usage.prompt_tokens ?? 0;
      const output = usage.output_tokens ?? usage.completion_tokens ?? 0;
      return `${{Number(input).toLocaleString()}} in · ${{Number(output).toLocaleString()}} out`;
    }}
    const roleLabels = {{course_architect:'Course Map', source_research:'Source research', technical_content:'Course book', pedagogy_review:'Pedagogy review', citation_review:'Citation review', design_review:'Design review', visual_planning:'Visual plan', visual_review:'Visual review', image_generation:'Generated image', localization:'Translation', localization_review:'Translation review'}};
    function renderCosts(report) {{
      const total = formatUsd(report?.total_estimated_usd);
      document.getElementById('costSummary').innerHTML = `<div class="metric"><div class="label">Total estimated investment</div><div class="value">${{total}}</div></div><div class="metric"><div class="label">Recorded API calls</div><div class="value">${{Number(report?.request_count || 0)}}</div></div>`;
      const math = report?.math || [];
      document.getElementById('costMath').innerHTML = math.length ? math.map(item => `<tr><td>${{esc(item.provider)}}</td><td>${{esc(item.model)}}</td><td>${{Number(item.calls)}}</td><td><strong>${{formatUsd(item.estimated_usd)}}</strong></td></tr>`).join('') + `<tr><td colspan="3"><strong>Total</strong></td><td><strong>${{total}}</strong></td></tr>` : '<tr><td colspan="4" class="muted">No cost calculation available yet.</td></tr>';
      const rows = report?.recent_requests || [];
      const recentLabel = Number(report?.request_count || 0) > 10 ? `Latest 10 API requests (of ${{Number(report.request_count)}} total)` : 'API requests';
      document.getElementById('costRecentLabel').textContent = recentLabel;
      document.getElementById('costRows').innerHTML = rows.length ? rows.map(item => {{
        const cost = item.cost || {{}};
        const costText = cost.status === 'estimated' ? formatUsd(cost.estimated_usd) : (item.outcome === 'completed' ? 'Rate not configured' : '—');
        const status = item.outcome === 'completed' ? (cost.status === 'estimated' ? 'Estimated' : 'Needs rate') : esc(item.outcome || 'unknown');
        return `<tr><td>${{esc(item.at || '—')}}</td><td>${{esc(roleLabels[item.role] || item.role || '—')}}</td><td>${{esc(item.provider || '—')}}</td><td>${{esc(item.model || '—')}}</td><td>${{usageLabel(item.usage)}}</td><td>${{costText}}</td><td><span class="status-pill ${{esc(item.outcome || 'missing')}}">${{status}}</span></td></tr>`;
      }}).join('') : '<tr><td colspan="7" class="muted">No AI calls recorded for this workspace.</td></tr>';
    }}
    const workerLabels = {{content:'Content worker', delivery:'Delivery worker', video:'Video worker'}};
    const stageActionLabels = {{
      study_guide:'Generate course book', deck:'Generate presentation',
      translations_book:'Translate course book', translations_deck:'Translate presentation',
      course_map:'Generate Course Map', marketing:'Generate marketing kit', video:'Generate video'
    }};
    function workerErrorAction(job) {{
      const stage = String(job?.payload?.stage || '');
      const requestType = String(job?.request_type || '').replace(/_/g, ' ');
      const action = stageActionLabels[stage] || job?.input_summary || requestType || 'Worker action';
      const lesson = Number(job?.lesson || (job?.payload?.lessons || [])[0] || 0);
      return lesson ? `${{action}} · Lesson ${{String(lesson).padStart(2, '0')}}` : action;
    }}
    function workerErrorExplanation(job) {{
      const raw = String(job?.last_error || '');
      if (/needs an approved course book before presentation production/i.test(raw)) return 'The presentation was requested before its Course Book was approved. Generate and approve the Course Book, then retry the presentation.';
      if (/ended mid-sentence|incomplete text content|max_output_tokens/i.test(raw)) return 'The AI response reached its output limit and stopped mid-section. Retry the Course Book; the saved complete draft is preserved for a focused revision.';
      if (/Independent study-guide reviewers still require changes/i.test(raw)) return 'The Course Book still had unresolved reviewer findings after the automatic correction rounds. Review the lesson QA reports, correct the cited content, then retry.';
      if (/source\\/reference.*QA failed/i.test(raw)) return 'The source/reference check found missing, incomplete, or unsupported citation data. Review the lesson source QA report and correct the flagged references before retrying.';
      if (/layout automatic QA failed|PDF layout QA failed/i.test(raw)) return 'The generated file failed automatic layout checks. Correct the reported overflow or page-layout issue, then retry; no incomplete file was released.';
      return operatorJobMessage(job) || 'The worker stopped. Review the action and retry after correcting the reported condition.';
    }}
    function renderWorkerErrors(errors) {{
      const rows = errors || [];
      document.getElementById('workerErrorRows').innerHTML = rows.length ? rows.map(job => {{
        const timestamp = job.updated_at || job.created_at;
        const when = timestamp ? new Date(timestamp).toLocaleString() : '—';
        return `<tr><td>${{esc(when)}}</td><td>${{esc(workerLabels[job.lane] || job.lane || 'Worker')}}</td><td class="worker-error-action">${{esc(workerErrorAction(job))}}</td><td class="worker-error-explanation">${{esc(workerErrorExplanation(job))}}</td></tr>`;
      }}).join('') : '<tr><td colspan="4" class="muted">No worker errors recorded for this workspace.</td></tr>';
    }}
    function renderCourseMapPanel() {{
      const map = artifactByNames(['course_map_md']);
      const panel = document.getElementById('courseMapPanel');
      const startButton = document.getElementById('startProduction');
      const activeCourseMap = currentJobs.some(job => job.request_type === 'course_start' && ['queued', 'running'].includes(job.state));
      const courseMapReady = Boolean(map && currentStatus?.course_map_ready === true);
      startButton.disabled = activeCourseMap;
      startButton.textContent = activeCourseMap ? 'Creating Course Map...' : (courseMapReady ? 'Regenerate Course Map with current brief and sources' : 'Start Course Map with current brief and sources');
      if (activeCourseMap) {{
        panel.innerHTML = '<strong>Course Map is being researched and reviewed.</strong> The file will appear only after every automatic check passes.';
        return;
      }}
      if (!courseMapReady) {{
        const blocked = currentStatus?.stage === 'SOURCE_QA_BLOCKED' || currentStatus?.stage === 'COURSE_MAP_QA_BLOCKED';
        panel.innerHTML = blocked ? '<strong>Course Map is not released.</strong> Greg must complete an automatic correction and pass QA first.' : '<strong>Course Map has not been generated yet.</strong> Add any optional source materials, then use the button above when you are ready.';
        return;
      }}
      const mapName = `${{cleanFilenamePart(course.value)}} - Course Map.md`;
      panel.innerHTML = `<strong>Course Map approved by automatic QA.</strong> <a class="download-link" href="/artifact?path=${{encodeURIComponent(map.path)}}&filename=${{encodeURIComponent(mapName)}}" target="_blank" rel="noopener">Download Course Map</a>`;
    }}
    function marketingLines(value) {{
      return Array.isArray(value) ? value.join('\\n') : '';
    }}
    function marketingList(id) {{
      return document.getElementById(id).value.split(/\\n+/).map(item => item.replace(/^[-•]\\s*/, '').trim()).filter(Boolean);
    }}
    function marketingPayload() {{
      const existing = currentMarketing?.marketing || {{}};
      return Object.assign({{}}, existing, {{
        course_title: document.getElementById('marketingTitle').value.trim(),
        short_description: document.getElementById('marketingShort').value.trim(),
        full_description: document.getElementById('marketingFull').value.trim(),
        value_proposition: document.getElementById('marketingPositioning').value.trim(),
        market_highlights: marketingList('marketingHighlights'),
        skills: marketingList('marketingSkills'),
        what_you_will_learn: marketingList('marketingLearn'),
        requirements: marketingList('marketingRequirements'),
        audience: document.getElementById('marketingAudience').value.trim(),
        career_outcomes: marketingList('marketingCareer'),
        call_to_action: document.getElementById('marketingCta').value.trim(),
        landing_page_url: document.getElementById('marketingUrl').value.trim()
      }});
    }}
    function renderMarketing(report) {{
      currentMarketing = report || {{ready:false, marketing:{{}}, brochure_ready:false}};
      const data = currentMarketing.marketing || {{}};
      document.getElementById('marketingTitle').value = data.course_title || '';
      document.getElementById('marketingShort').value = data.short_description || '';
      document.getElementById('marketingFull').value = data.full_description || '';
      document.getElementById('marketingPositioning').value = data.value_proposition || '';
      document.getElementById('marketingHighlights').value = marketingLines(data.market_highlights);
      document.getElementById('marketingSkills').value = marketingLines(data.skills);
      document.getElementById('marketingLearn').value = marketingLines(data.what_you_will_learn);
      document.getElementById('marketingRequirements').value = marketingLines(data.requirements);
      document.getElementById('marketingAudience').value = data.audience || '';
      document.getElementById('marketingCareer').value = marketingLines(data.career_outcomes);
      document.getElementById('marketingCta').value = data.call_to_action || '';
      document.getElementById('marketingUrl').value = data.landing_page_url || '';
      const active = currentJobs.some(job => job.request_type === 'production_stage' && job?.payload?.stage === 'marketing' && ['queued', 'running'].includes(job.state));
      const mapReady = currentStatus?.course_map_ready === true;
      const generate = document.getElementById('generateMarketing');
      const save = document.getElementById('saveMarketing');
      generate.disabled = !mapReady || active;
      save.disabled = !currentMarketing.ready || active;
      generate.textContent = active ? 'Creating marketing kit...' : (currentMarketing.ready ? 'Regenerate from Course Map' : 'Generate website copy + brochure');
      const status = document.getElementById('marketingStatus');
      status.classList.toggle('ready', Boolean(currentMarketing.ready));
      status.innerHTML = active
        ? '<strong>Marketing research and brochure production are in progress.</strong> Current U.S. market sources are being checked before the copy is released.'
        : currentMarketing.ready
          ? `<strong>Marketing kit ready.</strong> Edit the website fields below, then save to update the brochure.${{(data.market_sources || []).length ? ` ${{data.market_sources.length}} market source(s) are retained with the kit.` : ''}}`
          : mapReady
            ? '<strong>Course Map ready.</strong> Generate the marketing kit when you are ready to create public-facing copy.'
            : '<strong>Course Map required.</strong> Marketing is generated from the approved learning journey, not the draft syllabus.';
      const sources = data.market_sources || [];
      document.getElementById('marketingSources').innerHTML = sources.length
        ? '<strong>Market evidence:</strong> ' + sources.map((item, index) => item.url ? `<a href="${{esc(item.url)}}" target="_blank" rel="noopener">${{index + 1}}. ${{esc(item.organization || item.title || 'Source')}}</a>` : `${{index + 1}}. ${{esc(item.organization || item.title || 'Source')}}`).join(' · ')
        : '';
      const download = document.getElementById('downloadBrochure');
      download.classList.toggle('hidden', !currentMarketing.brochure_ready);
      if (currentMarketing.brochure_ready) {{
        const filename = `${{cleanFilenamePart(data.course_title || course.value)}} - BuildStak Course Brochure.pdf`;
        download.href = `/artifact?path=${{encodeURIComponent(currentMarketing.brochure_path)}}&filename=${{encodeURIComponent(filename)}}`;
      }}
    }}
    async function generateMarketing() {{
      if (!course.value || currentStatus?.course_map_ready !== true) {{
        msg.textContent = 'Generate and approve the Course Map before creating marketing content.';
        return;
      }}
      await post('/api/marketing-generate', {{course: course.value}});
      renderMarketing(currentMarketing);
    }}
    async function saveMarketingEdits() {{
      try {{
        const data = await api('/api/marketing-save', {{method:'POST', body:JSON.stringify({{course:course.value, marketing:marketingPayload()}})}});
        msg.textContent = data.message || 'Marketing content and brochure updated.';
        renderMarketing(data);
      }} catch (error) {{ msg.textContent = error.message; }}
    }}
    function renderOperatorTool() {{
      const select = document.getElementById('operatorTarget');
      const lessonSelect = document.getElementById('operatorLesson');
      const previouslySelected = select.value;
      const previouslySelectedLesson = lessonSelect.value;
      const previousAction = document.getElementById('operatorAction').value;
      operatorTargetMap = {{}};
      operatorTargetsByLesson = {{}};
      for (const lesson of currentStatus?.lessons || []) {{
        const lessonTargets = [];
        for (const group of approvalGroups) {{
          const pathField = `${{group.key}}_path`;
          const path = lesson[pathField];
          const status = lesson[group.approvalField];
          const revision = lesson[`${{group.approvalField}}_revision`];
          if (revision?.state === 'revision_requested') {{
            const stageByArtifact = {{study_guide:'study_guide', deck:'deck', pt_br_study_guide:'pt_br_book', pt_br_deck:'pt_br_deck', es_study_guide:'es_book', es_deck:'es_deck'}};
            const stage = stageByArtifact[group.artifactType];
            const matchingJobs = currentJobs.filter(job => String(job?.payload?.stage || '') === stage && Number(job?.lesson || (job?.payload?.lessons || [])[0] || 0) === Number(lesson.lesson));
            const latestJob = matchingJobs[matchingJobs.length - 1];
            const active = ['queued', 'running'].includes(latestJob?.state);
            const failed = latestJob?.state === 'failed';
            const id = `revision:${{lesson.lesson}}:${{group.key}}`;
            operatorTargetMap[id] = {{kind:'revision', lesson:Number(lesson.lesson), group, path, status, title:lesson.title, revision, stage, active, failed}};
            lessonTargets.push({{id, label: `${{group.title}} · ${{failed ? 'revision failed' : active ? 'revision in progress' : 'revision pending'}}`}});
            continue;
          }}
          if (!isDownloadablePath(path) || status === 'blocked') continue;
          const id = `artifact:${{lesson.lesson}}:${{group.key}}`;
          operatorTargetMap[id] = {{kind:'artifact', lesson:Number(lesson.lesson), group, path, status, title:lesson.title, revision}};
          lessonTargets.push({{id, label: `${{group.title}} · ${{status === 'approved' ? 'approved' : 'ready for review'}}`}});
        }}
        const requests = lesson.image_requests || [];
        if (requests.length) {{
          const id = `image-batch:${{lesson.lesson}}`;
          operatorTargetMap[id] = {{kind:'image', lesson:Number(lesson.lesson), requests}};
          lessonTargets.push({{id, label: `${{requests.length}} requested image${{requests.length === 1 ? '' : 's'}}`}});
        }}
        if (lessonTargets.length) operatorTargetsByLesson[String(lesson.lesson)] = lessonTargets;
      }}
      const availableLessons = Object.keys(operatorTargetsByLesson);
      const targetLesson = operatorTargetMap[previouslySelected]?.lesson;
      const selectedLesson = String(targetLesson || (availableLessons.includes(previouslySelectedLesson) ? previouslySelectedLesson : ''));
      lessonSelect.innerHTML = availableLessons.length
        ? '<option value="">Choose a lesson</option>' + availableLessons.map(number => `<option value="${{esc(number)}}">Lesson ${{String(number).padStart(2, '0')}}</option>`).join('')
        : '<option value="">No lesson needs operator action</option>';
      lessonSelect.disabled = !availableLessons.length;
      if (selectedLesson) lessonSelect.value = selectedLesson;
      renderOperatorTargetsForLesson(previouslySelected);
      const keptSelection = Boolean(previouslySelected && operatorTargetMap[previouslySelected] && String(operatorTargetMap[previouslySelected].lesson) === lessonSelect.value);
      renderOperatorToolDetails(!keptSelection);
      if (keptSelection) document.getElementById('operatorAction').value = previousAction;
    }}
    function renderOperatorTargetsForLesson(preferredTarget = '') {{
      const select = document.getElementById('operatorTarget');
      const targets = operatorTargetsByLesson[document.getElementById('operatorLesson').value] || [];
      select.innerHTML = targets.length
        ? targets.map(target => `<option value="${{esc(target.id)}}">${{esc(target.label)}}</option>`).join('')
        : '<option value="">Choose a lesson with a file or image request</option>';
      select.disabled = !targets.length;
      if (targets.some(target => target.id === preferredTarget)) select.value = preferredTarget;
    }}
    function renderOperatorToolDetails(resetAction = true) {{
      const target = operatorTargetMap[document.getElementById('operatorTarget').value];
      const action = document.getElementById('operatorAction');
      const details = document.getElementById('operatorToolDetails');
      if (!target) {{ action.disabled = true; details.innerHTML = '<div class="notice">Generated files will appear in the lesson table and become available here only after automatic QA passes.</div>'; return; }}
      action.disabled = false;
      const actionOptions = target.kind === 'image'
        ? [['attach_images', 'Attach requested images']]
        : target.kind === 'revision'
          ? [['retry_revision', 'Retry requested revision']]
          : [['approve', 'Approve'], ['request_edits', 'Request edits']];
      const previousAction = action.value;
      action.innerHTML = actionOptions.map(([value, label]) => `<option value="${{value}}">${{label}}</option>`).join('');
      const defaultAction = target.kind === 'image' ? 'attach_images' : target.kind === 'revision' ? 'retry_revision' : (target.status === 'approved' ? 'request_edits' : 'approve');
      action.value = !resetAction && actionOptions.some(([value]) => value === previousAction) ? previousAction : defaultAction;
      if (target.kind === 'image') {{
        const requestList = target.requests.map(request => `<li><strong>${{esc(request.visual_id)}}</strong> · ${{esc(request.learning_claim || request.purpose || '')}}</li>`).join('');
        details.innerHTML = `<div class="notice"><strong>Lesson ${{String(target.lesson).padStart(2, '0')}} technical image batch</strong><ul>${{requestList}}</ul></div><label>Image files</label><input id="operatorImageFiles" type="file" multiple accept=".png,.jpg,.jpeg,.webp"><label>Sources and URLs</label><textarea id="operatorImageSources" placeholder="filename.ext | source or attribution | https://source-url\nOne line per file, in the same order as the requests above."></textarea>`;
      }} else if (target.kind === 'revision') {{
        const requestItems = (target.revision?.requests || []).map((request, index) => `<li><strong>Request ${{index + 1}}:</strong> ${{esc(request.note || 'Revision requested.')}}</li>`).join('');
        const interactionLabels = {{request:'Request received', retry_requested:'Retry requested', worker_started:'Worker response', worker_failed:'Worker problem', ready_for_review:'Correction ready for review', approved:'Correction approved'}};
        let interactions = target.revision?.interactions || [];
        if (!interactions.length && (target.revision?.requests || []).length) {{
          interactions = [{{type:'request', at:target.revision?.accepted_at, requests:target.revision.requests}}];
        }}
        const history = interactions.map((entry) => {{
          const when = entry.at ? new Date(entry.at).toLocaleString() : 'Time not recorded';
          const listedRequests = (entry.requests || []).map(item => `<li>${{esc(item.note || 'Revision requested.')}}</li>`).join('');
          const problems = (entry.problems || []).map(item => `<li>${{esc(item)}}</li>`).join('');
          const resolutions = (entry.resolutions || []).map(item => `<li><strong>Slide ${{esc(item.slide_number || '—')}}:</strong> ${{esc(item.change || item.problem || 'Correction recorded.')}}</li>`).join('');
          return `<div class="notice"><strong>${{esc(interactionLabels[entry.type] || entry.type || 'Interaction')}} · ${{esc(when)}}</strong>${{entry.message ? `<div>${{esc(entry.message)}}</div>` : ''}}${{listedRequests ? `<div>Requested:</div><ul>${{listedRequests}}</ul>` : ''}}${{problems ? `<div>Problems:</div><ul>${{problems}}</ul>` : ''}}${{resolutions ? `<div>Responses:</div><ul>${{resolutions}}</ul>` : ''}}</div>`;
        }}).join('');
        const statusText = target.failed
          ? 'The request was accepted, but production stopped before a corrected file was created. Retry the revision to continue.'
          : target.active
            ? 'The request was accepted and the corrected file is being produced. It will appear here when every automatic check passes.'
            : 'The request was accepted. No active production job is visible, so you can safely retry it.';
        const baselineLink = isDownloadablePath(target.path) ? `<div><a class="download-link" href="/artifact?path=${{encodeURIComponent(target.path)}}" target="_blank" rel="noopener">Open approved baseline</a></div>` : '';
        details.innerHTML = `<div class="notice"><strong>${{target.failed ? 'Revision failed' : target.active ? 'Revision in progress' : 'Revision pending'}}</strong><div>${{statusText}}</div>${{requestItems ? `<ol>${{requestItems}}</ol>` : ''}}</div><div><strong>Communication history</strong></div>${{history}}${{baselineLink}}`;
        action.disabled = target.active;
      }} else {{
        const group = target.group;
        const filename = downloadFilename(group, target.path, target);
        const revisionItems = target.revision?.requests?.length ? `<div class="notice"><strong>Requested corrections applied</strong><ol>${{target.revision.requests.map((request, index) => `<li><strong>Request ${{index + 1}} · ${{esc(request.requested_at ? new Date(request.requested_at).toLocaleString() : target.revision.accepted_at ? new Date(target.revision.accepted_at).toLocaleString() : 'time not recorded')}}:</strong> ${{esc(request.note || 'Revision requested.')}}</li>`).join('')}}</ol>${{(target.revision.interactions || []).filter(entry => entry.type !== 'request').map(entry => {{ const response = (entry.problems || []).join(' · ') || (entry.resolutions || []).map(item => `Slide ${{item.slide_number}}: ${{item.change || item.problem}}`).join(' · ') || entry.message || 'Worker interaction recorded.'; return `<div><strong>${{esc(entry.at ? new Date(entry.at).toLocaleString() : 'Time not recorded')}}:</strong> ${{esc(response)}}</div>`; }}).join('')}}<div>Review the corrected file below, then approve it or request another edit.</div></div>` : '';
        const supportingFiles = action.value === 'request_edits' ? `<div class="hint">Add every requested change before applying the action. The agent receives them as one revision. Evidence files document an issue only; files marked for use can guide the edit and never become student references automatically.</div><div id="operatorRevisionRequests"></div><button type="button" class="mini" onclick="addRevisionRequest()">+ Add another requested change</button>` : '';
        details.innerHTML = `${{revisionItems}}<div><a class="download-link" href="/artifact?path=${{encodeURIComponent(target.path)}}&filename=${{encodeURIComponent(filename)}}" target="_blank" rel="noopener">Download selected file</a></div>${{action.value === 'request_edits' ? '' : '<textarea id="operatorNote" placeholder="Optional approval note."></textarea>'}}${{supportingFiles}}`;
        if (action.value === 'request_edits') {{ revisionRequestCount = 0; addRevisionRequest(); }}
      }}
    }}
    function addRevisionRequest() {{
      const holder = document.getElementById('operatorRevisionRequests');
      if (!holder) return;
      const id = revisionRequestCount++;
      const remove = id ? `<button type="button" class="mini danger" onclick="document.getElementById('revision-request-${{id}}').remove()">Remove</button>` : '';
      holder.insertAdjacentHTML('beforeend', `<div class="notice" id="revision-request-${{id}}"><strong>Requested change ${{id + 1}}</strong> ${{remove}}<textarea class="revision-note" data-request-id="${{id}}" placeholder="Describe this specific requested change."></textarea><label>Supporting files or images <span class="muted">(optional)</span></label><input class="revision-files" data-request-id="${{id}}" type="file" multiple accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp"><label>Attachment use</label><select class="revision-attachment-mode" data-request-id="${{id}}"><option value="evidence_only">Review evidence only — do not use or cite</option><option value="use_in_revision">Use in this requested change</option></select><label>Sources and URLs <span class="muted">(recommended for usable images)</span></label><textarea class="revision-sources" data-request-id="${{id}}" placeholder="filename.ext | source or attribution | https://source-url\nOne line per file."></textarea></div>`);
    }}
    function showOperatorResult(text, tone = '') {{
      const result = document.getElementById('operatorResult');
      result.textContent = text;
      result.className = `operator-result ${{tone}}`;
    }}
    async function applyOperatorAction() {{
      if (operatorActionInFlight) return;
      const target = operatorTargetMap[document.getElementById('operatorTarget').value];
      if (!target) return;
      const action = document.getElementById('operatorAction').value;
      const button = document.getElementById('applyOperatorAction');
      operatorActionInFlight = true;
      button.disabled = true;
      button.textContent = 'Applying…';
      msg.textContent = 'Applying operator action…';
      showOperatorResult('Saving your action…');
      try {{
        if (action === 'attach_images') {{ await uploadVisualBatch(target.lesson, target.requests); return; }}
        if (action === 'retry_revision') {{
          const data = await post('/api/produce', {{course: course.value, stage: target.stage, lessons: [target.lesson]}});
          showOperatorResult(data.message || 'Requested revision queued again.', 'success');
          return;
        }}
        const note = document.getElementById('operatorNote')?.value || '';
        if (action === 'request_edits' && ![...document.querySelectorAll('.revision-note')].some(item => item.value.trim())) {{ msg.textContent = 'Write at least one requested change before sending the file back.'; return; }}
        if (action === 'approve') {{ await approveArtifact(target.group.artifactType, null, target.path, target.lesson, note); return; }}
        await requestEdits(target.group.artifactType, null, target.lesson, note, target.path);
      }} finally {{
        operatorActionInFlight = false;
        button.disabled = false;
        button.textContent = 'Apply action';
      }}
    }}
    function scopeKind(value) {{
      return String(value || '').startsWith('lesson_') ? 'lesson' : 'course';
    }}
    function lessonNumber(value) {{
      const match = String(value || '').match(/^lesson_(\\d+)$/);
      return match ? Number(match[1]) : 1;
    }}
    function selected(value, expected) {{ return value === expected ? 'selected' : ''; }}
    function uploadRow(u) {{
      const id = esc(u.upload_id);
      const scope = scopeKind(u.scope);
      const lesson = lessonNumber(u.scope);
      const role = u.purpose === 'revision_evidence' ? 'Review evidence only' : u.purpose === 'revision_material' ? 'Use in requested revision' : u.purpose === 'visual_response' ? 'Requested visual response' : 'Course source';
      return `<tr>
        <td><strong>${{esc(u.filename)}}</strong></td>
        <td><div class="upload-edit">
          <select class="mini" id="scope-${{id}}" onchange="toggleUploadLesson('${{id}}')">
            <option value="course" ${{selected(scope, 'course')}}>Course</option>
            <option value="lesson" ${{selected(scope, 'lesson')}}>Lesson</option>
          </select>
          <input class="mini" id="lesson-${{id}}" type="number" min="1" value="${{lesson}}">
        </div></td>
        <td>${{esc(role)}}</td>
        <td><select class="mini" id="policy-${{id}}">
          <option value="context_only" ${{selected(u.reference_policy, 'context_only')}}>Context only - do not cite</option>
          <option value="image_only" ${{selected(u.reference_policy, 'image_only')}}>Do not cite text - images allowed</option>
          <option value="reference_only" ${{selected(u.reference_policy, 'reference_only')}}>Can cite - no images</option>
          <option value="reference_and_images" ${{selected(u.reference_policy, 'reference_and_images')}}>Can cite + images allowed</option>
        </select></td>
        <td>${{Math.round((u.size_bytes || 0) / 1024)}} KB</td>
        <td><div class="upload-actions"><button class="mini" onclick="saveUpload('${{id}}')">Save</button><button class="mini danger" onclick="deleteUpload('${{id}}')">Delete</button></div></td>
      </tr>`;
    }}
    function renderUploadTables(items) {{
      const sourceMaterials = items.filter(item => !item.purpose || item.purpose === 'source_material');
      const editingMaterials = items.filter(item => item.purpose && item.purpose !== 'source_material');
      document.getElementById('uploads').innerHTML = sourceMaterials.length
        ? sourceMaterials.map(uploadRow).join('')
        : '<tr><td colspan="6" class="muted">No source materials attached yet.</td></tr>';
      document.getElementById('revisionUploads').innerHTML = editingMaterials.length
        ? editingMaterials.map(uploadRow).join('')
        : '<tr><td colspan="6" class="muted">No editing materials attached yet.</td></tr>';
      for (const item of items) toggleUploadLesson(item.upload_id);
    }}
    function toggleUploadLesson(id) {{
      const lesson = document.getElementById('lesson-' + id);
      const scope = document.getElementById('scope-' + id);
      if (!lesson || !scope) return;
      const isLesson = scope.value === 'lesson';
      lesson.classList.toggle('hidden', !isLesson);
      lesson.disabled = !isLesson;
    }}
    async function api(path, options) {{
      const headers = options?.body instanceof FormData ? {{}} : {{'Content-Type': 'application/json'}};
      const res = await fetch(path, Object.assign({{headers}}, options || {{}}));
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.message || 'Request failed');
      return data;
    }}
    async function post(path, body) {{
      try {{
        const data = await api(path, {{method: 'POST', body: JSON.stringify(body || {{}})}});
        msg.textContent = data.message || 'Done.';
        const route = document.getElementById('route');
        if (data.route && route) route.innerHTML = `<strong>${{esc(data.route.intent)}}</strong> · ${{esc(data.route.stage)}}<br>${{esc(data.route.next_action)}}`;
        await loadWorkspace();
        return data;
      }} catch (error) {{
        msg.textContent = error.message;
        throw error;
      }}
    }}
    function resetWorkspace(showMessage = true) {{
      currentStatus = null;
      currentJobs = [];
      currentWorkerControls = {{content: false, delivery: false, video: false}};
      currentMarketing = null;
      operatorTargetMap = {{}};
      operatorTargetsByLesson = {{}};
      course.value = '';
      document.getElementById('courseTitle').value = '';
      document.getElementById('courseSlug').value = '';
      document.getElementById('syllabus').value = '';
      document.getElementById('expectedLessons').value = '10';
      document.getElementById('uploadScope').value = 'course';
      document.getElementById('referencePolicy').value = 'context_only';
      document.getElementById('uploadLesson').value = '1';
      document.getElementById('files').value = '';
      renderMarketing(null);
      uploadQueue = [];
      renderUploadQueue();
      setLevel('Basic');
      document.getElementById('uploads').innerHTML = '<tr><td colspan="6" class="muted">No source materials attached yet.</td></tr>';
      document.getElementById('revisionUploads').innerHTML = '<tr><td colspan="6" class="muted">No editing materials attached yet.</td></tr>';
      toggleLessonInput();
      renderPipeline();
      renderLessonSelection();
      renderVideoGenerator();
      renderJobs();
      if (showMessage) msg.textContent = 'New course workspace ready.';
    }}
    async function restoreSavedCourse() {{
      const buttons = [document.getElementById('refreshTop'), document.getElementById('refreshWorkspace')];
      buttons.forEach(button => button.disabled = true);
      try {{
        const data = await api('/api/courses');
        const picker = document.getElementById('coursePicker');
        const active = (data.courses || []).filter(item => item.status !== 'completed');
        picker.innerHTML = active.length
          ? active.map(item => `<option value="${{esc(item.course_slug)}}">${{esc(item.title)}} · in progress</option>`).join('')
          : '<option value="">No unfinished courses</option>';
        const selected = active.find(item => item.course_slug === course.value) || active[0];
        if (!selected) {{ resetWorkspace(false); return; }}
        course.value = selected.course_slug;
        picker.value = selected.course_slug;
        await loadWorkspace();
        msg.textContent = `Loaded saved course: ${{selected.title}}`;
      }} catch (error) {{
        msg.textContent = error.message;
      }} finally {{
        buttons.forEach(button => button.disabled = false);
      }}
    }}
    function openNewCourse() {{
      resetWorkspace();
      showConsolePage('sections-1-2', true);
      document.getElementById('brief').scrollIntoView({{behavior: 'smooth', block: 'start'}});
      document.getElementById('courseTitle').focus();
    }}
    function restartWorkspace() {{
      resetWorkspace();
      msg.textContent = 'Workspace cleared. The saved course remains on the server.';
      showConsolePage('sections-1-2', true);
      document.getElementById('brief').scrollIntoView({{behavior: 'smooth', block: 'start'}});
    }}
    async function deleteCourse() {{
      if (!course.value) {{
        msg.textContent = 'Choose a saved course before deleting it.';
        return;
      }}
      const selected = course.value;
      if (!confirm(`Delete ${'{'}selected{'}'} permanently? This removes its course files, uploaded materials, and job history from the server and cannot be undone.`)) return;
      try {{
        const data = await api('/api/delete-course', {{method: 'POST', body: JSON.stringify({{course: selected}})}});
        msg.textContent = data.message;
        await restoreSavedCourse();
      }} catch (error) {{ msg.textContent = error.message; }}
    }}
    function operatorFormIsBeingEdited() {{
      const form = document.getElementById('approvals');
      if (!form) return false;
      if (form.contains(document.activeElement)) return true;
      return [...form.querySelectorAll('textarea')].some(input => input.value.trim())
        || [...form.querySelectorAll('input[type="file"]')].some(input => input.files?.length);
    }}
    async function loadWorkspace() {{
      if (!course.value.trim()) {{
        return;
      }}
      if (workspaceLoadInFlight) return;
      workspaceLoadInFlight = true;
      try {{
        currentStatus = await api('/api/status?course=' + encodeURIComponent(course.value));
        const jobs = await api('/api/jobs?course=' + encodeURIComponent(course.value));
        currentJobs = jobs.jobs || [];
        currentWorkerControls = jobs.worker_controls || currentWorkerControls;
        renderJobs();
        renderWorkerErrors(jobs.worker_errors || []);
        const uploads = await api('/api/uploads?course=' + encodeURIComponent(course.value));
        renderUploadTables(uploads.uploads || []);
        const marketing = await api('/api/marketing?course=' + encodeURIComponent(course.value));
        renderMarketing(marketing);
        renderPipeline();
        renderLessonSelection();
        renderVideoGenerator();
        // Cost loading is intentionally independent: an unavailable report
        // must never hold up production, approvals, or revision controls.
        renderCosts(null);
        api('/api/costs?course=' + encodeURIComponent(course.value))
          .then(renderCosts)
          .catch(() => {{ document.getElementById('costProviders').textContent = 'Cost report is temporarily unavailable. Course production remains available.'; }});
      }} catch (error) {{
        msg.textContent = error.message;
      }} finally {{
        workspaceLoadInFlight = false;
      }}
    }}
    async function refreshWorkspaceIfIdle() {{
      if (document.hidden || operatorActionInFlight || operatorFormIsBeingEdited()) return;
      await loadWorkspace();
    }}
    let workspaceRefreshTimer = null;
    function scheduleWorkspaceRefresh() {{
      if (workspaceRefreshTimer) clearTimeout(workspaceRefreshTimer);
      const hasActiveWork = currentJobs.some(job => ['queued', 'running'].includes(job.state));
      const delay = hasActiveWork ? 30000 : 120000;
      workspaceRefreshTimer = setTimeout(async () => {{
        await refreshWorkspaceIfIdle();
        scheduleWorkspaceRefresh();
      }}, delay);
    }}
    function renderJobs() {{
      renderWorkerLanes();
      const active = currentJobs.slice().reverse().find(j => ['queued', 'running'].includes(j.state));
      const completedCourseMap = Boolean(currentStatus?.course_map_ready);
      const relevantJobs = currentJobs.filter(job => !(
        completedCourseMap && !active && job.state === 'failed' && job.request_type === 'course_start'
      ));
      const latest = active || relevantJobs[relevantJobs.length - 1];
      const holder = document.getElementById('currentActivity');
      const waiting = (currentStatus?.lessons || []).filter(item => item.visual_status === 'waiting_images');
      if (!active && waiting.length) {{
        holder.innerHTML = `<span class="state queued">waiting for images</span> · Lesson ${{waiting.map(item => Number(item.lesson)).join(', ')}}`;
        return;
      }}
      const corrected = (currentStatus?.lessons || []).find(item => approvalGroups.some(group => item[group.approvalField] === 'ready_for_review'));
      if (!active && corrected) {{
        holder.innerHTML = `<span class="state completed">ready for review</span> · A corrected file is available for Lesson ${{String(corrected.lesson).padStart(2, '0')}}.`;
        return;
      }}
      if (!latest) {{
        holder.textContent = 'Idle.';
        return;
      }}
      if (!active && latest.state !== 'failed') {{
        holder.textContent = 'Idle.';
        return;
      }}
      const state = active ? latest.state : 'needs attention';
      const detail = active ? activeJobMessage(latest) : operatorJobMessage(latest);
      const timing = active ? jobTiming(latest) : '';
      holder.innerHTML = `<span class="state ${{esc(latest.state)}}">${{esc(state)}}</span> · ${{esc(detail)}}${{timing ? ` · ${{esc(timing)}}` : ''}}`;
    }}
    function renderWorkerLanes() {{
      for (const lane of ['content', 'delivery', 'video']) {{
        const holder = document.getElementById(lane + 'LaneStatus');
        const taskHolder = document.getElementById(lane + 'LaneTasks');
        const control = document.getElementById(lane + 'LaneControl');
        const paused = Boolean(currentWorkerControls[lane]);
        const jobs = currentJobs.filter(job => String(job.lane || '') === lane && ['queued', 'running'].includes(job.state));
        const running = jobs.find(job => job.state === 'running');
        const queued = jobs.filter(job => job.state === 'queued').length;
        if (paused) {{
          holder.innerHTML = '<span class="state failed">Stopped</span> · Queue is paused';
        }} else if (running) {{
          holder.innerHTML = `<span class="state running">Working</span> · ${{esc(activeJobMessage(running))}}${{queued ? ` · ${{queued}} queued` : ''}}`;
        }} else if (queued) {{
          holder.innerHTML = `<span class="state queued">Ready</span> · ${{queued}} job${{queued === 1 ? '' : 's'}} queued`;
        }} else {{
          holder.innerHTML = `<span class="state completed">Available</span> · Ready for the next selected action`;
        }}
        taskHolder.innerHTML = jobs.length
          ? jobs.map(job => `<li><span class="state ${{esc(job.state)}}">${{esc(job.state)}}</span> · ${{esc(activeJobMessage(job))}}</li>`).join('')
          : '<li>No pending tasks.</li>';
        control.textContent = paused ? 'Resume worker' : 'Stop & clear queue';
        control.classList.toggle('danger', !paused);
        control.classList.toggle('primary', paused);
        control.disabled = workerControlInFlight.has(lane);
      }}
    }}
    async function controlWorker(lane) {{
      if (workerControlInFlight.has(lane)) return;
      const paused = Boolean(currentWorkerControls[lane]);
      if (!paused && !confirm(`Stop the ${{lane}} worker and cancel every queued or running job in this lane? Approved files will not be changed.`)) return;
      workerControlInFlight.add(lane);
      renderWorkerLanes();
      try {{
        const data = await post('/api/worker-control', {{lane, action: paused ? 'resume' : 'stop'}});
        msg.textContent = data.message;
      }} finally {{
        workerControlInFlight.delete(lane);
        renderWorkerLanes();
      }}
    }}
    function activeJobMessage(job) {{
      const activity = String(job?.progress?.activity || '');
      const labels = {{
        'model_text:source_research': 'Researching current sources',
        'model_text:technical_content': 'Writing the course book',
        'model_text:pedagogy_review': 'Checking learning design',
        'model_text:citation_review': 'Checking citations',
        'model_text:design_review': 'Checking document design',
        'model_text:visual_planning': 'Planning visuals',
        'model_text:visual_review': 'Checking visual accuracy',
        'model_image': 'Creating an illustration',
        'study_guide_render': 'Assembling the course book',
        'pdf_layout_qa': 'Checking the final PDF layout'
      }};
      return labels[activity] || operatorJobMessage(job);
    }}
    function jobTiming(job) {{
      const stage = String(job?.payload?.stage || job?.request_type || '');
      const lessonCount = Math.max(1, (job?.payload?.lessons || []).length || Number(job?.lesson || 1));
      const minutesByStage = {{
        course_start: 6,
        marketing: 12,
        study_guide: 25,
        deck: 6,
        translations_book: 16,
        translations_deck: 12,
        pt_br_book: 8,
        es_book: 8,
        pt_br_deck: 6,
        es_deck: 6
      }};
      const estimatedMinutes = (minutesByStage[stage] || 10) * lessonCount;
      const started = Date.parse(job.updated_at || job.created_at || '');
      if (!Number.isFinite(started)) return `Estimated completion: about ${{estimatedMinutes}} min`;
      const elapsedMinutes = Math.max(0, (Date.now() - started) / 60000);
      const remaining = Math.max(1, Math.ceil(estimatedMinutes - elapsedMinutes));
      if (elapsedMinutes >= estimatedMinutes) return `Running longer than the usual ${{estimatedMinutes}} min; still processing`;
      return `Estimated completion: about ${{remaining}} min remaining`;
    }}
    function operatorJobMessage(job) {{
      const raw = String(job?.last_error || job?.input_summary || job?.request_type || '');
      if (/source\\/reference.*QA failed/i.test(raw)) return 'Automatic source review needs another pass before the file can be released.';
      if (/layout automatic QA failed/i.test(raw)) return 'Automatic layout review needs another pass before the file can be released.';
      if (/Process-flow (?:title\\/detail exceeds|title does not fit|detail does not fit)/i.test(raw)) return 'A translated process diagram needs shorter text. No incomplete PDF was released.';
      if (/Comparison-matrix cell (?:exceeds|does not fit)/i.test(raw)) return 'A translated comparison table needs shorter text. No incomplete PDF was released.';
      if (/Localized course book layout QA failed/i.test(raw)) return 'The translated course book needs another automatic layout correction before release.';
      if (/Independent study-guide reviewers still require changes/i.test(raw)) return 'The Course Book reviewers found unresolved content issues. No new file was released, and the previous approved version remains unchanged.';
      if (/Traceback|File "\\/opt\\/profgreg/i.test(raw)) {{
        const parts = raw.split(/(?:RuntimeError|ValueError|ModelRequestError):\\s*/);
        const detail = parts.length > 1 ? parts[parts.length - 1].trim() : '';
        return detail && !/Traceback|File "\\/opt\\/profgreg/i.test(detail) ? detail.slice(0, 500) : 'Production needs attention. Technical details were recorded internally.';
      }}
      return raw.replace(/^.*?(RuntimeError|ValueError|ModelRequestError):\\s*/s, '').slice(-500);
    }}
    async function saveUpload(id) {{
      await post('/api/upload-update', {{ course: course.value, upload_id: id, scope: document.getElementById('scope-' + id).value, lesson: Number(document.getElementById('lesson-' + id).value || 1), reference_policy: document.getElementById('policy-' + id).value }});
    }}
    async function deleteUpload(id) {{
      if (!confirm('Delete this uploaded file from this course?')) return;
      await post('/api/upload-delete', {{ course: course.value, upload_id: id }});
    }}
    function toggleLessonInput() {{
      const lesson = document.getElementById('uploadLesson');
      const isLessonScope = document.getElementById('uploadScope').value === 'lesson';
      lesson.classList.toggle('hidden', !isLessonScope);
      lesson.disabled = !isLessonScope;
    }}
    function setLevel(level) {{
      document.querySelectorAll('[data-level]').forEach(btn => btn.classList.toggle('active', btn.dataset.level === level));
      document.getElementById('expectedLessons').value = expectedLessonsByLevel[level] || 10;
    }}
    function formatUploadSize(bytes) {{
      if (!Number.isFinite(bytes) || bytes < 1024) return `${{bytes || 0}} B`;
      if (bytes < 1024 * 1024) return `${{Math.round(bytes / 1024)}} KB`;
      return `${{(bytes / (1024 * 1024)).toFixed(1)}} MB`;
    }}
    function renderUploadQueue() {{
      const holder = document.getElementById('uploadQueue');
      if (!holder) return;
      holder.innerHTML = uploadQueue.map(item => `<div class="upload-queue-item ${{esc(item.state)}}">
        <div class="upload-queue-meta"><strong>${{esc(item.name)}}</strong><span>${{esc(item.status)}}</span></div>
        <div class="upload-queue-meta"><span>${{esc(formatUploadSize(item.size))}}</span><span>${{Math.round(item.progress)}}%</span></div>
        <div class="upload-bar"><span style="width:${{Math.max(0, Math.min(100, item.progress))}}%"></span></div>
      </div>`).join('');
    }}
    function setUploadQueue(files, state = 'ready', status = 'Ready to upload', progress = 0) {{
      uploadQueue = [...files].map(file => ({{ name: file.name, size: file.size, state, status, progress }}));
      renderUploadQueue();
    }}
    function updateUploadQueue(state, status, progress) {{
      uploadQueue.forEach(item => {{ item.state = state; item.status = status; item.progress = progress; }});
      renderUploadQueue();
    }}
    async function ensureCourseIntake() {{
      const title = document.getElementById('courseTitle').value.trim();
      const syllabus = document.getElementById('syllabus').value.trim();
      if (!title || !syllabus) {{
        throw new Error('Enter the course name and syllabus to create this course workspace.');
      }}
      if (course.value.trim()) return course.value;
      const level = document.querySelector('[data-level].active')?.dataset.level || 'Basic';
      const created = await api('/api/create-course', {{
        method: 'POST',
        body: JSON.stringify({{
          title,
          level,
          expected_lessons: Number(document.getElementById('expectedLessons').value || 0),
          slug: document.getElementById('courseSlug').value,
          syllabus
        }})
      }});
      const manualSlug = document.getElementById('courseSlug').value;
      course.value = created.course_slug || manualSlug;
      await restoreSavedCourse();
      return course.value;
    }}
    async function startProductionFlow() {{
      try {{
        await ensureCourseIntake();
      }} catch (error) {{
        msg.textContent = error.message;
        return;
      }}
      return post('/api/start-course', {{course: course.value}});
    }}
    function selectedLessons() {{
      return [...document.querySelectorAll('[data-lesson-select]:checked')]
        .map(input => Number(input.dataset.lessonSelect))
        .filter(Number.isFinite);
    }}
    function renderLessonSelection() {{
      const holder = document.getElementById('lessonSelection');
      const lessons = currentStatus?.lessons || [];
      holder.innerHTML = lessons.length
        ? lessons.map(item => `<tr>
            <td><input type="checkbox" data-lesson-select="${{esc(item.lesson)}}" aria-label="Select Lesson ${{esc(item.lesson)}}"></td>
            <td class="lesson-title-cell">Lesson ${{esc(item.lesson)}}<br><span class="muted">${{esc(item.title || '')}}</span></td>
            <td>${{visualCell(item)}}</td>
            <td>${{documentCell(item, 'study_guide', 'study_guide_path', 'Course Book')}}</td>
            <td>${{documentCell(item, 'deck', 'deck_path', 'Presentation')}}</td>
            <td>${{documentCell(item, 'pt_br_study_guide', 'pt_br_study_guide_path', 'PT-BR Book')}}</td>
            <td>${{documentCell(item, 'pt_br_deck', 'pt_br_deck_path', 'PT-BR Deck')}}</td>
            <td>${{documentCell(item, 'es_study_guide', 'es_study_guide_path', 'ES Book')}}</td>
            <td>${{documentCell(item, 'es_deck', 'es_deck_path', 'ES Deck')}}</td>
          </tr>`).join('')
        : '<tr><td colspan="9" class="muted">Generate the Course Map first to choose lessons.</td></tr>';
      document.getElementById('selectAllLessons').checked = false;
    }}
    function safeAiStudiosUrl(value) {{
      try {{
        const url = new URL(String(value || ''));
        return url.protocol === 'https:' && (url.hostname === 'aistudios.com' || url.hostname.endsWith('.aistudios.com')) ? url.href : '';
      }} catch (_error) {{ return ''; }}
    }}
    function safeHttpsUrl(value) {{
      try {{
        const url = new URL(String(value || ''));
        return url.protocol === 'https:' && !url.username && !url.password ? url.href : '';
      }} catch (_error) {{ return ''; }}
    }}
    function latestProductionJob(item, stage) {{
      return currentJobs.filter(job =>
        job.request_type === 'production_stage'
        && String(job?.payload?.stage || '') === stage
        && Number(job?.lesson || (job?.payload?.lessons || [])[0] || 0) === Number(item.lesson)
      ).slice(-1)[0];
    }}
    function activeProductionJob(item, stage) {{
      const job = latestProductionJob(item, stage);
      return job && ['queued', 'running'].includes(job.state) ? job : null;
    }}
    function activeVideoJob(item, locale, video) {{
      return currentJobs.find(job => {{
        if (job.request_type !== 'video_generation' || !['queued', 'running'].includes(job.state)) return false;
        if (Number(job?.lesson || 0) !== Number(item.lesson)) return false;
        if (String(job?.payload?.locale || '') !== locale) return false;
        const jobSource = String(job?.payload?.sourceSha256 || '');
        const videoSource = String(video?.source_sha256 || '');
        return !jobSource || !videoSource || jobSource === videoSource;
      }});
    }}
    function videoCell(item, locale, label) {{
      const video = item?.videos?.[locale] || {{status:'waiting_approved_presentation'}};
      const activeJob = activeVideoJob(item, locale, video);
      const labels = {{
        waiting_approved_presentation: 'waiting for approved presentation',
        presentation_too_large: 'presentation exceeds 20 MB',
        ready: 'ready for video generation',
        ready_new_revision: 'new approved revision ready',
        queued: 'queued', uploading: 'uploading', configuring: 'configuring',
        generating_transcripts: 'generating transcripts', awaiting_export_confirmation: 'awaiting export confirmation',
        exporting: 'exporting', rendering: 'rendering',
        video_ready: 'video available', needs_attention: 'needs attention', failed: 'failed'
      }};
      const status = activeJob ? 'generating' : (labels[video.status] || String(video.status || 'not started').replace(/_/g, ' '));
      const links = [];
      const canStart = !activeJob && ['ready', 'ready_new_revision', 'uploading', 'configuring', 'generating_transcripts', 'awaiting_export_confirmation', 'exporting', 'rendering', 'needs_attention', 'failed'].includes(video.status);
      if (canStart) {{
        const action = ['uploading', 'configuring', 'generating_transcripts', 'awaiting_export_confirmation', 'exporting', 'rendering'].includes(video.status) ? 'Resume monitoring' : 'Start video';
        links.push(`<button class="subtle video-start" onclick="startVideo(${{Number(item.lesson)}}, '${{esc(locale)}}')">${{action}}</button>`);
      }}
      const projectUrl = safeAiStudiosUrl(video.project_url);
      const downloadUrl = safeHttpsUrl(video.download_url);
      if (projectUrl) links.push(`<a class="doc-link" href="${{esc(projectUrl)}}" target="_blank" rel="noopener">AI Studios project</a>`);
      if (downloadUrl) links.push(`<a class="doc-link" href="${{esc(downloadUrl)}}" target="_blank" rel="noopener">download video</a>`);
      return `<span class="doc-cell">${{statusPill(status)}}${{links.length ? ' ' + links.join(' · ') : ''}}</span>`;
    }}
    async function startVideo(lesson, locale) {{
      try {{
        const result = await post('/api/video-generate', {{course: course.value, lesson, locale}});
        showOperatorResult(result.message || 'Video job queued.', 'success');
        await loadWorkspace();
      }} catch (error) {{ msg.textContent = error.message; }}
    }}
    function renderVideoGenerator() {{
      const holder = document.getElementById('videoGeneratorRows');
      const lessons = currentStatus?.lessons || [];
      const videos = lessons.flatMap(item => Object.values(item.videos || {{}}));
      const inProductionStates = new Set(['queued', 'uploading', 'configuring', 'generating_transcripts', 'awaiting_export_confirmation', 'exporting', 'rendering']);
      const available = videos.filter(video => video.status === 'video_ready').length;
      const activeVideoJobs = currentJobs.filter(job => job.request_type === 'video_generation' && ['queued', 'running'].includes(job.state));
      const activeVideoKeys = new Set(activeVideoJobs.map(job => `${{Number(job?.lesson || 0)}}:${{String(job?.payload?.locale || '')}}:${{String(job?.payload?.sourceSha256 || '')}}`));
      const persistedInProduction = lessons.flatMap(item => Object.entries(item.videos || {{}}).filter(([locale, video]) => {{
        if (!inProductionStates.has(video.status)) return false;
        const exactKey = `${{Number(item.lesson)}}:${{locale}}:${{String(video?.source_sha256 || '')}}`;
        const keyWithoutSource = `${{Number(item.lesson)}}:${{locale}}:`;
        return !activeVideoKeys.has(exactKey) && !activeVideoKeys.has(keyWithoutSource);
      }}));
      const inProduction = activeVideoJobs.length + persistedInProduction.length;
      const waiting = videos.filter(video => video.status === 'waiting_approved_presentation').length;
      document.getElementById('videoGeneratorSummary').innerHTML = `<div class="metric"><div class="label">Videos available</div><div class="value">${{available}}</div></div><div class="metric"><div class="label">In production</div><div class="value">${{inProduction}}</div></div><div class="metric"><div class="label">Waiting for presentation</div><div class="value">${{waiting}}</div></div>`;
      holder.innerHTML = lessons.length ? lessons.map(item => `<tr>
        <td class="lesson-title-cell">Lesson ${{esc(item.lesson)}}<br><span class="muted">${{esc(item.title || '')}}</span></td>
        <td>${{videoCell(item, 'en', 'English')}}</td>
        <td>${{videoCell(item, 'pt', 'Portuguese')}}</td>
        <td>${{videoCell(item, 'es', 'Spanish')}}</td>
      </tr>`).join('') : '<tr><td colspan="4" class="muted">Generate and approve a presentation to prepare its video.</td></tr>';
    }}
    function visualCell(item) {{
      return item.visual_status === 'included'
        ? '<span class="visual-present" aria-label="Visuals present" title="Visuals present">✓</span>'
        : '';
    }}
    function documentCell(item, statusField, pathField, label) {{
      const status = item[statusField] || 'missing';
      const path = item[pathField] || '';
      const revision = item[`${{statusField}}_revision`];
      const pendingRevision = status === 'revision_requested';
      const stageByStatus = {{study_guide:'study_guide', deck:'deck', pt_br_study_guide:'pt_br_book', pt_br_deck:'pt_br_deck', es_study_guide:'es_book', es_deck:'es_deck'}};
      const latestJob = latestProductionJob(item, stageByStatus[statusField]);
      const activeJob = latestJob && ['queued', 'running'].includes(latestJob.state) ? latestJob : null;
      const failedJob = latestJob?.state === 'failed';
      const normalized = activeJob
        ? 'generating'
        : status === 'approved'
        ? (revision?.state === 'approved' ? 'revision approved' : 'approved')
        : pendingRevision && failedJob
          ? 'revision failed'
          : pendingRevision
            ? 'revision pending'
            : failedJob
              ? 'generation failed'
            : status === 'ready_for_review' && revision
              ? 'revision corrected · ready for review'
              : path ? 'ready for review' : 'not generated';
      const pill = statusPill(normalized);
      if (activeJob || pendingRevision || !isDownloadablePath(path)) return `<span class="doc-cell">${{pill}}</span>`;
      const title = cleanFilenamePart(item.title || `Lesson ${{item.lesson}}`);
      const ext = fileExtension(path) || (label.toLowerCase().includes('deck') || label.toLowerCase().includes('presentation') ? '.pptx' : '.pdf');
      const filename = `Lesson ${{String(item.lesson).padStart(2, '0')}} - ${{title}} - ${{label}}${{ext}}`;
      return `<span class="doc-cell">${{pill}} <a class="doc-link" href="/artifact?path=${{encodeURIComponent(path)}}&filename=${{encodeURIComponent(filename)}}" target="_blank" rel="noopener">open</a></span>`;
    }}
    function statusPill(value) {{
      const clean = String(value || 'missing').replace(/_/g, ' ');
      const css = String(value || 'missing').replace(/[^a-z0-9_-]+/gi, '-').toLowerCase();
      return `<span class="status-pill ${{esc(css)}}">${{esc(clean)}}</span>`;
    }}
    async function produceSelected(stage) {{
      const lessons = selectedLessons();
      if (!lessons.length) {{
        msg.textContent = 'Select at least one lesson.';
        return;
      }}
      await post('/api/produce', {{course: course.value, stage, lessons}});
    }}
    async function approveArtifact(artifactType, noteId, artifactPath, lessonOverride, noteOverride) {{
      await post('/api/approve', {{
        course: course.value,
        lesson: Number(lessonOverride || 1),
        artifact_type: artifactType,
        artifact_path: artifactPath,
        note: noteOverride ?? document.getElementById(noteId)?.value ?? ''
      }});
    }}
    async function requestEdits(artifactType, noteId, lessonOverride, noteOverride, artifactPath = '') {{
      const note = noteOverride ?? document.getElementById(noteId)?.value ?? '';
      const requests = [...document.querySelectorAll('.revision-note')].map(item => {{
        const id = item.dataset.requestId;
        return {{id, note: item.value, attachment_mode: document.querySelector(`.revision-attachment-mode[data-request-id="${{id}}"]`)?.value || 'evidence_only', source_manifest: document.querySelector(`.revision-sources[data-request-id="${{id}}"]`)?.value || ''}};
      }}).filter(item => item.note.trim());
      if (!requests.length && !note.trim()) {{
        msg.textContent = 'Write at least one requested edit before sending the artifact back.';
        return;
      }}
      const form = new FormData();
      form.append('course', course.value);
      form.append('lesson', String(Number(lessonOverride || 1)));
      form.append('artifact_type', artifactType);
      form.append('artifact_path', artifactPath);
      form.append('note', note || requests.map(item => item.note).join('\\n\\n'));
      form.append('revision_requests_json', JSON.stringify(requests));
      for (const input of document.querySelectorAll('.revision-files')) for (const file of input.files || []) form.append(`revision_files_${{input.dataset.requestId}}`, file);
      try {{
        const data = await api('/api/request-changes', {{method: 'POST', body: form}});
        msg.textContent = data.message || 'Edit request recorded and queued.';
        showOperatorResult(data.message || 'Edit request recorded and queued.', 'success');
        await loadWorkspace();
      }} catch (error) {{
        msg.textContent = error.message;
        showOperatorResult(`Could not save the edit request: ${{error.message}}`, 'error');
      }}
    }}
    async function uploadFiles() {{
      try {{
        const files = [...document.getElementById('files').files];
        if (!files.length) throw new Error('Choose one or more source files to upload.');
        setUploadQueue(files, 'uploading', 'Preparing upload', 0);
        const uploadButton = document.getElementById('upload');
        uploadButton.disabled = true;
        await ensureCourseIntake();
        const form = new FormData();
        form.append('course', course.value);
        form.append('scope', document.getElementById('uploadScope').value);
        form.append('lesson', document.getElementById('uploadLesson').value || '1');
        form.append('reference_policy', document.getElementById('referencePolicy').value);
        for (const file of files) form.append('files', file);
        const data = await new Promise((resolve, reject) => {{
          const request = new XMLHttpRequest();
          request.open('POST', '/api/upload');
          request.upload.onprogress = event => {{
            if (event.lengthComputable) updateUploadQueue('uploading', 'Uploading', event.loaded / event.total * 100);
          }};
          request.onerror = () => reject(new Error('Upload failed. Check your connection and try again.'));
          request.onload = () => {{
            let response = {{}};
            try {{ response = JSON.parse(request.responseText || '{{}}'); }} catch (_) {{}}
            if (request.status < 200 || request.status >= 300) reject(new Error(response.error || response.message || 'Upload failed'));
            else resolve(response);
          }};
          request.send(form);
        }});
        updateUploadQueue('done', 'Uploaded', 100);
        msg.textContent = data.message || 'Uploaded.';
        await loadWorkspace();
        document.getElementById('files').value = '';
        uploadQueue = [];
        renderUploadQueue();
      }} catch (error) {{
        if (uploadQueue.length) updateUploadQueue('error', error.message || 'Upload failed', 0);
        msg.textContent = error.message;
      }} finally {{
        document.getElementById('upload').disabled = false;
      }}
    }}
    async function uploadVisualBatch(lesson, requests) {{
      try {{
        const input = document.getElementById('operatorImageFiles');
        if (!input?.files?.length) throw new Error('Choose all requested images for this lesson.');
        const form = new FormData();
        form.append('course', course.value);
        form.append('scope', 'lesson');
        form.append('lesson', lesson);
        form.append('reference_policy', 'image_only');
        form.append('purpose', 'visual_response');
        form.append('visual_request_ids', JSON.stringify(requests.map(request => request.visual_id)));
        form.append('source_manifest', document.getElementById('operatorImageSources')?.value || '');
        for (const file of input.files) form.append('files', file);
        const res = await fetch('/api/upload', {{method:'POST', body:form}});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Image upload failed');
        msg.textContent = data.message || 'Technical image batch received.';
        await loadWorkspace();
      }} catch (error) {{ msg.textContent = error.message; }}
    }}
    document.querySelectorAll('[data-level]').forEach(btn => btn.onclick = () => setLevel(btn.dataset.level));
    document.getElementById('refreshTop').onclick = restoreSavedCourse;
    document.getElementById('refreshWorkspace').onclick = restoreSavedCourse;
    document.getElementById('newCourse').onclick = openNewCourse;
    document.getElementById('restartWorkspace').onclick = restartWorkspace;
    document.getElementById('coursePicker').onchange = async event => {{
      course.value = event.target.value;
      await loadWorkspace();
    }};
    document.getElementById('deleteCourse').onclick = deleteCourse;
    document.getElementById('startProduction').onclick = startProductionFlow;
    document.getElementById('uploadScope').onchange = toggleLessonInput;
    document.getElementById('files').onchange = event => setUploadQueue(event.target.files);
    document.getElementById('upload').onclick = uploadFiles;
    document.getElementById('generateMarketing').onclick = generateMarketing;
    document.getElementById('saveMarketing').onclick = saveMarketingEdits;
    document.getElementById('operatorLesson').onchange = () => {{
      renderOperatorTargetsForLesson();
      renderOperatorToolDetails();
    }};
    document.getElementById('operatorTarget').onchange = renderOperatorToolDetails;
    document.getElementById('operatorAction').onchange = () => renderOperatorToolDetails(false);
    document.getElementById('applyOperatorAction').onclick = applyOperatorAction;
    document.getElementById('produceBooks').onclick = () => produceSelected('study_guide');
    document.getElementById('produceDecks').onclick = () => produceSelected('deck');
    document.getElementById('produceTranslatedBooks').onclick = () => produceSelected('translations_book');
    document.getElementById('producePtBrBooks').onclick = () => produceSelected('pt_br_book');
    document.getElementById('producePtBrDecks').onclick = () => produceSelected('pt_br_deck');
    document.getElementById('produceEsBooks').onclick = () => produceSelected('es_book');
    document.getElementById('produceEsDecks').onclick = () => produceSelected('es_deck');
    document.getElementById('produceTranslatedDecks').onclick = () => produceSelected('translations_deck');
    document.getElementById('selectAllLessons').onchange = event => {{
      document.querySelectorAll('[data-lesson-select]').forEach(input => input.checked = event.target.checked);
    }};
    window.addEventListener('hashchange', () => showConsolePage(location.hash.slice(1)));
    showConsolePage(location.hash.slice(1) || 'dashboard');
    toggleLessonInput();
    restoreSavedCourse().finally(scheduleWorkspaceRefresh);
  </script>
</body>
</html>"""


class GregUiHandler(BaseHTTPRequestHandler):
    server_version = "ProfGregUI/0.1"

    def send_bytes(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, filename: str | None = None) -> None:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        download_name = safe_download_filename(filename or path.name, path.name)
        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: HTTPStatus, data: object) -> None:
        self.send_bytes(status, json_bytes(data), "application/json; charset=utf-8")

    def check_token(self) -> bool:
        expected = getattr(self.server, "ui_token", "")
        if not expected:
            return True
        return self.headers.get("X-ProfGreg-Token") == expected

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                body = ui_shell(getattr(self.server, "default_course", DEFAULT_COURSE)).encode("utf-8")
                self.send_bytes(HTTPStatus.OK, body, "text/html; charset=utf-8")
                return
            if parsed.path == "/api/courses":
                self.send_json(HTTPStatus.OK, {"courses": list_course_workspaces()})
                return
            if parsed.path == "/api/status":
                course = parse_qs(parsed.query).get("course", [getattr(self.server, "default_course", DEFAULT_COURSE)])[0]
                self.send_json(HTTPStatus.OK, course_status(course))
                return
            if parsed.path == "/api/jobs":
                job_root = getattr(self.server, "job_root")
                query = parse_qs(parsed.query)
                course = query.get("course", [""])[0]
                jobs = list_jobs(job_root)
                if course:
                    jobs = [job for job in jobs if str(job.get("course_slug") or "") == slugify(course)]
                worker_errors = recent_worker_errors(jobs)
                jobs = operator_visible_jobs(jobs)
                self.send_json(HTTPStatus.OK, {"jobs": jobs, "worker_errors": worker_errors, "worker_controls": worker_control_status(job_root)})
                return
            if parsed.path == "/api/uploads":
                course = parse_qs(parsed.query).get("course", [getattr(self.server, "default_course", DEFAULT_COURSE)])[0]
                self.send_json(HTTPStatus.OK, {"uploads": list_uploads(getattr(self.server, "upload_root"), course)})
                return
            if parsed.path == "/api/costs":
                course = parse_qs(parsed.query).get("course", [getattr(self.server, "default_course", DEFAULT_COURSE)])[0]
                self.send_json(HTTPStatus.OK, course_cost_report(course))
                return
            if parsed.path == "/api/marketing":
                course = parse_qs(parsed.query).get("course", [getattr(self.server, "default_course", DEFAULT_COURSE)])[0]
                self.send_json(HTTPStatus.OK, marketing_status(course))
                return
            if parsed.path == "/artifact":
                query = parse_qs(parsed.query)
                artifact = query.get("path", [""])[0]
                filename = query.get("filename", [""])[0]
                try:
                    artifact_path = safe_artifact_path(artifact)
                except LocalizedDeckIntegrityError:
                    self.send_bytes(
                        HTTPStatus.CONFLICT,
                        blocked_localized_deck_page(),
                        "text/html; charset=utf-8",
                    )
                    return
                self.send_file(artifact_path, filename=filename)
                return
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)[:500]})

    def do_POST(self) -> None:
        if not self.check_token():
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/worker-control":
                body = read_request_body(self)
                lane = str(body.get("lane") or "")
                action = str(body.get("action") or "")
                if lane not in {"content", "delivery", "video"}:
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Choose a valid worker."})
                    return
                job_root = getattr(self.server, "job_root")
                if action == "stop":
                    result = pause_worker_lane(job_root, lane)
                    count = int(result["cancelled_count"])
                    noun = "job" if count == 1 else "jobs"
                    self.send_json(HTTPStatus.OK, {**result, "message": f"{lane.title()} worker stopped; {count} active {noun} cancelled and the queue cleared."})
                    return
                if action == "resume":
                    result = resume_worker_lane(job_root, lane)
                    self.send_json(HTTPStatus.OK, {**result, "message": f"{lane.title()} worker resumed and is ready for new work."})
                    return
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Choose stop or resume."})
                return
            if parsed.path == "/api/delete-course":
                body = read_request_body(self)
                result = delete_course_workspace(
                    course_slug=str(body.get("course") or ""),
                    job_root=getattr(self.server, "job_root"),
                    upload_root=getattr(self.server, "upload_root"),
                )
                self.send_json(
                    HTTPStatus.OK,
                    {"message": f"Deleted course {result['course_slug']} and {result['deleted_jobs']} saved job record(s).", **result},
                )
                return
            if parsed.path == "/api/complete-course":
                body = read_request_body(self)
                course = slugify(str(body.get("course") or ""))
                if not course or workspace_intake_path(SESSION_RUN_ROOT / course) is None:
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Choose an existing course workspace."})
                    return
                active = [job for job in list_jobs(getattr(self.server, "job_root")) if str(job.get("course_slug") or "") == course and job.get("state") in {"queued", "running"}]
                if active:
                    self.send_json(HTTPStatus.CONFLICT, {"error": "This course still has active work. Wait for it to finish before marking it complete."})
                    return
                write_course_session(course, "completed")
                self.send_json(HTTPStatus.OK, {"message": "Course marked complete. It remains stored and can be recovered from the server backup."})
                return
            if parsed.path == "/api/upload":
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                if content_length > MAX_UPLOAD_REQUEST_BYTES:
                    max_mb = MAX_UPLOAD_REQUEST_BYTES // (1024 * 1024)
                    self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": f"Upload batch is too large. Maximum per batch is {max_mb} MB."})
                    return
                raw = self.rfile.read(content_length)
                fields, file_fields = parse_multipart_form(self.headers.get("Content-Type", ""), raw)
                course = str(fields.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE))
                scope = str(fields.get("scope") or "course")
                lesson = int(fields.get("lesson") or 1)
                reference_policy = str(fields.get("reference_policy") or "context_only")
                purpose = str(fields.get("purpose") or "source_material")
                visual_request_id = str(fields.get("visual_request_id") or "")
                visual_request_ids = json.loads(fields.get("visual_request_ids") or "[]")
                if not isinstance(visual_request_ids, list):
                    raise ValueError("visual_request_ids must be a list.")
                source_manifest = parse_visual_source_manifest(str(fields.get("source_manifest") or ""))
                source_label = str(fields.get("source_label") or "")
                source_url = str(fields.get("source_url") or "")
                saved = []
                if purpose == "visual_response" and visual_request_ids:
                    fields_to_save = map_visual_batch(file_fields, [str(item) for item in visual_request_ids])
                else:
                    fields_to_save = [(field, visual_request_id) for field in file_fields]
                for field, mapped_request_id in fields_to_save:
                    filename = str(field.get("filename") or "")
                    data = bytes(field.get("data") or b"")
                    if not filename:
                        continue
                    source_meta = source_manifest.get(safe_filename(filename).casefold(), {})
                    saved.append(
                        save_uploaded_file(
                            upload_root=getattr(self.server, "upload_root"),
                            course_slug=course,
                            filename=filename,
                            data=data,
                            scope=scope,
                            lesson=lesson,
                            reference_policy=reference_policy,
                            purpose=purpose,
                            visual_request_id=mapped_request_id,
                            source_label=str(source_meta.get("source_label") or source_label or "Operator supplied technical image"),
                            source_url=str(source_meta.get("source_url") or source_url),
                        )
                    )
                job = None
                if purpose == "visual_response" and visual_request_ids:
                    available = {
                        item.get("visual_request_id")
                        for item in list_uploads(getattr(self.server, "upload_root"), course)
                        if item.get("purpose") == "visual_response"
                    }
                    if set(str(item) for item in visual_request_ids).issubset(available):
                        queued = enqueue_job(
                            job_root=getattr(self.server, "job_root"),
                            request_type="production_stage",
                            course_slug=course,
                            lesson=lesson,
                            summary=f"technical image batch received for Lesson {lesson}",
                            payload={"stage": "study_guide", "lessons": [lesson]},
                        )
                        job = queued.job
                message = f"Uploaded {len(saved)} file(s)."
                if job:
                    message += " Course book production resumed automatically."
                self.send_json(HTTPStatus.OK, {"message": message, "uploads": saved, "job": job})
                return
            if parsed.path == "/api/request-changes" and "multipart/form-data" in (self.headers.get("Content-Type", "")).lower():
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                if content_length > MAX_UPLOAD_REQUEST_BYTES:
                    self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": f"Revision attachments are too large. Maximum per request is {MAX_UPLOAD_REQUEST_BYTES // (1024 * 1024)} MB."})
                    return
                fields, revision_files = parse_multipart_form(self.headers.get("Content-Type", ""), self.rfile.read(content_length))
                body = fields
            else:
                body = read_request_body(self)
                revision_files = []
            job_root = getattr(self.server, "job_root")
            if parsed.path == "/api/backup":
                result = enqueue_job(job_root=job_root, request_type="backup", summary=str(body.get("summary") or "ui backup request"))
                self.send_json(HTTPStatus.OK, {"message": result.message, "job": result.job})
                return
            if parsed.path == "/api/upload-update":
                updated = update_upload_metadata(
                    upload_root=getattr(self.server, "upload_root"),
                    course_slug=str(body.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE)),
                    upload_id=str(body.get("upload_id") or ""),
                    scope=str(body.get("scope") or "course"),
                    lesson=int(body.get("lesson") or 1),
                    reference_policy=str(body.get("reference_policy") or "context_only"),
                )
                self.send_json(HTTPStatus.OK, {"message": "Upload updated.", "upload": updated})
                return
            if parsed.path == "/api/upload-delete":
                deleted = delete_uploaded_file(
                    upload_root=getattr(self.server, "upload_root"),
                    course_slug=str(body.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE)),
                    upload_id=str(body.get("upload_id") or ""),
                )
                self.send_json(HTTPStatus.OK, {"message": "Upload deleted.", "upload": deleted})
                return
            if parsed.path == "/api/lesson-lifecycle":
                result = enqueue_job(
                    job_root=job_root,
                    request_type="lesson_lifecycle",
                    course_slug=str(body.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE)),
                    lesson=int(body.get("lesson") or 1),
                    summary="ui lesson lifecycle request",
                )
                self.send_json(HTTPStatus.OK, {"message": result.message, "job": result.job})
                return
            if parsed.path == "/api/start-course":
                result = enqueue_job(
                    job_root=job_root,
                    request_type="course_start",
                    course_slug=str(body.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE)),
                    summary="operator started Course Map and source research",
                )
                self.send_json(HTTPStatus.OK, {"message": result.message, "job": result.job})
                return
            if parsed.path == "/api/marketing-generate":
                course = slugify(str(body.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE)))
                status = course_status(course)
                if status.get("course_map_ready") is not True:
                    self.send_json(HTTPStatus.CONFLICT, {"error": "Generate and approve the Course Map before creating marketing content."})
                    return
                active = next((job for job in list_jobs(job_root) if str(job.get("course_slug") or "") == course and job.get("state") in {"queued", "running"} and str((job.get("payload") or {}).get("stage") or "") == "marketing"), None)
                if active:
                    self.send_json(HTTPStatus.OK, {"message": "Marketing production is already in progress.", "job": active})
                    return
                result = enqueue_job(
                    job_root=job_root,
                    request_type="production_stage",
                    course_slug=course,
                    summary="operator requested website marketing copy and a five-page brochure",
                    payload={"stage": "marketing", "lessons": []},
                )
                self.send_json(HTTPStatus.OK, {"message": "Marketing research and brochure production queued.", "job": result.job})
                return
            if parsed.path == "/api/marketing-save":
                course = slugify(str(body.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE)))
                marketing = body.get("marketing")
                if not isinstance(marketing, dict):
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Marketing fields are required."})
                    return
                saved = save_marketing(course, marketing, render=True)
                self.send_json(HTTPStatus.OK, {**marketing_status(course), "marketing": saved, "message": "Marketing content saved and the five-page brochure updated."})
                return
            if parsed.path == "/api/produce":
                course = str(body.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE))
                stage = str(body.get("stage") or "")
                lessons = [int(value) for value in (body.get("lessons") or [])]
                if stage not in {"study_guide", "deck", "translations_book", "translations_deck", "pt_br_book", "pt_br_deck", "es_book", "es_deck"} or not lessons:
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Choose at least one lesson and a supported production type."})
                    return
                artifact_by_stage = {
                    "study_guide": "study_guide", "deck": "deck",
                    "pt_br_book": "pt_br_study_guide", "pt_br_deck": "pt_br_deck",
                    "es_book": "es_study_guide", "es_deck": "es_deck",
                }
                artifact_type = artifact_by_stage.get(stage)
                if artifact_type:
                    run = ROOT / "runs" / slugify(course)
                    for lesson in lessons:
                        state_path = run / "operator_feedback" / f"lesson_{lesson:02d}_{artifact_type}_revision_state.json"
                        if read_state(state_path).get("state") == "revision_requested":
                            append_interaction(
                                state_path,
                                "retry_requested",
                                message="Operator requested another production attempt for the pending revision.",
                            )
                jobs = enqueue_production_lesson_jobs(
                    job_root=job_root,
                    course=course,
                    stage=stage,
                    lessons=lessons,
                )
                noun = "job" if len(jobs) == 1 else "jobs"
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "message": f"{len(jobs)} production {noun} queued. Each lesson will remain in the queue until it is processed.",
                        "job": jobs[0] if jobs else None,
                        "jobs": jobs,
                    },
                )
                return
            if parsed.path == "/api/video-generate":
                course = str(body.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE))
                lesson = int(body.get("lesson") or 0)
                locale = str(body.get("locale") or "")
                status = course_status(course)
                lesson_row = next((row for row in status.get("lessons") or [] if int(row.get("lesson") or 0) == lesson), None)
                video = ((lesson_row or {}).get("videos") or {}).get(locale) if locale in {"en", "pt", "es"} else None
                if not video or str(video.get("status") or "") in {"waiting_approved_presentation", "presentation_too_large", "video_ready"}:
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "This presentation is not ready for video generation."})
                    return
                payload = {
                    "locale": locale,
                    "sourcePath": str(video.get("presentation_path") or ""),
                    "sourceSha256": str(video.get("source_sha256") or ""),
                    "title": str((lesson_row or {}).get("title") or f"Lesson {lesson:02d}"),
                    "recoveryCount": 0,
                }
                if not payload["sourcePath"] or not payload["sourceSha256"]:
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "The approved presentation source is unavailable."})
                    return
                active = next((job for job in list_jobs(job_root) if job.get("request_type") == "video_generation" and job.get("state") in {"queued", "running"} and str(job.get("course_slug") or "") == slugify(course) and int(job.get("lesson") or 0) == lesson and str((job.get("payload") or {}).get("locale") or "") == locale and str((job.get("payload") or {}).get("sourceSha256") or "") == payload["sourceSha256"]), None)
                if active:
                    self.send_json(HTTPStatus.OK, {"message": f"Video job already active: {active['job_id']}", "job": active})
                    return
                result = enqueue_job(job_root=job_root, request_type="video_generation", course_slug=course, lesson=lesson, requested_by="operator-ui", summary=f"operator started {locale} video generation", payload=payload)
                self.send_json(HTTPStatus.OK, {"message": result.message, "job": result.job})
                return
            if parsed.path == "/api/stage-next":
                result = enqueue_job(
                    job_root=job_root,
                    request_type="stage_next",
                    course_slug=str(body.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE)),
                    lesson=int(body.get("lesson") or 1),
                    summary="ui next stage request",
                )
                self.send_json(HTTPStatus.OK, {"message": result.message, "job": result.job})
                return
            if parsed.path == "/api/approve":
                course = str(body.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE))
                lesson = int(body.get("lesson") or 1)
                artifact_type = str(body.get("artifact_type") or "")
                artifact_path = str(body.get("artifact_path") or "").strip()
                note = str(body.get("note") or "")
                if artifact_path:
                    data = record_ui_artifact_approval(
                        course_slug=course,
                        lesson=lesson,
                        artifact_type=artifact_type,
                        artifact=artifact_path,
                        note=note,
                    )
                else:
                    data = record_ui_approval(
                        course_slug=course,
                        lesson=lesson,
                        artifact_type=artifact_type,
                        note=note,
                    )
                job = None
                if artifact_type == "study_guide":
                    queued = enqueue_job(
                        job_root=job_root,
                        request_type="production_stage",
                        course_slug=course,
                        lesson=lesson,
                        summary=f"study guide approved; produce presentation for Lesson {lesson}",
                        payload={"stage": "deck", "lessons": [lesson]},
                    )
                    job = queued.job
                self.send_json(HTTPStatus.OK, {"message": "Approval recorded." if not job else "Course book approved; presentation production queued.", "approval": data, "job": job})
                return
            if parsed.path == "/api/request-changes":
                course = str(body.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE))
                lesson = int(body.get("lesson") or 1)
                artifact_type = str(body.get("artifact_type") or "artifact")
                note = str(body.get("note") or "")
                if not note.strip():
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Describe the requested edits before sending the artifact back."})
                    return
                stage_by_artifact = {
                    "study_guide": "study_guide",
                    "deck": "deck",
                    "pt_br_study_guide": "pt_br_book",
                    "pt_br_deck": "pt_br_deck",
                    "es_study_guide": "es_book",
                    "es_deck": "es_deck",
                }
                stage = stage_by_artifact.get(artifact_type)
                if not stage:
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Unsupported artifact type for revision."})
                    return
                try:
                    requested_changes = json.loads(str(body.get("revision_requests_json") or "[]"))
                except json.JSONDecodeError:
                    requested_changes = []
                if not isinstance(requested_changes, list):
                    requested_changes = []
                if not requested_changes:
                    requested_changes = [{"id": "0", "note": note, "attachment_mode": str(body.get("revision_attachment_mode") or "evidence_only"), "source_manifest": str(body.get("source_manifest") or "")}]
                requests_by_id = {str(item.get("id") or index): item for index, item in enumerate(requested_changes)}
                request_attachments: dict[str, list[dict]] = {request_id: [] for request_id in requests_by_id}
                attachments = []
                for field in revision_files:
                    filename = str(field.get("filename") or "")
                    data = bytes(field.get("data") or b"")
                    if not filename:
                        continue
                    clean_name = safe_filename(filename)
                    request_id = str(field.get("name") or "revision_files_0").removeprefix("revision_files_")
                    request_meta = requests_by_id.get(request_id, requests_by_id.get("0", {}))
                    source_manifest = parse_visual_source_manifest(str(request_meta.get("source_manifest") or ""))
                    source_meta = source_manifest.get(clean_name.casefold(), {})
                    is_image = Path(clean_name).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                    attachment_purpose = "revision_material" if str(request_meta.get("attachment_mode") or "evidence_only") == "use_in_revision" else "revision_evidence"
                    attachment = save_uploaded_file(
                        upload_root=getattr(self.server, "upload_root"), course_slug=course, filename=filename, data=data,
                        scope="lesson", lesson=lesson,
                        reference_policy="image_only" if is_image and attachment_purpose == "revision_material" else "context_only",
                        purpose=attachment_purpose, revision_artifact_type=artifact_type,
                        source_label=str(source_meta.get("source_label") or "Operator-supplied revision material"),
                        source_url=str(source_meta.get("source_url") or ""),
                    )
                    attachments.append(attachment)
                    request_attachments.setdefault(request_id, []).append(attachment)
                normalized_requests = [
                    {"id": str(item.get("id") or index), "note": str(item.get("note") or ""), "attachments": request_attachments.get(str(item.get("id") or index), [])}
                    for index, item in enumerate(requested_changes)
                    if str(item.get("note") or "").strip()
                ]
                feedback = record_revision_request(
                    course_slug=course,
                    lesson=lesson,
                    artifact_type=artifact_type,
                    note=note,
                    artifact_path=str(body.get("artifact_path") or ""),
                    attachments=attachments,
                    requests=normalized_requests,
                )
                result = enqueue_job(
                    job_root=job_root,
                    request_type="production_stage",
                    course_slug=course,
                    lesson=lesson,
                    summary=f"ui revision request for {artifact_type} ({len(normalized_requests)} requested change(s)){' with supporting files' if attachments else ''}: {note[:180]}",
                    payload={"stage": stage, "lessons": [lesson]},
                )
                self.send_json(HTTPStatus.OK, {"message": f"{len(normalized_requests)} requested change(s) recorded and queued together.", "feedback": feedback, "job": result.job})
                return
            if parsed.path == "/api/request":
                request_text = str(body.get("request") or "").strip()
                if not request_text:
                    self.send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": "Type a specific command, or use Start / Continue Production for the normal course flow."},
                    )
                    return
                result = handle_request(
                    request_text,
                    course_slug=str(body.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE)),
                    lesson=int(body.get("lesson") or 1),
                    job_root=job_root,
                    enqueue=bool(body.get("enqueue")),
                )
                status = HTTPStatus.OK if result.allowed else HTTPStatus.CONFLICT
                self.send_json(status, {"message": result.message, "job": result.job, "route": result.route, "status": result.status})
                return
            if parsed.path == "/api/create-course":
                result = create_course_intake(
                    title=str(body.get("title") or ""),
                    level=str(body.get("level") or "Basic"),
                    syllabus=str(body.get("syllabus") or ""),
                    course_slug=str(body.get("slug") or "") or None,
                    expected_lessons=int(body.get("expected_lessons") or 0) or None,
                )
                self.send_json(HTTPStatus.OK, result)
                return
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)[:500]})

    def log_message(self, format: str, *args: object) -> None:
        return


def build_server(host: str, port: int, *, job_root: Path, upload_root: Path, default_course: str, ui_token: str = "") -> ThreadingHTTPServer:
    resolved_job_root = safe_job_root(job_root)
    resolved_upload_root = safe_upload_root(upload_root)
    server = ThreadingHTTPServer((host, port), GregUiHandler)
    server.job_root = resolved_job_root  # type: ignore[attr-defined]
    server.upload_root = resolved_upload_root  # type: ignore[attr-defined]
    server.default_course = default_course  # type: ignore[attr-defined]
    server.ui_token = ui_token  # type: ignore[attr-defined]
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the private Prof Greg operator UI.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--job-root", default=str(default_job_root()))
    parser.add_argument("--upload-root", default=str(SERVER_UPLOAD_ROOT if SERVER_UPLOAD_ROOT.exists() else LOCAL_UPLOAD_ROOT))
    parser.add_argument("--course", default=DEFAULT_COURSE)
    parser.add_argument("--token-env", default="PROFGREG_UI_TOKEN")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Refusing to bind UI outside localhost in the private v0 interface.")
    server = build_server(
        args.host,
        args.port,
        job_root=Path(args.job_root),
        upload_root=Path(args.upload_root),
        default_course=args.course,
        ui_token=os.environ.get(args.token_env, ""),
    )
    print(f"Prof Greg UI listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
