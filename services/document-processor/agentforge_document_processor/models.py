from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BoundingBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        values = (self.x0, self.y0, self.x1, self.y1)
        if any(value < 0.0 or value > 1.0 for value in values):
            raise ValueError("bounding box must use normalized coordinates")
        if self.x0 > self.x1 or self.y0 > self.y1:
            raise ValueError("bounding box coordinates are inverted")

    def as_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass(frozen=True)
class SafeFile:
    filename: str
    media_type: str
    extension: str
    data: bytes
    original_sha256: str
    stored_sha256: str
    byte_size: int
    page_count: int
    exif_removed: bool


@dataclass(frozen=True)
class OCRRegion:
    text: str
    bounding_box: BoundingBox
    content_type: str = "text"
    confidence: float = 1.0


@dataclass(frozen=True)
class Region:
    region_id: str
    page_number: int
    reading_order: int
    bounding_box: BoundingBox
    content_type: str
    text: str
    extractor_version: str
    confidence: float
    test_model: bool


@dataclass(frozen=True)
class ExtractedTable:
    table_id: str
    page_number: int
    bounding_box: BoundingBox
    cells: tuple[tuple[str, ...], ...]
    normalized_text: str
    extractor_version: str
    test_model: bool


@dataclass(frozen=True)
class ParsedDocument:
    page_count: int
    regions: tuple[Region, ...]
    tables: tuple[ExtractedTable, ...]
    extractor_version: str
    test_model: bool


@dataclass(frozen=True)
class ChunkSource:
    region_id: str
    page_number: int
    bounding_box: BoundingBox


@dataclass(frozen=True)
class Chunk:
    chunk_uid: str
    ordinal: int
    text: str
    content_type: str
    sources: tuple[ChunkSource, ...]
    chunker_version: str


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: tuple[tuple[float, ...], ...]
    model_id: str
    model_version: str
    dimension: int
    test_model: bool


JSONValue = str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
JSONMapping = dict[str, Any]
