"""Secret manager API (ROADMAP R5) — admin-only, encrypted at rest.

Listing returns names/metadata only (never plaintext); reading a value back is a
separate, explicit admin action and is audited.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db import get_session
from app.models.user import User
from app.services import audit_service, secret_service

router = APIRouter(prefix="/api/v1/secrets", tags=["secrets"])


class SecretUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1)
    description: str | None = Field(default=None, max_length=255)


class SecretMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str | None
    updated_at: datetime


class SecretList(BaseModel):
    items: list[SecretMeta]
    total: int


@router.get("", response_model=SecretList)
async def list_secrets(
    session: AsyncSession = Depends(get_session), _: User | None = Depends(require_admin)
) -> SecretList:
    items = await secret_service.list_secrets(session)
    return SecretList(items=[SecretMeta.model_validate(s) for s in items], total=len(items))


@router.put("", response_model=SecretMeta)
async def upsert_secret(
    payload: SecretUpsert,
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(require_admin),
) -> SecretMeta:
    row = await secret_service.set_secret(
        session, name=payload.name, value=payload.value, description=payload.description
    )
    await audit_service.record(
        session,
        action="secret.set",
        actor=admin.email if admin else "system",
        target=payload.name,
    )
    return SecretMeta.model_validate(row)


@router.get("/{name}/reveal")
async def reveal_secret(
    name: str,
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(require_admin),
) -> dict:
    value = await secret_service.get_secret(session, name)
    if value is None:
        raise HTTPException(status_code=404, detail="secret not found")
    await audit_service.record(
        session,
        action="secret.reveal",
        actor=admin.email if admin else "system",
        target=name,
    )
    return {"name": name, "value": value}


@router.delete("/{name}")
async def delete_secret(
    name: str,
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(require_admin),
) -> dict[str, str]:
    if not await secret_service.delete_secret(session, name):
        raise HTTPException(status_code=404, detail="secret not found")
    await audit_service.record(
        session, action="secret.delete", actor=admin.email if admin else "system", target=name
    )
    return {"status": "deleted"}
