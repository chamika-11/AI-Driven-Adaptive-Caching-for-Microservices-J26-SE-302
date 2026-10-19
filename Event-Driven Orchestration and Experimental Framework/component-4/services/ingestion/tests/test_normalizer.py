"""Unit tests for endpoint metadata normalization."""

from src.core.parser import DocumentParser
from src.core.normalizer import EndpointNormalizer


def test_normalize_openapi3_endpoints(load_fixture):
    raw = load_fixture("valid_openapi3.json")
    spec_dict = DocumentParser.parse_raw_content(raw, filename="orders.json")
    metadata, validated_spec = DocumentParser.identify_and_validate_spec(
        spec_dict, raw, filename="orders.json"
    )

    endpoints = EndpointNormalizer.normalize_specification(metadata, validated_spec)

    # 4 endpoints: GET /orders, POST /orders, GET /orders/{orderId}, DELETE /orders/{orderId}
    assert len(endpoints) == 4

    # Verify GET /orders
    get_orders = next(ep for ep in endpoints if ep.path == "/orders" and ep.method == "GET")
    assert get_orders.operation_id == "listOrders"
    assert get_orders.summary == "List all customer orders"
    assert "Orders" in get_orders.tags
    assert len(get_orders.parameters) == 2
    assert any(p.name == "status" and p.location == "query" for p in get_orders.parameters)
    assert any(p.name == "limit" and p.schema_type == "integer" for p in get_orders.parameters)
    assert len(get_orders.responses) == 1
    assert get_orders.responses[0].status_code == "200"
    assert get_orders.responses[0].schema_ref == "#/components/schemas/Order"

    # Verify POST /orders
    post_orders = next(ep for ep in endpoints if ep.path == "/orders" and ep.method == "POST")
    assert post_orders.operation_id == "createOrder"
    assert post_orders.request_body is not None
    assert post_orders.request_body.required is True
    assert "application/json" in post_orders.request_body.content_types
    assert post_orders.request_body.schema_ref == "#/components/schemas/CreateOrderInput"
    assert len(post_orders.responses) == 2

    # Verify Path Parameter propagation to GET /orders/{orderId}
    get_by_id = next(ep for ep in endpoints if ep.path == "/orders/{orderId}" and ep.method == "GET")
    assert any(p.name == "orderId" and p.location == "path" and p.required is True for p in get_by_id.parameters)


def test_normalize_swagger2_endpoints(load_fixture):
    raw = load_fixture("valid_swagger2.json")
    spec_dict = DocumentParser.parse_raw_content(raw, filename="inventory.json")
    metadata, validated_spec = DocumentParser.identify_and_validate_spec(
        spec_dict, raw, filename="inventory.json"
    )

    endpoints = EndpointNormalizer.normalize_specification(metadata, validated_spec)
    assert len(endpoints) == 2

    put_product = next(ep for ep in endpoints if ep.method == "PUT")
    assert put_product.path == "/products/{sku}"
    assert put_product.operation_id == "updateProductStock"
    assert put_product.request_body is not None
    assert put_product.request_body.schema_ref == "#/definitions/StockUpdate"


def test_optional_fields_are_none_when_missing():
    raw_spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Minimal Service",
            "version": "1.0.0"
        },
        "paths": {
            "/minimal": {
                "get": {
                    "responses": {
                        "200": { "description": "Success" }
                    }
                }
            }
        }
    }
    raw_bytes = b'{"openapi":"3.0.0","info":{"title":"Minimal Service","version":"1.0.0"},"paths":{"/minimal":{"get":{"responses":{"200":{"description":"Success"}}}}}}'
    metadata, validated = DocumentParser.identify_and_validate_spec(raw_spec, raw_bytes)
    endpoints = EndpointNormalizer.normalize_specification(metadata, validated)

    assert len(endpoints) == 1
    ep = endpoints[0]
    assert ep.operation_id is None
    assert ep.summary is None
    assert ep.description is None
    assert ep.tags == []
    assert ep.parameters == []
    assert ep.request_body is None


def test_ignore_non_http_methods():
    raw_spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Metadata Service",
            "version": "1.0.0"
        },
        "paths": {
            "/resource": {
                "summary": "Path level summary (not an HTTP operation)",
                "description": "Path level description",
                "get": {
                    "responses": { "200": { "description": "ok" } }
                }
            }
        }
    }
    raw_bytes = b"{}"
    metadata, validated = DocumentParser.identify_and_validate_spec(raw_spec, raw_bytes)
    endpoints = EndpointNormalizer.normalize_specification(metadata, validated)

    # Only 1 endpoint extracted (GET /resource), summary and description are NOT treated as endpoints
    assert len(endpoints) == 1
    assert endpoints[0].method == "GET"
