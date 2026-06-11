"""
Pytest fixtures shared across the test suite.
"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from api.main import app
from db.session import get_session

# Matches the default afroeval_secret_key in api/settings.py.
# Tests don't load .env so this stays as the hardcoded dev default.
_TEST_API_KEY = "dev-secret-change-in-production"


@pytest.fixture(name="session")
def session_fixture():
    """In-memory SQLite session for fast, isolated unit tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    """FastAPI test client wired to the in-memory DB session."""

    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app, headers={"X-API-Key": _TEST_API_KEY})
    yield client
    app.dependency_overrides.clear()
