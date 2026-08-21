"""Pytest configuration and fixtures for user preferences service tests."""

import pytest
from datetime import datetime, timedelta
from typing import Generator
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import jwt

from app.main import app
from app.database import Base, get_db
from app.config import settings


# Test database URL (use PostgreSQL from docker-compose)
# Create a separate test database to avoid interfering with dev data
TEST_DATABASE_URL = "postgresql://postgres:postgres@postgres:5432/test_preferences"

# Create test engine
test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """Create a fresh database for each test."""
    # Create all tables
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db: Session) -> Generator[TestClient, None, None]:
    """Create a test client with database dependency override."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# Test user IDs
USER_A_ID = uuid4()
USER_B_ID = uuid4()
ADMIN_USER_ID = uuid4()


def create_jwt_token(user_id: UUID, expires_delta: timedelta = timedelta(hours=1)) -> str:
    """Create a JWT token for testing."""
    expire = datetime.utcnow() + expires_delta
    payload = {
        "user_id": str(user_id),
        "type": "access",
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@pytest.fixture
def user_a_token() -> str:
    """Create JWT token for User A."""
    return create_jwt_token(USER_A_ID)


@pytest.fixture
def user_b_token() -> str:
    """Create JWT token for User B."""
    return create_jwt_token(USER_B_ID)


@pytest.fixture
def admin_token() -> str:
    """Create JWT token for admin user."""
    return create_jwt_token(ADMIN_USER_ID)


@pytest.fixture
def expired_token() -> str:
    """Create an expired JWT token."""
    return create_jwt_token(USER_A_ID, expires_delta=timedelta(seconds=-1))


@pytest.fixture
def invalid_token() -> str:
    """Create an invalid JWT token."""
    return "invalid.token.here"


@pytest.fixture
def user_a_id() -> UUID:
    """Return User A's ID."""
    return USER_A_ID


@pytest.fixture
def user_b_id() -> UUID:
    """Return User B's ID."""
    return USER_B_ID


def get_auth_headers(token: str) -> dict:
    """Helper to create authorization headers."""
    return {"Authorization": f"Bearer {token}"}
