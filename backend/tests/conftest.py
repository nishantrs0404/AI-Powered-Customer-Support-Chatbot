
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Provide a test client for the FastAPI application."""
    with TestClient(app) as test_client:
        yield test_client
