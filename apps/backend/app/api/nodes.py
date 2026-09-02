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
from app.schemas.node import NodeHeartbeat, NodeList, NodeRead, NodeRegister
from app.services import node_service

router = APIRouter(prefix="/api/v1/nodes", tags=["nodes"])


async def require_node_token(x_node_token: str | None = Header(default=None)) -> None:
    """Validate the node join token if one is configured."""

    expected = get_settings().node_join_token
    if not expected:
        return  # open in development
    if x_node_token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing node token")


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
    _: None = Depends(require_node_token),
) -> NodeRead:
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


@router.post("/{ref}/heartbeat", response_model=NodeRead)
async def node_heartbeat(
    ref: str,
    payload: NodeHeartbeat,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_node_token),
) -> NodeRead:
    node = await node_service.get_node_by_ref(session, ref)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found; register first")
    node = await node_service.heartbeat(session, node, payload)
    return _to_read(node)
