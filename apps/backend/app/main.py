"""ATLAS backend application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import (
    attachments,
    chat,
    conversation_queue,
    escalation,
    maintenance,
    service_accounts,
    tasks,
    webtools,
)
from app.api import (
    eval as eval_api,
)
from app.domains.config import api as config_api
from app.domains.governance import api as governance_api
from app.domains.runtime import api as runtime_api
from app.domains.improvement import api as improvement_api
from app.domains.knowledge import api as knowledge_api
from app.domains.infrastructure import api as infrastructure_api
from app.domains.observability import api as observability_api
from app.api.middleware import RequestContextMiddleware
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import get_sessionmaker
from app.services import chat_service, query_service, user_service

logger = logging.getLogger(__name__)

# Strong refs so the HA background loop is not garbage-collected.
_HA_TASKS: set[object] = set()


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
        try:
            # Re-queue queries left RUNNING by a previous (crashed) backend.
            await query_service.recover_and_resume()
        except Exception:  # noqa: BLE001 - never block startup on recovery
            logger.exception("query recovery failed", extra={"event": "query_recover_error"})
        try:
            # Fail chat replies left mid-generation by a crash (no stuck spinner).
            await chat_service.recover_pending_replies()
        except Exception:  # noqa: BLE001 - never block startup on recovery
            logger.exception("chat recovery failed", extra={"event": "chat_recover_error"})
        try:
            # Fully autonomous improvement proposer (no-op unless enabled).
            from app.services import automation_service

            automation_service.start_autonomous_proposer()
            # Code self-review on ATLAS's own source (propose-only, human-gated).
            automation_service.start_self_review()
        except Exception:  # noqa: BLE001 - never block startup on the proposer
            logger.exception("proposer start failed", extra={"event": "auto_propose_start_err"})
        try:
            # HA: register this instance and run leader election (no-op single-node).
            if settings.ha_enabled:
                import asyncio

                from app.services import leadership_service

                async def _ha_loop() -> None:
                    ttl = get_settings().ha_lease_ttl
                    while True:
                        try:
                            await leadership_service.register_instance()
                            await leadership_service.try_acquire_leadership(ttl)
                        except Exception:  # noqa: BLE001 - never kill the loop
                            logger.warning("ha loop error", extra={"event": "ha_loop_err"})
                        await asyncio.sleep(max(5, ttl // 2))

                _ha_task = asyncio.create_task(_ha_loop())
                _HA_TASKS.add(_ha_task)
                _ha_task.add_done_callback(_HA_TASKS.discard)
        except Exception:  # noqa: BLE001 - never block startup on HA
            logger.exception("ha start failed", extra={"event": "ha_start_err"})
        yield
        logger.info("backend stopping", extra={"event": "shutdown"})

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="ATLAS control plane API (Sprint 1 bootstrap).",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(tasks.router)
    app.include_router(chat.router)
    app.include_router(maintenance.router)
    app.include_router(escalation.router)
    app.include_router(webtools.router)
    app.include_router(conversation_queue.router)
    app.include_router(config_api.router)
    app.include_router(governance_api.router)
    app.include_router(runtime_api.router)
    app.include_router(improvement_api.router)
    app.include_router(knowledge_api.router)
    app.include_router(infrastructure_api.router)
    app.include_router(observability_api.router)
    app.include_router(eval_api.router)
    app.include_router(attachments.router)
    app.include_router(service_accounts.router)

    return app


app = create_app()
