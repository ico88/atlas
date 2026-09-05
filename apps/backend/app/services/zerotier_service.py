"""ZeroTier overlay controller (ROADMAP PR 7).

The overlay itself is set up by the node installer (join flow, PR 5). This service
is the optional **control-plane side**: when enabled, it talks to the ZeroTier
Central API to list a network's members and authorize/deauthorize them, so an
operator can admit nodes from the ATLAS UI. Every authorization change is audited.

OFF by default (local-first): with the controller disabled, `status()` simply
reports that, and no outbound call is ever made. Member shaping (`summarize_member`)
is pure and unit-tested; the API calls are exercised only when explicitly enabled.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ZeroTierError(RuntimeError):
    """Raised when the controller is misconfigured or the API call fails."""


def summarize_member(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape one ZeroTier Central member record into a compact, stable dict. Pure."""

    config = raw.get("config") or {}
    ips = config.get("ipAssignments") or raw.get("ipAssignments") or []
    return {
        "id": raw.get("nodeId") or raw.get("id"),
        "name": raw.get("name") or "",
        "authorized": bool(config.get("authorized", raw.get("authorized", False))),
        "online": bool(raw.get("online", False)),
        "ip_assignments": list(ips),
        "last_seen": raw.get("lastSeen") or raw.get("lastOnline"),
    }


def _client_config() -> tuple[str, str, str]:
    s = get_settings()
    if not s.zerotier_controller_enabled:
        raise ZeroTierError("ZeroTier controller is disabled (ATLAS_ZEROTIER_CONTROLLER_ENABLED)")
    if not s.zerotier_api_token or not s.zerotier_network_id:
        raise ZeroTierError("ZeroTier controller needs an API token and a network id")
    return s.zerotier_api.rstrip("/"), s.zerotier_api_token, s.zerotier_network_id


async def status() -> dict[str, Any]:
    """Controller status + (when enabled) a member summary. Never raises."""

    s = get_settings()
    out: dict[str, Any] = {
        "controller_enabled": s.zerotier_controller_enabled,
        "network_id": s.zerotier_network_id or None,
        "auto_authorize": s.zerotier_auto_authorize,
        "members": [],
        "member_count": 0,
        "authorized_count": 0,
        "error": None,
    }
    if not s.zerotier_controller_enabled:
        return out
    try:
        members = await list_members()
        out["members"] = members
        out["member_count"] = len(members)
        out["authorized_count"] = sum(1 for m in members if m["authorized"])
    except ZeroTierError as exc:
        out["error"] = str(exc)
    return out


async def _request(method: str, path: str, json: dict | None = None) -> Any:
    api, token, _ = _client_config()
    import httpx

    headers = {"Authorization": f"token {token}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.request(method, f"{api}{path}", headers=headers, json=json)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # noqa: BLE001 - surface a controlled error
        logger.warning("zerotier api call failed", extra={"event": "zt_api_error"})
        raise ZeroTierError(f"ZeroTier API {method} {path} failed: {exc}") from exc


async def list_members() -> list[dict[str, Any]]:
    _, _, network = _client_config()
    raw = await _request("GET", f"/network/{network}/member")
    items = raw if isinstance(raw, list) else raw.get("data", [])
    return [summarize_member(m) for m in items]


async def authorize_member(member_id: str, authorized: bool) -> dict[str, Any]:
    """Authorize/deauthorize a member on the network. Audited."""

    _, _, network = _client_config()
    raw = await _request(
        "POST",
        f"/network/{network}/member/{member_id}",
        json={"config": {"authorized": authorized}},
    )
    logger.info(
        "zerotier member authorization changed",
        extra={
            "event": "zt_authorize",
            "context": {"member": member_id, "authorized": authorized, "network": network},
        },
    )
    return summarize_member(raw)
