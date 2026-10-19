"""FastAPI route dependencies."""

import logging
from typing import Optional
from ..config import settings
from ..persistence.repository import (
    BaseDocumentRepository,
    InMemoryDocumentRepository,
    MongoDocumentRepository,
)

logger = logging.getLogger(__name__)

# Global singleton repository instance
_repo_instance: Optional[BaseDocumentRepository] = None


def get_repository() -> BaseDocumentRepository:
    """Dependency provider for document and endpoint persistence repository."""
    global _repo_instance
    if _repo_instance is None:
        if settings.MONGODB_URI:
            try:
                logger.info(f"Connecting MongoDocumentRepository to: {settings.MONGODB_URI[:25]}...")
                _repo_instance = MongoDocumentRepository(
                    uri=settings.MONGODB_URI,
                    database_name=settings.DATABASE_NAME,
                )
            except Exception as err:
                logger.warning(f"Could not connect to MongoDB ({err}). Falling back to InMemoryDocumentRepository.")
                _repo_instance = InMemoryDocumentRepository()
        else:
            logger.info("Using InMemoryDocumentRepository (MONGODB_URI not configured).")
            _repo_instance = InMemoryDocumentRepository()
    return _repo_instance


def set_repository(repo: BaseDocumentRepository):
    """Sets or overrides repository instance (used for testing)."""
    global _repo_instance
    _repo_instance = repo
