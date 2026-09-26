"""Node enrollment service (ROADMAP PR 6): invite, approve, reject, revoke, rotate.

Per-node credentials with a human approval gate. Tokens are high-entropy secrets
stored only as SHA-256 hashes; the plaintext is returned once at mint/rotate time
(an invite code). ``authenticate`` resolves a presented token to its enrollment.
"""

from __future__ import annotations

import hashlib
import logging
import secrets

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.node_enrollment import EnrollmentStatus, NodeEnrollment

logger = logging.getLogger(__name__)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _mint_token() -> tuple[str, str, str]:
    """Return (plaintext, hash, prefix). Prefix is a non-secret display hint."""

    token = secrets.token_urlsafe(32)
    return token, hash_token(token), token[:8]


async def create_enrollment(
    session: AsyncSession,
    *,
    node_id: str,
    label: str | None = None,
    created_by: str | None = None,
    auto_approve: bool = False,
) -> tuple[NodeEnrollment, str]:
    """Create an enrollment (invite) for ``node_id``. Returns (enrollment, token)."""

    existing = (
        await session.execute(select(NodeEnrollment).where(NodeEnrollment.node_id == node_id))
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError(f"enrollment for node_id '{node_id}' already exists")

    token, token_hash, prefix = _mint_token()
    enrollment = NodeEnrollment(
        node_id=node_id,
        label=label,
        status=(EnrollmentStatus.APPROVED if auto_approve else EnrollmentStatus.PENDING).value,
        token_hash=token_hash,
        token_prefix=prefix,
        created_by=created_by,
        decided_by=created_by if auto_approve else None,
        decided_at=utcnow() if auto_approve else None,
    )
    session.add(enrollment)
    await session.commit()
    await session.refresh(enrollment)
    logger.info(
        "node enrollment created",
        extra={"event": "enrollment_created", "context": {"node_id": node_id}},
    )
    return enrollment, token


async def list_enrollments(session: AsyncSession) -> tuple[list[NodeEnrollment], int]:
    items = list(
        (
            await session.execute(
                select(NodeEnrollment).order_by(NodeEnrollment.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    total = int(
        (await session.execute(select(func.count()).select_from(NodeEnrollment))).scalar_one()
    )
    return items, total


async def get_enrollment(session: AsyncSession, enrollment_id: str) -> NodeEnrollment | None:
    return await session.get(NodeEnrollment, enrollment_id)


async def authenticate(session: AsyncSession, token: str | None) -> NodeEnrollment | None:
    """Resolve a presented token to its enrollment (any status). None if unknown."""

    if not token:
        return None
    result = await session.execute(
        select(NodeEnrollment).where(NodeEnrollment.token_hash == hash_token(token))
    )
    enrollment = result.scalar_one_or_none()
    if enrollment is not None:
        enrollment.last_used_at = utcnow()
        await session.commit()
    return enrollment


async def _set_status(
    session: AsyncSession,
    enrollment: NodeEnrollment,
    status: EnrollmentStatus,
    *,
    decided_by: str | None,
) -> NodeEnrollment:
    enrollment.status = status.value
    enrollment.decided_by = decided_by
    enrollment.decided_at = utcnow()
    await session.commit()
    await session.refresh(enrollment)
    logger.info(
        "node enrollment %s",
        status.value.lower(),
        extra={"event": "enrollment_decided", "context": {"node_id": enrollment.node_id}},
    )
    return enrollment


async def approve(
    session: AsyncSession, enrollment: NodeEnrollment, *, decided_by: str | None = None
) -> NodeEnrollment:
    return await _set_status(session, enrollment, EnrollmentStatus.APPROVED, decided_by=decided_by)


async def reject(
    session: AsyncSession, enrollment: NodeEnrollment, *, decided_by: str | None = None
) -> NodeEnrollment:
    return await _set_status(session, enrollment, EnrollmentStatus.REJECTED, decided_by=decided_by)


async def revoke(
    session: AsyncSession, enrollment: NodeEnrollment, *, decided_by: str | None = None
) -> NodeEnrollment:
    return await _set_status(session, enrollment, EnrollmentStatus.REVOKED, decided_by=decided_by)


async def rotate(session: AsyncSession, enrollment: NodeEnrollment) -> tuple[NodeEnrollment, str]:
    """Mint a fresh secret for this enrollment; the old token stops working."""

    token, token_hash, prefix = _mint_token()
    enrollment.token_hash = token_hash
    enrollment.token_prefix = prefix
    enrollment.last_rotated_at = utcnow()
    await session.commit()
    await session.refresh(enrollment)
    logger.info(
        "node enrollment rotated",
        extra={"event": "enrollment_rotated", "context": {"node_id": enrollment.node_id}},
    )
    return enrollment, token
