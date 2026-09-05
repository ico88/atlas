"""ZeroTier controller (ROADMAP PR 7)."""

from __future__ import annotations

import pytest
from app.services.zerotier_service import ZeroTierError, summarize_member


def test_summarize_member_pure():
    raw = {
        "nodeId": "abcdef1234",
        "name": "worker-1",
        "online": True,
        "config": {"authorized": True, "ipAssignments": ["10.147.0.5"]},
        "lastSeen": 123,
    }
    m = summarize_member(raw)
    assert m["id"] == "abcdef1234"
    assert m["authorized"] is True and m["online"] is True
    assert m["ip_assignments"] == ["10.147.0.5"]


def test_summarize_member_defaults():
    m = summarize_member({"nodeId": "x"})
    assert m["authorized"] is False and m["online"] is False and m["ip_assignments"] == []


@pytest.mark.asyncio
async def test_status_reports_disabled(client):
    body = (await client.get("/api/v1/zerotier/status")).json()
    assert body["controller_enabled"] is False
    assert body["members"] == []


@pytest.mark.asyncio
async def test_members_conflict_when_disabled(client):
    resp = await client.get("/api/v1/zerotier/members")
    assert resp.status_code == 409  # controller disabled


@pytest.mark.asyncio
async def test_authorize_raises_when_disabled():
    from app.services import zerotier_service

    with pytest.raises(ZeroTierError):
        await zerotier_service.authorize_member("abcdef1234", True)
