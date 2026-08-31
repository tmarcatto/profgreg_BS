#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_aistudios_api.py"
spec = importlib.util.spec_from_file_location("greg_aistudios_api", MODULE_PATH)
api = importlib.util.module_from_spec(spec)
sys.modules["greg_aistudios_api"] = api
assert spec and spec.loader
spec.loader.exec_module(api)


class AiStudiosApiTests(unittest.TestCase):
    def test_credentials_are_loaded_without_exposing_values(self) -> None:
        with patch.dict(os.environ, {"AISTUDIOS_APP_ID": "app-id", "AISTUDIOS_USER_KEY": "secret-key"}, clear=False):
            credentials = api.AiStudiosCredentials.from_environment()
        self.assertEqual("app-id", credentials.app_id)
        self.assertEqual("secret-key", credentials.user_key)

    def test_missing_credentials_use_operator_safe_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(api.AiStudiosError, "protected environment file"):
                api.AiStudiosCredentials.from_environment()

    def test_transport_accepts_bare_list_catalog_response(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'[{"modelId":"model-1"}]'

        with patch.object(urllib.request, "urlopen", return_value=Response()):
            self.assertEqual(
                [{"modelId": "model-1"}],
                api.urllib_transport("GET", "https://app.aistudios.com/test", {}, None),
            )

    def test_fixed_docs_to_video_options_match_approved_flow(self) -> None:
        options = api.docs_to_video_options(locale="pt", template_id="template-1", model_id="gregory-1")
        self.assertEqual("pt", options["language"])
        self.assertEqual(api.OBJECTIVE, options["objective"])
        self.assertEqual(api.AUDIENCE, options["audience"])
        self.assertEqual(api.TONE, options["tone"])
        self.assertEqual(1, options["speed"])
        self.assertFalse(options["voiceOnly"])

    def test_presentation_validation_enforces_pptx_and_twenty_mb(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            valid = Path(tmp) / "lesson.pptx"
            valid.write_bytes(b"pptx")
            self.assertEqual(valid.resolve(), api.validate_presentation(valid))
            invalid = Path(tmp) / "lesson.pdf"
            invalid.write_bytes(b"pdf")
            with self.assertRaisesRegex(api.AiStudiosError, "PPTX"):
                api.validate_presentation(invalid)

    def test_download_url_is_available_only_after_completed_export(self) -> None:
        self.assertEqual("", api.completed_download_url({"progress": 99, "downloadUrl": "https://cdn.example/video.mp4"}))
        self.assertEqual(
            "https://cdn.example/video.mp4",
            api.completed_download_url({"progress": 100, "downloadUrl": "https://cdn.example/video.mp4"}),
        )
        with self.assertRaisesRegex(api.AiStudiosError, "valid HTTPS download URL"):
            api.completed_download_url({"progress": 100, "downloadUrl": "javascript:alert(1)"})

    def test_client_builds_docs_project_with_fixed_options(self) -> None:
        calls = []

        def transport(method, url, headers, body):
            calls.append((method, url, headers, body))
            if url.endswith("/auth/token"):
                return {"success": True, "data": {"token": "temporary-token"}}
            return {"success": True, "data": {"projectId": "project-123"}}

        client = api.AiStudiosClient(api.AiStudiosCredentials("app", "key"), transport=transport)
        project_id = client.create_docs_project(
            {"uri": "uploaded.pptx", "fileName": "lesson.pptx"},
            locale="es",
            template_id="template-1",
            model_id="gregory-1",
        )
        self.assertEqual("project-123", project_id)
        self.assertNotIn("key", str(calls[1][2]))
        self.assertIn(b'"language": "es"', calls[1][3])
        self.assertIn(b'"templateId": "template-1"', calls[1][3])

    def test_discovery_uses_business_file_background_template_filter(self) -> None:
        calls = []

        def transport(method, url, headers, body):
            calls.append((method, url, headers, body))
            if url.endswith("/auth/token"):
                return {"success": True, "data": {"token": "temporary-token"}}
            return {"success": True, "data": []}

        client = api.AiStudiosClient(api.AiStudiosCredentials("app", "key"), transport=transport)
        client.automation_templates()
        self.assertNotIn("?", calls[-1][1])
        self.assertIn(b'"category": "business"', calls[-1][3])
        self.assertIn(b'"orientation": "web"', calls[-1][3])
        self.assertIn(b'"fileBackground": true', calls[-1][3])

    def test_catalog_accepts_numeric_object_returned_by_template_endpoint(self) -> None:
        data = {
            "0": {"id": "template-1", "name": "First"},
            "1": {"id": "template-2", "name": "Second"},
        }
        self.assertEqual(["template-1", "template-2"], [item["id"] for item in api.AiStudiosClient._catalog(data, "templates")])

    def test_project_unwraps_project_payload(self) -> None:
        def transport(method, url, headers, body):
            if url.endswith("/auth/token"):
                return {"success": True, "data": {"token": "temporary-token"}}
            return {"success": True, "data": {"project": {"_id": "project-1", "scenes": []}}}

        client = api.AiStudiosClient(api.AiStudiosCredentials("app", "key"), transport=transport)
        self.assertEqual("project-1", client.project("project-1")["_id"])


if __name__ == "__main__":
    unittest.main()
