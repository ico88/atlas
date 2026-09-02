"""Unit tests for model-level invariants."""

from __future__ import annotations

from app.models import Base
from app.models.task import TaskStatus


def test_task_status_terminal_set():
    assert TaskStatus.COMPLETED.is_terminal
    assert TaskStatus.FAILED.is_terminal
    assert TaskStatus.CANCELLED.is_terminal
    assert not TaskStatus.QUEUED.is_terminal
    assert not TaskStatus.RUNNING.is_terminal


def test_all_spec_tables_registered():
    expected = {"users", "tasks", "task_events", "nodes", "approvals"}
    assert expected <= set(Base.metadata.tables)
