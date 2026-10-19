"""FastAPI routes for specification ingestion and normalized endpoint retrieval."""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from ..config import settings
from ..core.normalizer import EndpointNormalizer
from ..core.parser import (
    DocumentParser,
    SpecificationParseError,
    SpecificationValidationError,
    UnsupportedSpecificationError,
)
from ..core.security import SecurityValidationError
from ..models.schemas import (
    DocumentMetadata,
    IngestionResponse,
    NormalizedEndpoint,
)
from ..persistence.repository import BaseDocumentRepository
from .dependencies import get_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Ingestion"])


@router.post(
    "/ingest",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest and normalize OpenAPI or Swagger specification",
)
async def ingest_specification(
    file: UploadFile = File(...),
    repo: BaseDocumentRepository = Depends(get_repository),
) -> IngestionResponse:
    """Uploads an OpenAPI 3.x or Swagger 2.0 JSON or YAML document.

    Validates specification syntax and structural security, extracts
    normalized microservice endpoints, and stores the records for event correlation.
    """
    filename = file.filename or "uploaded_spec"

    try:
        raw_content = await file.read()
    except Exception as err:
        logger.error(f"Failed to read uploaded file: {err}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file stream: {str(err)}",
        )

    # 1. Enforce file size limit
    if len(raw_content) > settings.MAX_UPLOAD_SIZE_BYTES:
        max_mb = settings.MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowable upload size of {max_mb:.1f} MB (uploaded {len(raw_content)} bytes).",
        )

    # 2. Parse file content (JSON or YAML)
    try:
        spec_dict = DocumentParser.parse_raw_content(raw_content, filename=filename)
    except SpecificationParseError as parse_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(parse_err),
        )

    # 3. Security and structural validation
    try:
        metadata, validated_spec = DocumentParser.identify_and_validate_spec(
            spec=spec_dict, raw_content=raw_content, filename=filename
        )
    except SecurityValidationError as sec_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security Validation Failed: {str(sec_err)}",
        )
    except UnsupportedSpecificationError as unsupp_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(unsupp_err),
        )
    except SpecificationValidationError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(val_err),
        )

    # 4. Extract and normalize endpoints
    endpoints = EndpointNormalizer.normalize_specification(
        metadata=metadata, spec_dict=validated_spec
    )

    # 5. Persist to repository
    try:
        repo.save_document(metadata)
        repo.save_endpoints(endpoints)
    except Exception as persist_err:
        logger.error(f"Persistence error: {persist_err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist ingested endpoints: {str(persist_err)}",
        )

    warnings: List[str] = []
    if len(endpoints) == 0:
        warnings.append("Document parsed successfully, but zero HTTP operations were identified.")

    return IngestionResponse(
        success=True,
        message=f"Successfully ingested {metadata.spec_format.upper()} specification '{metadata.title}' with {len(endpoints)} endpoint(s).",
        document=metadata,
        endpoints_count=len(endpoints),
        endpoints=endpoints,
        warnings=warnings,
        errors=[],
    )


@router.get(
    "/documents",
    response_model=List[DocumentMetadata],
    summary="List all ingested API documentation specifications",
)
def list_documents(
    repo: BaseDocumentRepository = Depends(get_repository),
) -> List[DocumentMetadata]:
    """Retrieves all ingested specification records."""
    return repo.list_documents()


@router.get(
    "/documents/{document_id}",
    response_model=DocumentMetadata,
    summary="Get document metadata by ID",
)
def get_document(
    document_id: str,
    repo: BaseDocumentRepository = Depends(get_repository),
) -> DocumentMetadata:
    """Retrieves document metadata by its deterministic hash ID."""
    doc = repo.get_document(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )
    return doc


@router.get(
    "/documents/{document_id}/endpoints",
    response_model=List[NormalizedEndpoint],
    summary="Get normalized endpoints for a document",
)
def get_document_endpoints(
    document_id: str,
    repo: BaseDocumentRepository = Depends(get_repository),
) -> List[NormalizedEndpoint]:
    """Retrieves normalized endpoints extracted from a specific document."""
    doc = repo.get_document(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )
    return repo.get_endpoints_by_document(document_id)


@router.get(
    "/endpoints",
    response_model=List[NormalizedEndpoint],
    summary="List normalized endpoints across services",
)
def list_endpoints(
    service_name: Optional[str] = None,
    repo: BaseDocumentRepository = Depends(get_repository),
) -> List[NormalizedEndpoint]:
    """Retrieves all normalized endpoints, optionally filtered by service name."""
    return repo.list_endpoints(service_name=service_name)
