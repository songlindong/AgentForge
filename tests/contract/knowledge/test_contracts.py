from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from agentforge_document_processor import (
    FileSecurityPolicy,
    FinancialClauseChunker,
    HarnessMalwareScanner,
    HarnessOCRProvider,
    HashEmbeddingProvider,
    InProcessSandbox,
    MultimodalDocumentParser,
)
from agentforge_knowledge import (
    InMemoryKeywordIndex,
    InMemoryKnowledgeRepository,
    InMemoryObjectStore,
    InMemoryVectorIndex,
    IngestionConfig,
    IngestionRequest,
    KnowledgeIngestionPipeline,
)
from agentforge_knowledge.api import _job_payload
from agentforge_knowledge.event_payloads import event_envelope


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = ROOT / "contracts" / "json-schema"
EVENT_SCHEMA_ID = (
    "https://agentforge.local/contracts/json-schema/event-envelope.schema.json"
)
KNOWLEDGE_SCHEMA_ID = (
    "https://agentforge.local/contracts/json-schema/knowledge-event.schema.json"
)
JOB_SCHEMA_ID = (
    "https://agentforge.local/contracts/json-schema/"
    "knowledge-ingestion-job.schema.json"
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


def pipeline_and_repository():
    repository = InMemoryKnowledgeRepository()
    pipeline = KnowledgeIngestionPipeline(
        repository=repository,
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
        config=IngestionConfig(),
    )
    return pipeline, repository


class KnowledgeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = schema_registry()

    def test_job_and_all_outbox_events_match_json_schema(self) -> None:
        pipeline, repository = pipeline_and_repository()
        fixture = (
            ROOT
            / "harness"
            / "fixtures"
            / "documents"
            / "synthetic-loan-policy.pdf"
        )
        job = pipeline.ingest(
            IngestionRequest(
                tenant_id="tenant-a",
                knowledge_base_id="kb-loan",
                filename=fixture.name,
                declared_media_type="application/pdf",
                data=fixture.read_bytes(),
                idempotency_key="contract-0001",
                trace_id="a" * 32,
            )
        )
        job_validator = Draft202012Validator(
            {"$ref": f"{JOB_SCHEMA_ID}#/$defs/KnowledgeIngestionJob"},
            registry=self.registry,
        )
        self.assertEqual(
            list(job_validator.iter_errors(_job_payload(job))),
            [],
        )

        records = repository.pending_outbox("tenant-a")
        self.assertEqual(set(EVENT_DEFS), {record.event_type for record in records})
        for record in records:
            event_schema = {
                "allOf": [
                    {
                        "$ref": (
                            f"{EVENT_SCHEMA_ID}#/$defs/EventEnvelope"
                        )
                    },
                    {
                        "type": "object",
                        "properties": {
                            "event_type": {"const": record.event_type},
                            "event_version": {"const": "1.0.0"},
                            "data": {
                                "$ref": (
                                    f"{KNOWLEDGE_SCHEMA_ID}#/$defs/"
                                    f"{EVENT_DEFS[record.event_type]}"
                                )
                            },
                        },
                    },
                ]
            }
            validator = Draft202012Validator(
                event_schema,
                registry=self.registry,
            )
            errors = sorted(
                validator.iter_errors(event_envelope(record)),
                key=lambda error: list(error.path),
            )
            self.assertEqual(
                errors,
                [],
                msg=(
                    f"{record.event_type}: "
                    + "; ".join(error.message for error in errors)
                ),
            )

    def test_openapi_exposes_only_internal_ingestion_operations(self) -> None:
        contract = json.loads(
            (
                ROOT
                / "contracts"
                / "openapi"
                / "knowledge-ingestion.openapi.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(contract["paths"]),
            {
                "/internal/v1/knowledge/ingestions",
                "/internal/v1/knowledge/ingestions/{job_id}",
                "/internal/v1/knowledge/ingestions/{job_id}/retry",
            },
        )
        create = contract["paths"]["/internal/v1/knowledge/ingestions"]["post"]
        self.assertEqual(
            create["requestBody"]["content"]["multipart/form-data"]["schema"][
                "properties"
            ]["file"]["format"],
            "binary",
        )


if __name__ == "__main__":
    unittest.main()
