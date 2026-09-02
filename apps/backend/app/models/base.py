"""Declarative base and shared column helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def new_uuid() -> str:
    """Generate a string UUID.

    IDs are stored as ``CHAR(36)`` for portability across PostgreSQL (production)
    and SQLite (hermetic tests).
    """

    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


def pk_column():
    return mapped_column(String(36), primary_key=True, default=new_uuid)
