"""AI-assisted review output, stored for human review."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.contract import Contract
    from app.models.contract_document import ContractDocument


class ReviewResult(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "review_results"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The review may cover a contract as a whole, so the document is optional.
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contract_documents.id", ondelete="SET NULL"),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    review_type: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)

    # A JSON array of finding objects, e.g. [{"clause": "5.2", "risk": "high"}].
    findings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    contract: Mapped[Contract] = relationship(back_populates="review_results")
    document: Mapped[ContractDocument | None] = relationship(
        back_populates="review_results"
    )

    def __repr__(self) -> str:
        return f"<ReviewResult id={self.id} contract_id={self.contract_id}>"
