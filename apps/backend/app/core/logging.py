"""Structured JSON logging (spec §12).

Every record is emitted as a single JSON line carrying ``timestamp``, ``level``,
``service``, ``request_id`` and ``task_id`` so logs can be correlated across the
whole workflow. Secrets must never be logged: only pass structured, non-secret
values via the ``extra={"context": {...}}`` convention.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.context import get_request_id, get_task_id

# Attributes present on every stdlib LogRecord; anything else a caller attaches
# is treated as structured context and merged into the output.
_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Format log records as structured JSON lines."""

    def __init__(self, service: str = "backend") -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=UTC
            ).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", self.service),
            "logger": record.name,
            "request_id": get_request_id(),
            "task_id": get_task_id(),
            "event": getattr(record, "event", None),
            "message": record.getMessage(),
        }

        context = getattr(record, "context", None)
        if context:
            payload["context"] = context

        # Merge any additional non-reserved attributes (e.g. extra={"node_id": ...}).
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload and key != "context":
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO", service: str = "backend") -> None:
    """Install the JSON formatter on the root logger (idempotent)."""

    root = logging.getLogger()
    root.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service=service))

    root.handlers.clear()
    root.addHandler(handler)

    # Align uvicorn's loggers with our JSON handler.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
