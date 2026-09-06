"""Node Agent configuration (read from environment variables).

Kept dependency-free (plain ``os.environ``) so the agent stays lightweight.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field


def _parse_capabilities(raw: str) -> dict[str, bool]:
    """Parse a comma-separated capability list into a mapping.

    Example: ``"llm,build,test"`` -> ``{"llm": True, "build": True, "test": True}``.
    """

    return {c.strip(): True for c in raw.split(",") if c.strip()}


@dataclass
class AgentConfig:
    control_plane_url: str = "http://localhost:8000"
    node_id: str = field(default_factory=socket.gethostname)
    label: str | None = None
    version: str | None = None
    token: str = ""
    capabilities: dict[str, bool] = field(default_factory=dict)
    heartbeat_interval: float = 15.0
    poll_interval: float = 3.0  # how often to poll for claimable tasks
    register_max_retries: int = 0  # 0 = retry forever
    request_timeout: float = 10.0
    # Node Setup UI (ROADMAP PR 5) — local status/diagnostics before enrollment.
    setup_ui_enabled: bool = True
    setup_ui_host: str = "0.0.0.0"  # published to 127.0.0.1 on the host by compose
    setup_ui_port: int = 8971
    bootstrap_token: str = ""  # generated at startup if empty
    network_provider: str = "none"  # none | zerotier | existing
    zerotier_network_id: str = ""
    await_enrollment: bool = False
    # Local Ollama the agent drives (e.g. for control-plane-triggered model pulls).
    ollama_url: str = "http://localhost:11434"
    # URL the control plane should use to reach THIS node's Ollama (overlay IP).
    # Reported to the control plane so the setup UI can pre-fill the endpoint.
    ollama_advertise_url: str = ""

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> AgentConfig:
        env = environ if environ is not None else dict(os.environ)
        hostname = socket.gethostname()

        def _bool(key: str, default: str = "false") -> bool:
            return env.get(key, default).strip().lower() in ("1", "true", "yes", "on")

        return cls(
            control_plane_url=env.get("ATLAS_CONTROL_PLANE_URL", "http://localhost:8000").rstrip(
                "/"
            ),
            node_id=env.get("ATLAS_NODE_ID") or hostname,
            label=env.get("ATLAS_NODE_LABEL") or None,
            version=env.get("ATLAS_NODE_VERSION") or None,
            token=env.get("ATLAS_NODE_TOKEN", ""),
            capabilities=_parse_capabilities(env.get("ATLAS_NODE_CAPABILITIES", "")),
            heartbeat_interval=float(env.get("ATLAS_NODE_HEARTBEAT_INTERVAL", "15")),
            poll_interval=float(env.get("ATLAS_NODE_POLL_INTERVAL", "3")),
            register_max_retries=int(env.get("ATLAS_NODE_REGISTER_MAX_RETRIES", "0")),
            request_timeout=float(env.get("ATLAS_NODE_REQUEST_TIMEOUT", "10")),
            setup_ui_enabled=_bool("ATLAS_NODE_SETUP_UI", "true"),
            setup_ui_host=env.get("ATLAS_NODE_SETUP_UI_HOST", "0.0.0.0"),
            setup_ui_port=int(env.get("ATLAS_NODE_SETUP_UI_PORT", "8971")),
            bootstrap_token=env.get("ATLAS_NODE_BOOTSTRAP_TOKEN", ""),
            network_provider=env.get("ATLAS_NETWORK_PROVIDER", "none"),
            zerotier_network_id=env.get("ATLAS_ZEROTIER_NETWORK_ID", ""),
            await_enrollment=_bool("ATLAS_NODE_AWAIT_ENROLLMENT", "false"),
            ollama_url=env.get("ATLAS_OLLAMA_URL", "http://localhost:11434").rstrip("/"),
            ollama_advertise_url=env.get("ATLAS_NODE_OLLAMA_ADVERTISE_URL", "").rstrip("/"),
        )
