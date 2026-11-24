"""Authentication and server-side session operations."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import (
    generate_session_token,
    hash_session_token,
    verify_dummy_password,
    verify_password,
)
from app.models.user import User
from app.models.user_session import UserSession


def normalize_email(email: str) -> str:
    """Match the storage convention documented on the users.email column."""
    return email.strip().lower()


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Return an active user when the credentials are valid, otherwise None."""
    user = db.execute(
        select(User).where(User.email == normalize_email(email))
    ).scalar_one_or_none()

    if user is None:
        verify_dummy_password(password)
        return None

    if not verify_password(password, user.password_hash):
        return None

    # Disabled accounts get the same generic login failure as bad credentials.
    if not user.is_active:
        return None

    return user


def create_user_session(db: Session, user: User) -> tuple[str, UserSession]:
    """Create a session row and return (raw token, session).

    The raw token is returned to the caller so it can be placed in the cookie;
    only its SHA-256 hash is stored in the database.
    """
    settings = get_settings()
    raw_token = generate_session_token()
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.session_ttl_minutes
    )

    session = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    return raw_token, session


def find_user_session(db: Session, raw_token: str | None) -> UserSession | None:
    """Return a valid, unexpired session or None.

    An expired session is removed when it is discovered. Expired rows that are
    never presented are left for a future cleanup job.
    """
    if not raw_token:
        return None

    session = db.execute(
        select(UserSession)
        .options(selectinload(UserSession.user))
        .where(UserSession.token_hash == hash_session_token(raw_token))
    ).scalar_one_or_none()

    if session is None:
        return None

    if session.expires_at <= datetime.now(UTC):
        db.delete(session)
        db.commit()
        return None

    return session


def revoke_user_session(db: Session, raw_token: str | None) -> bool:
    """Delete the matching session. Returns True when a row was removed."""
    if not raw_token:
        return False

    result = db.execute(
        delete(UserSession).where(
            UserSession.token_hash == hash_session_token(raw_token)
        )
    )
    db.commit()
    return bool(result.rowcount and result.rowcount > 0)
