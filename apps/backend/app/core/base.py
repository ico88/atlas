"""Small id helpers used outside the ORM layer."""

from __future__ import annotations

from uuid import uuid4


def gen_request_id() -> str:
    return uuid4().hex
