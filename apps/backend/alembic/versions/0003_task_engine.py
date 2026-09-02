"""task engine: retries, idempotency, dependencies

Revision ID: 0003_task_engine
Revises: 0002_chat_and_models
Create Date: 2026-09-02

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_task_engine"
down_revision: str | None = "0002_chat_and_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tasks",
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tasks", sa.Column("idempotency_key", sa.String(length=128), nullable=True)
    )
    op.create_index("ix_tasks_idempotency_key", "tasks", ["idempotency_key"])

    op.create_table(
        "task_dependencies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("depends_on_task_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["depends_on_task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_dependencies_task_id", "task_dependencies", ["task_id"])
    op.create_index(
        "ix_task_dependencies_depends_on_task_id",
        "task_dependencies",
        ["depends_on_task_id"],
    )


def downgrade() -> None:
    op.drop_table("task_dependencies")
    op.drop_index("ix_tasks_idempotency_key", table_name="tasks")
    op.drop_column("tasks", "idempotency_key")
    op.drop_column("tasks", "max_retries")
    op.drop_column("tasks", "retries")
