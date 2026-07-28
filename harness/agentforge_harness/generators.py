"""固定 Seed、流式输出且不连接外部服务的数据生成器。"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
import hashlib
import json
from pathlib import Path
import random
import sys
from typing import Any, TextIO


MAX_GATEWAY_REQUESTS = 100_000
MAX_VECTORS = 1_000_000
MAX_DIMENSION = 4096
MAX_TENANTS = 10_000


def _identifier(prefix: str, seed: int, index: int, length: int = 16) -> str:
    digest = hashlib.sha256(f"{prefix}:{seed}:{index}".encode()).hexdigest()
    return f"{prefix}-{digest[:length]}"


def _trace_id(seed: int, index: int) -> str:
    return hashlib.sha256(f"trace:{seed}:{index}".encode()).hexdigest()[:32]


def _validate_common(count: int, tenant_count: int, maximum: int) -> None:
    if not 1 <= count <= maximum:
        raise ValueError(f"count 必须在 1..{maximum} 范围内")
    if not 1 <= tenant_count <= MAX_TENANTS:
        raise ValueError(f"tenant_count 必须在 1..{MAX_TENANTS} 范围内")


def gateway_records(
    count: int, seed: int, tenant_count: int = 2
) -> Iterator[dict[str, Any]]:
    _validate_common(count, tenant_count, MAX_GATEWAY_REQUESTS)
    patterns = ("text", "controlled_image", "tool_call", "sse", "cancel")
    for index in range(count):
        tenant_id = f"tenant-{index % tenant_count + 1:04d}"
        pattern = patterns[index % len(patterns)]
        content: str | list[dict[str, Any]] = "请说明合成贷款产品的适用条件"
        if pattern == "controlled_image":
            content = [
                {"type": "text", "text": "请解释截图中的合同条款"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"agentforge://objects/synthetic-image-{index:06d}",
                        "detail": "high",
                    },
                },
            ]
        body: dict[str, Any] = {
            "model": "fake-finance-model",
            "messages": [{"role": "user", "content": content}],
            "stream": pattern in {"sse", "cancel"},
            "temperature": 0,
            "max_tokens": 128,
            "user": hashlib.sha256(f"user:{seed}:{index}".encode()).hexdigest(),
        }
        if pattern == "tool_call":
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": "loan_rate_lookup",
                        "parameters": {
                            "type": "object",
                            "properties": {"product_id": {"type": "string"}},
                            "required": ["product_id"],
                        },
                        "strict": True,
                    },
                }
            ]
            body["tool_choice"] = "required"
        yield {
            "sequence": index,
            "pattern": pattern,
            "cancel_after_chunks": 1 if pattern == "cancel" else None,
            "headers": {
                "X-Tenant-ID": tenant_id,
                "X-Trace-ID": _trace_id(seed, index),
                "X-Run-ID": _identifier("run", seed, index),
                "X-Step-ID": _identifier("step", seed, index),
                "Idempotency-Key": _identifier("idem", seed, index),
                "X-Harness-Scenario": "sse" if pattern in {"sse", "cancel"} else "success",
            },
            "body": body,
        }


def vector_records(
    count: int,
    dimension: int,
    seed: int,
    tenant_count: int = 2,
) -> Iterator[dict[str, Any]]:
    _validate_common(count, tenant_count, MAX_VECTORS)
    if not 1 <= dimension <= MAX_DIMENSION:
        raise ValueError(f"dimension 必须在 1..{MAX_DIMENSION} 范围内")
    randomizer = random.Random(seed)
    content_types = ("text", "ocr_text", "table", "image_region")
    for index in range(count):
        tenant_id = f"tenant-{index % tenant_count + 1:04d}"
        yield {
            "vector_id": _identifier("vec", seed, index, 24),
            "tenant_id": tenant_id,
            "document_id": f"synthetic-document-{index // 8:08d}",
            "document_version": "1.0.0",
            "content_type": content_types[index % len(content_types)],
            "page_number": index % 12 + 1,
            "vector": [round(randomizer.uniform(-1.0, 1.0), 7) for _ in range(dimension)],
        }


def _write_lines(records: Iterable[dict[str, Any]], stream: TextIO) -> int:
    count = 0
    for record in records:
        stream.write(
            json.dumps(
                record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        )
        stream.write("\n")
        count += 1
    return count


def write_jsonl(records: Iterable[dict[str, Any]], output: Path | None) -> int:
    if output is None:
        return _write_lines(records, sys.stdout)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            count = _write_lines(records, stream)
        temporary.replace(output)
        return count
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
