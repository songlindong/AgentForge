from __future__ import annotations

from hashlib import sha256

from agentforge_document_processor.models import BoundingBox

from .models import (
    IndexedChunk,
    IngestionJob,
    OutboxRecord,
    StoredDocument,
    utc_now,
)


def event_envelope(record: OutboxRecord) -> dict[str, object]:
    return {
        "event_id": record.event_id,
        "event_type": record.event_type,
        "event_version": "1.0.0",
        "tenant_id": record.tenant_id,
        "partition_key": record.partition_key,
        "idempotency_key": record.idempotency_key,
        "correlation_id": record.correlation_id,
        "producer": "knowledge-service",
        "occurred_at": record.created_at.isoformat(),
        "trace_id": record.trace_id,
        "attempt": record.attempt,
        "data": record.data,
    }


def chunk_set_id(chunks: tuple[IndexedChunk, ...]) -> str:
    material = "|".join(chunk.chunk.chunk_uid for chunk in chunks)
    return f"chunkset_{sha256(material.encode('utf-8')).hexdigest()[:32]}"


def bounding_box_payload(box: BoundingBox) -> dict[str, object]:
    """Serialize normalized parser coordinates to the public contract shape."""
    return {
        "x": box.x0,
        "y": box.y0,
        "width": box.x1 - box.x0,
        "height": box.y1 - box.y0,
        "coordinate_space": "normalized_0_1",
    }


def document_uploaded(
    job: IngestionJob,
    document: StoredDocument,
) -> dict[str, object]:
    safe_file = document.safe_file
    return {
        **_document_base(job, document.object_key),
        "media_type": safe_file.media_type,
        "sha256": safe_file.stored_sha256,
        "byte_size": safe_file.byte_size,
        "page_count": safe_file.page_count,
        "security_scan_status": "accepted",
        "exif_removed": safe_file.exif_removed,
        "uploaded_at": utc_now().isoformat(),
    }


def document_parsed(
    job: IngestionJob,
    document: StoredDocument,
    *,
    regions: tuple[object, ...],
    extractor_version: str,
    page_count: int,
) -> dict[str, object]:
    region_payloads = []
    for region in regions:
        region_payloads.append(
            {
                "region_id": region.region_id,
                "page_number": region.page_number,
                "bounding_box": bounding_box_payload(region.bounding_box),
                "content_type": region.content_type,
                "artifact_ref": (
                    f"artifact://documents/{job.document_id}/versions/"
                    f"{job.document_version}/regions/{region.region_id}"
                ),
                "confidence": region.confidence,
            }
        )
    return {
        **_document_base(job, document.object_key),
        "extractor_model_version": extractor_version,
        "page_count": page_count,
        "regions": region_payloads,
        "ocr_artifact_ref": (
            f"artifact://documents/{job.document_id}/versions/"
            f"{job.document_version}/ocr"
        ),
        "layout_artifact_ref": (
            f"artifact://documents/{job.document_id}/versions/"
            f"{job.document_version}/layout"
        ),
        "table_artifact_ref": (
            f"artifact://documents/{job.document_id}/versions/"
            f"{job.document_version}/tables"
        ),
        "parsed_at": utc_now().isoformat(),
    }


def document_chunked(
    job: IngestionJob,
    document: StoredDocument,
    chunks: tuple[IndexedChunk, ...],
) -> dict[str, object]:
    first = chunks[0]
    current_chunk_set = chunk_set_id(chunks)
    return {
        **_document_base(job, document.object_key),
        "chunk_set_id": current_chunk_set,
        "chunker_version": first.chunk.chunker_version,
        "chunk_count": len(chunks),
        "chunk_manifest_ref": (
            f"artifact://documents/{job.document_id}/versions/"
            f"{job.document_version}/chunks/{current_chunk_set}"
        ),
        "chunked_at": utc_now().isoformat(),
    }


def embedding_requested(
    job: IngestionJob,
    document: StoredDocument,
    chunks: tuple[IndexedChunk, ...],
) -> dict[str, object]:
    first = chunks[0]
    return {
        **_document_base(job, document.object_key),
        "chunk_set_id": chunk_set_id(chunks),
        "embedding_model_id": first.embedding_model_id,
        "embedding_model_version": first.embedding_model_version,
        "dimension": len(first.embedding),
        "requested_at": utc_now().isoformat(),
    }


def knowledge_version_published(
    job: IngestionJob,
    *,
    bm25_index_version: str,
    vector_index_version: str,
) -> dict[str, object]:
    if job.knowledge_version is None:
        raise ValueError("knowledge version is required")
    return {
        "tenant_id": job.tenant_id,
        "knowledge_base_id": job.knowledge_base_id,
        "knowledge_version": job.knowledge_version,
        "document_id": job.document_id,
        "document_version": job.document_version,
        "bm25_index_version": bm25_index_version,
        "vector_index_version": vector_index_version,
        "trace_id": job.trace_id,
        "published_at": utc_now().isoformat(),
    }


def _document_base(
    job: IngestionJob,
    source_object_key: str,
) -> dict[str, object]:
    return {
        "tenant_id": job.tenant_id,
        "document_id": job.document_id,
        "document_version": job.document_version,
        "job_id": job.job_id,
        "attempt": job.attempt,
        "trace_id": job.trace_id,
        "source_object_key": source_object_key,
    }
