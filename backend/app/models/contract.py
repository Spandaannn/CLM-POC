"""The central contract record."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ContractStatus, enum_check
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.approval import Approval
    from app.models.audit_event import AuditEvent
    from app.models.contract_document import ContractDocument
    from app.models.obligation import Obligation
    from app.models.review_result import ReviewResult
    from app.models.user import User


class Contract(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contracts"
    __table_args__ = (
        enum_check("status", ContractStatus, "ck_contracts_status"),
        CheckConstraint(
            "contract_value IS NULL OR contract_value >= 0",
            name="ck_contracts_contract_value_non_negative",
        ),
        CheckConstraint(
            "start_date IS NULL OR end_date IS NULL OR end_date >= start_date",
            name="ck_contracts_date_range",
        ),
        # Status and end date are the usual list/filter and renewal criteria.
        Index("ix_contracts_status", "status"),
        Index("ix_contracts_end_date", "end_date"),
    )

    contract_number: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    contract_type: Mapped[str] = mapped_column(String(64), nullable=False)
    counterparty_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # NUMERIC (not float) keeps money exact. 18 digits, 2 decimal places.
    contract_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default="INR"
    )

    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=ContractStatus.DRAFT.value,
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    created_by_user: Mapped[User] = relationship(
        back_populates="contracts_created"
    )
    documents: Mapped[list[ContractDocument]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    approvals: Mapped[list[Approval]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    review_results: Mapped[list[ReviewResult]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    obligations: Mapped[list[Obligation]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # Audit events are kept if a contract is deleted, so the history survives.
    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="contract",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Contract id={self.id} number={self.contract_number!r}>"
