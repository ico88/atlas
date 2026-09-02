"""Feedback capture (spec §14: feedback)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import Feedback


async def add_feedback(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: str,
    rating: int = 0,
    comment: str | None = None,
    user_id: str | None = None,
) -> Feedback:
    fb = Feedback(
        target_type=target_type,
        target_id=target_id,
        rating=rating,
        comment=comment,
        user_id=user_id,
    )
    session.add(fb)
    await session.commit()
    await session.refresh(fb)
    return fb


async def list_feedback(
    session: AsyncSession, *, target_id: str | None = None
) -> list[Feedback]:
    query = select(Feedback).order_by(Feedback.created_at.desc())
    if target_id:
        query = query.where(Feedback.target_id == target_id)
    return list((await session.execute(query)).scalars().all())
