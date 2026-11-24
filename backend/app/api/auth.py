"""Session-based authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_csrf
from app.core.cookies import (
    SESSION_COOKIE_NAME,
    clear_csrf_cookie,
    clear_session_cookie,
    set_csrf_cookie,
    set_session_cookie,
)
from app.core.security import generate_csrf_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import CsrfTokenResponse, LoginRequest, LoginResponse
from app.schemas.common import ErrorResponse
from app.schemas.user import UserPublic
from app.services.auth import (
    authenticate_user,
    create_user_session,
    revoke_user_session,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get(
    "/csrf",
    response_model=CsrfTokenResponse,
    summary="Issue a CSRF token for the login and logout forms",
)
def issue_csrf_token(response: Response) -> CsrfTokenResponse:
    token = generate_csrf_token()
    set_csrf_cookie(response, token)
    return CsrfTokenResponse(csrf_token=token)


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate with email and password",
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    _: None = Depends(verify_csrf),
) -> LoginResponse:
    user = authenticate_user(db, str(payload.email), payload.password)
    if user is None:
        # Deliberately generic: do not reveal whether the email exists.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    raw_token, _session = create_user_session(db, user)

    # Rotate the CSRF token when a session starts.
    csrf_token = generate_csrf_token()
    set_session_cookie(response, raw_token)
    set_csrf_cookie(response, csrf_token)

    return LoginResponse(
        user=UserPublic.model_validate(user),
        csrf_token=csrf_token,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the current session and clear its cookies",
    responses={
        204: {"description": "Session removed"},
        403: {"model": ErrorResponse},
    },
)
def logout(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(verify_csrf),
) -> Response:
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    revoke_user_session(db, raw_token)

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    clear_csrf_cookie(response)
    return response


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Return the authenticated user",
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
