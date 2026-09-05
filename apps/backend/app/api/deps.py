"""Shared API dependencies: RBAC role gates (ROADMAP PR 27).

Enforcement is governed by ``ATLAS_AUTH_ENFORCE``:

* **off** (default) — local-first, single-operator: endpoints are open and the
  caller is treated as an admin. A token, if present, is still honored for
  attribution.
* **on** — real RBAC: a valid token is required and its role must satisfy the
  gate (``admin`` always passes).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db import get_session
from app.models.user import User

# Optional bearer: never auto-errors, so open mode works without a token.
_optional_bearer = HTTPBearer(auto_error=False)


async def current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Return the authenticated user if a valid token is presented, else None."""

    if credentials is None:
        return None
    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        return None
    user_id = claims.get("sub")
    if not user_id:
        return None
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def require_role(*allowed: str) -> Callable[..., Awaitable[User | None]]:
    """Build a dependency enforcing that the caller has one of ``allowed`` roles.

    ``admin`` always satisfies any gate. In open mode (auth not enforced) the gate
    is permissive and returns the caller if known, else None.
    """

    async def _dep(user: User | None = Depends(current_user_optional)) -> User | None:
        if not get_settings().auth_enforce:
            return user  # open mode: allow (caller may be None)
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        if user.role != "admin" and user.role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return _dep


require_admin = require_role("admin")
require_user = require_role("user")
