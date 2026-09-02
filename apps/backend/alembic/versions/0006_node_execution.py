"""node execution: tasks.required_capability + assigned_node_id

Revision ID: 0006_node_execution
Revises: 0005_rag_memory
Create Date: 2026-09-02

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_node_execution"
down_revision: str | None = "0005_rag_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks", sa.Column("required_capability", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "tasks", sa.Column("assigned_node_id", sa.String(length=36), nullable=True)
    )
    op.create_index("ix_tasks_required_capability", "tasks", ["required_capability"])
    op.create_index("ix_tasks_assigned_node_id", "tasks", ["assigned_node_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_assigned_node_id", table_name="tasks")
    op.drop_index("ix_tasks_required_capability", table_name="tasks")
    op.drop_column("tasks", "assigned_node_id")
    op.drop_column("tasks", "required_capability")
