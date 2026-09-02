"""Unit tests for the node executor (M4 remote execution)."""

from __future__ import annotations

import pytest
from agent.executor import execute_task


@pytest.mark.asyncio
async def test_execute_completed():
    result = await execute_task(
        {"id": "t1", "required_capability": "build", "payload": {"x": 1}}, work_seconds=0
    )
    assert result["status"] == "completed"
    assert result["result"]["capability"] == "build"
    assert result["result"]["echo"] == {"x": 1}


@pytest.mark.asyncio
async def test_execute_failure_flag():
    result = await execute_task({"id": "t2", "payload": {"fail": True}}, work_seconds=0)
    assert result["status"] == "failed"
    assert "error" in result
