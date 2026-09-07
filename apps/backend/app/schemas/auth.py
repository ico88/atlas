"""Auth schemas (spec §15)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    code: str | None = None  # TOTP code, required when the user has MFA enabled


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str | None
    role: str
    is_active: bool
    mfa_enabled: bool = False
    created_at: datetime


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaCode(BaseModel):
    code: str
