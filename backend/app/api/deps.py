"""FastAPI dependencies for database sessions, auth, and CSRF."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.cookies import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from app.core.security import tokens_match
from app.db.session import get_db
from app.models.user import User
from app.models.user_session import UserSession
from app.services.auth import find_user_session


def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
) -> UserSession:
    """Resolve the session cookie to a live database session."""
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    session = find_user_session(db, raw_token)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return session


def get_current_user(
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> User:
    """Return the authenticated user if the account is still active."""
    user = session.user
    if not user.is_active:
        # Disabling an account also ends its existing sessions.
        db.delete(session)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    return user


def verify_csrf(request: Request) -> None:
    """Double-submit cookie check for state-changing requests.

    The random CSRF cookie is issued by GET /api/auth/csrf. The client must
    copy it into the X-CSRF-Token header. A cross-site attacker cannot read the
    cookie, so it cannot produce a matching header.
    """
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)

    if (
        not cookie_token
        or not header_token
        or not tokens_match(cookie_token, header_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
        )
