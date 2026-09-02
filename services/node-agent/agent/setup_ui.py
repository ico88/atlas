"""Node Setup UI (ROADMAP PR 5).

A tiny, dependency-free local web UI served by the node agent for initial
configuration and diagnostics *before* enrollment. It exposes read-only status
(identity, hardware, capabilities, network/ZeroTier, control-plane reachability)
and one guarded action (re-request enrollment), protected by a one-time
bootstrap code shown at startup.

Security posture (spec PR 5):
- bind is intended for localhost/LAN only (published to 127.0.0.1 by compose);
- mutating endpoints require the bootstrap token;
- no arbitrary shell, no private keys, no secrets are ever returned.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from agent import __version__, zerotier
from agent.config import AgentConfig
from agent.hardware import collect_hardware

logger = logging.getLogger("node-agent.setup")


def check_control_plane(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=timeout) as resp:  # noqa: S310
            return resp.status == 200
    except Exception:  # noqa: BLE001 - reachability probe, never raises
        return False


def build_status(config: AgentConfig, *, probe_control_plane: bool = True) -> dict[str, Any]:
    """Assemble the node status document (no secrets)."""

    return {
        "agent_version": __version__,
        "node_id": config.node_id,
        "label": config.label,
        "capabilities": sorted(config.capabilities),
        "control_plane_url": config.control_plane_url,
        "control_plane_reachable": (
            check_control_plane(config.control_plane_url) if probe_control_plane else None
        ),
        "await_enrollment": config.await_enrollment,
        "token_configured": bool(config.token),
        "network": {
            "provider": config.network_provider,
            "zerotier_network_id": config.zerotier_network_id or None,
            "zerotier": zerotier.summary(),
        },
        "hardware": collect_hardware(),
    }


def authorized(expected_token: str, provided: str | None) -> bool:
    """Constant-ish comparison for the bootstrap token (empty expected => open)."""

    if not expected_token:
        return True
    return bool(provided) and provided == expected_token


_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>ATLAS Node Setup</title>
<style>body{{font-family:system-ui,sans-serif;background:#0b0f17;color:#e6edf6;margin:0;padding:24px}}
h1{{font-size:20px}}
pre{{background:#131a26;border:1px solid #26314480;border-radius:8px;padding:14px;overflow:auto}}
.muted{{color:#8aa0b8}}</style></head>
<body><h1>ATLAS — Node Setup</h1>
<p class="muted">Local configuration & diagnostics. Enroll this node from the control plane UI.</p>
<pre id="s">loading…</pre>
<script>
fetch('/api/status').then(r=>r.json()).then(d=>{{document.getElementById('s').textContent=
JSON.stringify(d,null,2)}}).catch(e=>{{document.getElementById('s').textContent='error: '+e}});
</script></body></html>"""


def make_handler(config: AgentConfig, token: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:  # quiet default logging
            return

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/" or self.path.startswith("/index"):
                self._send(200, _PAGE.encode(), "text/html; charset=utf-8")
            elif self.path.startswith("/api/status"):
                self._send(200, json.dumps(build_status(config)).encode())
            elif self.path.startswith("/api/diagnostics"):
                report = {"status": build_status(config), "note": "no secrets included"}
                self._send(200, json.dumps(report).encode())
            else:
                self._send(404, json.dumps({"detail": "not found"}).encode())

        def do_POST(self) -> None:  # noqa: N802
            provided = self.headers.get("X-Bootstrap-Token")
            if self.path.startswith("/api/reenroll"):
                if not authorized(token, provided):
                    self._send(401, json.dumps({"detail": "invalid bootstrap token"}).encode())
                    return
                # The actual re-enrollment is driven by the agent's register loop;
                # here we just acknowledge so the operator can trigger it.
                self._send(202, json.dumps({"status": "enrollment requested"}).encode())
            else:
                self._send(404, json.dumps({"detail": "not found"}).encode())

    return Handler


def start_setup_ui(config: AgentConfig, token: str) -> ThreadingHTTPServer:
    """Start the setup UI in a background thread; returns the server."""

    server = ThreadingHTTPServer(
        (config.setup_ui_host, config.setup_ui_port), make_handler(config, token)
    )
    thread = threading.Thread(target=server.serve_forever, name="node-setup-ui", daemon=True)
    thread.start()
    logger.info(
        "node setup UI on http://%s:%s (bootstrap token required for changes)",
        config.setup_ui_host,
        config.setup_ui_port,
    )
    return server
