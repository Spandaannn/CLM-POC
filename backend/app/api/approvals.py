"""Contract approval workflow endpoints.

Visibility follows the contract: anyone who may view a contract may read its
approval state and history. Every state-changing call needs the CSRF header,
and every rule (who may act, valid transitions, mandatory comments) is enforced
in ``app.services.approvals`` regardless of what the UI shows.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_csrf
from app.db.session import get_db
from app.models.user import User
from app.schemas.approval import (
    ApprovalState,
    ApprovalSummary,
    ApproverActionRequest,
    AssigneesResponse,
    ReviewerActionRequest,
    SubmitRequest,
)
from app.schemas.common import ErrorResponse
from app.services import approvals as approval_service
from app.services import contracts as contract_service

router = APIRouter(prefix="/api", tags=["approvals"])

AUTH_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Not authenticated"},
    403: {"model": ErrorResponse, "description": "Not permitted"},
}
ACTION_RESPONSES = {
    **AUTH_RESPONSES,
    404: {"model": ErrorResponse, "description": "Contract not found"},
    409: {"model": ErrorResponse, "description": "Invalid state transition"},
    422: {"model": ErrorResponse, "description": "Invalid input"},
}


@router.get(
    "/approvals/assignees",
    response_model=AssigneesResponse,
    summary="Active Legal Reviewers and Legal Approvers that can be assigned",
    responses=AUTH_RESPONSES,
)
def list_assignees(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssigneesResponse:
    return approval_service.list_assignees(db)


@router.get(
    "/approvals/summary",
    response_model=ApprovalSummary,
    summary="Contracts awaiting my action and the status of my own contracts",
    responses=AUTH_RESPONSES,
)
def approval_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApprovalSummary:
    return approval_service.build_summary(db, current_user)


@router.get(
    "/contracts/{contract_id}/approval",
    response_model=ApprovalState,
    summary="Approval status, history of every cycle, and my available actions",
    responses={**AUTH_RESPONSES, 404: ACTION_RESPONSES[404]},
)
def get_approval_state(
    contract_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApprovalState:
    contract = contract_service.get_contract_for_read(
        db, contract_id, current_user
    )
    return approval_service.get_state(db, contract, current_user)


def _state_after_change(
    db: Session, contract_id: UUID, user: User
) -> ApprovalState:
    contract = contract_service.get_contract_for_read(db, contract_id, user)
    return approval_service.get_state(db, contract, user)


@router.post(
    "/contracts/{contract_id}/approval/submit",
    response_model=ApprovalState,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a draft contract for approval (creator or admin)",
    responses=ACTION_RESPONSES,
)
def submit_for_approval(
    contract_id: UUID,
    payload: SubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(verify_csrf),
) -> ApprovalState:
    # Creator or admin only (same rule as editing the contract).
    contract = contract_service.get_contract_for_update(
        db, contract_id, current_user
    )
    approval_service.submit_for_approval(
        db, contract, current_user, payload, resubmit=False
    )
    return _state_after_change(db, contract_id, current_user)


@router.post(
    "/contracts/{contract_id}/approval/resubmit",
    response_model=ApprovalState,
    status_code=status.HTTP_201_CREATED,
    summary="Resubmit after changes were requested; starts a new cycle",
    responses=ACTION_RESPONSES,
)
def resubmit_for_approval(
    contract_id: UUID,
    payload: SubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(verify_csrf),
) -> ApprovalState:
    contract = contract_service.get_contract_for_update(
        db, contract_id, current_user
    )
    approval_service.submit_for_approval(
        db, contract, current_user, payload, resubmit=True
    )
    return _state_after_change(db, contract_id, current_user)


@router.post(
    "/contracts/{contract_id}/approval/reviewer-action",
    response_model=ApprovalState,
    summary="Legal Reviewer: recommend approval, request changes, or reject",
    responses=ACTION_RESPONSES,
)
def reviewer_action(
    contract_id: UUID,
    payload: ReviewerActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(verify_csrf),
) -> ApprovalState:
    contract = contract_service.get_contract_for_read(
        db, contract_id, current_user
    )
    approval_service.reviewer_action(
        db, contract, current_user, payload.action, payload.comment
    )
    return _state_after_change(db, contract_id, current_user)


@router.post(
    "/contracts/{contract_id}/approval/approver-action",
    response_model=ApprovalState,
    summary="Legal Approver: approve, request changes, or reject",
    responses=ACTION_RESPONSES,
)
def approver_action(
    contract_id: UUID,
    payload: ApproverActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(verify_csrf),
) -> ApprovalState:
    contract = contract_service.get_contract_for_read(
        db, contract_id, current_user
    )
    approval_service.approver_action(
        db, contract, current_user, payload.action, payload.comment
    )
    return _state_after_change(db, contract_id, current_user)
