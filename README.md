# ATLAS — Adaptive Task & LLM Array System

> **ALMA** — Autonomous Layer for Multi-Agent orchestration

ATLAS is a **local-first, distributed, multi-agent, human-governed** AI platform.
This repository contains the **Sprint 1 bootstrap**: a working, testable
foundation on which the full platform is built milestone by milestone.

> ⚠️ Sprint 1 scope is intentionally minimal. LLM inference (Ollama), RAG,
> distributed nodes, the maintenance auto-fix agent and cloud providers are
> **not** implemented yet — see the [implementation plan](docs/IMPLEMENTATION_PLAN.md).

## Architecture (Sprint 1)

```
                 Browser
                    │
                    ▼
             Caddy reverse proxy         ← only public entry point (HTTP/HTTPS)
              ├── /            → frontend (Next.js)
              └── /api, /health → backend (FastAPI)
                    │
        ┌───────────┼─────────────┐
        ▼           ▼             ▼
   PostgreSQL     Redis        Worker
   (state,       (task queue,  (consumes tasks:
    audit)        cache)        QUEUED→RUNNING→COMPLETED)
```

Everything except Caddy stays on an internal network (spec §13).

## Repository layout

| Path | Contents |
|------|----------|
| `apps/backend` | FastAPI control plane, models, migrations, worker, tests |
| `apps/frontend` | Next.js + TypeScript UI (sidebar shell, System Status) |
| `services/` | Placeholders for future domain services (spec §6) |
| `packages/` | Shared schemas / prompts / utilities (future) |
| `infrastructure/` | Caddy, Postgres, LiteLLM, scripts |
| `docs/` | Specification-derived documentation |
| `.github/workflows` | CI (lint, typecheck, tests, Docker build, secret scan) |

## Prerequisites

- **Host OS:** Ubuntu Server **24.04 LTS** (spec §4). The reference target;
  other Debian-based hosts may work but are untested.
- **Docker Engine + Docker Compose plugin**, `git`, `make`, `curl`.

Container base images are Debian-slim / Alpine by design (smaller, reduced
attack surface); they run on the Ubuntu host regardless — the host OS and the
container base images do not need to match.

### Automated install (Ubuntu)

An idempotent, **role-aware** installer sets up all prerequisites and prepares
`.env`. It asks whether this host is the **control plane** (manager, runs the
full stack) or a **node** (worker, runs only the node agent):

```bash
sudo ./infrastructure/scripts/install.sh   # or: make install  (interactive)
# then, if you were just added to the docker group:
newgrp docker
```

Non-interactive examples:

```bash
# Manager (control plane) — generates a node join token into .env
sudo ./infrastructure/scripts/install.sh --role control-plane --yes

# Worker node — points at the manager and joins with the shared token
sudo ./infrastructure/scripts/install.sh --role node \
     --manager-url http://<manager-host>:80 --token <JOIN_TOKEN> \
     --capabilities llm,build --label gpu-1 --yes
```

See [Multi-node federation](#multi-node-federation-m4) below for the full flow.

## Quick start

Once the prerequisites are installed:

```bash
cp .env.example .env      # or: make env
docker compose up --build # or: make up
```

Then open:

- **App / System Status:** http://localhost/system
- **Backend health:** http://localhost/health
- **API:** http://localhost/api/v1/system/status

### Create and observe a task

```bash
# Create a dummy task
curl -s -XPOST http://localhost/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title":"hello","payload":{"n":1}}'

# Poll it — it moves QUEUED → RUNNING → COMPLETED as the worker processes it
curl -s http://localhost/api/v1/tasks/<task_id>
curl -s http://localhost/api/v1/tasks/<task_id>/events
```

Tasks and their events are persisted in PostgreSQL and **survive a backend
restart**.

## Development

```bash
# Backend (hermetic tests: SQLite + fakeredis, no services needed)
cd apps/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
ruff check app tests
mypy app

# Frontend
cd apps/frontend
npm install
npm run typecheck
npm run lint
npm run build
```

The `Makefile` wraps the common commands (`make help`).

## Environment variables

See [`.env.example`](.env.example). All backend settings use the `ATLAS_`
prefix. **No secret is ever committed** — `.env` is git-ignored.

| Variable | Purpose |
|----------|---------|
| `ATLAS_ENV` | `development` / `production` / `test` |
| `ATLAS_LOG_LEVEL` | Log verbosity |
| `ATLAS_DATABASE_URL` | Async SQLAlchemy DSN (asyncpg) |
| `ATLAS_REDIS_URL` | Redis connection URL |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Postgres credentials |
| `ATLAS_SITE_ADDRESS` | Caddy site address (`:80` dev, domain for auto-HTTPS) |

## API (Sprint 1 subset)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/api/v1/system/status` | Backend / DB / Redis health |
| GET | `/api/v1/system/metrics` | Task counts, nodes online, pending approvals |
| POST | `/api/v1/tasks` | Create a task (enqueued for the worker) |
| GET | `/api/v1/tasks` | List tasks |
| GET | `/api/v1/tasks/{id}` | Get a task |
| POST | `/api/v1/tasks/{id}/cancel` | Logically cancel a task |
| GET | `/api/v1/tasks/{id}/events` | Task event history |
| GET | `/api/v1/nodes` | List registered nodes (with online status) |
| GET | `/api/v1/nodes/{id}` | Get a node (by db id or logical `node_id`) |
| POST | `/api/v1/nodes/register` | Register/upsert a node (node token) |
| POST | `/api/v1/nodes/{id}/heartbeat` | Node heartbeat (node token) |

## Multi-node federation (M4)

ATLAS is distributed by design. One host runs the **control plane** (manager);
additional hosts run a lightweight **node agent** that registers and sends
heartbeats. Nodes appear live on the **Nodes** page and in `GET /api/v1/nodes`.

```
   Manager (control plane)                 Worker node(s)
   full stack + REST API      <── register/heartbeat ──   node-agent
   ATLAS_NODE_JOIN_TOKEN                                  ATLAS_NODE_TOKEN
```

**On the manager:** set `ATLAS_NODE_JOIN_TOKEN` in `.env` (the installer can
generate one), then `docker compose up -d`.

**On each worker node** (a second machine):

```bash
# 1) install prerequisites + write node config (interactive role picker)
sudo ./infrastructure/scripts/install.sh --role node \
     --manager-url http://<manager-host>:80 --token <JOIN_TOKEN> \
     --capabilities llm,build --label gpu-1 --yes

# 2) start the node agent
docker compose -f docker-compose.node.yml up --build -d
```

The manager and nodes typically communicate over an encrypted overlay network
(Tailscale / ZeroTier, spec §3) — use the manager's overlay address as
`--manager-url`. Authentication uses the shared join token (least privilege,
§13); rotate it by changing `ATLAS_NODE_JOIN_TOKEN` on the manager.

> Scope note: this is the **minimal** M4 slice — registration, heartbeat and
> liveness. Capability-based scheduling and remote task execution on nodes come
> in later M4 work.

## Security

See [SECURITY.md](SECURITY.md). Highlights: only HTTPS is exposed, secrets never
touch Git, services run least-privilege, and critical actions require human
approval.

## License

Proprietary — private repository.
