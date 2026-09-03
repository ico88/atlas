"""Node enrollment management API (ROADMAP PR 6).

Operator endpoints to invite, approve, reject, revoke and rotate per-node
credentials. The one-time plaintext token is returned only by create and rotate.
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
from app.services import enrollment_service

router = APIRouter(prefix="/api/v1/enrollments", tags=["node-enrollment"])


def _with_token(enrollment, token: str) -> EnrollmentWithToken:
    data = EnrollmentRead.model_validate(enrollment).model_dump()
    return EnrollmentWithToken(**data, token=token)


@router.post("", response_model=EnrollmentWithToken, status_code=201)
async def create_enrollment(
    payload: EnrollmentCreate,
    session: AsyncSession = Depends(get_session),
) -> EnrollmentWithToken:
    try:
        enrollment, token = await enrollment_service.create_enrollment(
            session,
            node_id=payload.node_id,
            label=payload.label,
            created_by=payload.created_by,
            auto_approve=payload.auto_approve,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _with_token(enrollment, token)


@router.get("", response_model=EnrollmentList)
async def list_enrollments(session: AsyncSession = Depends(get_session)) -> EnrollmentList:
    items, total = await enrollment_service.list_enrollments(session)
    return EnrollmentList(items=[EnrollmentRead.model_validate(e) for e in items], total=total)


async def _load(session: AsyncSession, enrollment_id: str):
    enrollment = await enrollment_service.get_enrollment(session, enrollment_id)
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return enrollment


@router.post("/{enrollment_id}/approve", response_model=EnrollmentRead)
async def approve(
    enrollment_id: str,
    payload: EnrollmentDecision | None = None,
    session: AsyncSession = Depends(get_session),
) -> EnrollmentRead:
    enrollment = await _load(session, enrollment_id)
    decided_by = payload.decided_by if payload else None
    return EnrollmentRead.model_validate(
        await enrollment_service.approve(session, enrollment, decided_by=decided_by)
    )


@router.post("/{enrollment_id}/reject", response_model=EnrollmentRead)
async def reject(
    enrollment_id: str,
    payload: EnrollmentDecision | None = None,
    session: AsyncSession = Depends(get_session),
) -> EnrollmentRead:
    enrollment = await _load(session, enrollment_id)
    decided_by = payload.decided_by if payload else None
    return EnrollmentRead.model_validate(
        await enrollment_service.reject(session, enrollment, decided_by=decided_by)
    )


@router.post("/{enrollment_id}/revoke", response_model=EnrollmentRead)
async def revoke(
    enrollment_id: str,
    payload: EnrollmentDecision | None = None,
    session: AsyncSession = Depends(get_session),
) -> EnrollmentRead:
    enrollment = await _load(session, enrollment_id)
    decided_by = payload.decided_by if payload else None
    return EnrollmentRead.model_validate(
        await enrollment_service.revoke(session, enrollment, decided_by=decided_by)
    )


@router.post("/{enrollment_id}/rotate", response_model=EnrollmentWithToken)
async def rotate(
    enrollment_id: str,
    session: AsyncSession = Depends(get_session),
) -> EnrollmentWithToken:
    enrollment = await _load(session, enrollment_id)
    rotated, token = await enrollment_service.rotate(session, enrollment)
    return _with_token(rotated, token)
