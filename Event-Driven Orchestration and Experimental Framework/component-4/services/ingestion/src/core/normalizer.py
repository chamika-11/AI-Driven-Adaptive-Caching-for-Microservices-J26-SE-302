"""Deterministic Endpoint Normalizer for OpenAPI and Swagger specifications."""

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional, Set, Tuple

from ..models.schemas import (
    DocumentMetadata,
    NormalizedEndpoint,
    ParameterMetadata,
    RequestBodyMetadata,
    ResponseMetadata,
)

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}


class EndpointNormalizer:
    """Extracts and normalizes endpoint records from valid OpenAPI / Swagger documents."""

    @classmethod
    def generate_endpoint_id(cls, document_id: str, method: str, path: str) -> str:
        """Generates a deterministic unique hash for an endpoint."""
        token = f"{document_id}:{method.upper()}:{path.strip()}"
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]

    @classmethod
    def extract_schema_ref(cls, schema_obj: Any) -> Optional[str]:
        """Extracts $ref string if present in schema dictionary."""
        if isinstance(schema_obj, dict):
            if "$ref" in schema_obj and isinstance(schema_obj["$ref"], str):
                return schema_obj["$ref"]
            # Check items or properties for ref
            if "items" in schema_obj and isinstance(schema_obj["items"], dict):
                return cls.extract_schema_ref(schema_obj["items"])
        return None

    @classmethod
    def extract_schema_type(cls, param_obj: Dict[str, Any], is_openapi3: bool) -> Optional[str]:
        """Extracts data type for a parameter."""
        if is_openapi3:
            schema = param_obj.get("schema")
            if isinstance(schema, dict) and "type" in schema:
                return str(schema["type"])
        else:
            # Swagger 2.0 has type directly on param
            if "type" in param_obj:
                return str(param_obj["type"])
        return None

    @classmethod
    def normalize_parameters(
        cls,
        path_level_params: List[Any],
        op_level_params: List[Any],
        is_openapi3: bool,
    ) -> List[ParameterMetadata]:
        """Merges path-level and operation-level parameters (operation overrides path-level)."""
        merged_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

        # 1. Path-level
        for p in path_level_params:
            if isinstance(p, dict) and "name" in p and "in" in p:
                key = (str(p["name"]).strip(), str(p["in"]).strip())
                merged_map[key] = p

        # 2. Operation-level (overrides path-level with same (name, in))
        for p in op_level_params:
            if isinstance(p, dict) and "name" in p and "in" in p:
                key = (str(p["name"]).strip(), str(p["in"]).strip())
                merged_map[key] = p

        result: List[ParameterMetadata] = []
        for (name, loc), p in sorted(merged_map.items()):
            # Exclude Swagger 2.0 body params since they become request_body
            if not is_openapi3 and loc == "body":
                continue

            desc = p.get("description")
            result.append(
                ParameterMetadata(
                    name=name,
                    location=loc,
                    required=bool(p.get("required", False or loc == "path")),
                    description=str(desc).strip() if desc is not None else None,
                    schema_type=cls.extract_schema_type(p, is_openapi3),
                )
            )

        return result

    @classmethod
    def normalize_request_body(
        cls,
        op_dict: Dict[str, Any],
        op_level_params: List[Any],
        default_consumes: List[str],
        is_openapi3: bool,
    ) -> Optional[RequestBodyMetadata]:
        """Extracts request body for OpenAPI 3 (requestBody) or Swagger 2 (in: body)."""
        if is_openapi3:
            rb = op_dict.get("requestBody")
            if not isinstance(rb, dict):
                return None

            content = rb.get("content", {})
            content_types: List[str] = []
            schema_ref: Optional[str] = None

            if isinstance(content, dict):
                for ct, ct_val in content.items():
                    content_types.append(str(ct))
                    if schema_ref is None and isinstance(ct_val, dict):
                        schema = ct_val.get("schema")
                        schema_ref = cls.extract_schema_ref(schema)

            desc = rb.get("description")
            return RequestBodyMetadata(
                required=bool(rb.get("required", False)),
                description=str(desc).strip() if desc is not None else None,
                content_types=content_types,
                schema_ref=schema_ref,
            )
        else:
            # Swagger 2.0 body param
            body_params = [
                p for p in op_level_params if isinstance(p, dict) and p.get("in") == "body"
            ]
            if not body_params:
                return None

            bp = body_params[0]
            desc = bp.get("description")
            schema = bp.get("schema")
            schema_ref = cls.extract_schema_ref(schema)

            consumes = op_dict.get("consumes")
            if isinstance(consumes, list) and consumes:
                content_types = [str(c) for c in consumes]
            else:
                content_types = [str(c) for c in default_consumes] if default_consumes else ["application/json"]

            return RequestBodyMetadata(
                required=bool(bp.get("required", False)),
                description=str(desc).strip() if desc is not None else None,
                content_types=content_types,
                schema_ref=schema_ref,
            )

    @classmethod
    def normalize_responses(
        cls, responses_dict: Any, default_produces: List[str], is_openapi3: bool
    ) -> List[ResponseMetadata]:
        """Normalizes response status codes, descriptions, and content types."""
        if not isinstance(responses_dict, dict):
            return []

        results: List[ResponseMetadata] = []
        for code, resp in sorted(responses_dict.items(), key=lambda x: str(x[0])):
            if not isinstance(resp, dict):
                continue

            desc = resp.get("description")
            content_types: List[str] = []
            schema_ref: Optional[str] = None

            if is_openapi3:
                content = resp.get("content", {})
                if isinstance(content, dict):
                    for ct, ct_val in content.items():
                        content_types.append(str(ct))
                        if schema_ref is None and isinstance(ct_val, dict):
                            schema = ct_val.get("schema")
                            schema_ref = cls.extract_schema_ref(schema)
            else:
                schema = resp.get("schema")
                schema_ref = cls.extract_schema_ref(schema)
                produces = resp.get("produces")
                if isinstance(produces, list) and produces:
                    content_types = [str(p) for p in produces]
                elif default_produces:
                    content_types = [str(p) for p in default_produces]

            results.append(
                ResponseMetadata(
                    status_code=str(code),
                    description=str(desc).strip() if desc is not None else None,
                    content_types=content_types,
                    schema_ref=schema_ref,
                )
            )

        return results

    @classmethod
    def normalize_specification(
        cls, metadata: DocumentMetadata, spec_dict: Dict[str, Any]
    ) -> List[NormalizedEndpoint]:
        """Extracts and normalizes all HTTP endpoints from the specification."""
        is_openapi3 = metadata.spec_format == "openapi_3"
        paths_obj = spec_dict.get("paths", {})
        default_consumes = spec_dict.get("consumes", []) if not is_openapi3 else []
        default_produces = spec_dict.get("produces", []) if not is_openapi3 else []

        extracted_at = datetime.now(timezone.utc).isoformat()
        endpoints: List[NormalizedEndpoint] = []
        seen_endpoint_keys: Set[Tuple[str, str]] = set()

        # Sort paths for deterministic ordering
        for path_key in sorted(paths_obj.keys()):
            path_item = paths_obj[path_key]
            if not isinstance(path_item, dict):
                continue

            # Extract path-level parameters
            path_level_params = path_item.get("parameters", [])
            if not isinstance(path_level_params, list):
                path_level_params = []

            # Process HTTP methods separately
            for method_key in sorted(path_item.keys()):
                method_lower = method_key.lower().strip()
                if method_lower not in HTTP_METHODS:
                    continue  # Ignore non-HTTP operations ($ref, summary, description, etc.)

                op_dict = path_item[method_key]
                if not isinstance(op_dict, dict):
                    continue

                method_upper = method_lower.upper()
                dedup_key = (method_upper, path_key.strip())
                if dedup_key in seen_endpoint_keys:
                    continue
                seen_endpoint_keys.add(dedup_key)

                # Operation ID
                op_id = op_dict.get("operationId")
                if op_id is not None:
                    op_id = str(op_id).strip()

                # Summary & description
                summary = op_dict.get("summary")
                if summary is not None:
                    summary = str(summary).strip()

                desc = op_dict.get("description")
                if desc is not None:
                    desc = str(desc).strip()

                # Tags
                tags_raw = op_dict.get("tags", [])
                tags = [str(t).strip() for t in tags_raw if isinstance(t, (str, int))] if isinstance(tags_raw, list) else []

                # Operation-level parameters
                op_params = op_dict.get("parameters", [])
                if not isinstance(op_params, list):
                    op_params = []

                parameters = cls.normalize_parameters(path_level_params, op_params, is_openapi3)
                request_body = cls.normalize_request_body(op_dict, op_params, default_consumes, is_openapi3)
                responses = cls.normalize_responses(op_dict.get("responses"), default_produces, is_openapi3)

                endpoint_id = cls.generate_endpoint_id(metadata.document_id, method_upper, path_key)

                endpoints.append(
                    NormalizedEndpoint(
                        id=endpoint_id,
                        document_id=metadata.document_id,
                        service_name=metadata.service_name,
                        path=path_key.strip(),
                        method=method_upper,
                        operation_id=op_id,
                        summary=summary,
                        description=desc,
                        tags=tags,
                        parameters=parameters,
                        request_body=request_body,
                        responses=responses,
                        source_file=metadata.filename,
                        extracted_at=extracted_at,
                    )
                )

        return endpoints
