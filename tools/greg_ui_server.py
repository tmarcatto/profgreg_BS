#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from greg_operator import course_status, default_job_root, enqueue_job, handle_request
from greg_server_status import list_jobs, safe_job_root


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_COURSE = "construction-schedule-management"


def json_bytes(data: object) -> bytes:
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")


def read_request_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(min(length, 1024 * 1024))
    return json.loads(raw.decode("utf-8") or "{}")


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
    input, textarea {{ padding: 10px 12px; color: var(--ink); background: #fff; }}
    textarea {{ width: 100%; min-height: 86px; resize: vertical; }}
    button {{ padding: 10px 14px; background: #fff; color: var(--navy); font-weight: 680; cursor: pointer; }}
    button.primary {{ background: var(--orange); border-color: var(--orange); color: #fff; }}
    button:disabled {{ opacity: .55; cursor: not-allowed; }}
    .grid {{ display: grid; grid-template-columns: 1.15fr .85fr; gap: 18px; align-items: start; }}
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
      .toolbar, .grid, .facts {{ grid-template-columns: 1fr; }}
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
      }} catch (error) {{
        msg.textContent = error.message;
      }}
    }}
    document.getElementById('refresh').onclick = refresh;
    document.getElementById('backup').onclick = () => post('/api/backup', {{summary: 'ui backup request'}});
    document.getElementById('lifecycle').onclick = () => post('/api/lesson-lifecycle', {{course: course.value, lesson: 1}});
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
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)[:500]})

    def do_POST(self) -> None:
        if not self.check_token():
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
            return
        parsed = urlparse(self.path)
        try:
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
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)[:500]})

    def log_message(self, format: str, *args: object) -> None:
        return


def build_server(host: str, port: int, *, job_root: Path, default_course: str, ui_token: str = "") -> ThreadingHTTPServer:
    resolved_job_root = safe_job_root(job_root)
    server = ThreadingHTTPServer((host, port), GregUiHandler)
    server.job_root = resolved_job_root  # type: ignore[attr-defined]
    server.default_course = default_course  # type: ignore[attr-defined]
    server.ui_token = ui_token  # type: ignore[attr-defined]
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the private Prof Greg operator UI.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--job-root", default=str(default_job_root()))
    parser.add_argument("--course", default=DEFAULT_COURSE)
    parser.add_argument("--token-env", default="PROFGREG_UI_TOKEN")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Refusing to bind UI outside localhost in the private v0 interface.")
    server = build_server(
        args.host,
        args.port,
        job_root=Path(args.job_root),
        default_course=args.course,
        ui_token=os.environ.get(args.token_env, ""),
    )
    print(f"Prof Greg UI listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
