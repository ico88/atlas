"""resilient scheduler: task lease + checkpoint

Revision ID: 0012_task_lease
Revises: 0011_app_settings
Create Date: 2026-09-03

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_task_lease"
down_revision: str | None = "0011_app_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("lease_token", sa.String(length=36), nullable=True))
    op.add_column(
        "tasks", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("tasks", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("checkpoint", sa.JSON(), nullable=True))
    op.create_index("ix_tasks_lease_expires_at", "tasks", ["lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_tasks_lease_expires_at", table_name="tasks")
    op.drop_column("tasks", "checkpoint")
    op.drop_column("tasks", "heartbeat_at")
    op.drop_column("tasks", "lease_expires_at")
    op.drop_column("tasks", "lease_token")
