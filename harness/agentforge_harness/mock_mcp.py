"""只返回虚构动态金融数据的确定性 MCP Mock。"""

from __future__ import annotations

from typing import Any
import time

from .common import (
    BaseHarnessHandler,
    FIXED_TIME,
    HarnessHTTPError,
    create_server,
)


SCENARIOS = (
    "success",
    "dependency_failure",
    "timeout",
    "denied",
    "approval_required",
    "invalid_json",
)
TOOLS = (
    "loan_product_search",
    "loan_rate_lookup",
    "repayment_plan_calculate",
    "loan_application_status",
)


def _error(
    trace_id: str,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "error_id": f"err-{code.lower().replace('_', '-')}",
        "code": code,
        "message": message,
        "retryable": retryable,
        "trace_id": trace_id or "0" * 32,
        "occurred_at": FIXED_TIME,
    }
    if retryable:
        value["retry_after_ms"] = 100
    return value


def _result_base(invocation: dict[str, Any]) -> dict[str, Any]:
    return {
        "invocation_id": invocation.get("invocation_id", "invalid-invocation"),
        "tenant_id": invocation.get("tenant_id", "unknown-tenant"),
        "trace_id": invocation.get("trace_id", "0" * 32),
        "redaction_applied": True,
        "completed_at": FIXED_TIME,
    }


def _failure(
    invocation: dict[str, Any],
    status: str,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> dict[str, Any]:
    result = _result_base(invocation)
    result.update(
        {
            "status": status,
            "error": _error(
                result["trace_id"], code, message, retryable=retryable
            ),
        }
    )
    return result


def _tool_data(tool_id: str) -> dict[str, Any]:
    data = {
        "loan_product_search": {
            "products": [
                {
                    "product_id": "synthetic-product-a",
                    "name": "合成稳健贷",
                    "currency": "CNY",
                }
            ]
        },
        "loan_rate_lookup": {
            "product_id": "synthetic-product-a",
            "annual_rate_percent": "4.20",
            "effective_date": "2026-07-01",
            "synthetic": True,
        },
        "repayment_plan_calculate": {
            "currency": "CNY",
            "principal_minor_units": 1000000,
            "periods": 12,
            "first_payment_minor_units": 85150,
            "synthetic": True,
        },
        "loan_application_status": {
            "application_ref": "synthetic-application-001",
            "status": "manual_review",
            "updated_at": FIXED_TIME,
            "synthetic": True,
        },
    }
    return data[tool_id]


def invoke(invocation: dict[str, Any], verified_tenant: str, scenario: str) -> dict[str, Any] | bytes:
    """授权和租户边界优先于场景注入与工具执行。"""
    if not invocation.get("authorization_decision_id"):
        return _failure(
            invocation,
            "denied",
            "TOOL_FORBIDDEN",
            "缺少工具授权决策",
        )
    if not verified_tenant or invocation.get("tenant_id") != verified_tenant:
        return _failure(
            invocation,
            "denied",
            "TENANT_MISMATCH",
            "请求租户与已验证租户不一致",
        )
    if scenario not in SCENARIOS:
        return _failure(
            invocation,
            "failed",
            "VALIDATION_FAILED",
            f"未知 Harness 场景: {scenario}",
        )
    tool_id = invocation.get("tool_id")
    if tool_id not in TOOLS:
        return _failure(
            invocation,
            "failed",
            "RESOURCE_NOT_FOUND",
            "工具未注册",
        )
    if scenario == "invalid_json":
        return b'{"invocation_id":"broken"'
    if scenario == "dependency_failure":
        return _failure(
            invocation,
            "failed",
            "DEPENDENCY_UNAVAILABLE",
            "固定依赖不可用场景",
            retryable=True,
        )
    if scenario == "timeout":
        time.sleep(0.075)
        return _failure(
            invocation,
            "timeout",
            "DEPENDENCY_TIMEOUT",
            "固定依赖超时场景",
            retryable=True,
        )
    if scenario == "denied":
        return _failure(
            invocation, "denied", "TOOL_FORBIDDEN", "固定工具拒绝场景"
        )
    if scenario == "approval_required":
        return _failure(
            invocation,
            "approval_required",
            "APPROVAL_REQUIRED",
            "该工具调用需要人工审批",
        )
    result = _result_base(invocation)
    result.update(
        {
            "status": "succeeded",
            "data": _tool_data(tool_id),
            "provenance": {
                "tool_id": tool_id,
                "tool_version": invocation.get("tool_version", "1.0.0"),
                "observed_at": FIXED_TIME,
                "fresh_until": "2026-07-28T08:05:00Z",
                "source_system": "agentforge-harness",
                "mock": True,
            },
        }
    )
    return result


class MockMCPHandler(BaseHarnessHandler):
    def do_GET(self) -> None:
        if self.path == "/healthz":
            self.write_json(200, {"status": "ok", "provider": "mock-mcp"})
            return
        if self.path == "/harness/scenarios":
            self.write_json(
                200, {"scenarios": list(SCENARIOS), "tools": list(TOOLS)}
            )
            return
        self.write_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path not in {"/v1/tools/invoke", "/mcp"}:
            self.write_json(404, {"error": "not_found"})
            return
        try:
            body = self.read_json_object()
            is_json_rpc = self.path == "/mcp"
            invocation = body.get("params") if is_json_rpc else body
            if not isinstance(invocation, dict):
                raise HarnessHTTPError(
                    400, "VALIDATION_FAILED", "工具调用必须是 JSON Object"
                )
            scenario = self.headers.get("X-Harness-Scenario", "success")
            result = invoke(
                invocation, self.headers.get("X-Tenant-ID", ""), scenario
            )
            if isinstance(result, bytes):
                self.write_raw_json(200, result)
                return
            if is_json_rpc:
                result = {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": result,
                }
            self.write_json(200, result)
        except HarnessHTTPError as exc:
            self.write_json(
                exc.status,
                {"error": _error("0" * 32, exc.code, exc.message)},
            )


def make_server(host: str = "127.0.0.1", port: int = 18082):
    return create_server(MockMCPHandler, host, port)
