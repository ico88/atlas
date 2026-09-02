"""Model registry (spec §14: providers, models; M2)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import router
from app.models.provider import LLMModel

logger = logging.getLogger(__name__)


async def list_models(session: AsyncSession) -> list[LLMModel]:
    rows = await session.execute(
        select(LLMModel).order_by(LLMModel.provider.asc(), LLMModel.name.asc())
    )
    return list(rows.scalars().all())


async def refresh_models(session: AsyncSession) -> list[LLMModel]:
    """Discover models from available providers and upsert them (idempotent)."""

    discovered: dict[tuple[str, str], LLMModel] = {}
    for provider in await router.available_providers():
        for info in await provider.list_models():
            key = (info.provider, info.name)
            existing = (
                await session.execute(
                    select(LLMModel).where(
                        LLMModel.provider == info.provider, LLMModel.name == info.name
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = LLMModel(provider=info.provider, name=info.name)
                session.add(existing)
            existing.family = info.family
            existing.context_length = info.context_length
            existing.available = True
            discovered[key] = existing

    # Mark models no longer reported as unavailable (keep history).
    for model in await list_models(session):
        if (model.provider, model.name) not in discovered:
            model.available = False

    await session.commit()
    logger.info(
        "model registry refreshed",
        extra={"event": "models_refreshed", "context": {"count": len(discovered)}},
    )
    return await list_models(session)
