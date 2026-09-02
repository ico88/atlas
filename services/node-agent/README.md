# ATLAS Node Agent

Registers a worker node with the control plane and sends periodic heartbeats
(spec §8, milestone **M4**). Lightweight: standard library for hardware/health
collection, `httpx` for HTTP.

## Configuration (environment variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `ATLAS_CONTROL_PLANE_URL` | `http://localhost:8000` | Control-plane base URL (e.g. the manager's overlay IP) |
| `ATLAS_NODE_TOKEN` | *(empty)* | Join token; must match the control plane's `ATLAS_NODE_JOIN_TOKEN` |
| `ATLAS_NODE_ID` | hostname | Stable logical node id |
| `ATLAS_NODE_LABEL` | *(none)* | Human-friendly label |
| `ATLAS_NODE_VERSION` | *(none)* | Agent/node version string |
| `ATLAS_NODE_CAPABILITIES` | *(empty)* | Comma list, e.g. `llm,embeddings,build,test` |
| `ATLAS_NODE_HEARTBEAT_INTERVAL` | `15` | Seconds between heartbeats |
| `ATLAS_NODE_POLL_INTERVAL` | `3` | Seconds between polls for claimable tasks |
| `ATLAS_NODE_SETUP_UI` | `true` | Enable the local Setup UI (status & diagnostics) |
| `ATLAS_NODE_SETUP_UI_PORT` | `8971` | Setup UI port (published to `127.0.0.1` only) |
| `ATLAS_NODE_BOOTSTRAP_TOKEN` | *(generated)* | One-time code guarding the Setup UI's mutating actions |
| `ATLAS_NETWORK_PROVIDER` | `none` | Overlay network: `none`, `zerotier` or `existing` |
| `ATLAS_ZEROTIER_NETWORK_ID` | *(empty)* | ZeroTier network id (16 hex chars) |
| `ATLAS_NODE_AWAIT_ENROLLMENT` | `false` | Report "awaiting enrollment" until approved by the control plane |

## Node Setup UI (ROADMAP PR 5)

A tiny, dependency-free local web page the agent serves for **pre-enrollment
setup and diagnostics**. It shows this node's identity, capabilities, hardware,
overlay-network/ZeroTier status and whether the control plane is reachable — and
nothing secret (the join token is never returned). It binds to loopback:

```
http://127.0.0.1:8971/            # the page
GET  /api/status                  # JSON status
GET  /api/diagnostics             # JSON status + note
POST /api/reenroll                # guarded: needs header X-Bootstrap-Token
```

The one-time **bootstrap code** for guarded actions is printed in the agent log
at startup. If the node is remote, tunnel the UI over SSH:

```bash
ssh -L 8971:127.0.0.1:8971 user@<node-host>
```

### ZeroTier overlay (optional)

The installer (`--network-provider zerotier --zerotier-network-id <16-hex>`)
installs ZeroTier on the **host**, joins the network, and prints the node's
ZeroTier id and managed IP. Authorize the member in ZeroTier Central for a
private network, then point `ATLAS_CONTROL_PLANE_URL` at the manager's overlay
IP. The agent only *reads* ZeroTier status for the Setup UI; it never manages it.

## Run

```bash
# Directly
pip install -r requirements.txt
ATLAS_CONTROL_PLANE_URL=http://<manager>:80 \
ATLAS_NODE_TOKEN=<token> \
ATLAS_NODE_CAPABILITIES=llm,build \
python -m agent

# Or via Docker Compose (from the repo root, on the node host)
docker compose -f docker-compose.node.yml up --build -d
```

The agent registers on startup, then loops: it sends heartbeats and **claims
tasks** whose `required_capability` matches this node's capabilities, executes
them and **reports the result** back to the control plane. If the control plane
forgets the node (404 on heartbeat), it re-registers automatically. The node
appears in the UI **Nodes** page and in `GET /api/v1/nodes`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
ruff check agent tests
```
