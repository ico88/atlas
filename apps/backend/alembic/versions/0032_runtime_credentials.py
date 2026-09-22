"""allow encrypted runtime credentials

Revision ID: 0032_runtime_credentials
Revises: 0031_finetune
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_runtime_credentials"
down_revision: str | None = "0031_finetune"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("runtimes") as batch_op:
        batch_op.alter_column(
            "api_key", existing_type=sa.String(length=255), type_=sa.Text(), nullable=True
        )


def downgrade() -> None:
    with op.batch_alter_table("runtimes") as batch_op:
        batch_op.alter_column(
            "api_key", existing_type=sa.Text(), type_=sa.String(length=255), nullable=True
        )
