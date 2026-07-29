from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
from io import BytesIO

from .errors import ProcessingError
from .models import (
    BoundingBox,
    ExtractedTable,
    ParsedDocument,
    Region,
    SafeFile,
)
from .ports import OCRProviderPort


def _stable_id(prefix: str, *values: object) -> str:
    material = "|".join(str(value) for value in values).encode("utf-8")
    return f"{prefix}_{sha256(material).hexdigest()[:32]}"


def _normalize_box(
    bbox: tuple[float, float, float, float],
    width: float,
    height: float,
) -> BoundingBox:
    x0, y0, x1, y1 = bbox
    return BoundingBox(
        round(max(0.0, min(1.0, x0 / width)), 6),
        round(max(0.0, min(1.0, y0 / height)), 6),
        round(max(0.0, min(1.0, x1 / width)), 6),
        round(max(0.0, min(1.0, y1 / height)), 6),
    )


class MultimodalDocumentParser:
    native_extractor_version = "pdf-baseline-1.0.0"

    def parse(
        self,
        safe_file: SafeFile,
        *,
        ocr_provider: OCRProviderPort,
    ) -> ParsedDocument:
        if safe_file.media_type == "application/pdf":
            return self._parse_pdf(safe_file, ocr_provider)
        if safe_file.media_type in {"image/png", "image/jpeg"}:
            return self._parse_image(safe_file, ocr_provider)
        raise ProcessingError("UNSUPPORTED_MEDIA_TYPE", "unsupported parser media type")

    def _parse_pdf(
        self,
        safe_file: SafeFile,
        ocr_provider: OCRProviderPort,
    ) -> ParsedDocument:
        try:
            import pdfplumber
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(safe_file.data), strict=True)
            regions: list[Region] = []
            tables: list[ExtractedTable] = []
            used_test_model = False
            with pdfplumber.open(BytesIO(safe_file.data)) as plumber:
                for page_index, (reader_page, page) in enumerate(
                    zip(reader.pages, plumber.pages, strict=True),
                    start=1,
                ):
                    page_regions, page_tables = self._parse_native_page(
                        source_sha256=safe_file.original_sha256,
                        page_number=page_index,
                        page=page,
                        fallback_text=reader_page.extract_text() or "",
                        starting_order=len(regions),
                    )
                    if not any(region.text.strip() for region in page_regions):
                        page_regions = self._ocr_page(
                            safe_file=safe_file,
                            page_number=page_index,
                            ocr_provider=ocr_provider,
                            starting_order=len(regions),
                        )
                        used_test_model = used_test_model or ocr_provider.test_provider
                    regions.extend(page_regions)
                    tables.extend(page_tables)
        except ProcessingError:
            raise
        except Exception as exc:
            raise ProcessingError("VALIDATION_FAILED", "PDF parsing failed") from exc

        if not regions:
            raise ProcessingError("VALIDATION_FAILED", "document contains no readable regions")
        versions = {region.extractor_version for region in regions}
        extractor_version = (
            ocr_provider.model_version
            if versions == {ocr_provider.model_version}
            else self.native_extractor_version
        )
        return ParsedDocument(
            page_count=safe_file.page_count,
            regions=tuple(regions),
            tables=tuple(tables),
            extractor_version=extractor_version,
            test_model=used_test_model,
        )

    def _parse_native_page(
        self,
        *,
        source_sha256: str,
        page_number: int,
        page: object,
        fallback_text: str,
        starting_order: int,
    ) -> tuple[list[Region], list[ExtractedTable]]:
        width = float(getattr(page, "width"))
        height = float(getattr(page, "height"))
        tables: list[ExtractedTable] = []
        table_objects = list(getattr(page, "find_tables")())
        for table_index, table_object in enumerate(table_objects):
            raw_cells = table_object.extract() or []
            cells = tuple(
                tuple((cell or "").strip() for cell in row)
                for row in raw_cells
                if any((cell or "").strip() for cell in row)
            )
            if not cells:
                continue
            normalized_text = "\n".join(" | ".join(row) for row in cells)
            bbox = _normalize_box(tuple(table_object.bbox), width, height)
            tables.append(
                ExtractedTable(
                    table_id=_stable_id(
                        "table",
                        source_sha256,
                        page_number,
                        table_index,
                        normalized_text,
                    ),
                    page_number=page_number,
                    bounding_box=bbox,
                    cells=cells,
                    normalized_text=normalized_text,
                    extractor_version=self.native_extractor_version,
                    test_model=False,
                )
            )

        words = list(
            getattr(page, "extract_words")(
                use_text_flow=True,
                keep_blank_chars=False,
            )
        )
        lines = list(self._group_words_into_lines(words))
        regions: list[Region] = []
        for line_index, line in enumerate(lines):
            text = " ".join(str(word["text"]).strip() for word in line).strip()
            if not text:
                continue
            bbox = _normalize_box(
                (
                    min(float(word["x0"]) for word in line),
                    min(float(word["top"]) for word in line),
                    max(float(word["x1"]) for word in line),
                    max(float(word["bottom"]) for word in line),
                ),
                width,
                height,
            )
            content_type = "title" if line_index == 0 and len(text) <= 80 else "text"
            order = starting_order + len(regions)
            regions.append(
                Region(
                    region_id=_stable_id(
                        "region",
                        source_sha256,
                        page_number,
                        order,
                        text,
                        bbox.as_list(),
                    ),
                    page_number=page_number,
                    reading_order=order,
                    bounding_box=bbox,
                    content_type=content_type,
                    text=text,
                    extractor_version=self.native_extractor_version,
                    confidence=1.0,
                    test_model=False,
                )
            )

        if not regions and fallback_text.strip():
            text = "\n".join(
                line.strip() for line in fallback_text.splitlines() if line.strip()
            )
            bbox = BoundingBox(0.0, 0.0, 1.0, 1.0)
            regions.append(
                Region(
                    region_id=_stable_id(
                        "region",
                        source_sha256,
                        page_number,
                        starting_order,
                        text,
                    ),
                    page_number=page_number,
                    reading_order=starting_order,
                    bounding_box=bbox,
                    content_type="text",
                    text=text,
                    extractor_version=self.native_extractor_version,
                    confidence=1.0,
                    test_model=False,
                )
            )

        for table in tables:
            order = starting_order + len(regions)
            regions.append(
                Region(
                    region_id=_stable_id("region", table.table_id),
                    page_number=page_number,
                    reading_order=order,
                    bounding_box=table.bounding_box,
                    content_type="table",
                    text=table.normalized_text,
                    extractor_version=table.extractor_version,
                    confidence=1.0,
                    test_model=False,
                )
            )
        return regions, tables

    @staticmethod
    def _group_words_into_lines(
        words: Iterable[dict[str, object]],
    ) -> Iterable[list[dict[str, object]]]:
        ordered = sorted(words, key=lambda word: (float(word["top"]), float(word["x0"])))
        current: list[dict[str, object]] = []
        current_top: float | None = None
        for word in ordered:
            top = float(word["top"])
            if current and current_top is not None and abs(top - current_top) > 3.0:
                yield sorted(current, key=lambda item: float(item["x0"]))
                current = []
                current_top = None
            current.append(word)
            current_top = top if current_top is None else (current_top + top) / 2.0
        if current:
            yield sorted(current, key=lambda item: float(item["x0"]))

    def _ocr_page(
        self,
        *,
        safe_file: SafeFile,
        page_number: int,
        ocr_provider: OCRProviderPort,
        starting_order: int,
    ) -> list[Region]:
        results = ocr_provider.recognize(
            source_sha256=safe_file.original_sha256,
            page_number=page_number,
            image_bytes=b"",
        )
        return [
            Region(
                region_id=_stable_id(
                    "region",
                    safe_file.original_sha256,
                    page_number,
                    index,
                    result.text,
                    result.bounding_box.as_list(),
                ),
                page_number=page_number,
                reading_order=starting_order + index,
                bounding_box=result.bounding_box,
                content_type=result.content_type,
                text=result.text.strip(),
                extractor_version=ocr_provider.model_version,
                confidence=result.confidence,
                test_model=ocr_provider.test_provider,
            )
            for index, result in enumerate(results)
            if result.text.strip()
        ]

    def _parse_image(
        self,
        safe_file: SafeFile,
        ocr_provider: OCRProviderPort,
    ) -> ParsedDocument:
        regions = self._ocr_page(
            safe_file=safe_file,
            page_number=1,
            ocr_provider=ocr_provider,
            starting_order=0,
        )
        if not regions:
            raise ProcessingError("VALIDATION_FAILED", "OCR returned no readable regions")
        return ParsedDocument(
            page_count=1,
            regions=tuple(regions),
            tables=(),
            extractor_version=ocr_provider.model_version,
            test_model=ocr_provider.test_provider,
        )
