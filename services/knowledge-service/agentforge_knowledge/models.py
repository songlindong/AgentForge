from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from agentforge_document_processor.models import Chunk, ParsedDocument, SafeFile


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IngestionState(StrEnum):
    RECEIVED = "received"
    SCANNING = "scanning"
    REJECTED = "rejected"
    ACCEPTED = "accepted"
    STORED = "stored"
    PARSING = "parsing"
    PARSED = "parsed"
    CHUNKING = "chunking"
    CHUNKED = "chunked"
    INDEXING = "indexing"
    FAILED = "failed"
    INDEX_READY = "index_ready"
    PUBLISHED = "published"


ALLOWED_TRANSITIONS: dict[IngestionState, frozenset[IngestionState]] = {
    IngestionState.RECEIVED: frozenset({IngestionState.SCANNING}),
    IngestionState.SCANNING: frozenset(
        {IngestionState.REJECTED, IngestionState.ACCEPTED, IngestionState.FAILED}
    ),
    IngestionState.ACCEPTED: frozenset(
        {IngestionState.STORED, IngestionState.FAILED}
    ),
    IngestionState.STORED: frozenset(
        {IngestionState.PARSING, IngestionState.FAILED}
    ),
    IngestionState.PARSING: frozenset(
        {IngestionState.PARSED, IngestionState.FAILED}
    ),
    IngestionState.PARSED: frozenset(
        {IngestionState.CHUNKING, IngestionState.FAILED}
    ),
    IngestionState.CHUNKING: frozenset(
        {IngestionState.CHUNKED, IngestionState.FAILED}
    ),
    IngestionState.CHUNKED: frozenset(
        {IngestionState.INDEXING, IngestionState.FAILED}
    ),
    IngestionState.INDEXING: frozenset(
        {IngestionState.FAILED, IngestionState.INDEX_READY}
    ),
    IngestionState.FAILED: frozenset(
        {
            IngestionState.SCANNING,
            IngestionState.STORED,
            IngestionState.PARSING,
            IngestionState.CHUNKING,
            IngestionState.INDEXING,
        }
    ),
    IngestionState.INDEX_READY: frozenset({IngestionState.PUBLISHED}),
    IngestionState.REJECTED: frozenset(),
    IngestionState.PUBLISHED: frozenset(),
}


@dataclass(frozen=True)
class IngestionRequest:
    tenant_id: str
    knowledge_base_id: str
    filename: str
    declared_media_type: str
    data: bytes
    idempotency_key: str
    trace_id: str
    sensitive_content_policy: str = "reject"


@dataclass
class StageCounts:
    pages: int = 0
    regions: int = 0
    tables: int = 0
    chunks: int = 0
    bm25_indexed: int = 0
    vectors_indexed: int = 0


@dataclass
class IngestionJob:
    tenant_id: str
    job_id: str
    knowledge_base_id: str
    document_id: str
    document_version: int
    request_digest: str
    idempotency_key: str
    trace_id: str
    state: IngestionState = IngestionState.RECEIVED
    attempt: int = 1
    max_attempts: int = 3
    retryable: bool = False
    error_code: str | None = None
    error_summary: str | None = None
    failure_stage: IngestionState | None = None
    knowledge_version: str | None = None
    counts: StageCounts = field(default_factory=StageCounts)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class StoredDocument:
    tenant_id: str
    knowledge_base_id: str
    document_id: str
    document_version: int
    object_key: str
    safe_file: SafeFile


@dataclass(frozen=True)
class IndexedChunk:
    tenant_id: str
    knowledge_base_id: str
    document_id: str
    document_version: int
    source_object_key: str
    chunk: Chunk
    extractor_version: str
    embedding_model_id: str
    embedding_model_version: str
    embedding: tuple[float, ...]
    test_model: bool


@dataclass(frozen=True)
class OutboxRecord:
    tenant_id: str
    event_id: str
    topic: str
    partition_key: str
    event_type: str
    idempotency_key: str
    trace_id: str
    data: dict[str, Any]
    created_at: datetime = field(default_factory=utc_now)
    published_at: datetime | None = None


@dataclass(frozen=True)
class DocumentArtifacts:
    document: StoredDocument
    parsed: ParsedDocument | None
    chunks: tuple[IndexedChunk, ...]
