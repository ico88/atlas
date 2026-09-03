"""node enrollment: node_enrollments

Revision ID: 0010_node_enrollment
Revises: 0009_message_citations
Create Date: 2026-09-03

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_node_enrollment"
down_revision: str | None = "0009_message_citations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "node_enrollments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=12), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_node_enrollments_node_id", "node_enrollments", ["node_id"], unique=True)
    op.create_index("ix_node_enrollments_status", "node_enrollments", ["status"])
    op.create_index("ix_node_enrollments_token_hash", "node_enrollments", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_node_enrollments_token_hash", table_name="node_enrollments")
    op.drop_index("ix_node_enrollments_status", table_name="node_enrollments")
    op.drop_index("ix_node_enrollments_node_id", table_name="node_enrollments")
    op.drop_table("node_enrollments")
