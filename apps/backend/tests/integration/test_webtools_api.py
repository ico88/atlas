"""Integration tests for the web tools API (ROADMAP PR 15).

Hermetic: no real network. Web tools are disabled by default; when enabled we
use the offline Null search provider and rely on the policy layer rejecting
private targets *before* any DNS/socket use.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings
from app.services import webtools_service


def _settings(**over: object) -> Settings:
    base = {"env": "test", "web_tools_enabled": True, "web_search_provider": "none"}
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


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
async def test_search_returns_empty_with_null_provider(client, monkeypatch):
    monkeypatch.setattr(webtools_service, "get_settings", lambda: _settings())
    resp = await client.post("/api/v1/web/search", json={"query": "anything"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "none"
    assert body["count"] == 0
    assert body["citations"] == []


@pytest.mark.asyncio
async def test_fetch_blocks_private_ip(client, monkeypatch):
    monkeypatch.setattr(webtools_service, "get_settings", lambda: _settings())
    resp = await client.post(
        "/api/v1/web/fetch", json={"url": "http://169.254.169.254/latest/meta-data/"}
    )
    assert resp.status_code == 400
    assert "policy" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_fetch_rejects_non_http_scheme(client, monkeypatch):
    monkeypatch.setattr(webtools_service, "get_settings", lambda: _settings())
    resp = await client.post("/api/v1/web/fetch", json={"url": "file:///etc/passwd"})
    assert resp.status_code == 400
