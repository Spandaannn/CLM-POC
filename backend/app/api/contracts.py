"""Contract metadata endpoints.

All routes require an authenticated, active user. Create and update also
require the double-submit CSRF header used by the rest of the API.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_csrf
from app.db.session import get_db
from app.models.enums import ContractStatus
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.contract import (
    ContractCreate,
    ContractListResponse,
    ContractRead,
    ContractUpdate,
)
from app.services import contracts as contract_service

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

AUTH_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Not authenticated"},
    403: {"model": ErrorResponse, "description": "Not permitted"},
}


@router.post(
    "",
    response_model=ContractRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft contract",
    responses={
        **AUTH_RESPONSES,
        422: {"model": ErrorResponse, "description": "Invalid input"},
    },
)
def create_contract(
    payload: ContractCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(verify_csrf),
) -> ContractRead:
    contract = contract_service.create_contract(db, payload, current_user)
    return contract_service.contract_to_read(contract)


@router.get(
    "",
    response_model=ContractListResponse,
    summary="List contracts with search, filters, and pagination",
    responses=AUTH_RESPONSES,
)
def list_contracts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, max_length=200),
    status_filter: ContractStatus | None = Query(
        default=None, alias="status", description="Exact contract status"
    ),
    contract_type: str | None = Query(default=None, max_length=64),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContractListResponse:
    contracts, total = contract_service.list_contracts(
        db,
        current_user,
        page=page,
        page_size=page_size,
        search=q,
        contract_status=status_filter,
        contract_type=contract_type,
    )

    return ContractListResponse(
        items=[contract_service.contract_to_read(item) for item in contracts],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.get(
    "/{contract_id}",
    response_model=ContractRead,
    summary="Get one contract",
    responses={
        **AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Contract not found"},
    },
)
def get_contract(
    contract_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContractRead:
    contract = contract_service.get_contract_for_read(
        db, contract_id, current_user
    )
    return contract_service.contract_to_read(contract)


@router.patch(
    "/{contract_id}",
    response_model=ContractRead,
    summary="Update contract metadata",
    responses={
        **AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Contract not found"},
        422: {"model": ErrorResponse, "description": "Invalid input"},
    },
)
def update_contract(
    contract_id: UUID,
    payload: ContractUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(verify_csrf),
) -> ContractRead:
    contract = contract_service.get_contract_for_update(
        db, contract_id, current_user
    )
    contract = contract_service.update_contract(
        db, contract, payload, current_user
    )
    return contract_service.contract_to_read(contract)
