"""Unit tests for repository persistence."""

from src.models.schemas import DocumentMetadata, NormalizedEndpoint
from src.persistence.repository import InMemoryDocumentRepository


def test_in_memory_repository_document_crud():
    repo = InMemoryDocumentRepository()

    doc = DocumentMetadata(
        document_id="doc12345",
        title="Test Microservice",
        version="1.0.0",
        service_name="test-microservice",
        spec_format="openapi_3",
        spec_version="3.0.0",
        base_urls=["http://localhost:3000"],
    )

    saved = repo.save_document(doc)
    assert saved.document_id == "doc12345"

    retrieved = repo.get_document("doc12345")
    assert retrieved is not None
    assert retrieved.title == "Test Microservice"

    all_docs = repo.list_documents()
    assert len(all_docs) == 1


def test_in_memory_repository_endpoint_crud():
    repo = InMemoryDocumentRepository()

    ep1 = NormalizedEndpoint(
        id="ep1",
        document_id="doc1",
        service_name="auth-service",
        path="/login",
        method="POST",
        extracted_at="2026-10-19T00:00:00Z",
    )
    ep2 = NormalizedEndpoint(
        id="ep2",
        document_id="doc1",
        service_name="order-service",
        path="/orders",
        method="GET",
        extracted_at="2026-10-19T00:00:00Z",
    )

    saved_count = repo.save_endpoints([ep1, ep2])
    assert saved_count == 2

    # Filter by service name
    auth_endpoints = repo.list_endpoints(service_name="auth-service")
    assert len(auth_endpoints) == 1
    assert auth_endpoints[0].path == "/login"

    # Filter by document_id
    doc_endpoints = repo.get_endpoints_by_document("doc1")
    assert len(doc_endpoints) == 2
