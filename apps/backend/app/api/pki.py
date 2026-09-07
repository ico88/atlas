"""Internal PKI API (ROADMAP R5) — issue/list/revoke node mTLS certs (admin)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db import get_session
from app.models.user import User
from app.services import audit_service, pki_service

router = APIRouter(prefix="/api/v1/pki", tags=["pki"])


class IssueRequest(BaseModel):
    common_name: str = Field(min_length=1, max_length=255)
    days: int = Field(default=365, ge=1, le=3650)


class CertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    serial: str
    common_name: str
    revoked: bool
    not_after: datetime | None
    created_at: datetime


@router.get("/ca")
async def get_ca(session: AsyncSession = Depends(get_session)) -> dict:
    """The CA certificate (public) — the trust root for the ATLAS overlay."""

    return {"ca_pem": await pki_service.ca_cert_pem(session)}


@router.post("/issue")
async def issue(
    payload: IssueRequest,
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(require_admin),
) -> dict:
    result = await pki_service.issue_cert(session, payload.common_name, days=payload.days)
    await audit_service.record(
        session,
        action="pki.issue",
        actor=admin.email if admin else "system",
        target=payload.common_name,
        detail={"serial": result["serial"]},
    )
    return result


@router.get("/certs", response_model=list[CertRead])
async def list_certs(
    session: AsyncSession = Depends(get_session), _: User | None = Depends(require_admin)
) -> list[CertRead]:
    return [CertRead.model_validate(c) for c in await pki_service.list_certs(session)]


@router.post("/revoke/{serial}")
async def revoke(
    serial: str,
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(require_admin),
) -> dict[str, str]:
    if not await pki_service.revoke(session, serial):
        raise HTTPException(status_code=404, detail="certificate not found")
    await audit_service.record(
        session, action="pki.revoke", actor=admin.email if admin else "system", target=serial
    )
    return {"status": "revoked"}


@router.get("/crl")
async def crl(session: AsyncSession = Depends(get_session)) -> dict:
    """Revoked serial numbers — checked by the control plane on mTLS."""

    return {"revoked": await pki_service.revocation_list(session)}
