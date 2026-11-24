"""Contract queries, access rules, and audit-event recording."""

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.audit_event import AuditEvent
from app.models.contract import Contract
from app.models.enums import ContractStatus, UserRole
from app.models.user import User
from app.schemas.contract import ContractCreate, ContractRead, ContractUpdate

# These roles need to see every contract for review and approval work. A
# business user can only see the contracts they created.
ALL_CONTRACT_ROLES = {
    UserRole.LEGAL_REVIEWER.value,
    UserRole.LEGAL_APPROVER.value,
    UserRole.ADMIN.value,
}

# Only the creator or an administrator can change contract metadata. Workflow
# decisions (approvals) are intentionally out of scope for this phase.
ADMIN_ROLE = UserRole.ADMIN.value

AUDIT_ENTITY_TYPE = "contract"

# --- approval workflow guards ------------------------------------------------
# Only a draft's content can change. Statuses draft / pending_review / approved /
# rejected are controlled by the approval workflow, never by a plain edit.
# After approval a contract may move through its lifecycle manually.
LIFECYCLE_STATUSES = {
    ContractStatus.ACTIVE.value,
    ContractStatus.EXPIRED.value,
    ContractStatus.TERMINATED.value,
}
LIFECYCLE_SOURCE_STATUSES = LIFECYCLE_STATUSES | {ContractStatus.APPROVED.value}


def content_locked_message(contract: Contract, what: str = "edited") -> str:
    """Why this contract's content can't be changed right now."""
    if contract.status == ContractStatus.PENDING_REVIEW.value:
        return (
            f"This contract is under approval and cannot be {what} until "
            "changes are requested."
        )
    if contract.status == ContractStatus.REJECTED.value:
        return f"This contract was rejected and can no longer be {what}."
    return f"Only draft contracts can be {what}. Approved contracts are fixed."


def ensure_content_editable(contract: Contract, what: str = "edited") -> None:
    """Raise 409 unless the contract is a draft (see the approval workflow)."""
    if contract.status != ContractStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=content_locked_message(contract, what),
        )


def _enforce_workflow_rules(
    contract: Contract, changes: dict[str, dict[str, object]]
) -> None:
    if any(field != "status" for field in changes):
        ensure_content_editable(contract)

    if "status" in changes:
        new_status = changes["status"]["to"]
        if new_status not in LIFECYCLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"The status '{new_status}' is set by the approval "
                    "workflow and cannot be changed here."
                ),
            )
        if contract.status not in LIFECYCLE_SOURCE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "A contract must be approved before it can be Active, "
                    "Expired, or Terminated."
                ),
            )


def generate_contract_number(db: Session) -> str:
    """Return an unused contract number.

    Format: ``CTR-<year>-<8 random uppercase hex characters>``. A random
    suffix avoids a sequence migration and is safe for a POC; the unique
    database constraint remains the final guard against duplicates.
    """
    year = datetime.now(UTC).year

    for _ in range(10):
        candidate = f"CTR-{year}-{uuid4().hex[:8].upper()}"
        existing = db.execute(
            select(Contract.id).where(Contract.contract_number == candidate)
        ).scalar_one_or_none()
        if existing is None:
            return candidate

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not generate a unique contract number",
    )


def can_view_contract(user: User, contract: Contract) -> bool:
    """Return whether the user may read this contract."""
    return user.role in ALL_CONTRACT_ROLES or contract.created_by == user.id


def can_edit_contract(user: User, contract: Contract) -> bool:
    """Return whether the user may change this contract's metadata."""
    return user.role == ADMIN_ROLE or contract.created_by == user.id


def get_contract_for_read(
    db: Session, contract_id: UUID, user: User
) -> Contract:
    """Load a contract the user may read, or raise 404/403."""
    contract = db.execute(
        select(Contract)
        .options(selectinload(Contract.created_by_user))
        .where(Contract.id == contract_id)
    ).scalar_one_or_none()

    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found",
        )

    if not can_view_contract(user, contract):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this contract",
        )

    return contract


def get_contract_for_update(
    db: Session, contract_id: UUID, user: User
) -> Contract:
    """Load a contract the user may edit, or raise 404/403."""
    contract = get_contract_for_read(db, contract_id, user)

    if not can_edit_contract(user, contract):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this contract",
        )

    return contract


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so a search treats them as literal characters."""
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def list_contracts(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    search: str | None,
    contract_status: ContractStatus | None,
    contract_type: str | None,
) -> tuple[list[Contract], int]:
    """Return one page of visible contracts and the unfiltered-by-page total."""
    filters = []

    if user.role not in ALL_CONTRACT_ROLES:
        filters.append(Contract.created_by == user.id)

    if search:
        pattern = f"%{_escape_like(search.strip())}%"
        filters.append(
            or_(
                Contract.title.ilike(pattern, escape="\\"),
                Contract.contract_number.ilike(pattern, escape="\\"),
                Contract.counterparty_name.ilike(pattern, escape="\\"),
            )
        )

    if contract_status is not None:
        filters.append(Contract.status == contract_status.value)

    if contract_type:
        filters.append(
            func.lower(Contract.contract_type)
            == contract_type.strip().lower()
        )

    total = db.execute(
        select(func.count(Contract.id)).where(*filters)
    ).scalar_one()

    contracts = list(
        db.execute(
            select(Contract)
            .options(selectinload(Contract.created_by_user))
            .where(*filters)
            .order_by(Contract.created_at.desc(), Contract.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    return contracts, total


def _json_value(value: object) -> object:
    """Convert model values into JSON-safe values for the audit log."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def record_audit_event(
    db: Session,
    *,
    contract: Contract,
    actor: User,
    action: str,
    details: dict[str, object],
) -> None:
    """Add an audit row to the current transaction."""
    db.add(
        AuditEvent(
            contract_id=contract.id,
            actor_user_id=actor.id,
            action=action,
            entity_type=AUDIT_ENTITY_TYPE,
            entity_id=str(contract.id),
            details=details,
        )
    )


def create_contract(
    db: Session, payload: ContractCreate, user: User
) -> Contract:
    """Create a draft contract and its creation audit event atomically."""
    contract = Contract(
        contract_number=generate_contract_number(db),
        title=payload.title,
        contract_type=payload.contract_type,
        counterparty_name=payload.counterparty_name,
        description=payload.description,
        contract_value=payload.contract_value,
        currency=payload.currency,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=ContractStatus.DRAFT.value,
        # Never trust a value from the request; the authenticated user owns
        # the contract.
        created_by=user.id,
    )
    db.add(contract)
    db.flush()

    record_audit_event(
        db,
        contract=contract,
        actor=user,
        action="contract.created",
        details={
            "contract_number": contract.contract_number,
            "title": contract.title,
            "contract_type": contract.contract_type,
            "counterparty_name": contract.counterparty_name,
            "status": contract.status,
        },
    )

    db.commit()
    db.refresh(contract)
    return contract


def update_contract(
    db: Session, contract: Contract, payload: ContractUpdate, user: User
) -> Contract:
    """Apply changed fields and record one audit event for the update."""
    data = payload.model_dump(exclude_unset=True)

    if "status" in data and data["status"] is not None:
        data["status"] = (
            data["status"].value
            if isinstance(data["status"], ContractStatus)
            else data["status"]
        )

    # Validate the combined date range before changing the ORM object.
    merged_start = (
        data["start_date"] if "start_date" in data else contract.start_date
    )
    merged_end = data["end_date"] if "end_date" in data else contract.end_date

    if (
        merged_start is not None
        and merged_end is not None
        and merged_end < merged_start
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="end_date must be on or after start_date",
        )

    changes: dict[str, dict[str, object]] = {}

    for field_name, new_value in data.items():
        old_value = getattr(contract, field_name)
        if old_value == new_value:
            continue
        changes[field_name] = {
            "from": _json_value(old_value),
            "to": _json_value(new_value),
        }

    if not changes:
        # A request that changes nothing is a successful no-op. Do not create
        # a misleading audit event.
        return contract

    _enforce_workflow_rules(contract, changes)

    for field_name in changes:
        setattr(contract, field_name, data[field_name])

    record_audit_event(
        db,
        contract=contract,
        actor=user,
        action="contract.updated",
        details={
            "contract_number": contract.contract_number,
            "changes": changes,
        },
    )

    db.commit()
    db.refresh(contract)
    return contract


def contract_to_read(contract: Contract) -> ContractRead:
    """Build the API response from an ORM object."""
    creator = contract.created_by_user
    return ContractRead(
        id=contract.id,
        contract_number=contract.contract_number,
        title=contract.title,
        contract_type=contract.contract_type,
        counterparty_name=contract.counterparty_name,
        description=contract.description,
        contract_value=contract.contract_value,
        currency=contract.currency,
        start_date=contract.start_date,
        end_date=contract.end_date,
        status=contract.status,
        created_by=contract.created_by,
        created_by_name=creator.full_name if creator is not None else None,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
    )
