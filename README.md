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

## Quick start

Requires Docker + Docker Compose.

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

## Security

See [SECURITY.md](SECURITY.md). Highlights: only HTTPS is exposed, secrets never
touch Git, services run least-privilege, and critical actions require human
approval.

## License

Proprietary — private repository.
