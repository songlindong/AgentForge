from __future__ import annotations

from dataclasses import dataclass

from agentforge_document_processor.ports import (
    EmbeddingProviderPort,
    MalwareScannerPort,
    OCRProviderPort,
    DocumentSandboxPort,
)

from .errors import KnowledgeError


@dataclass(frozen=True)
class IngestionConfig:
    profile: str = "test"
    parse_timeout_seconds: int = 30
    max_attempts: int = 3

    def validate(
        self,
        *,
        malware_scanner: MalwareScannerPort,
        ocr_provider: OCRProviderPort,
        embedding_provider: EmbeddingProviderPort,
        sandbox: DocumentSandboxPort,
    ) -> None:
        if self.profile not in {"local", "test", "production"}:
            raise KnowledgeError("VALIDATION_FAILED", "unknown runtime profile")
        if self.parse_timeout_seconds < 1 or self.max_attempts not in range(1, 6):
            raise KnowledgeError("VALIDATION_FAILED", "invalid ingestion limits")
        if self.profile == "production":
            test_components = (
                malware_scanner.test_provider,
                ocr_provider.test_provider,
                embedding_provider.test_provider,
                sandbox.test_provider,
            )
            if any(test_components):
                raise KnowledgeError(
                    "VALIDATION_FAILED",
                    "production profile forbids test ingestion providers",
                )
