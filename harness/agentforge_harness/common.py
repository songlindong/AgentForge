"""Harness 服务共用的安全 HTTP 与序列化工具。"""

from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from typing import Any


FIXED_TIME = "2026-07-28T08:00:00Z"
FIXED_CREATED = 1785225600
MAX_BODY_BYTES = 1024 * 1024


@dataclass(slots=True)
class HarnessHTTPError(Exception):
    status: int
    code: str
    message: str


def ensure_loopback(host: str) -> None:
    """拒绝把无生产鉴权的 Harness 监听到外部网卡。"""
    if host.lower() == "localhost":
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("Harness host 必须是明确的 Loopback 地址") from exc
    if not address.is_loopback:
        raise ValueError("Harness 只能监听 Loopback 地址")


def compact_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


class HarnessHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class BaseHarnessHandler(BaseHTTPRequestHandler):
    """不记录 Header 或 Body，避免凭证和输入原文进入日志。"""

    server_version = "AgentForgeHarness/0.1"
    sys_version = ""

    def log_message(self, format: str, *args: object) -> None:
        return

    def read_json_object(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise HarnessHTTPError(400, "VALIDATION_FAILED", "缺少 Content-Length")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise HarnessHTTPError(
                400, "VALIDATION_FAILED", "Content-Length 无效"
            ) from exc
        if length <= 0:
            raise HarnessHTTPError(400, "VALIDATION_FAILED", "请求 Body 不能为空")
        if length > MAX_BODY_BYTES:
            raise HarnessHTTPError(413, "PAYLOAD_TOO_LARGE", "请求 Body 超过 1 MiB")
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HarnessHTTPError(400, "VALIDATION_FAILED", "请求 Body 不是有效 JSON") from exc
        if not isinstance(value, dict):
            raise HarnessHTTPError(400, "VALIDATION_FAILED", "请求 Body 必须是 JSON Object")
        return value

    def write_json(
        self,
        status: int,
        value: Any,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        payload = compact_json(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        for name, content in (headers or {}).items():
            self.send_header(name, content)
        self.end_headers()
        self.wfile.write(payload)

    def write_raw_json(self, status: int, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)


def create_server(
    handler: type[BaseHTTPRequestHandler], host: str, port: int
) -> HarnessHTTPServer:
    ensure_loopback(host)
    if not 0 <= port <= 65535:
        raise ValueError("端口必须在 0..65535 范围内")
    return HarnessHTTPServer((host, port), handler)


def serve(server: HarnessHTTPServer, label: str) -> None:
    host, port = server.server_address[:2]
    print(f"{label} 正在监听 http://{host}:{port}；仅供本机测试")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
