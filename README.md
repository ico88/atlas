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
| POST | `/api/v1/auth/login` | Email + password → JWT access token |
| GET | `/api/v1/auth/me` | Current user (Bearer token) |
| POST | `/api/v1/chat/stream` | Streaming chat reply (SSE), persists history |
| GET | `/api/v1/conversations` | List conversations |
| GET | `/api/v1/conversations/{id}` | Conversation with messages |
| GET | `/api/v1/models` | Model registry |
| POST | `/api/v1/models/refresh` | Discover models from providers |
| GET | `/api/v1/system/hardware` | Host hardware scan |
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

## ALMA orchestrator (M5)

ALMA turns a high-level objective into a plan and runs it (spec §6, §7). Create a
task of type `alma`; the orchestrator:

1. **decomposes** the objective into a DAG of subtasks (a default
   Analyze → Execute → Summarize plan, or an explicit `payload.plan`),
2. runs the subtasks through the M3 task engine — independent ones in parallel,
   each with its own retry/backoff,
3. **aggregates** the subtask results into the parent when they all complete,
   and **fails** the parent if a subtask fails.

```bash
curl -s -XPOST http://localhost/api/v1/tasks -H 'Content-Type: application/json' \
  -d '{"title":"Prepare release notes","type":"alma"}'
# then inspect the plan:
curl -s http://localhost/api/v1/tasks/<alma_id>/subtasks
```

The **Tasks** page in the UI submits objectives to ALMA and shows the subtask
DAG live.

## Task engine (M3)

Tasks are persistent and drive a state machine (spec §7). The worker also acts as
a base **scheduler**:

- **Concurrency limits** — global / per-user / per-type, enforced via Redis
  counters; over-limit tasks are requeued with a short delay
  (`ATLAS_MAX_CONCURRENT_*`).
- **Retries** — exponential backoff **+ jitter**, capped by `max_retries` (no
  infinite loops). Failed attempts move to `RETRYING` on a delayed queue.
- **Delayed queue / scheduler** — a Redis sorted set of not-yet-ready tasks,
  promoted into the work queue each loop.
- **Dependencies (DAG-ready)** — a task with `depends_on` starts in
  `WAITING_DEPENDENCY` and is queued automatically once every dependency
  completes. This is the foundation ALMA (M5) builds on.
- **Idempotency** — repeating a create with the same `idempotency_key` returns
  the existing task instead of duplicating it.

```bash
# A task that depends on another; it runs only after the parent completes
curl -s -XPOST http://localhost/api/v1/tasks -H 'Content-Type: application/json' \
  -d '{"title":"child","depends_on":["<parent_task_id>"]}'
```

## Local AI (M2)

Chat is **provider-agnostic** (spec §9). The AI Router prefers **local** Ollama
inference and falls back to a built-in **echo** provider when no model is
reachable — so chat, streaming and history work out of the box, even without a
GPU or any model pulled.

```bash
# Start the stack with local LLM support and pull a model
docker compose --profile ai up --build -d
docker compose exec ollama ollama pull llama3.2
```

Then open the **Chat** page. Replies stream token-by-token (Server-Sent Events);
every turn is persisted (**cronologia**) and listed in the sidebar. The
**Models** page shows the registry and a host hardware scan (CPU/RAM/GPU) used to
inform local model selection.

> External/manual modes (ChatGPT/Claude) and cloud APIs are later milestones
> (M7/M9). Set `ATLAS_OLLAMA_URL=` (empty) to force the echo provider.

## Authentication (M1)

JWT-based auth (bcrypt password hashing, `HS256` tokens). Set `ATLAS_JWT_SECRET`
in `.env` (`openssl rand -hex 32`) and optionally a bootstrap admin
(`ATLAS_ADMIN_EMAIL` / `ATLAS_ADMIN_PASSWORD`), which is created on first
startup.

```bash
# Log in and call an authenticated endpoint
TOKEN=$(curl -s -XPOST http://localhost/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"change-me-admin-password"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -s http://localhost/api/v1/auth/me -H "Authorization: Bearer $TOKEN"
```

> Note: email addresses must use a real domain format — reserved TLDs such as
> `.local` are rejected. In this milestone the read endpoints remain public so
> the UI works without a login screen; route-level enforcement is applied
> incrementally in later milestones.

## Security

See [SECURITY.md](SECURITY.md). Highlights: only HTTPS is exposed, secrets never
touch Git, services run least-privilege, and critical actions require human
approval.

## License

Proprietary — private repository.
