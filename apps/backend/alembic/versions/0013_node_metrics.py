"""resource telemetry: node_metrics

Revision ID: 0013_node_metrics
Revises: 0012_task_lease
Create Date: 2026-09-03

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_node_metrics"
down_revision: str | None = "0012_task_lease"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "node_metrics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("load1", sa.Float(), nullable=True),
        sa.Column("ram_free_mb", sa.Integer(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_node_metrics_node_id", "node_metrics", ["node_id"])
    op.create_index("ix_node_metrics_created_at", "node_metrics", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_node_metrics_created_at", table_name="node_metrics")
    op.drop_index("ix_node_metrics_node_id", table_name="node_metrics")
    op.drop_table("node_metrics")
