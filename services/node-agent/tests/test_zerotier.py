"""Unit tests for the ZeroTier output parsers (ROADMAP PR 5, no network)."""

from __future__ import annotations

from agent import zerotier

INFO = "200 info 1a2b3c4d5e 1.12.2 ONLINE\n"

LISTNETWORKS = """200 listnetworks <nwid> <name> <mac> <status> <type> <dev> <ZT assigned ips>
200 listnetworks 8056c2e21c000001 atlas-mesh 3a:1b:2c:3d:4e:5f OK PRIVATE ztabc123 10.147.20.5/24
200 listnetworks 8056c2e21c000002 - a1:b2:c3:d4:e5:f6 REQUESTING_CONFIGURATION PRIVATE ztdef456 -
"""


def test_parse_info_extracts_node_fields():
    info = zerotier.parse_info(INFO)
    assert info == {"node_id": "1a2b3c4d5e", "version": "1.12.2", "status": "ONLINE"}


def test_parse_info_empty_on_garbage():
    assert zerotier.parse_info("nonsense\n") == {}


def test_parse_networks_skips_header_and_reads_ips():
    nets = zerotier.parse_networks(LISTNETWORKS)
    assert len(nets) == 2
    first = nets[0]
    assert first["network_id"] == "8056c2e21c000001"
    assert first["name"] == "atlas-mesh"
    assert first["status"] == "OK"
    assert first["managed_ips"] == ["10.147.20.5/24"]


def test_parse_networks_no_ip_when_unassigned():
    nets = zerotier.parse_networks(LISTNETWORKS)
    second = nets[1]
    assert second["status"] == "REQUESTING_CONFIGURATION"
    assert second["managed_ips"] == []


def test_summary_unavailable_without_cli(monkeypatch):
    monkeypatch.setattr(zerotier.shutil, "which", lambda _name: None)
    summary = zerotier.summary()
    assert summary == {
        "available": False,
        "node_id": None,
        "status": None,
        "networks": [],
    }
