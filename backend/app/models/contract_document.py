"""Metadata for files attached to a contract.

The file bytes live on the local filesystem; this table keeps the location and
descriptive fields. Each upload creates a new row, so old versions are retained.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.contract import Contract
    from app.models.review_result import ReviewResult
    from app.models.user import User


class ContractDocument(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "contract_documents"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "version_number",
            name="uq_contract_documents_contract_id_version_number",
        ),
        CheckConstraint(
            "version_number >= 1",
            name="ck_contract_documents_version_number_positive",
        ),
        CheckConstraint(
            "file_size >= 0",
            name="ck_contract_documents_file_size_non_negative",
        ),
        # Partial unique index: at most one current document per contract.
        Index(
            "uq_contract_documents_one_current",
            "contract_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    contract: Mapped[Contract] = relationship(back_populates="documents")
    uploaded_by_user: Mapped[User] = relationship(
        back_populates="documents_uploaded"
    )
    review_results: Mapped[list[ReviewResult]] = relationship(
        back_populates="document",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ContractDocument id={self.id} contract_id={self.contract_id} "
            f"version={self.version_number}>"
        )
