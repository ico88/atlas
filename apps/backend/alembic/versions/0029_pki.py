"""internal PKI: issued certificates (ROADMAP R5)

Revision ID: 0029_pki
Revises: 0028_secrets
Create Date: 2026-09-07

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_pki"
down_revision: str | None = "0028_secrets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "issued_certs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("serial", sa.String(length=64), nullable=False),
        sa.Column("common_name", sa.String(length=255), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("serial"),
    )
    op.create_index("ix_issued_certs_serial", "issued_certs", ["serial"])
    op.create_index("ix_issued_certs_common_name", "issued_certs", ["common_name"])


def downgrade() -> None:
    op.drop_index("ix_issued_certs_common_name", table_name="issued_certs")
    op.drop_index("ix_issued_certs_serial", table_name="issued_certs")
    op.drop_table("issued_certs")
