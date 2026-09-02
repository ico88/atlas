"""Minimal local worker (spec §17.8).

Consumes ``task_id`` values from the Redis queue and drives a *dummy* task
through the lifecycle QUEUED -> RUNNING -> COMPLETED, writing a ``task_events``
row at every transition. This is intentionally the simplest thing that proves
the concurrency/queue design end to end; real executors are added in later
milestones (M3+).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from app.core.config import get_settings
from app.core.context import set_request_id, set_task_id
from app.core.logging import configure_logging
from app.db import get_sessionmaker
from app.models.task import TaskStatus
from app.services import queue, task_service

logger = logging.getLogger("app.worker")

_shutdown = asyncio.Event()


async def process_task(task_id: str) -> None:
    """Execute a single task. Safe to call directly from tests."""

    set_task_id(task_id)
    sessionmaker = get_sessionmaker()
    settings = get_settings()

    async with sessionmaker() as session:
        task = await task_service.get_task(session, task_id)
        if task is None:
            logger.warning(
                "task not found", extra={"event": "worker_task_missing"}
            )
            return

        # Respect cancellation / non-queued states (idempotent processing).
        if task.status != TaskStatus.QUEUED.value:
            logger.info(
                "skipping task in non-queued state",
                extra={"event": "worker_skip", "context": {"status": task.status}},
            )
            return

        await task_service.mark_running(session, task)
        logger.info("task running", extra={"event": "worker_running"})

        try:
            # Simulated unit of work for the dummy task type.
            await asyncio.sleep(settings.worker_dummy_duration)
            result = {"echo": task.payload, "type": task.type, "worker": "local"}
            await task_service.mark_completed(session, task, result=result)
            logger.info("task completed", extra={"event": "worker_completed"})
        except Exception as exc:  # noqa: BLE001 - record failure, keep loop alive
            await task_service.mark_failed(session, task, error=str(exc))
            logger.exception("task failed", extra={"event": "worker_failed"})
        finally:
            set_task_id(None)


async def run() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, service="worker")
    logger.info("worker started", extra={"event": "worker_startup"})

    while not _shutdown.is_set():
        set_request_id(None)
        set_task_id(None)
        try:
            task_id = await queue.dequeue()
        except Exception:  # noqa: BLE001 - transient Redis error, back off and retry
            logger.exception("dequeue failed", extra={"event": "worker_dequeue_error"})
            await asyncio.sleep(1)
            continue

        if task_id is None:
            continue  # poll timeout, loop again
        await process_task(task_id)

    logger.info("worker stopped", extra={"event": "worker_shutdown"})


def _install_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # pragma: no cover - e.g. Windows
            loop.add_signal_handler(sig, _shutdown.set)


def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _install_signal_handlers(loop)
    try:
        loop.run_until_complete(run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
