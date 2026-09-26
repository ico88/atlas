"""Secret manager: encrypted-at-rest secrets (ROADMAP R5).

Secrets are encrypted with Fernet (AES-128-CBC + HMAC). The master key comes from
``ATLAS_SECRET_KEY`` (a urlsafe-base64 32-byte Fernet key); if unset it is derived
deterministically from the JWT secret so the store works out of the box in dev and
in tests. Listing never exposes plaintext — only an admin ``get`` decrypts a value.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.secret import Secret

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    settings = get_settings()
    key = getattr(settings, "secret_key", "") or ""
    if key:
        return Fernet(key.encode() if isinstance(key, str) else key)
    # Derive a stable Fernet key from the JWT secret (dev/test convenience).
    digest = hashlib.sha256(settings.jwt_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")


async def set_secret(
    session: AsyncSession, *, name: str, value: str, description: str | None = None
) -> Secret:
    row = (
        await session.execute(select(Secret).where(Secret.name == name))
    ).scalar_one_or_none()
    if row is None:
        row = Secret(name=name)
        session.add(row)
    row.ciphertext = encrypt(value)
    if description is not None:
        row.description = description
    await session.commit()
    await session.refresh(row)
    logger.info("secret stored", extra={"event": "secret_set", "context": {"name": name}})
    return row


async def get_secret(session: AsyncSession, name: str) -> str | None:
    row = (
        await session.execute(select(Secret).where(Secret.name == name))
    ).scalar_one_or_none()
    if row is None:
        return None
    try:
        return decrypt(row.ciphertext)
    except InvalidToken:
        logger.error("secret decrypt failed (wrong master key?)", extra={"event": "secret_error"})
        return None


async def list_secrets(session: AsyncSession) -> list[Secret]:
    rows = await session.execute(select(Secret).order_by(Secret.name.asc()))
    return list(rows.scalars().all())


async def delete_secret(session: AsyncSession, name: str) -> bool:
    row = (
        await session.execute(select(Secret).where(Secret.name == name))
    ).scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True
