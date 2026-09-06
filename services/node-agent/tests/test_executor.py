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


@pytest.mark.asyncio
async def test_model_pull_requires_model():
    result = await execute_task({"id": "t3", "type": "model_pull", "payload": {}}, work_seconds=0)
    assert result["status"] == "failed"
    assert "model" in result["error"]


@pytest.mark.asyncio
async def test_model_pull_calls_ollama(monkeypatch):
    calls = {}

    async def fake_pull(url, model, timeout=1800.0):
        calls["url"] = url
        calls["model"] = model
        return {"status": "completed", "result": {"pulled": model}}

    monkeypatch.setattr("agent.executor.pull_model", fake_pull)
    result = await execute_task(
        {"id": "t4", "type": "model_pull", "payload": {"model": "qwen2.5:3b"}},
        ollama_url="http://localhost:11434",
    )
    assert result["status"] == "completed"
    assert calls["model"] == "qwen2.5:3b"
    assert calls["url"] == "http://localhost:11434"
