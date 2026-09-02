"""HTTP client and payload builders for the control-plane node API."""

from __future__ import annotations

import socket

import httpx

from agent.config import AgentConfig


def build_register_payload(config: AgentConfig, hardware: dict[str, object]) -> dict[str, object]:
    return {
        "node_id": config.node_id,
        "hostname": socket.gethostname(),
        "label": config.label,
        "version": config.version,
        "capabilities": config.capabilities,
        "hardware": hardware,
    }


def build_heartbeat_payload(health: dict[str, object]) -> dict[str, object]:
    return {"status": "online", "health": health}


class ControlPlaneClient:
    """Thin async wrapper over the control-plane node endpoints."""

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        headers = {}
        if config.token:
            headers["X-Node-Token"] = config.token
        self._client = httpx.AsyncClient(
            base_url=config.control_plane_url,
            headers=headers,
            timeout=config.request_timeout,
        )

    async def register(self, payload: dict[str, object]) -> dict[str, object]:
        resp = await self._client.post("/api/v1/nodes/register", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def heartbeat(self, node_id: str, payload: dict[str, object]) -> dict[str, object]:
        resp = await self._client.post(f"/api/v1/nodes/{node_id}/heartbeat", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._client.aclose()
