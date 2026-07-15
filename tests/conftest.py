"""
Pytest fixtures shared across the test suite.
"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from api.main import app
from api.settings import get_settings
from db.session import get_session

# Authenticate with the key the app is actually configured with, rather than a
# hardcoded guess. This respects AFROEVAL_SECRET_KEY when the environment
# overrides the default (e.g. CI sets it to "test-secret-key"), so the auth
# tests pass regardless of how the key is provided.
_TEST_API_KEY = get_settings().afroeval_secret_key


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
