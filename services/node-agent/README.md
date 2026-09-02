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
