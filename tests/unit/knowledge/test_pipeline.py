from __future__ import annotations

from pathlib import Path
import unittest

from agentforge_document_processor import (
    BoundingBox,
    ExtractedTable,
    FileSecurityPolicy,
    FinancialClauseChunker,
    HarnessMalwareScanner,
    HarnessOCRProvider,
    HashEmbeddingProvider,
    InProcessSandbox,
    MultimodalDocumentParser,
    ParsedDocument,
    ProcessingError,
    Region,
)
from agentforge_knowledge import (
    InMemoryKeywordIndex,
    InMemoryKnowledgeRepository,
    InMemoryObjectStore,
    InMemoryVectorIndex,
    IngestionConfig,
    IngestionRequest,
    KnowledgeError,
    KnowledgeIngestionPipeline,
    OutboxPublisher,
    RecordingEventPublisher,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "harness" / "fixtures"


def build_pipeline(*, vector_failures: int = 0):
    repository = InMemoryKnowledgeRepository()
    object_store = InMemoryObjectStore()
    keyword_index = InMemoryKeywordIndex()
    vector_index = InMemoryVectorIndex(failures_remaining=vector_failures)
    pipeline = KnowledgeIngestionPipeline(
        repository=repository,
        object_store=object_store,
        keyword_index=keyword_index,
        vector_index=vector_index,
        security_policy=FileSecurityPolicy(),
        malware_scanner=HarnessMalwareScanner(),
        parser=MultimodalDocumentParser(),
        ocr_provider=HarnessOCRProvider(),
        chunker=FinancialClauseChunker(),
        embedding_provider=HashEmbeddingProvider(),
        sandbox=InProcessSandbox(),
        config=IngestionConfig(),
    )
    return pipeline, repository, object_store, keyword_index, vector_index


def request(
    *,
    tenant_id: str = "tenant-a",
    idempotency_key: str = "upload-0001",
) -> IngestionRequest:
    path = FIXTURES / "documents" / "synthetic-loan-policy.pdf"
    return IngestionRequest(
        tenant_id=tenant_id,
        knowledge_base_id="kb-loan",
        filename=path.name,
        declared_media_type="application/pdf",
        data=path.read_bytes(),
        idempotency_key=idempotency_key,
        trace_id="a" * 32,
    )


class KnowledgePipelineTests(unittest.TestCase):
    def test_complete_ingestion_is_published_and_traceable(self) -> None:
        pipeline, repository, _, keyword_index, vector_index = build_pipeline()
        job = pipeline.ingest(request())

        self.assertEqual(str(job.state), "published")
        self.assertEqual(job.knowledge_version, "1.0.0")
        self.assertGreater(job.counts.chunks, 0)
        self.assertEqual(job.counts.chunks, job.counts.bm25_indexed)
        self.assertEqual(job.counts.chunks, job.counts.vectors_indexed)
        chunks = repository.get_chunks(
            "tenant-a", job.document_id, job.document_version
        )
        self.assertTrue(all(chunk.chunk.sources for chunk in chunks))
        self.assertEqual(
            keyword_index.count_document(
                tenant_id="tenant-a",
                document_id=job.document_id,
                document_version=job.document_version,
            ),
            len(chunks),
        )
        self.assertEqual(
            vector_index.count_document(
                tenant_id="tenant-a",
                document_id=job.document_id,
                document_version=job.document_version,
            ),
            len(chunks),
        )

    def test_duplicate_request_returns_original_job(self) -> None:
        pipeline, repository, _, _, _ = build_pipeline()
        first = pipeline.ingest(request())
        pending_before = repository.pending_outbox("tenant-a")
        second = pipeline.ingest(request())

        self.assertEqual(first.job_id, second.job_id)
        self.assertEqual(first.document_version, second.document_version)
        self.assertEqual(first.attempt, second.attempt)
        self.assertEqual(pending_before, repository.pending_outbox("tenant-a"))

    def test_idempotency_conflict_is_rejected(self) -> None:
        pipeline, _, _, _, _ = build_pipeline()
        pipeline.ingest(request())
        changed = request()
        changed = IngestionRequest(
            **{
                **changed.__dict__,
                "data": changed.data + b"different",
            }
        )
        with self.assertRaises(KnowledgeError) as error:
            pipeline.ingest(changed)
        self.assertEqual(error.exception.code, "IDEMPOTENCY_CONFLICT")

    def test_vector_failure_retries_once_with_same_chunk_ids(self) -> None:
        pipeline, repository, _, _, _ = build_pipeline(vector_failures=1)
        failed = pipeline.ingest(request())
        self.assertEqual(str(failed.state), "failed")
        self.assertTrue(failed.retryable)
        original_ids = tuple(
            chunk.chunk.chunk_uid
            for chunk in repository.get_chunks(
                "tenant-a", failed.document_id, failed.document_version
            )
        )

        recovered = pipeline.retry(
            "tenant-a",
            failed.job_id,
            idempotency_key="retry-0001",
        )
        self.assertEqual(str(recovered.state), "published")
        self.assertEqual(recovered.attempt, 2)
        recovered_ids = tuple(
            chunk.chunk.chunk_uid
            for chunk in repository.get_chunks(
                "tenant-a", recovered.document_id, recovered.document_version
            )
        )
        self.assertEqual(original_ids, recovered_ids)

        duplicate = pipeline.retry(
            "tenant-a",
            failed.job_id,
            idempotency_key="retry-0001",
        )
        self.assertEqual(duplicate.attempt, 2)
        with self.assertRaises(KnowledgeError):
            pipeline.retry(
                "tenant-a",
                failed.job_id,
                idempotency_key="retry-0002",
            )

    def test_cross_tenant_job_and_object_are_not_visible(self) -> None:
        pipeline, repository, object_store, _, _ = build_pipeline()
        job = pipeline.ingest(request())
        document = repository.get_document(
            "tenant-a", job.document_id, job.document_version
        )
        with self.assertRaises(KnowledgeError) as job_error:
            repository.get_job("tenant-b", job.job_id)
        self.assertEqual(job_error.exception.code, "RESOURCE_NOT_FOUND")
        with self.assertRaises(KnowledgeError) as object_error:
            object_store.get(
                tenant_id="tenant-b",
                object_key=document.object_key,
            )
        self.assertEqual(object_error.exception.code, "RESOURCE_NOT_FOUND")

    def test_outbox_and_inbox_are_idempotent_per_tenant(self) -> None:
        pipeline, repository, _, _, _ = build_pipeline()
        pipeline.ingest(request())
        pending = repository.pending_outbox("tenant-a")
        self.assertEqual(
            {record.event_type for record in pending},
            {
                "document.uploaded",
                "document.parsed",
                "document.chunked",
                "embedding.requested",
                "knowledge.version.published",
            },
        )
        publisher = RecordingEventPublisher()
        sent = OutboxPublisher(
            repository=repository,
            publisher=publisher,
        ).publish_pending("tenant-a")
        self.assertEqual(sent, len(pending))
        self.assertEqual(repository.pending_outbox("tenant-a"), ())

        event_id = pending[0].event_id
        self.assertTrue(
            repository.claim_inbox(
                tenant_id="tenant-a",
                consumer_name="test-consumer",
                event_id=event_id,
            )
        )
        self.assertFalse(
            repository.claim_inbox(
                tenant_id="tenant-a",
                consumer_name="test-consumer",
                event_id=event_id,
            )
        )
        self.assertTrue(
            repository.claim_inbox(
                tenant_id="tenant-b",
                consumer_name="test-consumer",
                event_id=event_id,
            )
        )

    def test_sensitive_values_are_redacted_in_regions_and_table_cells(self) -> None:
        sensitive = "身份证号 11010519491231002X"
        parsed = ParsedDocument(
            page_count=1,
            regions=(
                Region(
                    region_id="region-a",
                    page_number=1,
                    reading_order=0,
                    bounding_box=BoundingBox(0.1, 0.1, 0.9, 0.2),
                    content_type="table",
                    text=sensitive,
                    extractor_version="1.0.0",
                    confidence=1.0,
                    test_model=False,
                ),
            ),
            tables=(
                ExtractedTable(
                    table_id="table-a",
                    page_number=1,
                    bounding_box=BoundingBox(0.1, 0.1, 0.9, 0.2),
                    cells=(("字段", sensitive),),
                    normalized_text=f"字段 | {sensitive}",
                    extractor_version="1.0.0",
                    test_model=False,
                ),
            ),
            extractor_version="1.0.0",
            test_model=False,
        )
        redacted = KnowledgeIngestionPipeline._apply_sensitive_policy(
            parsed, "redact"
        )
        self.assertNotIn("11010519491231002X", redacted.regions[0].text)
        self.assertNotIn("11010519491231002X", redacted.tables[0].cells[0][1])
        with self.assertRaises(ProcessingError):
            KnowledgeIngestionPipeline._apply_sensitive_policy(parsed, "reject")

    def test_production_configuration_rejects_all_test_providers(self) -> None:
        with self.assertRaises(KnowledgeError) as error:
            KnowledgeIngestionPipeline(
                repository=InMemoryKnowledgeRepository(),
                object_store=InMemoryObjectStore(),
                keyword_index=InMemoryKeywordIndex(),
                vector_index=InMemoryVectorIndex(),
                security_policy=FileSecurityPolicy(),
                malware_scanner=HarnessMalwareScanner(),
                parser=MultimodalDocumentParser(),
                ocr_provider=HarnessOCRProvider(),
                chunker=FinancialClauseChunker(),
                embedding_provider=HashEmbeddingProvider(),
                sandbox=InProcessSandbox(),
                config=IngestionConfig(profile="production"),
            )
        self.assertEqual(error.exception.code, "VALIDATION_FAILED")


if __name__ == "__main__":
    unittest.main()
