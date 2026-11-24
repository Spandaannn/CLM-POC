"""Approval decisions for a whole contract or a specific clause."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ApprovalScope, ApprovalStatus, enum_check
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.contract import Contract
    from app.models.user import User


class Approval(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        enum_check("approval_scope", ApprovalScope, "ck_approvals_approval_scope"),
        enum_check("status", ApprovalStatus, "ck_approvals_status"),
        CheckConstraint(
            "approval_scope <> 'clause' OR clause_reference IS NOT NULL",
            name="ck_approvals_clause_reference_required",
        ),
        Index("ix_approvals_contract_id_status", "contract_id", "status"),
    )

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    approval_scope: Mapped[str] = mapped_column(String(16), nullable=False)
    clause_reference: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=ApprovalStatus.PENDING.value,
    )
    comments: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    contract: Mapped[Contract] = relationship(back_populates="approvals")
    approver: Mapped[User] = relationship(back_populates="approvals")

    def __repr__(self) -> str:
        return f"<Approval id={self.id} contract_id={self.contract_id} status={self.status}>"
