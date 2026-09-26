"""Runtime Management API — Runtimes, Nodes, Fleet, Models, Deployments, Environments.

Runtime domain: AI model runtimes (Ollama, llama.cpp, vLLM), node management,
fleet orchestration, model deployments, and environment configuration.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.runtime import (
    AliasList,
    AliasUpsert,
    DeploymentCreate,
    DeploymentList,
    DeploymentUpdate,
    EnvironmentCreate,
    EnvironmentList,
    EnvironmentRead,
    EnvironmentUpdate,
    FleetRead,
    FleetUpdate,
    ModelAliasRead,
    ModelDeploymentRead,
    ModelRead,
    PolicyList,
    PolicyUpsert,
    RoutingPolicyRead,
    RuntimeCreate,
    RuntimeHealthRead,
    RuntimeList,
    RuntimeRead,
    RuntimeUpdate,
)
from app.schemas.node import NodeEnrollmentRead, NodeList, NodeRead, NodeUpdate
from app.domains.runtime import deployment, environment, runtime
from app.services import benchmark_service, learning_service, runtime_service, node_service

router = APIRouter(tags=["runtime"])

# ============================================================================
# Runtimes
# ============================================================================

runtimes_router = APIRouter(prefix="/api/v1", tags=["runtimes"])


@runtimes_router.get("/runtimes", response_model=RuntimeList)
async def list_runtimes(session: AsyncSession = Depends(get_session)) -> RuntimeList:
    items = await runtime_service.list_runtimes(session)
    return RuntimeList(items=[RuntimeRead.model_validate(r) for r in items], total=len(items))


@runtimes_router.post("/runtimes", response_model=RuntimeRead, status_code=201)
async def create_runtime(
    payload: RuntimeCreate, session: AsyncSession = Depends(get_session)
) -> RuntimeRead:
    if await runtime_service.get_runtime_by_name(session, payload.name):
        raise HTTPException(status_code=409, detail="runtime name already exists")
    rt = await runtime_service.create_runtime(session, **payload.model_dump())
    return RuntimeRead.model_validate(rt)


@runtimes_router.patch("/runtimes/{runtime_id}", response_model=RuntimeRead)
async def update_runtime(
    runtime_id: str, payload: RuntimeUpdate, session: AsyncSession = Depends(get_session)
) -> RuntimeRead:
    rt = await runtime_service.get_runtime(session, runtime_id)
    if rt is None:
        raise HTTPException(status_code=404, detail="runtime not found")
    rt = await runtime_service.update_runtime(
        session, rt, **payload.model_dump(exclude_unset=True)
    )
    return RuntimeRead.model_validate(rt)


@runtimes_router.delete("/runtimes/{runtime_id}")
async def delete_runtime(
    runtime_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    rt = await runtime_service.get_runtime(session, runtime_id)
    if rt is None:
        raise HTTPException(status_code=404, detail="runtime not found")
    await runtime_service.delete_runtime(session, rt)
    return {"status": "deleted"}


@runtimes_router.get("/runtimes-health", response_model=list[RuntimeHealthRead])
async def runtimes_health(session: AsyncSession = Depends(get_session)):
    return [RuntimeHealthRead.model_validate(r) for r in await runtime_service.list_runtimes(session)]


# Deployments (partial - see deployment.py for full API)
@runtimes_router.get("/deployments", response_model=DeploymentList)
async def list_deployments(session: AsyncSession = Depends(get_session)) -> DeploymentList:
    items = await runtime_service.list_deployments(session)
    return DeploymentList(
        items=[ModelDeploymentRead.model_validate(d) for d in items], total=len(items)
    )


@runtimes_router.post("/deployments", response_model=ModelDeploymentRead, status_code=201)
async def create_deployment(
    payload: DeploymentCreate, session: AsyncSession = Depends(get_session)
) -> ModelDeploymentRead:
    dep = await runtime_service.create_deployment(session, **payload.model_dump())
    return ModelDeploymentRead.model_validate(dep)


# Aliases
@runtimes_router.get("/aliases", response_model=AliasList)
async def list_aliases(session: AsyncSession = Depends(get_session)) -> AliasList:
    items = await runtime_service.list_aliases(session)
    return AliasList(items=[ModelAliasRead.model_validate(a) for a in items], total=len(items))


@runtimes_router.put("/aliases", response_model=ModelAliasRead)
async def upsert_alias(
    payload: AliasUpsert, session: AsyncSession = Depends(get_session)
) -> ModelAliasRead:
    alias = await runtime_service.upsert_alias(session, **payload.model_dump())
    return ModelAliasRead.model_validate(alias)


# Routing policies
@runtimes_router.get("/policies", response_model=PolicyList)
async def list_policies(session: AsyncSession = Depends(get_session)) -> PolicyList:
    items = await runtime_service.list_policies(session)
    return PolicyList(items=[RoutingPolicyRead.model_validate(p) for p in items], total=len(items))


@runtimes_router.put("/policies", response_model=RoutingPolicyRead)
async def upsert_policy(
    payload: PolicyUpsert, session: AsyncSession = Depends(get_session)
) -> RoutingPolicyRead:
    policy = await runtime_service.upsert_policy(session, **payload.model_dump())
    return RoutingPolicyRead.model_validate(policy)


# Benchmarking
@runtimes_router.post("/runtimes/{runtime_id}/benchmark")
async def benchmark_runtime(runtime_id: str, session: AsyncSession = Depends(get_session)):
    rt = await runtime_service.get_runtime(session, runtime_id)
    if rt is None:
        raise HTTPException(status_code=404, detail="runtime not found")
    result = await benchmark_service.benchmark_runtime(session, rt)
    return result


# ============================================================================
# Nodes
# ============================================================================

nodes_router = APIRouter(prefix="/api/v1/nodes", tags=["nodes"])


@nodes_router.get("", response_model=NodeList)
async def list_nodes(session: AsyncSession = Depends(get_session)) -> NodeList:
    items = await node_service.list_nodes(session)
    return NodeList(items=[NodeRead.model_validate(n) for n in items], total=len(items))


@nodes_router.get("/{node_id}", response_model=NodeRead)
async def get_node(node_id: str, session: AsyncSession = Depends(get_session)) -> NodeRead:
    node = await node_service.get_node(session, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return NodeRead.model_validate(node)


@nodes_router.patch("/{node_id}", response_model=NodeRead)
async def update_node(
    node_id: str, payload: NodeUpdate, session: AsyncSession = Depends(get_session)
) -> NodeRead:
    node = await node_service.get_node(session, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    node = await node_service.update_node(
        session, node, **payload.model_dump(exclude_unset=True)
    )
    return NodeRead.model_validate(node)


# ============================================================================
# Fleet
# ============================================================================

fleet_router = APIRouter(prefix="/api/v1/fleet", tags=["fleet"])


@fleet_router.get("", response_model=FleetRead)
async def get_fleet_summary(session: AsyncSession = Depends(get_session)) -> FleetRead:
    nodes = await node_service.list_nodes(session)
    return FleetRead(
        total_nodes=len(nodes),
        healthy_nodes=sum(1 for n in nodes if n.status == "online"),
        total_capacity=sum(n.capacity or 0 for n in nodes),
    )


@fleet_router.patch("", response_model=FleetRead)
async def update_fleet(
    payload: FleetUpdate, session: AsyncSession = Depends(get_session)
) -> FleetRead:
    # Fleet-level settings
    nodes = await node_service.list_nodes(session)
    return FleetRead(
        total_nodes=len(nodes),
        healthy_nodes=sum(1 for n in nodes if n.status == "online"),
        total_capacity=sum(n.capacity or 0 for n in nodes),
    )


# ============================================================================
# Models
# ============================================================================

models_router = APIRouter(prefix="/api/v1/models", tags=["models"])


@models_router.get("", response_model=list[ModelRead])
async def list_models(session: AsyncSession = Depends(get_session)):
    return await runtime_service.list_models(session)


# ============================================================================
# Environments
# ============================================================================

environments_router = APIRouter(prefix="/api/v1/environments", tags=["environments"])


@environments_router.get("", response_model=EnvironmentList)
async def list_environments(session: AsyncSession = Depends(get_session)) -> EnvironmentList:
    items = await environment.list_environments(session)
    return EnvironmentList(
        items=[EnvironmentRead.model_validate(e) for e in items], total=len(items)
    )


@environments_router.post("", response_model=EnvironmentRead, status_code=201)
async def create_environment(
    payload: EnvironmentCreate, session: AsyncSession = Depends(get_session)
) -> EnvironmentRead:
    env = await environment.create_environment(session, **payload.model_dump())
    return EnvironmentRead.model_validate(env)


@environments_router.patch("/{env_id}", response_model=EnvironmentRead)
async def update_environment(
    env_id: str, payload: EnvironmentUpdate, session: AsyncSession = Depends(get_session)
) -> EnvironmentRead:
    env = await environment.get_environment(session, env_id)
    if env is None:
        raise HTTPException(status_code=404, detail="environment not found")
    env = await environment.update_environment(
        session, env, **payload.model_dump(exclude_unset=True)
    )
    return EnvironmentRead.model_validate(env)


@environments_router.delete("/{env_id}")
async def delete_environment(
    env_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    env = await environment.get_environment(session, env_id)
    if env is None:
        raise HTTPException(status_code=404, detail="environment not found")
    await environment.delete_environment(session, env)
    return {"status": "deleted"}


# ============================================================================
# Aggregate all runtime routers
# ============================================================================

router.include_router(runtimes_router)
router.include_router(nodes_router)
router.include_router(fleet_router)
router.include_router(models_router)
router.include_router(environments_router)
