"""Authentication API (spec §15): login and current-user."""

from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import totp
from app.core.security import create_access_token, decode_access_token
from app.db import get_session
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MfaCode,
    MfaSetupResponse,
    TokenResponse,
    UserRead,
)
from app.services import audit_service, user_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=True)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user = await user_service.authenticate(session, str(payload.email), payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Second factor: when MFA is enabled a valid TOTP code is required.
    if user.mfa_enabled:
        if not payload.code:
            raise HTTPException(
                status_code=401, detail="MFA code required", headers={"X-MFA": "required"}
            )
        if not totp.verify(user.mfa_secret or "", payload.code):
            raise HTTPException(status_code=401, detail="Invalid MFA code")
    token = create_access_token(subject=user.id, role=user.role)
    return TokenResponse(access_token=token)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)


@router.post("/mfa/setup", response_model=MfaSetupResponse)
async def mfa_setup(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MfaSetupResponse:
    """Generate a TOTP secret (not yet active) and return it + the otpauth URI."""

    secret = totp.generate_secret()
    current_user.mfa_secret = secret
    current_user.mfa_enabled = False
    await session.commit()
    return MfaSetupResponse(
        secret=secret,
        otpauth_uri=totp.provisioning_uri(secret, current_user.email),
    )


@router.post("/mfa/enable", response_model=UserRead)
async def mfa_enable(
    payload: MfaCode,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserRead:
    """Confirm a code against the pending secret and turn MFA on."""

    if not current_user.mfa_secret:
        raise HTTPException(status_code=400, detail="run /mfa/setup first")
    if not totp.verify(current_user.mfa_secret, payload.code):
        raise HTTPException(status_code=400, detail="invalid code")
    current_user.mfa_enabled = True
    await session.commit()
    await audit_service.record(
        session, action="mfa.enable", actor=current_user.email, target=current_user.id
    )
    await session.refresh(current_user)
    return UserRead.model_validate(current_user)


@router.post("/mfa/disable", response_model=UserRead)
async def mfa_disable(
    payload: MfaCode,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserRead:
    """Turn MFA off (requires a current code) and clear the secret."""

    if not current_user.mfa_enabled:
        return UserRead.model_validate(current_user)
    if not totp.verify(current_user.mfa_secret or "", payload.code):
        raise HTTPException(status_code=400, detail="invalid code")
    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    await session.commit()
    await audit_service.record(
        session, action="mfa.disable", actor=current_user.email, target=current_user.id
    )
    await session.refresh(current_user)
    return UserRead.model_validate(current_user)
