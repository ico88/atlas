"""Autopilot summary: read-only aggregation of autonomous activity."""

from __future__ import annotations

import pytest
from app.services import code_review_service, finetune_service, improvement_service


@pytest.mark.asyncio
async def test_autopilot_empty_shape(client):
    body = (await client.get("/api/v1/autopilot")).json()
    assert set(body) == {"automation", "pending", "counts", "activity"}
    # Automation flags are reported (defaults are on).
    assert body["automation"]["self_review"] is True
    assert body["activity"] == []
    assert body["counts"]["proposals"] == 0


@pytest.mark.asyncio
async def test_autopilot_reflects_activity(client, session, tmp_path, monkeypatch):
    # A model proposal (autonomous-style) shows up in the feed.
    await improvement_service.create_proposal(
        session, title="Adopt fast-model", candidate_model="fast:1b"
    )

    # A self-review finding shows up as a self-review activity item.
    src = tmp_path / "apps" / "backend" / "app"
    src.mkdir(parents=True)
    (src / "m.py").write_text("x = 1  # FIXME: later\n", encoding="utf-8")
    monkeypatch.setattr(code_review_service, "_run_ruff", _no_ruff)
    await code_review_service.run_self_review(session, tmp_path)

    # A fine-tune job shows up too.
    ds = await finetune_service.create_dataset(session, name="d", base_model="m")
    await finetune_service.add_example(session, dataset_id=ds.id, prompt="p", response="r")

    body = (await client.get("/api/v1/autopilot")).json()
    kinds = {a["kind"] for a in body["activity"]}
    assert "proposal" in kinds
    assert "self-review" in kinds
    assert body["counts"]["self_review_issues"] >= 1
    assert body["pending"]["open_issues"] >= 1


async def _no_ruff(_root):
    return []
