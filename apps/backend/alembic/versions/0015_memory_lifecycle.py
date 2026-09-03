"""memory lifecycle: provenance, retention, usage on memories

Revision ID: 0015_memory_lifecycle
Revises: 0014_environments
Create Date: 2026-09-03

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_memory_lifecycle"
down_revision: str | None = "0014_environments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("memories", sa.Column("source", sa.String(length=64), nullable=True))
    op.add_column("memories", sa.Column("source_id", sa.String(length=64), nullable=True))
    op.add_column(
        "memories",
        sa.Column("mem_type", sa.String(length=32), nullable=False, server_default="fact"),
    )
    op.add_column("memories", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column(
        "memories", sa.Column("importance", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "memories", sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("memories", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "memories", sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "memories", sa.Column("access_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.create_index("ix_memories_source", "memories", ["source"])
    op.create_index("ix_memories_expires_at", "memories", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_memories_expires_at", table_name="memories")
    op.drop_index("ix_memories_source", table_name="memories")
    op.drop_column("memories", "access_count")
    op.drop_column("memories", "last_accessed_at")
    op.drop_column("memories", "expires_at")
    op.drop_column("memories", "pinned")
    op.drop_column("memories", "importance")
    op.drop_column("memories", "tags")
    op.drop_column("memories", "mem_type")
    op.drop_column("memories", "source_id")
    op.drop_column("memories", "source")
