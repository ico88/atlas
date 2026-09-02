"""Local worker + scheduler (spec §7).

Consumes ``task_id`` values from the Redis queue and drives a task through its
lifecycle, writing a ``task_events`` row at every transition. On top of the
minimal QUEUED -> RUNNING -> COMPLETED flow it now enforces:

* concurrency limits (global / per-user / per-type),
* retries with exponential backoff + jitter (no infinite loops),
* a delayed queue promoted each loop (the scheduler base),
* DAG dependency release (dependents are queued when their deps complete).

The *dummy* executor also honours payload flags so tests can exercise failures:
``{"fail": true}`` always fails; ``{"succeed_after": N}`` fails until the Nth
retry, then succeeds.
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
from app.models.task import Task, TaskStatus
from app.services import concurrency, queue, task_service

logger = logging.getLogger("app.worker")

_shutdown = asyncio.Event()

_RUNNABLE = {TaskStatus.QUEUED.value, TaskStatus.RETRYING.value}


class _DummyFailure(RuntimeError):
    """Raised by the dummy executor to simulate a task failure."""


def _concurrency_limits() -> dict[str, int]:
    settings = get_settings()
    return {
        "global": settings.max_concurrent_global,
        "per_user": settings.max_concurrent_per_user,
        "per_type": settings.max_concurrent_per_type,
    }


async def _execute_dummy(task: Task) -> dict:
    """Simulated unit of work; honours failure flags for testing/retries."""

    settings = get_settings()
    await asyncio.sleep(settings.worker_dummy_duration)
    payload = task.payload or {}
    if payload.get("fail"):
        raise _DummyFailure("forced failure (payload.fail)")
    succeed_after = payload.get("succeed_after")
    if isinstance(succeed_after, int) and task.retries < succeed_after:
        raise _DummyFailure(f"transient failure (attempt {task.retries})")
    return {"echo": task.payload, "type": task.type, "worker": "local"}


async def _release_dependents(session, task_id: str) -> None:
    promoted = await task_service.ready_dependents(session, task_id)
    for dep in promoted:
        await queue.enqueue(dep.id)


async def process_task(task_id: str) -> None:
    """Execute a single task. Safe to call directly from tests."""

    set_task_id(task_id)
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as session:
        task = await task_service.get_task(session, task_id)
        if task is None:
            logger.warning("task not found", extra={"event": "worker_task_missing"})
            return

        if task.status not in _RUNNABLE:
            logger.info(
                "skipping task in non-runnable state",
                extra={"event": "worker_skip", "context": {"status": task.status}},
            )
            return

        # Reserve concurrency slots; if unavailable, requeue with a small delay.
        scopes = concurrency.build_scopes(
            owner_id=task.owner_id, task_type=task.type, limits=_concurrency_limits()
        )
        acquired = await concurrency.acquire(scopes)
        if acquired is None:
            await queue.enqueue_delayed(
                task_id, get_settings().concurrency_retry_delay
            )
            logger.info(
                "concurrency limit reached; requeued",
                extra={"event": "worker_deferred"},
            )
            return

        try:
            await task_service.mark_running(session, task)
            logger.info("task running", extra={"event": "worker_running"})
            try:
                result = await _execute_dummy(task)
            except Exception as exc:  # noqa: BLE001 - decide retry vs fail
                if task.retries < task.max_retries:
                    delay = await task_service.schedule_retry(session, task, str(exc))
                    await queue.enqueue_delayed(task_id, delay)
                    logger.info(
                        "task scheduled for retry",
                        extra={"event": "worker_retry", "context": {"delay": delay}},
                    )
                else:
                    await task_service.mark_failed(session, task, error=str(exc))
                    logger.warning("task failed", extra={"event": "worker_failed"})
                return

            await task_service.mark_completed(session, task, result=result)
            await _release_dependents(session, task.id)
            logger.info("task completed", extra={"event": "worker_completed"})
        finally:
            await concurrency.release(acquired)
            set_task_id(None)


async def run() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, service="worker")
    logger.info("worker started", extra={"event": "worker_startup"})

    while not _shutdown.is_set():
        set_request_id(None)
        set_task_id(None)
        try:
            # Scheduler step: move due delayed/retry tasks into the main queue.
            await queue.promote_due()
            task_id = await queue.dequeue(timeout=1)
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
