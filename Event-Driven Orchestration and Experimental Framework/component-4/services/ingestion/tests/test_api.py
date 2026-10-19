"""Integration and API route tests using FastAPI TestClient."""

import io
from src.config import settings


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "api-docs-ingestion"
    assert "uptime_seconds" in data


def test_ingest_valid_openapi3_json(client, load_fixture):
    content = load_fixture("valid_openapi3.json")
    response = client.post(
        "/api/v1/ingest",
        files={"file": ("orders.json", io.BytesIO(content), "application/json")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["endpoints_count"] == 4
    assert data["document"]["title"] == "Order Management Service"
    assert data["document"]["spec_format"] == "openapi_3"
    assert len(data["endpoints"]) == 4

    doc_id = data["document"]["document_id"]

    # Verify query by document_id
    doc_resp = client.get(f"/api/v1/documents/{doc_id}")
    assert doc_resp.status_code == 200
    assert doc_resp.json()["document_id"] == doc_id

    # Verify query endpoints by document
    ep_resp = client.get(f"/api/v1/documents/{doc_id}/endpoints")
    assert ep_resp.status_code == 200
    assert len(ep_resp.json()) == 4


def test_ingest_valid_openapi3_yaml(client, load_fixture):
    content = load_fixture("valid_openapi3.yaml")
    response = client.post(
        "/api/v1/ingest",
        files={"file": ("payments.yaml", io.BytesIO(content), "application/x-yaml")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["endpoints_count"] == 2
    assert data["document"]["title"] == "Payment Gateway Service"


def test_ingest_valid_swagger2_json(client, load_fixture):
    content = load_fixture("valid_swagger2.json")
    response = client.post(
        "/api/v1/ingest",
        files={"file": ("inventory.json", io.BytesIO(content), "application/json")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["document"]["spec_format"] == "swagger_2"
    assert data["endpoints_count"] == 2


def test_ingest_malformed_json_returns_400(client, load_fixture):
    content = load_fixture("malformed.json")
    response = client.post(
        "/api/v1/ingest",
        files={"file": ("bad.json", io.BytesIO(content), "application/json")},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "Malformed JSON" in data["message"]


def test_ingest_missing_required_fields_returns_422(client, load_fixture):
    content = load_fixture("missing_required.json")
    response = client.post(
        "/api/v1/ingest",
        files={"file": ("incomplete.json", io.BytesIO(content), "application/json")},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert "info.title" in data["message"] or "paths" in data["message"]


def test_ingest_unsupported_version_returns_422(client, load_fixture):
    content = load_fixture("unsupported_version.json")
    response = client.post(
        "/api/v1/ingest",
        files={"file": ("future.json", io.BytesIO(content), "application/json")},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert "Unsupported OpenAPI version" in data["message"]


def test_ingest_remote_ref_returns_400(client, load_fixture):
    content = load_fixture("unresolved_remote_ref.json")
    response = client.post(
        "/api/v1/ingest",
        files={"file": ("ssrf.json", io.BytesIO(content), "application/json")},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "Security Validation Failed" in data["message"]


def test_ingest_file_exceeding_size_limit(client, monkeypatch):
    # Temporarily set max upload size to 100 bytes
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_BYTES", 100)
    oversized = b"a" * 200
    response = client.post(
        "/api/v1/ingest",
        files={"file": ("huge.json", io.BytesIO(oversized), "application/json")},
    )
    assert response.status_code == 413
    data = response.json()
    assert data["success"] is False
    assert "exceeds maximum allowable upload size" in data["message"]


def test_get_nonexistent_document_returns_404(client):
    response = client.get("/api/v1/documents/nonexistent-id")
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert "not found" in data["message"].lower()


def test_list_all_endpoints_and_filter_by_service(client, load_fixture):
    # Ingest orders
    client.post(
        "/api/v1/ingest",
        files={"file": ("orders.json", io.BytesIO(load_fixture("valid_openapi3.json")), "application/json")},
    )
    # Ingest payments
    client.post(
        "/api/v1/ingest",
        files={"file": ("payments.yaml", io.BytesIO(load_fixture("valid_openapi3.yaml")), "application/x-yaml")},
    )

    all_eps = client.get("/api/v1/endpoints").json()
    assert len(all_eps) == 6  # 4 orders + 2 payments

    filtered = client.get("/api/v1/endpoints?service_name=payment-gateway-service").json()
    assert len(filtered) == 2
    assert all(ep["service_name"] == "payment-gateway-service" for ep in filtered)
