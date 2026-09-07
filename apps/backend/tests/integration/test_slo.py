"""Service-level objectives + alerts (ROADMAP R5)."""

from __future__ import annotations

import pytest
from app.services import slo_service


def test_evaluate_all_ok():
    r = slo_service.evaluate(
        completed=99, failed=1, nodes_total=10, nodes_online=10, healthy=True,
        task_target=0.95, nodes_target=0.9,
    )
    assert r["ok"] is True
    assert r["alerts"] == []
    names = {s["name"] for s in r["slos"]}
    assert {"task_success_rate", "nodes_online_ratio", "control_plane_healthy"} <= names


def test_evaluate_flags_breaches():
    r = slo_service.evaluate(
        completed=50, failed=50, nodes_total=10, nodes_online=1, healthy=False,
        task_target=0.95, nodes_target=0.9,
    )
    assert r["ok"] is False
    breached = {a["slo"] for a in r["alerts"]}
    assert breached == {"task_success_rate", "nodes_online_ratio", "control_plane_healthy"}


def test_evaluate_skips_task_slo_without_data():
    r = slo_service.evaluate(
        completed=0, failed=0, nodes_total=0, nodes_online=0, healthy=True,
        task_target=0.95, nodes_target=0.9,
    )
    names = {s["name"] for s in r["slos"]}
    # No finished tasks and no nodes -> only the health SLO is present, and OK.
    assert names == {"control_plane_healthy"}
    assert r["ok"] is True


@pytest.mark.asyncio
async def test_slo_api(client):
    r = await client.get("/api/v1/slo")
    assert r.status_code == 200
    body = r.json()
    assert "slos" in body and "alerts" in body and "generated_at" in body
    assert any(s["name"] == "control_plane_healthy" for s in body["slos"])
