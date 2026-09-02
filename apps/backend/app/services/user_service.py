"""User creation and authentication (spec §14: users)."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User

logger = logging.getLogger(__name__)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def count_users(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(User))).scalar_one())


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str | None = None,
    role: str = "user",
) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info(
        "user created",
        extra={"event": "user_created", "context": {"email": email, "role": role}},
    )
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    user = await get_by_email(session, email)
    if user is None or not user.hashed_password or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
