"""Integration tests for manual escalation (M7, spec §10)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_prepare_package_has_all_sections(client):
    resp = await client.post(
        "/api/v1/escalations",
        json={
            "objective": "Fix the ollama timeout",
            "target": "claude",
            "context": {"logs": "ollama_timeout after 30s", "hypothesis": "increase timeout"},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "PREPARED"
    assert body["target"] == "claude"
    pkg = body["package"]
    for section in (
        "EXTERNAL ESCALATION PACKAGE",
        "Correlation ID:",
        "Target: Claude Pro",
        "## Task objective",
        "## Logs / stack trace",
        "## Expected output format",
        "## Request for patch / analysis",
    ):
        assert section in pkg
    assert "ollama_timeout after 30s" in pkg


@pytest.mark.asyncio
async def test_import_response_is_untrusted_then_validated(client):
    esc = (
        await client.post("/api/v1/escalations", json={"objective": "do a thing"})
    ).json()

    imported = await client.post(
        "/api/v1/external-response/import",
        json={"escalation_id": esc["id"], "response": "Here is a patch:\n```diff\n@@\n+fix\n```"},
    )
    assert imported.status_code == 200
    body = imported.json()
    assert body["status"] == "RESPONSE_IMPORTED"
    # Imported responses are untrusted until a human validates them.
    assert body["validation"]["trusted"] is False
    assert body["validation"]["auto_checks"]["contains_diff"] is True

    validated = await client.post(
        f"/api/v1/escalations/{esc['id']}/validate",
        json={"approved": True, "notes": "looks safe", "decided_by": "alice"},
    )
    assert validated.json()["status"] == "VALIDATED"
    assert validated.json()["validation"]["trusted"] is True


@pytest.mark.asyncio
async def test_reject_response(client):
    esc = (await client.post("/api/v1/escalations", json={"objective": "x"})).json()
    await client.post(
        "/api/v1/external-response/import",
        json={"escalation_id": esc["id"], "response": "nonsense"},
    )
    rejected = await client.post(
        f"/api/v1/escalations/{esc['id']}/validate", json={"approved": False}
    )
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["validation"]["trusted"] is False


@pytest.mark.asyncio
async def test_secret_in_response_is_flagged(client):
    esc = (await client.post("/api/v1/escalations", json={"objective": "x"})).json()
    imported = await client.post(
        "/api/v1/external-response/import",
        json={"escalation_id": esc["id"], "response": "set API_KEY=abc and password=123"},
    )
    assert imported.json()["validation"]["auto_checks"]["mentions_secret"] is True


@pytest.mark.asyncio
async def test_prepare_external_from_issue(client):
    issue = (
        await client.post(
            "/api/v1/maintenance/logs",
            json={"message": "db connection refused", "service": "backend", "level": "ERROR"},
        )
    ).json()
    resp = await client.post(f"/api/v1/maintenance/issues/{issue['id']}/prepare-external")
    assert resp.status_code == 200
    body = resp.json()
    assert body["subject_type"] == "maintenance_issue"
    assert body["subject_id"] == issue["id"]
    assert "db connection refused" in body["package"]

    listing = await client.get("/api/v1/escalations")
    assert listing.json()["total"] == 1


@pytest.mark.asyncio
async def test_import_unknown_escalation_404(client):
    resp = await client.post(
        "/api/v1/external-response/import",
        json={"escalation_id": "nope", "response": "x"},
    )
    assert resp.status_code == 404
