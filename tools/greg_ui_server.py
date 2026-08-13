#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from greg_operator import course_status, default_job_root, enqueue_job, handle_request
from greg_server_status import list_jobs, safe_job_root
from greg_create_run import create_run, slugify


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_COURSE = "construction-schedule-management"
ROOT = Path(__file__).resolve().parents[1]
SERVER_UPLOAD_ROOT = Path("/srv/profgreg/uploads")
LOCAL_UPLOAD_ROOT = ROOT / "tmp" / "uploads"
MAX_UPLOAD_BYTES = 75 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


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


def save_uploaded_file(
    *,
    upload_root: Path,
    course_slug: str,
    filename: str,
    data: bytes,
    scope: str = "course",
    lesson: int | None = None,
) -> dict:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Upload is too large.")
    clean_name = safe_filename(filename)
    scope_name = "course" if scope != "lesson" else f"lesson_{int(lesson or 1):02d}"
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
        "size_bytes": len(data),
        "sha256": file_sha256(target),
    }
    manifest = upload_course_dir(upload_root, course_slug) / "upload_manifest.jsonl"
    with manifest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(meta, ensure_ascii=False) + "\n")
    return meta


def list_uploads(upload_root: Path, course_slug: str) -> list[dict]:
    manifest = upload_course_dir(upload_root, course_slug) / "upload_manifest.jsonl"
    if not manifest.exists():
        return []
    return [json.loads(line) for line in manifest.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()][-50:]


def create_course_intake(*, title: str, level: str, syllabus: str, course_slug: str | None = None) -> dict:
    if not title.strip():
        raise ValueError("Course title is required.")
    setup = create_run(title.strip(), course_slug, level or "Basic")
    intake = ROOT / setup.intake_path
    intake.write_text(
        "\n".join(
            [
                f"# {title.strip()}",
                "",
                f"Course slug: `{setup.course_slug}`",
                f"Course level: {level or 'Basic'}",
                "Base language: English",
                "Audience: U.S. residential construction workforce.",
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


def ui_shell(default_course: str) -> str:
    course = html.escape(default_course)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Prof Greg Operator</title>
  <style>
    :root {{
      --navy: #1f3f66;
      --orange: #ff6b13;
      --ink: #182235;
      --muted: #667085;
      --line: #d9e0ea;
      --soft: #f4f7fb;
      --ok: #157347;
      --warn: #a15c00;
      --bad: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #fff;
    }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      min-height: 72px;
      padding: 18px 28px;
      border-bottom: 1px solid var(--line);
      background: var(--navy);
      color: #fff;
    }}
    .brand {{ display: flex; align-items: center; gap: 12px; font-weight: 760; font-size: 20px; }}
    .mark {{
      width: 30px; height: 30px; border: 2px solid var(--orange); border-radius: 50%;
      display: grid; place-items: center; font-size: 16px; color: #fff;
    }}
    .status-pill {{ color: #fff; border: 1px solid rgba(255,255,255,.32); padding: 8px 12px; border-radius: 999px; font-size: 13px; }}
    main {{ padding: 24px 28px 36px; display: grid; gap: 20px; max-width: 1240px; margin: 0 auto; }}
    .toolbar {{ display: grid; grid-template-columns: minmax(220px, 1fr) auto auto auto; gap: 10px; align-items: center; }}
    input, textarea, button {{
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
    }}
    input, textarea, select {{ padding: 10px 12px; color: var(--ink); background: #fff; }}
    textarea {{ width: 100%; min-height: 86px; resize: vertical; }}
    button {{ padding: 10px 14px; background: #fff; color: var(--navy); font-weight: 680; cursor: pointer; }}
    button.primary {{ background: var(--orange); border-color: var(--orange); color: #fff; }}
    button:disabled {{ opacity: .55; cursor: not-allowed; }}
    .grid {{ display: grid; grid-template-columns: 1.15fr .85fr; gap: 18px; align-items: start; }}
    .wide {{ grid-column: 1 / -1; }}
    .form-grid {{ display: grid; grid-template-columns: minmax(240px, 1fr) 180px 180px; gap: 10px; align-items: start; }}
    .file-grid {{ display: grid; grid-template-columns: minmax(240px, 1fr) 190px 96px auto; gap: 10px; align-items: center; }}
    section {{ border: 1px solid var(--line); border-radius: 8px; background: #fff; overflow: hidden; }}
    section h2 {{ margin: 0; padding: 14px 16px; font-size: 16px; color: var(--navy); border-bottom: 1px solid var(--line); background: var(--soft); }}
    .body {{ padding: 16px; }}
    .facts {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
    .fact {{ border: 1px solid var(--line); border-radius: 6px; padding: 12px; min-height: 78px; }}
    .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    .value {{ margin-top: 6px; color: var(--ink); font-weight: 720; line-height: 1.25; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .route, .message {{ border-left: 4px solid var(--orange); background: #fff8f1; padding: 12px; border-radius: 4px; margin-top: 12px; color: var(--ink); }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 10px 8px; vertical-align: top; font-size: 14px; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    .state {{ font-weight: 760; }}
    .completed {{ color: var(--ok); }}
    .queued, .running {{ color: var(--warn); }}
    .failed, .cancelled {{ color: var(--bad); }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 820px) {{
      header {{ align-items: flex-start; flex-direction: column; }}
      .toolbar, .grid, .facts, .form-grid, .file-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="brand"><div class="mark">G</div><div>Prof Greg Operator</div></div>
    <div class="status-pill">Private server console</div>
  </header>
  <main>
    <div class="toolbar">
      <input id="course" value="{course}" aria-label="Course slug">
      <button id="refresh">Refresh</button>
      <button id="backup">Queue Backup</button>
      <button class="primary" id="lifecycle">Queue Lesson Lifecycle</button>
    </div>
    <div class="grid">
      <section class="wide">
        <h2>Create Course / Intake</h2>
        <div class="body">
          <div class="form-grid">
            <input id="courseTitle" placeholder="Course title">
            <select id="courseLevel">
              <option>Basic</option>
              <option>Intermediate</option>
              <option>Advanced</option>
            </select>
            <input id="courseSlug" placeholder="Optional slug">
          </div>
          <textarea id="syllabus" placeholder="Paste the initial syllabus direction here. Greg treats this as a starting point, not a fixed Course Map."></textarea>
          <div class="actions">
            <button class="primary" id="createCourse">Create Intake</button>
          </div>
        </div>
      </section>
      <section class="wide">
        <h2>Upload Materials</h2>
        <div class="body">
          <div class="file-grid">
            <input id="files" type="file" multiple accept=".pdf,.docx,.txt,.md">
            <select id="uploadScope">
              <option value="course">Course-level source</option>
              <option value="lesson">Lesson-specific source</option>
            </select>
            <input id="uploadLesson" type="number" min="1" value="1">
            <button class="primary" id="upload">Upload</button>
          </div>
          <table>
            <thead><tr><th>File</th><th>Scope</th><th>Size</th></tr></thead>
            <tbody id="uploads"><tr><td colspan="3" class="muted">No uploads loaded.</td></tr></tbody>
          </table>
        </div>
      </section>
      <section>
        <h2>Course Status</h2>
        <div class="body">
          <div class="facts">
            <div class="fact"><div class="label">Stage</div><div class="value" id="stage">Loading</div></div>
            <div class="fact"><div class="label">Gate</div><div class="value" id="gate">Loading</div></div>
            <div class="fact"><div class="label">Next</div><div class="value" id="next">Loading</div></div>
          </div>
          <div class="message" id="message">Ready.</div>
          <div class="actions">
            <textarea id="requestText" placeholder="Type a request, for example: mostre o status, gere o deck, rode o lifecycle da lesson 1"></textarea>
            <button id="interpret">Interpret Only</button>
            <button class="primary" id="enqueue">Interpret and Queue Safe Job</button>
          </div>
          <div class="route" id="route">No request interpreted yet.</div>
        </div>
      </section>
      <section>
        <h2>Jobs</h2>
        <div class="body">
          <table>
            <thead><tr><th>Job</th><th>State</th><th>Type</th></tr></thead>
            <tbody id="jobs"><tr><td colspan="3" class="muted">Loading</td></tr></tbody>
          </table>
        </div>
      </section>
    </div>
  </main>
  <script>
    const course = document.getElementById('course');
    const msg = document.getElementById('message');
    const route = document.getElementById('route');
    function esc(value) {{
      return String(value ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    }}
    async function api(path, options) {{
      const res = await fetch(path, Object.assign({{headers: {{'Content-Type': 'application/json'}}}}, options || {{}}));
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Request failed');
      return data;
    }}
    async function refresh() {{
      try {{
        const status = await api('/api/status?course=' + encodeURIComponent(course.value));
        document.getElementById('stage').textContent = status.stage || 'Unknown';
        document.getElementById('gate').textContent = status.gate_status || 'Unknown';
        document.getElementById('next').textContent = status.next_recommended_action || 'Review status.';
        const jobs = await api('/api/jobs');
        const rows = jobs.jobs.length ? jobs.jobs.map(j => `<tr><td><code>${{esc(j.job_id)}}</code></td><td class="state ${{esc(j.state)}}">${{esc(j.state)}}</td><td>${{esc(j.request_type)}}</td></tr>`).join('') : '<tr><td colspan="3" class="muted">No jobs yet.</td></tr>';
        document.getElementById('jobs').innerHTML = rows;
        const uploads = await api('/api/uploads?course=' + encodeURIComponent(course.value));
        const uploadRows = uploads.uploads.length ? uploads.uploads.map(u => `<tr><td>${{esc(u.filename)}}</td><td>${{esc(u.scope)}}</td><td>${{Math.round((u.size_bytes || 0) / 1024)}} KB</td></tr>`).join('') : '<tr><td colspan="3" class="muted">No uploads yet.</td></tr>';
        document.getElementById('uploads').innerHTML = uploadRows;
      }} catch (error) {{
        msg.textContent = error.message;
      }}
    }}
    async function post(path, body) {{
      try {{
        const data = await api(path, {{method: 'POST', body: JSON.stringify(body || {{}})}});
        msg.textContent = data.message || 'Done.';
        if (data.route) {{
          route.innerHTML = `<strong>${{esc(data.route.intent)}}</strong> · ${{esc(data.route.stage)}}<br>${{esc(data.route.next_action)}}`;
        }}
        await refresh();
        return data;
      }} catch (error) {{
        msg.textContent = error.message;
        throw error;
      }}
    }}
    document.getElementById('refresh').onclick = refresh;
    document.getElementById('backup').onclick = () => post('/api/backup', {{summary: 'ui backup request'}});
    document.getElementById('lifecycle').onclick = () => post('/api/lesson-lifecycle', {{course: course.value, lesson: 1}});
    document.getElementById('createCourse').onclick = () => post('/api/create-course', {{
      title: document.getElementById('courseTitle').value,
      level: document.getElementById('courseLevel').value,
      slug: document.getElementById('courseSlug').value,
      syllabus: document.getElementById('syllabus').value
    }}).then((data) => {{
      const manualSlug = document.getElementById('courseSlug').value;
      course.value = data.course_slug || manualSlug || course.value;
    }}).then(refresh);
    }});
    document.getElementById('upload').onclick = async () => {{
      try {{
        const form = new FormData();
        form.append('course', course.value);
        form.append('scope', document.getElementById('uploadScope').value);
        form.append('lesson', document.getElementById('uploadLesson').value);
        for (const file of document.getElementById('files').files) form.append('files', file);
        const res = await fetch('/api/upload', {{ method: 'POST', body: form }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Upload failed');
        msg.textContent = data.message || 'Uploaded.';
        await refresh();
      }} catch (error) {{
        msg.textContent = error.message;
      }}
    }};
    document.getElementById('interpret').onclick = () => post('/api/request', {{course: course.value, lesson: 1, request: document.getElementById('requestText').value, enqueue: false}});
    document.getElementById('enqueue').onclick = () => post('/api/request', {{course: course.value, lesson: 1, request: document.getElementById('requestText').value, enqueue: true}});
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
                if content_length > MAX_UPLOAD_BYTES + 1024 * 1024:
                    self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Upload request is too large."})
                    return
                raw = self.rfile.read(content_length)
                fields, file_fields = parse_multipart_form(self.headers.get("Content-Type", ""), raw)
                course = str(fields.get("course") or getattr(self.server, "default_course", DEFAULT_COURSE))
                scope = str(fields.get("scope") or "course")
                lesson = int(fields.get("lesson") or 1)
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
            if parsed.path == "/api/request":
                result = handle_request(
                    str(body.get("request") or ""),
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
