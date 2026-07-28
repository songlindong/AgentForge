"""与内部 LLM Gateway 契约对齐的确定性 OpenAI 风格 Fake。"""

from __future__ import annotations

from http import HTTPStatus
import json
import time
from typing import Any

from .common import (
    BaseHarnessHandler,
    FIXED_CREATED,
    HarnessHTTPError,
    compact_json,
    create_server,
)


SCENARIOS = (
    "success",
    "vision_success",
    "json_schema",
    "tool_call",
    "sse",
    "delay",
    "rate_limit",
    "server_error",
    "unavailable",
    "timeout",
    "stream_disconnect",
    "invalid_json",
)
REQUIRED_HEADERS = (
    "X-Tenant-ID",
    "X-Trace-ID",
    "X-Run-ID",
    "X-Step-ID",
    "Idempotency-Key",
)


def _error_body(
    trace_id: str,
    code: str,
    message: str,
    error_type: str,
    *,
    retryable: bool = False,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "message": message,
        "type": error_type,
        "param": None,
        "code": code,
        "retryable": retryable,
        "trace_id": trace_id or "0" * 32,
    }
    if retryable:
        error["retry_after_ms"] = 100
    return {"error": error}


def _content_for(scenario: str) -> str:
    if scenario == "vision_success":
        return "图片中的虚构合同条款为提前还款需提前三个工作日申请。[合成合同第1页区域A]"
    if scenario == "json_schema":
        return json.dumps(
            {"answer": "该信息来自固定测试响应", "grounded": True},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return "这是固定的金融客服测试响应；具体利率和审批状态必须通过受控工具查询。"


def _completion(model: str, scenario: str) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": _content_for(scenario)}
    finish_reason = "stop"
    if scenario == "tool_call":
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-loan-rate-001",
                    "type": "function",
                    "function": {
                        "name": "loan_rate_lookup",
                        "arguments": "{\"product_id\":\"synthetic-product-a\"}",
                    },
                }
            ],
        }
        finish_reason = "tool_calls"
    return {
        "id": "chatcmpl-harness-001",
        "object": "chat.completion",
        "created": FIXED_CREATED,
        "model": model,
        "choices": [
            {"index": 0, "message": message, "finish_reason": finish_reason}
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 18,
            "total_tokens": 30,
            "cost_minor_units": 0,
            "currency": "CNY",
        },
    }


def _image_urls(body: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    messages = body.get("messages")
    if not isinstance(messages, list):
        return urls
    for message in messages:
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            continue
        for part in message["content"]:
            if not isinstance(part, dict) or part.get("type") != "image_url":
                continue
            image = part.get("image_url")
            if isinstance(image, dict) and isinstance(image.get("url"), str):
                urls.append(image["url"])
    return urls


class FakeLLMHandler(BaseHarnessHandler):
    def do_GET(self) -> None:
        if self.path == "/healthz":
            self.write_json(200, {"status": "ok", "provider": "fake-llm"})
            return
        if self.path == "/harness/scenarios":
            self.write_json(200, {"scenarios": list(SCENARIOS)})
            return
        self.write_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.write_json(404, {"error": "not_found"})
            return
        trace_id = self.headers.get("X-Trace-ID", "")
        try:
            missing = [name for name in REQUIRED_HEADERS if not self.headers.get(name)]
            if missing:
                raise HarnessHTTPError(
                    400,
                    "VALIDATION_FAILED",
                    "缺少必需 Header: " + ", ".join(missing),
                )
            body = self.read_json_object()
            if not isinstance(body.get("model"), str) or not isinstance(
                body.get("messages"), list
            ) or not body["messages"]:
                raise HarnessHTTPError(
                    400, "VALIDATION_FAILED", "model 和非空 messages 为必填项"
                )
            for url in _image_urls(body):
                if not url.startswith("agentforge://objects/"):
                    raise HarnessHTTPError(
                        422,
                        "VALIDATION_FAILED",
                        "图片只允许 agentforge://objects/ 受控引用",
                    )
            scenario = self.headers.get("X-Harness-Scenario", "success")
            if scenario not in SCENARIOS:
                raise HarnessHTTPError(
                    400, "VALIDATION_FAILED", f"未知 Harness 场景: {scenario}"
                )
            self._respond(body, scenario, trace_id)
        except HarnessHTTPError as exc:
            error_type = (
                "invalid_request_error"
                if exc.status < 500
                else "server_error"
            )
            self.write_json(
                exc.status,
                _error_body(trace_id, exc.code, exc.message, error_type),
                headers={"X-Trace-ID": trace_id or "0" * 32},
            )

    def _respond(self, body: dict[str, Any], scenario: str, trace_id: str) -> None:
        if scenario == "delay":
            time.sleep(0.075)
        failures = {
            "rate_limit": (
                HTTPStatus.TOO_MANY_REQUESTS,
                "RATE_LIMITED",
                "固定限流场景",
                "rate_limit_error",
                True,
            ),
            "server_error": (
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "固定服务错误场景",
                "server_error",
                False,
            ),
            "unavailable": (
                HTTPStatus.SERVICE_UNAVAILABLE,
                "DEPENDENCY_UNAVAILABLE",
                "固定 Provider 不可用场景",
                "server_error",
                True,
            ),
            "timeout": (
                HTTPStatus.GATEWAY_TIMEOUT,
                "DEADLINE_EXCEEDED",
                "固定请求超时场景",
                "timeout_error",
                False,
            ),
        }
        if scenario in failures:
            status, code, message, error_type, retryable = failures[scenario]
            headers = {"X-Trace-ID": trace_id}
            if retryable:
                headers["Retry-After"] = "1"
            self.write_json(
                int(status),
                _error_body(
                    trace_id,
                    code,
                    message,
                    error_type,
                    retryable=retryable,
                ),
                headers=headers,
            )
            return
        if scenario == "invalid_json":
            self.write_raw_json(200, b'{"id":"chatcmpl-broken"')
            return
        if scenario in {"sse", "stream_disconnect"} or body.get("stream") is True:
            self._write_stream(body["model"], scenario, trace_id)
            return
        self.write_json(
            200,
            _completion(body["model"], scenario),
            headers={
                "X-Trace-ID": trace_id,
                "X-Provider-ID": "fake-provider",
                "X-Model-ID": body["model"],
            },
        )

    def _write_stream(self, model: str, scenario: str, trace_id: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_header("X-Trace-ID", trace_id)
        self.send_header("X-Provider-ID", "fake-provider")
        self.send_header("X-Model-ID", model)
        self.end_headers()
        chunks = [
            {
                "id": "chatcmpl-harness-stream-001",
                "object": "chat.completion.chunk",
                "created": FIXED_CREATED,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "固定流式响应"},
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "chatcmpl-harness-stream-001",
                "object": "chat.completion.chunk",
                "created": FIXED_CREATED,
                "model": model,
                "choices": [
                    {"index": 0, "delta": {}, "finish_reason": "stop"}
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 4,
                    "total_tokens": 16,
                    "cost_minor_units": 0,
                    "currency": "CNY",
                },
            },
        ]
        limit = 1 if scenario == "stream_disconnect" else len(chunks)
        try:
            for chunk in chunks[:limit]:
                self.wfile.write(b"data: " + compact_json(chunk) + b"\n\n")
                self.wfile.flush()
            if scenario != "stream_disconnect":
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True


def make_server(host: str = "127.0.0.1", port: int = 18081):
    return create_server(FakeLLMHandler, host, port)
