"""Pydantic schemas and models for OpenAPI ingestion and endpoint normalization."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ParameterMetadata(BaseModel):
    """Metadata for an API parameter (path, query, header, cookie)."""

    name: str
    location: str = Field(description="Parameter location: path, query, header, or cookie")
    required: bool = False
    description: Optional[str] = None
    schema_type: Optional[str] = None


class RequestBodyMetadata(BaseModel):
    """Metadata for an operation request body."""

    required: bool = False
    description: Optional[str] = None
    content_types: List[str] = Field(default_factory=list)
    schema_ref: Optional[str] = None


class ResponseMetadata(BaseModel):
    """Metadata for an operation response."""

    status_code: str
    description: Optional[str] = None
    content_types: List[str] = Field(default_factory=list)
    schema_ref: Optional[str] = None


class NormalizedEndpoint(BaseModel):
    """Normalized endpoint representation for event intelligence and downstream caching."""

    id: str = Field(description="Deterministic endpoint identifier (hash of doc + method + path)")
    document_id: str = Field(description="SHA-256 provenance hash of the source specification")
    service_name: str
    path: str
    method: str = Field(description="Uppercase HTTP method (GET, POST, PUT, DELETE, etc.)")
    operation_id: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    parameters: List[ParameterMetadata] = Field(default_factory=list)
    request_body: Optional[RequestBodyMetadata] = None
    responses: List[ResponseMetadata] = Field(default_factory=list)
    source_file: Optional[str] = None
    extracted_at: str


class DocumentMetadata(BaseModel):
    """Normalized metadata for the ingested API specification."""

    document_id: str = Field(description="Deterministic SHA-256 hash of document content")
    title: str
    version: str
    description: Optional[str] = None
    service_name: str
    spec_format: str = Field(description="Spec format: openapi_3 or swagger_2")
    spec_version: str
    base_urls: List[str] = Field(default_factory=list)
    filename: Optional[str] = None
    file_size_bytes: int = 0


class IngestionResponse(BaseModel):
    """Standardized response schema for API specification ingestion."""

    success: bool
    message: str
    document: Optional[DocumentMetadata] = None
    endpoints_count: int = 0
    endpoints: List[NormalizedEndpoint] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class IngestionSummaryResponse(BaseModel):
    """Lightweight response summarizing the ingestion without returning entire endpoint array."""

    success: bool
    message: str
    document: Optional[DocumentMetadata] = None
    endpoints_count: int = 0
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str = "healthy"
    service: str
    version: str
    uptime_seconds: float
    mongodb_connected: bool = False
