"""Node federation API (spec §8, §15).

Nodes authenticate to the control plane with a shared join token (least
privilege, §13). When ``ATLAS_NODE_JOIN_TOKEN`` is unset the endpoints are open
-- intended for local development only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import get_session
from app.models.node_enrollment import EnrollmentStatus
from app.schemas.node import NodeHeartbeat, NodeList, NodeRead, NodeRegister
from app.schemas.task import TaskRead
from app.services import enrollment_service, node_service

router = APIRouter(prefix="/api/v1/nodes", tags=["nodes"])


async def require_node_token(x_node_token: str | None = Header(default=None)) -> None:
    """Validate the node join token if one is configured."""

    expected = get_settings().node_join_token
    if not expected:
        return  # open in development
    if x_node_token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing node token")


async def _require_enrollment(
    node_id: str,
    x_node_token: str | None,
    session: AsyncSession,
    *,
    for_claim: bool,
) -> None:
    """Enforce per-node enrollment when enabled (ROADMAP PR 6).

    Off by default (``node_enrollment_required=False``) so the shared-join-token
    flow is unchanged. When on: the presented token must map to this node's
    enrollment, it must be active (not rejected/revoked), and claiming work
    additionally requires an APPROVED enrollment.
    """

    if not get_settings().node_enrollment_required:
        return
    enrollment = await enrollment_service.authenticate(session, x_node_token)
    if enrollment is None or enrollment.node_id != node_id:
        raise HTTPException(status_code=401, detail="Invalid or missing enrollment token")
    status_enum = EnrollmentStatus(enrollment.status)
    if not status_enum.is_active:
        raise HTTPException(
            status_code=403, detail=f"node enrollment is {enrollment.status.lower()}"
        )
    if for_claim and not status_enum.can_claim:
        raise HTTPException(
            status_code=403, detail="node enrollment awaiting approval; cannot claim work yet"
        )


def _to_read(node) -> NodeRead:
    read = NodeRead.model_validate(node)
    read.online = node_service.is_online(node)
    return read


@router.get("", response_model=NodeList)
async def list_nodes(session: AsyncSession = Depends(get_session)) -> NodeList:
    nodes = await node_service.list_nodes(session)
    items = [_to_read(n) for n in nodes]
    return NodeList(
        items=items,
        total=len(items),
        online=sum(1 for i in items if i.online),
    )


@router.post("/register", response_model=NodeRead, status_code=status.HTTP_201_CREATED)
async def register_node(
    payload: NodeRegister,
    session: AsyncSession = Depends(get_session),
    x_node_token: str | None = Header(default=None),
    _: None = Depends(require_node_token),
) -> NodeRead:
    await _require_enrollment(payload.node_id, x_node_token, session, for_claim=False)
    node = await node_service.register_node(session, payload)
    return _to_read(node)


@router.get("/{ref}", response_model=NodeRead)
async def get_node(
    ref: str,
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    node = await node_service.get_node_by_ref(session, ref)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return _to_read(node)


@router.post("/{ref}/claim-task", response_model=TaskRead | None)
async def claim_task(
    ref: str,
    session: AsyncSession = Depends(get_session),
    x_node_token: str | None = Header(default=None),
    _: None = Depends(require_node_token),
) -> TaskRead | None:
    """A node claims the next task matching its capabilities (spec §6, §8)."""

    node = await node_service.get_node_by_ref(session, ref)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found; register first")
    await _require_enrollment(node.node_id, x_node_token, session, for_claim=True)
    task = await node_service.claim_task(session, node)
    return TaskRead.model_validate(task) if task is not None else None


@router.post("/{ref}/heartbeat", response_model=NodeRead)
async def node_heartbeat(
    ref: str,
    payload: NodeHeartbeat,
    session: AsyncSession = Depends(get_session),
    x_node_token: str | None = Header(default=None),
    _: None = Depends(require_node_token),
) -> NodeRead:
    node = await node_service.get_node_by_ref(session, ref)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found; register first")
    await _require_enrollment(node.node_id, x_node_token, session, for_claim=False)
    node = await node_service.heartbeat(session, node, payload)
    return _to_read(node)
