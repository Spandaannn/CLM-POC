"""Allowed values for roles and workflow statuses.

These values are stored as text columns guarded by CHECK constraints rather
than PostgreSQL native ENUM types. Adding a new value later is then an ordinary
constraint change in a migration, without dealing with ALTER TYPE.
"""

from enum import Enum

from sqlalchemy import CheckConstraint


class UserRole(str, Enum):
    BUSINESS_USER = "business_user"
    LEGAL_REVIEWER = "legal_reviewer"
    LEGAL_APPROVER = "legal_approver"
    ADMIN = "admin"


class ContractStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class ApprovalScope(str, Enum):
    CONTRACT = "contract"
    CLAUSE = "clause"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalCycleStatus(str, Enum):
    """Where one submission cycle currently stands."""

    PENDING_REVIEWER = "pending_reviewer"  # awaiting the Legal Reviewer
    PENDING_APPROVER = "pending_approver"  # recommended, awaiting the Approver
    APPROVED = "approved"  # final, approved
    REJECTED = "rejected"  # final, rejected
    CHANGES_REQUESTED = "changes_requested"  # closed; creator may resubmit


class ApprovalActionType(str, Enum):
    SUBMITTED = "submitted"
    RESUBMITTED = "resubmitted"
    RECOMMENDED = "recommended"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"
    APPROVED = "approved"


class ApprovalStage(str, Enum):
    CREATOR = "creator"
    REVIEWER = "reviewer"
    APPROVER = "approver"


class ObligationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class ReviewStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


def enum_check(
    column: str, enum_type: type[Enum], constraint_name: str
) -> CheckConstraint:
    """Build a CHECK constraint from the values of an Enum class."""
    allowed = ", ".join(f"'{member.value}'" for member in enum_type)
    return CheckConstraint(f"{column} IN ({allowed})", name=constraint_name)
