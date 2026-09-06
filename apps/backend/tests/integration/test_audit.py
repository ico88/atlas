"""Append-only, tamper-evident audit trail (ROADMAP R5)."""

from __future__ import annotations

import pytest
from app.models.audit import AuditLog
from app.services import audit_service
from sqlalchemy import select


@pytest.mark.asyncio
async def test_chain_links_and_verifies(session):
    a = await audit_service.record(session, action="model.activate", target="m1")
    b = await audit_service.record(session, action="node.attach", target="n1")
    assert a.seq == 1 and b.seq == 2
    assert a.prev_hash == audit_service.GENESIS
    assert b.prev_hash == a.hash  # chained
    result = await audit_service.verify_chain(session)
    assert result == {"ok": True, "count": 2}


@pytest.mark.asyncio
async def test_tampering_is_detected(session):
    await audit_service.record(session, action="a", target="1")
    await audit_service.record(session, action="b", target="2")
    await audit_service.record(session, action="c", target="3")

    # Tamper with the second entry's detail without recomputing the hash.
    row = (
        await session.execute(select(AuditLog).where(AuditLog.seq == 2))
    ).scalar_one()
    row.target = "HACKED"
    await session.commit()

    result = await audit_service.verify_chain(session)
    assert result["ok"] is False
    assert result["broken_at"] == 2


@pytest.mark.asyncio
async def test_audit_api_lists_and_verifies(client, session):
    await audit_service.record(session, action="model.activate", target="qwen", actor="alice")

    r = await client.get("/api/v1/audit")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["action"] == "model.activate"
    assert body["items"][0]["actor"] == "alice"

    v = await client.get("/api/v1/audit/verify")
    assert v.status_code == 200
    assert v.json()["ok"] is True


@pytest.mark.asyncio
async def test_activate_model_writes_audit(client, session):
    await client.post("/api/v1/setup/activate", json={"model": "qwen2.5:3b"})
    entries = await audit_service.list_entries(session)
    actions = {e.action for e in entries}
    assert "model.activate" in actions
