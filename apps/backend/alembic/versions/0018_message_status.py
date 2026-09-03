"""chat lifecycle: messages.status + conversations.archived

Revision ID: 0018_message_status
Revises: 0017_improvements
Create Date: 2026-09-03

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_message_status"
down_revision: str | None = "0017_improvements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="complete",
        ),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "archived")
    op.drop_column("messages", "status")
