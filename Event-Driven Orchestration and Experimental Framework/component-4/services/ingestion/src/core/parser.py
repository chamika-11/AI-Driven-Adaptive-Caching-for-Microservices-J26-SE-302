"""OpenAPI 3.x and Swagger 2.0 Document Parser."""

import hashlib
import json
import logging
from typing import Any, Dict, Tuple, Optional
import yaml

from ..models.schemas import DocumentMetadata
from .security import SafeSpecScanner, SecurityValidationError

logger = logging.getLogger(__name__)


class SpecificationParseError(Exception):
    """Raised when specification document is malformed or invalid."""

    pass


class SpecificationValidationError(Exception):
    """Raised when specification is missing required OpenAPI/Swagger structural fields."""

    pass


class UnsupportedSpecificationError(Exception):
    """Raised when specification version is unsupported."""

    pass


class DocumentParser:
    """Parses and validates OpenAPI 3.x and Swagger 2.0 specifications."""

    SUPPORTED_OPENAPI_PREFIXES = ("3.0.", "3.1.", "3.0", "3.1")
    SUPPORTED_SWAGGER_VERSIONS = ("2.0",)

    @classmethod
    def compute_document_hash(cls, raw_content: bytes) -> str:
        """Computes deterministic SHA-256 hash of raw document content."""
        return hashlib.sha256(raw_content).hexdigest()

    @classmethod
    def parse_raw_content(cls, raw_content: bytes, filename: Optional[str] = None) -> Dict[str, Any]:
        """Safely parses raw bytes as JSON or YAML without trusting MIME or filename."""
        text = raw_content.decode("utf-8", errors="replace").strip()
        if not text:
            raise SpecificationParseError("Uploaded specification document is empty.")

        # Attempt JSON parse first if it looks like JSON
        if text.startswith("{") or text.startswith("["):
            try:
                data = json.loads(text)
                if not isinstance(data, dict):
                    raise SpecificationParseError("Document root must be a JSON object.")
                return data
            except json.JSONDecodeError as json_err:
                # If it started with '{', treat as broken JSON
                raise SpecificationParseError(f"Malformed JSON specification: {json_err.msg} at line {json_err.lineno}")

        # Attempt safe YAML parse
        try:
            data = yaml.safe_load(text)
            if not isinstance(data, dict):
                raise SpecificationParseError("Document root must be a YAML mapping/object.")
            return data
        except yaml.YAMLError as yaml_err:
            raise SpecificationParseError(f"Malformed YAML specification: {str(yaml_err)}")

    @classmethod
    def identify_and_validate_spec(
        cls, spec: Dict[str, Any], raw_content: bytes, filename: Optional[str] = None
    ) -> Tuple[DocumentMetadata, Dict[str, Any]]:
        """Identifies OpenAPI/Swagger format, checks structural requirements, runs security checks."""
        # 1. Structural security validation (SSRF / external ref scanning)
        SafeSpecScanner.validate_security(spec)

        # 2. Check format & version
        spec_format: str
        spec_version: str

        if "openapi" in spec:
            version_str = str(spec.get("openapi", "")).strip()
            if not any(version_str.startswith(prefix) for prefix in cls.SUPPORTED_OPENAPI_PREFIXES):
                raise UnsupportedSpecificationError(
                    f"Unsupported OpenAPI version '{version_str}'. Supported versions: OpenAPI 3.0.x and 3.1.x."
                )
            spec_format = "openapi_3"
            spec_version = version_str
        elif "swagger" in spec:
            version_str = str(spec.get("swagger", "")).strip()
            if version_str not in cls.SUPPORTED_SWAGGER_VERSIONS:
                raise UnsupportedSpecificationError(
                    f"Unsupported Swagger version '{version_str}'. Supported versions: Swagger 2.0."
                )
            spec_format = "swagger_2"
            spec_version = version_str
        else:
            raise SpecificationValidationError(
                "Document is missing specification identifier ('openapi' or 'swagger' top-level field)."
            )

        # 3. Check required 'info' object
        info = spec.get("info")
        if not isinstance(info, dict):
            raise SpecificationValidationError("Missing or invalid 'info' object in specification.")

        title = info.get("title")
        if not title or not isinstance(title, str) or not title.strip():
            raise SpecificationValidationError("Specification 'info.title' is required and cannot be empty.")
        title = title.strip()

        version = info.get("version")
        if version is None or not str(version).strip():
            raise SpecificationValidationError("Specification 'info.version' is required and cannot be empty.")
        version = str(version).strip()

        description = info.get("description")
        if description is not None:
            description = str(description).strip()

        # 4. Check 'paths' object
        paths = spec.get("paths")
        if paths is None or not isinstance(paths, dict):
            raise SpecificationValidationError("Missing or invalid 'paths' object in specification.")

        # 5. Extract service name (derive from info.title or sanitize title)
        service_name = title.lower().replace(" ", "-").replace("_", "-")

        # 6. Extract base URLs / servers
        base_urls: list[str] = []
        if spec_format == "openapi_3":
            servers = spec.get("servers", [])
            if isinstance(servers, list):
                for s in servers:
                    if isinstance(s, dict) and "url" in s and isinstance(s["url"], str):
                        url_clean = s["url"].strip()
                        if url_clean and url_clean not in base_urls:
                            base_urls.append(url_clean)
        elif spec_format == "swagger_2":
            host = spec.get("host", "").strip()
            base_path = spec.get("basePath", "").strip()
            schemes = spec.get("schemes", ["http"])
            scheme = schemes[0] if isinstance(schemes, list) and schemes else "http"
            if host:
                full_base = f"{scheme}://{host}{base_path}".rstrip("/")
                base_urls.append(full_base)
            elif base_path:
                base_urls.append(base_path)

        doc_hash = cls.compute_document_hash(raw_content)

        metadata = DocumentMetadata(
            document_id=doc_hash,
            title=title,
            version=version,
            description=description,
            service_name=service_name,
            spec_format=spec_format,
            spec_version=spec_version,
            base_urls=base_urls,
            filename=filename,
            file_size_bytes=len(raw_content),
        )

        return metadata, spec
