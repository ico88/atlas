"""Unit tests for the node agent (no network)."""

from __future__ import annotations

from agent.client import build_heartbeat_payload, build_register_payload
from agent.config import AgentConfig
from agent.hardware import collect_hardware


def test_config_parses_capabilities_from_env():
    config = AgentConfig.from_env(
        {
            "ATLAS_CONTROL_PLANE_URL": "http://cp:8000/",
            "ATLAS_NODE_ID": "node-x",
            "ATLAS_NODE_CAPABILITIES": "llm, build ,test",
            "ATLAS_NODE_HEARTBEAT_INTERVAL": "5",
            "ATLAS_NODE_TOKEN": "tok",
        }
    )
    assert config.control_plane_url == "http://cp:8000"  # trailing slash stripped
    assert config.node_id == "node-x"
    assert config.capabilities == {"llm": True, "build": True, "test": True}
    assert config.heartbeat_interval == 5.0
    assert config.token == "tok"


def test_config_defaults_node_id_to_hostname():
    config = AgentConfig.from_env({})
    assert config.node_id  # non-empty (the hostname)
    assert config.capabilities == {}


def test_build_register_payload_shape():
    config = AgentConfig.from_env({"ATLAS_NODE_ID": "n1", "ATLAS_NODE_LABEL": "gpu"})
    payload = build_register_payload(config, {"cpu_cores": 4})
    assert payload["node_id"] == "n1"
    assert payload["label"] == "gpu"
    assert payload["hardware"] == {"cpu_cores": 4}
    assert "hostname" in payload


def test_build_heartbeat_payload():
    payload = build_heartbeat_payload({"load1": 0.5})
    assert payload["status"] == "online"
    assert payload["health"] == {"load1": 0.5}


def test_collect_hardware_has_core_fields():
    hw = collect_hardware()
    assert "cpu_cores" in hw
    assert "platform" in hw
    assert "arch" in hw
