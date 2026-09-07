"""Service-account API (ROADMAP R5) — admin management + token auth demo."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db import get_session
from app.models.user import User
from app.services import audit_service, service_account_service

router = APIRouter(prefix="/api/v1/service-accounts", tags=["service-accounts"])


class SACreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    role: str = Field(default="user", pattern="^(user|admin)$")


class SARead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    role: str
    active: bool
    token_prefix: str
    created_at: datetime
    last_used_at: datetime | None


class SACreated(SARead):
    token: str


@router.get("", response_model=list[SARead])
async def list_accounts(
    session: AsyncSession = Depends(get_session), _: User | None = Depends(require_admin)
) -> list[SARead]:
    return [SARead.model_validate(a) for a in await service_account_service.list_accounts(session)]


@router.post("", response_model=SACreated, status_code=201)
async def create_account(
    payload: SACreate,
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(require_admin),
) -> SACreated:
    account, token = await service_account_service.create(
        session, name=payload.name, role=payload.role
    )
    await audit_service.record(
        session,
        action="service_account.create",
        actor=admin.email if admin else "system",
        target=payload.name,
    )
    data = SARead.model_validate(account).model_dump()
    return SACreated(**data, token=token)


@router.post("/{account_id}/revoke")
async def revoke_account(
    account_id: str,
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(require_admin),
) -> dict[str, str]:
    if not await service_account_service.revoke(session, account_id):
        raise HTTPException(status_code=404, detail="service account not found")
    await audit_service.record(
        session,
        action="service_account.revoke",
        actor=admin.email if admin else "system",
        target=account_id,
    )
    return {"status": "revoked"}


@router.get("/whoami")
async def whoami(
    session: AsyncSession = Depends(get_session),
    x_service_token: str | None = Header(default=None),
) -> dict:
    """Authenticate with a service-account token (X-Service-Token header)."""

    account = await service_account_service.verify(session, x_service_token or "")
    if account is None:
        raise HTTPException(status_code=401, detail="invalid service token")
    return {"name": account.name, "role": account.role}
