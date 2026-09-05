"""deployment load policy (multi-runtime Fase 4)

Revision ID: 0024_deployment_load_policy
Revises: 0023_routing_policies
Create Date: 2026-09-05

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_deployment_load_policy"
down_revision: str | None = "0023_routing_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_deployments",
        sa.Column("load_policy", sa.String(length=16), nullable=False, server_default="ON_DEMAND"),
    )


def downgrade() -> None:
    op.drop_column("model_deployments", "load_policy")
