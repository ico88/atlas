"""continuous improvement: improvement_proposals

Revision ID: 0017_improvements
Revises: 0016_evals
Create Date: 2026-09-03

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_improvements"
down_revision: str | None = "0016_evals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "improvement_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("suite_id", sa.String(length=36), nullable=True),
        sa.Column("baseline_model", sa.String(length=128), nullable=True),
        sa.Column("candidate_model", sa.String(length=128), nullable=True),
        sa.Column("change", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("baseline_run_id", sa.String(length=36), nullable=True),
        sa.Column("candidate_run_id", sa.String(length=36), nullable=True),
        sa.Column("comparison", sa.JSON(), nullable=True),
        sa.Column("recommendation", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["suite_id"], ["eval_suites.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_improvement_proposals_status", "improvement_proposals", ["status"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_improvement_proposals_status", table_name="improvement_proposals"
    )
    op.drop_table("improvement_proposals")
