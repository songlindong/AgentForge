from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol, TypeVar

from .models import EmbeddingBatch, OCRRegion


class MalwareScannerPort(Protocol):
    test_provider: bool

    def scan(self, *, filename: str, data: bytes) -> bool:
        """Return True only when the file is accepted as clean."""


class OCRProviderPort(Protocol):
    model_version: str
    test_provider: bool

    def recognize(
        self,
        *,
        source_sha256: str,
        page_number: int,
        image_bytes: bytes,
    ) -> Sequence[OCRRegion]:
        """Return OCR regions in normalized top-left coordinates."""


class EmbeddingProviderPort(Protocol):
    model_id: str
    model_version: str
    dimension: int
    test_provider: bool

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Embed texts while preserving input order."""


T = TypeVar("T")


class DocumentSandboxPort(Protocol):
    test_provider: bool

    def execute(self, operation: Callable[[], T], *, timeout_seconds: int) -> T:
        """Execute an untrusted parsing operation within its configured boundary."""
