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
    register_max_retries: int = 0  # 0 = retry forever
    request_timeout: float = 10.0

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> AgentConfig:
        env = environ if environ is not None else dict(os.environ)
        hostname = socket.gethostname()
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
            register_max_retries=int(env.get("ATLAS_NODE_REGISTER_MAX_RETRIES", "0")),
            request_timeout=float(env.get("ATLAS_NODE_REQUEST_TIMEOUT", "10")),
        )
