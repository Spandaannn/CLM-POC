"""Add structured AI review fields to review_results.

Adds the reviewed document version, status, initiating user, and separate
JSONB columns for the summary details, metadata, clauses, playbook results,
and extraction statistics. The existing ``findings`` column keeps the risk
findings. Existing rows (if any) receive safe defaults.

Revision ID: 20261124_0002
Revises: 20261123_0001
Create Date: 2026-11-24 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261124_0002"
down_revision: str | None = "20261123_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _jsonb_column(name: str, empty: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(),
        server_default=sa.text(f"'{empty}'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    op.add_column(
        "review_results", sa.Column("document_version", sa.Integer(), nullable=True)
    )
    op.add_column(
        "review_results",
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="completed",
            nullable=False,
        ),
    )
    op.add_column(
        "review_results",
        sa.Column("initiated_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("review_results", _jsonb_column("summary_details", "{}"))
    op.add_column("review_results", _jsonb_column("extracted_metadata", "{}"))
    op.add_column("review_results", _jsonb_column("clauses", "[]"))
    op.add_column("review_results", _jsonb_column("playbook_results", "[]"))
    op.add_column(
        "review_results",
        sa.Column("playbook_version", sa.String(length=100), nullable=True),
    )
    op.add_column("review_results", _jsonb_column("source_info", "{}"))

    op.create_foreign_key(
        "fk_review_results_initiated_by_users",
        "review_results",
        "users",
        ["initiated_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_review_results_initiated_by", "review_results", ["initiated_by"]
    )
    op.create_check_constraint(
        "ck_review_results_status",
        "review_results",
        "status IN ('completed', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_review_results_status", "review_results", type_="check"
    )
    op.drop_index("ix_review_results_initiated_by", table_name="review_results")
    op.drop_constraint(
        "fk_review_results_initiated_by_users",
        "review_results",
        type_="foreignkey",
    )
    for column in (
        "source_info",
        "playbook_version",
        "playbook_results",
        "clauses",
        "extracted_metadata",
        "summary_details",
        "initiated_by",
        "status",
        "document_version",
    ):
        op.drop_column("review_results", column)
