"""System Monitor: real host metrics, honest N/A (SPEC §11)."""

from __future__ import annotations

import pytest
from app.services import system_monitor_service as sm


# --------------------------------------------------------------------------- #
# Pure parsers
# --------------------------------------------------------------------------- #
def test_mem_stats():
    info = {"MemTotal": 1000, "MemAvailable": 250}
    m = sm.mem_stats(info)
    assert m["total"] == 1000 * 1024
    assert m["available"] == 250 * 1024
    assert m["used"] == 750 * 1024
    assert m["percent"] == 75.0
    # No MemTotal -> all None.
    assert sm.mem_stats({})["total"] is None


def test_swap_stats():
    assert sm.swap_stats({"SwapTotal": 100, "SwapFree": 100})["percent"] == 0.0
    assert sm.swap_stats({"SwapTotal": 200, "SwapFree": 50})["used"] == 150 * 1024
    assert sm.swap_stats({})["total"] is None  # N/A when no swap line


def test_parse_uptime_and_loadavg():
    assert sm.parse_uptime("12345.67 98765.43") == 12345.67
    assert sm.parse_uptime("garbage") is None
    assert sm.parse_loadavg("0.50 0.40 0.30 1/234 5678") == [0.5, 0.4, 0.3]
    assert sm.parse_loadavg("") is None


def test_cpu_percent_from_two_samples():
    # total grows by 100 jiffies, idle by 90 -> 10% busy.
    prev = "cpu  100 0 100 700 100 0 0 0 0 0"
    cur = "cpu  105 0 105 790 100 0 0 0 0 0"
    assert sm.cpu_percent(prev, cur) == 10.0
    # No movement -> None (can't divide).
    assert sm.cpu_percent(prev, prev) is None
    assert sm.cpu_percent("bogus", cur) is None


def test_parse_thermal():
    assert sm.parse_thermal("49000") == 49.0
    assert sm.parse_thermal("x") is None


# --------------------------------------------------------------------------- #
# Live snapshot + API
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_snapshot_shape():
    snap = await sm.snapshot("/")
    assert set(snap) == {
        "cpu",
        "memory",
        "swap",
        "storage",
        "uptime_seconds",
        "cpu_temperature",
        "gpu",
    }
    # Storage of "/" is always readable in the container.
    assert snap["storage"]["total"] and snap["storage"]["percent"] is not None
    assert isinstance(snap["gpu"], list)


@pytest.mark.asyncio
async def test_monitor_endpoint(client):
    body = (await client.get("/api/v1/system/monitor")).json()
    assert "cpu" in body and "memory" in body and "storage" in body
    assert body["storage"]["total"] is not None
