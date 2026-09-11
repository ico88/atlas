"""local fine-tuning: datasets, examples, jobs (ROADMAP self-improvement)

Revision ID: 0031_finetune
Revises: 0030_service_accounts
Create Date: 2026-09-11

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_finetune"
down_revision: str | None = "0030_service_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "finetune_datasets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_model", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_finetune_datasets_name", "finetune_datasets", ["name"])

    op.create_table(
        "finetune_examples",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column("quality", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("included", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["finetune_datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "content_hash", name="uq_finetune_example_hash"),
    )
    op.create_index("ix_finetune_examples_dataset_id", "finetune_examples", ["dataset_id"])
    op.create_index("ix_finetune_examples_content_hash", "finetune_examples", ["content_hash"])

    op.create_table(
        "finetune_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("base_model", sa.String(length=128), nullable=False),
        sa.Column("adapter_name", sa.String(length=128), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False, server_default="lora"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("example_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hyperparams", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["finetune_datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_finetune_jobs_dataset_id", "finetune_jobs", ["dataset_id"])
    op.create_index("ix_finetune_jobs_status", "finetune_jobs", ["status"])
    op.create_index("ix_finetune_jobs_task_id", "finetune_jobs", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_finetune_jobs_task_id", table_name="finetune_jobs")
    op.drop_index("ix_finetune_jobs_status", table_name="finetune_jobs")
    op.drop_index("ix_finetune_jobs_dataset_id", table_name="finetune_jobs")
    op.drop_table("finetune_jobs")
    op.drop_index("ix_finetune_examples_content_hash", table_name="finetune_examples")
    op.drop_index("ix_finetune_examples_dataset_id", table_name="finetune_examples")
    op.drop_table("finetune_examples")
    op.drop_index("ix_finetune_datasets_name", table_name="finetune_datasets")
    op.drop_table("finetune_datasets")
