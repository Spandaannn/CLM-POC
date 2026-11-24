"""AI-assisted review output, stored for human review.

Each row is one review of one document version. Structured parts of the
result live in separate JSONB columns so they can be queried and displayed
without re-parsing raw AI text; the raw response is intentionally not stored.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ReviewStatus, enum_check
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.contract import Contract
    from app.models.contract_document import ContractDocument
    from app.models.user import User


class ReviewResult(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "review_results"
    __table_args__ = (
        enum_check("status", ReviewStatus, "ck_review_results_status"),
    )

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The document is optional so a review survives if the file row is removed.
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contract_documents.id", ondelete="SET NULL"),
        index=True,
    )
    # Copied from the document at review time, so the reviewed version stays
    # known even if the document row is later removed.
    document_version: Mapped[int | None] = mapped_column(Integer)

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    review_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=ReviewStatus.COMPLETED.value,
    )
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # Executive summary: `summary` holds the overview paragraph and
    # `summary_details` the parties, commercial terms, and dates/obligations.
    summary: Mapped[str | None] = mapped_column(Text)
    summary_details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    extracted_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    clauses: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # Risk findings (AI observations). A JSON array of finding objects.
    findings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    # Results of comparing the contract with the configured playbook rules.
    playbook_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    playbook_version: Mapped[str | None] = mapped_column(String(100))
    # Extraction statistics (characters, truncation, method). No contract text.
    source_info: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    contract: Mapped[Contract] = relationship(back_populates="review_results")
    document: Mapped[ContractDocument | None] = relationship(
        back_populates="review_results"
    )
    initiator: Mapped[User | None] = relationship(
        foreign_keys=[initiated_by]
    )

    def __repr__(self) -> str:
        return f"<ReviewResult id={self.id} contract_id={self.contract_id}>"
