"""Governance API — Users, Auth, Approvals, Compliance, Security, PKI, Secrets.

Governance domain: User management, authentication, approvals, compliance,
security policies, secret management, and PKI/certificates.
"""

from __future__ import annotations

import jwt
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core import totp
from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token
from app.db import get_session
from app.models.approval import ApprovalStatus
from app.models.user import User
from app.schemas.approval import ApprovalDecision, ApprovalList, ApprovalRead
from app.schemas.auth import (
    LoginRequest,
    MfaCode,
    MfaSetupResponse,
    TokenResponse,
    UserRead,
)
from app.schemas.user import UserCreate, UserList, UserUpdate
from app.domains.governance import approval, users as users_module, secret, compliance as compliance_module
from app.services import audit_service, pki_service

router = APIRouter(tags=["governance"])
_bearer = HTTPBearer(auto_error=True)

# ============================================================================
# Authentication (auth)
# ============================================================================

auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@auth_router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user = await users_module.authenticate(session, str(payload.email), payload.password)
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
    credentials = Depends(lambda: HTTPBearer(auto_error=True)()),
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


@auth_router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)


@auth_router.post("/mfa/setup", response_model=MfaSetupResponse)
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


@auth_router.post("/mfa/enable", response_model=UserRead)
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


@auth_router.post("/mfa/disable", response_model=UserRead)
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


# ============================================================================
# User Management (users)
# ============================================================================

users_router = APIRouter(
    prefix="/api/v1/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)


@users_router.get("", response_model=UserList)
async def list_users(session: AsyncSession = Depends(get_session)) -> UserList:
    items = await users_module.list_users(session)
    return UserList(
        items=[UserRead.model_validate(u) for u in items],
        total=len(items),
        auth_enforced=get_settings().auth_enforce,
    )


@users_router.post("", response_model=UserRead, status_code=201)
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> UserRead:
    if await users_module.get_by_email(session, str(payload.email)) is not None:
        raise HTTPException(status_code=409, detail="A user with that email already exists")
    user = await users_module.create_user(
        session,
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
    )
    return UserRead.model_validate(user)


@users_router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
) -> UserRead:
    user = await users_module.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        user = await users_module.update_user(
            session, user, role=payload.role, is_active=payload.is_active
        )
    except users_module.LastAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return UserRead.model_validate(user)


# ============================================================================
# Approvals
# ============================================================================

approvals_router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


@approvals_router.get("", response_model=ApprovalList)
async def list_approvals(
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> ApprovalList:
    items = await approval.list_approvals(session, status=status_filter)
    return ApprovalList(
        items=[ApprovalRead.model_validate(a) for a in items], total=len(items)
    )


@approvals_router.post("/{approval_id}/approve", response_model=ApprovalRead)
async def approve(
    approval_id: str,
    decision: ApprovalDecision | None = None,
    session: AsyncSession = Depends(get_session),
) -> ApprovalRead:
    apr = await approval.get_approval(session, approval_id)
    if apr is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if apr.status != ApprovalStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="Approval already decided")
    decision = decision or ApprovalDecision()
    apr = await approval.approve(
        session, apr, decided_by=decision.decided_by, reason=decision.reason
    )
    return ApprovalRead.model_validate(apr)


@approvals_router.post("/{approval_id}/reject", response_model=ApprovalRead)
async def reject(
    approval_id: str,
    decision: ApprovalDecision | None = None,
    session: AsyncSession = Depends(get_session),
) -> ApprovalRead:
    apr = await approval.get_approval(session, approval_id)
    if apr is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if apr.status != ApprovalStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="Approval already decided")
    decision = decision or ApprovalDecision()
    apr = await approval.reject(
        session, apr, decided_by=decision.decided_by, reason=decision.reason
    )
    return ApprovalRead.model_validate(apr)


# ============================================================================
# Secrets
# ============================================================================

class SecretUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1)
    description: str | None = Field(default=None, max_length=255)


class SecretMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    description: str | None
    updated_at: datetime


class SecretList(BaseModel):
    items: list[SecretMeta]
    total: int


secrets_router = APIRouter(prefix="/api/v1/secrets", tags=["secrets"])


@secrets_router.get("", response_model=SecretList)
async def list_secrets(
    session: AsyncSession = Depends(get_session), _: User | None = Depends(require_admin)
) -> SecretList:
    items = await secret.list_secrets(session)
    return SecretList(items=[SecretMeta.model_validate(s) for s in items], total=len(items))


@secrets_router.put("", response_model=SecretMeta)
async def upsert_secret(
    payload: SecretUpsert,
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(require_admin),
) -> SecretMeta:
    row = await secret.set_secret(
        session, name=payload.name, value=payload.value, description=payload.description
    )
    await audit_service.record(
        session,
        action="secret.set",
        actor=admin.email if admin else "system",
        target=payload.name,
    )
    return SecretMeta.model_validate(row)


@secrets_router.get("/{name}/reveal")
async def reveal_secret(
    name: str,
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(require_admin),
) -> dict:
    value = await secret.get_secret(session, name)
    if value is None:
        raise HTTPException(status_code=404, detail="secret not found")
    await audit_service.record(
        session,
        action="secret.reveal",
        actor=admin.email if admin else "system",
        target=name,
    )
    return {"name": name, "value": value}


@secrets_router.delete("/{name}")
async def delete_secret(
    name: str,
    session: AsyncSession = Depends(get_session),
    admin: User | None = Depends(require_admin),
) -> dict[str, str]:
    if not await secret.delete_secret(session, name):
        raise HTTPException(status_code=404, detail="secret not found")
    await audit_service.record(
        session, action="secret.delete", actor=admin.email if admin else "system", target=name
    )
    return {"status": "deleted"}


# ============================================================================
# PKI / Certificates
# ============================================================================

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


pki_router = APIRouter(prefix="/api/v1/pki", tags=["pki"])


@pki_router.get("/ca")
async def get_ca(session: AsyncSession = Depends(get_session)) -> dict:
    """The CA certificate (public) — the trust root for the ATLAS overlay."""
    return {"ca_pem": await pki_service.ca_cert_pem(session)}


@pki_router.post("/issue")
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


@pki_router.get("/certs", response_model=list[CertRead])
async def list_certs(
    session: AsyncSession = Depends(get_session), _: User | None = Depends(require_admin)
) -> list[CertRead]:
    return [CertRead.model_validate(c) for c in await pki_service.list_certs(session)]


@pki_router.post("/revoke/{serial}")
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


@pki_router.get("/crl")
async def crl(session: AsyncSession = Depends(get_session)) -> dict:
    """Revoked serial numbers — checked by the control plane on mTLS."""
    return {"revoked": await pki_service.revocation_list(session)}


# ============================================================================
# Aggregate all governance routers
# ============================================================================

router.include_router(auth_router)
router.include_router(users_router)
router.include_router(approvals_router)
router.include_router(secrets_router)
router.include_router(pki_router)
