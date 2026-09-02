"""manual escalation: escalations

Revision ID: 0007_escalations
Revises: 0006_node_execution
Create Date: 2026-09-02

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_escalations"
down_revision: str | None = "0006_node_execution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "escalations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=True),
        sa.Column("target", sa.String(length=16), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("package", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("validation", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_escalations_subject_id", "escalations", ["subject_id"])
    op.create_index("ix_escalations_correlation_id", "escalations", ["correlation_id"])
    op.create_index("ix_escalations_status", "escalations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_escalations_status", table_name="escalations")
    op.drop_index("ix_escalations_correlation_id", table_name="escalations")
    op.drop_index("ix_escalations_subject_id", table_name="escalations")
    op.drop_table("escalations")
