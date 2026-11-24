"""Schemas for the contract approval workflow."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# What a user can be offered / can do, computed once on the server.
WorkflowAction = Literal[
    "submit",
    "resubmit",
    "recommend",
    "request_changes",
    "reject",
    "approve",
]

# "not_submitted" before the first submission; otherwise the latest cycle status.
WorkflowStatus = Literal[
    "not_submitted",
    "pending_reviewer",
    "pending_approver",
    "approved",
    "rejected",
    "changes_requested",
]

MIN_DECISION_COMMENT = 10
MAX_COMMENT = 2000


class UserRef(BaseModel):
    id: UUID
    full_name: str
    role: str


class AssigneeRead(UserRef):
    email: str


class AssigneesResponse(BaseModel):
    """Active users who can be assigned as reviewer / approver."""

    reviewers: list[AssigneeRead]
    approvers: list[AssigneeRead]


class SubmitRequest(BaseModel):
    """Submit (or resubmit) a contract for approval."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reviewer_id: UUID
    approver_id: UUID
    comment: str | None = Field(default=None, max_length=2000)


class ReviewerActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["recommend", "request_changes", "reject"]
    comment: str | None = Field(default=None, max_length=2000)


class ApproverActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["approve", "request_changes", "reject"]
    comment: str | None = Field(default=None, max_length=2000)


class ApprovalActionRead(BaseModel):
    id: UUID
    sequence: int
    action_type: str
    stage: str
    actor: UserRef | None
    comment: str | None
    created_at: datetime


class ApprovalCycleRead(BaseModel):
    id: UUID
    cycle_number: int
    status: str
    reviewer: UserRef
    approver: UserRef
    submitted_by: UserRef
    document_version: int | None
    submitted_at: datetime
    completed_at: datetime | None
    actions: list[ApprovalActionRead]


class ApprovalState(BaseModel):
    """Workflow status and full history for one contract."""

    contract_id: UUID
    contract_status: str
    workflow_status: WorkflowStatus
    current_cycle: ApprovalCycleRead | None = Field(
        description="The latest cycle, if the contract was ever submitted."
    )
    cycles: list[ApprovalCycleRead] = Field(
        description="Every cycle, newest first. Earlier cycles are never changed."
    )
    available_actions: list[WorkflowAction] = Field(
        description="What the signed-in user may do right now."
    )
    content_locked: bool = Field(
        description="True when the contract and its documents cannot be edited."
    )
    advisory_note: str = (
        "AI review findings are advisory only. They never submit, approve, "
        "reject, or change the approval state of a contract."
    )


class QueueItem(BaseModel):
    contract_id: UUID
    contract_number: str
    title: str
    counterparty_name: str
    cycle_number: int
    status: str
    reviewer_name: str
    approver_name: str
    submitted_by_name: str
    updated_at: datetime


class ApprovalSummary(BaseModel):
    """Dashboard summary for the signed-in user."""

    awaiting_my_action: list[QueueItem]
    my_contracts: list[QueueItem] = Field(
        description="Contracts I created that are in the workflow."
    )
    awaiting_my_action_count: int
    under_approval_count: int
    changes_requested_count: int
