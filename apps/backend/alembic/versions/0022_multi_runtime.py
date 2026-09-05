"""multi-runtime: runtimes, model_deployments, model_aliases + models columns

Revision ID: 0022_multi_runtime
Revises: 0021_fleet_compliance
Create Date: 2026-09-05

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_multi_runtime"
down_revision: str | None = "0021_fleet_compliance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extend the model registry with the fields aliases/deployments reference.
    op.add_column("models", sa.Column("model_key", sa.String(length=128), nullable=True))
    op.add_column("models", sa.Column("parameter_count", sa.String(length=32), nullable=True))
    op.add_column("models", sa.Column("quantization", sa.String(length=32), nullable=True))
    op.add_column("models", sa.Column("format", sa.String(length=32), nullable=True))
    op.create_index("ix_models_model_key", "models", ["model_key"])

    op.create_table(
        "runtimes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("runtime_type", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=True),
        sa.Column("endpoint", sa.String(length=255), nullable=True),
        sa.Column("api_key", sa.String(length=255), nullable=True),
        sa.Column("node_id", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="UNKNOWN"),
        sa.Column("supports_streaming", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("supports_embeddings", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("supports_tools", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("supports_vision", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_concurrency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_runtimes_name", "runtimes", ["name"])
    op.create_index("ix_runtimes_node_id", "runtimes", ["node_id"])

    op.create_table(
        "model_deployments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("model_key", sa.String(length=128), nullable=False),
        sa.Column("runtime_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=True),
        sa.Column("runtime_model_name", sa.String(length=128), nullable=False),
        sa.Column("loaded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="READY"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("max_context", sa.Integer(), nullable=True),
        sa.Column("max_concurrency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("estimated_tokens_per_second", sa.Float(), nullable=True),
        sa.Column("last_benchmark", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_deployments_model_key", "model_deployments", ["model_key"])
    op.create_index("ix_model_deployments_runtime_id", "model_deployments", ["runtime_id"])
    op.create_index("ix_model_deployments_node_id", "model_deployments", ["node_id"])

    op.create_table(
        "model_aliases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("alias", sa.String(length=64), nullable=False),
        sa.Column("targets", sa.JSON(), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alias"),
    )
    op.create_index("ix_model_aliases_alias", "model_aliases", ["alias"])


def downgrade() -> None:
    op.drop_index("ix_model_aliases_alias", table_name="model_aliases")
    op.drop_table("model_aliases")
    op.drop_index("ix_model_deployments_node_id", table_name="model_deployments")
    op.drop_index("ix_model_deployments_runtime_id", table_name="model_deployments")
    op.drop_index("ix_model_deployments_model_key", table_name="model_deployments")
    op.drop_table("model_deployments")
    op.drop_index("ix_runtimes_node_id", table_name="runtimes")
    op.drop_index("ix_runtimes_name", table_name="runtimes")
    op.drop_table("runtimes")
    op.drop_index("ix_models_model_key", table_name="models")
    op.drop_column("models", "format")
    op.drop_column("models", "quantization")
    op.drop_column("models", "parameter_count")
    op.drop_column("models", "model_key")
