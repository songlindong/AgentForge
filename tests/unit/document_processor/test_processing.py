from __future__ import annotations

from dataclasses import replace
from math import sqrt
from pathlib import Path
import unittest

from agentforge_document_processor import (
    FileSecurityPolicy,
    FinancialClauseChunker,
    HarnessMalwareScanner,
    HarnessOCRProvider,
    HashEmbeddingProvider,
    MultimodalDocumentParser,
    ProcessingError,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "harness" / "fixtures"


class DocumentProcessingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = FileSecurityPolicy()
        self.scanner = HarnessMalwareScanner()
        self.parser = MultimodalDocumentParser()
        self.ocr = HarnessOCRProvider()

    def safe_file(self, relative: str, media_type: str):
        path = FIXTURES / relative
        return self.policy.validate(
            filename=path.name,
            declared_media_type=media_type,
            data=path.read_bytes(),
            malware_scanner=self.scanner,
        )

    def test_text_pdf_extracts_regions_and_table_with_provenance(self) -> None:
        safe_file = self.safe_file(
            "documents/synthetic-loan-policy.pdf",
            "application/pdf",
        )
        parsed = self.parser.parse(safe_file, ocr_provider=self.ocr)

        self.assertEqual(parsed.page_count, 2)
        self.assertGreater(len(parsed.regions), 0)
        self.assertEqual(len(parsed.tables), 1)
        self.assertIn("期次", parsed.tables[0].normalized_text)
        self.assertTrue(
            all(
                0.0 <= value <= 1.0
                for region in parsed.regions
                for value in region.bounding_box.as_list()
            )
        )
        self.assertTrue(
            all(region.extractor_version == "1.0.0" for region in parsed.regions)
        )

    def test_scanned_pdf_uses_registered_ocr_result(self) -> None:
        safe_file = self.safe_file(
            "documents/synthetic-scan-contract.pdf",
            "application/pdf",
        )
        parsed = self.parser.parse(safe_file, ocr_provider=self.ocr)

        self.assertTrue(parsed.test_model)
        self.assertTrue(all(region.test_model for region in parsed.regions))
        self.assertIn(
            "最终审批结果以人工审核记录为准。",
            {region.text for region in parsed.regions},
        )

    def test_png_is_sanitized_before_ocr(self) -> None:
        safe_file = self.safe_file(
            "images/synthetic-contract-screenshot.png",
            "image/png",
        )
        self.assertTrue(safe_file.exif_removed)
        self.assertEqual(len(safe_file.original_sha256), 64)
        self.assertEqual(len(safe_file.stored_sha256), 64)
        self.assertTrue(safe_file.data.startswith(b"\x89PNG\r\n\x1a\n"))
        parsed = self.parser.parse(safe_file, ocr_provider=self.ocr)
        self.assertIn(
            "回答应定位到本区域，而不是整页泛化。",
            {region.text for region in parsed.regions},
        )

    def test_magic_mismatch_and_path_traversal_are_rejected(self) -> None:
        mismatch = FIXTURES / "security" / "mime-mismatch.jpg"
        with self.assertRaises(ProcessingError) as mismatch_error:
            self.policy.validate(
                filename=mismatch.name,
                declared_media_type="image/jpeg",
                data=mismatch.read_bytes(),
                malware_scanner=self.scanner,
            )
        self.assertEqual(mismatch_error.exception.code, "UNSUPPORTED_MEDIA_TYPE")

        source = FIXTURES / "documents" / "synthetic-loan-policy.pdf"
        with self.assertRaises(ProcessingError) as path_error:
            self.policy.validate(
                filename="../policy.pdf",
                declared_media_type="application/pdf",
                data=source.read_bytes(),
                malware_scanner=self.scanner,
            )
        self.assertEqual(path_error.exception.code, "VALIDATION_FAILED")

    def test_production_rejects_test_scanner(self) -> None:
        source = FIXTURES / "documents" / "synthetic-loan-policy.pdf"
        with self.assertRaises(ProcessingError) as error:
            self.policy.validate(
                filename=source.name,
                declared_media_type="application/pdf",
                data=source.read_bytes(),
                malware_scanner=self.scanner,
                profile="production",
            )
        self.assertEqual(error.exception.code, "VALIDATION_FAILED")

    def test_chunk_and_embedding_are_deterministic(self) -> None:
        safe_file = self.safe_file(
            "documents/synthetic-loan-policy.pdf",
            "application/pdf",
        )
        parsed = self.parser.parse(safe_file, ocr_provider=self.ocr)
        chunker = FinancialClauseChunker(max_characters=800)
        kwargs = {
            "tenant_id": "tenant-a",
            "knowledge_base_id": "kb-a",
            "document_id": "doc-a",
            "document_version": 1,
        }
        first = chunker.chunk(parsed, **kwargs)
        second = chunker.chunk(parsed, **kwargs)
        self.assertEqual(first, second)
        self.assertTrue(all(chunk.sources for chunk in first))

        provider = HashEmbeddingProvider(dimension=64)
        batch = provider.embed(tuple(chunk.text for chunk in first))
        self.assertEqual(len(batch.vectors), len(first))
        for vector in batch.vectors:
            self.assertTrue(any(value != 0.0 for value in vector))
            self.assertAlmostEqual(
                sqrt(sum(value * value for value in vector)),
                1.0,
                places=6,
            )
        self.assertEqual(batch, provider.embed(tuple(chunk.text for chunk in first)))

    def test_unknown_image_is_not_fabricated_by_harness_ocr(self) -> None:
        safe_file = self.safe_file(
            "images/synthetic-contract-photo.jpg",
            "image/jpeg",
        )
        unknown = replace(safe_file, original_sha256="0" * 64)
        with self.assertRaises(ProcessingError) as error:
            self.parser.parse(unknown, ocr_provider=self.ocr)
        self.assertEqual(error.exception.code, "DEPENDENCY_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
