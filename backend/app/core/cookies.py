"""Cookie name and attribute helpers for session authentication."""

from fastapi import Response

from app.core.config import get_settings

SESSION_COOKIE_NAME = "clm_session"
CSRF_COOKIE_NAME = "clm_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


def _cookie_options() -> dict[str, object]:
    settings = get_settings()
    return {
        "path": "/",
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
    }


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=settings.session_ttl_minutes * 60,
        httponly=True,
        **_cookie_options(),
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        httponly=True,
        **_cookie_options(),
    )


def set_csrf_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    # This cookie must be readable by the frontend so it can be copied into
    # the X-CSRF-Token header.
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=settings.session_ttl_minutes * 60,
        httponly=False,
        **_cookie_options(),
    )


def clear_csrf_cookie(response: Response) -> None:
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        httponly=False,
        **_cookie_options(),
    )
