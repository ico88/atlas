"""ZeroTier helpers for the node (ROADMAP PR 5).

Pure parsers for ``zerotier-cli`` output (unit-testable) plus tolerant wrappers
that run the CLI when available. ZeroTier is normally installed and managed on
the HOST by the installer; the agent uses these only to *read* status when it can
reach the CLI. Never raises: a missing CLI yields an "unavailable" summary.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any


def parse_info(text: str) -> dict[str, str]:
    """Parse ``zerotier-cli info`` -> {node_id, version, status}.

    Example line: ``200 info 1a2b3c4d5e 1.12.2 ONLINE``
    """

    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1] == "info":
            return {"node_id": parts[2], "version": parts[3], "status": parts[4]}
    return {}


def parse_networks(text: str) -> list[dict[str, Any]]:
    """Parse ``zerotier-cli listnetworks`` into a list of networks.

    Line: ``200 listnetworks <nwid> <name> <mac> <status> <type> <dev> <ips>``
    The header row (where the nwid column literally reads ``<nwid>``) is skipped.
    """

    networks: list[dict[str, Any]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[1] != "listnetworks":
            continue
        nwid = parts[2]
        if nwid == "<nwid>":  # header row
            continue
        name = parts[3]
        status = parts[5] if len(parts) > 5 else "UNKNOWN"
        ips_field = parts[-1] if len(parts) >= 9 else "-"
        managed_ips = [ip for ip in ips_field.split(",") if ip and ip != "-"]
        networks.append(
            {"network_id": nwid, "name": name, "status": status, "managed_ips": managed_ips}
        )
    return networks


def _run(args: list[str], timeout: float = 5.0) -> str | None:
    exe = shutil.which("zerotier-cli")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return proc.stdout or ""


def available() -> bool:
    return shutil.which("zerotier-cli") is not None


def summary() -> dict[str, Any]:
    """Best-effort ZeroTier status for the setup UI (never raises)."""

    if not available():
        return {"available": False, "node_id": None, "status": None, "networks": []}
    info = parse_info(_run(["info"]) or "")
    networks = parse_networks(_run(["listnetworks"]) or "")
    return {
        "available": True,
        "node_id": info.get("node_id"),
        "version": info.get("version"),
        "status": info.get("status"),
        "networks": networks,
    }
