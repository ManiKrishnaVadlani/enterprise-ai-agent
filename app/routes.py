"""FastAPI routes for health, document management, and grounded questions."""

import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app.auth import get_rate_limited_user
from app.config import Settings
from app.dependencies import get_services
from app.errors import (
    AgentError,
    DocumentNotFoundError,
    InvalidDocumentError,
    ProviderConfigurationError,
    ProviderError,
    StorageError,
)
from app.rag import NO_DOCUMENTS_ANSWER
from app.models import UserRecord
from app.services import ApplicationServices


logger = logging.getLogger(__name__)
router = APIRouter()


class RootResponse(BaseModel):
    message: str
    status: str


class HealthResponse(BaseModel):
    status: str
    application: str


class ReadyResponse(BaseModel):
    status: str
    database: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_id: UUID | None = None

    @field_validator("question")
    @classmethod
    def question_must_contain_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Question must contain non-whitespace text.")
        return cleaned


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: str
    filename: str
    chunk_id: str
    page_number: int | None
    relevance_score: float


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[SourceResponse]


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: str
    filename: str
    ingested_at: datetime
    chunk_count: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


@router.get("/", response_model=RootResponse, summary="Application status")
def read_root(request: Request):
    return {"message": request.app.state.settings.app_name, "status": "running"}


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
def health_check(request: Request):
    return {
        "status": "healthy",
        "application": request.app.state.settings.app_name,
    }


@router.get("/ready", response_model=ReadyResponse, summary="Readiness check")
def readiness_check(
    services: Annotated[ApplicationServices, Depends(get_services)],
):
    services.store.check_ready()
    return {"status": "ready", "database": "ready"}


@router.post(
    "/documents/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and index a PDF or TXT document",
    description=(
        "Send the file bytes as application/octet-stream and set X-Filename "
        "to the plain filename. This streams the body and enforces the upload limit."
    ),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def upload_document(
    request: Request,
    filename: Annotated[str, Header(alias="X-Filename")],
    services: Annotated[ApplicationServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_rate_limited_user)],
):
    settings: Settings = request.app.state.settings
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            content_length = int(declared_length)
        except ValueError as error:
            raise InvalidDocumentError(
                "Content-Length must be a non-negative integer."
            ) from error
        if content_length < 0:
            raise InvalidDocumentError(
                "Content-Length must be a non-negative integer."
            )
        if content_length > settings.max_upload_bytes:
            raise InvalidDocumentError(
                f"The document exceeds the {settings.max_upload_bytes}-byte upload limit."
            )
    upload_limiter = request.app.state.upload_limiter
    if not await run_in_threadpool(upload_limiter.acquire):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upload capacity is busy. Try again shortly.",
            headers={"Retry-After": "1"},
        )
    try:
        content = bytearray()
        async for part in request.stream():
            if len(content) + len(part) > settings.max_upload_bytes:
                raise InvalidDocumentError(
                    f"The document exceeds the {settings.max_upload_bytes}-byte upload limit."
                )
            content.extend(part)
        result = await run_in_threadpool(
            services.documents.ingest,
            filename,
            bytes(content),
            owner_id=current_user.user_id,
        )
    finally:
        upload_limiter.release()
    logger.info("Document ingestion completed.")
    return result


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List indexed documents",
)
def list_documents(
    services: Annotated[ApplicationServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_rate_limited_user)],
):
    documents = services.documents.list_documents(owner_id=current_user.user_id)
    return {"documents": documents, "total": len(documents)}


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and its chunks",
)
def delete_document(
    document_id: UUID,
    services: Annotated[ApplicationServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_rate_limited_user)],
):
    services.documents.delete_document(str(document_id), owner_id=current_user.user_id)
    logger.info("Document deletion completed.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ask", response_model=AskResponse, summary="Ask over indexed documents")
def ask_question(
    request_body: AskRequest,
    services: Annotated[ApplicationServices, Depends(get_services)],
    current_user: Annotated[UserRecord, Depends(get_rate_limited_user)],
):
    logger.info("Ask request received.")
    result = services.rag.answer(
        request_body.question,
        str(request_body.document_id) if request_body.document_id else None,
        owner_id=current_user.user_id,
    )
    if result.answer != NO_DOCUMENTS_ANSWER:
        logger.info("Grounded answer prepared.")
    return {
        "question": request_body.question,
        "answer": result.answer,
        "sources": result.sources,
    }


async def application_error_handler(_request: Request, error: AgentError):
    if isinstance(error, DocumentNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, InvalidDocumentError):
        code = status.HTTP_400_BAD_REQUEST
    elif isinstance(error, ProviderConfigurationError | StorageError):
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(error, ProviderError):
        code = status.HTTP_502_BAD_GATEWAY
    else:
        code = status.HTTP_400_BAD_REQUEST
    return JSONResponse(status_code=code, content={"detail": str(error)})


async def unexpected_error_handler(_request: Request, _error: Exception):
    # Avoid putting document text, questions, provider messages, or secrets in logs.
    logger.error("Unexpected internal error; request could not be completed.")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected server error occurred."},
    )
