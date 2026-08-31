#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Union


API_HOST = "https://app.aistudios.com"
MAX_PPTX_BYTES = 20 * 1024 * 1024
SUPPORTED_LOCALES = {"en", "pt", "es"}
OBJECTIVE = "Teach practical construction knowledge that students can understand"
AUDIENCE = "subcontractors, general contractors, project managers, and construction workers"
TONE = "practical, empowering, trustworthy, and friendly"


class AiStudiosError(RuntimeError):
    pass


@dataclass(frozen=True)
class AiStudiosCredentials:
    app_id: str
    user_key: str

    @classmethod
    def from_environment(cls) -> "AiStudiosCredentials":
        app_id = os.environ.get("AISTUDIOS_APP_ID", "").strip()
        user_key = os.environ.get("AISTUDIOS_USER_KEY", "").strip()
        if not app_id or not user_key:
            raise AiStudiosError(
                "AI Studios credentials are not configured. Set AISTUDIOS_APP_ID and "
                "AISTUDIOS_USER_KEY in the protected environment file."
            )
        return cls(app_id=app_id, user_key=user_key)


def docs_to_video_options(*, locale: str, template_id: str, model_id: str) -> dict[str, Any]:
    if locale not in SUPPORTED_LOCALES:
        raise ValueError(f"Unsupported AI Studios locale: {locale}")
    if not template_id.strip() or not model_id.strip():
        raise ValueError("AI Studios template and Gregory model IDs are required.")
    return {
        "language": locale,
        "objective": OBJECTIVE,
        "audience": AUDIENCE,
        "tone": TONE,
        "speed": 1,
        "templateId": template_id,
        "model": model_id,
        "voiceOnly": False,
    }


def validate_presentation(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.suffix.lower() != ".pptx":
        raise AiStudiosError("Video Generator accepts approved PPTX presentations only.")
    if not resolved.exists() or not resolved.is_file():
        raise AiStudiosError("Approved PPTX presentation was not found.")
    if resolved.stat().st_size > MAX_PPTX_BYTES:
        raise AiStudiosError("Approved PPTX exceeds the 20 MB Docs-to-Video limit.")
    return resolved


def completed_download_url(progress: dict[str, Any]) -> str:
    """Return the final HTTPS export URL only after AI Studios reports completion."""
    try:
        percent = float(progress.get("progress") or 0)
    except (TypeError, ValueError):
        percent = 0
    if percent < 100:
        return ""
    value = str(progress.get("downloadUrl") or "").strip()
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise AiStudiosError("AI Studios completed the export without a valid HTTPS download URL.")
    return value


def multipart_file_body(path: Path, *, field_name: str = "files") -> tuple[bytes, str]:
    boundary = f"----prof-greg-{secrets.token_hex(12)}"
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{path.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return prefix + path.read_bytes() + suffix, f"multipart/form-data; boundary={boundary}"


JsonResponse = Union[dict[str, Any], list[Any]]
Transport = Callable[[str, str, dict[str, str], Optional[bytes]], JsonResponse]


def urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> JsonResponse:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise AiStudiosError(f"AI Studios request failed with HTTP {error.code}.") from error
    except urllib.error.URLError as error:
        raise AiStudiosError("AI Studios could not be reached.") from error
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise AiStudiosError("AI Studios returned an invalid response.") from error
    if not isinstance(data, (dict, list)) or (isinstance(data, dict) and data.get("success") is False):
        error_data = data.get("error") if isinstance(data, dict) else None
        if isinstance(error_data, dict):
            code = str(error_data.get("code") or "unknown")
        elif error_data is not None:
            code = str(error_data)[:80]
        else:
            code = "unexpected_response"
        raise AiStudiosError(f"AI Studios rejected the request (code {code}).")
    return data


class AiStudiosClient:
    def __init__(self, credentials: AiStudiosCredentials, *, transport: Transport = urllib_transport) -> None:
        self.credentials = credentials
        self.transport = transport
        self._token = ""

    @staticmethod
    def _data(response: JsonResponse) -> Any:
        return response.get("data", response) if isinstance(response, dict) else response

    @staticmethod
    def _catalog(data: Any, field: str) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if not isinstance(data, dict):
            return []
        nested = data.get(field)
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
        if data and all(isinstance(item, dict) for item in data.values()):
            return list(data.values())
        return []

    def _json_request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> JsonResponse:
        url = API_HOST + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = self.access_token()
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        return self.transport(method, url, headers, body)

    def access_token(self) -> str:
        if self._token:
            return self._token
        response = self._json_request(
            "POST",
            "/api/odin/v3/auth/token",
            payload={"appId": self.credentials.app_id, "userKey": self.credentials.user_key},
            authenticated=False,
        )
        token = str((self._data(response) or {}).get("token") or "")
        if not token:
            raise AiStudiosError("AI Studios did not issue an access token.")
        self._token = token
        return token

    def workspaces(self) -> list[dict[str, Any]]:
        data = self._data(self._json_request("GET", "/api/odin/v3/dropdown/workspaces"))
        return self._catalog(data, "workspaces")

    def models(self) -> list[dict[str, Any]]:
        data = self._data(self._json_request("GET", "/api/odin/v3/dropdown/models"))
        return self._catalog(data, "models")

    def automation_templates(self) -> list[dict[str, Any]]:
        response = self._json_request(
            "POST",
            "/api/odin/v3/dropdown/templates_automation",
            payload={"category": "business", "orientation": "web", "fileBackground": True},
        )
        data = self._data(response)
        return self._catalog(data, "templates")

    def upload_presentation(self, path: Path) -> dict[str, str]:
        presentation = validate_presentation(path)
        body, content_type = multipart_file_body(presentation)
        response = self.transport(
            "POST",
            API_HOST + "/api/odin/v3/automation/docs-to-video/upload-files",
            {"Authorization": self.access_token(), "Content-Type": content_type},
            body,
        )
        results = (self._data(response) or {}).get("uploadResults") or []
        if len(results) != 1 or not results[0].get("uri"):
            raise AiStudiosError("AI Studios did not return one uploaded presentation URI.")
        return {"uri": str(results[0]["uri"]), "fileName": str(results[0].get("fileName") or presentation.name)}

    def create_docs_project(
        self,
        uploaded_file: dict[str, str],
        *,
        locale: str,
        template_id: str,
        model_id: str,
    ) -> str:
        response = self._json_request(
            "POST",
            "/api/odin/v3/automation/docs-to-video",
            payload={
                "files": [uploaded_file],
                "options": docs_to_video_options(locale=locale, template_id=template_id, model_id=model_id),
            },
        )
        project_id = str((self._data(response) or {}).get("projectId") or "")
        if not project_id:
            raise AiStudiosError("AI Studios did not return a Docs-to-Video project ID.")
        return project_id

    def creation_progress(self, project_id: str) -> dict[str, Any]:
        return dict(self._data(self._json_request("GET", "/api/odin/v3/automation/progress", query={"projectId": project_id})) or {})

    def project(self, project_id: str) -> dict[str, Any]:
        data = self._data(self._json_request("GET", f"/api/odin/v3/editor/project/{project_id}"))
        if not isinstance(data, dict):
            raise AiStudiosError("AI Studios did not return valid project data.")
        project = data.get("project", data)
        if not isinstance(project, dict) or not project.get("_id"):
            raise AiStudiosError("AI Studios did not return the generated project.")
        return dict(project)

    def export_project(self, project_id: str, *, workspace_id: str = "") -> str:
        payload = {"projectId": project_id}
        if workspace_id:
            payload["workspaceId"] = workspace_id
        response = self._json_request("POST", "/api/odin/v3/editor/project/export", payload=payload)
        return str((self._data(response) or {}).get("projectId") or project_id)

    def export_progress(self, project_id: str) -> dict[str, Any]:
        return dict(self._data(self._json_request("GET", f"/api/odin/v3/editor/progress/{project_id}")) or {})

    def completed_export_url(self, project_id: str) -> str:
        return completed_download_url(self.export_progress(project_id))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the protected AI Studios API configuration.")
    parser.add_argument("--check-config", action="store_true", help="Check only that protected environment values exist.")
    args = parser.parse_args()
    credentials = AiStudiosCredentials.from_environment()
    if args.check_config:
        print("AI Studios API configuration is present. No network request was made.")
        return 0
    raise SystemExit("Use --check-config. Live API actions are enabled only through the guided Video Generator pilot.")


if __name__ == "__main__":
    raise SystemExit(main())
