"""Persistence abstraction and MongoDB repository for ingested specifications and endpoints."""

from abc import ABC, abstractmethod
import logging
from typing import Dict, List, Optional
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError

from ..models.schemas import DocumentMetadata, NormalizedEndpoint

logger = logging.getLogger(__name__)


class BaseDocumentRepository(ABC):
    """Abstract persistence interface for API documents and normalized endpoints."""

    @abstractmethod
    def save_document(self, document: DocumentMetadata) -> DocumentMetadata:
        """Persists or updates document metadata."""
        pass

    @abstractmethod
    def get_document(self, document_id: str) -> Optional[DocumentMetadata]:
        """Retrieves document metadata by deterministic document ID."""
        pass

    @abstractmethod
    def list_documents(self) -> List[DocumentMetadata]:
        """Retrieves all persisted document metadata."""
        pass

    @abstractmethod
    def save_endpoints(self, endpoints: List[NormalizedEndpoint]) -> int:
        """Persists or updates a list of normalized endpoints. Returns count saved."""
        pass

    @abstractmethod
    def get_endpoints_by_document(self, document_id: str) -> List[NormalizedEndpoint]:
        """Retrieves all endpoints belonging to a specific document."""
        pass

    @abstractmethod
    def list_endpoints(self, service_name: Optional[str] = None) -> List[NormalizedEndpoint]:
        """Retrieves normalized endpoints, optionally filtered by service name."""
        pass


class InMemoryDocumentRepository(BaseDocumentRepository):
    """In-memory repository implementation for hermetic unit testing and offline development."""

    def __init__(self):
        self._documents: Dict[str, DocumentMetadata] = {}
        self._endpoints: Dict[str, NormalizedEndpoint] = {}

    def save_document(self, document: DocumentMetadata) -> DocumentMetadata:
        self._documents[document.document_id] = document
        return document

    def get_document(self, document_id: str) -> Optional[DocumentMetadata]:
        return self._documents.get(document_id)

    def list_documents(self) -> List[DocumentMetadata]:
        return list(self._documents.values())

    def save_endpoints(self, endpoints: List[NormalizedEndpoint]) -> int:
        count = 0
        for ep in endpoints:
            self._endpoints[ep.id] = ep
            count += 1
        return count

    def get_endpoints_by_document(self, document_id: str) -> List[NormalizedEndpoint]:
        return [ep for ep in self._endpoints.values() if ep.document_id == document_id]

    def list_endpoints(self, service_name: Optional[str] = None) -> List[NormalizedEndpoint]:
        if service_name:
            return [ep for ep in self._endpoints.values() if ep.service_name.lower() == service_name.lower()]
        return list(self._endpoints.values())

    def clear(self):
        """Helper to reset in-memory state during tests."""
        self._documents.clear()
        self._endpoints.clear()


class MongoDocumentRepository(BaseDocumentRepository):
    """MongoDB persistence adapter for storing API documents and endpoints."""

    def __init__(self, uri: str, database_name: str = "component4"):
        self.uri = uri
        self.database_name = database_name
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[database_name]
        self.docs_collection = self.db["api_documents"]
        self.endpoints_collection = self.db["api_endpoints"]
        self._ensure_indexes()

    def _ensure_indexes(self):
        try:
            self.docs_collection.create_index("document_id", unique=True)
            self.endpoints_collection.create_index("id", unique=True)
            self.endpoints_collection.create_index("document_id")
            self.endpoints_collection.create_index("service_name")
            self.endpoints_collection.create_index([("method", 1), ("path", 1)])
        except Exception as err:
            logger.warning(f"Could not initialize MongoDB indexes: {err}")

    def is_connected(self) -> bool:
        """Checks if MongoDB connection is active."""
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False

    def save_document(self, document: DocumentMetadata) -> DocumentMetadata:
        try:
            doc_data = document.model_dump()
            self.docs_collection.replace_one(
                {"document_id": document.document_id},
                doc_data,
                upsert=True,
            )
            return document
        except PyMongoError as err:
            logger.error(f"Failed to persist document to MongoDB: {err}")
            raise

    def get_document(self, document_id: str) -> Optional[DocumentMetadata]:
        try:
            record = self.docs_collection.find_one({"document_id": document_id}, {"_id": 0})
            if record:
                return DocumentMetadata(**record)
            return None
        except PyMongoError as err:
            logger.error(f"Failed to retrieve document from MongoDB: {err}")
            raise

    def list_documents(self) -> List[DocumentMetadata]:
        try:
            records = self.docs_collection.find({}, {"_id": 0})
            return [DocumentMetadata(**r) for r in records]
        except PyMongoError as err:
            logger.error(f"Failed to list documents from MongoDB: {err}")
            raise

    def save_endpoints(self, endpoints: List[NormalizedEndpoint]) -> int:
        if not endpoints:
            return 0
        try:
            ops = [
                UpdateOne({"id": ep.id}, {"$set": ep.model_dump()}, upsert=True)
                for ep in endpoints
            ]
            result = self.endpoints_collection.bulk_write(ops, ordered=False)
            return result.upserted_count + result.modified_count
        except PyMongoError as err:
            logger.error(f"Failed to persist endpoints to MongoDB: {err}")
            raise

    def get_endpoints_by_document(self, document_id: str) -> List[NormalizedEndpoint]:
        try:
            records = self.endpoints_collection.find({"document_id": document_id}, {"_id": 0})
            return [NormalizedEndpoint(**r) for r in records]
        except PyMongoError as err:
            logger.error(f"Failed to retrieve endpoints by document from MongoDB: {err}")
            raise

    def list_endpoints(self, service_name: Optional[str] = None) -> List[NormalizedEndpoint]:
        try:
            query = {"service_name": service_name} if service_name else {}
            records = self.endpoints_collection.find(query, {"_id": 0})
            return [NormalizedEndpoint(**r) for r in records]
        except PyMongoError as err:
            logger.error(f"Failed to list endpoints from MongoDB: {err}")
            raise
