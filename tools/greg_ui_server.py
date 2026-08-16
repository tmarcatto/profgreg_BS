#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import mimetypes
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from greg_operator import course_status, default_job_root, enqueue_job, handle_request
from greg_record_approval import record_approval
from greg_server_status import list_jobs, safe_job_root
from greg_create_run import create_run, slugify


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_COURSE = "construction-schedule-management"
ROOT = Path(__file__).resolve().parents[1]
SERVER_UPLOAD_ROOT = Path("/srv/profgreg/uploads")
LOCAL_UPLOAD_ROOT = ROOT / "tmp" / "uploads"
MAX_UPLOAD_FILE_BYTES = 200 * 1024 * 1024
MAX_UPLOAD_REQUEST_BYTES = 500 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
REFERENCE_POLICIES = {
    "context_only": "Use as production context only; do not cite in student references and do not reuse images.",
    "image_only": "Do not cite text in student references; images may be reused when properly referenced.",
    "reference_only": "May appear in student references; do not reuse images.",
    "reference_and_images": "May appear in student references and images may be reused when properly referenced.",
}
DEFAULT_LESSON_COUNT_BY_LEVEL = {"Basic": 10, "Intermediate": 15, "Advanced": 15}


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


def safe_filename(value: str) -> str:
    name = Path(value or "uploaded-file").name
    clean = re.sub(r"[^a-zA-Z0-9._ -]+", "-", name).strip(" .-_")
    if not clean:
        clean = "uploaded-file"
    suffix = Path(clean).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError(f"Unsupported upload type: {suffix or '[none]'}")
    return clean[:120]


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
    return resolved


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
    return meta


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
) -> dict:
    if len(data) > MAX_UPLOAD_FILE_BYTES:
        raise ValueError(f"Upload is too large. Maximum per file is {MAX_UPLOAD_FILE_BYTES // (1024 * 1024)} MB.")
    clean_name = safe_filename(filename)
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
    return {**setup.__dict__, "message": f"Course intake created: {setup.course_slug}"}


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


def record_revision_request(*, course_slug: str, lesson: int, artifact_type: str, note: str) -> dict:
    course_slug = slugify(course_slug)
    lesson_tag = f"lesson_{lesson:02d}"
    target = ROOT / "runs" / course_slug / "operator_feedback" / f"{lesson_tag}_{artifact_type}_revision_request.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                f"# {lesson_tag} {artifact_type} Revision Request",
                "",
                f"- Course slug: {course_slug}",
                f"- Lesson: {lesson:02d}",
                f"- Artifact type: {artifact_type}",
                "",
                "Requested changes:",
                note.strip() or "- Revision requested from Prof Greg Operator.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"feedback_path": str(target.relative_to(ROOT))}


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
    main {{ padding: 24px 28px 44px; display: grid; gap: 18px; max-width: 1360px; margin: 0 auto; }}
    input, textarea, button, select {{
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
    }}
    input, textarea, select {{ padding: 10px 12px; color: var(--ink); background: #fff; }}
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
    .slugbar {{
      display: grid;
      grid-template-columns: minmax(240px, 1fr) auto auto;
      gap: 10px;
      align-items: center;
    }}
    .brief-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      align-items: start;
    }}
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
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; margin-top: 16px; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 760px; }}
    th, td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 12px 10px; vertical-align: top; font-size: 14px; }}
    tr:last-child td {{ border-bottom: 0; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; background: #f7f9fc; }}
    .pipeline-strip {{
      display: grid;
      grid-template-columns: repeat(9, minmax(116px, 1fr));
      gap: 10px;
      overflow-x: auto;
      padding-bottom: 4px;
    }}
    .stage-card {{
      min-height: 96px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
      cursor: pointer;
    }}
    .stage-card.active {{ border-color: var(--orange); background: var(--orange-soft); box-shadow: inset 3px 0 0 var(--orange); }}
    .stage-card.selected {{ outline: 2px solid var(--orange); outline-offset: 2px; }}
    .stage-card.done {{ border-color: #b8dec8; background: #f4fbf6; }}
    .stage-card.blocked {{ border-color: #f4b0aa; background: #fff7f6; }}
    .stage-kicker {{ display: flex; align-items: center; gap: 7px; color: var(--muted); font-size: 12px; font-weight: 760; }}
    .dot {{ width: 8px; height: 8px; border-radius: 50%; background: #b7c2cf; }}
    .done .dot {{ background: var(--ok); }}
    .active .dot {{ background: var(--orange); }}
    .blocked .dot {{ background: var(--bad); }}
    .stage-title {{ margin-top: 8px; color: var(--navy); font-weight: 800; line-height: 1.2; }}
    .stage-status {{ margin-top: 5px; color: var(--muted); font-size: 12px; }}
    .gate-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .gate-box {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #fff; min-height: 172px; }}
    .gate-box h3 {{ margin: 0 0 8px; font-size: 15px; color: var(--navy); }}
    .approval-list {{ display: grid; gap: 12px; }}
    .approval-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: #fff;
      display: grid;
      grid-template-columns: minmax(220px, 1fr) minmax(260px, 1.2fr) auto;
      gap: 14px;
      align-items: start;
    }}
    .approval-card.ready {{ border-color: var(--orange); box-shadow: inset 3px 0 0 var(--orange); }}
    .approval-card.approved {{ border-color: #b8dec8; background: #f4fbf6; }}
    .approval-title {{ color: var(--navy); font-weight: 820; }}
    .approval-meta {{ margin-top: 5px; color: var(--muted); font-size: 13px; line-height: 1.35; }}
    .approval-actions {{ display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }}
    .approval-note {{ min-height: 74px; }}
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
    .checklist {{ display: grid; gap: 8px; margin-top: 10px; }}
    .check {{ display: flex; gap: 8px; align-items: flex-start; color: #344054; font-size: 13px; }}
    .check span:first-child {{ width: 18px; height: 18px; border-radius: 50%; background: #e8f0f8; display: grid; place-items: center; color: var(--navy); font-size: 11px; flex: 0 0 auto; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; align-items: center; }}
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
    .hidden {{ display: none !important; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }}
    @media (max-width: 980px) {{
      .topbar, .slugbar, .brief-grid, .field-grid, .gate-grid, .status-summary, .upload-controls, .log-tools, .approval-card {{ grid-template-columns: 1fr; }}
      .approval-actions {{ justify-content: flex-start; }}
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
        <button class="primary" id="startTop">Start production</button>
      </div>
    </div>
    <nav class="nav" aria-label="Console sections">
      <a href="#brief">Brief</a>
      <a href="#materials">Materials</a>
      <a href="#pipeline">Status</a>
      <a href="#approvals">Approvals</a>
      <a href="#activity">Activity log</a>
    </nav>
  </header>
  <main>
    <div class="slugbar">
      <input id="course" value="{course}" aria-label="Course slug">
      <input id="targetLesson" type="number" min="1" value="1" aria-label="Target lesson" title="Lesson number">
      <button class="primary" id="startProduction">Start production</button>
    </div>

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
          <span class="muted">PDF, DOCX, TXT, or Markdown. Multiple files are supported.</span>
          <input id="files" type="file" multiple accept=".pdf,.docx,.txt,.md">
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
        <div class="table-wrap">
          <table>
            <thead><tr><th>File</th><th>Scope</th><th>Reference policy</th><th>Size</th><th>Actions</th></tr></thead>
            <tbody id="uploads"><tr><td colspan="5" class="muted">No uploads loaded.</td></tr></tbody>
          </table>
        </div>
      </div>
    </section>

    <section id="pipeline" class="card">
      <div class="section-head">
        <div class="title-row">
          <div class="step-num">3</div>
          <div><h2>Production Status</h2><div class="hint">The system advances through the pipeline after the main start button and each approval decision.</div></div>
        </div>
        <div class="muted" id="approvalCount">0 approvals</div>
      </div>
      <div class="body">
        <div class="status-summary">
          <div class="metric"><div class="label">Current stage</div><div class="value" id="stage">Loading</div></div>
          <div class="metric"><div class="label">Gate</div><div class="value" id="gate">Loading</div></div>
          <div class="metric"><div class="label">Next action</div><div class="value" id="next">Loading</div></div>
        </div>
        <div class="notice" id="message">Ready.</div>
        <div class="pipeline-strip" id="pipelineStrip"></div>
      </div>
    </section>

    <section id="approvals" class="card">
      <div class="section-head">
        <div class="title-row">
          <div class="step-num">4</div>
          <div><h2>Approval Queue</h2><div class="hint">Only the relevant approval sections appear here. Use approve to continue, or request edits to send feedback back into the production flow.</div></div>
        </div>
      </div>
      <div class="body">
        <div class="approval-list" id="approvalPanels"></div>
      </div>
    </section>

    <section id="activity" class="card">
      <div class="section-head">
        <div class="title-row">
          <div class="step-num">5</div>
          <div><h2>Activity Log</h2><div class="hint">Jobs and operator events, newest first.</div></div>
        </div>
      </div>
      <div class="body">
        <div class="log-tools">
          <input id="logSearch" placeholder="Search jobs and messages">
          <select id="stageFilter"><option value="">All stages</option></select>
          <select id="actorFilter"><option value="">All states</option><option>queued</option><option>running</option><option>completed</option><option>failed</option><option>cancelled</option></select>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Job</th><th>State</th><th>Type</th><th>Message</th></tr></thead>
            <tbody id="jobs"><tr><td colspan="4" class="muted">Loading</td></tr></tbody>
          </table>
        </div>
      </div>
    </section>
  </main>
  <script>
    const course = document.getElementById('course');
    const msg = document.getElementById('message');
    const expectedLessonsByLevel = {{ Basic: 10, Intermediate: 15, Advanced: 15 }};
    let currentStatus = null;
    let currentJobs = [];
    let selectedStageKey = 'INTAKE';
    let userSelectedStage = false;
    const stages = [
      ['INTAKE', 'Input', ['intake']],
      ['COURSE_MAP', 'Course Map', ['course_map', 'course_map_md']],
      ['SOURCE_LEDGER', 'Sources', ['source_ledger']],
      ['DOCX_PDF', 'Course Book', ['study_guide_pdf', 'lesson_01_study_guide_pdf']],
      ['HUMAN_APPROVAL', 'Book Approval', ['study_guide_approval', 'lesson_01_study_guide_approval']],
      ['DECK', 'Presentation', ['deck', 'deck_pptx', 'lesson_01_deck_pptx']],
      ['DECK_APPROVAL', 'Deck Approval', ['deck_approval', 'lesson_01_deck_approval']],
      ['LOCALIZATION', 'Localization', ['localization_pt_br', 'localization_es_419']],
      ['FINAL_REVIEW', 'Final Review', ['process_review', 'lesson_01_pipeline_qa']]
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
        artifactNames: lesson => [`lesson_${{lesson}}_deck_pptx`, 'deck_pptx', 'deck'],
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
      if (key === 'PROCESS_REVIEW' || key === 'FULL_FLOW_CONFIRMATION_COMPLETE') return 'FINAL_REVIEW';
      return key || 'INTAKE';
    }}
    function stageIndex(key) {{
      const index = stages.findIndex(stage => stage[0] === normalizedStage(key));
      return index >= 0 ? index : stages.length - 1;
    }}
    function artifactExists(names) {{
      const artifacts = currentStatus?.artifacts || [];
      return artifacts.some(item => names.includes(item.name) && item.exists);
    }}
    function artifactByNames(names) {{
      const artifacts = currentStatus?.artifacts || [];
      return artifacts.find(item => names.includes(item.name) && item.exists) || null;
    }}
    function selectedLessonTag() {{
      const value = Number(document.getElementById('targetLesson').value || 1);
      return String(Math.max(1, value)).padStart(2, '0');
    }}
    function lessonStatus(field) {{
      const tag = selectedLessonTag();
      const lesson = (currentStatus?.lessons || []).find(item => String(item.lesson).padStart(2, '0') === tag);
      return lesson ? lesson[field] : '';
    }}
    function stageState(key, names) {{
      if (artifactExists(names)) return 'done';
      const currentStage = normalizedStage(currentStatus?.stage);
      if (key === currentStage) return 'active';
      const current = stageIndex(currentStatus?.stage || 'INTAKE');
      const mine = stageIndex(key);
      if (mine < current) return 'done';
      return 'pending';
    }}
    function renderPipeline() {{
      const strip = document.getElementById('pipelineStrip');
      strip.innerHTML = stages.map(([key, title, names], index) => {{
        const state = stageState(key, names);
        const label = state === 'done' ? 'approved / present' : state === 'active' ? 'active' : 'pending';
        return `<div class="stage-card ${{state}} ${{selectedStageKey === key ? 'selected' : ''}}" onclick="selectStage('${{key}}')">
          <div class="stage-kicker"><span class="dot"></span> Stage ${{index + 1}}</div>
          <div class="stage-title">${{esc(title)}}</div>
          <div class="stage-status">${{esc(label)}}</div>
        </div>`;
      }}).join('');
      const approved = approvalGroups.filter(group => lessonStatus(group.approvalField) === 'approved').length;
      document.getElementById('approvalCount').textContent = `${{approved}} approvals`;
      renderApprovals();
    }}
    function selectStage(key) {{
      selectedStageKey = key;
      userSelectedStage = true;
      renderPipeline();
    }}
    function renderApprovals() {{
      const tag = selectedLessonTag();
      const rows = approvalGroups.map(group => {{
        const artifact = artifactByNames(group.artifactNames(tag));
        const status = lessonStatus(group.approvalField);
        if (!artifact && status !== 'approved') return '';
        const approved = status === 'approved';
        const css = approved ? 'approved' : 'ready';
        const noteId = `note-${{group.key}}`;
        const artifactPath = artifact?.path || '';
        return `<div class="approval-card ${{css}}">
          <div>
            <div class="approval-title">${{esc(group.title)}}</div>
            <div class="approval-meta">${{esc(group.description)}}<br>Status: <strong>${{approved ? 'approved' : 'waiting for review'}}</strong></div>
          </div>
          <div>
            <textarea class="approval-note" id="${{noteId}}" placeholder="Write edit requests or approval notes here."></textarea>
            <div class="approval-meta">${{artifactPath ? esc(artifactPath) : 'Approval already recorded.'}}</div>
          </div>
          <div class="approval-actions">
            ${{artifactPath ? `<a class="download-link" href="/artifact?path=${{encodeURIComponent(artifactPath)}}" target="_blank" rel="noopener">Download</a>` : ''}}
            <button class="danger" onclick="requestEdits('${{group.artifactType}}', '${{noteId}}')">Request edits</button>
            <button class="primary" onclick="approveArtifact('${{group.artifactType}}', '${{noteId}}', '${{esc(artifactPath)}}')" ${{approved ? 'disabled' : ''}}>Approve</button>
          </div>
        </div>`;
      }}).filter(Boolean).join('');
      document.getElementById('approvalPanels').innerHTML = rows || '<div class="notice">No artifact is waiting for approval yet. After production creates a course book, presentation, or translation, the right approval section will appear here.</div>';
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
      return `<tr>
        <td><strong>${{esc(u.filename)}}</strong></td>
        <td><div class="upload-edit">
          <select class="mini" id="scope-${{id}}" onchange="toggleUploadLesson('${{id}}')">
            <option value="course" ${{selected(scope, 'course')}}>Course</option>
            <option value="lesson" ${{selected(scope, 'lesson')}}>Lesson</option>
          </select>
          <input class="mini" id="lesson-${{id}}" type="number" min="1" value="${{lesson}}">
        </div></td>
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
        await refresh();
        return data;
      }} catch (error) {{
        msg.textContent = error.message;
        throw error;
      }}
    }}
    async function refresh() {{
      try {{
        currentStatus = await api('/api/status?course=' + encodeURIComponent(course.value));
        document.getElementById('stage').textContent = currentStatus.stage || 'Unknown';
        document.getElementById('gate').textContent = currentStatus.gate_status || 'Unknown';
        document.getElementById('next').textContent = currentStatus.next_recommended_action || 'Review status.';
        if (!userSelectedStage) selectedStageKey = normalizedStage(currentStatus.stage || selectedStageKey);
        const jobs = await api('/api/jobs');
        currentJobs = jobs.jobs || [];
        renderJobs();
        const uploads = await api('/api/uploads?course=' + encodeURIComponent(course.value));
        document.getElementById('uploads').innerHTML = uploads.uploads.length ? uploads.uploads.map(uploadRow).join('') : '<tr><td colspan="5" class="muted">No source materials attached yet.</td></tr>';
        for (const item of uploads.uploads) toggleUploadLesson(item.upload_id);
        renderPipeline();
      }} catch (error) {{
        msg.textContent = error.message;
      }}
    }}
    function renderJobs() {{
      const state = document.getElementById('actorFilter').value;
      const query = document.getElementById('logSearch').value.toLowerCase();
      const filtered = currentJobs.filter(j => (!state || j.state === state) && (!query || JSON.stringify(j).toLowerCase().includes(query)));
      document.getElementById('jobs').innerHTML = filtered.length ? filtered.slice().reverse().map(j => `<tr><td><code>${{esc(j.job_id)}}</code></td><td class="state ${{esc(j.state)}}">${{esc(j.state)}}</td><td>${{esc(j.request_type)}}</td><td>${{esc(j.last_error || j.input_summary || '')}}</td></tr>`).join('') : '<tr><td colspan="4" class="muted">No activity recorded.</td></tr>';
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
    async function startProductionFlow() {{
      const title = document.getElementById('courseTitle').value.trim();
      const syllabus = document.getElementById('syllabus').value.trim();
      if (title && syllabus) {{
        const level = document.querySelector('[data-level].active')?.dataset.level || 'Basic';
        const created = await post('/api/create-course', {{
          title,
          level,
          expected_lessons: Number(document.getElementById('expectedLessons').value || 0),
          slug: document.getElementById('courseSlug').value,
          syllabus
        }});
        const manualSlug = document.getElementById('courseSlug').value;
        course.value = created.course_slug || manualSlug || course.value;
      }}
      return post('/api/stage-next', {{course: course.value, lesson: Number(document.getElementById('targetLesson').value || 1)}});
    }}
    async function approveArtifact(artifactType, noteId, artifactPath) {{
      await post('/api/approve', {{
        course: course.value,
        lesson: Number(document.getElementById('targetLesson').value || 1),
        artifact_type: artifactType,
        artifact_path: artifactPath,
        note: document.getElementById(noteId)?.value || ''
      }});
    }}
    async function requestEdits(artifactType, noteId) {{
      const note = document.getElementById(noteId)?.value || '';
      if (!note.trim()) {{
        msg.textContent = 'Write the requested edits before sending the artifact back.';
        return;
      }}
      await post('/api/request-changes', {{
        course: course.value,
        lesson: Number(document.getElementById('targetLesson').value || 1),
        artifact_type: artifactType,
        note
      }});
    }}
    async function uploadFiles() {{
      try {{
        const form = new FormData();
        form.append('course', course.value);
        form.append('scope', document.getElementById('uploadScope').value);
        form.append('lesson', document.getElementById('uploadLesson').value || '1');
        form.append('reference_policy', document.getElementById('referencePolicy').value);
        for (const file of document.getElementById('files').files) form.append('files', file);
        const res = await fetch('/api/upload', {{ method: 'POST', body: form }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Upload failed');
        msg.textContent = data.message || 'Uploaded.';
        await refresh();
      }} catch (error) {{ msg.textContent = error.message; }}
    }}
    document.querySelectorAll('[data-level]').forEach(btn => btn.onclick = () => setLevel(btn.dataset.level));
    document.getElementById('startTop').onclick = startProductionFlow;
    document.getElementById('startProduction').onclick = startProductionFlow;
    document.getElementById('uploadScope').onchange = toggleLessonInput;
    document.getElementById('upload').onclick = uploadFiles;
    document.getElementById('logSearch').oninput = renderJobs;
    document.getElementById('actorFilter').onchange = renderJobs;
    document.getElementById('targetLesson').onchange = renderApprovals;
    toggleLessonInput();
    refresh();
    setInterval(refresh, 10000);
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

    def send_file(self, path: Path) -> None:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
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
            if parsed.path == "/api/status":
                course = parse_qs(parsed.query).get("course", [getattr(self.server, "default_course", DEFAULT_COURSE)])[0]
                self.send_json(HTTPStatus.OK, course_status(course))
                return
            if parsed.path == "/api/jobs":
                job_root = getattr(self.server, "job_root")
                jobs = list_jobs(job_root)[-30:]
                self.send_json(HTTPStatus.OK, {"jobs": jobs})
                return
            if parsed.path == "/api/uploads":
                course = parse_qs(parsed.query).get("course", [getattr(self.server, "default_course", DEFAULT_COURSE)])[0]
                self.send_json(HTTPStatus.OK, {"uploads": list_uploads(getattr(self.server, "upload_root"), course)})
                return
            if parsed.path == "/artifact":
                artifact = parse_qs(parsed.query).get("path", [""])[0]
                self.send_file(safe_artifact_path(artifact))
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
                saved = []
                for field in file_fields:
                    filename = str(field.get("filename") or "")
                    data = bytes(field.get("data") or b"")
                    if not filename:
                        continue
                    saved.append(
                        save_uploaded_file(
                            upload_root=getattr(self.server, "upload_root"),
                            course_slug=course,
                            filename=filename,
                            data=data,
                            scope=scope,
                            lesson=lesson,
                            reference_policy=reference_policy,
                        )
                    )
                self.send_json(HTTPStatus.OK, {"message": f"Uploaded {len(saved)} file(s).", "uploads": saved})
                return
            body = read_request_body(self)
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
                self.send_json(HTTPStatus.OK, {"message": "Approval recorded.", "approval": data})
                return
            if parsed.path == "/api/request-changes":
                course = str(body.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE))
                lesson = int(body.get("lesson") or 1)
                artifact_type = str(body.get("artifact_type") or "artifact")
                note = str(body.get("note") or "")
                feedback = record_revision_request(course_slug=course, lesson=lesson, artifact_type=artifact_type, note=note)
                result = enqueue_job(
                    job_root=job_root,
                    request_type="stage_next",
                    course_slug=course,
                    lesson=lesson,
                    summary=f"ui revision request for {artifact_type}: {note[:180]}",
                )
                self.send_json(HTTPStatus.OK, {"message": "Edit request recorded and queued.", "feedback": feedback, "job": result.job})
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
