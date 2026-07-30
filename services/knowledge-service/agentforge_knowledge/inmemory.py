from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from threading import RLock

from agentforge_document_processor.models import ParsedDocument

from .errors import KnowledgeError
from .event_payloads import (
    document_chunked,
    document_parsed,
    document_uploaded,
    embedding_requested,
    knowledge_version_published,
)
from .models import (
    ALLOWED_TRANSITIONS,
    IndexedChunk,
    IngestionJob,
    IngestionState,
    OutboxRecord,
    StoredDocument,
    utc_now,
)


STATE_TOPICS = {
    IngestionState.STORED: ("document.uploaded", "document.uploaded"),
    IngestionState.PARSED: ("document.parsed", "document.parsed"),
    IngestionState.CHUNKED: ("document.chunked", "document.chunked"),
    IngestionState.INDEXING: ("embedding.requested", "embedding.requested"),
    IngestionState.PUBLISHED: (
        "knowledge.version.published",
        "knowledge.version.published",
    ),
}


def _identifier(prefix: str, *parts: str) -> str:
    material = "|".join(parts).encode("utf-8")
    return f"{prefix}_{sha256(material).hexdigest()[:32]}"


class InMemoryKnowledgeRepository:
    def __init__(
        self,
        *,
        bm25_index_version: str = "1.0.0",
        vector_index_version: str = "1.0.0",
    ) -> None:
        self._lock = RLock()
        self._jobs: dict[tuple[str, str], IngestionJob] = {}
        self._idempotency: dict[tuple[str, str], tuple[str, str]] = {}
        self._versions: dict[tuple[str, str, str], dict[str, int]] = {}
        self._documents: dict[tuple[str, str, int], StoredDocument] = {}
        self._parsed: dict[tuple[str, str, int], ParsedDocument] = {}
        self._chunks: dict[tuple[str, str, int], dict[str, IndexedChunk]] = {}
        self._inbox: set[tuple[str, str, str]] = set()
        self._commands: dict[tuple[str, str, str], int] = {}
        self._outbox: dict[tuple[str, str], OutboxRecord] = {}
        self._published: dict[tuple[str, str], int] = {}
        self.bm25_index_version = bm25_index_version
        self.vector_index_version = vector_index_version

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
    ) -> tuple[IngestionJob, bool]:
        with self._lock:
            idempotency_scope = (tenant_id, idempotency_key)
            existing = self._idempotency.get(idempotency_scope)
            if existing is not None:
                existing_digest, job_id = existing
                if existing_digest != request_digest:
                    raise KnowledgeError(
                        "IDEMPOTENCY_CONFLICT",
                        "idempotency key is bound to another request",
                    )
                return deepcopy(self._jobs[(tenant_id, job_id)]), False

            logical_scope = (tenant_id, knowledge_base_id, filename.lower())
            digest_versions = self._versions.setdefault(logical_scope, {})
            if request_digest in digest_versions:
                document_version = digest_versions[request_digest]
            else:
                document_version = max(digest_versions.values(), default=0) + 1
                digest_versions[request_digest] = document_version

            document_id = _identifier(
                "doc", tenant_id, knowledge_base_id, filename.lower()
            )
            job_id = _identifier("job", tenant_id, idempotency_key)
            job = IngestionJob(
                tenant_id=tenant_id,
                job_id=job_id,
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
                document_version=document_version,
                request_digest=request_digest,
                idempotency_key=idempotency_key,
                sensitive_content_policy=sensitive_content_policy,
                trace_id=trace_id,
            )
            self._jobs[(tenant_id, job_id)] = job
            self._idempotency[idempotency_scope] = (request_digest, job_id)
            return deepcopy(job), True

    def get_job(self, tenant_id: str, job_id: str) -> IngestionJob:
        with self._lock:
            try:
                return deepcopy(self._jobs[(tenant_id, job_id)])
            except KeyError as exc:
                raise KnowledgeError("RESOURCE_NOT_FOUND", "job is not visible") from exc

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
    ) -> IngestionJob:
        with self._lock:
            job = self._mutable_job(tenant_id, job_id)
            target = IngestionState(target_state)
            if target not in ALLOWED_TRANSITIONS[job.state]:
                raise KnowledgeError(
                    "INVALID_STATE_TRANSITION",
                    f"cannot transition from {job.state} to {target}",
                )
            previous = job.state
            job.state = target
            job.updated_at = utc_now()
            job.retryable = retryable
            job.error_code = error_code
            job.error_summary = error_summary
            job.failure_stage = (
                IngestionState(failure_stage)
                if target == IngestionState.FAILED and failure_stage
                else None
            )
            if target not in {IngestionState.FAILED, IngestionState.REJECTED}:
                job.error_code = None
                job.error_summary = None
            self._append_state_event(job, previous)
            return deepcopy(job)

    def increment_attempt(self, tenant_id: str, job_id: str) -> IngestionJob:
        with self._lock:
            job = self._mutable_job(tenant_id, job_id)
            if not job.retryable or job.attempt >= job.max_attempts:
                raise KnowledgeError(
                    "INVALID_STATE_TRANSITION",
                    "job has no retry budget",
                )
            job.attempt += 1
            job.updated_at = utc_now()
            return deepcopy(job)

    def begin_retry(
        self,
        *,
        tenant_id: str,
        job_id: str,
        idempotency_key: str,
        target_state: str,
    ) -> tuple[IngestionJob, bool]:
        with self._lock:
            command_key = (tenant_id, job_id, idempotency_key)
            if command_key in self._commands:
                return deepcopy(self._mutable_job(tenant_id, job_id)), False
            job = self._mutable_job(tenant_id, job_id)
            target = IngestionState(target_state)
            if (
                job.state != IngestionState.FAILED
                or not job.retryable
                or job.attempt >= job.max_attempts
                or target not in ALLOWED_TRANSITIONS[IngestionState.FAILED]
            ):
                raise KnowledgeError(
                    "INVALID_STATE_TRANSITION",
                    "job has no legal retry transition",
                )
            previous = job.state
            job.attempt += 1
            job.state = target
            job.retryable = False
            job.error_code = None
            job.error_summary = None
            job.failure_stage = None
            job.updated_at = utc_now()
            self._commands[command_key] = job.attempt
            self._append_state_event(job, previous)
            return deepcopy(job), True

    def save_document(self, document: StoredDocument) -> None:
        with self._lock:
            self._documents[
                (document.tenant_id, document.document_id, document.document_version)
            ] = document

    def get_document(
        self,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> StoredDocument:
        with self._lock:
            try:
                return self._documents[(tenant_id, document_id, document_version)]
            except KeyError as exc:
                raise KnowledgeError(
                    "RESOURCE_NOT_FOUND", "document is not visible"
                ) from exc

    def save_parsed(
        self,
        *,
        tenant_id: str,
        document_id: str,
        document_version: int,
        parsed: ParsedDocument,
    ) -> None:
        with self._lock:
            self._parsed[(tenant_id, document_id, document_version)] = parsed
            for job in self._jobs.values():
                if (
                    job.tenant_id == tenant_id
                    and job.document_id == document_id
                    and job.document_version == document_version
                ):
                    job.counts.pages = parsed.page_count
                    job.counts.regions = len(parsed.regions)
                    job.counts.tables = len(parsed.tables)

    def get_parsed(
        self,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> ParsedDocument:
        with self._lock:
            try:
                return self._parsed[(tenant_id, document_id, document_version)]
            except KeyError as exc:
                raise KnowledgeError(
                    "RESOURCE_NOT_FOUND", "parsed document is not visible"
                ) from exc

    def save_chunks(
        self,
        *,
        tenant_id: str,
        document_id: str,
        document_version: int,
        chunks: tuple[IndexedChunk, ...] | list[IndexedChunk],
    ) -> None:
        with self._lock:
            scope = (tenant_id, document_id, document_version)
            target = self._chunks.setdefault(scope, {})
            for chunk in chunks:
                if chunk.tenant_id != tenant_id:
                    raise KnowledgeError("TENANT_MISMATCH", "chunk tenant mismatch")
                target[chunk.chunk.chunk_uid] = chunk
            for job in self._jobs.values():
                if (
                    job.tenant_id == tenant_id
                    and job.document_id == document_id
                    and job.document_version == document_version
                ):
                    job.counts.chunks = len(target)

    def get_chunks(
        self,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> tuple[IndexedChunk, ...]:
        with self._lock:
            values = self._chunks.get((tenant_id, document_id, document_version), {})
            return tuple(
                deepcopy(value)
                for value in sorted(values.values(), key=lambda item: item.chunk.ordinal)
            )

    def set_index_counts(
        self,
        *,
        tenant_id: str,
        job_id: str,
        bm25_indexed: int,
        vectors_indexed: int,
    ) -> IngestionJob:
        with self._lock:
            job = self._mutable_job(tenant_id, job_id)
            job.counts.bm25_indexed = bm25_indexed
            job.counts.vectors_indexed = vectors_indexed
            job.updated_at = utc_now()
            return deepcopy(job)

    def publish_version(self, tenant_id: str, job_id: str) -> IngestionJob:
        with self._lock:
            job = self._mutable_job(tenant_id, job_id)
            if job.state != IngestionState.INDEX_READY:
                raise KnowledgeError(
                    "INVALID_STATE_TRANSITION", "indexes are not ready"
                )
            scope = (tenant_id, job.knowledge_base_id)
            sequence = self._published.get(scope, 0)
            job.knowledge_version = f"1.0.{sequence}"
            self._published[scope] = sequence + 1
            return self.transition(tenant_id, job_id, IngestionState.PUBLISHED)

    def claim_inbox(
        self,
        *,
        tenant_id: str,
        consumer_name: str,
        event_id: str,
    ) -> bool:
        with self._lock:
            key = (tenant_id, consumer_name, event_id)
            if key in self._inbox:
                return False
            self._inbox.add(key)
            return True

    def pending_outbox(
        self, tenant_id: str, *, limit: int = 100
    ) -> tuple[OutboxRecord, ...]:
        with self._lock:
            return tuple(
                deepcopy(record)
                for record in self._outbox.values()
                if record.tenant_id == tenant_id and record.published_at is None
            )[:limit]

    def mark_outbox_published(self, tenant_id: str, event_id: str) -> None:
        with self._lock:
            key = (tenant_id, event_id)
            try:
                self._outbox[key] = replace(
                    self._outbox[key], published_at=utc_now()
                )
            except KeyError as exc:
                raise KnowledgeError(
                    "RESOURCE_NOT_FOUND", "outbox record is not visible"
                ) from exc

    def _mutable_job(self, tenant_id: str, job_id: str) -> IngestionJob:
        try:
            return self._jobs[(tenant_id, job_id)]
        except KeyError as exc:
            raise KnowledgeError("RESOURCE_NOT_FOUND", "job is not visible") from exc

    def _append_state_event(
        self,
        job: IngestionJob,
        previous: IngestionState,
    ) -> None:
        topic_event = STATE_TOPICS.get(job.state)
        if topic_event is None:
            return
        topic, event_type = topic_event
        document_key = (job.tenant_id, job.document_id, job.document_version)
        if job.state == IngestionState.STORED:
            payload = document_uploaded(job, self._documents[document_key])
        elif job.state == IngestionState.PARSED:
            parsed = self._parsed[document_key]
            payload = document_parsed(
                job,
                self._documents[document_key],
                regions=parsed.regions,
                extractor_version=parsed.extractor_version,
                page_count=parsed.page_count,
            )
        elif job.state == IngestionState.CHUNKED:
            chunks = self.get_chunks(*document_key)
            payload = document_chunked(
                job,
                self._documents[document_key],
                chunks,
            )
        elif job.state == IngestionState.INDEXING:
            chunks = self.get_chunks(*document_key)
            payload = embedding_requested(
                job,
                self._documents[document_key],
                chunks,
            )
        else:
            payload = knowledge_version_published(
                job,
                bm25_index_version=self.bm25_index_version,
                vector_index_version=self.vector_index_version,
            )
        event_id = _identifier(
            "evt",
            job.tenant_id,
            job.job_id,
            job.state,
            str(job.attempt),
        )
        record = OutboxRecord(
            tenant_id=job.tenant_id,
            event_id=event_id,
            topic=topic,
            partition_key=_identifier(
                "partition",
                job.tenant_id,
                (
                    job.knowledge_base_id
                    if job.state == IngestionState.PUBLISHED
                    else job.document_id
                ),
            ),
            event_type=event_type,
            idempotency_key=f"{job.job_id}:{job.state}:{job.attempt}",
            correlation_id=job.job_id,
            attempt=job.attempt,
            trace_id=job.trace_id,
            data=payload,
        )
        self._outbox[(job.tenant_id, event_id)] = record


class InMemoryObjectStore:
    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], tuple[bytes, str, str]] = {}

    def put_if_absent(
        self,
        *,
        tenant_id: str,
        object_key: str,
        data: bytes,
        media_type: str,
        sha256_hex: str,
    ) -> None:
        if not object_key.startswith(f"tenants/{tenant_id}/"):
            raise KnowledgeError("TENANT_MISMATCH", "object key tenant mismatch")
        key = (tenant_id, object_key)
        existing = self._objects.get(key)
        candidate = (data, media_type, sha256_hex)
        if existing is not None and existing != candidate:
            raise KnowledgeError("VERSION_CONFLICT", "object content differs")
        self._objects[key] = candidate

    def get(self, *, tenant_id: str, object_key: str) -> bytes:
        try:
            return self._objects[(tenant_id, object_key)][0]
        except KeyError as exc:
            raise KnowledgeError("RESOURCE_NOT_FOUND", "object is not visible") from exc


class InMemoryKeywordIndex:
    index_name = "agentforge-knowledge-chunks-v1"
    index_version = "1.0.0"

    def __init__(self) -> None:
        self._chunks: dict[tuple[str, str], IndexedChunk] = {}

    def upsert(
        self,
        *,
        tenant_id: str,
        chunks: tuple[IndexedChunk, ...] | list[IndexedChunk],
    ) -> int:
        for chunk in chunks:
            if chunk.tenant_id != tenant_id:
                raise KnowledgeError("TENANT_MISMATCH", "keyword chunk tenant mismatch")
            self._chunks[(tenant_id, chunk.chunk.chunk_uid)] = chunk
        return len(chunks)

    def count_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> int:
        return sum(
            1
            for (scope_tenant, _), chunk in self._chunks.items()
            if scope_tenant == tenant_id
            and chunk.document_id == document_id
            and chunk.document_version == document_version
        )


class InMemoryVectorIndex:
    collection_name = "agentforge_knowledge_chunks_v1"
    index_version = "1.0.0"

    def __init__(self, *, failures_remaining: int = 0) -> None:
        self._chunks: dict[tuple[str, str], IndexedChunk] = {}
        self.failures_remaining = failures_remaining

    def upsert(
        self,
        *,
        tenant_id: str,
        chunks: tuple[IndexedChunk, ...] | list[IndexedChunk],
    ) -> int:
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE",
                "vector index fault injection",
                retryable=True,
            )
        for chunk in chunks:
            if chunk.tenant_id != tenant_id:
                raise KnowledgeError("TENANT_MISMATCH", "vector chunk tenant mismatch")
            self._chunks[(tenant_id, chunk.chunk.chunk_uid)] = chunk
        return len(chunks)

    def count_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> int:
        return sum(
            1
            for (scope_tenant, _), chunk in self._chunks.items()
            if scope_tenant == tenant_id
            and chunk.document_id == document_id
            and chunk.document_version == document_version
        )


class RecordingEventPublisher:
    def __init__(self) -> None:
        self.records: list[OutboxRecord] = []

    def publish(self, record: OutboxRecord) -> None:
        self.records.append(record)
