"""Fleet compliance (ROADMAP PR 24): inventory, desired state, drift.

The desired fleet state (target version, required capabilities, minimum online
count) is stored as an operator setting. `compute_drift` is a pure function that
compares the live inventory against it and reports per-node issues plus a
fleet-level compliance summary — so the dashboard and auto-remediation share one
source of truth.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import node_service, settings_service

FLEET_KEY = "fleet_desired"

_DEFAULT_DESIRED: dict[str, Any] = {
    "target_version": "",
    "required_capabilities": [],
    "min_online": 0,
}


async def get_desired(session: AsyncSession) -> dict[str, Any]:
    stored = await settings_service.get_overrides(FLEET_KEY, session)
    return {**_DEFAULT_DESIRED, **stored}


async def set_desired(session: AsyncSession, patch: dict[str, Any]) -> dict[str, Any]:
    clean = {k: v for k, v in patch.items() if k in _DEFAULT_DESIRED}
    await settings_service.set_overrides(FLEET_KEY, clean, session)
    return await get_desired(session)


def compute_drift(nodes: list[dict], desired: dict[str, Any]) -> dict[str, Any]:
    """Compare the inventory against the desired state. Pure/testable.

    ``nodes`` items: {ref, online, version, capabilities: [...], quarantined}.
    """

    target = (desired.get("target_version") or "").strip()
    required = [c for c in (desired.get("required_capabilities") or []) if c]
    min_online = int(desired.get("min_online") or 0)

    node_reports: list[dict[str, Any]] = []
    online = compliant = quarantined = 0

    for n in nodes:
        issues: list[str] = []
        caps = list(n.get("capabilities") or [])
        is_online = bool(n.get("online"))
        is_quar = bool(n.get("quarantined"))
        if is_online:
            online += 1
        if is_quar:
            quarantined += 1
            issues.append("quarantined")
        if not is_online:
            issues.append("offline")
        if target and n.get("version") and n["version"] != target:
            issues.append(f"version {n['version']} != {target}")
        if target and not n.get("version"):
            issues.append("version unknown")
        missing = [c for c in required if c not in caps]
        if missing:
            issues.append("missing capability: " + ", ".join(missing))

        node_compliant = is_online and not is_quar and not issues
        if node_compliant:
            compliant += 1
        node_reports.append(
            {
                "node_ref": n.get("ref"),
                "online": is_online,
                "quarantined": is_quar,
                "version": n.get("version"),
                "compliant": node_compliant,
                "issues": issues,
            }
        )

    total = len(nodes)
    summary = {
        "total": total,
        "online": online,
        "quarantined": quarantined,
        "compliant": compliant,
        "drifted": sum(
            1 for r in node_reports if r["online"] and not r["quarantined"] and not r["compliant"]
        ),
        "compliance_pct": round(compliant / total, 4) if total else 1.0,
        "min_online": min_online,
        "meets_min_online": online >= min_online,
    }
    return {"summary": summary, "nodes": node_reports}


async def fleet_report(session: AsyncSession) -> dict[str, Any]:
    """Live compliance report: desired state + drift over the current inventory."""

    desired = await get_desired(session)
    nodes = await node_service.list_nodes(session)
    infos = [
        {
            "ref": n.node_id,
            "online": node_service.is_online(n),
            "version": n.version,
            "capabilities": node_service.node_capabilities(n),
            "quarantined": bool(getattr(n, "quarantined", False)),
        }
        for n in nodes
    ]
    report = compute_drift(infos, desired)
    report["desired"] = desired
    return report
