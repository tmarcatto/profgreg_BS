import http.client
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import greg_model_router


class ModelRouterRetryTests(unittest.TestCase):
    @patch("greg_model_router.time.sleep")
    @patch("greg_model_router.urllib.request.urlopen")
    def test_retries_remote_disconnect_then_returns_json(self, urlopen, sleep):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok": true}'
        urlopen.side_effect = [http.client.RemoteDisconnected(), response]

        result = greg_model_router.post_json("https://example.test", {"x": 1}, {})

        self.assertEqual({"ok": True}, result)
        self.assertEqual(2, urlopen.call_count)
        sleep.assert_called_once_with(1)

    @patch("greg_model_router.post_json")
    def test_anthropic_long_generation_uses_extended_timeout(self, post_json):
        post_json.return_value = {"content": [{"type": "text", "text": "draft"}]}

        result = greg_model_router.anthropic_text(
            "https://example.test", "secret", "configured-model", "prompt", 14000
        )

        self.assertEqual("draft", result)
        self.assertEqual(600, post_json.call_args.kwargs["timeout"])
        self.assertEqual(2, post_json.call_args.kwargs["attempts"])

    @patch("greg_model_router.post_json")
    def test_request_text_records_provider_token_usage(self, post_json):
        post_json.return_value = {
            "content": [{"type": "text", "text": "draft"}],
            "usage": {"input_tokens": 12, "output_tokens": 34},
        }
        binding = {"provider": "anthropic", "model": "configured-model"}
        provider = {"api_key_env": "TEST_ANTHROPIC_KEY", "base_url_env": ""}
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(greg_model_router, "ROOT", Path(temporary)), patch.object(
                greg_model_router, "binding_for", return_value=(binding, provider)
            ), patch.dict("os.environ", {"TEST_ANTHROPIC_KEY": "key"}):
                self.assertEqual("draft", greg_model_router.request_text("course", "technical_content", "prompt"))
                log = Path(temporary, "runs", "course", "ops", "model_usage_log.jsonl")
                row = json.loads(log.read_text(encoding="utf-8"))
        self.assertEqual({"input_tokens": 12, "output_tokens": 34}, row["usage"])

    @patch("greg_model_router.time.sleep")
    @patch("greg_model_router.urllib.request.urlopen")
    def test_remote_disconnect_is_normalized_after_last_attempt(self, urlopen, sleep):
        urlopen.side_effect = http.client.RemoteDisconnected()

        with self.assertRaisesRegex(greg_model_router.ModelRequestError, "could not be reached"):
            greg_model_router.post_json("https://example.test", {"x": 1}, {}, attempts=2)

        self.assertEqual(2, urlopen.call_count)
        sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
