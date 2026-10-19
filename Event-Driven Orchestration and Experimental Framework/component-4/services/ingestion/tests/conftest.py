"""Pytest configuration, fixtures, and TestClient setup."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.persistence.repository import InMemoryDocumentRepository
from src.api.dependencies import get_repository, set_repository

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_repository():
    """Provides a fresh isolated InMemoryDocumentRepository for every test."""
    repo = InMemoryDocumentRepository()
    set_repository(repo)
    app.dependency_overrides[get_repository] = lambda: repo
    yield repo
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


@pytest.fixture
def load_fixture():
    """Helper function to load fixture files as bytes."""
    def _loader(filename: str) -> bytes:
        filepath = FIXTURES_DIR / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Fixture '{filename}' not found at {filepath}")
        return filepath.read_bytes()
    return _loader
