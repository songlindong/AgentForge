from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath

from .errors import ProcessingError
from .models import SafeFile
from .ports import MalwareScannerPort


MEDIA_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}


def detect_media_type(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


@dataclass(frozen=True)
class HarnessMalwareScanner:
    test_provider: bool = True

    def scan(self, *, filename: str, data: bytes) -> bool:
        del filename, data
        return True


@dataclass(frozen=True)
class FileSecurityPolicy:
    max_bytes: int = 100 * 1024 * 1024
    max_pdf_pages: int = 500
    max_image_pixels: int = 40_000_000
    max_decompression_ratio: float = 200.0

    def validate(
        self,
        *,
        filename: str,
        declared_media_type: str,
        data: bytes,
        malware_scanner: MalwareScannerPort,
        profile: str = "test",
    ) -> SafeFile:
        safe_name = self._validate_filename(filename)
        if not data:
            raise ProcessingError("VALIDATION_FAILED", "file is empty")
        if len(data) > self.max_bytes:
            raise ProcessingError("PAYLOAD_TOO_LARGE", "file exceeds byte limit")

        detected_media_type = detect_media_type(data)
        if detected_media_type is None or detected_media_type != declared_media_type:
            raise ProcessingError(
                "UNSUPPORTED_MEDIA_TYPE",
                "declared media type does not match file signature",
            )
        expected_extension = MEDIA_EXTENSIONS[detected_media_type]
        supplied_extension = PurePosixPath(safe_name.lower()).suffix
        valid_extensions = {expected_extension}
        if detected_media_type == "image/jpeg":
            valid_extensions.add(".jpeg")
        if supplied_extension not in valid_extensions:
            raise ProcessingError(
                "UNSUPPORTED_MEDIA_TYPE",
                "filename extension does not match file signature",
            )

        if profile == "production" and malware_scanner.test_provider:
            raise ProcessingError(
                "VALIDATION_FAILED",
                "production requires a non-test malware scanner",
            )
        if not malware_scanner.scan(filename=safe_name, data=data):
            raise ProcessingError("MALWARE_DETECTED", "file security scan rejected")

        original_digest = sha256(data).hexdigest()
        if detected_media_type == "application/pdf":
            page_count = self._inspect_pdf(data)
            stored_data = data
            exif_removed = False
        else:
            page_count = 1
            stored_data = self._sanitize_image(data, detected_media_type)
            exif_removed = True

        return SafeFile(
            filename=safe_name,
            media_type=detected_media_type,
            extension=expected_extension.lstrip("."),
            data=stored_data,
            original_sha256=original_digest,
            stored_sha256=sha256(stored_data).hexdigest(),
            byte_size=len(stored_data),
            page_count=page_count,
            exif_removed=exif_removed,
        )

    @staticmethod
    def _validate_filename(filename: str) -> str:
        if (
            not filename
            or len(filename) > 255
            or "\x00" in filename
            or "/" in filename
            or "\\" in filename
            or filename in {".", ".."}
            or any(ord(character) < 32 for character in filename)
        ):
            raise ProcessingError("VALIDATION_FAILED", "unsafe filename")
        return filename

    def _inspect_pdf(self, data: bytes) -> int:
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise ProcessingError("VALIDATION_FAILED", "encrypted PDF is not accepted")
            page_count = len(reader.pages)
        except ProcessingError:
            raise
        except Exception as exc:
            raise ProcessingError("VALIDATION_FAILED", "PDF cannot be decoded") from exc
        if page_count < 1:
            raise ProcessingError("VALIDATION_FAILED", "PDF has no pages")
        if page_count > self.max_pdf_pages:
            raise ProcessingError("PAYLOAD_TOO_LARGE", "PDF exceeds page limit")
        return page_count

    def _sanitize_image(self, data: bytes, media_type: str) -> bytes:
        try:
            from PIL import Image

            with Image.open(BytesIO(data)) as image:
                image.load()
                width, height = image.size
                if width <= 0 or height <= 0:
                    raise ProcessingError("VALIDATION_FAILED", "image has invalid size")
                pixels = width * height
                if pixels > self.max_image_pixels:
                    raise ProcessingError("PAYLOAD_TOO_LARGE", "image exceeds pixel limit")
                if pixels * max(len(image.getbands()), 1) / max(len(data), 1) > self.max_decompression_ratio:
                    raise ProcessingError(
                        "PAYLOAD_TOO_LARGE",
                        "image exceeds decompression ratio limit",
                    )

                output = BytesIO()
                if media_type == "image/jpeg":
                    cleaned = image.convert("RGB")
                    cleaned.save(
                        output,
                        format="JPEG",
                        quality=90,
                        subsampling=0,
                        optimize=False,
                        progressive=False,
                    )
                else:
                    cleaned = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                    cleaned.save(output, format="PNG", optimize=False, compress_level=9)
                return output.getvalue()
        except ProcessingError:
            raise
        except Exception as exc:
            raise ProcessingError("VALIDATION_FAILED", "image cannot be decoded") from exc
