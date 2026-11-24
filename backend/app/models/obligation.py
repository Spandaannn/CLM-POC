"""Follow-up duties created from a contract, such as renewal notices."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ObligationStatus, enum_check
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.contract import Contract


class Obligation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "obligations"
    __table_args__ = (
        enum_check("status", ObligationStatus, "ck_obligations_status"),
        Index("ix_obligations_due_date", "due_date"),
    )

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    responsible_party: Mapped[str] = mapped_column(String(255), nullable=False)
    # Optional: some obligations are recorded before a deadline is agreed.
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=ObligationStatus.PENDING.value,
    )

    contract: Mapped[Contract] = relationship(back_populates="obligations")

    def __repr__(self) -> str:
        return f"<Obligation id={self.id} title={self.title!r}>"
