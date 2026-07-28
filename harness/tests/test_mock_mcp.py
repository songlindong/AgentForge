from __future__ import annotations

import json
import threading
import unittest
from urllib.request import Request, urlopen

from harness.agentforge_harness.mock_mcp import make_server


class MockMCPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = make_server(port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/v1/tools/invoke"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def invocation(self) -> dict[str, object]:
        return {
            "invocation_id": "invocation-0001",
            "tenant_id": "tenant-0001",
            "actor": {"actor_type": "agent", "actor_id": "finance-agent"},
            "run_id": "run-0001",
            "task_id": "task-0001",
            "step_id": "step-0001",
            "tool_id": "loan_rate_lookup",
            "tool_version": "1.0.0",
            "trace_id": "abcdef0123456789abcdef0123456789",
            "purpose": "查询固定合成利率",
            "authorization_decision_id": "authorization-0001",
            "deadline": "2026-07-28T08:01:00Z",
            "arguments": {"product_id": "synthetic-product-a"},
        }

    def call(
        self,
        invocation: dict[str, object],
        *,
        tenant: str = "tenant-0001",
        scenario: str = "success",
    ) -> bytes:
        request = Request(
            self.url,
            data=json.dumps(invocation).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Tenant-ID": tenant,
                "X-Harness-Scenario": scenario,
            },
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            return response.read()

    def test_success_has_fixed_mock_provenance(self) -> None:
        result = json.loads(self.call(self.invocation()))
        self.assertEqual("succeeded", result["status"])
        self.assertTrue(result["provenance"]["mock"])
        self.assertEqual("4.20", result["data"]["annual_rate_percent"])

    def test_missing_authorization_wins_over_success(self) -> None:
        invocation = self.invocation()
        del invocation["authorization_decision_id"]
        result = json.loads(self.call(invocation))
        self.assertEqual("denied", result["status"])
        self.assertEqual("TOOL_FORBIDDEN", result["error"]["code"])
        self.assertNotIn("data", result)

    def test_tenant_mismatch_wins_over_invalid_json_scenario(self) -> None:
        result = json.loads(
            self.call(
                self.invocation(), tenant="tenant-0002", scenario="invalid_json"
            )
        )
        self.assertEqual("denied", result["status"])
        self.assertEqual("TENANT_MISMATCH", result["error"]["code"])
        self.assertNotIn("data", result)

    def test_failure_and_approval_scenarios_have_no_dynamic_data(self) -> None:
        for scenario, status in (
            ("dependency_failure", "failed"),
            ("timeout", "timeout"),
            ("denied", "denied"),
            ("approval_required", "approval_required"),
        ):
            with self.subTest(scenario=scenario):
                result = json.loads(self.call(self.invocation(), scenario=scenario))
                self.assertEqual(status, result["status"])
                self.assertNotIn("data", result)


if __name__ == "__main__":
    unittest.main()
