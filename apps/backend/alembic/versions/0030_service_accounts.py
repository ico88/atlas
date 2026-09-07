"""service accounts (ROADMAP R5)

Revision ID: 0030_service_accounts
Revises: 0029_pki
Create Date: 2026-09-07

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_service_accounts"
down_revision: str | None = "0029_pki"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="user"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_service_accounts_name", "service_accounts", ["name"])
    op.create_index("ix_service_accounts_token_prefix", "service_accounts", ["token_prefix"])


def downgrade() -> None:
    op.drop_index("ix_service_accounts_token_prefix", table_name="service_accounts")
    op.drop_index("ix_service_accounts_name", table_name="service_accounts")
    op.drop_table("service_accounts")
