"""routing policies (multi-runtime Fase 3 / M9)

Revision ID: 0023_routing_policies
Revises: 0022_multi_runtime
Create Date: 2026-09-05

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_routing_policies"
down_revision: str | None = "0022_multi_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "routing_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("required_capabilities", sa.JSON(), nullable=True),
        sa.Column("preferred_alias", sa.String(length=64), nullable=True),
        sa.Column("privacy", sa.String(length=24), nullable=False, server_default="LOCAL_PREFERRED"),
        sa.Column("max_latency_ms", sa.Integer(), nullable=True),
        sa.Column("fallback", sa.JSON(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_type"),
    )
    op.create_index("ix_routing_policies_task_type", "routing_policies", ["task_type"])


def downgrade() -> None:
    op.drop_index("ix_routing_policies_task_type", table_name="routing_policies")
    op.drop_table("routing_policies")
