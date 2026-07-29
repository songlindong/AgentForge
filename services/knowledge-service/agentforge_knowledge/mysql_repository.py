from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Any

from agentforge_document_processor.models import (
    BoundingBox,
    Chunk,
    ChunkSource,
    ExtractedTable,
    ParsedDocument,
    Region,
    SafeFile,
)

from .errors import KnowledgeError
from .models import (
    ALLOWED_TRANSITIONS,
    IndexedChunk,
    IngestionJob,
    IngestionState,
    OutboxRecord,
    StageCounts,
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


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


@dataclass(frozen=True)
class MySQLConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    connect_timeout_seconds: int = 5


class MySQLKnowledgeRepository:
    def __init__(
        self,
        config: MySQLConfig,
        *,
        bm25_index_version: str = "1.0.0",
        vector_index_version: str = "1.0.0",
    ) -> None:
        self.config = config
        self.bm25_index_version = bm25_index_version
        self.vector_index_version = vector_index_version

    def _connect(self) -> Any:
        try:
            import pymysql

            return pymysql.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                charset="utf8mb4",
                autocommit=False,
                connect_timeout=self.config.connect_timeout_seconds,
                cursorclass=pymysql.cursors.DictCursor,
            )
        except Exception as exc:
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE",
                "MySQL connection failed",
                retryable=True,
            ) from exc

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        connection = self._connect()
        try:
            connection.begin()
            yield connection
            connection.commit()
        except KnowledgeError:
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE",
                "MySQL operation failed",
                retryable=True,
            ) from exc
        finally:
            connection.close()

    @staticmethod
    def _job_from_row(row: dict[str, Any]) -> IngestionJob:
        failure_stage = (
            IngestionState(row["failure_stage"]) if row["failure_stage"] else None
        )
        return IngestionJob(
            tenant_id=row["tenant_id"],
            job_id=row["job_id"],
            knowledge_base_id=row["knowledge_base_id"],
            document_id=row["document_id"],
            document_version=int(row["document_version"]),
            request_digest=row["request_digest"],
            idempotency_key=row["idempotency_key"],
            trace_id=row["trace_id"],
            state=IngestionState(row["state"]),
            attempt=int(row["attempt"]),
            max_attempts=int(row["max_attempts"]),
            retryable=bool(row["retryable"]),
            error_code=row["error_code"],
            error_summary=row["error_summary"],
            failure_stage=failure_stage,
            knowledge_version=row["knowledge_version"],
            counts=StageCounts(
                pages=int(row["page_count"]),
                regions=int(row["region_count"]),
                tables=int(row["table_count"]),
                chunks=int(row["chunk_count"]),
                bm25_indexed=int(row["bm25_indexed"]),
                vectors_indexed=int(row["vectors_indexed"]),
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_or_get_job(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        filename: str,
        request_digest: str,
        idempotency_key: str,
        trace_id: str,
    ) -> tuple[IngestionJob, bool]:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM knowledge_ingestion_jobs
                    WHERE tenant_id = %s AND idempotency_key = %s
                    FOR UPDATE
                    """,
                    (tenant_id, idempotency_key),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    if existing["request_digest"] != request_digest:
                        raise KnowledgeError(
                            "IDEMPOTENCY_CONFLICT",
                            "idempotency key is bound to another request",
                        )
                    return self._job_from_row(existing), False

                logical_filename = filename.lower()
                cursor.execute(
                    """
                    SELECT request_digest, document_version
                    FROM knowledge_ingestion_jobs
                    WHERE tenant_id = %s
                      AND knowledge_base_id = %s
                      AND logical_filename = %s
                    ORDER BY document_version DESC
                    FOR UPDATE
                    """,
                    (tenant_id, knowledge_base_id, logical_filename),
                )
                versions = cursor.fetchall()
                matching = next(
                    (
                        int(row["document_version"])
                        for row in versions
                        if row["request_digest"] == request_digest
                    ),
                    None,
                )
                document_version = matching or (
                    max(
                        (int(row["document_version"]) for row in versions),
                        default=0,
                    )
                    + 1
                )
                document_id = _identifier(
                    "doc", tenant_id, knowledge_base_id, logical_filename
                )
                job_id = _identifier("job", tenant_id, idempotency_key)
                now = utc_now()
                cursor.execute(
                    """
                    INSERT INTO knowledge_ingestion_jobs (
                        tenant_id, job_id, knowledge_base_id, document_id,
                        document_version, logical_filename, request_digest,
                        idempotency_key, trace_id, state, attempt, max_attempts,
                        retryable, page_count, region_count, table_count,
                        chunk_count, bm25_indexed, vectors_indexed,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        1, 3, FALSE, 0, 0, 0, 0, 0, 0, %s, %s
                    )
                    """,
                    (
                        tenant_id,
                        job_id,
                        knowledge_base_id,
                        document_id,
                        document_version,
                        logical_filename,
                        request_digest,
                        idempotency_key,
                        trace_id,
                        IngestionState.RECEIVED,
                        now,
                        now,
                    ),
                )
                cursor.execute(
                    """
                    SELECT *
                    FROM knowledge_ingestion_jobs
                    WHERE tenant_id = %s AND job_id = %s
                    """,
                    (tenant_id, job_id),
                )
                return self._job_from_row(cursor.fetchone()), True

    def get_job(self, tenant_id: str, job_id: str) -> IngestionJob:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM knowledge_ingestion_jobs
                    WHERE tenant_id = %s AND job_id = %s
                    """,
                    (tenant_id, job_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KnowledgeError("RESOURCE_NOT_FOUND", "job is not visible")
                return self._job_from_row(row)

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
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                job = self._select_job_for_update(cursor, tenant_id, job_id)
                return self._transition_locked(
                    cursor,
                    job,
                    IngestionState(target_state),
                    retryable=retryable,
                    error_code=error_code,
                    error_summary=error_summary,
                    failure_stage=failure_stage,
                )

    def increment_attempt(self, tenant_id: str, job_id: str) -> IngestionJob:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                job = self._select_job_for_update(cursor, tenant_id, job_id)
                if not job.retryable or job.attempt >= job.max_attempts:
                    raise KnowledgeError(
                        "INVALID_STATE_TRANSITION", "job has no retry budget"
                    )
                cursor.execute(
                    """
                    UPDATE knowledge_ingestion_jobs
                    SET attempt = attempt + 1, updated_at = %s
                    WHERE tenant_id = %s AND job_id = %s
                    """,
                    (utc_now(), tenant_id, job_id),
                )
                return self._select_job_for_update(cursor, tenant_id, job_id)

    def _select_job_for_update(
        self,
        cursor: Any,
        tenant_id: str,
        job_id: str,
    ) -> IngestionJob:
        cursor.execute(
            """
            SELECT *
            FROM knowledge_ingestion_jobs
            WHERE tenant_id = %s AND job_id = %s
            FOR UPDATE
            """,
            (tenant_id, job_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise KnowledgeError("RESOURCE_NOT_FOUND", "job is not visible")
        return self._job_from_row(row)

    def _transition_locked(
        self,
        cursor: Any,
        job: IngestionJob,
        target: IngestionState,
        *,
        retryable: bool = False,
        error_code: str | None = None,
        error_summary: str | None = None,
        failure_stage: str | None = None,
    ) -> IngestionJob:
        if target not in ALLOWED_TRANSITIONS[job.state]:
            raise KnowledgeError(
                "INVALID_STATE_TRANSITION",
                f"cannot transition from {job.state} to {target}",
            )
        if target not in {IngestionState.FAILED, IngestionState.REJECTED}:
            error_code = None
            error_summary = None
        stored_failure_stage = (
            failure_stage if target == IngestionState.FAILED else None
        )
        cursor.execute(
            """
            UPDATE knowledge_ingestion_jobs
            SET state = %s,
                retryable = %s,
                error_code = %s,
                error_summary = %s,
                failure_stage = %s,
                updated_at = %s
            WHERE tenant_id = %s AND job_id = %s
            """,
            (
                target,
                retryable,
                error_code,
                error_summary,
                stored_failure_stage,
                utc_now(),
                job.tenant_id,
                job.job_id,
            ),
        )
        self._insert_state_outbox(cursor, job, target)
        return self._select_job_for_update(cursor, job.tenant_id, job.job_id)

    def _insert_state_outbox(
        self,
        cursor: Any,
        job: IngestionJob,
        target: IngestionState,
    ) -> None:
        topic_event = STATE_TOPICS.get(target)
        if topic_event is None:
            return
        topic, event_type = topic_event
        event_id = _identifier(
            "evt",
            job.tenant_id,
            job.job_id,
            target,
            str(job.attempt),
        )
        payload = {
            "job_id": job.job_id,
            "knowledge_base_id": job.knowledge_base_id,
            "document_id": job.document_id,
            "document_version": job.document_version,
            "previous_state": str(job.state),
            "state": str(target),
            "attempt": job.attempt,
        }
        cursor.execute(
            """
            INSERT IGNORE INTO knowledge_outbox (
                tenant_id, event_id, topic, partition_key, event_type,
                idempotency_key, trace_id, payload, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                job.tenant_id,
                event_id,
                topic,
                f"{job.tenant_id}:{job.document_id}",
                event_type,
                f"{job.job_id}:{target}:{job.attempt}",
                job.trace_id,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                utc_now(),
            ),
        )

    def save_document(self, document: StoredDocument) -> None:
        safe_file = document.safe_file
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO knowledge_documents (
                        tenant_id, knowledge_base_id, document_id,
                        document_version, logical_filename, media_type,
                        object_key, original_sha256, stored_sha256, byte_size,
                        page_count, exif_removed, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON DUPLICATE KEY UPDATE
                        object_key = VALUES(object_key),
                        stored_sha256 = VALUES(stored_sha256),
                        byte_size = VALUES(byte_size),
                        page_count = VALUES(page_count),
                        exif_removed = VALUES(exif_removed)
                    """,
                    (
                        document.tenant_id,
                        document.knowledge_base_id,
                        document.document_id,
                        document.document_version,
                        safe_file.filename,
                        safe_file.media_type,
                        document.object_key,
                        safe_file.original_sha256,
                        safe_file.stored_sha256,
                        safe_file.byte_size,
                        safe_file.page_count,
                        safe_file.exif_removed,
                        utc_now(),
                    ),
                )

    def get_document(
        self,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> StoredDocument:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM knowledge_documents
                    WHERE tenant_id = %s
                      AND document_id = %s
                      AND document_version = %s
                    """,
                    (tenant_id, document_id, document_version),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KnowledgeError(
                        "RESOURCE_NOT_FOUND", "document is not visible"
                    )
                extension = {
                    "application/pdf": "pdf",
                    "image/png": "png",
                    "image/jpeg": "jpg",
                }[row["media_type"]]
                safe_file = SafeFile(
                    filename=row["logical_filename"],
                    media_type=row["media_type"],
                    extension=extension,
                    data=b"",
                    original_sha256=row["original_sha256"],
                    stored_sha256=row["stored_sha256"],
                    byte_size=int(row["byte_size"]),
                    page_count=int(row["page_count"]),
                    exif_removed=bool(row["exif_removed"]),
                )
                return StoredDocument(
                    tenant_id=tenant_id,
                    knowledge_base_id=row["knowledge_base_id"],
                    document_id=document_id,
                    document_version=document_version,
                    object_key=row["object_key"],
                    safe_file=safe_file,
                )

    def save_parsed(
        self,
        *,
        tenant_id: str,
        document_id: str,
        document_version: int,
        parsed: ParsedDocument,
    ) -> None:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                regions_by_page: dict[int, list[Region]] = {}
                for region in parsed.regions:
                    regions_by_page.setdefault(region.page_number, []).append(region)
                for page_number in range(1, parsed.page_count + 1):
                    page_regions = regions_by_page.get(page_number, [])
                    extractor_version = (
                        page_regions[0].extractor_version
                        if page_regions
                        else parsed.extractor_version
                    )
                    test_model = any(
                        region.test_model for region in page_regions
                    ) or parsed.test_model
                    cursor.execute(
                        """
                        INSERT INTO knowledge_document_pages (
                            tenant_id, document_id, document_version,
                            page_number, extractor_version, test_model
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            extractor_version = VALUES(extractor_version),
                            test_model = VALUES(test_model)
                        """,
                        (
                            tenant_id,
                            document_id,
                            document_version,
                            page_number,
                            extractor_version,
                            test_model,
                        ),
                    )
                for region in parsed.regions:
                    cursor.execute(
                        """
                        INSERT INTO knowledge_regions (
                            tenant_id, document_id, document_version, region_id,
                            page_number, reading_order, bounding_box,
                            content_type, content_text, extractor_version,
                            confidence, test_model
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON DUPLICATE KEY UPDATE
                            page_number = VALUES(page_number),
                            reading_order = VALUES(reading_order),
                            bounding_box = VALUES(bounding_box),
                            content_type = VALUES(content_type),
                            content_text = VALUES(content_text),
                            extractor_version = VALUES(extractor_version),
                            confidence = VALUES(confidence),
                            test_model = VALUES(test_model)
                        """,
                        (
                            tenant_id,
                            document_id,
                            document_version,
                            region.region_id,
                            region.page_number,
                            region.reading_order,
                            json.dumps(region.bounding_box.as_list()),
                            region.content_type,
                            region.text,
                            region.extractor_version,
                            region.confidence,
                            region.test_model,
                        ),
                    )
                for table in parsed.tables:
                    cursor.execute(
                        """
                        INSERT INTO knowledge_tables (
                            tenant_id, document_id, document_version, table_id,
                            page_number, bounding_box, cells, normalized_text,
                            extractor_version, test_model
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            page_number = VALUES(page_number),
                            bounding_box = VALUES(bounding_box),
                            cells = VALUES(cells),
                            normalized_text = VALUES(normalized_text),
                            extractor_version = VALUES(extractor_version),
                            test_model = VALUES(test_model)
                        """,
                        (
                            tenant_id,
                            document_id,
                            document_version,
                            table.table_id,
                            table.page_number,
                            json.dumps(table.bounding_box.as_list()),
                            json.dumps(
                                table.cells,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                            table.normalized_text,
                            table.extractor_version,
                            table.test_model,
                        ),
                    )
                cursor.execute(
                    """
                    UPDATE knowledge_ingestion_jobs
                    SET page_count = %s,
                        region_count = %s,
                        table_count = %s,
                        updated_at = %s
                    WHERE tenant_id = %s
                      AND document_id = %s
                      AND document_version = %s
                    """,
                    (
                        parsed.page_count,
                        len(parsed.regions),
                        len(parsed.tables),
                        utc_now(),
                        tenant_id,
                        document_id,
                        document_version,
                    ),
                )

    def get_chunks(
        self,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> tuple[IndexedChunk, ...]:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM knowledge_chunks
                    WHERE tenant_id = %s
                      AND document_id = %s
                      AND document_version = %s
                    ORDER BY ordinal
                    """,
                    (tenant_id, document_id, document_version),
                )
                chunk_rows = cursor.fetchall()
                result: list[IndexedChunk] = []
                for row in chunk_rows:
                    cursor.execute(
                        """
                        SELECT *
                        FROM knowledge_chunk_sources
                        WHERE tenant_id = %s AND chunk_uid = %s
                        ORDER BY source_ordinal
                        """,
                        (tenant_id, row["chunk_uid"]),
                    )
                    sources = tuple(
                        ChunkSource(
                            region_id=source["region_id"],
                            page_number=int(source["page_number"]),
                            bounding_box=BoundingBox(
                                *_json_value(source["bounding_box"])
                            ),
                        )
                        for source in cursor.fetchall()
                    )
                    chunk = Chunk(
                        chunk_uid=row["chunk_uid"],
                        ordinal=int(row["ordinal"]),
                        text=row["content_text"],
                        content_type=row["content_type"],
                        sources=sources,
                        chunker_version=row["chunker_version"],
                    )
                    result.append(
                        IndexedChunk(
                            tenant_id=tenant_id,
                            knowledge_base_id=row["knowledge_base_id"],
                            document_id=document_id,
                            document_version=document_version,
                            source_object_key=row["source_object_key"],
                            chunk=chunk,
                            extractor_version=row["extractor_version"],
                            embedding_model_id=row["embedding_model_id"],
                            embedding_model_version=row[
                                "embedding_model_version"
                            ],
                            embedding=tuple(
                                float(value)
                                for value in _json_value(row["embedding_json"])
                            ),
                            test_model=bool(row["test_model"]),
                        )
                    )
                return tuple(result)

    def set_index_counts(
        self,
        *,
        tenant_id: str,
        job_id: str,
        bm25_indexed: int,
        vectors_indexed: int,
    ) -> IngestionJob:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                self._select_job_for_update(cursor, tenant_id, job_id)
                cursor.execute(
                    """
                    UPDATE knowledge_ingestion_jobs
                    SET bm25_indexed = %s,
                        vectors_indexed = %s,
                        updated_at = %s
                    WHERE tenant_id = %s AND job_id = %s
                    """,
                    (
                        bm25_indexed,
                        vectors_indexed,
                        utc_now(),
                        tenant_id,
                        job_id,
                    ),
                )
                return self._select_job_for_update(cursor, tenant_id, job_id)

    def publish_version(self, tenant_id: str, job_id: str) -> IngestionJob:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                job = self._select_job_for_update(cursor, tenant_id, job_id)
                if job.state != IngestionState.INDEX_READY:
                    raise KnowledgeError(
                        "INVALID_STATE_TRANSITION", "indexes are not ready"
                    )
                if (
                    job.counts.chunks < 1
                    or job.counts.bm25_indexed != job.counts.chunks
                    or job.counts.vectors_indexed != job.counts.chunks
                ):
                    raise KnowledgeError(
                        "INDEX_COUNT_MISMATCH",
                        "dual index reconciliation failed",
                        retryable=True,
                    )
                cursor.execute(
                    """
                    SELECT sequence_number
                    FROM knowledge_versions
                    WHERE tenant_id = %s AND knowledge_base_id = %s
                    ORDER BY sequence_number DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (tenant_id, job.knowledge_base_id),
                )
                previous = cursor.fetchone()
                sequence = int(previous["sequence_number"]) + 1 if previous else 0
                knowledge_version = f"1.0.{sequence}"
                cursor.execute(
                    """
                    INSERT INTO knowledge_versions (
                        tenant_id, knowledge_base_id, knowledge_version,
                        sequence_number, document_id, document_version,
                        bm25_index_version, vector_index_version, chunk_count,
                        trace_id, published_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        tenant_id,
                        job.knowledge_base_id,
                        knowledge_version,
                        sequence,
                        job.document_id,
                        job.document_version,
                        self.bm25_index_version,
                        self.vector_index_version,
                        job.counts.chunks,
                        job.trace_id,
                        utc_now(),
                    ),
                )
                cursor.execute(
                    """
                    UPDATE knowledge_ingestion_jobs
                    SET knowledge_version = %s
                    WHERE tenant_id = %s AND job_id = %s
                    """,
                    (knowledge_version, tenant_id, job_id),
                )
                job.knowledge_version = knowledge_version
                return self._transition_locked(
                    cursor, job, IngestionState.PUBLISHED
                )

    def claim_inbox(
        self,
        *,
        tenant_id: str,
        consumer_name: str,
        event_id: str,
    ) -> bool:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT IGNORE INTO knowledge_inbox (
                        tenant_id, consumer_name, event_id, processed_at
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (tenant_id, consumer_name, event_id, utc_now()),
                )
                return cursor.rowcount == 1

    def pending_outbox(
        self,
        tenant_id: str,
        *,
        limit: int = 100,
    ) -> tuple[OutboxRecord, ...]:
        safe_limit = max(1, min(int(limit), 1000))
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT *
                    FROM knowledge_outbox
                    WHERE tenant_id = %s AND published_at IS NULL
                    ORDER BY created_at
                    LIMIT {safe_limit}
                    """,
                    (tenant_id,),
                )
                return tuple(
                    OutboxRecord(
                        tenant_id=row["tenant_id"],
                        event_id=row["event_id"],
                        topic=row["topic"],
                        partition_key=row["partition_key"],
                        event_type=row["event_type"],
                        idempotency_key=row["idempotency_key"],
                        trace_id=row["trace_id"],
                        data=_json_value(row["payload"]),
                        created_at=row["created_at"],
                        published_at=row["published_at"],
                    )
                    for row in cursor.fetchall()
                )

    def mark_outbox_published(self, tenant_id: str, event_id: str) -> None:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE knowledge_outbox
                    SET published_at = COALESCE(published_at, %s)
                    WHERE tenant_id = %s AND event_id = %s
                    """,
                    (utc_now(), tenant_id, event_id),
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        """
                        SELECT event_id
                        FROM knowledge_outbox
                        WHERE tenant_id = %s AND event_id = %s
                        """,
                        (tenant_id, event_id),
                    )
                    if cursor.fetchone() is None:
                        raise KnowledgeError(
                            "RESOURCE_NOT_FOUND",
                            "outbox record is not visible",
                        )

    def apply_migration(self, migration_sql: str) -> None:
        statements = [
            statement.strip()
            for statement in migration_sql.split(";")
            if statement.strip()
        ]
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)

    def get_parsed(
        self,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> ParsedDocument:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT page_count
                    FROM knowledge_documents
                    WHERE tenant_id = %s
                      AND document_id = %s
                      AND document_version = %s
                    """,
                    (tenant_id, document_id, document_version),
                )
                document = cursor.fetchone()
                if document is None:
                    raise KnowledgeError(
                        "RESOURCE_NOT_FOUND", "parsed document is not visible"
                    )
                cursor.execute(
                    """
                    SELECT *
                    FROM knowledge_regions
                    WHERE tenant_id = %s
                      AND document_id = %s
                      AND document_version = %s
                    ORDER BY reading_order
                    """,
                    (tenant_id, document_id, document_version),
                )
                regions = tuple(
                    Region(
                        region_id=row["region_id"],
                        page_number=int(row["page_number"]),
                        reading_order=int(row["reading_order"]),
                        bounding_box=BoundingBox(*_json_value(row["bounding_box"])),
                        content_type=row["content_type"],
                        text=row["content_text"],
                        extractor_version=row["extractor_version"],
                        confidence=float(row["confidence"]),
                        test_model=bool(row["test_model"]),
                    )
                    for row in cursor.fetchall()
                )
                cursor.execute(
                    """
                    SELECT *
                    FROM knowledge_tables
                    WHERE tenant_id = %s
                      AND document_id = %s
                      AND document_version = %s
                    ORDER BY page_number, table_id
                    """,
                    (tenant_id, document_id, document_version),
                )
                tables = tuple(
                    ExtractedTable(
                        table_id=row["table_id"],
                        page_number=int(row["page_number"]),
                        bounding_box=BoundingBox(*_json_value(row["bounding_box"])),
                        cells=tuple(
                            tuple(str(cell) for cell in cells)
                            for cells in _json_value(row["cells"])
                        ),
                        normalized_text=row["normalized_text"],
                        extractor_version=row["extractor_version"],
                        test_model=bool(row["test_model"]),
                    )
                    for row in cursor.fetchall()
                )
                if not regions:
                    raise KnowledgeError(
                        "RESOURCE_NOT_FOUND", "parsed regions are not visible"
                    )
                versions = {region.extractor_version for region in regions}
                extractor_version = (
                    next(iter(versions))
                    if len(versions) == 1
                    else "pdf-baseline-1.0.0"
                )
                return ParsedDocument(
                    page_count=int(document["page_count"]),
                    regions=regions,
                    tables=tables,
                    extractor_version=extractor_version,
                    test_model=any(region.test_model for region in regions),
                )

    def save_chunks(
        self,
        *,
        tenant_id: str,
        document_id: str,
        document_version: int,
        chunks: Sequence[IndexedChunk],
    ) -> None:
        with self._transaction() as connection:
            with connection.cursor() as cursor:
                for indexed in chunks:
                    if indexed.tenant_id != tenant_id:
                        raise KnowledgeError(
                            "TENANT_MISMATCH", "chunk tenant mismatch"
                        )
                    chunk = indexed.chunk
                    cursor.execute(
                        """
                        INSERT INTO knowledge_chunks (
                            tenant_id, knowledge_base_id, document_id,
                            document_version, chunk_uid, ordinal, content_type,
                            content_text, source_object_key, chunker_version,
                            extractor_version, embedding_model_id,
                            embedding_model_version, embedding_dimension,
                            embedding_json, test_model, created_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON DUPLICATE KEY UPDATE
                            ordinal = VALUES(ordinal),
                            content_type = VALUES(content_type),
                            content_text = VALUES(content_text),
                            source_object_key = VALUES(source_object_key),
                            chunker_version = VALUES(chunker_version),
                            extractor_version = VALUES(extractor_version),
                            embedding_model_id = VALUES(embedding_model_id),
                            embedding_model_version = VALUES(embedding_model_version),
                            embedding_dimension = VALUES(embedding_dimension),
                            embedding_json = VALUES(embedding_json),
                            test_model = VALUES(test_model)
                        """,
                        (
                            tenant_id,
                            indexed.knowledge_base_id,
                            document_id,
                            document_version,
                            chunk.chunk_uid,
                            chunk.ordinal,
                            chunk.content_type,
                            chunk.text,
                            indexed.source_object_key,
                            chunk.chunker_version,
                            indexed.extractor_version,
                            indexed.embedding_model_id,
                            indexed.embedding_model_version,
                            len(indexed.embedding),
                            json.dumps(indexed.embedding),
                            indexed.test_model,
                            utc_now(),
                        ),
                    )
                    cursor.execute(
                        """
                        DELETE FROM knowledge_chunk_sources
                        WHERE tenant_id = %s AND chunk_uid = %s
                        """,
                        (tenant_id, chunk.chunk_uid),
                    )
                    for source_ordinal, source in enumerate(chunk.sources):
                        cursor.execute(
                            """
                            INSERT INTO knowledge_chunk_sources (
                                tenant_id, chunk_uid, source_ordinal, region_id,
                                page_number, bounding_box
                            ) VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (
                                tenant_id,
                                chunk.chunk_uid,
                                source_ordinal,
                                source.region_id,
                                source.page_number,
                                json.dumps(source.bounding_box.as_list()),
                            ),
                        )
                cursor.execute(
                    """
                    UPDATE knowledge_ingestion_jobs
                    SET chunk_count = %s, updated_at = %s
                    WHERE tenant_id = %s
                      AND document_id = %s
                      AND document_version = %s
                    """,
                    (
                        len(chunks),
                        utc_now(),
                        tenant_id,
                        document_id,
                        document_version,
                    ),
                )
