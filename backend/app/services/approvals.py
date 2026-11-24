"""Contract approval workflow: states, permissions, transitions, and history.

Roles (existing; no new role system):
  creator   - the contract's creator (or an admin) submits and resubmits.
  reviewer  - the assigned ``legal_reviewer`` (or admin) recommends, requests
              changes, or rejects.
  approver  - the assigned ``legal_approver`` (or admin) gives final approval,
              requests changes, or rejects.

Cycle states and transitions::

    (none) --submit--> pending_reviewer --recommend--> pending_approver --approve--> approved
                            |  \\                           |  \\
                            |   +--reject--> rejected      |   +--reject--> rejected
                            +--request_changes--> changes_requested <--+
    changes_requested --resubmit--> NEW cycle (pending_reviewer); old cycle untouched

Contract status follows the workflow: submit/resubmit -> ``pending_review``,
recommend -> unchanged, request changes -> ``draft`` (creator can edit again),
reject -> ``rejected``, approve -> ``approved``.

Hard rules enforced here (never only in the UI):
* the contract creator can never act as reviewer or approver on their own
  contract, even if they are an admin;
* reviewer and approver must be different, active users with the right roles;
* nobody who recommended in a cycle may give that cycle's final approval;
* decisions that send a contract back or end it need a meaningful comment;
* every state change locks the contract row, so two requests cannot both win;
* actions are only ever inserted; earlier cycles are never modified.
AI review findings are advisory and are not connected to any of this.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.approval_cycle import ApprovalAction, ApprovalCycle
from app.models.audit_event import AuditEvent
from app.models.contract import Contract
from app.models.contract_document import ContractDocument
from app.models.enums import (
    ApprovalActionType,
    ApprovalCycleStatus,
    ApprovalStage,
    ContractStatus,
    UserRole,
)
from app.models.user import User
from app.schemas.approval import (
    MIN_DECISION_COMMENT,
    ApprovalActionRead,
    ApprovalCycleRead,
    ApprovalState,
    ApprovalSummary,
    AssigneeRead,
    AssigneesResponse,
    QueueItem,
    SubmitRequest,
    UserRef,
)

AUDIT_ENTITY_TYPE = "approval"

OPEN_STATUSES = (
    ApprovalCycleStatus.PENDING_REVIEWER.value,
    ApprovalCycleStatus.PENDING_APPROVER.value,
)
QUEUE_LIMIT = 20

# Reviewer-stage / approver-stage actions and where they lead.
_REVIEWER_ACTIONS = {"recommend", "request_changes", "reject"}
_APPROVER_ACTIONS = {"approve", "request_changes", "reject"}


# ------------------------------- helpers ------------------------------------


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _invalid(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail
    )


def _user_ref(user: User | None) -> UserRef | None:
    if user is None:
        return None
    return UserRef(id=user.id, full_name=user.full_name, role=user.role)


def _lock_contract(db: Session, contract: Contract) -> None:
    """Serialise workflow changes for this contract and reload its state."""
    db.execute(
        select(Contract.id).where(Contract.id == contract.id).with_for_update()
    )
    db.refresh(contract)


def latest_cycle(db: Session, contract_id: UUID) -> ApprovalCycle | None:
    return db.execute(
        select(ApprovalCycle)
        .options(
            selectinload(ApprovalCycle.actions).selectinload(
                ApprovalAction.actor
            ),
            selectinload(ApprovalCycle.reviewer),
            selectinload(ApprovalCycle.approver),
            selectinload(ApprovalCycle.submitter),
        )
        .where(ApprovalCycle.contract_id == contract_id)
        .order_by(ApprovalCycle.cycle_number.desc())
        .limit(1)
    ).scalar_one_or_none()


def _next_sequence(cycle: ApprovalCycle) -> int:
    return len(cycle.actions) + 1


def content_locked(contract: Contract) -> bool:
    """Only drafts can be edited; everything else is fixed or in the workflow."""
    return contract.status != ContractStatus.DRAFT.value


# ----------------------------- permissions ----------------------------------


def available_actions(
    user: User, contract: Contract, cycle: ApprovalCycle | None
) -> list[str]:
    """The single source of truth for what ``user`` may do right now."""
    is_creator = user.id == contract.created_by
    is_admin = user.role == UserRole.ADMIN.value

    if contract.status == ContractStatus.DRAFT.value:
        if not (is_creator or is_admin):
            return []
        if cycle is None:
            return ["submit"]
        if cycle.status == ApprovalCycleStatus.CHANGES_REQUESTED.value:
            return ["resubmit"]
        return []

    if cycle is None or is_creator:
        # The creator may never decide on their own contract.
        return []

    if (
        contract.status == ContractStatus.PENDING_REVIEW.value
        and cycle.status == ApprovalCycleStatus.PENDING_REVIEWER.value
    ):
        assigned = (
            user.id == cycle.reviewer_id
            and user.role == UserRole.LEGAL_REVIEWER.value
        )
        if assigned or is_admin:
            return ["recommend", "request_changes", "reject"]
        return []

    if (
        contract.status == ContractStatus.PENDING_REVIEW.value
        and cycle.status == ApprovalCycleStatus.PENDING_APPROVER.value
    ):
        assigned = (
            user.id == cycle.approver_id
            and user.role == UserRole.LEGAL_APPROVER.value
        )
        recommended_it = any(
            a.actor_id == user.id
            and a.action_type == ApprovalActionType.RECOMMENDED.value
            for a in cycle.actions
        )
        if (assigned or is_admin) and not recommended_it:
            return ["approve", "request_changes", "reject"]
        return []

    return []


# ------------------------------- reading ------------------------------------


def _cycle_read(cycle: ApprovalCycle) -> ApprovalCycleRead:
    return ApprovalCycleRead(
        id=cycle.id,
        cycle_number=cycle.cycle_number,
        status=cycle.status,
        reviewer=_user_ref(cycle.reviewer),
        approver=_user_ref(cycle.approver),
        submitted_by=_user_ref(cycle.submitter),
        document_version=cycle.document_version,
        submitted_at=cycle.submitted_at,
        completed_at=cycle.completed_at,
        actions=[
            ApprovalActionRead(
                id=a.id,
                sequence=a.sequence,
                action_type=a.action_type,
                stage=a.stage,
                actor=_user_ref(a.actor),
                comment=a.comment,
                created_at=a.created_at,
            )
            for a in cycle.actions
        ],
    )


def get_state(db: Session, contract: Contract, user: User) -> ApprovalState:
    cycles = list(
        db.execute(
            select(ApprovalCycle)
            .options(
                selectinload(ApprovalCycle.actions).selectinload(
                    ApprovalAction.actor
                ),
                selectinload(ApprovalCycle.reviewer),
                selectinload(ApprovalCycle.approver),
                selectinload(ApprovalCycle.submitter),
            )
            .where(ApprovalCycle.contract_id == contract.id)
            .order_by(ApprovalCycle.cycle_number.desc())
        )
        .scalars()
        .all()
    )
    latest = cycles[0] if cycles else None

    return ApprovalState(
        contract_id=contract.id,
        contract_status=contract.status,
        workflow_status=latest.status if latest else "not_submitted",
        current_cycle=_cycle_read(latest) if latest else None,
        cycles=[_cycle_read(c) for c in cycles],
        available_actions=available_actions(user, contract, latest),
        content_locked=content_locked(contract),
    )


def list_assignees(db: Session) -> AssigneesResponse:
    def users_with(role: UserRole) -> list[AssigneeRead]:
        rows = db.execute(
            select(User)
            .where(User.role == role.value, User.is_active.is_(True))
            .order_by(User.full_name, User.email)
        ).scalars()
        return [
            AssigneeRead(
                id=u.id, full_name=u.full_name, role=u.role, email=u.email
            )
            for u in rows
        ]

    return AssigneesResponse(
        reviewers=users_with(UserRole.LEGAL_REVIEWER),
        approvers=users_with(UserRole.LEGAL_APPROVER),
    )


# ------------------------------- writing ------------------------------------


def _record(
    db: Session,
    *,
    contract: Contract,
    cycle: ApprovalCycle,
    actor: User,
    action_type: ApprovalActionType,
    stage: ApprovalStage,
    comment: str | None,
    contract_status_before: str,
    extra: dict | None = None,
) -> ApprovalAction:
    """Append one action and its audit event (never updates earlier rows)."""
    action = ApprovalAction(
        cycle_id=cycle.id,
        sequence=_next_sequence(cycle),
        action_type=action_type.value,
        stage=stage.value,
        actor_id=actor.id,
        comment=comment,
        # Explicit so actions made in one transaction still order correctly.
        created_at=datetime.now(UTC),
    )
    db.add(action)
    cycle.actions.append(action)

    db.add(
        AuditEvent(
            contract_id=contract.id,
            actor_user_id=actor.id,
            action=f"approval.{action_type.value}",
            entity_type=AUDIT_ENTITY_TYPE,
            entity_id=str(cycle.id),
            details={
                "contract_number": contract.contract_number,
                "cycle_number": cycle.cycle_number,
                "stage": stage.value,
                "has_comment": bool(comment),
                "contract_status": {
                    "from": contract_status_before,
                    "to": contract.status,
                },
                **(extra or {}),
            },
        )
    )
    return action


def _assignee(db: Session, user_id: UUID, role: UserRole, label: str) -> User:
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.role != role.value:
        raise _invalid(f"Select an active {label}.")
    return user


def submit_for_approval(
    db: Session,
    contract: Contract,
    user: User,
    payload: SubmitRequest,
    *,
    resubmit: bool,
) -> ApprovalCycle:
    """Start approval cycle 1 (submit) or cycle N+1 (resubmit)."""
    _lock_contract(db, contract)
    latest = latest_cycle(db, contract.id)

    if resubmit:
        if (
            contract.status != ContractStatus.DRAFT.value
            or latest is None
            or latest.status != ApprovalCycleStatus.CHANGES_REQUESTED.value
        ):
            raise _conflict(
                "Only a contract with requested changes can be resubmitted."
            )
    else:
        if latest is not None:
            raise _conflict(
                "Changes were requested on this contract; resubmit it instead."
                if latest.status == ApprovalCycleStatus.CHANGES_REQUESTED.value
                else "This contract has already been submitted for approval."
            )
        if contract.status != ContractStatus.DRAFT.value:
            raise _conflict("Only draft contracts can be submitted for approval.")

    document = db.execute(
        select(ContractDocument).where(
            ContractDocument.contract_id == contract.id,
            ContractDocument.is_current.is_(True),
        )
    ).scalar_one_or_none()
    if document is None:
        raise _conflict("Upload a document before submitting for approval.")

    if payload.reviewer_id == payload.approver_id:
        raise _invalid("The reviewer and approver must be different people.")
    reviewer = _assignee(
        db, payload.reviewer_id, UserRole.LEGAL_REVIEWER, "Legal Reviewer"
    )
    approver = _assignee(
        db, payload.approver_id, UserRole.LEGAL_APPROVER, "Legal Approver"
    )
    for person in (reviewer, approver):
        if person.id in (contract.created_by, user.id):
            raise _invalid(
                "The contract's creator (or the person submitting it) cannot "
                "be its reviewer or approver."
            )

    comment = payload.comment or None
    before = contract.status
    cycle = ApprovalCycle(
        contract_id=contract.id,
        cycle_number=(latest.cycle_number + 1) if latest else 1,
        status=ApprovalCycleStatus.PENDING_REVIEWER.value,
        reviewer_id=reviewer.id,
        approver_id=approver.id,
        submitted_by=user.id,
        document_id=document.id,
        document_version=document.version_number,
        submitted_at=datetime.now(UTC),
    )
    db.add(cycle)
    db.flush()
    cycle.actions = []
    contract.status = ContractStatus.PENDING_REVIEW.value

    _record(
        db,
        contract=contract,
        cycle=cycle,
        actor=user,
        action_type=(
            ApprovalActionType.RESUBMITTED
            if resubmit
            else ApprovalActionType.SUBMITTED
        ),
        stage=ApprovalStage.CREATOR,
        comment=comment,
        contract_status_before=before,
        extra={
            "reviewer_id": str(reviewer.id),
            "approver_id": str(approver.id),
            "document_version": document.version_number,
        },
    )
    db.commit()
    return cycle


def _decide(
    db: Session,
    contract: Contract,
    user: User,
    *,
    action: str,
    comment: str | None,
    stage: ApprovalStage,
) -> ApprovalCycle:
    """Apply a reviewer-stage or approver-stage decision."""
    _lock_contract(db, contract)
    cycle = latest_cycle(db, contract.id)

    expected = (
        ApprovalCycleStatus.PENDING_REVIEWER
        if stage is ApprovalStage.REVIEWER
        else ApprovalCycleStatus.PENDING_APPROVER
    )
    if (
        cycle is None
        or cycle.status != expected.value
        or contract.status != ContractStatus.PENDING_REVIEW.value
    ):
        raise _conflict(
            "This contract is not awaiting legal review."
            if stage is ApprovalStage.REVIEWER
            else "This contract is not awaiting final approval."
        )

    if user.id == contract.created_by:
        raise _forbidden("You cannot decide on a contract you created.")

    allowed = set(available_actions(user, contract, cycle))
    ui_action = action  # recommend / approve / request_changes / reject
    if ui_action not in allowed:
        raise _forbidden(
            "You are not the assigned Legal Reviewer for this contract."
            if stage is ApprovalStage.REVIEWER
            else "You are not the assigned Legal Approver for this contract, "
            "or you already recommended this contract."
        )

    needs_comment = ui_action in ("request_changes", "reject")
    if needs_comment and len((comment or "").strip()) < MIN_DECISION_COMMENT:
        raise _invalid(
            f"A comment of at least {MIN_DECISION_COMMENT} characters is "
            "required to request changes or reject."
        )

    before = contract.status
    now = datetime.now(UTC)

    if ui_action == "recommend":
        cycle.status = ApprovalCycleStatus.PENDING_APPROVER.value
        action_type = ApprovalActionType.RECOMMENDED
    elif ui_action == "approve":
        cycle.status = ApprovalCycleStatus.APPROVED.value
        cycle.completed_at = now
        contract.status = ContractStatus.APPROVED.value
        action_type = ApprovalActionType.APPROVED
    elif ui_action == "reject":
        cycle.status = ApprovalCycleStatus.REJECTED.value
        cycle.completed_at = now
        contract.status = ContractStatus.REJECTED.value
        action_type = ApprovalActionType.REJECTED
    else:  # request_changes
        cycle.status = ApprovalCycleStatus.CHANGES_REQUESTED.value
        cycle.completed_at = now
        contract.status = ContractStatus.DRAFT.value
        action_type = ApprovalActionType.CHANGES_REQUESTED

    _record(
        db,
        contract=contract,
        cycle=cycle,
        actor=user,
        action_type=action_type,
        stage=stage,
        comment=(comment or None),
        contract_status_before=before,
    )
    db.commit()
    return cycle


def reviewer_action(
    db: Session, contract: Contract, user: User, action: str, comment: str | None
) -> ApprovalCycle:
    if action not in _REVIEWER_ACTIONS:
        raise _invalid("Unknown reviewer action.")
    return _decide(
        db, contract, user, action=action, comment=comment,
        stage=ApprovalStage.REVIEWER,
    )


def approver_action(
    db: Session, contract: Contract, user: User, action: str, comment: str | None
) -> ApprovalCycle:
    if action not in _APPROVER_ACTIONS:
        raise _invalid("Unknown approver action.")
    return _decide(
        db, contract, user, action=action, comment=comment,
        stage=ApprovalStage.APPROVER,
    )


# ------------------------------ dashboard -----------------------------------


def _queue_item(cycle: ApprovalCycle) -> QueueItem:
    contract = cycle.contract
    return QueueItem(
        contract_id=contract.id,
        contract_number=contract.contract_number,
        title=contract.title,
        counterparty_name=contract.counterparty_name,
        cycle_number=cycle.cycle_number,
        status=cycle.status,
        reviewer_name=cycle.reviewer.full_name,
        approver_name=cycle.approver.full_name,
        submitted_by_name=cycle.submitter.full_name,
        updated_at=cycle.updated_at,
    )


def _cycle_options():
    return (
        selectinload(ApprovalCycle.actions),
        selectinload(ApprovalCycle.contract),
        selectinload(ApprovalCycle.reviewer),
        selectinload(ApprovalCycle.approver),
        selectinload(ApprovalCycle.submitter),
    )


def build_summary(db: Session, user: User) -> ApprovalSummary:
    """What needs my action, and where my own contracts stand."""
    open_query = (
        select(ApprovalCycle)
        .options(*_cycle_options())
        .where(ApprovalCycle.status.in_(OPEN_STATUSES))
        .order_by(ApprovalCycle.updated_at.desc())
    )
    if user.role != UserRole.ADMIN.value:
        open_query = open_query.where(
            (ApprovalCycle.reviewer_id == user.id)
            | (ApprovalCycle.approver_id == user.id)
        )
    awaiting = [
        c
        for c in db.execute(open_query).scalars().all()
        if available_actions(user, c.contract, c)
    ]

    mine_cycles = (
        db.execute(
            select(ApprovalCycle)
            .options(*_cycle_options())
            .join(Contract, Contract.id == ApprovalCycle.contract_id)
            .where(Contract.created_by == user.id)
            .order_by(ApprovalCycle.contract_id, ApprovalCycle.cycle_number)
        )
        .scalars()
        .all()
    )
    latest_by_contract: dict[UUID, ApprovalCycle] = {}
    for cycle in mine_cycles:  # ascending, so the last one wins
        latest_by_contract[cycle.contract_id] = cycle
    mine = sorted(
        (
            c
            for c in latest_by_contract.values()
            if c.status in OPEN_STATUSES
            or c.status == ApprovalCycleStatus.CHANGES_REQUESTED.value
        ),
        key=lambda c: c.updated_at,
        reverse=True,
    )

    return ApprovalSummary(
        awaiting_my_action=[_queue_item(c) for c in awaiting[:QUEUE_LIMIT]],
        my_contracts=[_queue_item(c) for c in mine[:QUEUE_LIMIT]],
        awaiting_my_action_count=len(awaiting),
        under_approval_count=sum(1 for c in mine if c.status in OPEN_STATUSES),
        changes_requested_count=sum(
            1
            for c in mine
            if c.status == ApprovalCycleStatus.CHANGES_REQUESTED.value
        ),
    )
