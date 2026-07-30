CREATE TABLE IF NOT EXISTS knowledge_ingestion_jobs (
    tenant_id VARCHAR(128) NOT NULL,
    job_id VARCHAR(128) NOT NULL,
    knowledge_base_id VARCHAR(128) NOT NULL,
    document_id VARCHAR(128) NOT NULL,
    document_version INT UNSIGNED NOT NULL,
    logical_filename VARCHAR(255) NOT NULL,
    request_digest CHAR(64) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    sensitive_content_policy VARCHAR(16) NOT NULL,
    trace_id CHAR(32) NOT NULL,
    state VARCHAR(32) NOT NULL,
    attempt TINYINT UNSIGNED NOT NULL DEFAULT 1,
    max_attempts TINYINT UNSIGNED NOT NULL DEFAULT 3,
    retryable BOOLEAN NOT NULL DEFAULT FALSE,
    error_code VARCHAR(64) NULL,
    error_summary VARCHAR(1024) NULL,
    failure_stage VARCHAR(32) NULL,
    knowledge_version VARCHAR(64) NULL,
    page_count INT UNSIGNED NOT NULL DEFAULT 0,
    region_count INT UNSIGNED NOT NULL DEFAULT 0,
    table_count INT UNSIGNED NOT NULL DEFAULT 0,
    chunk_count INT UNSIGNED NOT NULL DEFAULT 0,
    bm25_indexed INT UNSIGNED NOT NULL DEFAULT 0,
    vectors_indexed INT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (tenant_id, job_id),
    UNIQUE KEY uq_ingestion_idempotency (tenant_id, idempotency_key),
    KEY idx_ingestion_document (tenant_id, document_id, document_version),
    KEY idx_ingestion_logical (
        tenant_id,
        knowledge_base_id,
        logical_filename,
        document_version
    ),
    KEY idx_ingestion_state (tenant_id, state, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS knowledge_documents (
    tenant_id VARCHAR(128) NOT NULL,
    knowledge_base_id VARCHAR(128) NOT NULL,
    document_id VARCHAR(128) NOT NULL,
    document_version INT UNSIGNED NOT NULL,
    logical_filename VARCHAR(255) NOT NULL,
    media_type VARCHAR(64) NOT NULL,
    object_key VARCHAR(1024) NOT NULL,
    original_sha256 CHAR(64) NOT NULL,
    stored_sha256 CHAR(64) NOT NULL,
    byte_size BIGINT UNSIGNED NOT NULL,
    page_count INT UNSIGNED NOT NULL,
    exif_removed BOOLEAN NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (tenant_id, document_id, document_version),
    UNIQUE KEY uq_document_object (tenant_id, object_key(512)),
    KEY idx_document_knowledge (tenant_id, knowledge_base_id, document_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS knowledge_job_commands (
    tenant_id VARCHAR(128) NOT NULL,
    job_id VARCHAR(128) NOT NULL,
    command_type VARCHAR(32) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    resulting_attempt TINYINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (tenant_id, job_id, command_type, idempotency_key),
    CONSTRAINT fk_command_job
        FOREIGN KEY (tenant_id, job_id)
        REFERENCES knowledge_ingestion_jobs (tenant_id, job_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS knowledge_document_pages (
    tenant_id VARCHAR(128) NOT NULL,
    document_id VARCHAR(128) NOT NULL,
    document_version INT UNSIGNED NOT NULL,
    page_number INT UNSIGNED NOT NULL,
    extractor_version VARCHAR(64) NOT NULL,
    test_model BOOLEAN NOT NULL,
    PRIMARY KEY (tenant_id, document_id, document_version, page_number),
    CONSTRAINT fk_page_document
        FOREIGN KEY (tenant_id, document_id, document_version)
        REFERENCES knowledge_documents (tenant_id, document_id, document_version)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS knowledge_regions (
    tenant_id VARCHAR(128) NOT NULL,
    document_id VARCHAR(128) NOT NULL,
    document_version INT UNSIGNED NOT NULL,
    region_id VARCHAR(128) NOT NULL,
    page_number INT UNSIGNED NOT NULL,
    reading_order INT UNSIGNED NOT NULL,
    bounding_box JSON NOT NULL,
    content_type VARCHAR(32) NOT NULL,
    content_text LONGTEXT NOT NULL,
    extractor_version VARCHAR(64) NOT NULL,
    confidence DECIMAL(7,6) NOT NULL,
    test_model BOOLEAN NOT NULL,
    PRIMARY KEY (tenant_id, document_id, document_version, region_id),
    UNIQUE KEY uq_region_order (
        tenant_id,
        document_id,
        document_version,
        reading_order
    ),
    CONSTRAINT fk_region_document
        FOREIGN KEY (tenant_id, document_id, document_version)
        REFERENCES knowledge_documents (tenant_id, document_id, document_version)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS knowledge_tables (
    tenant_id VARCHAR(128) NOT NULL,
    document_id VARCHAR(128) NOT NULL,
    document_version INT UNSIGNED NOT NULL,
    table_id VARCHAR(128) NOT NULL,
    page_number INT UNSIGNED NOT NULL,
    bounding_box JSON NOT NULL,
    cells JSON NOT NULL,
    normalized_text LONGTEXT NOT NULL,
    extractor_version VARCHAR(64) NOT NULL,
    test_model BOOLEAN NOT NULL,
    PRIMARY KEY (tenant_id, document_id, document_version, table_id),
    CONSTRAINT fk_table_document
        FOREIGN KEY (tenant_id, document_id, document_version)
        REFERENCES knowledge_documents (tenant_id, document_id, document_version)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    tenant_id VARCHAR(128) NOT NULL,
    knowledge_base_id VARCHAR(128) NOT NULL,
    document_id VARCHAR(128) NOT NULL,
    document_version INT UNSIGNED NOT NULL,
    chunk_uid VARCHAR(80) NOT NULL,
    ordinal INT UNSIGNED NOT NULL,
    content_type VARCHAR(32) NOT NULL,
    content_text LONGTEXT NOT NULL,
    source_object_key VARCHAR(1024) NOT NULL,
    chunker_version VARCHAR(64) NOT NULL,
    extractor_version VARCHAR(64) NOT NULL,
    embedding_model_id VARCHAR(128) NOT NULL,
    embedding_model_version VARCHAR(64) NOT NULL,
    embedding_dimension INT UNSIGNED NOT NULL,
    embedding_json JSON NOT NULL,
    test_model BOOLEAN NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (tenant_id, chunk_uid),
    UNIQUE KEY uq_chunk_order (
        tenant_id,
        document_id,
        document_version,
        ordinal
    ),
    KEY idx_chunk_document (tenant_id, document_id, document_version),
    CONSTRAINT fk_chunk_document
        FOREIGN KEY (tenant_id, document_id, document_version)
        REFERENCES knowledge_documents (tenant_id, document_id, document_version)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS knowledge_chunk_sources (
    tenant_id VARCHAR(128) NOT NULL,
    chunk_uid VARCHAR(80) NOT NULL,
    source_ordinal INT UNSIGNED NOT NULL,
    region_id VARCHAR(128) NOT NULL,
    page_number INT UNSIGNED NOT NULL,
    bounding_box JSON NOT NULL,
    PRIMARY KEY (tenant_id, chunk_uid, source_ordinal),
    CONSTRAINT fk_source_chunk
        FOREIGN KEY (tenant_id, chunk_uid)
        REFERENCES knowledge_chunks (tenant_id, chunk_uid)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS knowledge_versions (
    tenant_id VARCHAR(128) NOT NULL,
    knowledge_base_id VARCHAR(128) NOT NULL,
    knowledge_version VARCHAR(64) NOT NULL,
    sequence_number BIGINT UNSIGNED NOT NULL,
    document_id VARCHAR(128) NOT NULL,
    document_version INT UNSIGNED NOT NULL,
    bm25_index_version VARCHAR(64) NOT NULL,
    vector_index_version VARCHAR(64) NOT NULL,
    chunk_count INT UNSIGNED NOT NULL,
    trace_id CHAR(32) NOT NULL,
    published_at DATETIME(6) NOT NULL,
    PRIMARY KEY (tenant_id, knowledge_base_id, knowledge_version),
    UNIQUE KEY uq_knowledge_sequence (
        tenant_id,
        knowledge_base_id,
        sequence_number
    ),
    KEY idx_version_document (tenant_id, document_id, document_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS knowledge_outbox (
    tenant_id VARCHAR(128) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    partition_key VARCHAR(255) NOT NULL,
    event_type VARCHAR(128) NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    correlation_id VARCHAR(128) NOT NULL,
    attempt INT UNSIGNED NOT NULL,
    trace_id CHAR(32) NOT NULL,
    payload JSON NOT NULL,
    created_at DATETIME(6) NOT NULL,
    published_at DATETIME(6) NULL,
    PRIMARY KEY (tenant_id, event_id),
    KEY idx_outbox_pending (published_at, created_at),
    KEY idx_outbox_tenant (tenant_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS knowledge_inbox (
    tenant_id VARCHAR(128) NOT NULL,
    consumer_name VARCHAR(128) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    processed_at DATETIME(6) NOT NULL,
    PRIMARY KEY (tenant_id, consumer_name, event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
