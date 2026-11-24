"""Import every model so SQLAlchemy registers it on Base.metadata.

Alembic reads Base.metadata, so a model that is not imported here would be
missing from migrations.
"""

from app.models.approval import Approval
from app.models.approval_cycle import ApprovalAction, ApprovalCycle
from app.models.audit_event import AuditEvent
from app.models.contract import Contract
from app.models.contract_document import ContractDocument
from app.models.obligation import Obligation
from app.models.review_result import ReviewResult
from app.models.user import User
from app.models.user_session import UserSession

__all__ = [
    "Approval",
    "ApprovalAction",
    "ApprovalCycle",
    "AuditEvent",
    "Contract",
    "ContractDocument",
    "Obligation",
    "ReviewResult",
    "User",
    "UserSession",
]
