"""Correlation context shared across a workflow.

``request_id`` and ``task_id`` are stored in :mod:`contextvars` so they can be
attached to every log record without threading them through every function call.
The same ``request_id`` follows a request across middleware, services and (via
the task record) into the worker as ``task_id`` -- this is the single
correlation id required by the spec (§12).
"""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
task_id_var: ContextVar[str | None] = ContextVar("task_id", default=None)


def set_request_id(value: str | None) -> None:
    request_id_var.set(value)


def set_task_id(value: str | None) -> None:
    task_id_var.set(value)


def get_request_id() -> str | None:
    return request_id_var.get()


def get_task_id() -> str | None:
    return task_id_var.get()
