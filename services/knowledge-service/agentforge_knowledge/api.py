from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from secrets import token_hex
from typing import Annotated

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .errors import KnowledgeError
from .models import IngestionJob, IngestionRequest
from .pipeline import KnowledgeIngestionPipeline


TRACEPARENT = re.compile(
    r"^00-(?P<trace_id>[0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$"
)


@dataclass(frozen=True)
class ServicePrincipal:
    tenant_id: str
    subject: str
    scopes: frozenset[str]


class StaticServiceAuthenticator:
    """Local/Test service-token mapping; production must use verified OIDC claims."""

    def __init__(self, tokens: Mapping[str, ServicePrincipal]) -> None:
        self._tokens = dict(tokens)

    def authenticate(self, authorization: str | None) -> ServicePrincipal:
        if not authorization or not authorization.startswith("Bearer "):
            raise KnowledgeError(
                "AUTHENTICATION_REQUIRED",
                "service bearer token is required",
            )
        token = authorization.removeprefix("Bearer ").strip()
        principal = self._tokens.get(token)
        if principal is None:
            raise KnowledgeError(
                "AUTHENTICATION_REQUIRED",
                "service bearer token is invalid",
            )
        if "knowledge:write" not in principal.scopes:
            raise KnowledgeError(
                "FORBIDDEN",
                "service identity lacks knowledge:write",
            )
        return principal


def _trace_id(traceparent: str | None) -> str:
    if traceparent:
        match = TRACEPARENT.fullmatch(traceparent)
        if match:
            return match.group("trace_id")
    return token_hex(16)


def _job_payload(job: IngestionJob) -> dict[str, object]:
    payload: dict[str, object] = {
        "job_id": job.job_id,
        "knowledge_base_id": job.knowledge_base_id,
        "document_id": job.document_id,
        "document_version": job.document_version,
        "state": str(job.state),
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "retryable": job.retryable,
        "stage_counts": {
            "pages": job.counts.pages,
            "regions": job.counts.regions,
            "tables": job.counts.tables,
            "chunks": job.counts.chunks,
            "bm25_indexed": job.counts.bm25_indexed,
            "vectors_indexed": job.counts.vectors_indexed,
        },
        "trace_id": job.trace_id,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }
    if job.knowledge_version is not None:
        payload["knowledge_version"] = job.knowledge_version
    if job.error_code is not None:
        payload["error_code"] = job.error_code
    if job.error_summary is not None:
        payload["error_summary"] = job.error_summary
    return payload


ERROR_STATUS = {
    "AUTHENTICATION_REQUIRED": 401,
    "FORBIDDEN": 403,
    "TENANT_MISMATCH": 403,
    "RESOURCE_NOT_FOUND": 404,
    "IDEMPOTENCY_CONFLICT": 409,
    "VERSION_CONFLICT": 409,
    "INVALID_STATE_TRANSITION": 409,
    "PAYLOAD_TOO_LARGE": 413,
    "UNSUPPORTED_MEDIA_TYPE": 415,
    "MALWARE_DETECTED": 422,
    "SENSITIVE_CONTENT_BLOCKED": 422,
    "RATE_LIMITED": 429,
    "DEPENDENCY_TIMEOUT": 503,
    "DEPENDENCY_UNAVAILABLE": 503,
    "INDEX_COUNT_MISMATCH": 503,
}


def create_app(
    *,
    pipeline: KnowledgeIngestionPipeline,
    authenticator: StaticServiceAuthenticator,
) -> FastAPI:
    app = FastAPI(
        title="AgentForge Internal Knowledge Ingestion API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    async def principal(
        authorization: Annotated[str | None, Header()] = None,
    ) -> ServicePrincipal:
        return authenticator.authenticate(authorization)

    @app.middleware("http")
    async def trace_context(request: Request, call_next: object) -> object:
        request.state.trace_id = _trace_id(request.headers.get("traceparent"))
        response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Trace-ID"] = request.state.trace_id
        return response

    @app.exception_handler(KnowledgeError)
    async def knowledge_error(request: Request, exc: KnowledgeError) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", token_hex(16))
        body: dict[str, object] = {
            "error_id": f"err_{token_hex(12)}",
            "code": exc.code,
            "message": str(exc),
            "retryable": exc.retryable,
            "trace_id": trace_id,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        if exc.retryable:
            body["retry_after_ms"] = 1000
        return JSONResponse(
            status_code=ERROR_STATUS.get(exc.code, 400),
            content=body,
            headers={"X-Trace-ID": trace_id},
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del exc
        trace_id = getattr(request.state, "trace_id", token_hex(16))
        return JSONResponse(
            status_code=400,
            content={
                "error_id": f"err_{token_hex(12)}",
                "code": "VALIDATION_FAILED",
                "message": "request does not satisfy the ingestion contract",
                "retryable": False,
                "trace_id": trace_id,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            },
            headers={"X-Trace-ID": trace_id},
        )

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/internal/v1/knowledge/ingestions", status_code=202)
    async def create_ingestion(
        request: Request,
        knowledge_base_id: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        background_tasks: BackgroundTasks,
        service_principal: ServicePrincipal = Depends(principal),
        sensitive_content_policy: Annotated[str, Form()] = "reject",
    ) -> JSONResponse:
        data = await _read_limited(file, pipeline.security_policy.max_bytes)
        job = pipeline.stage(
            IngestionRequest(
                tenant_id=service_principal.tenant_id,
                knowledge_base_id=knowledge_base_id,
                filename=file.filename or "",
                declared_media_type=file.content_type or "",
                data=data,
                idempotency_key=idempotency_key,
                trace_id=request.state.trace_id,
                sensitive_content_policy=sensitive_content_policy,
            )
        )
        if str(job.state) == "stored":
            background_tasks.add_task(
                pipeline.process_staged,
                service_principal.tenant_id,
                job.job_id,
            )
        return JSONResponse(
            status_code=202,
            content=_job_payload(job),
            headers={"X-Trace-ID": request.state.trace_id},
        )

    @app.get("/internal/v1/knowledge/ingestions/{job_id}")
    async def get_ingestion(
        request: Request,
        job_id: str,
        service_principal: ServicePrincipal = Depends(principal),
    ) -> JSONResponse:
        job = pipeline.repository.get_job(service_principal.tenant_id, job_id)
        return JSONResponse(
            content=_job_payload(job),
            headers={"X-Trace-ID": request.state.trace_id},
        )

    @app.post(
        "/internal/v1/knowledge/ingestions/{job_id}/retry",
        status_code=202,
    )
    async def retry_ingestion(
        request: Request,
        job_id: str,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        service_principal: ServicePrincipal = Depends(principal),
    ) -> JSONResponse:
        job = pipeline.retry(
            service_principal.tenant_id,
            job_id,
            idempotency_key=idempotency_key,
        )
        return JSONResponse(
            status_code=202,
            content=_job_payload(job),
            headers={"X-Trace-ID": request.state.trace_id},
        )

    return app


async def _read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(min(1024 * 1024, max_bytes + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise KnowledgeError("PAYLOAD_TOO_LARGE", "file exceeds byte limit")
        chunks.append(chunk)
    return b"".join(chunks)
