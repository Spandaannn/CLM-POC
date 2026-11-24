"""Add the contract approval workflow tables.

Additive only: creates ``approval_cycles`` (one row per submission cycle) and
``approval_actions`` (append-only decision log). The older ``approvals`` table
is not touched.

Revision ID: 20261125_0003
Revises: 20261124_0002
Create Date: 2026-11-25 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261125_0003"
down_revision: str | None = "20261124_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _timestamp(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "approval_cycles",
        _uuid_pk(),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_version", sa.Integer(), nullable=True),
        _timestamp("submitted_at"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_approval_cycles"),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contracts.id"],
            name="fk_approval_cycles_contract_id_contracts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
            name="fk_approval_cycles_reviewer_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approver_id"],
            ["users.id"],
            name="fk_approval_cycles_approver_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"],
            ["users.id"],
            name="fk_approval_cycles_submitted_by_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["contract_documents.id"],
            name="fk_approval_cycles_document_id_contract_documents",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "contract_id",
            "cycle_number",
            name="uq_approval_cycles_contract_id_cycle_number",
        ),
        sa.CheckConstraint(
            "cycle_number >= 1", name="ck_approval_cycles_cycle_number_positive"
        ),
        sa.CheckConstraint(
            "status IN ('pending_reviewer', 'pending_approver', 'approved', "
            "'rejected', 'changes_requested')",
            name="ck_approval_cycles_status",
        ),
        sa.CheckConstraint(
            "reviewer_id <> approver_id",
            name="ck_approval_cycles_reviewer_not_approver",
        ),
    )
    op.create_index(
        "ix_approval_cycles_contract_id", "approval_cycles", ["contract_id"]
    )
    op.create_index(
        "ix_approval_cycles_reviewer_id", "approval_cycles", ["reviewer_id"]
    )
    op.create_index(
        "ix_approval_cycles_approver_id", "approval_cycles", ["approver_id"]
    )
    op.create_index(
        "uq_approval_cycles_one_open",
        "approval_cycles",
        ["contract_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending_reviewer', 'pending_approver')"
        ),
    )

    op.create_table(
        "approval_actions",
        _uuid_pk(),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=24), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_approval_actions"),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["approval_cycles.id"],
            name="fk_approval_actions_cycle_id_approval_cycles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_approval_actions_actor_id_users",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "cycle_id", "sequence", name="uq_approval_actions_cycle_id_sequence"
        ),
        sa.CheckConstraint(
            "action_type IN ('submitted', 'resubmitted', 'recommended', "
            "'changes_requested', 'rejected', 'approved')",
            name="ck_approval_actions_action_type",
        ),
        sa.CheckConstraint(
            "stage IN ('creator', 'reviewer', 'approver')",
            name="ck_approval_actions_stage",
        ),
    )
    op.create_index(
        "ix_approval_actions_cycle_id", "approval_actions", ["cycle_id"]
    )
    op.create_index(
        "ix_approval_actions_actor_id", "approval_actions", ["actor_id"]
    )


def downgrade() -> None:
    op.drop_table("approval_actions")
    op.drop_table("approval_cycles")
