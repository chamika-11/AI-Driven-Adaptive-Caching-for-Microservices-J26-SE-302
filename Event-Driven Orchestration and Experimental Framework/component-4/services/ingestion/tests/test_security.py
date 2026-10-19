"""Security and boundary validation tests."""

import pytest
from src.core.parser import DocumentParser, SpecificationParseError
from src.core.security import SafeSpecScanner, SecurityValidationError


def test_reject_unsafe_python_yaml(load_fixture):
    raw = load_fixture("unsafe.yaml")
    # yaml.safe_load should reject !!python/object
    with pytest.raises(SpecificationParseError) as exc_info:
        DocumentParser.parse_raw_content(raw, filename="unsafe.yaml")
    assert "could not determine a constructor" in str(exc_info.value).lower() or "malformed yaml" in str(exc_info.value).lower()


def test_reject_remote_ref_ssrf_risk(load_fixture):
    raw = load_fixture("unresolved_remote_ref.json")
    spec_dict = DocumentParser.parse_raw_content(raw)
    with pytest.raises(SecurityValidationError) as exc_info:
        DocumentParser.identify_and_validate_spec(spec_dict, raw)
    assert "prohibited remote references" in str(exc_info.value).lower()


def test_reject_external_file_ref():
    spec = {
        "openapi": "3.0.0",
        "info": { "title": "File Ref Spec", "version": "1.0.0" },
        "paths": {
            "/sensitive": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "desc",
                            "content": {
                                "application/json": {
                                    "schema": { "$ref": "../secret_directory/database.json" }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    raw = b"{}"
    with pytest.raises(SecurityValidationError) as exc_info:
        DocumentParser.identify_and_validate_spec(spec, raw)
    assert "external file references" in str(exc_info.value).lower()


def test_allow_internal_schema_ref():
    spec = {
        "openapi": "3.0.0",
        "info": { "title": "Safe Internal Ref", "version": "1.0.0" },
        "paths": {
            "/users": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "desc",
                            "content": {
                                "application/json": {
                                    "schema": { "$ref": "#/components/schemas/User" }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    # Should not raise SecurityValidationError
    SafeSpecScanner.validate_security(spec)
