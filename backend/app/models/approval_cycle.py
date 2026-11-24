"""Approval workflow: one row per submission cycle plus an append-only action log.

A contract is submitted for approval (cycle 1). If changes are requested and the
creator resubmits, a *new* cycle (2, 3, ...) is created; earlier cycles and
their actions are never modified or removed. The older ``approvals`` table
(per-approver, per-clause decisions) is separate and unused by this workflow.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    ApprovalActionType,
    ApprovalCycleStatus,
    ApprovalStage,
    enum_check,
)
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.contract import Contract
    from app.models.user import User


class ApprovalCycle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "approval_cycles"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "cycle_number",
            name="uq_approval_cycles_contract_id_cycle_number",
        ),
        CheckConstraint(
            "cycle_number >= 1", name="ck_approval_cycles_cycle_number_positive"
        ),
        enum_check("status", ApprovalCycleStatus, "ck_approval_cycles_status"),
        CheckConstraint(
            "reviewer_id <> approver_id",
            name="ck_approval_cycles_reviewer_not_approver",
        ),
        # At most one open (in-progress) cycle per contract.
        Index(
            "uq_approval_cycles_one_open",
            "contract_id",
            unique=True,
            postgresql_where=text(
                "status IN ('pending_reviewer', 'pending_approver')"
            ),
        ),
    )

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)

    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # The document version that was submitted (kept even if the row is gone).
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contract_documents.id", ondelete="SET NULL")
    )
    document_version: Mapped[int | None] = mapped_column(Integer)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Set when the cycle reaches approved, rejected, or changes_requested.
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    contract: Mapped[Contract] = relationship(back_populates="approval_cycles")
    reviewer: Mapped[User] = relationship(foreign_keys=[reviewer_id])
    approver: Mapped[User] = relationship(foreign_keys=[approver_id])
    submitter: Mapped[User] = relationship(foreign_keys=[submitted_by])
    actions: Mapped[list[ApprovalAction]] = relationship(
        back_populates="cycle",
        order_by="ApprovalAction.sequence",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ApprovalCycle id={self.id} contract_id={self.contract_id} "
            f"cycle={self.cycle_number} status={self.status}>"
        )


class ApprovalAction(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One recorded step. Rows are only ever inserted, never updated."""

    __tablename__ = "approval_actions"
    __table_args__ = (
        UniqueConstraint(
            "cycle_id", "sequence", name="uq_approval_actions_cycle_id_sequence"
        ),
        enum_check(
            "action_type", ApprovalActionType, "ck_approval_actions_action_type"
        ),
        enum_check("stage", ApprovalStage, "ck_approval_actions_stage"),
    )

    cycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("approval_cycles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Position within the cycle (1, 2, 3, ...), so order is never ambiguous.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(24), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    comment: Mapped[str | None] = mapped_column(Text)

    cycle: Mapped[ApprovalCycle] = relationship(back_populates="actions")
    actor: Mapped[User] = relationship(foreign_keys=[actor_id])

    def __repr__(self) -> str:
        return (
            f"<ApprovalAction id={self.id} cycle_id={self.cycle_id} "
            f"{self.action_type}>"
        )
