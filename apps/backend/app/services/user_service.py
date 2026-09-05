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


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at.asc()))
    return list(result.scalars().all())


async def get_user(session: AsyncSession, user_id: str) -> User | None:
    return await session.get(User, user_id)


async def count_active_admins(session: AsyncSession) -> int:
    stmt = (
        select(func.count())
        .select_from(User)
        .where(User.role == "admin", User.is_active.is_(True))
    )
    return int((await session.execute(stmt)).scalar_one())


class LastAdminError(RuntimeError):
    """Raised when an action would remove the last active administrator."""


async def update_user(
    session: AsyncSession,
    user: User,
    *,
    role: str | None = None,
    is_active: bool | None = None,
) -> User:
    """Update a user's role / active flag, refusing to strip the last admin."""

    demoting = role is not None and role != "admin" and user.role == "admin"
    deactivating = is_active is False and user.is_active
    loses_admin = user.role == "admin" and (demoting or deactivating)
    if loses_admin and await count_active_admins(session) <= 1:
        raise LastAdminError("Cannot remove the last active administrator")

    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    await session.commit()
    await session.refresh(user)
    logger.info(
        "user updated",
        extra={"event": "user_updated", "context": {"user_id": user.id, "role": user.role}},
    )
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    user = await get_by_email(session, email)
    if user is None or not user.hashed_password or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
