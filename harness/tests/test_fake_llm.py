from __future__ import annotations

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from harness.agentforge_harness.fake_llm import SCENARIOS, make_server


class FakeLLMTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = make_server(port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(
        self,
        scenario: str = "success",
        *,
        body: dict[str, object] | None = None,
    ):
        headers = {
            "Content-Type": "application/json",
            "X-Tenant-ID": "tenant-0001",
            "X-Trace-ID": "0123456789abcdef0123456789abcdef",
            "X-Run-ID": "run-harness-0001",
            "X-Step-ID": "step-harness-0001",
            "Idempotency-Key": "idem-harness-0001",
            "X-Harness-Scenario": scenario,
        }
        payload = body or {
            "model": "fake-finance-model",
            "messages": [{"role": "user", "content": "固定问题"}],
        }
        return urlopen(
            Request(
                self.base_url + "/v1/chat/completions",
                data=json.dumps(payload).encode(),
                headers=headers,
                method="POST",
            ),
            timeout=2,
        )

    def test_scenario_catalog_and_success_are_deterministic(self) -> None:
        with urlopen(self.base_url + "/harness/scenarios", timeout=2) as response:
            catalog = json.loads(response.read())
        self.assertEqual(list(SCENARIOS), catalog["scenarios"])
        with self.request() as first, self.request() as second:
            self.assertEqual(first.read(), second.read())

    def test_complete_sse_has_done_and_disconnect_does_not(self) -> None:
        with self.request("sse") as response:
            complete = response.read()
        with self.request("stream_disconnect") as response:
            disconnected = response.read()
        self.assertTrue(complete.endswith(b"data: [DONE]\n\n"))
        self.assertNotIn(b"[DONE]", disconnected)

    def test_remote_image_is_rejected(self) -> None:
        body = {
            "model": "fake-finance-model",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "解释图片"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "https://untrusted.invalid/a.png"},
                        },
                    ],
                }
            ],
        }
        with self.assertRaises(HTTPError) as raised:
            self.request(body=body)
        self.assertEqual(422, raised.exception.code)
        error = json.loads(raised.exception.read())
        self.assertEqual("VALIDATION_FAILED", error["error"]["code"])

    def test_rate_limit_is_retryable_and_invalid_json_is_malformed(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self.request("rate_limit")
        error = json.loads(raised.exception.read())
        self.assertEqual(429, raised.exception.code)
        self.assertTrue(error["error"]["retryable"])
        with self.request("invalid_json") as response:
            malformed = response.read()
        with self.assertRaises(json.JSONDecodeError):
            json.loads(malformed)

    def test_non_loopback_listener_is_forbidden(self) -> None:
        with self.assertRaises(ValueError):
            make_server(host="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
