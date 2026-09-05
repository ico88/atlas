"""critical review: critical_reviews

Revision ID: 0019_critical_reviews
Revises: 0018_message_status
Create Date: 2026-09-03

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_critical_reviews"
down_revision: str | None = "0018_message_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "critical_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("references", sa.JSON(), nullable=True),
        sa.Column("best_answer", sa.Text(), nullable=True),
        sa.Column("best_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("rounds", sa.JSON(), nullable=True),
        sa.Column("consensus", sa.JSON(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("round_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("critical_reviews")
