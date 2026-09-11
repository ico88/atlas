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

    async def fake_pull(url, model, timeout=1800.0, on_progress=None):
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


def test_pull_percent_pure():
    from agent.executor import pull_percent
    assert pull_percent({"completed": 50, "total": 100}) == 50
    assert pull_percent({"completed": 100, "total": 100}) == 100
    assert pull_percent({"status": "pulling"}) is None
    assert pull_percent({"completed": 5, "total": 0}) is None


def test_count_records_pure():
    from agent.executor import count_records
    assert count_records('{"a":1}\n{"b":2}\n\n  ') == 2
    assert count_records("") == 0


def test_simulated_metrics_loss_decreases_with_data():
    from agent.executor import simulated_metrics
    small = simulated_metrics(2, 3)["final_loss"]
    large = simulated_metrics(50, 3)["final_loss"]
    assert large < small


@pytest.mark.asyncio
async def test_fine_tune_simulate_completes_with_metrics():
    seen: list[int] = []

    async def cb(pct, status):
        seen.append(pct)

    result = await execute_task(
        {
            "id": "ft1",
            "type": "fine_tune",
            "payload": {
                "base_model": "llama3.2:3b",
                "adapter_name": "llama3.2-mine-ft",
                "training_data": '{"messages":[]}\n{"messages":[]}',
                "simulate": True,
                "hyperparams": {"epochs": 2},
            },
        },
        progress_cb=cb,
    )
    assert result["status"] == "completed"
    assert result["result"]["model"] == "llama3.2-mine-ft"
    assert result["result"]["metrics"]["examples"] == 2
    assert seen[-1] == 100


@pytest.mark.asyncio
async def test_fine_tune_without_backend_fails_honestly(monkeypatch):
    import agent.executor as ex

    monkeypatch.delenv("ATLAS_TRAIN_CMD", raising=False)
    monkeypatch.setattr(ex.shutil, "which", lambda _: None)
    result = await execute_task(
        {
            "id": "ft2",
            "type": "fine_tune",
            "payload": {
                "base_model": "m",
                "adapter_name": "a",
                "training_data": '{"messages":[]}',
            },
        }
    )
    assert result["status"] == "failed"
    assert "training backend" in result["error"]


@pytest.mark.asyncio
async def test_fine_tune_requires_fields():
    result = await execute_task(
        {"id": "ft3", "type": "fine_tune", "payload": {"training_data": "x"}}
    )
    assert result["status"] == "failed"
    assert "required" in result["error"]


@pytest.mark.asyncio
async def test_pull_model_reports_progress(monkeypatch):
    seen: list[int] = []

    async def cb(pct, status):
        seen.append(pct)

    # Simulate an Ollama pull stream via a fake httpx client.
    import agent.executor as ex

    class _Resp:
        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            for c in (
                '{"status":"pulling","completed":10,"total":100}',
                '{"status":"pulling","completed":60,"total":100}',
                '{"status":"success"}',
            ):
                yield c

    class _Stream:
        async def __aenter__(self):
            return _Resp()

        async def __aexit__(self, *a):
            return False

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, *a, **k):
            return _Stream()

    monkeypatch.setattr(ex.httpx, "AsyncClient", lambda *a, **k: _Client())
    result = await ex.pull_model("http://x:11434", "m", on_progress=cb)
    assert result["status"] == "completed"
    assert 10 in seen and 60 in seen and seen[-1] == 100  # final 100 reported
