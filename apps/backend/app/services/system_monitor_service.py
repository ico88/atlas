"""Real host metrics for the ATLAS Control System Monitor (SPEC §11).

Reads the Linux host through ``/proc`` and ``/sys`` (plus the existing GPU scan),
never a third-party dependency and **never a simulated value** — a metric that
cannot be read is reported as ``None`` so the UI can show ``N/A`` (spec §11, §33).

The parsing helpers are pure and unit-tested; :func:`snapshot` does the I/O.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from app.core.hardware import _read_meminfo, scan_gpus

logger = logging.getLogger(__name__)


# --- pure parsers -----------------------------------------------------------


def _kib_to_bytes(kib: int) -> int:
    return kib * 1024


def mem_stats(meminfo: dict[str, int]) -> dict[str, Any]:
    """RAM total/used/available/percent from /proc/meminfo (values in KiB)."""

    total = meminfo.get("MemTotal")
    available = meminfo.get("MemAvailable")
    if not total:
        return {"total": None, "used": None, "available": None, "percent": None}
    avail = available if available is not None else meminfo.get("MemFree", 0)
    used = max(0, total - avail)
    return {
        "total": _kib_to_bytes(total),
        "used": _kib_to_bytes(used),
        "available": _kib_to_bytes(avail),
        "percent": round(used / total * 100, 1) if total else None,
    }


def swap_stats(meminfo: dict[str, int]) -> dict[str, Any]:
    total = meminfo.get("SwapTotal")
    if total is None:
        return {"total": None, "used": None, "percent": None}
    free = meminfo.get("SwapFree", 0)
    used = max(0, total - free)
    return {
        "total": _kib_to_bytes(total),
        "used": _kib_to_bytes(used),
        "percent": round(used / total * 100, 1) if total else 0.0,
    }


def parse_uptime(text: str) -> float | None:
    try:
        return float(text.split()[0])
    except (ValueError, IndexError):
        return None


def parse_loadavg(text: str) -> list[float] | None:
    parts = text.split()
    try:
        return [float(parts[0]), float(parts[1]), float(parts[2])]
    except (ValueError, IndexError):
        return None


def _cpu_totals(stat_line: str) -> tuple[int, int] | None:
    """From a /proc/stat 'cpu ...' line -> (idle, total) jiffies."""

    parts = stat_line.split()
    if not parts or parts[0] != "cpu":
        return None
    try:
        nums = [int(x) for x in parts[1:]]
    except ValueError:
        return None
    if len(nums) < 5:
        return None
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)  # idle + iowait
    return idle, sum(nums)


def cpu_percent(prev_cpu_line: str, cur_cpu_line: str) -> float | None:
    """Busy percentage between two /proc/stat 'cpu' samples."""

    prev = _cpu_totals(prev_cpu_line)
    cur = _cpu_totals(cur_cpu_line)
    if prev is None or cur is None:
        return None
    idle_d = cur[0] - prev[0]
    total_d = cur[1] - prev[1]
    if total_d <= 0:
        return None
    return round((1 - idle_d / total_d) * 100, 1)


def parse_thermal(millideg: str) -> float | None:
    try:
        return round(int(millideg.strip()) / 1000, 1)
    except ValueError:
        return None


# --- I/O snapshot -----------------------------------------------------------


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def _first_cpu_line(stat: str | None) -> str:
    if not stat:
        return ""
    return stat.splitlines()[0] if stat.splitlines() else ""


def _cpu_temp() -> float | None:
    base = Path("/sys/class/thermal")
    if not base.is_dir():
        return None
    temps: list[float] = []
    try:
        for zone in base.glob("thermal_zone*"):
            raw = _read(str(zone / "temp"))
            if raw:
                v = parse_thermal(raw)
                if v is not None:
                    temps.append(v)
    except OSError:
        return None
    return max(temps) if temps else None


def _gpu() -> list[dict[str, Any]]:
    try:
        devices, _rocm = scan_gpus()
    except Exception:  # noqa: BLE001 - GPU probing is best-effort
        return []
    out: list[dict[str, Any]] = []
    for d in devices:
        out.append(
            {
                "name": getattr(d, "name", None),
                "vendor": getattr(d, "vendor", None),
                "vram_total": getattr(d, "vram_mb", None),
                "temperature": getattr(d, "temperature_c", None),
                "utilization": getattr(d, "utilization", None),
            }
        )
    return out


async def snapshot(storage_path: str = "/") -> dict[str, Any]:
    """One real reading of the host. Missing metrics come back as None (N/A)."""

    stat1 = _read("/proc/stat")
    await asyncio.sleep(0.1)  # short delta for a real CPU% sample
    stat2 = _read("/proc/stat")
    cpu = cpu_percent(_first_cpu_line(stat1), _first_cpu_line(stat2))

    meminfo = {}
    try:
        meminfo = _read_meminfo()
    except Exception:  # noqa: BLE001 - meminfo unavailable -> N/A
        meminfo = {}

    load = parse_loadavg(_read("/proc/loadavg") or "")
    uptime = parse_uptime(_read("/proc/uptime") or "")

    disk: dict[str, Any]
    try:
        du = shutil.disk_usage(storage_path)
        disk = {
            "path": storage_path,
            "total": du.total,
            "used": du.used,
            "free": du.free,
            "percent": round(du.used / du.total * 100, 1) if du.total else None,
        }
    except OSError:
        disk = {"path": storage_path, "total": None, "used": None, "free": None, "percent": None}

    return {
        "cpu": {"percent": cpu, "cores": os.cpu_count(), "load_average": load},
        "memory": mem_stats(meminfo),
        "swap": swap_stats(meminfo),
        "storage": disk,
        "uptime_seconds": uptime,
        "cpu_temperature": _cpu_temp(),
        "gpu": _gpu(),
    }
