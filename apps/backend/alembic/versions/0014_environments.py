"""environments: environments, environment_snapshots + scoping columns

Revision ID: 0014_environments
Revises: 0013_node_metrics
Create Date: 2026-09-03

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_environments"
down_revision: str | None = "0013_node_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "environments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=True),
        sa.Column("variables", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_environments_slug", "environments", ["slug"], unique=True)
    op.create_index("ix_environments_status", "environments", ["status"])

    op.create_table(
        "environment_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("environment_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("manifest", sa.JSON(), nullable=True),
        sa.Column("variables", sa.JSON(), nullable=True),
        sa.Column("stats", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_environment_snapshots_environment_id",
        "environment_snapshots",
        ["environment_id"],
    )

    op.add_column("tasks", sa.Column("environment_id", sa.String(length=36), nullable=True))
    op.create_index("ix_tasks_environment_id", "tasks", ["environment_id"])
    op.add_column("queries", sa.Column("environment_id", sa.String(length=36), nullable=True))
    op.create_index("ix_queries_environment_id", "queries", ["environment_id"])
    op.add_column("memories", sa.Column("environment_id", sa.String(length=36), nullable=True))
    op.create_index("ix_memories_environment_id", "memories", ["environment_id"])


def downgrade() -> None:
    op.drop_index("ix_memories_environment_id", table_name="memories")
    op.drop_column("memories", "environment_id")
    op.drop_index("ix_queries_environment_id", table_name="queries")
    op.drop_column("queries", "environment_id")
    op.drop_index("ix_tasks_environment_id", table_name="tasks")
    op.drop_column("tasks", "environment_id")
    op.drop_index("ix_environment_snapshots_environment_id", table_name="environment_snapshots")
    op.drop_table("environment_snapshots")
    op.drop_index("ix_environments_status", table_name="environments")
    op.drop_index("ix_environments_slug", table_name="environments")
    op.drop_table("environments")
