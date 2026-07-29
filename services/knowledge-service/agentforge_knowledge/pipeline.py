from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import re

from agentforge_document_processor import (
    FileSecurityPolicy,
    FinancialClauseChunker,
    MultimodalDocumentParser,
    ProcessingError,
)
from agentforge_document_processor.models import ParsedDocument, Region
from agentforge_document_processor.ports import (
    DocumentSandboxPort,
    EmbeddingProviderPort,
    MalwareScannerPort,
    OCRProviderPort,
)

from .config import IngestionConfig
from .errors import KnowledgeError
from .models import (
    IndexedChunk,
    IngestionJob,
    IngestionRequest,
    IngestionState,
    StoredDocument,
)
from .ports import (
    EventPublisherPort,
    KeywordIndexPort,
    KnowledgeRepositoryPort,
    ObjectStorePort,
    VectorIndexPort,
)


SENSITIVE_PATTERNS = (
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
)


def _request_digest(request: IngestionRequest) -> str:
    material = b"\x00".join(
        (
            request.tenant_id.encode("utf-8"),
            request.knowledge_base_id.encode("utf-8"),
            request.filename.lower().encode("utf-8"),
            request.declared_media_type.encode("ascii"),
            request.sensitive_content_policy.encode("ascii"),
            sha256(request.data).hexdigest().encode("ascii"),
        )
    )
    return sha256(material).hexdigest()


class KnowledgeIngestionPipeline:
    def __init__(
        self,
        *,
        repository: KnowledgeRepositoryPort,
        object_store: ObjectStorePort,
        keyword_index: KeywordIndexPort,
        vector_index: VectorIndexPort,
        security_policy: FileSecurityPolicy,
        malware_scanner: MalwareScannerPort,
        parser: MultimodalDocumentParser,
        ocr_provider: OCRProviderPort,
        chunker: FinancialClauseChunker,
        embedding_provider: EmbeddingProviderPort,
        sandbox: DocumentSandboxPort,
        config: IngestionConfig,
    ) -> None:
        config.validate(
            malware_scanner=malware_scanner,
            ocr_provider=ocr_provider,
            embedding_provider=embedding_provider,
            sandbox=sandbox,
        )
        self.repository = repository
        self.object_store = object_store
        self.keyword_index = keyword_index
        self.vector_index = vector_index
        self.security_policy = security_policy
        self.malware_scanner = malware_scanner
        self.parser = parser
        self.ocr_provider = ocr_provider
        self.chunker = chunker
        self.embedding_provider = embedding_provider
        self.sandbox = sandbox
        self.config = config

    def ingest(self, request: IngestionRequest) -> IngestionJob:
        self._validate_request(request)
        digest = _request_digest(request)
        job, created = self.repository.create_or_get_job(
            tenant_id=request.tenant_id,
            knowledge_base_id=request.knowledge_base_id,
            filename=request.filename,
            request_digest=digest,
            idempotency_key=request.idempotency_key,
            trace_id=request.trace_id,
        )
        if not created:
            return job

        try:
            self.repository.transition(
                request.tenant_id, job.job_id, IngestionState.SCANNING
            )
            safe_file = self.security_policy.validate(
                filename=request.filename,
                declared_media_type=request.declared_media_type,
                data=request.data,
                malware_scanner=self.malware_scanner,
                profile=self.config.profile,
            )
            self.repository.transition(
                request.tenant_id, job.job_id, IngestionState.ACCEPTED
            )
            object_key = self._object_key(job, safe_file.stored_sha256, safe_file.extension)
            self.object_store.put_if_absent(
                tenant_id=request.tenant_id,
                object_key=object_key,
                data=safe_file.data,
                media_type=safe_file.media_type,
                sha256_hex=safe_file.stored_sha256,
            )
            document = StoredDocument(
                tenant_id=request.tenant_id,
                knowledge_base_id=request.knowledge_base_id,
                document_id=job.document_id,
                document_version=job.document_version,
                object_key=object_key,
                safe_file=safe_file,
            )
            self.repository.save_document(document)
            self.repository.transition(
                request.tenant_id, job.job_id, IngestionState.STORED
            )
            return self._process_stored(
                job=self.repository.get_job(request.tenant_id, job.job_id),
                document=document,
                sensitive_content_policy=request.sensitive_content_policy,
            )
        except (ProcessingError, KnowledgeError) as exc:
            return self._record_failure(
                tenant_id=request.tenant_id,
                job_id=job.job_id,
                error=exc,
            )

    def retry(self, tenant_id: str, job_id: str) -> IngestionJob:
        job = self.repository.get_job(tenant_id, job_id)
        if job.state != IngestionState.FAILED:
            raise KnowledgeError(
                "INVALID_STATE_TRANSITION", "only failed jobs can be retried"
            )
        self.repository.increment_attempt(tenant_id, job_id)
        try:
            if job.failure_stage == IngestionState.INDEXING:
                self.repository.transition(
                    tenant_id, job_id, IngestionState.INDEXING
                )
                return self._index_and_publish(
                    self.repository.get_job(tenant_id, job_id)
                )
            document = self.repository.get_document(
                tenant_id, job.document_id, job.document_version
            )
            source_data = self.object_store.get(
                tenant_id=tenant_id,
                object_key=document.object_key,
            )
            document = replace(
                document,
                safe_file=replace(document.safe_file, data=source_data),
            )
            self.repository.transition(tenant_id, job_id, IngestionState.STORED)
            return self._process_stored(
                job=self.repository.get_job(tenant_id, job_id),
                document=document,
                sensitive_content_policy="reject",
            )
        except (ProcessingError, KnowledgeError) as exc:
            return self._record_failure(
                tenant_id=tenant_id,
                job_id=job_id,
                error=exc,
            )

    def _process_stored(
        self,
        *,
        job: IngestionJob,
        document: StoredDocument,
        sensitive_content_policy: str,
    ) -> IngestionJob:
        tenant_id = job.tenant_id
        self.repository.transition(tenant_id, job.job_id, IngestionState.PARSING)
        parsed = self.sandbox.execute(
            lambda: self.parser.parse(
                document.safe_file,
                ocr_provider=self.ocr_provider,
            ),
            timeout_seconds=self.config.parse_timeout_seconds,
        )
        parsed = self._apply_sensitive_policy(parsed, sensitive_content_policy)
        self.repository.save_parsed(
            tenant_id=tenant_id,
            document_id=job.document_id,
            document_version=job.document_version,
            parsed=parsed,
        )
        self.repository.transition(tenant_id, job.job_id, IngestionState.PARSED)
        self.repository.transition(tenant_id, job.job_id, IngestionState.CHUNKING)
        chunks = self.chunker.chunk(
            parsed,
            tenant_id=tenant_id,
            knowledge_base_id=job.knowledge_base_id,
            document_id=job.document_id,
            document_version=job.document_version,
        )
        embedding_batch = self.embedding_provider.embed(
            tuple(chunk.text for chunk in chunks)
        )
        if len(embedding_batch.vectors) != len(chunks):
            raise KnowledgeError(
                "INDEX_COUNT_MISMATCH",
                "embedding result count differs from chunk count",
                retryable=True,
            )
        indexed_chunks = tuple(
            IndexedChunk(
                tenant_id=tenant_id,
                knowledge_base_id=job.knowledge_base_id,
                document_id=job.document_id,
                document_version=job.document_version,
                source_object_key=document.object_key,
                chunk=chunk,
                extractor_version=parsed.extractor_version,
                embedding_model_id=embedding_batch.model_id,
                embedding_model_version=embedding_batch.model_version,
                embedding=vector,
                test_model=parsed.test_model or embedding_batch.test_model,
            )
            for chunk, vector in zip(
                chunks, embedding_batch.vectors, strict=True
            )
        )
        self.repository.save_chunks(
            tenant_id=tenant_id,
            document_id=job.document_id,
            document_version=job.document_version,
            chunks=indexed_chunks,
        )
        self.repository.transition(tenant_id, job.job_id, IngestionState.CHUNKED)
        self.repository.transition(tenant_id, job.job_id, IngestionState.INDEXING)
        return self._index_and_publish(self.repository.get_job(tenant_id, job.job_id))

    def _index_and_publish(self, job: IngestionJob) -> IngestionJob:
        chunks = self.repository.get_chunks(
            job.tenant_id,
            job.document_id,
            job.document_version,
        )
        expected = len(chunks)
        self.keyword_index.upsert(tenant_id=job.tenant_id, chunks=chunks)
        self.vector_index.upsert(tenant_id=job.tenant_id, chunks=chunks)
        bm25_count = self.keyword_index.count_document(
            tenant_id=job.tenant_id,
            document_id=job.document_id,
            document_version=job.document_version,
        )
        vector_count = self.vector_index.count_document(
            tenant_id=job.tenant_id,
            document_id=job.document_id,
            document_version=job.document_version,
        )
        self.repository.set_index_counts(
            tenant_id=job.tenant_id,
            job_id=job.job_id,
            bm25_indexed=bm25_count,
            vectors_indexed=vector_count,
        )
        if expected == 0 or bm25_count != expected or vector_count != expected:
            raise KnowledgeError(
                "INDEX_COUNT_MISMATCH",
                "dual index reconciliation failed",
                retryable=True,
            )
        self.repository.transition(
            job.tenant_id, job.job_id, IngestionState.INDEX_READY
        )
        return self.repository.publish_version(job.tenant_id, job.job_id)

    def _record_failure(
        self,
        *,
        tenant_id: str,
        job_id: str,
        error: ProcessingError | KnowledgeError,
    ) -> IngestionJob:
        job = self.repository.get_job(tenant_id, job_id)
        if (
            job.state == IngestionState.SCANNING
            and not error.retryable
            and error.code
            in {
                "VALIDATION_FAILED",
                "PAYLOAD_TOO_LARGE",
                "UNSUPPORTED_MEDIA_TYPE",
                "MALWARE_DETECTED",
                "SENSITIVE_CONTENT_BLOCKED",
            }
        ):
            return self.repository.transition(
                tenant_id,
                job_id,
                IngestionState.REJECTED,
                error_code=error.code,
                error_summary=str(error),
            )
        retryable = error.retryable and job.attempt < job.max_attempts
        return self.repository.transition(
            tenant_id,
            job_id,
            IngestionState.FAILED,
            retryable=retryable,
            error_code=error.code,
            error_summary=str(error),
            failure_stage=job.state,
        )

    @staticmethod
    def _object_key(job: IngestionJob, digest: str, extension: str) -> str:
        return (
            f"tenants/{job.tenant_id}/knowledge/{job.knowledge_base_id}/"
            f"documents/{job.document_id}/versions/{job.document_version}/"
            f"source/{digest}.{extension}"
        )

    @staticmethod
    def _validate_request(request: IngestionRequest) -> None:
        if not all(
            (
                request.tenant_id,
                request.knowledge_base_id,
                request.filename,
                request.idempotency_key,
            )
        ):
            raise KnowledgeError("VALIDATION_FAILED", "request scope is incomplete")
        if not re.fullmatch(r"[0-9a-f]{32}", request.trace_id):
            raise KnowledgeError("VALIDATION_FAILED", "trace_id is invalid")
        if request.sensitive_content_policy not in {"reject", "redact"}:
            raise KnowledgeError(
                "VALIDATION_FAILED", "sensitive content policy is invalid"
            )

    @staticmethod
    def _apply_sensitive_policy(
        parsed: ParsedDocument,
        policy: str,
    ) -> ParsedDocument:
        matched = any(
            pattern.search(region.text)
            for pattern in SENSITIVE_PATTERNS
            for region in parsed.regions
        )
        if not matched:
            return parsed
        if policy == "reject":
            raise ProcessingError(
                "SENSITIVE_CONTENT_BLOCKED",
                "document contains blocked sensitive values",
            )
        regions: list[Region] = []
        for region in parsed.regions:
            text = region.text
            for pattern in SENSITIVE_PATTERNS:
                text = pattern.sub("[REDACTED]", text)
            regions.append(replace(region, text=text))
        return replace(parsed, regions=tuple(regions))


class OutboxPublisher:
    def __init__(
        self,
        *,
        repository: KnowledgeRepositoryPort,
        publisher: EventPublisherPort,
    ) -> None:
        self.repository = repository
        self.publisher = publisher

    def publish_pending(self, tenant_id: str, *, limit: int = 100) -> int:
        published = 0
        for record in self.repository.pending_outbox(tenant_id, limit=limit):
            self.publisher.publish(record)
            self.repository.mark_outbox_published(record.tenant_id, record.event_id)
            published += 1
        return published
