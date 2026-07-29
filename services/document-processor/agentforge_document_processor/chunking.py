from __future__ import annotations

from hashlib import sha256
import re

from .errors import ProcessingError
from .models import Chunk, ChunkSource, ParsedDocument, Region


WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    return WHITESPACE.sub(" ", text).strip()


class FinancialClauseChunker:
    version = "1.0.0"

    def __init__(self, *, max_characters: int = 800) -> None:
        if max_characters < 100:
            raise ValueError("max_characters must be at least 100")
        self.max_characters = max_characters

    def chunk(
        self,
        parsed: ParsedDocument,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        document_id: str,
        document_version: int,
    ) -> tuple[Chunk, ...]:
        for identifier in (tenant_id, knowledge_base_id, document_id):
            if not identifier:
                raise ProcessingError("VALIDATION_FAILED", "chunk scope is incomplete")
        if document_version < 1:
            raise ProcessingError("VALIDATION_FAILED", "document version is invalid")

        groups: list[list[tuple[Region, str]]] = []
        current: list[tuple[Region, str]] = []
        current_length = 0
        for region in sorted(parsed.regions, key=lambda item: item.reading_order):
            normalized = normalize_text(region.text)
            if not normalized:
                continue
            pieces = self._split_region(normalized)
            for piece in pieces:
                force_boundary = region.content_type == "table"
                if current and (
                    force_boundary
                    or current_length + 1 + len(piece) > self.max_characters
                    or (
                        region.content_type == "title"
                        and current[-1][0].content_type != "title"
                    )
                ):
                    groups.append(current)
                    current = []
                    current_length = 0
                current.append((region, piece))
                current_length += len(piece) + (1 if current_length else 0)
                if force_boundary:
                    groups.append(current)
                    current = []
                    current_length = 0
        if current:
            groups.append(current)

        chunks: list[Chunk] = []
        for ordinal, group in enumerate(groups):
            text = "\n".join(piece for _, piece in group)
            sources = tuple(
                ChunkSource(
                    region_id=region.region_id,
                    page_number=region.page_number,
                    bounding_box=region.bounding_box,
                )
                for region, _ in group
            )
            content_type = "table" if all(
                region.content_type == "table" for region, _ in group
            ) else "text"
            material = "|".join(
                (
                    tenant_id,
                    knowledge_base_id,
                    document_id,
                    str(document_version),
                    self.version,
                    ",".join(source.region_id for source in sources),
                    text,
                )
            )
            chunks.append(
                Chunk(
                    chunk_uid=f"chunk_{sha256(material.encode('utf-8')).hexdigest()}",
                    ordinal=ordinal,
                    text=text,
                    content_type=content_type,
                    sources=sources,
                    chunker_version=self.version,
                )
            )
        if not chunks:
            raise ProcessingError("VALIDATION_FAILED", "document produced no chunks")
        return tuple(chunks)

    def _split_region(self, text: str) -> tuple[str, ...]:
        if len(text) <= self.max_characters:
            return (text,)
        return tuple(
            text[offset : offset + self.max_characters]
            for offset in range(0, len(text), self.max_characters)
        )
