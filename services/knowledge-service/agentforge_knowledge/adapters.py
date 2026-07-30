from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from typing import Any

from .errors import KnowledgeError
from .event_payloads import event_envelope
from .models import IndexedChunk, OutboxRecord


def _source_payload(chunk: IndexedChunk) -> list[dict[str, Any]]:
    return [
        {
            "region_id": source.region_id,
            "page_number": source.page_number,
            "bounding_box": source.bounding_box.as_list(),
        }
        for source in chunk.chunk.sources
    ]


@dataclass
class MinioObjectStore:
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    secure: bool = False

    def __post_init__(self) -> None:
        try:
            from minio import Minio

            self._client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )
            if not self._client.bucket_exists(self.bucket):
                self._client.make_bucket(self.bucket)
        except Exception as exc:
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE",
                "MinIO client initialization failed",
                retryable=True,
            ) from exc

    def put_if_absent(
        self,
        *,
        tenant_id: str,
        object_key: str,
        data: bytes,
        media_type: str,
        sha256_hex: str,
    ) -> None:
        if not object_key.startswith(f"tenants/{tenant_id}/"):
            raise KnowledgeError("TENANT_MISMATCH", "object key tenant mismatch")
        try:
            existing = self._client.stat_object(self.bucket, object_key)
            existing_digest = existing.metadata.get("x-amz-meta-sha256")
            if existing_digest != sha256_hex:
                raise KnowledgeError(
                    "VERSION_CONFLICT", "object key already contains another digest"
                )
            return
        except KnowledgeError:
            raise
        except Exception as exc:
            response = getattr(exc, "code", "")
            if response not in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                raise KnowledgeError(
                    "DEPENDENCY_UNAVAILABLE",
                    "MinIO stat failed",
                    retryable=True,
                ) from exc
        try:
            self._client.put_object(
                self.bucket,
                object_key,
                BytesIO(data),
                length=len(data),
                content_type=media_type,
                metadata={"sha256": sha256_hex, "tenant-id": tenant_id},
            )
        except Exception as exc:
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE", "MinIO write failed", retryable=True
            ) from exc

    def get(self, *, tenant_id: str, object_key: str) -> bytes:
        if not object_key.startswith(f"tenants/{tenant_id}/"):
            raise KnowledgeError("TENANT_MISMATCH", "object key tenant mismatch")
        response = None
        try:
            response = self._client.get_object(self.bucket, object_key)
            return response.read()
        except Exception as exc:
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE", "MinIO read failed", retryable=True
            ) from exc
        finally:
            if response is not None:
                response.close()
                response.release_conn()


@dataclass
class OpenSearchKeywordIndex:
    hosts: list[str]
    index_name: str = "agentforge-knowledge-chunks-v1"
    index_version: str = "1.0.0"

    def __post_init__(self) -> None:
        try:
            from opensearchpy import OpenSearch

            self._client = OpenSearch(self.hosts)
            if not self._client.indices.exists(index=self.index_name):
                self._client.indices.create(
                    index=self.index_name,
                    body={
                        "settings": {
                            "number_of_shards": 1,
                            "number_of_replicas": 0,
                        },
                        "mappings": {
                            "dynamic": "strict",
                            "properties": {
                                "tenant_id": {"type": "keyword"},
                                "knowledge_base_id": {"type": "keyword"},
                                "document_id": {"type": "keyword"},
                                "document_version": {"type": "integer"},
                                "chunk_uid": {"type": "keyword"},
                                "ordinal": {"type": "integer"},
                                "content_type": {"type": "keyword"},
                                "text": {"type": "text"},
                                "source_object_key": {
                                    "type": "keyword",
                                    "index": False,
                                },
                                "sources": {
                                    "type": "object",
                                    "enabled": False,
                                },
                                "extractor_version": {"type": "keyword"},
                                "embedding_model_id": {"type": "keyword"},
                                "embedding_model_version": {"type": "keyword"},
                                "test_model": {"type": "boolean"},
                                "index_version": {"type": "keyword"},
                            },
                        },
                    },
                )
        except Exception as exc:
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE",
                "OpenSearch initialization failed",
                retryable=True,
            ) from exc

    def upsert(
        self,
        *,
        tenant_id: str,
        chunks: tuple[IndexedChunk, ...] | list[IndexedChunk],
    ) -> int:
        try:
            from opensearchpy.helpers import bulk

            actions = []
            for chunk in chunks:
                if chunk.tenant_id != tenant_id:
                    raise KnowledgeError(
                        "TENANT_MISMATCH", "keyword chunk tenant mismatch"
                    )
                actions.append(
                    {
                        "_op_type": "index",
                        "_index": self.index_name,
                        "_id": chunk.chunk.chunk_uid,
                        "_source": {
                            "tenant_id": tenant_id,
                            "knowledge_base_id": chunk.knowledge_base_id,
                            "document_id": chunk.document_id,
                            "document_version": chunk.document_version,
                            "chunk_uid": chunk.chunk.chunk_uid,
                            "ordinal": chunk.chunk.ordinal,
                            "content_type": chunk.chunk.content_type,
                            "text": chunk.chunk.text,
                            "source_object_key": chunk.source_object_key,
                            "sources": _source_payload(chunk),
                            "extractor_version": chunk.extractor_version,
                            "embedding_model_id": chunk.embedding_model_id,
                            "embedding_model_version": chunk.embedding_model_version,
                            "test_model": chunk.test_model,
                            "index_version": self.index_version,
                        },
                    }
                )
            successful, _ = bulk(
                self._client,
                actions,
                refresh="wait_for",
                raise_on_error=True,
            )
            return successful
        except KnowledgeError:
            raise
        except Exception as exc:
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE",
                "OpenSearch write failed",
                retryable=True,
            ) from exc

    def count_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> int:
        try:
            result = self._client.count(
                index=self.index_name,
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"tenant_id": tenant_id}},
                                {"term": {"document_id": document_id}},
                                {"term": {"document_version": document_version}},
                            ]
                        }
                    }
                },
            )
            return int(result["count"])
        except Exception as exc:
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE",
                "OpenSearch count failed",
                retryable=True,
            ) from exc


@dataclass
class MilvusVectorIndex:
    uri: str
    token: str = ""
    collection_name: str = "agentforge_knowledge_chunks_v1"
    index_version: str = "1.0.0"

    def __post_init__(self) -> None:
        try:
            from pymilvus import MilvusClient

            parameters: dict[str, str] = {"uri": self.uri}
            if self.token:
                parameters["token"] = self.token
            self._client = MilvusClient(**parameters)
        except Exception as exc:
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE",
                "Milvus client initialization failed",
                retryable=True,
            ) from exc

    def _ensure_collection(self, dimension: int) -> None:
        try:
            if self._client.has_collection(self.collection_name):
                return
            from pymilvus import DataType, MilvusClient

            schema = MilvusClient.create_schema(
                auto_id=False,
                enable_dynamic_field=False,
            )
            schema.add_field(
                "chunk_uid",
                DataType.VARCHAR,
                is_primary=True,
                max_length=80,
            )
            schema.add_field("tenant_id", DataType.VARCHAR, max_length=128)
            schema.add_field("knowledge_base_id", DataType.VARCHAR, max_length=128)
            schema.add_field("document_id", DataType.VARCHAR, max_length=128)
            schema.add_field("document_version", DataType.INT64)
            schema.add_field("ordinal", DataType.INT64)
            schema.add_field("source_json", DataType.VARCHAR, max_length=8192)
            schema.add_field("extractor_version", DataType.VARCHAR, max_length=64)
            schema.add_field("embedding_model_id", DataType.VARCHAR, max_length=128)
            schema.add_field(
                "embedding_model_version", DataType.VARCHAR, max_length=64
            )
            schema.add_field("test_model", DataType.BOOL)
            schema.add_field("index_version", DataType.VARCHAR, max_length=64)
            schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dimension)
            index_params = self._client.prepare_index_params()
            index_params.add_index(
                field_name="embedding",
                index_type="AUTOINDEX",
                metric_type="COSINE",
            )
            self._client.create_collection(
                collection_name=self.collection_name,
                schema=schema,
                index_params=index_params,
            )
        except Exception as exc:
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE",
                "Milvus collection initialization failed",
                retryable=True,
            ) from exc

    def upsert(
        self,
        *,
        tenant_id: str,
        chunks: tuple[IndexedChunk, ...] | list[IndexedChunk],
    ) -> int:
        if not chunks:
            return 0
        dimension = len(chunks[0].embedding)
        self._ensure_collection(dimension)
        rows = []
        for chunk in chunks:
            if chunk.tenant_id != tenant_id:
                raise KnowledgeError(
                    "TENANT_MISMATCH", "vector chunk tenant mismatch"
                )
            if len(chunk.embedding) != dimension:
                raise KnowledgeError(
                    "VALIDATION_FAILED", "embedding dimensions are inconsistent"
                )
            rows.append(
                {
                    "chunk_uid": chunk.chunk.chunk_uid,
                    "tenant_id": tenant_id,
                    "knowledge_base_id": chunk.knowledge_base_id,
                    "document_id": chunk.document_id,
                    "document_version": chunk.document_version,
                    "ordinal": chunk.chunk.ordinal,
                    "source_json": json.dumps(
                        _source_payload(chunk),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    "extractor_version": chunk.extractor_version,
                    "embedding_model_id": chunk.embedding_model_id,
                    "embedding_model_version": chunk.embedding_model_version,
                    "test_model": chunk.test_model,
                    "index_version": self.index_version,
                    "embedding": list(chunk.embedding),
                }
            )
        try:
            result = self._client.upsert(
                collection_name=self.collection_name,
                data=rows,
            )
            return int(result.get("upsert_count", len(rows)))
        except Exception as exc:
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE", "Milvus write failed", retryable=True
            ) from exc

    def count_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        document_version: int,
    ) -> int:
        safe_tenant = tenant_id.replace("\\", "\\\\").replace('"', '\\"')
        safe_document = document_id.replace("\\", "\\\\").replace('"', '\\"')
        expression = (
            f'tenant_id == "{safe_tenant}" and '
            f'document_id == "{safe_document}" and '
            f"document_version == {int(document_version)}"
        )
        try:
            result = self._client.query(
                collection_name=self.collection_name,
                filter=expression,
                output_fields=["count(*)"],
                consistency_level="Strong",
            )
            return int(result[0]["count(*)"]) if result else 0
        except Exception as exc:
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE", "Milvus count failed", retryable=True
            ) from exc


@dataclass
class KafkaEventPublisher:
    bootstrap_servers: list[str]
    client_id: str = "agentforge-knowledge-outbox"
    timeout_seconds: int = 10

    def __post_init__(self) -> None:
        try:
            from kafka import KafkaProducer

            self._producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                client_id=self.client_id,
                acks="all",
                retries=5,
                max_in_flight_requests_per_connection=1,
                key_serializer=lambda value: value.encode("utf-8"),
                value_serializer=lambda value: json.dumps(
                    value,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8"),
            )
        except Exception as exc:
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE",
                "Kafka producer initialization failed",
                retryable=True,
            ) from exc

    def publish(self, record: OutboxRecord) -> None:
        envelope = event_envelope(record)
        try:
            traceparent = (
                f"00-{record.trace_id}-"
                f"{sha256(record.event_id.encode('utf-8')).hexdigest()[:16]}-01"
            )
            future = self._producer.send(
                record.topic,
                key=record.partition_key,
                value=envelope,
                headers=[
                    ("content_type", b"application/json"),
                    (
                        "schema_id",
                        (
                            "contracts/asyncapi/kafka.asyncapi.json#/"
                            f"components/messages/{record.event_type}"
                        ).encode("utf-8"),
                    ),
                    ("tenant_id", record.tenant_id.encode("utf-8")),
                    ("traceparent", traceparent.encode("ascii")),
                    (
                        "idempotency_key",
                        record.idempotency_key.encode("utf-8"),
                    ),
                ],
            )
            future.get(timeout=self.timeout_seconds)
        except Exception as exc:
            raise KnowledgeError(
                "DEPENDENCY_UNAVAILABLE",
                "Kafka publish failed",
                retryable=True,
            ) from exc
