"""Shared pytest fixtures.

Tests run against the real PostgreSQL database configured in backend/.env.
Each test is wrapped in an outer transaction that is rolled back afterwards, so
test users and sessions are never committed permanently. SQLite is not used.
"""

import os
from uuid import uuid4

# Tests use plain HTTP, so cookies must not require HTTPS. These environment
# variables take precedence over backend/.env for the test process.
os.environ["COOKIE_SECURE"] = "false"
os.environ["COOKIE_SAMESITE"] = "lax"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.db.session import engine, get_db
from app.main import app
from app.models.enums import UserRole
from app.models.user import User

TEST_PASSWORD = "Pytest-Password-123!"


@pytest.fixture(scope="session", autouse=True)
def require_postgres() -> None:
    """Fail with a clear message rather than silently skipping the tests."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.exit(
            f"PostgreSQL is not reachable with backend/.env: {exc}", returncode=1
        )


@pytest.fixture
def db_session():
    """Provide a session whose changes are rolled back after the test."""
    connection = engine.connect()
    outer_transaction = connection.begin()
    testing_session_factory = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session = testing_session_factory()

    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    """FastAPI test client using the transaction-scoped database session."""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def no_real_ai_provider():
    """Safety net: no test can reach the real AI provider.

    backend/.env may hold a real API key. By default the provider dependency
    reports "not configured"; tests that need AI install a fake provider.
    """
    from app.ai.errors import AIConfigurationError
    from app.api.reviews import get_ai_provider_factory

    def unconfigured():
        def build():
            raise AIConfigurationError()

        return build

    app.dependency_overrides[get_ai_provider_factory] = unconfigured
    yield
    app.dependency_overrides.pop(get_ai_provider_factory, None)


@pytest.fixture
def user_factory(db_session):
    """Create active (or inactive) users with unique email addresses."""

    def create_user(
        *,
        is_active: bool = True,
        role: UserRole = UserRole.BUSINESS_USER,
    ) -> User:
        user = User(
            full_name="Pytest User",
            email=f"pytest-{uuid4().hex}@example.com",
            password_hash=hash_password(TEST_PASSWORD),
            role=role.value,
            is_active=is_active,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return create_user
