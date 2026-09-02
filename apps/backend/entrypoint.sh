#!/usr/bin/env bash
# Container entrypoint. Usage: entrypoint.sh [api|worker]
set -euo pipefail

ROLE="${1:-api}"

case "$ROLE" in
  api)
    echo "Running database migrations..."
    alembic upgrade head
    echo "Starting API server..."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    echo "Starting worker..."
    exec python -m app.worker.worker
    ;;
  *)
    echo "Unknown role: $ROLE (expected 'api' or 'worker')" >&2
    exit 1
    ;;
esac
