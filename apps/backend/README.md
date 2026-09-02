# ATLAS Backend

FastAPI control-plane API for ATLAS (Sprint 1 bootstrap).

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Run migrations (needs a reachable PostgreSQL, see docker-compose)
alembic upgrade head

# Serve
uvicorn app.main:app --reload --port 8000

# Worker (separate process)
python -m app.worker.worker
```

## Tests

The suite is hermetic (SQLite + fakeredis) so it needs no running services:

```bash
pytest
ruff check .
mypy app
```

Configuration is read from `ATLAS_`-prefixed environment variables
(see `app/core/config.py`).
