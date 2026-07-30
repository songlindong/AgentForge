from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from agentforge_document_processor import (
    FileSecurityPolicy,
    FinancialClauseChunker,
    HarnessMalwareScanner,
    HarnessOCRProvider,
    HashEmbeddingProvider,
    InProcessSandbox,
    MultimodalDocumentParser,
)

from .adapters import (
    KafkaEventPublisher,
    MilvusVectorIndex,
    MinioObjectStore,
    OpenSearchKeywordIndex,
)
from .api import ServicePrincipal, StaticServiceAuthenticator, create_app
from .config import IngestionConfig
from .errors import KnowledgeError
from .mysql_repository import MySQLConfig, MySQLKnowledgeRepository
from .pipeline import KnowledgeIngestionPipeline, OutboxPublisher


ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "infra/mysql/migrations/0001_knowledge_ingestion.sql"


def _required(mapping: Mapping[str, str], name: str) -> str:
    value = mapping.get(name, "").strip()
    if not value:
        raise KnowledgeError("VALIDATION_FAILED", f"missing setting: {name}")
    return value


def _integer(mapping: Mapping[str, str], name: str, default: int) -> int:
    raw = mapping.get(name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise KnowledgeError(
            "VALIDATION_FAILED", f"setting must be an integer: {name}"
        ) from exc


@dataclass(frozen=True)
class RuntimeSettings:
    profile: str
    mysql: MySQLConfig
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    opensearch_url: str
    milvus_uri: str
    kafka_bootstrap_servers: tuple[str, ...]
    service_tokens_json: str = ""
    api_host: str = "127.0.0.1"
    api_port: int = 8087

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, str]) -> RuntimeSettings:
        mysql_host = mapping.get("MYSQL_HOST", "127.0.0.1").strip()
        minio_host = mapping.get("MINIO_HOST", "127.0.0.1").strip()
        opensearch_host = mapping.get("OPENSEARCH_HOST", "127.0.0.1").strip()
        milvus_host = mapping.get("MILVUS_HOST", "127.0.0.1").strip()
        kafka_host = mapping.get("KAFKA_HOST", "127.0.0.1").strip()
        kafka_value = mapping.get(
            "KAFKA_BOOTSTRAP_SERVERS",
            f"{kafka_host}:{_integer(mapping, 'KAFKA_PORT', 9092)}",
        )
        bootstrap_servers = tuple(
            value.strip() for value in kafka_value.split(",") if value.strip()
        )
        if not bootstrap_servers:
            raise KnowledgeError(
                "VALIDATION_FAILED", "Kafka bootstrap servers are missing"
            )
        return cls(
            profile=mapping.get("AGENTFORGE_PROFILE", "local").strip(),
            mysql=MySQLConfig(
                host=mysql_host,
                port=_integer(mapping, "MYSQL_PORT", 3307),
                user=_required(mapping, "MYSQL_USER"),
                password=_required(mapping, "MYSQL_PASSWORD"),
                database=_required(mapping, "MYSQL_DATABASE"),
            ),
            minio_endpoint=mapping.get(
                "MINIO_ENDPOINT",
                f"{minio_host}:{_integer(mapping, 'MINIO_API_PORT', 9000)}",
            ).strip(),
            minio_access_key=_required(mapping, "MINIO_ROOT_USER"),
            minio_secret_key=_required(mapping, "MINIO_ROOT_PASSWORD"),
            minio_bucket=_required(mapping, "AGENTFORGE_BUCKET"),
            opensearch_url=mapping.get(
                "OPENSEARCH_URL",
                f"http://{opensearch_host}:"
                f"{_integer(mapping, 'OPENSEARCH_PORT', 9200)}",
            ).strip(),
            milvus_uri=mapping.get(
                "MILVUS_URI",
                f"http://{milvus_host}:{_integer(mapping, 'MILVUS_PORT', 19530)}",
            ).strip(),
            kafka_bootstrap_servers=bootstrap_servers,
            service_tokens_json=mapping.get(
                "AGENTFORGE_SERVICE_TOKENS_JSON", ""
            ).strip(),
            api_host=mapping.get("KNOWLEDGE_API_HOST", "127.0.0.1").strip(),
            api_port=_integer(mapping, "KNOWLEDGE_API_PORT", 8087),
        )


@dataclass(frozen=True)
class RuntimeComponents:
    settings: RuntimeSettings
    repository: MySQLKnowledgeRepository
    pipeline: KnowledgeIngestionPipeline
    authenticator: StaticServiceAuthenticator
    outbox: OutboxPublisher

    def app(self) -> Any:
        return create_app(
            pipeline=self.pipeline,
            authenticator=self.authenticator,
        )


def build_repository(settings: RuntimeSettings) -> MySQLKnowledgeRepository:
    return MySQLKnowledgeRepository(settings.mysql)


def apply_migration(settings: RuntimeSettings) -> None:
    build_repository(settings).apply_migration(MIGRATION.read_text(encoding="utf-8"))


def build_authenticator(settings: RuntimeSettings) -> StaticServiceAuthenticator:
    if settings.profile == "production":
        raise KnowledgeError(
            "VALIDATION_FAILED",
            "production authentication belongs to the verified OIDC integration",
        )
    if not settings.service_tokens_json:
        raise KnowledgeError(
            "VALIDATION_FAILED", "local/test service token mapping is missing"
        )
    try:
        values = json.loads(settings.service_tokens_json)
        principals = {
            token: ServicePrincipal(
                tenant_id=str(definition["tenant_id"]),
                subject=str(definition["subject"]),
                scopes=frozenset(str(scope) for scope in definition["scopes"]),
            )
            for token, definition in values.items()
        }
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise KnowledgeError(
            "VALIDATION_FAILED", "service token mapping is invalid"
        ) from exc
    if not principals:
        raise KnowledgeError(
            "VALIDATION_FAILED", "service token mapping cannot be empty"
        )
    return StaticServiceAuthenticator(principals)


def build_runtime(settings: RuntimeSettings) -> RuntimeComponents:
    repository = build_repository(settings)
    keyword_index = OpenSearchKeywordIndex(hosts=[settings.opensearch_url])
    vector_index = MilvusVectorIndex(uri=settings.milvus_uri)
    pipeline = KnowledgeIngestionPipeline(
        repository=repository,
        object_store=MinioObjectStore(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
        ),
        keyword_index=keyword_index,
        vector_index=vector_index,
        security_policy=FileSecurityPolicy(),
        malware_scanner=HarnessMalwareScanner(),
        parser=MultimodalDocumentParser(),
        ocr_provider=HarnessOCRProvider(),
        chunker=FinancialClauseChunker(),
        embedding_provider=HashEmbeddingProvider(),
        sandbox=InProcessSandbox(),
        config=IngestionConfig(profile=settings.profile),
    )
    return RuntimeComponents(
        settings=settings,
        repository=repository,
        pipeline=pipeline,
        authenticator=build_authenticator(settings),
        outbox=OutboxPublisher(
            repository=repository,
            publisher=KafkaEventPublisher(
                bootstrap_servers=list(settings.kafka_bootstrap_servers)
            ),
        ),
    )
