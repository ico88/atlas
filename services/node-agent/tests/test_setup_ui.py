"""Unit tests for the Node Setup UI (ROADMAP PR 5, no network)."""

from __future__ import annotations

from agent import setup_ui
from agent.config import AgentConfig


def _config(**over: object) -> AgentConfig:
    base = {
        "ATLAS_NODE_ID": "node-1",
        "ATLAS_NODE_LABEL": "gpu",
        "ATLAS_NODE_CAPABILITIES": "build,test",
        "ATLAS_NODE_TOKEN": "join-tok",
        "ATLAS_NETWORK_PROVIDER": "zerotier",
        "ATLAS_ZEROTIER_NETWORK_ID": "8056c2e21c000001",
    }
    base.update({k: str(v) for k, v in over.items()})
    return AgentConfig.from_env(base)  # type: ignore[arg-type]


def test_build_status_shape_and_no_secrets():
    status = setup_ui.build_status(_config(), probe_control_plane=False)
    assert status["node_id"] == "node-1"
    assert status["label"] == "gpu"
    assert status["capabilities"] == ["build", "test"]  # sorted
    assert status["control_plane_reachable"] is None  # probing disabled
    assert status["token_configured"] is True
    assert status["network"]["provider"] == "zerotier"
    assert status["network"]["zerotier_network_id"] == "8056c2e21c000001"
    assert "hardware" in status
    # The raw join token must never be leaked in the status document.
    assert "join-tok" not in str(status)


def test_authorized_requires_matching_token():
    assert setup_ui.authorized("code123", "code123") is True
    assert setup_ui.authorized("code123", "wrong") is False
    assert setup_ui.authorized("code123", None) is False


def test_authorized_open_when_no_token_expected():
    assert setup_ui.authorized("", None) is True
    assert setup_ui.authorized("", "anything") is True


def test_check_control_plane_false_on_unreachable():
    # An obviously dead endpoint must return False, never raise.
    assert setup_ui.check_control_plane("http://127.0.0.1:0", timeout=0.2) is False
