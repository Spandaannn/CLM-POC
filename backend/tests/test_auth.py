"""Authentication endpoint tests.

Every test uses the transaction-scoped session from conftest, so no users or
sessions created here survive the test run.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.core.cookies import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
)
from app.core.security import generate_session_token, hash_session_token
from app.models.user_session import UserSession

TEST_PASSWORD = "Pytest-Password-123!"


def get_csrf_token(client) -> str:
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200
    token = response.json()["csrf_token"]
    assert token
    return token


def login(client, email: str, password: str = TEST_PASSWORD, csrf=None):
    token = csrf or get_csrf_token(client)
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={CSRF_HEADER_NAME: token},
    )


def session_count(db_session, user_id) -> int:
    rows = db_session.scalars(
        select(UserSession).where(UserSession.user_id == user_id)
    )
    return len(list(rows))


def test_successful_login_sets_cookie_and_stores_only_hash(
    client, db_session, user_factory
) -> None:
    user = user_factory()

    initial_csrf = get_csrf_token(client)
    login_response = login(client, user.email.upper(), csrf=initial_csrf)

    assert login_response.status_code == 200
    body = login_response.json()
    assert body["user"]["email"] == user.email
    assert body["user"]["role"] == "business_user"
    assert "password" not in body["user"]
    assert "password_hash" not in login_response.text

    raw_session_token = client.cookies.get(SESSION_COOKIE_NAME)
    assert raw_session_token
    assert raw_session_token not in login_response.text

    rows = list(
        db_session.scalars(
            select(UserSession).where(UserSession.user_id == user.id)
        )
    )
    assert len(rows) == 1
    assert rows[0].token_hash == hash_session_token(raw_session_token)
    assert rows[0].token_hash != raw_session_token
    assert body["csrf_token"] != initial_csrf

    set_cookie_headers = login_response.headers.get_list("set-cookie")
    session_header = next(
        header
        for header in set_cookie_headers
        if header.startswith(f"{SESSION_COOKIE_NAME}=")
    )
    assert "HttpOnly" in session_header
    assert "SameSite=lax" in session_header

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == user.email
    assert user.password_hash not in me_response.text


def test_login_with_invalid_password_is_rejected(
    client, db_session, user_factory
) -> None:
    user = user_factory()

    response = login(client, user.email, password="definitely-wrong")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert client.cookies.get(SESSION_COOKIE_NAME) is None
    assert session_count(db_session, user.id) == 0


def test_login_with_unknown_email_is_rejected(client) -> None:
    response = login(
        client, f"missing-{uuid4().hex}@example.com", password="wrong"
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_requires_csrf_header(client, user_factory) -> None:
    user = user_factory()

    response = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": TEST_PASSWORD},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed"


def test_inactive_user_cannot_log_in(client, db_session, user_factory) -> None:
    user = user_factory(is_active=False)

    response = login(client, user.email)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert session_count(db_session, user.id) == 0


def test_me_without_session_is_rejected(client) -> None:
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_me_with_invalid_session_is_rejected(client) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, "not-a-real-session-token")
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_expired_session_is_rejected_and_deleted(
    client, db_session, user_factory
) -> None:
    user = user_factory()
    raw_token = generate_session_token()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.add(session)
    db_session.commit()

    client.cookies.set(SESSION_COOKIE_NAME, raw_token)
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert session_count(db_session, user.id) == 0


def test_inactive_user_with_session_is_forbidden_and_session_deleted(
    client, db_session, user_factory
) -> None:
    user = user_factory(is_active=False)
    raw_token = generate_session_token()
    db_session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
    )
    db_session.commit()

    client.cookies.set(SESSION_COOKIE_NAME, raw_token)
    response = client.get("/api/auth/me")

    assert response.status_code == 403
    assert response.json()["detail"] == "User account is inactive"
    assert session_count(db_session, user.id) == 0


def test_logout_invalidates_session_and_clears_cookies(
    client, db_session, user_factory
) -> None:
    user = user_factory()
    login_response = login(client, user.email)
    assert login_response.status_code == 200
    csrf_token = login_response.json()["csrf_token"]

    response = client.post(
        "/api/auth/logout", headers={CSRF_HEADER_NAME: csrf_token}
    )

    assert response.status_code == 204
    assert response.content == b""
    assert client.cookies.get(SESSION_COOKIE_NAME) is None
    assert client.cookies.get(CSRF_COOKIE_NAME) is None
    assert session_count(db_session, user.id) == 0
    assert client.get("/api/auth/me").status_code == 401


def test_logout_without_csrf_header_is_rejected(
    client, db_session, user_factory
) -> None:
    user = user_factory()
    login_response = login(client, user.email)
    assert login_response.status_code == 200

    response = client.post("/api/auth/logout")

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed"
    assert session_count(db_session, user.id) == 1


def test_validation_errors_do_not_echo_passwords(client, user_factory) -> None:
    user = user_factory()
    csrf_token = get_csrf_token(client)

    response = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": ""},
        headers={CSRF_HEADER_NAME: csrf_token},
    )

    assert response.status_code == 422
    assert '"input"' not in response.text
