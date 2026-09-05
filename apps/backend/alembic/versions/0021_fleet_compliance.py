"""fleet compliance & remediation: nodes.quarantined + remediation_events

Revision ID: 0021_fleet_compliance
Revises: 0020_fleet_deployments
Create Date: 2026-09-03

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_fleet_compliance"
down_revision: str | None = "0020_fleet_deployments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "nodes",
        sa.Column("quarantined", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "remediation_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("node_ref", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("automatic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_remediation_events_node_ref", "remediation_events", ["node_ref"])


def downgrade() -> None:
    op.drop_index("ix_remediation_events_node_ref", table_name="remediation_events")
    op.drop_table("remediation_events")
    op.drop_column("nodes", "quarantined")
