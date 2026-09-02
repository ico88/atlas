"""ATLAS backend application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import (
    approvals,
    auth,
    chat,
    maintenance,
    models,
    nodes,
    system,
    tasks,
)
from app.api.middleware import RequestContextMiddleware
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import get_sessionmaker
from app.services import user_service

logger = logging.getLogger(__name__)


async def _seed_admin() -> None:
    """Create the bootstrap admin user if configured and not present."""

    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        return
    async with get_sessionmaker()() as session:
        existing = await user_service.get_by_email(session, settings.admin_email)
        if existing is not None:
            return
        await user_service.create_user(
            session,
            email=settings.admin_email,
            password=settings.admin_password,
            full_name="Administrator",
            role="admin",
        )
        logger.info("bootstrap admin created", extra={"event": "admin_seeded"})


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level, service="backend")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:  # pragma: no cover - trivial
        logger.info(
            "backend started",
            extra={"event": "startup", "context": {"environment": settings.env}},
        )
        try:
            await _seed_admin()
        except Exception:  # noqa: BLE001 - never block startup on seeding
            logger.exception("admin seeding failed", extra={"event": "admin_seed_error"})
        yield
        logger.info("backend stopping", extra={"event": "shutdown"})

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="ATLAS control plane API (Sprint 1 bootstrap).",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(auth.router)
    app.include_router(system.router)
    app.include_router(tasks.router)
    app.include_router(nodes.router)
    app.include_router(chat.router)
    app.include_router(models.router)
    app.include_router(maintenance.router)
    app.include_router(approvals.router)

    return app


app = create_app()
