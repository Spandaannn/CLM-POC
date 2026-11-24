"""The user account table."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import UserRole, enum_check
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.approval import Approval
    from app.models.audit_event import AuditEvent
    from app.models.contract import Contract
    from app.models.contract_document import ContractDocument
    from app.models.user_session import UserSession


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (enum_check("role", UserRole, "ck_users_role"),)

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Store emails in lowercase in application code so uniqueness is
    # effectively case-insensitive (PostgreSQL text comparison is case-sensitive).
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=UserRole.BUSINESS_USER.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )

    # A user is never hard-deleted while they own records: the foreign keys use
    # ON DELETE RESTRICT. Deactivate the account with is_active instead.
    contracts_created: Mapped[list[Contract]] = relationship(
        back_populates="created_by_user",
        passive_deletes=True,
    )
    documents_uploaded: Mapped[list[ContractDocument]] = relationship(
        back_populates="uploaded_by_user",
        passive_deletes=True,
    )
    approvals: Mapped[list[Approval]] = relationship(
        back_populates="approver",
        passive_deletes=True,
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="actor",
        passive_deletes=True,
    )
    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
