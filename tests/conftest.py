"""
Pytest fixtures shared across all tests.

Uses an in-memory SQLite database to keep tests isolated and fast.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.core.dependencies import get_db
from app.core.config import settings
from app.main import app

settings.app_env = "testing"

# ── In-memory SQLite for tests ────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    # StaticPool ensures all connections share the SAME in-memory SQLite
    # database — critical for tests, otherwise each new connection creates
    # a fresh empty DB and "no such table" errors occur.
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function", autouse=True)
def setup_db():
    """Create all tables before each test, drop after."""
    import app.models  # noqa — registers all models
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    """Yield a test DB session."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    """
    TestClient with the real DB dependency overridden to use the test DB.
    """
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def registered_user(client):
    """Register a test user and return the response."""
    resp = client.post("/register", data={
        "email": "test@example.com",
        "username": "testuser",
        "password": "TestPass123!",
        "confirm_password": "TestPass123!",
    }, follow_redirects=False)
    return resp


@pytest.fixture
def auth_client(client, registered_user):
    """TestClient with a logged-in session cookie."""
    client.post("/login", data={
        "email": "test@example.com",
        "password": "TestPass123!",
    }, follow_redirects=False)
    return client
