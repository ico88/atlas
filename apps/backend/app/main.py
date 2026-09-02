"""ATLAS backend application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import system, tasks
from app.api.middleware import RequestContextMiddleware
from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level, service="backend")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:  # pragma: no cover - trivial
        logger.info(
            "backend started",
            extra={"event": "startup", "context": {"environment": settings.env}},
        )
        yield
        logger.info("backend stopping", extra={"event": "shutdown"})

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="ATLAS control plane API (Sprint 1 bootstrap).",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(system.router)
    app.include_router(tasks.router)

    return app


app = create_app()
