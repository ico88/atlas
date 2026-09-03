"""Integration tests for the web tools API (ROADMAP PR 15).

Hermetic: no real network. Web tools are disabled by default; when enabled (via
the runtime settings API) we use the offline Null search provider and rely on the
policy layer rejecting private targets *before* any DNS/socket use.
"""

from __future__ import annotations

import pytest


async def _enable(client, **over):
    body = {"enabled": True, "provider": "none"}
    body.update(over)
    resp = await client.put("/api/v1/settings/web", json=body)
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.asyncio
async def test_policy_endpoint_reports_disabled_by_default(client):
    resp = await client.get("/api/v1/web/policy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["provider"] == "none"
    assert body["allow_private_ips"] is False


@pytest.mark.asyncio
async def test_search_forbidden_when_disabled(client):
    resp = await client.post("/api/v1/web/search", json={"query": "hello"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_fetch_forbidden_when_disabled(client):
    resp = await client.post("/api/v1/web/fetch", json={"url": "https://example.com"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_search_returns_empty_with_null_provider(client):
    await _enable(client)
    resp = await client.post("/api/v1/web/search", json={"query": "anything"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "none"
    assert body["count"] == 0
    assert body["citations"] == []


@pytest.mark.asyncio
async def test_fetch_blocks_private_ip(client):
    await _enable(client)
    resp = await client.post(
        "/api/v1/web/fetch", json={"url": "http://169.254.169.254/latest/meta-data/"}
    )
    assert resp.status_code == 400
    assert "policy" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_fetch_rejects_non_http_scheme(client):
    await _enable(client)
    resp = await client.post("/api/v1/web/fetch", json={"url": "file:///etc/passwd"})
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# runtime settings config
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_web_config_roundtrip_and_secret_masking(client):
    # Default effective config is disabled.
    got = (await client.get("/api/v1/settings/web")).json()
    assert got["enabled"] is False
    assert got["has_api_key"] is False

    updated = await _enable(
        client,
        provider="searxng",
        url="http://searxng:8080/search",
        api_key="s3cr3t",
        allowlist=["example.com", "docs.python.org"],
    )
    assert updated["enabled"] is True
    assert updated["provider"] == "searxng"
    assert updated["allowlist"] == ["example.com", "docs.python.org"]
    # The API key is write-only: never returned, only its presence.
    assert "api_key" not in updated
    assert updated["has_api_key"] is True

    # The policy endpoint reflects the runtime config.
    policy = (await client.get("/api/v1/web/policy")).json()
    assert policy["enabled"] is True
    assert policy["allowlist"] == ["example.com", "docs.python.org"]


@pytest.mark.asyncio
async def test_web_config_partial_update_preserves_other_fields(client):
    await _enable(client, max_results=7)
    # A later patch that only flips allow_private_ips keeps enabled + max_results.
    resp = await client.put("/api/v1/settings/web", json={"allow_private_ips": True})
    body = resp.json()
    assert body["enabled"] is True
    assert body["max_results"] == 7
    assert body["allow_private_ips"] is True
