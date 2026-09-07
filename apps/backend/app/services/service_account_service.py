"""Service-account tokens (ROADMAP R5).

A token is ``atlas_sa_<random>``; only its SHA-256 hash and a short prefix are
stored. Verification looks up by prefix, compares the hash in constant time, and
updates ``last_used_at``. Tokens can be scoped by role and revoked.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.service_account import ServiceAccount

logger = logging.getLogger(__name__)

_PREFIX = "atlas_sa_"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create(
    session: AsyncSession, *, name: str, role: str = "user"
) -> tuple[ServiceAccount, str]:
    """Create a service account. Returns the row and the plaintext token (once)."""

    token = _PREFIX + secrets.token_urlsafe(32)
    account = ServiceAccount(
        name=name,
        token_prefix=token[: len(_PREFIX) + 6],
        token_hash=_hash(token),
        role=role,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    logger.info(
        "service account created",
        extra={"event": "sa_create", "context": {"name": name, "role": role}},
    )
    return account, token


async def verify(session: AsyncSession, token: str) -> ServiceAccount | None:
    """Return the active account for a token, or None. Updates last_used_at."""

    if not token or not token.startswith(_PREFIX):
        return None
    prefix = token[: len(_PREFIX) + 6]
    candidates = (
        await session.execute(
            select(ServiceAccount).where(
                ServiceAccount.token_prefix == prefix, ServiceAccount.active.is_(True)
            )
        )
    ).scalars().all()
    digest = _hash(token)
    for account in candidates:
        if hmac.compare_digest(account.token_hash, digest):
            account.last_used_at = utcnow()
            await session.commit()
            return account
    return None


async def list_accounts(session: AsyncSession) -> list[ServiceAccount]:
    rows = await session.execute(select(ServiceAccount).order_by(ServiceAccount.name.asc()))
    return list(rows.scalars().all())


async def revoke(session: AsyncSession, account_id: str) -> bool:
    account = await session.get(ServiceAccount, account_id)
    if account is None:
        return False
    account.active = False
    await session.commit()
    return True
