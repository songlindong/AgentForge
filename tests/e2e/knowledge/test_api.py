from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

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
    KnowledgeIngestionPipeline,
    ServicePrincipal,
    StaticServiceAuthenticator,
    create_app,
)


ROOT = Path(__file__).resolve().parents[3]
PDF = ROOT / "harness" / "fixtures" / "documents" / "synthetic-loan-policy.pdf"


def client_and_repository() -> tuple[TestClient, InMemoryKnowledgeRepository]:
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
    authenticator = StaticServiceAuthenticator(
        {
            "token-a": ServicePrincipal(
                tenant_id="tenant-a",
                subject="knowledge-operator-a",
                scopes=frozenset({"knowledge:write"}),
            ),
            "token-b": ServicePrincipal(
                tenant_id="tenant-b",
                subject="knowledge-operator-b",
                scopes=frozenset({"knowledge:write"}),
            ),
            "token-read": ServicePrincipal(
                tenant_id="tenant-a",
                subject="read-only",
                scopes=frozenset(),
            ),
        }
    )
    return TestClient(create_app(pipeline=pipeline, authenticator=authenticator)), repository


class KnowledgeAPITests(unittest.TestCase):
    def test_upload_returns_durable_job_then_background_publishes(self) -> None:
        client, repository = client_and_repository()
        response = client.post(
            "/internal/v1/knowledge/ingestions",
            headers={
                "Authorization": "Bearer token-a",
                "Idempotency-Key": "upload-api-0001",
                "traceparent": f"00-{'a' * 32}-{'b' * 16}-01",
            },
            data={
                "knowledge_base_id": "kb-loan",
                "sensitive_content_policy": "reject",
            },
            files={"file": (PDF.name, PDF.read_bytes(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["state"], "stored")
        self.assertEqual(response.headers["X-Trace-ID"], "a" * 32)

        job_id = response.json()["job_id"]
        current = repository.get_job("tenant-a", job_id)
        self.assertEqual(str(current.state), "published")
        status = client.get(
            f"/internal/v1/knowledge/ingestions/{job_id}",
            headers={"Authorization": "Bearer token-a"},
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["state"], "published")

    def test_authentication_scope_and_tenant_visibility(self) -> None:
        client, _ = client_and_repository()
        missing = client.get("/internal/v1/knowledge/ingestions/job-missing")
        self.assertEqual(missing.status_code, 401)
        forbidden = client.get(
            "/internal/v1/knowledge/ingestions/job-missing",
            headers={"Authorization": "Bearer token-read"},
        )
        self.assertEqual(forbidden.status_code, 403)

        created = client.post(
            "/internal/v1/knowledge/ingestions",
            headers={
                "Authorization": "Bearer token-a",
                "Idempotency-Key": "upload-api-0002",
            },
            data={"knowledge_base_id": "kb-loan"},
            files={"file": (PDF.name, PDF.read_bytes(), "application/pdf")},
        )
        hidden = client.get(
            f"/internal/v1/knowledge/ingestions/{created.json()['job_id']}",
            headers={"Authorization": "Bearer token-b"},
        )
        self.assertEqual(hidden.status_code, 404)

    def test_conflicting_idempotency_key_returns_contract_error(self) -> None:
        client, _ = client_and_repository()
        headers = {
            "Authorization": "Bearer token-a",
            "Idempotency-Key": "upload-api-0003",
        }
        first = client.post(
            "/internal/v1/knowledge/ingestions",
            headers=headers,
            data={"knowledge_base_id": "kb-loan"},
            files={"file": (PDF.name, PDF.read_bytes(), "application/pdf")},
        )
        self.assertEqual(first.status_code, 202)
        conflict = client.post(
            "/internal/v1/knowledge/ingestions",
            headers=headers,
            data={"knowledge_base_id": "kb-loan"},
            files={
                "file": (
                    PDF.name,
                    PDF.read_bytes() + b"different",
                    "application/pdf",
                )
            },
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["code"], "IDEMPOTENCY_CONFLICT")
        self.assertFalse(conflict.json()["retryable"])

    def test_framework_validation_uses_the_shared_error_contract(self) -> None:
        client, _ = client_and_repository()
        response = client.post(
            "/internal/v1/knowledge/ingestions",
            headers={"Authorization": "Bearer token-a"},
            data={"knowledge_base_id": "kb-loan"},
            files={"file": (PDF.name, PDF.read_bytes(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "VALIDATION_FAILED")
        self.assertFalse(response.json()["retryable"])
        self.assertEqual(response.headers["X-Trace-ID"], response.json()["trace_id"])


if __name__ == "__main__":
    unittest.main()
