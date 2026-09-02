"""Manual escalation API (spec §10, §15, M7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.escalation.package import EscalationContext
from app.schemas.escalation import (
    EscalationList,
    EscalationPrepare,
    EscalationRead,
    EscalationSummary,
    EscalationValidate,
    ExternalResponseImport,
)
from app.services import escalation_service

router = APIRouter(prefix="/api/v1", tags=["escalation"])


@router.post("/escalations", response_model=EscalationRead, status_code=201)
async def prepare_escalation(
    payload: EscalationPrepare,
    session: AsyncSession = Depends(get_session),
) -> EscalationRead:
    ctx = None
    if payload.context is not None:
        ctx = EscalationContext(**payload.context.model_dump())
    escalation = await escalation_service.prepare(
        session, objective=payload.objective, target=payload.target, context=ctx
    )
    return EscalationRead.model_validate(escalation)


@router.get("/escalations", response_model=EscalationList)
async def list_escalations(
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> EscalationList:
    items = await escalation_service.list_escalations(session, status=status_filter)
    return EscalationList(
        items=[EscalationSummary.model_validate(e) for e in items], total=len(items)
    )


@router.get("/escalations/{escalation_id}", response_model=EscalationRead)
async def get_escalation(
    escalation_id: str,
    session: AsyncSession = Depends(get_session),
) -> EscalationRead:
    escalation = await escalation_service.get_escalation(session, escalation_id)
    if escalation is None:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return EscalationRead.model_validate(escalation)


@router.post("/external-response/import", response_model=EscalationRead)
async def import_external_response(
    payload: ExternalResponseImport,
    session: AsyncSession = Depends(get_session),
) -> EscalationRead:
    escalation = await escalation_service.get_escalation(session, payload.escalation_id)
    if escalation is None:
        raise HTTPException(status_code=404, detail="Escalation not found")
    escalation = await escalation_service.import_response(session, escalation, payload.response)
    return EscalationRead.model_validate(escalation)


@router.post("/escalations/{escalation_id}/validate", response_model=EscalationRead)
async def validate_escalation(
    escalation_id: str,
    payload: EscalationValidate,
    session: AsyncSession = Depends(get_session),
) -> EscalationRead:
    escalation = await escalation_service.get_escalation(session, escalation_id)
    if escalation is None:
        raise HTTPException(status_code=404, detail="Escalation not found")
    escalation = await escalation_service.validate(
        session,
        escalation,
        approved=payload.approved,
        notes=payload.notes,
        decided_by=payload.decided_by,
    )
    return EscalationRead.model_validate(escalation)
