"""Unit tests for OpenAPI and Swagger document parser."""

import pytest
from src.core.parser import (
    DocumentParser,
    SpecificationParseError,
    SpecificationValidationError,
    UnsupportedSpecificationError,
)


def test_parse_valid_openapi3_json(load_fixture):
    raw = load_fixture("valid_openapi3.json")
    spec_dict = DocumentParser.parse_raw_content(raw, filename="orders.json")
    assert isinstance(spec_dict, dict)

    metadata, validated_spec = DocumentParser.identify_and_validate_spec(
        spec_dict, raw, filename="orders.json"
    )
    assert metadata.title == "Order Management Service"
    assert metadata.version == "1.4.0"
    assert metadata.spec_format == "openapi_3"
    assert metadata.spec_version == "3.0.3"
    assert metadata.service_name == "order-management-service"
    assert len(metadata.base_urls) == 1
    assert metadata.base_urls[0] == "https://api.orders.example.com/v1"
    assert len(metadata.document_id) == 64  # SHA-256 hex


def test_parse_valid_openapi3_yaml(load_fixture):
    raw = load_fixture("valid_openapi3.yaml")
    spec_dict = DocumentParser.parse_raw_content(raw, filename="payments.yaml")
    assert isinstance(spec_dict, dict)

    metadata, validated_spec = DocumentParser.identify_and_validate_spec(
        spec_dict, raw, filename="payments.yaml"
    )
    assert metadata.title == "Payment Gateway Service"
    assert metadata.version == "2.1.0"
    assert metadata.spec_format == "openapi_3"
    assert metadata.spec_version == "3.1.0"
    assert "https://payments.example.com/api" in metadata.base_urls


def test_parse_valid_swagger2_json(load_fixture):
    raw = load_fixture("valid_swagger2.json")
    spec_dict = DocumentParser.parse_raw_content(raw, filename="inventory.json")

    metadata, validated_spec = DocumentParser.identify_and_validate_spec(
        spec_dict, raw, filename="inventory.json"
    )
    assert metadata.title == "Inventory Management API"
    assert metadata.spec_format == "swagger_2"
    assert metadata.spec_version == "2.0"
    assert "http://inventory.internal.svc:8080/v2" in metadata.base_urls


def test_parse_malformed_json(load_fixture):
    raw = load_fixture("malformed.json")
    with pytest.raises(SpecificationParseError) as exc_info:
        DocumentParser.parse_raw_content(raw, filename="broken.json")
    assert "Malformed JSON" in str(exc_info.value)


def test_parse_malformed_yaml(load_fixture):
    raw = load_fixture("malformed.yaml")
    with pytest.raises(SpecificationParseError) as exc_info:
        DocumentParser.parse_raw_content(raw, filename="broken.yaml")
    assert "Malformed YAML" in str(exc_info.value)


def test_parse_empty_content():
    with pytest.raises(SpecificationParseError) as exc_info:
        DocumentParser.parse_raw_content(b"   ", filename="empty.json")
    assert "empty" in str(exc_info.value).lower()


def test_parse_missing_required_fields(load_fixture):
    raw = load_fixture("missing_required.json")
    spec_dict = DocumentParser.parse_raw_content(raw)
    with pytest.raises(SpecificationValidationError) as exc_info:
        DocumentParser.identify_and_validate_spec(spec_dict, raw)
    assert "title" in str(exc_info.value).lower() or "paths" in str(exc_info.value).lower()


def test_parse_unsupported_version(load_fixture):
    raw = load_fixture("unsupported_version.json")
    spec_dict = DocumentParser.parse_raw_content(raw)
    with pytest.raises(UnsupportedSpecificationError) as exc_info:
        DocumentParser.identify_and_validate_spec(spec_dict, raw)
    assert "Unsupported OpenAPI version '4.0.0'" in str(exc_info.value)
