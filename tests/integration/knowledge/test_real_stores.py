from __future__ import annotations

import json
import os
from pathlib import Path
import time
import unittest

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from agentforge_knowledge import IngestionRequest, KnowledgeError
from agentforge_knowledge.event_payloads import event_envelope
from agentforge_knowledge.runtime import (
    RuntimeSettings,
    apply_migration,
    build_runtime,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "harness/fixtures"
SCHEMA_ROOT = ROOT / "contracts/json-schema"
ENABLED = os.environ.get("AGENTFORGE_RUN_KNOWLEDGE_INTEGRATION") == "1"
EVENT_SCHEMA_ID = (
    "https://agentforge.local/contracts/json-schema/event-envelope.schema.json"
)
KNOWLEDGE_SCHEMA_ID = (
    "https://agentforge.local/contracts/json-schema/knowledge-event.schema.json"
)
EVENT_DEFS = {
    "document.uploaded": "DocumentUploadedPayload",
    "document.parsed": "DocumentParsedPayload",
    "document.chunked": "DocumentChunkedPayload",
    "embedding.requested": "EmbeddingRequestedPayload",
    "knowledge.version.published": "KnowledgeVersionPublishedPayload",
}


def schema_registry() -> Registry:
    registry = Registry()
    for path in SCHEMA_ROOT.glob("*.schema.json"):
        contents = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(
            contents["$id"],
            Resource.from_contents(contents),
        )
    return registry


class FailOnceVectorIndex:
    def __init__(self, delegate: object) -> None:
        self.delegate = delegate
        self.collection_name = delegate.collection_name
        self.index_version = delegate.index_version
        self.failures_remaining = 1

    def upsert(self, *, tenant_id: str, chunks: object) -> int:
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE",
                "integration fault injection",
                retryable=True,
            )
        return self.delegate.upsert(tenant_id=tenant_id, chunks=chunks)

    def count_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> int:
        return self.delegate.count_document(
            tenant_id=tenant_id,
            document_id=document_id,
            document_version=document_version,
        )


@unittest.skipUnless(ENABLED, "需要显式启用第 7 步真实存储联调")
class RealKnowledgeStoresTests(unittest.TestCase):
    def test_multimodal_write_retry_outbox_and_tenant_isolation(self) -> None:
        settings = RuntimeSettings.from_mapping(os.environ)
        apply_migration(settings)
        runtime = build_runtime(settings)
        run_id = os.environ.get("AGENTFORGE_INTEGRATION_RUN_ID", "manual")
        tenant_id = f"tenant-step7-{run_id}"
        jobs = []
        fixtures = (
            ("documents/synthetic-loan-policy.pdf", "application/pdf"),
            ("documents/synthetic-scan-contract.pdf", "application/pdf"),
            ("images/synthetic-contract-screenshot.png", "image/png"),
            ("images/synthetic-contract-photo.jpg", "image/jpeg"),
        )

        for ordinal, (relative_path, media_type) in enumerate(fixtures):
            path = FIXTURES / relative_path
            job = runtime.pipeline.ingest(
                IngestionRequest(
                    tenant_id=tenant_id,
                    knowledge_base_id="kb-loan",
                    filename=path.name,
                    declared_media_type=media_type,
                    data=path.read_bytes(),
                    idempotency_key=f"step7-{run_id}-{ordinal:02d}",
                    trace_id=f"{ordinal + 1:032x}",
                )
            )
            self.assertEqual(str(job.state), "published")
            self.assertGreater(job.counts.chunks, 0)
            self.assertEqual(job.counts.chunks, job.counts.bm25_indexed)
            self.assertEqual(job.counts.chunks, job.counts.vectors_indexed)
            document = runtime.repository.get_document(
                tenant_id, job.document_id, job.document_version
            )
            self.assertTrue(
                runtime.pipeline.object_store.get(
                    tenant_id=tenant_id,
                    object_key=document.object_key,
                )
            )
            parsed = runtime.repository.get_parsed(
                tenant_id, job.document_id, job.document_version
            )
            self.assertTrue(parsed.regions)
            self.assertTrue(
                all(
                    region.page_number >= 1
                    and region.extractor_version
                    and region.bounding_box.x1 > region.bounding_box.x0
                    and region.bounding_box.y1 > region.bounding_box.y0
                    for region in parsed.regions
                )
            )
            jobs.append(job)

        duplicate_path = FIXTURES / fixtures[0][0]
        duplicate = runtime.pipeline.ingest(
            IngestionRequest(
                tenant_id=tenant_id,
                knowledge_base_id="kb-loan",
                filename=duplicate_path.name,
                declared_media_type="application/pdf",
                data=duplicate_path.read_bytes(),
                idempotency_key=f"step7-{run_id}-00",
                trace_id=f"{1:032x}",
            )
        )
        self.assertEqual(duplicate.job_id, jobs[0].job_id)
        self.assertEqual(duplicate.document_version, jobs[0].document_version)

        mismatch = FIXTURES / "security/mime-mismatch.jpg"
        rejected = runtime.pipeline.ingest(
            IngestionRequest(
                tenant_id=tenant_id,
                knowledge_base_id="kb-loan",
                filename=mismatch.name,
                declared_media_type="image/jpeg",
                data=mismatch.read_bytes(),
                idempotency_key=f"step7-{run_id}-rejected",
                trace_id="e" * 32,
            )
        )
        self.assertEqual(str(rejected.state), "rejected")
        self.assertEqual(rejected.error_code, "UNSUPPORTED_MEDIA_TYPE")

        real_vector = runtime.pipeline.vector_index
        runtime.pipeline.vector_index = FailOnceVectorIndex(real_vector)
        retry_path = FIXTURES / "documents/synthetic-loan-policy.pdf"
        failed = runtime.pipeline.ingest(
            IngestionRequest(
                tenant_id=tenant_id,
                knowledge_base_id="kb-loan",
                filename=f"retry-{retry_path.name}",
                declared_media_type="application/pdf",
                data=retry_path.read_bytes(),
                idempotency_key=f"step7-{run_id}-retry-source",
                trace_id="f" * 32,
            )
        )
        self.assertEqual(str(failed.state), "failed")
        self.assertTrue(failed.retryable)
        original_ids = tuple(
            chunk.chunk.chunk_uid
            for chunk in runtime.repository.get_chunks(
                tenant_id, failed.document_id, failed.document_version
            )
        )
        recovered = runtime.pipeline.retry(
            tenant_id,
            failed.job_id,
            idempotency_key=f"step7-{run_id}-retry-command",
        )
        self.assertEqual(str(recovered.state), "published")
        self.assertEqual(recovered.attempt, 2)
        self.assertEqual(
            original_ids,
            tuple(
                chunk.chunk.chunk_uid
                for chunk in runtime.repository.get_chunks(
                    tenant_id, recovered.document_id, recovered.document_version
                )
            ),
        )

        with self.assertRaises(KnowledgeError) as hidden:
            runtime.repository.get_job("tenant-step7-other", jobs[0].job_id)
        self.assertEqual(hidden.exception.code, "RESOURCE_NOT_FOUND")
        pending = runtime.repository.pending_outbox(tenant_id, limit=1000)
        self.assertGreaterEqual(len(pending), 26)
        registry = schema_registry()
        for record in pending:
            definition = EVENT_DEFS[record.event_type]
            validator = Draft202012Validator(
                {
                    "allOf": [
                        {"$ref": f"{EVENT_SCHEMA_ID}#/$defs/EventEnvelope"},
                        {
                            "type": "object",
                            "properties": {
                                "event_type": {"const": record.event_type},
                                "data": {
                                    "$ref": (
                                        f"{KNOWLEDGE_SCHEMA_ID}#/$defs/{definition}"
                                    )
                                },
                            },
                        },
                    ]
                },
                registry=registry,
                format_checker=FormatChecker(),
            )
            self.assertEqual(
                list(validator.iter_errors(event_envelope(record))),
                [],
                msg=record.event_type,
            )

        sample_event = pending[0].event_id
        self.assertTrue(
            runtime.repository.claim_inbox(
                tenant_id=tenant_id,
                consumer_name="step7-integration",
                event_id=sample_event,
            )
        )
        self.assertFalse(
            runtime.repository.claim_inbox(
                tenant_id=tenant_id,
                consumer_name="step7-integration",
                event_id=sample_event,
            )
        )

        received = self._publish_and_consume(runtime, tenant_id, pending)
        self.assertEqual(len(received), len(pending))
        self.assertEqual(runtime.repository.pending_outbox(tenant_id), ())
        self.assertEqual(
            {message.value["event_id"] for message in received},
            {record.event_id for record in pending},
        )
        print(
            "第 7 步真实存储联调通过: "
            f"tenant={tenant_id}, documents=5, events={len(received)}"
        )

    def _publish_and_consume(
        self,
        runtime: object,
        tenant_id: str,
        pending: tuple[object, ...],
    ) -> list[object]:
        from kafka import KafkaConsumer, TopicPartition
        from kafka.admin import KafkaAdminClient, NewTopic
        from kafka.errors import TopicAlreadyExistsError

        topics = sorted({record.topic for record in pending})
        admin = KafkaAdminClient(
            bootstrap_servers=list(runtime.settings.kafka_bootstrap_servers),
            client_id="agentforge-step7-integration-admin",
        )
        try:
            admin.create_topics(
                [NewTopic(name=topic, num_partitions=3, replication_factor=1) for topic in topics]
            )
        except TopicAlreadyExistsError:
            pass
        finally:
            admin.close()

        consumer = KafkaConsumer(
            bootstrap_servers=list(runtime.settings.kafka_bootstrap_servers),
            enable_auto_commit=False,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        )
        try:
            partitions = [
                TopicPartition(topic, partition)
                for topic in topics
                for partition in sorted(consumer.partitions_for_topic(topic) or ())
            ]
            self.assertTrue(partitions, "Kafka topics have no readable partitions")
            consumer.assign(partitions)
            end_offsets = consumer.end_offsets(partitions)
            for partition in partitions:
                consumer.seek(partition, end_offsets[partition])
            sent = runtime.outbox.publish_pending(tenant_id, limit=1000)
            self.assertEqual(sent, len(pending))

            messages = []
            deadline = time.monotonic() + 20
            while len(messages) < sent and time.monotonic() < deadline:
                batches = consumer.poll(timeout_ms=1000, max_records=sent)
                for records in batches.values():
                    for message in records:
                        if message.value.get("tenant_id") == tenant_id:
                            headers = {key for key, _ in message.headers}
                            self.assertTrue(
                                {
                                    "content_type",
                                    "schema_id",
                                    "tenant_id",
                                    "traceparent",
                                    "idempotency_key",
                                }.issubset(headers)
                            )
                            messages.append(message)
            return messages
        finally:
            consumer.close()


if __name__ == "__main__":
    unittest.main()
