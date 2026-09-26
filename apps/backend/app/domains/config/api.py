"""Configuration & Enrollment API.

Config domain: Settings overrides and node enrollment management.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.enrollment import (
    EnrollmentCreate,
    EnrollmentDecision,
    EnrollmentList,
    EnrollmentRead,
    EnrollmentWithToken,
)
from app.schemas.settings import WebConfigRead, WebConfigUpdate
from app.domains.config import autoconfig, enrollment, settings

router = APIRouter(tags=["config"])


# Settings routes


@router.get("/api/v1/settings/web", response_model=WebConfigRead)
async def get_web_config() -> WebConfigRead:
    return WebConfigRead.model_validate(await settings.get_web_config_public())


@router.put("/api/v1/settings/web", response_model=WebConfigRead)
async def update_web_config(payload: WebConfigUpdate) -> WebConfigRead:
    patch = payload.model_dump(exclude_none=True)
    return WebConfigRead.model_validate(await settings.set_web_config(patch))


# Enrollment routes


def _with_token(enrollment, token: str) -> EnrollmentWithToken:
    data = EnrollmentRead.model_validate(enrollment).model_dump()
    return EnrollmentWithToken(**data, token=token)


@router.post("/api/v1/enrollments", response_model=EnrollmentWithToken, status_code=201)
async def create_enrollment(
    payload: EnrollmentCreate,
    session: AsyncSession = Depends(get_session),
) -> EnrollmentWithToken:
    try:
        enr, token = await enrollment.create_enrollment(
            session,
            node_id=payload.node_id,
            label=payload.label,
            created_by=payload.created_by,
            auto_approve=payload.auto_approve,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _with_token(enr, token)


@router.get("/api/v1/enrollments", response_model=EnrollmentList)
async def list_enrollments(session: AsyncSession = Depends(get_session)) -> EnrollmentList:
    items, total = await enrollment.list_enrollments(session)
    return EnrollmentList(items=[EnrollmentRead.model_validate(e) for e in items], total=total)


async def _load(session: AsyncSession, enrollment_id: str):
    enr = await enrollment.get_enrollment(session, enrollment_id)
    if enr is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return enr


@router.post("/api/v1/enrollments/{enrollment_id}/approve", response_model=EnrollmentRead)
async def approve(
    enrollment_id: str,
    payload: EnrollmentDecision | None = None,
    session: AsyncSession = Depends(get_session),
) -> EnrollmentRead:
    enr = await _load(session, enrollment_id)
    decided_by = payload.decided_by if payload else None
    return EnrollmentRead.model_validate(
        await enrollment.approve(session, enr, decided_by=decided_by)
    )


@router.post("/api/v1/enrollments/{enrollment_id}/reject", response_model=EnrollmentRead)
async def reject(
    enrollment_id: str,
    payload: EnrollmentDecision | None = None,
    session: AsyncSession = Depends(get_session),
) -> EnrollmentRead:
    enr = await _load(session, enrollment_id)
    decided_by = payload.decided_by if payload else None
    return EnrollmentRead.model_validate(
        await enrollment.reject(session, enr, decided_by=decided_by)
    )


@router.post("/api/v1/enrollments/{enrollment_id}/revoke", response_model=EnrollmentRead)
async def revoke(
    enrollment_id: str,
    payload: EnrollmentDecision | None = None,
    session: AsyncSession = Depends(get_session),
) -> EnrollmentRead:
    enr = await _load(session, enrollment_id)
    decided_by = payload.decided_by if payload else None
    return EnrollmentRead.model_validate(
        await enrollment.revoke(session, enr, decided_by=decided_by)
    )


@router.post("/api/v1/enrollments/{enrollment_id}/rotate", response_model=EnrollmentWithToken)
async def rotate(
    enrollment_id: str,
    session: AsyncSession = Depends(get_session),
) -> EnrollmentWithToken:
    enr = await _load(session, enrollment_id)
    rotated, token = await enrollment.rotate(session, enr)
    return _with_token(rotated, token)
