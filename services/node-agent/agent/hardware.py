"""Hardware and health collection (stdlib only, Linux-friendly).

All functions degrade gracefully on platforms where a source is unavailable, so
the agent runs anywhere for local development while giving rich data on Linux
worker hosts (spec §8).
"""

from __future__ import annotations

import os
import platform


def _read_meminfo() -> dict[str, int]:
    """Return selected /proc/meminfo values in kB (empty on non-Linux)."""

    values: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                parts = rest.split()
                if parts and parts[0].isdigit():
                    values[key.strip()] = int(parts[0])
    except OSError:
        pass
    return values


def collect_hardware() -> dict[str, object]:
    """Static-ish hardware inventory for registration."""

    mem = _read_meminfo()
    ram_mb = round(mem["MemTotal"] / 1024) if "MemTotal" in mem else None
    return {
        "platform": platform.system(),
        "release": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "cpu_cores": os.cpu_count(),
        "ram_mb": ram_mb,
    }


def collect_health() -> dict[str, object]:
    """Dynamic health snapshot for heartbeats."""

    health: dict[str, object] = {}

    try:
        load1, load5, load15 = os.getloadavg()
        health["load1"] = round(load1, 2)
        health["load5"] = round(load5, 2)
        health["load15"] = round(load15, 2)
    except (OSError, AttributeError):
        pass

    mem = _read_meminfo()
    if "MemAvailable" in mem:
        health["ram_free_mb"] = round(mem["MemAvailable"] / 1024)

    return health
