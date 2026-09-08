"""Continuous Improvement API (ROADMAP PR 18)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.improvement import ProposalCreate, ProposalList, ProposalRead
from app.services import canary_service, improvement_service
from app.services.canary_service import CanaryError
from app.services.improvement_service import ImprovementStateError

router = APIRouter(prefix="/api/v1/improvements", tags=["improvements"])


@router.post("/proposals", response_model=ProposalRead, status_code=201)
async def create_proposal(
    payload: ProposalCreate,
    session: AsyncSession = Depends(get_session),
) -> ProposalRead:
    proposal = await improvement_service.create_proposal(
        session,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        suite_id=payload.suite_id,
        baseline_model=payload.baseline_model,
        candidate_model=payload.candidate_model,
        change=payload.change,
    )
    return ProposalRead.model_validate(proposal)


@router.post("/auto-propose", response_model=ProposalList, status_code=201)
async def auto_propose(
    session: AsyncSession = Depends(get_session),
) -> ProposalList:
    """Let ATLAS generate improvement proposals itself (candidate models vs default).

    Each created proposal auto-runs its experiment; you are left with approve/apply.
    """

    created = await improvement_service.propose_now(session)
    return ProposalList(
        items=[ProposalRead.model_validate(p) for p in created], total=len(created)
    )


@router.get("/proposals", response_model=ProposalList)
async def list_proposals(
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> ProposalList:
    items = await improvement_service.list_proposals(session, status=status_filter)
    return ProposalList(
        items=[ProposalRead.model_validate(p) for p in items], total=len(items)
    )


@router.get("/proposals/{proposal_id}", response_model=ProposalRead)
async def get_proposal(
    proposal_id: str,
    session: AsyncSession = Depends(get_session),
) -> ProposalRead:
    proposal = await improvement_service.get_proposal(session, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return ProposalRead.model_validate(proposal)


@router.post("/proposals/{proposal_id}/experiment", response_model=ProposalRead)
async def run_experiment(
    proposal_id: str,
    session: AsyncSession = Depends(get_session),
) -> ProposalRead:
    proposal = await improvement_service.get_proposal(session, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    try:
        proposal, _approval = await improvement_service.run_experiment(session, proposal)
    except ImprovementStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ProposalRead.model_validate(proposal)


@router.post("/proposals/{proposal_id}/apply", response_model=ProposalRead)
async def apply_proposal(
    proposal_id: str,
    session: AsyncSession = Depends(get_session),
) -> ProposalRead:
    """Apply an APPROVED proposal (governed; 409 if not approved)."""

    proposal = await improvement_service.get_proposal(session, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    try:
        proposal = await improvement_service.apply_proposal(session, proposal)
    except ImprovementStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ProposalRead.model_validate(proposal)


@router.post("/proposals/{proposal_id}/canary", response_model=ProposalRead)
async def start_canary(
    proposal_id: str,
    session: AsyncSession = Depends(get_session),
) -> ProposalRead:
    """Roll out an APPROVED proposal to a watched canary window (R6)."""

    proposal = await improvement_service.get_proposal(session, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    try:
        proposal = await canary_service.start(session, proposal)
    except CanaryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ProposalRead.model_validate(proposal)


@router.post("/proposals/{proposal_id}/canary/evaluate", response_model=ProposalRead)
async def evaluate_canary(
    proposal_id: str,
    session: AsyncSession = Depends(get_session),
) -> ProposalRead:
    """Run the health gate: promote (APPLIED) or auto-rollback (ROLLED_BACK)."""

    proposal = await improvement_service.get_proposal(session, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    try:
        proposal = await canary_service.evaluate(session, proposal)
    except CanaryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ProposalRead.model_validate(proposal)
