"""HTTP client and payload builders for the control-plane node API."""

from __future__ import annotations

import contextlib
import socket

import httpx

from agent.config import AgentConfig


def build_register_payload(config: AgentConfig, hardware: dict[str, object]) -> dict[str, object]:
    hw = dict(hardware)
    if config.ollama_advertise_url:
        # Tell the control plane where to reach this node's Ollama, so the setup
        # UI can pre-fill the endpoint when attaching a model to the node.
        hw["ollama_url"] = config.ollama_advertise_url
    return {
        "node_id": config.node_id,
        "hostname": socket.gethostname(),
        "label": config.label,
        "version": config.version,
        "capabilities": config.capabilities,
        "hardware": hw,
    }


def build_heartbeat_payload(
    health: dict[str, object], ollama_url: str = ""
) -> dict[str, object]:
    h = dict(health)
    if ollama_url:
        h["ollama_url"] = ollama_url
    return {"status": "online", "health": h}


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

    async def claim_task(self, node_id: str) -> dict[str, object] | None:
        """Claim the next task matching this node's capabilities, or None."""

        resp = await self._client.post(f"/api/v1/nodes/{node_id}/claim-task")
        resp.raise_for_status()
        data = resp.json()
        return data if data else None

    async def report_result(
        self, task_id: str, payload: dict[str, object]
    ) -> dict[str, object]:
        resp = await self._client.post(f"/api/v1/tasks/{task_id}/result", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def report_progress(self, task_id: str, payload: dict[str, object]) -> None:
        """Advisory progress update while a task runs (best-effort, never raises)."""

        with contextlib.suppress(httpx.HTTPError, OSError):
            await self._client.post(f"/api/v1/tasks/{task_id}/progress", json=payload)

    async def aclose(self) -> None:
        await self._client.aclose()
