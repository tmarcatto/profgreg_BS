import http.client
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import greg_model_router


class ModelRouterRetryTests(unittest.TestCase):
    @patch("greg_model_router.load_config")
    def test_cost_estimate_uses_input_cached_and_output_rates(self, load_config):
        load_config.return_value = {
            "cost_tracking": {"rates": {"openai/test-model": {
                "input_per_million_usd": 2, "cached_input_per_million_usd": 0.2,
                "output_per_million_usd": 10, "rate_version": "test-rate"
            }}}
        }
        cost = greg_model_router.cost_estimate(
            {"provider": "openai", "model": "test-model"},
            {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "input_tokens_details": {"cached_tokens": 200_000}},
        )
        self.assertEqual("estimated", cost["status"])
        self.assertEqual(11.64, cost["estimated_usd"])

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

    @patch("greg_model_router.post_json")
    def test_openai_reasoning_effort_is_sent_from_the_binding(self, post_json):
        post_json.return_value = {"output_text": "review", "usage": {"input_tokens": 1, "output_tokens": 2}}

        result = greg_model_router.openai_text(
            "https://example.test", "secret", "gpt-5.6-luna", "prompt", 100, False, reasoning="max"
        )

        self.assertEqual("review", result)
        self.assertEqual({"effort": "max"}, post_json.call_args.args[1]["reasoning"])

    @patch("greg_model_router.openai_text")
    @patch("greg_model_router.append_usage")
    @patch("greg_model_router.binding_for")
    def test_empty_max_reasoning_retries_same_model_at_high(self, binding_for, append_usage, openai_text):
        binding_for.return_value = (
            {"provider": "openai", "model": "gpt-5.6-luna", "reasoning": "max"},
            {"api_key_env": "TEST_OPENAI_KEY", "base_url_env": ""},
        )
        openai_text.side_effect = [
            greg_model_router.ModelRequestError(
                "OpenAI returned no text content (reason={'reason': 'max_output_tokens'})."
            ),
            ("completed", {"input_tokens": 1, "output_tokens": 2}),
        ]
        with patch.dict("os.environ", {"TEST_OPENAI_KEY": "key"}):
            result = greg_model_router.request_text("course", "technical_content", "prompt")

        self.assertEqual("completed", result)
        self.assertEqual("max", openai_text.call_args_list[0].kwargs["reasoning"])
        self.assertEqual("high", openai_text.call_args_list[1].kwargs["reasoning"])
        self.assertEqual("high_after_empty_max", append_usage.call_args.kwargs["usage"]["reasoning_fallback"])

    @patch("greg_model_router.openai_text")
    @patch("greg_model_router.append_usage")
    @patch("greg_model_router.binding_for")
    def test_empty_high_reasoning_retries_same_model_at_medium(self, binding_for, append_usage, openai_text):
        binding_for.return_value = (
            {"provider": "openai", "model": "gpt-5.6-luna", "reasoning": "high"},
            {"api_key_env": "TEST_OPENAI_KEY", "base_url_env": ""},
        )
        openai_text.side_effect = [
            greg_model_router.ModelRequestError(
                "OpenAI returned no text content (status='completed', reason='no completion detail')."
            ),
            ("completed", {"input_tokens": 1, "output_tokens": 2}),
        ]
        with patch.dict("os.environ", {"TEST_OPENAI_KEY": "key"}):
            result = greg_model_router.request_text("course", "source_research", "prompt", web_search=True)

        self.assertEqual("completed", result)
        self.assertEqual("high", openai_text.call_args_list[0].kwargs["reasoning"])
        self.assertEqual("medium", openai_text.call_args_list[1].kwargs["reasoning"])
        self.assertEqual("medium_after_empty_high", append_usage.call_args.kwargs["usage"]["reasoning_fallback"])

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
