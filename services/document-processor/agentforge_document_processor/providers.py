from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from hashlib import sha256
from math import sqrt
import struct
from typing import TypeVar

from .errors import ProcessingError
from .models import BoundingBox, EmbeddingBatch, OCRRegion


HARNESS_OCR_REGIONS: dict[str, tuple[OCRRegion, ...]] = {
    "479ae491b97c16a38636d144a0580ce9194a2624ade6102c98f9a089ed463371": (
        OCRRegion("合成贷款合同节选", BoundingBox(0.28, 0.07, 0.72, 0.13), "title"),
        OCRRegion(
            "第一条 本文件只用于固定 OCR、版面和引用测试。",
            BoundingBox(0.10, 0.20, 0.90, 0.29),
        ),
        OCRRegion(
            "第二条 提前还款需提前三个工作日提交申请。",
            BoundingBox(0.10, 0.29, 0.90, 0.38),
        ),
        OCRRegion(
            "第三条 动态利率与审批状态应从受控业务接口获取。",
            BoundingBox(0.10, 0.38, 0.90, 0.47),
        ),
        OCRRegion(
            "最终审批结果以人工审核记录为准。",
            BoundingBox(0.10, 0.49, 0.90, 0.63),
        ),
    ),
    "4d326a092e9469ad303deb4cb6519a5330962ce3d1fdbee9c86bcd6bd76e1f2a": (
        OCRRegion("合同局部截图", BoundingBox(0.05, 0.02, 0.48, 0.10), "title"),
        OCRRegion("提前还款条款", BoundingBox(0.10, 0.25, 0.55, 0.34), "title"),
        OCRRegion(
            "借款人需提前三个工作日提交申请。动态费用以受控业务接口返回为准。",
            BoundingBox(0.10, 0.34, 0.90, 0.56),
        ),
        OCRRegion(
            "回答应定位到本区域，而不是整页泛化。",
            BoundingBox(0.10, 0.55, 0.90, 0.70),
        ),
    ),
    "64713b996ecc8e57a12858b2861a6000b99131911051ec047451a4abe35ce10d": (
        OCRRegion("合成合同拍照页", BoundingBox(0.25, 0.07, 0.75, 0.15), "title"),
        OCRRegion(
            "1. 固定文本用于 OCR 质量校验。",
            BoundingBox(0.15, 0.24, 0.82, 0.33),
        ),
        OCRRegion(
            "2. 金融动态数据不得由模型臆测。",
            BoundingBox(0.15, 0.37, 0.82, 0.46),
        ),
        OCRRegion(
            "3. 原图、页码与区域坐标必须保留。",
            BoundingBox(0.15, 0.50, 0.82, 0.59),
        ),
    ),
}


@dataclass(frozen=True)
class HarnessOCRProvider:
    model_version: str = "1.0.0-test"
    test_provider: bool = True

    def recognize(
        self,
        *,
        source_sha256: str,
        page_number: int,
        image_bytes: bytes,
    ) -> Sequence[OCRRegion]:
        del image_bytes
        regions = HARNESS_OCR_REGIONS.get(source_sha256)
        if regions is None:
            raise ProcessingError(
                "DEPENDENCY_UNAVAILABLE",
                "Harness OCR has no registered result for this file",
                retryable=False,
            )
        if page_number != 1:
            raise ProcessingError(
                "VALIDATION_FAILED",
                "Harness OCR fixture only contains one scanned page",
            )
        return regions


@dataclass(frozen=True)
class HashEmbeddingProvider:
    dimension: int = 64
    model_id: str = "hash-embedding"
    model_version: str = "1.0.0-test"
    test_provider: bool = True

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        vectors = tuple(self._vector(text) for text in texts)
        return EmbeddingBatch(
            vectors=vectors,
            model_id=self.model_id,
            model_version=self.model_version,
            dimension=self.dimension,
            test_model=True,
        )

    def _vector(self, text: str) -> tuple[float, ...]:
        if not text.strip():
            raise ProcessingError("VALIDATION_FAILED", "cannot embed empty text")
        values: list[float] = []
        counter = 0
        while len(values) < self.dimension:
            digest = sha256(f"{counter}:{text}".encode("utf-8")).digest()
            for offset in range(0, len(digest), 4):
                unsigned = struct.unpack(">I", digest[offset : offset + 4])[0]
                values.append((unsigned / 4_294_967_295.0) * 2.0 - 1.0)
                if len(values) == self.dimension:
                    break
            counter += 1
        norm = sqrt(sum(value * value for value in values))
        return tuple(value / norm for value in values)


T = TypeVar("T")


@dataclass(frozen=True)
class InProcessSandbox:
    test_provider: bool = True

    def execute(self, operation: Callable[[], T], *, timeout_seconds: int) -> T:
        if timeout_seconds < 1:
            raise ProcessingError("VALIDATION_FAILED", "timeout must be positive")
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="document-test")
        future = executor.submit(operation)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeout as exc:
            future.cancel()
            raise ProcessingError(
                "DEPENDENCY_TIMEOUT",
                "document processing exceeded its deadline",
                retryable=True,
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
