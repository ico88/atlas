# Sprint 1 — Bootstrap

This sprint delivers a **working, testable foundation** only (spec §17–19). It
does **not** implement the whole product.

## Delivered (spec §18 mandatory output)

1. ✅ Monorepo structure (§5).
2. ✅ Docker Compose (`docker-compose.yml` + `docker-compose.dev.yml`) for
   frontend, backend, worker, PostgreSQL, Redis and Caddy.
3. ✅ FastAPI backend with `/health` and `/api/v1/system/status`
   (plus `/api/v1/system/metrics`).
4. ✅ SQLAlchemy models + Alembic migration for `users`, `tasks`,
   `task_events`, `nodes`, `approvals`.
5. ✅ Next.js + TypeScript shell branded ATLAS with a sidebar and a
   **System Status** page.
6. ✅ JSON structured logging with `request_id` / `task_id` correlation (§12).
7. ✅ Task CRUD API and a minimal local worker consuming a dummy task
   (`QUEUED → RUNNING → COMPLETED`).
8. ✅ Unit + integration tests (hermetic: SQLite + fakeredis).
9. ✅ GitHub Actions CI: lint, type-check, tests, migration-on-Postgres,
   Docker build and secret scan.
10. ✅ `README.md`, `.env.example`, `SECURITY.md`, `Makefile`.

## Explicitly deferred (§17.12)

- LLM inference (Ollama), RAG, Git auto-fix, cloud provider APIs.

## Acceptance criteria (spec §19)

| Criterion | How it is met |
|-----------|---------------|
| `docker compose up` starts services without critical errors | Compose file with healthchecks + ordered `depends_on` |
| Frontend reachable; System Status shows backend/database/Redis | `/system` page polls `/api/v1/system/status` |
| `GET /health` returns healthy | `app/api/system.py` |
| Create a dummy task and observe QUEUED → RUNNING → COMPLETED | Task API + local worker; verified in `tests/integration/test_worker.py` |
| Tasks and events survive a backend restart | Persisted in PostgreSQL; every transition writes a `task_events` row |
| CI passes on a development branch | `.github/workflows/ci.yml` |
| No secret is present in the repository | `.env` git-ignored; secret-scan job in CI |

## Design notes

- **IDs** are stored as `CHAR(36)` string UUIDs for portability across
  PostgreSQL (production) and SQLite (hermetic tests).
- **Correlation:** `request_id` is generated/propagated per HTTP request and the
  worker sets `task_id`; both are attached to every JSON log line.
- **Queue:** a simple Redis list (`RPUSH`/`BLPOP`, FIFO) — enough to prove the
  concurrency model; a richer priority/stream queue arrives in M3+.
- **State transitions** always go through `task_service`, which records an event,
  so the audit trail is complete and restart-safe.
