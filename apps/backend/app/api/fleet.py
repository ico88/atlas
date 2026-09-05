"""Fleet compliance & auto-remediation API (ROADMAP PR 24 / PR 25)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.fleet import (
    ComplianceReport,
    DesiredState,
    RemediateRequest,
    RemediationEventRead,
)
from app.services import compliance_service, remediation_service
from app.services.remediation_service import RemediationError

router = APIRouter(prefix="/api/v1/fleet", tags=["fleet"])


async def _report_with_diagnosis(session: AsyncSession) -> dict:
    report = await compliance_service.fleet_report(session)
    for nr in report["nodes"]:
        dx = remediation_service.diagnose(nr)
        nr["diagnosis"] = dx["diagnosis"]
        nr["recommended_action"] = dx["recommended_action"]
    return report


@router.get("/compliance", response_model=ComplianceReport)
async def get_compliance(session: AsyncSession = Depends(get_session)) -> ComplianceReport:
    return ComplianceReport.model_validate(await _report_with_diagnosis(session))


@router.get("/desired", response_model=DesiredState)
async def get_desired(session: AsyncSession = Depends(get_session)) -> DesiredState:
    return DesiredState.model_validate(await compliance_service.get_desired(session))


@router.put("/desired", response_model=DesiredState)
async def set_desired(
    payload: DesiredState,
    session: AsyncSession = Depends(get_session),
) -> DesiredState:
    updated = await compliance_service.set_desired(session, payload.model_dump())
    return DesiredState.model_validate(updated)


@router.post("/remediate", response_model=RemediationEventRead)
async def remediate(
    payload: RemediateRequest,
    session: AsyncSession = Depends(get_session),
) -> RemediationEventRead:
    try:
        if payload.action == "remediate":
            desired = await compliance_service.get_desired(session)
            ev = await remediation_service.remediate(
                session, payload.node_ref, target_version=desired.get("target_version", "")
            )
        elif payload.action == "quarantine":
            ev = await remediation_service.quarantine(
                session, payload.node_ref, reason=payload.reason
            )
        else:  # reinstate
            ev = await remediation_service.reinstate(session, payload.node_ref)
    except RemediationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RemediationEventRead.model_validate(ev)


@router.post("/auto-remediate", response_model=ComplianceReport)
async def auto_remediate(session: AsyncSession = Depends(get_session)) -> ComplianceReport:
    await remediation_service.auto_remediate(session)
    return ComplianceReport.model_validate(await _report_with_diagnosis(session))


@router.get("/remediation-events", response_model=list[RemediationEventRead])
async def list_events(session: AsyncSession = Depends(get_session)) -> list[RemediationEventRead]:
    events = await remediation_service.list_events(session)
    return [RemediationEventRead.model_validate(e) for e in events]
