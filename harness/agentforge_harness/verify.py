"""Fixture、场景目录与回放的统一离线验证。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .fake_llm import SCENARIOS as LLM_SCENARIOS
from .mock_mcp import SCENARIOS as MCP_SCENARIOS
from .replay import replay_all


HARNESS_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = HARNESS_ROOT / "fixtures"
REQUIRED_KINDS = {
    "text_pdf",
    "scanned_pdf",
    "png",
    "jpeg",
    "table",
    "channel_messages",
    "golden_annotations",
    "golden_questions",
    "security",
}
TRACEABILITY_FIELDS = {
    "document_id",
    "document_version",
    "page_number",
    "bounding_box",
    "content_type",
    "extractor_model_version",
    "source_object_key",
}


class VerifyError(RuntimeError):
    pass


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerifyError(f"JSON 无法解析: {path.relative_to(HARNESS_ROOT)}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_fixtures(root: Path = FIXTURE_ROOT) -> int:
    catalog_path = root / "catalog.json"
    catalog = _load_json(catalog_path)
    entries = catalog.get("fixtures") if isinstance(catalog, dict) else None
    if not isinstance(entries, list) or not entries:
        raise VerifyError("Fixture catalog 缺少 fixtures")
    kinds: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise VerifyError("Fixture catalog 条目必须是 Object")
        relative = entry.get("path")
        expected_hash = entry.get("sha256")
        kind = entry.get("kind")
        if not isinstance(relative, str) or not isinstance(expected_hash, str):
            raise VerifyError("Fixture catalog 条目缺少 path 或 sha256")
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise VerifyError(f"Fixture 路径越界: {relative}") from exc
        if not path.is_file() or path.is_symlink():
            raise VerifyError(f"Fixture 不存在或是符号链接: {relative}")
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            raise VerifyError(
                f"Fixture 哈希不一致: {relative}: expected={expected_hash}, actual={actual_hash}"
            )
        kinds.add(kind)
        data = path.read_bytes()[:16]
        if kind in {"text_pdf", "scanned_pdf"} and not data.startswith(b"%PDF-"):
            raise VerifyError(f"PDF 魔数无效: {relative}")
        if kind == "png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise VerifyError(f"PNG 魔数无效: {relative}")
        if kind == "jpeg":
            complete = path.read_bytes()
            if not complete.startswith(b"\xff\xd8") or b"Exif\x00\x00" in complete:
                raise VerifyError(f"JPEG 无效或仍包含 EXIF: {relative}")
        if kind == "security" and not entry.get("expected_rejection"):
            raise VerifyError(f"安全样例缺少 expected_rejection: {relative}")
    missing = REQUIRED_KINDS - kinds
    if missing:
        raise VerifyError(f"Fixture 类型覆盖不完整: {sorted(missing)}")

    annotations = _load_json(root / "annotations" / "document-golden.json")
    regions = annotations.get("regions") if isinstance(annotations, dict) else None
    if not isinstance(regions, list) or not regions:
        raise VerifyError("黄金标注缺少 regions")
    for index, region in enumerate(regions):
        if not isinstance(region, dict) or not TRACEABILITY_FIELDS <= region.keys():
            raise VerifyError(f"黄金标注 region[{index}] 缺少可追溯字段")

    channels: set[str] = set()
    message_path = root / "messages" / "channel-messages.jsonl"
    for line_number, line in enumerate(
        message_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise VerifyError(f"渠道消息第 {line_number} 行无效") from exc
        channel = message.get("channel")
        if channel not in {"app", "h5"}:
            raise VerifyError(f"渠道消息第 {line_number} 行包含未授权渠道")
        if not message.get("tenant_id"):
            raise VerifyError(f"渠道消息第 {line_number} 行缺少 tenant_id")
        channels.add(channel)
    if channels != {"app", "h5"}:
        raise VerifyError("渠道样例必须同时覆盖 APP 与 H5")
    return len(entries)


def verify_all() -> dict[str, int]:
    if len(LLM_SCENARIOS) != 12 or len(set(LLM_SCENARIOS)) != 12:
        raise VerifyError("Fake LLM 场景必须为 12 个且不能重复")
    if len(MCP_SCENARIOS) != 6 or len(set(MCP_SCENARIOS)) != 6:
        raise VerifyError("Mock MCP 场景必须为 6 个且不能重复")
    return {
        "fake_llm_scenarios": len(LLM_SCENARIOS),
        "mock_mcp_scenarios": len(MCP_SCENARIOS),
        "fixtures": verify_fixtures(),
        "replay_scenarios": replay_all(),
    }
