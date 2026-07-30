from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from agentforge_document_processor.models import ParsedDocument

from .models import IndexedChunk, IngestionJob, OutboxRecord, StoredDocument


class KnowledgeRepositoryPort(Protocol):
    def create_or_get_job(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        filename: str,
        request_digest: str,
        idempotency_key: str,
        sensitive_content_policy: str,
        trace_id: str,
    ) -> tuple[IngestionJob, bool]: ...

    def get_job(self, tenant_id: str, job_id: str) -> IngestionJob: ...

    def transition(
        self,
        tenant_id: str,
        job_id: str,
        target_state: str,
        *,
        retryable: bool = False,
        error_code: str | None = None,
        error_summary: str | None = None,
        failure_stage: str | None = None,
    ) -> IngestionJob: ...

    def increment_attempt(self, tenant_id: str, job_id: str) -> IngestionJob: ...

    def begin_retry(
        self,
        *,
        tenant_id: str,
        job_id: str,
        idempotency_key: str,
        target_state: str,
    ) -> tuple[IngestionJob, bool]: ...

    def save_document(self, document: StoredDocument) -> None: ...

    def get_document(
        self,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> StoredDocument: ...

    def save_parsed(
        self,
        *,
        tenant_id: str,
        document_id: str,
        document_version: int,
        parsed: ParsedDocument,
    ) -> None: ...

    def get_parsed(
        self,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> ParsedDocument: ...

    def save_chunks(
        self,
        *,
        tenant_id: str,
        document_id: str,
        document_version: int,
        chunks: Sequence[IndexedChunk],
    ) -> None: ...

    def get_chunks(
        self,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> tuple[IndexedChunk, ...]: ...

    def set_index_counts(
        self,
        *,
        tenant_id: str,
        job_id: str,
        bm25_indexed: int,
        vectors_indexed: int,
    ) -> IngestionJob: ...

    def publish_version(self, tenant_id: str, job_id: str) -> IngestionJob: ...

    def claim_inbox(
        self,
        *,
        tenant_id: str,
        consumer_name: str,
        event_id: str,
    ) -> bool: ...

    def pending_outbox(
        self, tenant_id: str, *, limit: int = 100
    ) -> tuple[OutboxRecord, ...]: ...

    def mark_outbox_published(self, tenant_id: str, event_id: str) -> None: ...


class ObjectStorePort(Protocol):
    def put_if_absent(
        self,
        *,
        tenant_id: str,
        object_key: str,
        data: bytes,
        media_type: str,
        sha256_hex: str,
    ) -> None: ...

    def get(self, *, tenant_id: str, object_key: str) -> bytes: ...


class KeywordIndexPort(Protocol):
    index_name: str
    index_version: str

    def upsert(self, *, tenant_id: str, chunks: Sequence[IndexedChunk]) -> int: ...

    def count_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> int: ...


class VectorIndexPort(Protocol):
    collection_name: str
    index_version: str

    def upsert(self, *, tenant_id: str, chunks: Sequence[IndexedChunk]) -> int: ...

    def count_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> int: ...


class EventPublisherPort(Protocol):
    def publish(self, record: OutboxRecord) -> None: ...
