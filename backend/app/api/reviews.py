"""AI contract review endpoints.

Anyone who may view a contract may start and read its reviews (so a business
user can never review a contract they cannot already see). Starting a review
requires the CSRF header and is always an explicit user action: contract text
is only sent to the AI provider from ``POST .../reviews``, never on upload.
Reviews are suggestions only; nothing here changes a contract.
"""

from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.base import AIProvider
from app.ai.errors import (
    AIAuthenticationError,
    AIConfigurationError,
    AIError,
    AIModelUnavailableError,
    AIProviderError,
    AIRateLimitError,
    AIRequestTooLargeError,
    AIResponseFormatError,
    AITimeoutError,
)
from app.ai.factory import build_provider, get_ai_status
from app.api.deps import get_current_user, verify_csrf
from app.api.documents import get_storage_root
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.review import (
    AIStatusResponse,
    ReviewDetail,
    ReviewListResponse,
)
from app.services import contracts as contract_service
from app.services import reviews as review_service

router = APIRouter(prefix="/api", tags=["ai-reviews"])

AUTH_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Not authenticated"},
    403: {"model": ErrorResponse, "description": "Not permitted"},
}

# Provider problems are reported with a status that tells the client what
# kind of failure it was, but only ever with a generic, safe message.
_AI_ERROR_STATUS: dict[type[AIError], int] = {
    AIConfigurationError: status.HTTP_503_SERVICE_UNAVAILABLE,
    AIRateLimitError: status.HTTP_429_TOO_MANY_REQUESTS,
    AITimeoutError: status.HTTP_504_GATEWAY_TIMEOUT,
    AIRequestTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
    AIAuthenticationError: status.HTTP_502_BAD_GATEWAY,
    AIModelUnavailableError: status.HTTP_502_BAD_GATEWAY,
    AIResponseFormatError: status.HTTP_502_BAD_GATEWAY,
    AIProviderError: status.HTTP_502_BAD_GATEWAY,
}


def get_ai_provider_factory(
    settings: Settings = Depends(get_settings),
) -> Callable[[], AIProvider]:
    """Return a function that builds the provider when it is needed.

    Building is deferred so that authentication, permissions, and the
    "no document" check happen before configuration problems are reported.
    Tests override this dependency with a fake provider.
    """
    return lambda: build_provider(settings)


@router.get(
    "/ai/status",
    response_model=AIStatusResponse,
    summary="Is AI review configured? (never returns credentials)",
    responses=AUTH_RESPONSES,
)
def ai_status(
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> AIStatusResponse:
    info = get_ai_status(settings)
    return AIStatusResponse(
        configured=info.configured,
        provider=info.provider,
        model=info.model,
        message=info.message,
        max_input_chars=settings.ai_max_input_chars,
    )


@router.post(
    "/contracts/{contract_id}/reviews",
    response_model=ReviewDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Run an AI review of the contract's current document version",
    responses={
        **AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Contract not found"},
        409: {"model": ErrorResponse, "description": "No document uploaded"},
        422: {"model": ErrorResponse, "description": "No extractable text"},
        429: {"model": ErrorResponse, "description": "AI rate limit reached"},
        502: {"model": ErrorResponse, "description": "AI provider problem"},
        503: {"model": ErrorResponse, "description": "AI not configured"},
    },
)
def start_review(
    contract_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage_root: Path = Depends(get_storage_root),
    settings: Settings = Depends(get_settings),
    provider_factory: Callable[[], AIProvider] = Depends(get_ai_provider_factory),
    _: None = Depends(verify_csrf),
) -> ReviewDetail:
    contract = contract_service.get_contract_for_read(
        db, contract_id, current_user
    )

    try:
        review = review_service.run_review(
            db,
            contract=contract,
            user=current_user,
            storage_root=storage_root,
            provider_factory=provider_factory,
            settings=settings,
        )
    except AIError as error:
        raise HTTPException(
            status_code=_AI_ERROR_STATUS.get(
                type(error), status.HTTP_502_BAD_GATEWAY
            ),
            detail=error.message,
        ) from None

    # Reload relationships (document, initiator) for the response.
    review = review_service.get_review_for_read(db, review.id, current_user)
    return review_service.to_detail(db, review)


@router.get(
    "/contracts/{contract_id}/reviews",
    response_model=ReviewListResponse,
    summary="Review history for a contract, newest first",
    responses={
        **AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Contract not found"},
    },
)
def list_reviews(
    contract_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewListResponse:
    contract_service.get_contract_for_read(db, contract_id, current_user)
    items = [
        review_service.to_list_item(db, review)
        for review in review_service.list_reviews(db, contract_id)
    ]
    return ReviewListResponse(items=items, total=len(items))


@router.get(
    "/reviews/{review_id}",
    response_model=ReviewDetail,
    summary="One review with its summary, metadata, clauses, risks, and playbook results",
    responses={
        **AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Review not found"},
    },
)
def get_review(
    review_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewDetail:
    review = review_service.get_review_for_read(db, review_id, current_user)
    return review_service.to_detail(db, review)
