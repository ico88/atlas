"""fleet deployments: deployments, deployment_targets, nodes.desired_version

Revision ID: 0020_fleet_deployments
Revises: 0019_critical_reviews
Create Date: 2026-09-03

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_fleet_deployments"
down_revision: str | None = "0019_critical_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("desired_version", sa.String(length=64), nullable=True))

    op.create_table(
        "deployments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("target_version", sa.String(length=64), nullable=False),
        sa.Column("previous_version", sa.String(length=64), nullable=True),
        sa.Column("strategy", sa.String(length=32), nullable=False),
        sa.Column("canary_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deployments_status", "deployments", ["status"])

    op.create_table(
        "deployment_targets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deployment_id", sa.String(length=36), nullable=False),
        sa.Column("node_pk", sa.String(length=36), nullable=False),
        sa.Column("node_ref", sa.String(length=128), nullable=False),
        sa.Column("from_version", sa.String(length=64), nullable=True),
        sa.Column("wave", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_deployment_targets_deployment_id", "deployment_targets", ["deployment_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_deployment_targets_deployment_id", table_name="deployment_targets")
    op.drop_table("deployment_targets")
    op.drop_index("ix_deployments_status", table_name="deployments")
    op.drop_table("deployments")
    op.drop_column("nodes", "desired_version")
