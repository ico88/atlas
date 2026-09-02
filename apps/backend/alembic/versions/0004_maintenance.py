"""maintenance core: issues, runs, git_actions + approval subject

Revision ID: 0004_maintenance
Revises: 0003_task_engine
Create Date: 2026-09-02

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_maintenance"
down_revision: str | None = "0003_task_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("approvals", sa.Column("subject_type", sa.String(length=64), nullable=True))
    op.add_column("approvals", sa.Column("subject_id", sa.String(length=36), nullable=True))
    op.create_index("ix_approvals_subject_id", "approvals", ["subject_id"])

    op.create_table(
        "maintenance_issues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("service", sa.String(length=64), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("sample", sa.JSON(), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_maintenance_issues_fingerprint",
        "maintenance_issues",
        ["fingerprint"],
        unique=True,
    )
    op.create_index("ix_maintenance_issues_status", "maintenance_issues", ["status"])

    op.create_table(
        "maintenance_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("issue_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=True),
        sa.Column("analysis", sa.Text(), nullable=True),
        sa.Column("patch", sa.Text(), nullable=True),
        sa.Column("tests_summary", sa.Text(), nullable=True),
        sa.Column("pr_url", sa.String(length=512), nullable=True),
        sa.Column("risk", sa.String(length=16), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["maintenance_issues.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_runs_issue_id", "maintenance_runs", ["issue_id"])

    op.create_table(
        "git_actions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("issue_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=True),
        sa.Column("target", sa.String(length=255), nullable=True),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["maintenance_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["maintenance_issues.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("git_actions")
    op.drop_table("maintenance_runs")
    op.drop_index("ix_maintenance_issues_status", table_name="maintenance_issues")
    op.drop_index("ix_maintenance_issues_fingerprint", table_name="maintenance_issues")
    op.drop_table("maintenance_issues")
    op.drop_index("ix_approvals_subject_id", table_name="approvals")
    op.drop_column("approvals", "subject_id")
    op.drop_column("approvals", "subject_type")
