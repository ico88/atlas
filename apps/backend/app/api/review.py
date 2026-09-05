"""Critical Review API (ROADMAP PR 19)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.review import ReviewList, ReviewRead, ReviewRequest, ReviewSummary
from app.services import review_service

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])


@router.post("", response_model=ReviewRead, status_code=201)
async def run_review(
    payload: ReviewRequest,
    session: AsyncSession = Depends(get_session),
) -> ReviewRead:
    review = await review_service.run_review(
        session,
        prompt=payload.prompt,
        references=payload.references,
        max_rounds=payload.max_rounds,
        model=payload.model,
    )
    return ReviewRead.model_validate(review)


@router.get("", response_model=ReviewList)
async def list_reviews(session: AsyncSession = Depends(get_session)) -> ReviewList:
    items = await review_service.list_reviews(session)
    return ReviewList(
        items=[ReviewSummary.model_validate(r) for r in items], total=len(items)
    )


@router.get("/{review_id}", response_model=ReviewRead)
async def get_review(
    review_id: str,
    session: AsyncSession = Depends(get_session),
) -> ReviewRead:
    review = await review_service.get_review(session, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return ReviewRead.model_validate(review)
