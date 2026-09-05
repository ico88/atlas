"""User management API (ROADMAP PR 27) — admin-gated.

In open mode (auth not enforced) these endpoints work without a token so an
operator can create users and then turn on ``ATLAS_AUTH_ENFORCE``. Once enforced,
they require an admin token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.config import get_settings
from app.db import get_session
from app.schemas.user import UserCreate, UserList, UserRead, UserUpdate
from app.services import user_service
from app.services.user_service import LastAdminError

router = APIRouter(prefix="/api/v1/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=UserList)
async def list_users(session: AsyncSession = Depends(get_session)) -> UserList:
    users = await user_service.list_users(session)
    return UserList(
        items=[UserRead.model_validate(u) for u in users],
        total=len(users),
        auth_enforced=get_settings().auth_enforce,
    )


@router.post("", response_model=UserRead, status_code=201)
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> UserRead:
    if await user_service.get_by_email(session, str(payload.email)) is not None:
        raise HTTPException(status_code=409, detail="A user with that email already exists")
    user = await user_service.create_user(
        session,
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
    )
    return UserRead.model_validate(user)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
) -> UserRead:
    user = await user_service.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        user = await user_service.update_user(
            session, user, role=payload.role, is_active=payload.is_active
        )
    except LastAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return UserRead.model_validate(user)
