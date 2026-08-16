import http.client
import unittest
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
