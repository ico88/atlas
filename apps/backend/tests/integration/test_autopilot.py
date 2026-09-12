"""Autopilot summary: read-only aggregation of autonomous activity."""

from __future__ import annotations

import pytest
from app.services import code_review_service, finetune_service, improvement_service


@pytest.mark.asyncio
async def test_autopilot_empty_shape(client):
    body = (await client.get("/api/v1/autopilot")).json()
    assert set(body) == {"automation", "pending", "counts", "actions", "activity"}
    # Automation flags are reported (defaults are on).
    assert body["automation"]["self_review"] is True
    assert body["activity"] == []
    assert body["actions"] == []
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


@pytest.mark.asyncio
async def test_autopilot_actions_expose_ids(client, session):
    from app.models.approval import Approval, ApprovalStatus
    from app.models.improvement import ProposalStatus

    # An approved proposal surfaces a "rollout" action carrying its id.
    approved = await improvement_service.create_proposal(
        session, title="Adopt A", candidate_model="a:1b"
    )
    approved.status = ProposalStatus.APPROVED.value
    # A second proposal with a PENDING approval surfaces a "decide" action.
    pend = await improvement_service.create_proposal(
        session, title="Adopt B", candidate_model="b:1b"
    )
    session.add(
        Approval(
            subject_type="improvement_proposal",
            subject_id=pend.id,
            action="adopt candidate",
            status=ApprovalStatus.PENDING.value,
        )
    )
    await session.commit()

    body = (await client.get("/api/v1/autopilot")).json()
    by_action = {a["action"]: a for a in body["actions"]}
    assert by_action["rollout"]["proposal_id"] == approved.id
    decide = by_action["decide"]
    assert decide["proposal_id"] == pend.id
    assert decide["approval_id"] and decide["title"] == "Adopt B"
